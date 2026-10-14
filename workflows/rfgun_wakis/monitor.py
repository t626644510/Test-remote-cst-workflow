"""Read-only local diagnostics; writes only monitor state and timestamped audits."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import argparse,time,shutil
from .config import load_config
from .io import read_json,atomic_json,digest,validate_manifest
from .cst_prepare import ProcessIdentity

def inspect(config_path: Path) -> dict:
    """Check persisted identity/progress/evidence without opening CST or resuming."""
    import psutil
    config=load_config(config_path);root=Path(config.paths.output_dir)
    state=read_json(root/'state.json');now=time.time();issues=[]
    heartbeat=read_json(root/'heartbeat.json') if (root/'heartbeat.json').exists() else {}
    age=now-heartbeat.get('at',0);owner=read_json(root/'owner.json') if (root/'owner.json').exists() else None
    live=False
    if owner:
        identity=ProcessIdentity(**dict(owner,command=tuple(owner['command'])))
        live=identity.alive()
    active=state['status'] in ('running','draining')
    if state['status']=='error':issues.append('coordinator_error')
    if active and not live:issues.append('coordinator_missing')
    if active and age>90:issues.append('coordinator_heartbeat_stale')
    provenance=read_json(root/'provenance.json')
    try:validate_manifest(Path(__file__).parent,provenance['code'])
    except (ValueError,OSError):issues.append('code_fingerprint_changed')
    if config.digest()!=state['contract']:issues.append('configuration_drift')
    if digest(config.paths.template)!=provenance['template_sha256']:issues.append('source_template_changed')
    process_rows=[];pending=state.get('pending');phase_detail={}
    if pending:
        phase=pending.get('phase');path=pending.get('phase_requests',{}).get(phase)
        if path:
            request=Path(path);owner_file=request.with_suffix('.owner.json')
            if owner_file.exists():
                for v in read_json(owner_file)['processes']:
                    identity=ProcessIdentity(**dict(v,command=tuple(v['command'])))
                    if identity.alive():
                        p=psutil.Process(identity.pid);cpu=p.cpu_times()
                        process_rows.append(dict(**asdict(identity),cpu_seconds=cpu.user+cpu.system,rss_bytes=p.memory_info().rss))
            spec=read_json(request);output=Path(spec['output'])
            for path in (output/'status.json',output/'cst/heartbeat.json',output/'cst/assembly_stop.json'):
                if path.exists():phase_detail[path.name]=read_json(path)
            if request.with_suffix('.cleanup.json').exists():
                if not read_json(request.with_suffix('.cleanup.json'))['success']:issues.append('worker_cleanup_failed')
    disks={str(Path(p).anchor):shutil.disk_usage(p).free/2**30 for p in (config.paths.output_dir,config.paths.artifact_dir)}
    if min(disks.values())<config.runtime.minimum_free_disk_gib:issues.append('low_disk_space')
    free_ram=psutil.virtual_memory().available/2**30
    if free_ram<config.runtime.running_free_ram_gib:issues.append('low_host_memory')
    evidence=[]
    for item in state.get('results',[])[-2:]:
        path=Path(item['result_path'])
        if digest(path)!=item['result_sha256']:issues.append('registered_result_changed');continue
        result=read_json(path);field=Path(result['field_directory'])
        manifest_path=field/'raw_manifest.json'
        try:
            validate_manifest(field,read_json(manifest_path))
            analyzed=[]
            for analysis_manifest in sorted(field.glob('analysis_*/manifest.json')):
                analysis=analysis_manifest.parent
                analysis_result=read_json(analysis/'result.json')
                if analysis_result.get('raw_sha256')==result['raw_sha256'] and analysis_result.get('stage')==result['stage']:
                    validate_manifest(analysis,read_json(analysis_manifest));analyzed.append(str(analysis_manifest))
            if not analyzed:raise ValueError('Completed stage analysis manifest missing')
            evidence.append(dict(job=item['key'],raw_manifest_verified=True,analysis_manifests=analyzed))
        except (ValueError,OSError):issues.append('raw_manifest_mismatch')
    previous=read_json(root/'monitor_state.json') if (root/'monitor_state.json').exists() else {}
    old={(p['pid'],p['created']):p for p in previous.get('processes',[])}
    for p in process_rows:
        before=old.get((p['pid'],p['created']))
        p['cpu_delta_seconds']=p['cpu_seconds']-before['cpu_seconds'] if before else None
    issue=';'.join(sorted(set(issues))) or None
    count=(previous.get('consecutive_count',0)+1 if previous.get('issue_key')==issue else 1) if issue else 0
    audit=dict(at=now,status=state['status'],pending=pending,heartbeat_age_s=age,owner_alive=live,
        active_hours=state['active_seconds']/3600,remaining_hours=max(0,state['cap_seconds']-state['active_seconds'])/3600,
        processes=process_rows,phase_detail=phase_detail,host_free_gib=free_ram,disk_free_gib=disks,evidence=evidence,
        issue_key=issue,consecutive_count=count,user_action_required=False,action='read_only_diagnostic',
        candidates=len(state['candidates']),qualified_X_screening=sum(c.get('feasibility',{}).get('qualified_X_screening',False) for c in state['candidates']))
    name=time.strftime('monitor_%Y%m%dT%H%M%SZ.json',time.gmtime(now))
    atomic_json(root/'audits'/name,audit);atomic_json(root/'monitor_state.json',audit);return audit

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    result=inspect(Path(args.config));print({k:result[k] for k in ('status','issue_key','consecutive_count','candidates','remaining_hours')})
