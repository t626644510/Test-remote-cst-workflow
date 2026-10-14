"""One isolated phase per process; complete field traces survive fit failures."""
from __future__ import annotations
from pathlib import Path
import argparse,os,sys,time,traceback
from .config import load_config
from .io import atomic_json,read_json

def execute(request: dict) -> dict:
    """Execute an explicit phase without selecting candidates or dispatching work."""
    config=load_config(request['config']);config.validate(live=True)
    if request['contract']!=config.digest():raise ValueError('Worker configuration drift')
    out=Path(request['output']);kind=request['phase']
    if kind=='prepare':
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
        from .cst_prepare import prepare_cst
        from .prepare import prepare
        result=prepare_cst(config,request['parameters'],out/'cst')
        prepared=out/'prepared'
        prepare(Path(result['project']),Path(result['geometry']),prepared,tuple(config.physics.thermal_solids))
        return dict(prepared=str(prepared),cst=result)
    if kind=='solve':
        from .gpu import run
        return run(config,Path(request['prepared']),out,request['stage'])
    if kind=='analyze':
        from .postprocess import analyze
        return analyze(config,Path(request['field_directory']),out,request['stage'],request['parameters'],
                       Path(request['axis_directory']) if request.get('axis_directory') else None)
    raise ValueError('Unknown worker phase')

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('request');args=parser.parse_args()
    request=read_json(args.request);reply=Path(args.request).with_suffix('.reply.json')
    started=time.time()
    try:
        value=execute(request)
        atomic_json(reply,dict(request_id=request['request_id'],contract=request['contract'],status='completed',
                               result=value,started=started,finished=time.time(),pid=os.getpid()))
        return 0
    except BaseException:
        atomic_json(reply,dict(request_id=request['request_id'],contract=request['contract'],status='failed',
                               traceback=traceback.format_exc(),started=started,finished=time.time(),pid=os.getpid()))
        return 1

if __name__=='__main__':raise SystemExit(main())
