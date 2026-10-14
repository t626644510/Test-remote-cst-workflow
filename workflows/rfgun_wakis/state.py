"""Single-writer round journal, exact-once result registration and drain policy.

Budget units are seconds of active coordinator wall time, including preparation,
GPU work, fitting, retries and draining. Paused idle time is excluded. The cap
does not terminate a running stage; its overrun remains visible in accounting.
"""
from __future__ import annotations
from contextlib import AbstractContextManager
import json
from pathlib import Path
import time
from .io import atomic_json, digest, read_json

class WriterLock(AbstractContextManager):
    """Persistent lock file with an OS byte-range lock; never unlink a lock."""
    def __init__(self,path:Path):self.path=path;self.file=None
    def __enter__(self):
        import msvcrt
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+b')
        self.file.seek(0,2)
        if self.file.tell()==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file.close();self.file=None
            raise RuntimeError('Another WF7 coordinator owns this round')
        return self
    def __exit__(self,*exc):
        if self.file is not None:
            import msvcrt
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            self.file.close();self.file=None

class RoundStore:
    """State is authoritative; immutable stage results are replayable evidence."""
    VERSION=1
    def __init__(self,path:Path,contract:str,*,hours:float=48.):
        self.path=path;self.contract=contract;self.cap=hours*3600
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            self.data=read_json(self.path)
            if self.data['version']!=self.VERSION or self.data['contract']!=contract:
                raise RuntimeError('Round contract differs; migration requires explicit review')
        else:
            self.data=dict(version=self.VERSION,contract=contract,status='prepared',
                active_seconds=0.,exploration_seconds=0.,cap_seconds=self.cap,
                candidates=[],pending=None,completed_stage_keys=[],failures=[],
                radius=.25,round=1,last_update_utc_s=time.time())
            self.save()
        if self.data['cap_seconds']!=self.cap:raise RuntimeError('Cannot reset or enlarge round cap')
        self._last=None

    def save(self):
        self.data['last_update_utc_s']=time.time();atomic_json(self.path,self.data)

    def activate(self,now:float|None=None):
        if self.data['status'] in ('budget_exhausted','finished'):
            raise RuntimeError('A new round requires manual audit/start')
        if self._last is not None:raise RuntimeError('Clock already active')
        self._last=time.monotonic() if now is None else now
        self.data['status']='running';self.save()

    def tick(self,now:float|None=None,*,exploration:bool=False):
        if self._last is None:return
        now=time.monotonic() if now is None else now
        dt=now-self._last
        if dt<0:raise ValueError('Monotonic clock moved backwards')
        self.data['active_seconds']+=dt
        if exploration:self.data['exploration_seconds']+=dt
        self._last=now;self.save()

    @property
    def may_dispatch(self):
        return (self.data['status']=='running' and self.data['pending'] is None
                and self.data['active_seconds']<self.cap)

    def drain(self,reason:str):
        if reason not in ('budget','user'):raise ValueError('Unknown drain reason')
        self.data['status']='draining';self.data['drain_reason']=reason;self.save()

    def pause(self,*,now:float|None=None):
        if self.data['pending'] is not None:raise RuntimeError('Running stage must finish before pause')
        self.tick(now)
        self._last=None
        self.data['status']='budget_exhausted' if self.data['active_seconds']>=self.cap else 'paused'
        self.save()

    def begin(self,job:dict):
        if not self.may_dispatch:raise RuntimeError('Dispatch is paused, occupied or over budget')
        if job['key'] in self.data['completed_stage_keys']:raise RuntimeError('Duplicate completed stage')
        self.data['pending']=dict(job);self.save()

    def register(self,key:str,result:Path):
        """Result files commit before state, so interrupted registration replays once."""
        if key in self.data['completed_stage_keys']:return False
        pending=self.data['pending']
        if pending is None or pending['key']!=key:raise RuntimeError('Result/pending identity mismatch')
        data=read_json(result)
        if data.get('job_key')!=key or data.get('status')!='completed':raise RuntimeError('Unsuccessful or foreign stage result')
        pending.update(result_path=str(result),result_sha256=digest(result))
        self.data['completed_stage_keys'].append(key)
        self.data.setdefault('results',[]).append(pending)
        self.data['pending']=None;self.save();return True

    def fail(self,key:str,error:dict):
        pending=self.data['pending']
        if pending is None or pending['key']!=key:raise RuntimeError('Failure/pending identity mismatch')
        self.data['failures'].append(dict(job=pending,error=error,utc_s=time.time()))
        self.data['pending']=None;self.save()
