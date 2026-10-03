"""Independent worker watchdog and exact owned-process identity checks."""
from __future__ import annotations
import ctypes,json,os,subprocess,sys,time
from pathlib import Path
from .io import atomic_json
from .session_recovery import ensure_sessions_inactive,query_pid


def process_birth(pid: int) -> int | None:
    """Windows creation FILETIME prevents termination of a reused PID."""
    if os.name!='nt':return None
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD);api.OpenProcess.restype=wintypes.HANDLE
    api.GetProcessTimes.argtypes=(wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4));api.GetProcessTimes.restype=wintypes.BOOL
    api.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        times=[wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):return None
        return times[0].dwHighDateTime*2**32+times[0].dwLowDateTime
    finally:api.CloseHandle(handle)


def check_recovery(directory: Path):
    worker=directory/'worker.json'
    if worker.exists():
        info=json.loads(worker.read_text())
        if query_pid(info['pid'])!='absent':
            raise RuntimeError('Previous worker PID remains occupied; refusing duplicate execution')
    ensure_sessions_inactive(directory.parent)


def stop_owned_sessions(directory: Path):
    from cst_optimization.core.cleanup import force_kill_cst
    for p in directory.glob('*_session.json'):
        record=json.loads(p.read_text());pid=record.get('pid')
        if pid and query_pid(pid)=='absent':continue
        birth=record.get('process_birth')
        if not pid or birth is None or process_birth(pid)!=birth:
            raise RuntimeError('Cannot verify CST process identity for watchdog cleanup')
        force_kill_cst(pid)
        if query_pid(pid)!='absent':raise RuntimeError('Owned CST process did not exit')


def launch_worker(config_path: Path,task: dict,store,timeout_s: float) -> dict:
    """Budget is reserved by caller before launch; the parent remains responsive."""
    folder=Path(task['directory']);folder.mkdir(parents=True,exist_ok=True)
    task_path=folder/'task.json';atomic_json(task_path,task)
    check_recovery(folder)
    output=folder/task.get('result_filename','worker_result.json')
    if output.exists():return json.loads(output.read_text())
    entry=Path(__file__).resolve().parents[2]/'run_workflow_6.py'
    with (folder/'worker.stdout.log').open('a',encoding='utf-8') as out,(folder/'worker.stderr.log').open('a',encoding='utf-8') as err:
        process=subprocess.Popen([sys.executable,str(entry),'--config',str(config_path),'worker','--task',str(task_path)],
            stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        birth=process_birth(process.pid)
        atomic_json(folder/'worker.json',dict(pid=process.pid,process_birth=birth,task=task['identity']))
        started=time.monotonic()
        while process.poll() is None:
            time.sleep(min(store.config.runtime.heartbeat_s,5.));store.tick()
            atomic_json(store.root/'heartbeat.json',dict(time=time.time(),pid=os.getpid(),job=task['id'],worker=process.pid,active_seconds=store.state['active_seconds']))
            if time.monotonic()-started>timeout_s:
                # Windows venv python.exe can be a launcher with a second Python
                # child. Terminate the verified owned TREE, not only the launcher.
                from cst_optimization.core.cleanup import force_kill_cst
                if birth is None or process_birth(process.pid)!=birth:
                    raise RuntimeError('Worker process identity changed; watchdog will not kill an unrelated PID')
                if not force_kill_cst(process.pid):raise RuntimeError('Owned worker tree could not be stopped')
                process.wait(timeout=30)
                stop_owned_sessions(folder)
                result=dict(status='failed',category='watchdog_timeout',error='Owned stage exceeded wall-time limit')
                atomic_json(output,result);return result
    if output.exists():return json.loads(output.read_text())
    check_recovery(folder)
    return dict(status='failed',category='worker_crash',error=f'Worker exited {process.returncode} without final record')
