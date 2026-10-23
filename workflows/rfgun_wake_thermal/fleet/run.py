"""WF6 fleet CLI. Inspect, identity, migrate and publication never start CST."""
from __future__ import annotations
import argparse, base64, json, logging, shutil, time, subprocess
from dataclasses import asdict
from pathlib import Path
from .protocol import Node,read_json,publish_json,execution_identity,fingerprint,safe_id
from .transport import validate_relative
from ..config import load_config
from ..io import atomic_json,digest
from ..storage import campaign_lock,verify_evidence


def migrate(config,config_path:Path,nodes:list[Node],execution:dict)->dict:
    """Adopt a safely drained serial round; no budget reset and no solver start."""
    root=Path(config.paths.output_dir);artifacts=Path(config.paths.artifact_dir)
    state=read_json(root/'state.json')
    manifest=dict(execution=execution,nodes=[asdict(n) for n in nodes],source_contract=state['contract'])
    fleet_contract=fingerprint(manifest)
    if state.get('fleet_contract'):
        if state['fleet_contract']!=fleet_contract:raise ValueError('Fleet execution configuration changed')
        return {'status':'already_migrated','fleet_contract':fleet_contract}
    if state['status']!='paused' or state.get('pending') or state.get('pending_nodes') or any(j['status']=='reserved' or not j.get('applied') for j in state['jobs']):
        raise ValueError('Finish and pause all serial work before fleet migration')
    if read_json(artifacts/'owner.json')['contract']!=state['contract']:raise ValueError('Artifact owner mismatch')
    for c in state['candidates']:
        for s in c['stages'].values():
            if not verify_evidence(Path(s['raw'])):raise ValueError('Existing permanent raw evidence failed verification')
    # A global READ-ONLY absence check also closes legacy startup records that
    # never captured a PID. It never authorizes killing an unrelated process.
    command="$p=@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {$_.Name -match '^(CST DESIGN ENVIRONMENT|Solver_|modeler_)'} | Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine); ConvertTo-Json -InputObject $p -Depth 3"
    probe=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,check=True,timeout=30.)
    processes=json.loads(probe.stdout.decode('utf-8-sig',errors='replace'))
    if processes:raise ValueError('Local CST processes remain; finish before reopening legacy failed coordinates')
    audit=root/'audits'/time.strftime('fleet_migration_%Y%m%dT%H%M%SZ',time.gmtime())
    audit.mkdir(parents=True,exist_ok=False)
    atomic_json(audit/'station_quiescence.json',dict(time=time.time(),processes=processes,action='read-only absence check; no termination'))
    paused_at=(root/'state.json').stat().st_mtime
    for name in ('state.json','report.json','evaluations.sqlite','search.ckpt','effective_config.yaml'):
        if (root/name).exists():shutil.copy2(root/name,audit/name)
    shutil.copy2(artifacts/'owner.json',audit/'owner.json');shutil.copy2(config_path,audit/'config.yaml')
    package=Path(__file__).resolve().parents[1]
    shutil.copytree(package,audit/'code',ignore=shutil.ignore_patterns('__pycache__','*.pyc','config.local.yaml'))
    remote=next(n.name for n in nodes if n.ssh_host)
    state.update(fleet_contract=fleet_contract,pending_nodes={},fleet_retry=[],node_seconds={n.name:0. for n in nodes})
    for c in state['candidates']:
        if c['failed'] and not c['complete']:
            last=next((j for j in reversed(state['jobs']) if j['candidate']==c['id']),None)
            if c.get('failure',{}).get('category')=='postprocess_failed' or (last and (Path(last['directory'])/'solved.json').exists()):
                c['fleet_recovery_hold']='Saved completion: diagnose/extract before any new solve'
                continue
            stage=next((s for s in config.active_stages if s not in c['stages']),None)
            if stage:
                c.setdefault('failure_history',[]).append(c.get('failure',{}));c['failed']=False
                state['fleet_retry'].append(dict(candidate=c['id'],stage=stage,node=remote,exploration=None,
                    queued_at=time.time(),reason='legacy single-station failure; preserved history, fresh two-station cycle'))
    # Continuous authorized development after serial drain is maintenance, once.
    maintenance=max(0.,time.time()-paused_at)
    state['active_seconds']+=maintenance
    atomic_json(audit/'maintenance_accounting.json',dict(seconds=maintenance,before=read_json(audit/'state.json')['active_seconds'],after=state['active_seconds']))
    atomic_json(root/'fleet_contract.json',manifest);atomic_json(root/'state.json',state)
    atomic_json(audit/'migration.json',dict(fleet_contract=fleet_contract,state_sha256=digest(root/'state.json'),solver_starts=0,
        retry_candidates=[q['candidate'] for q in state['fleet_retry']],maintenance_seconds=maintenance))
    return dict(status='migrated_paused',fleet_contract=fleet_contract,audit=str(audit),retry_candidates=len(state['fleet_retry']))


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description='WF6 local/remote stage fleet')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('identity','worker','migrate','coordinator','prepare-heat'):
        p=sub.add_parser(name);p.add_argument('--config',type=Path,required=True)
        if name=='worker':p.add_argument('--root',type=Path,required=True);p.add_argument('--node',required=True)
        if name in ('migrate','coordinator','prepare-heat'):p.add_argument('--nodes',type=Path,required=True)
        if name=='prepare-heat':p.add_argument('--reference',type=Path,required=True)
    p=sub.add_parser('inspect');p.add_argument('--root',type=Path,required=True)
    p=sub.add_parser('publish');p.add_argument('--root',type=Path,required=True);p.add_argument('--relative',required=True);p.add_argument('--payload',required=True)
    p=sub.add_parser('publish-file');p.add_argument('--root',type=Path,required=True);p.add_argument('--relative',required=True);p.add_argument('--sha256',required=True)
    args=parser.parse_args(argv)
    if args.command=='inspect':
        from .worker import worker_snapshot
        result=worker_snapshot(args.root)
    elif args.command in ('publish','publish-file'):
        relative=validate_relative(args.relative)
        if not (relative=='STOP' or (relative.startswith('inbox/') and relative.endswith('.json'))):raise ValueError('Not a protocol publication')
        if args.command=='publish':value=json.loads(base64.b64decode(args.payload))
        else:
            if len(args.sha256)!=64 or any(c not in '0123456789abcdef' for c in args.sha256):raise ValueError('Invalid upload digest')
            upload=args.root/'uploads'/(args.sha256+'.json')
            if digest(upload)!=args.sha256:raise ValueError('Uploaded message corrupt')
            value=read_json(upload)
        publish_json(args.root/relative,value);result={'published':relative}
    else:
        config=load_config(args.config);config.validate(live=True)
        if args.command=='identity':result=execution_identity(config)
        elif args.command=='prepare-heat':
            from ..heat_prepare import prepare
            result=prepare(config,args.config.resolve(),[Node.from_dict(v) for v in read_json(args.nodes)['nodes']],args.reference)
        elif args.command=='worker':
            from .worker import run_worker
            run_worker(config,args.config.resolve(),args.root,args.node);return 0
        else:
            nodes=[Node.from_dict(v) for v in read_json(args.nodes)['nodes']]
            identity=execution_identity(config);root=Path(config.paths.output_dir)
            with campaign_lock(root):
                if args.command=='migrate':result=migrate(config,args.config,nodes,identity)
                else:
                    from .coordinator import FleetCampaign
                    saved=read_json(root/'fleet_contract.json');state=read_json(root/'state.json')
                    expected=dict(execution=identity,nodes=[asdict(n) for n in nodes],source_contract=state['contract'])
                    if fingerprint(saved)!=state.get('fleet_contract') or saved!=expected:raise ValueError('Fleet source/config/template identity changed')
                    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(root/'fleet.log',encoding='utf-8'),logging.StreamHandler()])
                    templates={s:str(Path(config.paths.artifact_dir)/'templates'/s/Path(p).name) for s,p in config.paths.templates.items()}
                    campaign=FleetCampaign(config,args.config.resolve(),state['contract'],dict(templates=templates),nodes,fingerprint(identity))
                    campaign.run_fleet();result=dict(status=campaign.state['status'])
    print(json.dumps(result,ensure_ascii=True,allow_nan=False));return 0
