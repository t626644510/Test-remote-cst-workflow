"""Bounded local workers with PID/birth/command ownership and no global cleanup."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
import os,subprocess,time
from .cst_prepare import ProcessIdentity,valid_child
from .io import atomic_json,read_json

class OwnershipError(RuntimeError):
    """An ambiguous or surviving process requires stopping dispatch."""

def matches_worker(command: list[str],request: Path) -> bool:
    """A supervisor may carry the request path without being its phase worker."""
    return 'workflows.rfgun_wakis.worker' in command and str(request) in command

def descendants(root: ProcessIdentity) -> list[ProcessIdentity]:
    """Read only children whose entire live chain has valid birth ordering."""
    import psutil
    if not root.alive():return []
    found={root.pid:root};pending=list(psutil.process_iter(['pid','ppid','create_time','cmdline']))
    for _ in range(20):
        changed=False
        for p in pending:
            v=p.info
            if v['pid'] in found or v['ppid'] not in found:continue
            child=ProcessIdentity(v['pid'],v['ppid'],v['create_time'],tuple(v['cmdline'] or ()))
            if valid_child(found[child.parent],child):found[child.pid]=child;changed=True
        if not changed:break
    return list(found.values())

def cleanup(known: list[ProcessIdentity],path: Path) -> None:
    """Terminate only exact identities already proven to descend from our worker."""
    import psutil
    killed=[];errors=[]
    for v in sorted(known,key=lambda v:v.created,reverse=True):
        try:
            if v.alive():psutil.Process(v.pid).kill();killed.append(asdict(v))
        except psutil.NoSuchProcess:pass
        except Exception as e:errors.append(repr(e))
    limit=time.monotonic()+10
    while time.monotonic()<limit and any(v.alive() for v in known):time.sleep(.25)
    remaining=[asdict(v) for v in known if v.alive()]
    atomic_json(path,dict(killed=killed,errors=errors,remaining=remaining,success=not remaining))
    if remaining:raise OwnershipError('Owned worker cleanup failed')

@dataclass
class RunningPhase:
    """One owned process tree, polled on the coordinator's single writer thread."""
    request: Path
    timeout: float
    spec: dict
    proc: object = None
    root: ProcessIdentity | None = None
    known: dict = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)
    low_since: float | None = None
    result: dict | None = None
    memory_floor_gib: float | None = None
    memory_grace_s: float = 8.

class Supervisor:
    """Nonblocking phase handles allow one CPU preparation beside one GPU job.

    Only the coordinator calls tick; polling never bills a second clock. Exact
    process ownership and cleanup apply independently to the two process trees.
    """
    def __init__(self,config,tick):self.config=config;self.tick=tick

    def start(self,request: Path,timeout: float) -> RunningPhase:
        """Replay terminal evidence or start exactly one hidden phase process."""
        import psutil
        reply=request.with_suffix('.reply.json');owner=request.with_suffix('.owner.json')
        spec=read_json(request)
        terminal=request.with_suffix('.supervision_result.json')
        if terminal.exists() or reply.exists():
            result=read_json(terminal if terminal.exists() else reply)
            if result['request_id']!=spec['request_id'] or result['contract']!=spec['contract']:
                raise OwnershipError('Foreign phase reply')
            if owner.exists():
                identities=[ProcessIdentity(**dict(v,command=tuple(v['command']))) for v in read_json(owner)['processes']]
                if any(v.alive() for v in identities):raise OwnershipError('Previous phase process remains alive')
            return RunningPhase(request,timeout,spec,result=result)
        if owner.exists():
            identities=[ProcessIdentity(**dict(v,command=tuple(v['command']))) for v in read_json(owner)['processes']]
            if any(v.alive() for v in identities):raise OwnershipError('Previous phase is still running; no duplicate launch')
            return RunningPhase(request,timeout,spec,result=dict(status='failed',
                error='Previous worker exited without a reply',interrupted=True))
        for process in psutil.process_iter(['cmdline']):
            command=process.info['cmdline'] or []
            if matches_worker(command,request):
                raise OwnershipError('Matching phase request already has a live process')
        env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MPLBACKEND='Agg')
        checkout=Path(__file__).resolve().parents[2]
        env['PYTHONPATH']=os.pathsep.join((str(checkout),str(checkout/'src')))
        out=request.with_suffix('.stdout.log');err=request.with_suffix('.stderr.log')
        with out.open('xb') as stdout,err.open('xb') as stderr:
            proc=subprocess.Popen([self.config.paths.gpu_python,'-m','workflows.rfgun_wakis.worker',str(request)],
                  cwd=checkout,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        root=ProcessIdentity.read(proc.pid);parent=ProcessIdentity.read(os.getpid())
        if not valid_child(parent,root):raise OwnershipError('Launched worker identity mismatch')
        handle=RunningPhase(request,timeout,spec,proc,root,{(root.pid,root.created):root})
        self._record_owner(handle)
        return handle

    def _record_owner(self,handle:RunningPhase) -> None:
        for v in descendants(handle.root):handle.known[(v.pid,v.created)]=v
        atomic_json(handle.request.with_suffix('.owner.json'),dict(root=asdict(handle.root),
            processes=[asdict(v) for v in handle.known.values()],at=time.time()))

    def poll(self,handle:RunningPhase) -> dict | None:
        """Return None while running; guard/cleanup only this handle's own tree."""
        import psutil
        if handle.result is not None:return handle.result
        self._record_owner(handle)
        problem=None;now=time.monotonic();returncode=handle.proc.poll()
        if returncode is None:
            free=psutil.virtual_memory().available/2**30
            if free<(handle.memory_floor_gib or self.config.runtime.running_free_ram_gib):
                if handle.low_since is None:handle.low_since=now
            else:handle.low_since=None
            if handle.low_since is not None and now-handle.low_since>=handle.memory_grace_s:problem='Host memory protection'
            if now-handle.started>handle.timeout:problem='Phase timeout'
            if problem is None:return None
        cleanup(list(handle.known.values()),handle.request.with_suffix('.cleanup.json'))
        reply=handle.request.with_suffix('.reply.json')
        if problem:result=dict(status='failed',error=problem)
        elif reply.exists():result=read_json(reply)
        else:result=dict(status='failed',error='Worker exited without complete reply',returncode=returncode)
        spec=handle.spec
        if 'request_id' in result and (result['request_id']!=spec['request_id'] or result['contract']!=spec['contract']):
            raise OwnershipError('Phase reply identity mismatch')
        result=dict(result,request_id=spec['request_id'],contract=spec['contract'])
        atomic_json(handle.request.with_suffix('.supervision_result.json'),result)
        handle.result=result
        return result

    def run(self,request: Path,timeout: float) -> dict:
        """Blocking foreground compatibility, while tick services CPU prefetch."""
        handle=self.start(request,timeout)
        try:
            while True:
                self.tick()
                result=self.poll(handle)
                if result is not None:return result
                time.sleep(2)
        except BaseException:
            if handle.result is None:
                self._record_owner(handle)
                cleanup(list(handle.known.values()),request.with_suffix('.cleanup.json'))
            raise
