"""Regression coverage for exited handles and cleanup-only recovery."""
import json,subprocess,sys
from types import SimpleNamespace
import pytest
from cst_optimization.core.cleanup import _windows_process_exists,_process_exists
from workflows.rfgun_wake_thermal.fleet import station_recovery as r

@pytest.mark.parametrize('handle,error,wait,expected',[(0,87,0,False),(0,5,0,True),(8,0,0,False),(8,0,258,True),(8,0,0xffffffff,True)])
def test_wait_probe_fail_closed(handle,error,wait,expected):
    closed=[];k=SimpleNamespace(OpenProcess=lambda *x:handle,WaitForSingleObject=lambda *x:wait,CloseHandle=lambda h:closed.append(h))
    assert _windows_process_exists(123,k,lambda:error)==expected
    assert closed==([handle] if handle else [])

def test_exited_process_with_retained_popen_handle():
    child=subprocess.Popen([sys.executable,'-c','pass']);child.wait()
    assert child._handle is not None
    assert _process_exists(child.pid) is False

@pytest.mark.parametrize('variant',['safe','alive','unknown','wrong_session','missing_pid'])
def test_cleanup_only_failure_remains_failed(tmp_path,monkeypatch,variant):
    session=dict(pid=123,session_id='uuid',project='project.cst')
    cleanup=dict(session,success=False,exit_verified=True)
    if variant=='wrong_session':cleanup['session_id']='wrong'
    if variant=='missing_pid':session['pid']=None
    for name,value in [('prepare_session.json',session),('prepare_cleanup.json',cleanup)]:
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
    monkeypatch.setattr(r,'query_pid',lambda pid:variant if variant in ('alive','unknown') else 'absent')
    original=dict(status='failed',category='cleanup_failed',error='exact original cleanup failure')
    if variant!='safe':
        with pytest.raises(r.SessionRecoveryBlocked):r.classify(original,tmp_path)
    else:
        result=r.classify(original,tmp_path)
        assert result['status']=='failed' and result['original_result']==original
        assert result['error']==original['error'] and result['cleanup_only']
