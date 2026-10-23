"""No-CST regression tests for bounded station-local recovery and safety gates."""
from dataclasses import replace
from pathlib import Path
import time
import pytest
from workflows.rfgun_wake_thermal.config import Config, Paths
from workflows.rfgun_wake_thermal.fleet.station_recovery import StationRecovery, classify
from workflows.rfgun_wake_thermal.session_recovery import ensure_sessions_inactive, SessionRecoveryBlocked
from workflows.rfgun_wake_thermal.io import atomic_json, digest

pytestmark=pytest.mark.no_cst

def harness(tmp_path, launch):
    cfg=Config(Paths({s:str(tmp_path/(s+'.cst')) for s in ('axis','x','y','thermal')},str(tmp_path/'state'),str(tmp_path/'artifacts')))
    spec=dict(id='job_1',identity='physical',parameters={},ports=[20,20],stage='axis',timeout_s=30,station_deadline=time.time()+3600)
    return StationRecovery(cfg,tmp_path/'cfg',tmp_path,spec,None,launch,
        quiesce=lambda p:None,probe=lambda:{'free_kib':8*1024**2},sleep=lambda s:None)

def failure():return dict(status='failed',category='solver_failed',error='CST unavailable')

def test_reopen_then_rebuild_exhaustion_is_bounded_and_replay_no_launch(tmp_path):
    calls=[]
    def launch(c,t,*args):calls.append(t);return failure()
    r=harness(tmp_path,launch);folder,result,history=r.run()
    assert len(calls)==5 and result['recovery_exhausted']
    assert [h['tier'] for h in history]==['initial','reopen','reopen','rebuild','rebuild']
    assert len({t['directory'] for t in calls})==5
    assert all(t['ports']==[20,20] and t['identity']=='physical' for t in calls)
    r.run();assert len(calls)==5

@pytest.mark.parametrize('success_at',[1,2,3,4,5])
def test_success_stops_escalation_and_remains_terminal(tmp_path,success_at):
    calls=[]
    def launch(c,t,*args):
        calls.append(t)
        return dict(status='complete') if len(calls)==success_at else failure()
    r=harness(tmp_path,launch);_,result,history=r.run()
    assert result['status']=='complete' and len(history)==success_at
    r.run();assert len(calls)==success_at

def test_crashed_claim_is_recorded_not_reexecuted(tmp_path):
    calls=[]
    r=harness(tmp_path,lambda c,t,*args:(calls.append(t) or failure()))
    f=tmp_path/'jobs/job_1/attempt_00000'
    atomic_json(f/'station_started.json',dict(time=time.time(),identity='physical',tier='initial'))
    _,_,history=r.run()
    assert len(calls)==4 and history[0]['result']['category']=='interrupted'

def test_cap_does_not_abort_admitted_solve_but_defers_next(tmp_path):
    def launch(*args):r.spec['station_deadline']=0;return failure()
    r=harness(tmp_path,launch);_,result,history=r.run()
    assert len(history)==1 and result['category']=='recovery_deferred'
    assert not result['station_recovery_complete']

def test_stop_defers_recovery_without_cross_station_terminal(tmp_path):
    def launch(*args):(tmp_path/'STOP').write_text('stop');return failure()
    r=harness(tmp_path,launch);_,result,history=r.run()
    assert len(history)==1 and result['category']=='recovery_deferred'

def test_low_memory_holds_without_consuming_next_attempt(tmp_path):
    r=harness(tmp_path,lambda *a:failure());r.probe=lambda:{'free_kib':1}
    with pytest.raises(SessionRecoveryBlocked,match='memory'):r.run()
    assert not (tmp_path/'jobs/job_1/attempt_00001/station_started.json').exists()

def test_unknown_ownership_never_retries(tmp_path):
    r=harness(tmp_path,lambda *a:dict(status='failed',category='ownership_failed'))
    with pytest.raises(SessionRecoveryBlocked,match='Ownership'):r.run()

def test_saved_solve_extraction_success_no_second_solve(tmp_path):
    calls=[]
    def launch(c,t,*a):
        calls.append(t)
        if 'result_filename' in t:return dict(status='complete')
        atomic_json(Path(t['directory'])/'solved.json',{'identity':'physical'})
        return dict(status='failed',category='postprocess_failed')
    r=harness(tmp_path,launch);_,result,history=r.run()
    assert result['status']=='complete' and len(calls)==2 and len(history)==1
    assert calls[1]['result_filename']=='worker_result_extraction.json'

def test_saved_solve_extraction_failure_holds_instead_of_resolve(tmp_path):
    calls=[]
    def launch(c,t,*a):
        calls.append(t);atomic_json(Path(t['directory'])/'solved.json',{'identity':'physical'})
        return dict(status='failed',category='postprocess_failed')
    r=harness(tmp_path,launch)
    with pytest.raises(SessionRecoveryBlocked,match='Saved solve'):r.run()
    assert len(calls)==2
    with pytest.raises(SessionRecoveryBlocked):r.run()
    assert len(calls)==2

def test_absence_certificate_scoped_to_session_bytes_and_timestamp(tmp_path):
    p=tmp_path/'attempt_00000/prepare_session.json'
    atomic_json(p,dict(session_id='a',pid=None,project='owned',phase='opening'))
    with pytest.raises(SessionRecoveryBlocked):ensure_sessions_inactive(tmp_path,probe=lambda p:'unknown')
    proof=dict(kind='read_only_global_absence',processes=[],observed_at=time.time()+1,
               session_hashes={str(p.relative_to(tmp_path)):digest(p)})
    atomic_json(tmp_path/'station_quiescence.json',proof)
    ensure_sessions_inactive(tmp_path,probe=lambda p:'unknown')
    atomic_json(p,dict(session_id='b',pid=None,project='owned',phase='opening'))
    with pytest.raises(SessionRecoveryBlocked):ensure_sessions_inactive(tmp_path,probe=lambda p:'unknown')

def test_cleanup_classification_preserves_original(tmp_path):
    original=dict(status='failed',category='cleanup_failed',error='original cleanup failure')
    atomic_json(tmp_path/'prepare_cleanup.json',{'primary_error':'TimeoutError: DE connect'})
    result=classify(original,tmp_path)
    assert result['category']=='session_failed' and result['original_result']==original

def test_quiescence_failure_prevents_every_new_attempt(tmp_path):
    calls=[];r=harness(tmp_path,lambda *a:calls.append(a))
    def blocked(p):raise SessionRecoveryBlocked('still alive')
    r.quiesce=blocked
    with pytest.raises(SessionRecoveryBlocked):r.run()
    assert calls==[]


def test_worker_new_ladder_publishes_only_after_station_exhaustion(tmp_path,monkeypatch):
    from workflows.rfgun_wake_thermal.fleet import worker as w, station_recovery as recovery
    from workflows.rfgun_wake_thermal.fleet.protocol import fingerprint, publish_json
    cfg=harness(tmp_path,lambda *a:None).config
    original=recovery.StationRecovery
    def factory(*args,**kwargs):
        return original(*args,**kwargs,quiesce=lambda p:None,probe=lambda:{'free_kib':8*1024**2},sleep=lambda s:None)
    monkeypatch.setattr(recovery,'StationRecovery',factory)
    monkeypatch.setattr(w,'execution_identity',lambda cfg:{'test':1})
    monkeypatch.setattr(w,'process_birth',lambda pid:123)
    spec=dict(id='job_1',contract='science',parameters={},ports=[20,20],stage='axis',
              node='remote',execution=fingerprint({'test':1}),admit_before=time.time()+60,
              station_deadline=time.time()+3600,station_recovery=True,timeout_s=30)
    spec['identity']=fingerprint({k:spec[k] for k in ('contract','parameters','ports','stage')})
    publish_json(tmp_path/'inbox/job_1.json',spec)
    calls=[]
    def launch(c,t,*args):
        assert not (tmp_path/'jobs/job_1/outcome.json').exists()
        calls.append(t);return failure()
    monkeypatch.setattr(w,'launch_worker',launch)
    pack=w.publish_json
    def publish(path,value):
        pack(path,value)
        if path.name=='outcome.json':(tmp_path/'STOP').write_text('stop')
    monkeypatch.setattr(w,'publish_json',publish)
    w.run_worker(cfg,tmp_path/'cfg',tmp_path,'remote')
    import json,zipfile
    outcome=json.loads((tmp_path/'jobs/job_1/outcome.json').read_text())
    assert len(calls)==5 and outcome['station_attempts']==5 and outcome['result']['recovery_exhausted']
    with zipfile.ZipFile(tmp_path/'jobs/job_1/evidence.zip') as z:
        assert 'station_attempts/attempt_00000/attempt_return.json' in z.namelist()
    status=json.loads((tmp_path/'status.json').read_text())
    assert status['recovery_tier']=='rebuild' and status['attempt_directory'].endswith('attempt_00004')


def test_repair_time_is_cumulative_across_attempts(tmp_path):
    r=harness(tmp_path,lambda *a:failure());r.spec['repair_budget_s']=1
    counter=iter([0,0,2,2,2,2,2,2])
    r.now=lambda:next(counter)
    _,result,history=r.run()
    assert len(history)==1 and result['repair_budget_exhausted']
