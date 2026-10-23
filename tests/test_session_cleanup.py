"""No-CST ownership and exited-process regression tests."""
import os
import subprocess
import sys
from types import SimpleNamespace
import pytest
from cst_optimization.core.cleanup import _windows_process_exists, _process_exists
from cst_optimization.core import session_cleanup as cleanup

@pytest.mark.parametrize("handle,error,wait,expected", [(0,87,0,False),(0,5,0,True),(8,0,0,False),(8,0,258,True),(8,0,0xffffffff,True)])
def test_windows_wait_probe(handle,error,wait,expected):
    closed=[]
    kernel=SimpleNamespace(OpenProcess=lambda *args:handle, WaitForSingleObject=lambda *args:wait, CloseHandle=closed.append)
    assert _windows_process_exists(123,kernel,lambda:error) is expected
    assert closed == ([handle] if handle else [])

@pytest.mark.skipif(os.name != "nt", reason="Windows retained process handle")
def test_exited_process_with_retained_handle():
    child=subprocess.Popen([sys.executable,"-c","pass"])
    child.wait()
    assert child._handle is not None
    assert _process_exists(child.pid) is False

@pytest.mark.parametrize("created,parent,expected", [(2.,os.getpid(),True),(1.,os.getpid(),False),(2.,-1,False)])
def test_cleanup_checks_session_identity(monkeypatch,created,parent,expected):
    calls=[]
    proc=SimpleNamespace(create_time=lambda:created,ppid=lambda:parent,children=lambda:[])
    monkeypatch.setattr(cleanup.psutil,"Process",lambda pid:proc)
    connection=SimpleNamespace(close_targeted=lambda **kw:calls.append(kw) or {"success":True})
    if expected:
        assert cleanup.close_owned_session(connection,123,2.)["success"]
        assert calls == [{"pid_override":123,"timeout_s":15}]
    else:
        with pytest.raises(RuntimeError,match="ownership"):
            cleanup.close_owned_session(connection,123,2.)
        assert not calls

def test_cleanup_refuses_unverified_exit(monkeypatch):
    proc=SimpleNamespace(create_time=lambda:2.,ppid=os.getpid,children=lambda:[])
    monkeypatch.setattr(cleanup.psutil,"Process",lambda pid:proc)
    connection=SimpleNamespace(close_targeted=lambda **kw:{"success":False})
    with pytest.raises(RuntimeError,match="cleanup failed"):
        cleanup.close_owned_session(connection,123,2.)
