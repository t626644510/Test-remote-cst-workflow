"""WF6 CLI; validate/offline paths never load CST's Python modules."""
from __future__ import annotations
import argparse,json,logging,sys,traceback
from pathlib import Path
from .config import load_config,STAGES
from .io import atomic_json


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='WF6 staged wake impedance / antenna power optimization')
    parser.add_argument('--config',required=True,type=Path)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('validate');sub.add_parser('baseline');sub.add_parser('optimize')
    resume=sub.add_parser('resume');resume.add_argument('--baseline-only',action='store_true')
    stage=sub.add_parser('stage');stage.add_argument('--stage',required=True,choices=STAGES)
    worker=sub.add_parser('worker');worker.add_argument('--task',type=Path,required=True)
    offline=sub.add_parser('offline');offline.add_argument('--candidate',required=True);offline.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args(argv);config=load_config(args.config)
    if args.command=='worker':
        from .runtime import CSTWorker
        task=json.loads(args.task.read_text());folder=Path(task['directory'])
        try:result=CSTWorker(config).run(task)
        except Exception as exc:
            traceback.print_exc();result=dict(status='failed',category=getattr(exc,'category','worker_failed'),error=f'{type(exc).__name__}: {exc}')
        atomic_json(folder/task.get('result_filename','worker_result.json'),result)
        return 0 if result['status']=='complete' else 1
    if args.command=='validate':
        config.validate(live=True)
        from .runtime import metadata,effective_settings
        from .geometry import Geometry
        baseline=[]
        for s,p in config.paths.templates.items():
            effective_settings(Path(p),s,config)
            point=Geometry(config).collapse(metadata(Path(p))['parameters']);baseline.append(point)
            errors=Geometry(config).violations(point)
            if errors:raise ValueError('; '.join(errors))
        if any(p!=baseline[0] for p in baseline):raise ValueError('Four template coordinates differ')
        print(json.dumps(dict(status='valid',baseline=baseline[0],physical=Geometry(config).expand(baseline[0])),indent=2));return 0
    if args.command=='offline':
        from .campaign import offline_candidate
        state=json.loads((Path(config.paths.output_dir)/'state.json').read_text())
        candidate=next(c for c in state['candidates'] if c['id']==args.candidate)
        result=offline_candidate(config,candidate,args.destination)
        print(json.dumps(result['metrics'],indent=2));return 0
    config.validate(live=True)
    from .storage import campaign_lock
    from .campaign import initialize,Campaign
    root=Path(config.paths.output_dir)
    with campaign_lock(root):
        if args.command!='resume' and (root/'state.json').exists():
            raise ValueError('Existing campaign: explicitly use resume to preserve state and budget')
        if args.command=='resume' and not (root/'state.json').exists():raise ValueError('No campaign state to resume')
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
            handlers=[logging.FileHandler(root/'campaign.log',encoding='utf-8'),logging.StreamHandler()])
        contract,snapshot=initialize(config)
        campaign=Campaign(config,args.config.resolve(),contract,snapshot)
        campaign.run('baseline' if getattr(args,'baseline_only',False) else args.command,getattr(args,'stage',None))
        print(json.dumps(dict(status=campaign.state['status'],report=str(root/'report.json')),indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
