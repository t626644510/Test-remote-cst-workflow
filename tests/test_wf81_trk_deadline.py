"""No-CST validation of the hard wall-time guard and terminal timeout records."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from workflows.trk_multipacting import trk_supervise as s
from workflows.trk_multipacting.trk_run import completed, timed_out

pytestmark=pytest.mark.no_cst

@pytest.mark.parametrize('change,now,expected',[
    ({},309.99,False),({},310,True),({},10000,True),
    ({'finished':True},10000,False),({'owner':{'pid':9}},10000,False),
    ({'key':'another'},10000,False),({'started_monotonic':20000},10000,False),
    ({'limit_s':float('nan')},10000,False),({'limit_s':0},10000,False)])
def test_deadline_identity_and_boundary(change,now,expected):
    owner={'pid':1,'created':2}
    timer=dict(key='case',owner=owner,started_monotonic=10,limit_s=300,finished=False)
    timer.update(change)
    assert s.solve_deadline_reached(timer,owner,'case',now)==expected

@pytest.mark.parametrize('limit',[0,-1,float('nan'),float('inf')])
def test_invalid_limit_rejected(tmp_path,limit):
    with pytest.raises(ValueError):s.Supervisor(tmp_path,Path('unused'),'unused',solve_limit_s=limit)

def fixture(root,monkeypatch):
    owner=dict(pid=10,created=20);key='s01_f100_p000'
    case=root/'cases'/key;case.mkdir(parents=True)
    timer=dict(key=key,owner=owner,started_monotonic=10,limit_s=300,finished=False)
    state=dict(status='running',owner=owner,current=dict(key=key))
    s.write_json(root/'state.json',state);s.write_json(case/'solve_timer.json',timer)
    s.write_json(case/'task.json',dict(key=key))
    work=root/'work/a.cst';log=work.with_suffix('')/'Result/Model.log';log.parent.mkdir(parents=True)
    log.write_text('Running time loop...')
    s.write_json(root/'snapshot.json',dict(project=str(work)))
    calls=[]
    proc=SimpleNamespace(create_time=lambda:20,suspend=lambda:calls.append('suspend'),resume=lambda:calls.append('resume'))
    monkeypatch.setattr(s.psutil,'Process',lambda _:proc)
    monkeypatch.setattr(s.time,'monotonic',lambda:311)
    monkeypatch.setattr(s,'owned_tree',lambda _: [owner])
    monkeypatch.setattr(s,'terminate_verified',lambda rows:calls.append('terminate'))
    monkeypatch.setattr(s,'preserve_lock',lambda *args:calls.append('archive'))
    monkeypatch.setattr(s,'fresh_project',lambda *args:calls.append('fresh'))
    child=SimpleNamespace(wait=lambda **kwargs:calls.append('wait'))
    audit=root/'audit';audit.mkdir()
    return owner,key,case,state,proc,calls,child,audit

def test_timeout_preserved_separate_from_success_and_not_retried(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=fixture(tmp_path,monkeypatch)
    assert s.Supervisor(tmp_path,Path('unused'),'unused').enforce_solve_limit(child,owner,audit,state,[owner])
    assert calls==['suspend','terminate','wait','archive','fresh']
    assert timed_out(tmp_path)=={key} and completed(tmp_path)=={}
    assert (audit/'solve_time_limit/Model.log').read_text()=='Running time loop...'
    assert (audit/'solve_time_limit/case_before_stop/task.json').exists()
    assert not (tmp_path/'guard_retries.json').exists()
    assert s.read_json(case/'timeout.json')['elapsed_s']==301

def test_completion_race_resumes_worker_without_kill(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=fixture(tmp_path,monkeypatch)
    def finish():
        calls.append('suspend')
        timer=s.read_json(case/'solve_timer.json');timer['finished']=True;s.write_json(case/'solve_timer.json',timer)
    proc.suspend=finish
    assert not s.Supervisor(tmp_path,Path('unused'),'unused').enforce_solve_limit(child,owner,audit,state,[owner])
    assert calls==['suspend','resume'] and not timed_out(tmp_path)

def test_cleanup_failure_never_marks_timeout_or_advances(tmp_path,monkeypatch):
    owner,key,case,state,proc,calls,child,audit=fixture(tmp_path,monkeypatch)
    def refused(*args):raise RuntimeError('identity changed')
    monkeypatch.setattr(s,'terminate_verified',refused)
    with pytest.raises(RuntimeError,match='identity'):
        s.Supervisor(tmp_path,Path('unused'),'unused').enforce_solve_limit(child,owner,audit,state,[owner])
    assert 'fresh' not in calls and not timed_out(tmp_path)

def test_all_timeouts_finish_without_launch(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'timed_out',lambda _:{t.key for t in s.tasks()})
    def forbidden(*a,**k):raise AssertionError('Must not launch')
    monkeypatch.setattr(s.subprocess,'Popen',forbidden)
    s.Supervisor(tmp_path,Path('unused'),'unused').run()
    assert s.read_json(tmp_path/'guard_state.json')['status']=='complete_with_timeouts'
    assert s.read_json(tmp_path/'guard_state.json')['completed']==0
