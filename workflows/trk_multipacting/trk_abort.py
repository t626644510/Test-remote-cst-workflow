"""Request native CST abort through a separate, identity-checked IPC connection.

Official CST 2026 Project.connect and Model3D.abort_solver APIs; no solver start,
rebuild, project close or process termination. The scientific worker saves results.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import psutil
from .trk_run import utc, write_json


def validate_request(root: Path, request: dict) -> None:
    """Fail closed on a different task, reused process or unrelated CST session."""
    state=json.loads((root/'state.json').read_text())
    owner=json.loads((root/'owner.json').read_text())
    timer=json.loads((root/'cases'/request['key']/'solve_timer.json').read_text())
    snapshot=json.loads((root/'snapshot.json').read_text())
    if (state.get('owner') != request['owner'] or state.get('current',{}).get('key') != request['key']
            or timer.get('owner') != request['owner'] or timer.get('key') != request['key']
            or timer.get('finished') is not False or snapshot['project'] != request['project']
            or owner != request['session_owner']):
        raise RuntimeError('Abort identity/task changed; no command sent')
    worker=psutil.Process(owner['pid']);cst=psutil.Process(owner['cst_pid'])
    if (worker.create_time()!=owner['created'] or cst.create_time()!=owner['cst_created']
            or cst.ppid()!=worker.pid or cst.create_time()<worker.create_time()):
        raise RuntimeError('Abort process ownership mismatch')


def request_abort(root: Path, request_path: Path, library: str) -> None:
    """Attach only to the recorded scratch project and ask it to flush/stop."""
    request=json.loads(request_path.read_text())
    evidence=dict(key=request['key'],requested_utc=request['utc'])
    try:
        validate_request(root,request)
        from cst_optimization.core import init_cst_path
        init_cst_path(library)
        from cst.interface import Project
        project=Project.connect(request['project'])
        validate_request(root,request)
        running=project.model3d.is_solver_running(timeout=15)
        evidence['running_before']=running
        if running:
            project.model3d.abort_solver(timeout=60)
            evidence['abort_call_returned']=True
        else:
            evidence['abort_call_returned']=False
            evidence['reason']='solver already stopped; worker must validate results'
        evidence['status']='returned'
    except Exception as exc:
        evidence.update(status='failed',error=repr(exc))
        raise
    finally:
        evidence['utc']=utc()
        write_json(request_path.with_name('abort_response.json'),evidence)


def main() -> None:
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--request',required=True,type=Path)
    parser.add_argument('--cst-library',required=True)
    args=parser.parse_args()
    request_abort(args.root,args.request,args.cst_library)

if __name__=='__main__':main()
