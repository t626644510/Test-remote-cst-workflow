"""WF6 station-local staged recovery, before cross-station fallback.

WF2/WF3 tier counts are retained (0 simple, 2 reopen, 2 clean rebuild).
Each attempt is immutable and uses a new owned CST session. No global kill,
lock deletion, parameter change, or reuse of a failed numerical observation.
"""
from __future__ import annotations
from pathlib import Path
import json
import subprocess
import time
from typing import Callable

from ..io import atomic_json, digest, project_manifest
from ..session_recovery import SessionRecoveryBlocked, ensure_sessions_inactive, query_pid
from ..supervision import check_recovery
from .protocol import read_json, publish_json, fingerprint

POLICY = dict(version=1, reopen=2, rebuild=2, cooldown_s=5.)


def station_absence() -> dict:
    """Read-only global absence check; executable names NEVER authorize killing."""
    script = """$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$os=Get-CimInstance Win32_OperatingSystem
@{free_kib=[long]$os.FreePhysicalMemory;processes=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^(CST DESIGN ENVIRONMENT|Solver_|modeler_)'} | ForEach-Object {@{pid=[int]$_.ProcessId;name=[string]$_.Name;birth=$_.CreationDate.ToUniversalTime().ToString('o')}})}|ConvertTo-Json -Depth 4 -Compress"""
    # Flat primitive-only serialization, no provider/file objects. Process has
    # no children; timeout terminates this directly-owned PowerShell locally.
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                            capture_output=True,timeout=15.,check=True)
    value=json.loads(result.stdout.decode('utf-8-sig'))
    if value['processes']:
        raise SessionRecoveryBlocked('CST session remains; no station-wide termination is allowed')
    return dict(value,observed_at=time.time(),kind='read_only_global_absence')


def certify_quiescence(folder: Path, probe: Callable=station_absence) -> None:
    """Resolve unknown-PID startup only after fresh absence and worker exit proof."""
    worker=folder/'worker.json'
    if worker.exists() and query_pid(read_json(worker)['pid'])!='absent':
        raise SessionRecoveryBlocked('Previous stage worker remains occupied or unknown')
    try:
        check_recovery(folder)
    except SessionRecoveryBlocked:
        records={str(p.relative_to(folder.parent)):digest(p)
                 for p in folder.parent.glob('attempt_*/*_session.json')}
        if not records:raise
        proof=probe()
        if proof.get('processes')!=[] or proof.get('kind')!='read_only_global_absence':
            raise SessionRecoveryBlocked('Absence proof incomplete')
        atomic_json(folder.parent/'station_quiescence.json',dict(proof,session_hashes=records))
        check_recovery(folder)


def classify(result: dict, folder: Path) -> dict:
    """Separate a resolved safety incident from its original evaluation failure."""
    if result.get('category')=='ownership_failed':
        raise SessionRecoveryBlocked('Ownership mismatch requires operator diagnosis')
    if result.get('category')!='cleanup_failed':return result
    records=[read_json(p) for p in folder.glob('*_cleanup.json')]
    primary=next((r.get('primary_error') for r in reversed(records) if r.get('primary_error')),None)
    if not records:
        raise SessionRecoveryBlocked('Unsafe cleanup outcome lacks primary evidence')
    if not primary:
        # A cleanup operation may itself fail after an otherwise normal body.
        # Keep it FAILED, without inventing a preceding CST/geometry exception.
        # Only matching known sessions and fresh exact-PID absence release it.
        for marker in folder.glob('*_cleanup.json'):
            cleanup=read_json(marker)
            session_path=marker.with_name(marker.name.replace('_cleanup.json','_session.json'))
            if not session_path.exists():raise SessionRecoveryBlocked('Cleanup-only session missing')
            session=read_json(session_path);pid=session.get('pid')
            if (not isinstance(pid,int) or isinstance(pid,bool) or pid<=0
                or not session.get('session_id')
                or any(session.get(k)!=cleanup.get(k) for k in ('session_id','pid','project'))
                or cleanup.get('exit_verified') is not True
                or query_pid(pid)!='absent'):
                raise SessionRecoveryBlocked('Cleanup-only session not proven inactive')
        return dict(status='failed',category='session_failed',error=result.get('error','Cleanup failed'),
                    original_result=result,quiescence_resolved=True,cleanup_only=True)
    return dict(status='failed',category='session_failed',error=primary,
                original_result=result,quiescence_resolved=True)


def prepared_source(job: Path, identity: str) -> dict | None:
    """Return only a digest-verified immutable prepared geometry snapshot."""
    for marker in sorted(job.glob('attempt_*/prepared.json'),reverse=True):
        proof=read_json(marker)
        if proof['identity']!=identity:raise ValueError('Prepared identity mismatch')
        project=marker.parent/'prepared'/proof['name']
        if project_manifest(project)!=proof['files']:raise ValueError('Prepared snapshot changed')
        return dict(project=str(project),identity=identity,files=proof['files'])
    return None


class StationRecovery:
    """Durable bounded attempt ladder; failures never become GP observations."""
    def __init__(self,config,config_path:Path,root:Path,spec:dict,clock,
                 launch:Callable,quiesce:Callable=certify_quiescence,
                 probe:Callable=station_absence,now:Callable=time.time,sleep:Callable=time.sleep,
                 on_attempt:Callable=lambda folder,tier:None):
        self.config=config;self.config_path=config_path;self.root=root;self.spec=spec
        self.job=root/'jobs'/spec['id'];self.clock=clock;self.launch=launch
        self.quiesce=quiesce;self.probe=probe;self.now=now;self.sleep=sleep;self.on_attempt=on_attempt

    def run(self) -> tuple[Path,dict,list]:
        spec=self.spec;history=[];last=None
        for index,tier in enumerate(('initial','reopen','reopen','rebuild','rebuild')):
            folder=self.job/f'attempt_{index:05d}';claim=folder/'station_started.json'
            final=folder/'station_result.json'
            legacy=index==0 and (self.job/'started.json').exists()
            claimed=claim.exists() or legacy
            remaining=spec.get('repair_budget_s',float('inf'))-sum(h['elapsed_s'] for h in history)
            if index and not claimed and remaining<=0:
                return last,dict(result,station_recovery_complete=True,recovery_exhausted=True,repair_budget_exhausted=True),history
            if index and not claimed and (self.root/'STOP').exists():
                return self._deferred(last,history,'station STOP')
            if not claimed and self.now()>=spec['station_deadline']:
                return self._deferred(last,history,'round deadline')
            if index and not claimed:
                proof=self.probe()
                if proof['free_kib']<4*1024**2:
                    raise SessionRecoveryBlocked('Station memory remains below 4 GiB; recovery held')
                self.sleep(POLICY['cooldown_s'])
                if (self.root/'STOP').exists() or self.now()>=spec['station_deadline']:
                    return self._deferred(last,history,'admission closed during cooldown')
            task={k:spec[k] for k in ('id','identity','parameters','ports','stage')}
            task.update(directory=str(folder),template=self.config.paths.templates[spec['stage']])
            if claimed and (folder/'task.json').exists():
                task=read_json(folder/'task.json')
                for key in ('id','identity','parameters','ports','stage'):
                    if task[key]!=spec[key]:raise ValueError('Recovery task identity changed')
            elif not claimed:
                task['station_recovery']=True
                if tier=='reopen':
                    source=prepared_source(self.job,spec['identity'])
                    if source:task['prepared_source']=source
                folder.mkdir(parents=True,exist_ok=True)
                publish_json(folder/'task.json',task)
            folder.mkdir(parents=True,exist_ok=True)
            self.on_attempt(folder,tier)
            self.quiesce(folder)
            if final.exists():
                entry=read_json(final);result=entry['result']
                if any(not (folder/name).is_file() or digest(folder/name)!=sha for name,sha in entry['files'].items()):
                    raise ValueError('Station attempt evidence changed')
            else:
                start=self.now()
                if not claimed:
                    publish_json(claim,dict(time=start,identity=spec['identity'],tier=tier))
                output=folder/'worker_result.json'
                if claimed and (folder/'attempt_return.json').exists():result=read_json(folder/'attempt_return.json')
                elif claimed and output.exists():result=read_json(output)
                elif claimed and not (folder/'solved.json').exists():
                    result=dict(status='failed',category='interrupted',error='Interrupted physical attempt; durable claim prohibits implicit repeat')
                else:
                    result=self.launch(self.config_path,task,self.clock,min(spec['timeout_s'],max(1.,remaining)))
                publish_json(folder/'attempt_return.json',result)
                self.quiesce(folder)
                result=classify(result,folder)
                # Completed solve always takes extraction-only recovery priority.
                if (folder/'solved.json').exists() and result['status']!='complete':
                    retry=folder/'extraction_started.json';output=folder/'worker_result_extraction.json'
                    if output.exists():result=read_json(output)
                    elif not retry.exists():
                        publish_json(retry,dict(time=self.now(),identity=spec['identity']))
                        extraction=dict(task,result_filename=output.name)
                        result=self.launch(self.config_path,extraction,self.clock,self.config.runtime.postprocess_timeout_s+300)
                        publish_json(output,result)
                        self.quiesce(folder)
                        result=classify(result,folder)
                    if result['status']!='complete':
                        raise SessionRecoveryBlocked('Saved solve extraction unresolved; never repeat electromagnetic solve')
                # Initial elapsed uses the original completion time on replay,
                # excludes stopped idle. New attempt wall time is seconds.
                elapsed=max(0.,self.now()-start)
                if claimed and claim.exists():
                    finished=folder/'attempt_return.json'
                    endpoint=finished.stat().st_mtime if finished.exists() else self.now()
                    elapsed+=max(0.,endpoint-read_json(claim)['time'])
                if legacy and (folder/'worker_result.json').exists():
                    elapsed=max(0.,(folder/'worker_result.json').stat().st_mtime-read_json(self.job/'started.json')['time'])
                entry=dict(index=index,tier=tier,identity=spec['identity'],result=result,elapsed_s=elapsed,
                    files={p.name:digest(p) for p in folder.glob('*.json') if p.name!='station_result.json'})
                publish_json(final,entry)
            if entry['identity']!=spec['identity']:raise ValueError('Station result identity mismatch')
            history.append(entry);last=folder
            if result['status']=='complete':return folder,dict(result,station_recovery_complete=True),history
            if result.get('category') in ('identity_failed','settings_failed'):
                raise SessionRecoveryBlocked('Physical evidence/settings mismatch; not a numerical retry')
        return last,dict(result,error='\n'.join(h['result'].get('error','') for h in history),
                         station_recovery_complete=True,recovery_exhausted=True),history

    def _deferred(self,folder,history,reason):
        if folder is None:raise SessionRecoveryBlocked('No admitted recovery attempt')
        return folder,dict(status='failed',category='recovery_deferred',error=reason,
                           station_recovery_complete=False),history
