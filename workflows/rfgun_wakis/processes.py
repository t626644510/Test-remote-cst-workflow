"""Bounded local workers with PID/birth/command ownership and no global cleanup."""
from __future__ import annotations
from dataclasses import asdict
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

class Supervisor:
    """All phase waits tick the shared wall clock; the round cap never kills work."""
    def __init__(self,config,tick):self.config=config;self.tick=tick

    def run(self,request: Path,timeout: float) -> dict:
        import psutil
        reply=request.with_suffix('.reply.json');owner=request.with_suffix('.owner.json')
        spec=read_json(request)
        if reply.exists():
            result=read_json(reply)
            if result['request_id']!=spec['request_id'] or result['contract']!=spec['contract']:
                raise OwnershipError('Foreign phase reply')
            if owner.exists():
                identities=[ProcessIdentity(**dict(v,command=tuple(v['command']))) for v in read_json(owner)['processes']]
                if any(v.alive() for v in identities):raise OwnershipError('Previous phase process remains alive')
            return result
        if owner.exists():
            identities=[ProcessIdentity(**dict(v,command=tuple(v['command']))) for v in read_json(owner)['processes']]
            if any(v.alive() for v in identities):raise OwnershipError('Previous phase is still running; no duplicate launch')
            return dict(status='failed',error='Previous worker exited without a reply',interrupted=True)
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
            known={(root.pid,root.created):root};start=time.monotonic();low_since=None;problem=None
            try:
                while True:
                    for v in descendants(root):known[(v.pid,v.created)]=v
                    atomic_json(owner,dict(root=asdict(root),processes=[asdict(v) for v in known.values()],at=time.time()))
                    self.tick()
                    if proc.poll() is not None:break
                    free=psutil.virtual_memory().available/2**30
                    if free<self.config.runtime.running_free_ram_gib:
                        if low_since is None:low_since=time.monotonic()
                    else:low_since=None
                    if low_since is not None and time.monotonic()-low_since>=8:problem='Host memory protection'
                    if time.monotonic()-start>timeout:problem='Phase timeout'
                    if problem:break
                    time.sleep(2)
            finally:
                cleanup(list(known.values()),request.with_suffix('.cleanup.json'))
            if problem:return dict(status='failed',error=problem)
        if not reply.exists():return dict(status='failed',error='Worker exited without complete reply',returncode=proc.returncode)
        result=read_json(reply)
        if result['request_id']!=spec['request_id'] or result['contract']!=spec['contract']:
            raise OwnershipError('Phase reply identity mismatch')
        return result
