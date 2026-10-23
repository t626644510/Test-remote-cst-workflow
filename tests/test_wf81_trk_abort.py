"""Native abort dispatch, grace, stale task and ownership checks without CST."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from workflows.trk_multipacting import trk_supervise as s
from workflows.trk_multipacting import trk_abort as a
from test_wf81_trk_deadline import fixture
pytestmark=pytest.mark.no_cst

def setup(root,monkeypatch):
    parts=fixture(root,monkeypatch)
    owner,key,case,state,proc,calls,child,audit=parts
    timer=s.read_json(case/'solve_timer.json');timer['stop_policy']='native_abort_then_collect'
    s.write_json(case/'solve_timer.json',timer)
    s.write_json(root/'owner.json',dict(owner,cst_pid=11,cst_created=21))
    monkeypatch.setattr(s.subprocess,'Popen',lambda *args,**kwargs:SimpleNamespace(pid=50))
    monkeypatch.setattr(s,'identity',lambda _:dict(pid=50,created=22))
    return parts

def test_first_deadline_requests_abort_without_suspend_kill_or_timeout(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=setup(tmp_path,monkeypatch)
    sup=s.Supervisor(tmp_path,Path('unused'),'unused')
    assert not sup.enforce_solve_limit(child,owner,audit,state,[owner])
    assert calls==[] and not s.timed_out(tmp_path)
    request=s.read_json(case/'abort_request.json')
    assert request['owner']==owner and request['key']==key
    def no_second(*args,**kwargs):raise AssertionError('Duplicate abort helper')
    monkeypatch.setattr(s.subprocess,'Popen',no_second)
    monkeypatch.setattr(s.time,'monotonic',lambda:490.9)
    assert not sup.enforce_solve_limit(child,owner,audit,state,[owner])
    assert calls==[]

def test_unresponsive_abort_fallback_only_after_grace(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=setup(tmp_path,monkeypatch)
    sup=s.Supervisor(tmp_path,Path('unused'),'unused')
    assert not sup.enforce_solve_limit(child,owner,audit,state,[owner])
    monkeypatch.setattr(s.time,'monotonic',lambda:491)
    assert sup.enforce_solve_limit(child,owner,audit,state,[owner])
    assert calls==['suspend','terminate','wait','archive','fresh']
    assert s.read_json(case/'timeout.json')['abort_request']['reason']=='solve_wall_limit'

def test_finished_partial_result_not_killed_at_grace(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=setup(tmp_path,monkeypatch)
    sup=s.Supervisor(tmp_path,Path('unused'),'unused')
    sup.enforce_solve_limit(child,owner,audit,state,[owner])
    timer=s.read_json(case/'solve_timer.json');timer['finished']=True;s.write_json(case/'solve_timer.json',timer)
    monkeypatch.setattr(s.time,'monotonic',lambda:1000)
    assert not sup.enforce_solve_limit(child,owner,audit,state,[owner])
    assert calls==[]

def test_helper_refuses_changed_case_and_reused_cst(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=setup(tmp_path,monkeypatch)
    sup=s.Supervisor(tmp_path,Path('unused'),'unused')
    sup.enforce_solve_limit(child,owner,audit,state,[owner])
    request=s.read_json(case/'abort_request.json')
    processes={10:SimpleNamespace(pid=10,create_time=lambda:20),
               11:SimpleNamespace(pid=11,create_time=lambda:21,ppid=lambda:10)}
    monkeypatch.setattr(a.psutil,'Process',lambda pid:processes[pid])
    a.validate_request(tmp_path,request)
    processes[11].create_time=lambda:19
    with pytest.raises(RuntimeError,match='ownership'):a.validate_request(tmp_path,request)
    state['current']['key']='other';s.write_json(tmp_path/'state.json',state)
    with pytest.raises(RuntimeError,match='identity/task'):a.validate_request(tmp_path,request)


@pytest.mark.parametrize('active,requested,text,ok',[
    (['particle1'],False,'',True),
    ([],True,'Particle Tracking Solver has been aborted. Statistics for particle source particle1:',True),
    ([],False,'Particle Tracking Solver has been aborted. Statistics for particle source particle1:',False),
    ([],True,'Statistics for particle source particle1:',False),
    (['particle2'],True,'Particle Tracking Solver has been aborted. Statistics for particle source particle1:',False),
    ([],True,'Particle Tracking Solver has been aborted. Statistics for particle source particle2:',False)])
def test_native_abort_source_curve_exception_is_narrow(active,requested,text,ok):
    from workflows.trk_multipacting.trk_run import validate_source_currents
    if ok:assert validate_source_currents(active,'particle1',text,requested)
    else:
        with pytest.raises(ValueError):validate_source_currents(active,'particle1',text,requested)
