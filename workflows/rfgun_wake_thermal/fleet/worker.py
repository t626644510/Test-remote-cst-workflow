"""Persistent station worker. One owned stage at a time; no shared database."""
from __future__ import annotations
import os, shutil, threading, time, traceback
from pathlib import Path
from typing import Any
from .protocol import read_json, owner_lock, execution_identity, fingerprint, pack_evidence, publish_json, safe_id
from ..io import atomic_json
from ..supervision import launch_worker, check_recovery, process_birth


class WorkerClock:
    """Adapter for the existing supervised stage runner; seconds are node effort."""
    def __init__(self, config, root: Path):
        self.config=config; self.root=root; self.state={'active_seconds':0.}; self.last=time.monotonic()
    def tick(self):
        now=time.monotonic(); self.state['active_seconds']+=now-self.last; self.last=now


def worker_snapshot(root: Path) -> dict[str, Any]:
    """Read status and worker identity without connecting to or starting CST."""
    path=root/'status.json'
    value=read_json(path) if path.exists() else {'status':'not_started'}
    value['observed_at']=time.time()
    value['process_matches']=bool(value.get('pid') and value.get('birth') and process_birth(value['pid'])==value['birth'])
    value['outcomes']={p.parent.name:read_json(p) for p in sorted((root/'jobs').glob('*/outcome.json'))}
    value['free_bytes']=shutil.disk_usage(root if root.exists() else root.parent).free
    return value


def validate_task(spec: dict, node: str, execution: str, now: float, *, started: bool=False) -> None:
    safe_id(spec['id'])
    if spec['node']!=node or spec['execution']!=execution:
        raise ValueError('Task belongs to a different node or execution contract')
    expected=fingerprint({k:spec[k] for k in ('contract','parameters','ports','stage')})
    if spec['identity']!=expected or spec['stage'] not in ('axis','x','y','thermal'):
        raise ValueError('Stage identity mismatch')
    if not started and now>spec['admit_before']:
        raise TimeoutError('Stage admission expired; no solve was started')


def run_worker(config, config_path: Path, root: Path, node: str) -> None:
    """Run independent of SSH lifetime, retaining all native and numeric evidence."""
    safe_id(node); root.mkdir(parents=True,exist_ok=True)
    with owner_lock(root/'worker.lock'):
        identity=execution_identity(config); execution=fingerprint(identity)
        publish_json(root/'execution.json',identity)
        (root/'inbox').mkdir(exist_ok=True)
        (root/'uploads').mkdir(exist_ok=True)
        status=dict(node=node,execution=execution,pid=os.getpid(),birth=process_birth(os.getpid()),
                    status='idle',job=None,started_at=time.time())
        halted=threading.Event()
        def heartbeat():
            while not halted.is_set():
                try:atomic_json(root/'status.json',dict(status,time=time.time()))
                except OSError:pass
                halted.wait(5.)
        thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
        try:
            while not (root/'STOP').exists():
                selected=next((p for p in sorted((root/'inbox').glob('*.json'))
                    if not (root/'jobs'/p.stem/'outcome.json').exists()),None)
                if selected is None:
                    time.sleep(2.);continue
                spec=read_json(selected); jobroot=root/'jobs'/safe_id(spec['id'])
                folder=jobroot/'attempt_00000'; jobroot.mkdir(parents=True,exist_ok=True)
                started=jobroot/'started.json'; now=time.time()
                grant_path=root/'recovery_grants'/(spec['id']+'.json')
                grant=read_json(grant_path) if grant_path.exists() else None
                expected_execution=execution
                recovery_spec=dict(spec)
                if grant:
                    if grant['new_execution']!=execution or grant['original_task_sha256']!=fingerprint(spec):
                        raise ValueError('Recovery migration grant mismatch')
                    expected_execution=spec['execution']
                    recovery_spec.update(station_recovery=True,station_deadline=grant['station_deadline'])
                try:validate_task(spec,node,expected_execution,now,started=started.exists() or any(jobroot.glob("attempt_*/station_started.json")))
                except TimeoutError:
                    publish_json(jobroot/'outcome.json',dict(id=spec['id'],identity=spec['identity'],node=node,
                        status='not_started',category='admission_expired',elapsed_s=0.,execution=execution))
                    continue
                status.update(status='running',job=spec['id'],task=spec,stage_started=now)
                if recovery_spec.get('station_recovery'):
                    if fingerprint(execution_identity(config))!=execution:
                        raise ValueError('Station execution changed before recovery')
                    from .station_recovery import StationRecovery
                    from .protocol import pack_station_evidence
                    clock=WorkerClock(config,jobroot)
                    runner=StationRecovery(config,config_path,root,recovery_spec,clock,launch_worker,
                        on_attempt=lambda folder,tier:status.update(attempt_directory=str(folder),recovery_tier=tier))
                    folder,result,history=runner.run()
                    atomic_json(folder/'station_recovery_history.json',history)
                    archive=jobroot/'evidence.zip';sha=pack_station_evidence(folder,jobroot,archive)
                    outcome=dict(id=spec['id'],node=node,execution=spec['execution'],identity=spec['identity'],
                        status=result['status'],result=result,elapsed_s=sum(x['elapsed_s'] for x in history),
                        finished_at=time.time(),quiescent=True,evidence=f'jobs/{spec["id"]}/evidence.zip',
                        sha256=sha,native_directory=str(folder),station_attempts=len(history))
                    publish_json(jobroot/'outcome.json',outcome)
                    status.update(status='idle',job=None,task=None)
                    continue
                task={k:spec[k] for k in ('id','identity','parameters','ports','stage')}
                task.update(directory=str(folder),template=config.paths.templates[spec['stage']])
                folder.mkdir(parents=True,exist_ok=True)
                if (folder/'task.json').exists():
                    saved=read_json(folder/'task.json')
                    if any(saved.get(k)!=v for k,v in task.items()):raise ValueError('Saved station task mismatch')
                else:publish_json(folder/'task.json',task)
                clock=WorkerClock(config,jobroot)
                # Durable claim BEFORE invoking the runner. A restart may extract
                # saved success, but can never issue the same electromagnetic solve.
                if started.exists():
                    check_recovery(folder)
                    output=folder/'worker_result.json'
                    if output.exists():result=read_json(output)
                    elif (folder/'solved.json').exists():
                        result=launch_worker(config_path,task,clock,config.runtime.postprocess_timeout_s+300)
                    else:result=dict(status='failed',category='interrupted',error='Worker restarted without saved completion; original attempt retained')
                else:
                    if fingerprint(execution_identity(config))!=execution:
                        raise ValueError('Station execution files changed while worker was running')
                    # Validate again after hashing; queued work cannot start late.
                    try:validate_task(spec,node,execution,time.time())
                    except TimeoutError:
                        publish_json(jobroot/'outcome.json',dict(id=spec['id'],identity=spec['identity'],node=node,
                            status='not_started',category='admission_expired',elapsed_s=0.,execution=execution))
                        status.update(status='idle',job=None,task=None)
                        continue
                    publish_json(started,dict(time=time.time(),task=spec))
                    result=launch_worker(config_path,task,clock,
                        spec['timeout_s'])
                # Always establish station quiescence before publishing transferable failure.
                check_recovery(folder)
                if result.get('category')=='postprocess_failed' and (folder/'solved.json').exists():
                    # Extraction-only retry under existing saved-solve fingerprint gate.
                    task['result_filename']='worker_result_postprocess_retry.json'
                    result=launch_worker(config_path,task,clock,config.runtime.postprocess_timeout_s+300)
                    check_recovery(folder)
                if result.get('category') in ('cleanup_failed','ownership_failed'):
                    raise RuntimeError('Unsafe session outcome requires station diagnosis: '+str(result))
                archive=jobroot/'evidence.zip'; sha=pack_evidence(folder,archive)
                started_at=read_json(started)['time']
                outcome=dict(id=spec['id'],node=node,execution=execution,identity=spec['identity'],
                    status=result['status'],result=result,elapsed_s=max(0.,time.time()-started_at),
                    started_at=started_at,finished_at=time.time(),quiescent=True,
                    evidence=f'jobs/{spec["id"]}/evidence.zip',sha256=sha,native_directory=str(folder))
                publish_json(jobroot/'outcome.json',outcome)
                status.update(status='idle',job=None,task=None)
        except BaseException as exc:
            status.update(status='needs_attention',error=f'{type(exc).__name__}: {exc}')
            atomic_json(root/'failure.json',dict(status,traceback=traceback.format_exc(),time=time.time()))
            raise
        finally:
            halted.set();thread.join(timeout=10.)
            if status['status']!='needs_attention':status['status']='stopped'
            atomic_json(root/'status.json',dict(status,time=time.time()))
