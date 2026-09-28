"""No-CST checks for global permits, distinct asynchronous jobs and artifact replay."""
from dataclasses import replace
import json
from pathlib import Path
import time
import zipfile

import pytest

from workflows.rfgun_hom_target.config import (PARAMETER_DEFAULTS, ParameterConfig,
    PathsConfig, PhysicsConfig, SearchConfig, WorkflowConfig)
from workflows.rfgun_hom_target.storage import CampaignStore, atomic_json, digest
from workflows.rfgun_hom_target.distributed import coordinator as module
from workflows.rfgun_hom_target.distributed.coordinator import AsyncPlanner, Coordinator, issue_permit
from workflows.rfgun_hom_target.distributed.protocol import Node, publish_json, unpack_evidence
from workflows.rfgun_hom_target.distributed.worker import execute_task, PermitClient

pytestmark = pytest.mark.no_cst


def test_atomic_publish_retries_sharing_violation_preserving_previous_json(tmp_path, monkeypatch):
    from workflows.rfgun_hom_target import storage
    path = tmp_path / 'heartbeat.json'
    atomic_json(path, {'status': 'evaluating'})
    original = storage.os.replace
    calls = []
    def replace(source, destination):
        calls.append(1)
        if len(calls) < 3:
            assert json.loads(path.read_text()) == {'status': 'evaluating'}
            raise PermissionError('Windows sharing violation')
        original(source, destination)
    monkeypatch.setattr(storage.os, 'replace', replace)
    monkeypatch.setattr(storage.time, 'sleep', lambda _: None)
    atomic_json(path, {'status': 'ready'})
    assert len(calls) == 3
    assert json.loads(path.read_text()) == {'status': 'ready'}


def test_atomic_publish_persistent_failure_is_bounded(tmp_path, monkeypatch):
    from workflows.rfgun_hom_target import storage
    calls = []
    def denied(*args):
        calls.append(1)
        raise PermissionError('denied')
    monkeypatch.setattr(storage.os, 'replace', denied)
    monkeypatch.setattr(storage.time, 'sleep', lambda _: None)
    with pytest.raises(PermissionError):
        atomic_json(tmp_path / 'state.json', {'solve_count': 12})
    assert len(calls) == 11


def test_heartbeat_survives_io_failure_and_reports_current_ready_state(tmp_path, monkeypatch, caplog):
    import threading
    from workflows.rfgun_hom_target.distributed import worker
    stopped = threading.Event()
    info = dict(active='candidate', status='evaluating')
    calls = []
    def publish(path, value):
        calls.append(value)
        if len(calls) == 1:
            info.update(active=None, status='ready')
            raise PermissionError('sharing violation')
        atomic_json(path, value)
        stopped.set()
    monkeypatch.setattr(worker, 'atomic_json', publish)
    with caplog.at_level('INFO'):
        worker.write_heartbeats(tmp_path, info, stopped, interval_s=0.)
    assert len(calls) == 2
    assert json.loads((tmp_path / 'heartbeat.json').read_text())['status'] == 'ready'
    assert 'Heartbeat publication recovered' in caplog.text


@pytest.fixture
def setup(tmp_path):
    config = WorkflowConfig(paths=PathsConfig(tmp_path/'template.cst',tmp_path/'campaign'),
        parameters=tuple(ParameterConfig(*p) for p in PARAMETER_DEFAULTS),
        physics=PhysicsConfig(z_range_mm=(-235.,235.)),
        search=SearchConfig(max_solves=40, initial_points=12, candidate_pool=32))
    store = CampaignStore(config.paths.output_dir,'identity',40)
    baseline = dict(selfangle2=45.,UpperHeight2=26.,DownHeight2=4.,Lin2=12.,inner_angle3=71.,inner_r2=12.)
    store.state['records']=[dict(id='baseline',status='valid',parameters=baseline,
        worst=400000.,objective=1.6,attempt_dir=str(tmp_path))]
    yield config,store,baseline
    store.close()


def request(task='a', identity='r1'):
    return dict(task_id=task,request_id=identity,contract='identity',attempt='owned')


def test_duplicate_and_lost_reply_do_not_consume_budget_twice(setup):
    _,store,_=setup
    job=dict(id='a',node='remote')
    first=issue_permit(store,request(),job)
    assert first['number']==1
    store.state=json.loads(store.path.read_text()) # Coordinator restart after lost SSH reply.
    assert issue_permit(store,request(),job)==first
    assert store.state['solve_count']==1


def test_two_workers_share_hard_40_and_retry_consumes_another_slot(setup):
    _,store,_=setup
    store.state['solve_count']=38
    assert issue_permit(store,request('a','one'),dict(id='a',node='local'))['number']==39
    assert issue_permit(store,request('b','two'),dict(id='b',node='remote'))['number']==40
    assert 'denied' in issue_permit(store,request('a','retry'),dict(id='a',node='local'))
    assert store.state['solve_count']==40


def test_identity_mismatch_and_target_stop_never_start_solver(setup):
    _,store,_=setup
    with pytest.raises(ValueError):
        issue_permit(store,request('foreign'),dict(id='a',node='remote'))
    store.state['target_reached']=True
    assert 'denied' in issue_permit(store,request(),dict(id='a',node='remote'))
    assert store.state['solve_count']==0


def test_pending_points_excluded_and_never_used_as_gp_observations(setup):
    config,store,baseline=setup
    planner=AsyncPlanner(config,store.state)
    pending=[]
    for i in range(4):
        params,source=planner.ask_async(baseline,pending)
        assert all(planner.key(params)!=planner.key(p['parameters']) for p in pending)
        pending.append(dict(parameters=params))
    assert len(store.state['records'])==1
    assert planner.valid_training_data()[0].shape==(1,6)


def test_message_replay_is_immutable(tmp_path):
    path=tmp_path/'task.json'
    publish_json(path,{'id':'one'})
    publish_json(path,{'id':'one'})
    with pytest.raises(ValueError): publish_json(path,{'id':'two'})
    assert json.loads(path.read_text())=={'id':'one'}


@pytest.mark.parametrize('member',['../bad','C:/bad','/bad','x/../../bad'])
def test_artifact_path_escape_rejected_before_extraction(tmp_path,member):
    artifact=tmp_path/'result.zip'
    with zipfile.ZipFile(artifact,'w') as stream: stream.writestr(member,'bad')
    with pytest.raises(ValueError): unpack_evidence(artifact,tmp_path/'out',digest(artifact))
    assert not (tmp_path/'out').exists()


def test_artifact_tampering_rejected(tmp_path):
    artifact=tmp_path/'result.zip'
    with zipfile.ZipFile(artifact,'w') as stream: stream.writestr('field.txt','data')
    with pytest.raises(ValueError): unpack_evidence(artifact,tmp_path/'out','wrong')


def test_worker_completed_task_is_not_run_again(setup,tmp_path):
    config,store,baseline=setup
    job=tmp_path/'jobs/a';job.mkdir(parents=True)
    atomic_json(job/'task.json',dict(id='a',parameters=baseline,contract='identity'))
    calls=[]
    def factory(config,template):
        def evaluate(params,root,reserve):
            calls.append(params)
            root.mkdir()
            return dict(status='geometry_failed',worst=None)
        return evaluate
    execute_task(job,config,'identity',factory)
    execute_task(job,config,'identity',factory)
    assert len(calls)==1
    assert (job/'evidence.zip').is_file()


def test_worker_rejects_different_contract_before_cst(setup,tmp_path):
    config,_,baseline=setup
    job=tmp_path/'a';job.mkdir()
    atomic_json(job/'task.json',dict(id='a',parameters=baseline,contract='old'))
    with pytest.raises(ValueError): execute_task(job,config,'new',lambda *a: pytest.fail('no CST'))


class FakeTransport:
    def __init__(self,node):
        self.node=node
        self.snapshot=dict(heartbeat=dict(contract='identity',status='ready',timestamp=time.time()),jobs={})
        self.sent=[]
        self.fail=False
    def inspect(self):
        if self.fail: raise ConnectionError('offline')
        return self.snapshot
    def publish(self,path,value):
        self.sent.append((path,value))


def make_coordinator(setup,monkeypatch):
    config,store,baseline=setup
    monkeypatch.setattr(module,'read_baseline',lambda *a: baseline)
    monkeypatch.setattr(module,'Transport',FakeTransport)
    monkeypatch.setattr(module.Campaign,'report',lambda self: {})
    return Coordinator(config,store,[Node('local','a','b','c','d'),Node('remote','e','f','g','h')])


def test_two_distinct_candidates_and_no_duplicates_on_disconnect_resume(setup,monkeypatch):
    c=make_coordinator(setup,monkeypatch)
    c.tick()
    active=c.active()
    assert len(active)==2
    assert active[0]['parameters']!=active[1]['parameters']
    c.nodes['remote'].fail=True
    c.tick()
    assert len(c.active())==2
    assert c.store.state['solve_count']==0
    assert c.store.state['node_status']['remote']['status']=='unavailable'


def test_success_already_observed_prevents_initial_batch_dispatch(setup,monkeypatch):
    c=make_coordinator(setup,monkeypatch)
    c.store.state['target_reached']=True
    c.tick()
    assert not c.active()


def test_mismatched_worker_cannot_receive_tasks_or_grants(setup,monkeypatch):
    c=make_coordinator(setup,monkeypatch)
    c.nodes['remote'].snapshot['heartbeat']['contract']='wrong'
    c.tick()
    assert [j['node'] for j in c.active()]==['local']
    assert not c.nodes['remote'].sent


def test_unstarted_task_reserves_capacity_without_charging_cst(setup,monkeypatch):
    c=make_coordinator(setup,monkeypatch)
    c.store.state['solve_count']=39
    c.tick()
    assert len(c.active())==1
    assert c.store.state['solve_count']==39


def test_completed_valid_without_raw_field_bundle_is_rejected(setup,tmp_path):
    config,_,baseline=setup
    task=dict(id='a',parameters=baseline,contract='identity')
    with pytest.raises(ValueError,match='evidence'):
        module.validate_return(config,task,{**task,'result':dict(status='valid',worst=0)},tmp_path)


def test_remote_raw_fields_replayed_and_changed_scores_or_settings_rejected(setup,tmp_path,monkeypatch):
    from dataclasses import asdict
    from workflows.rfgun_hom_target import postprocess as pp
    from workflows.rfgun_hom_target.runtime import postprocess_config
    from test_workflow5_physics import write_raw
    config,_,baseline=setup
    config=replace(config,physics=replace(config.physics,z_range_mm=(-100.,100.),z_samples=101,mode_policy='largest_two'))
    info={'length_unit':'mm','frequency_unit':'MHz'}
    monkeypatch.setattr(module,'metadata',lambda path: info)
    options=postprocess_config(config,info)
    evidence=tmp_path/'raw';bundle=evidence/'attempt_000/postprocess_000'
    modes=[pp.NativeMode(1,1.04e9,1000),pp.NativeMode(2,1.05e9,1000)]
    for mode in modes: write_raw(bundle/'fields'/f'mode_{mode.mode_number}',mode,options)
    atomic_json(bundle/'field_config.json',{**asdict(options),'band_mhz':[1030.,1060.]})
    atomic_json(bundle/'native.json',{'modes':[m.to_dict() for m in modes]})
    processed=pp.analyze_bundle(bundle)
    assert processed.quality_ok
    task=dict(id='a',parameters=baseline,contract='identity')
    outcome={**task,'result':dict(status='valid',worst=processed.worst_impedance_ohm_per_m,modes=json.loads(json.dumps(processed.to_dict())))}
    assert module.validate_return(config,task,outcome,evidence)['worst']==processed.worst_impedance_ohm_per_m
    outcome['result']['worst']=0.
    with pytest.raises(ValueError,match='score'):
        module.validate_return(config,task,outcome,evidence)
    outcome['result']['worst']=processed.worst_impedance_ohm_per_m
    settings=json.loads((bundle/'field_config.json').read_text())
    settings['gradient_tolerance']=1.
    atomic_json(bundle/'field_config.json',settings)
    with pytest.raises(ValueError,match='convention'):
        module.validate_return(config,task,outcome,evidence)


def test_roundoff_allowed_but_nans_and_physical_changes_rejected():
    assert module.equivalent_metrics({'z':[1.]},{'z':[1.+1e-12]})
    assert not module.equivalent_metrics({'z':[1.]},{'z':[.99]})
    assert not module.equivalent_metrics(float('nan'),float('nan'))
    assert not module.equivalent_metrics(False,0)


def test_worker_after_geometry_failure_does_not_charge_budget(setup,tmp_path):
    config,_,baseline=setup
    job=tmp_path/'a';job.mkdir()
    atomic_json(job/'task.json',dict(id='a',parameters=baseline,contract='identity'))
    def factory(*args):
        return lambda params,path,reserve: dict(status='save_failed',worst=None)
    execute_task(job,config,'identity',factory)
    assert not list((job/'requests').glob('*.json'))


def test_resume_with_already_successful_record_does_not_dispatch(setup,monkeypatch):
    setup[1].state['records'][0]['worst']=90000.
    c=make_coordinator(setup,monkeypatch)
    c.tick()
    assert c.store.state['target_reached'] is True
    assert not c.active()


def test_postprocessing_recovery_preserves_solve_journal_and_failed_outcome(tmp_path,monkeypatch):
    from workflows.rfgun_hom_target.distributed.run import recover_postprocess
    from workflows.rfgun_hom_target import runtime,session_recovery
    root=tmp_path/'worker';job=root/'jobs/a'
    atomic_json(job/'outcome.json',{'result':{'status':'postprocess_failed'}})
    journal={'phase':'postprocess_pending','project':'saved.cst','current':'attempt_000','attempts':1}
    atomic_json(job/'evaluation/evaluation.json',journal)
    atomic_json(root/'STOP',{})
    monkeypatch.setattr(runtime,'verify_solved',lambda *args: {})
    monkeypatch.setattr(session_recovery,'ensure_sessions_inactive',lambda *args: None)
    result=recover_postprocess(root,'a')
    assert result['new_solve_required'] is False
    assert json.loads((job/'evaluation/evaluation.json').read_text())==journal
    assert len(list(job.glob('outcome.failed-*.json')))==1
    assert not (job/'outcome.json').exists()
    assert not (root/'STOP').exists()


def test_recovery_cannot_take_over_an_active_worker(tmp_path):
    from workflows.rfgun_hom_target.distributed.run import recover_postprocess
    from workflows.rfgun_hom_target.distributed.protocol import owner_lock
    with owner_lock(tmp_path/'worker.lock'):
        with pytest.raises(OSError): recover_postprocess(tmp_path,'a')


def test_serial_import_preserves_total_budget_and_all_records(setup,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from workflows.rfgun_hom_target.distributed import migration
    from workflows.rfgun_hom_target.storage import fingerprint
    config,store,baseline=setup
    store.state['records']=[]
    source=tmp_path/'old';source.mkdir()
    (source/'campaign.lock').write_bytes(b'0')
    old_config=config.as_dict();old_config['search']['max_solves']=36
    original={'config':old_config,'template':{'original.cst':'hash'},'code':{'physics.py':'oldhash'}}
    path=source/'evaluations/baseline';bundle=path/'attempt_000/postprocess_000'
    atomic_json(bundle/'field_config.json',{})
    record=dict(id='baseline',status='valid',parameters=baseline,worst=400000.,objective=1.6,
                attempt_dir=str(path),modes={'modes':[]})
    old=dict(contract=fingerprint(original),records=[record],pending=None,solve_count=4,
             reservations=[dict(number=i+1,attempt=str(i)) for i in range(4)],rng_state=None,
             radius=.25,improvements=0,no_improvement=0)
    atomic_json(source/'state.json',old);atomic_json(source/'config.resolved.json',old_config)
    atomic_json(source/'original.json',original)
    monkeypatch.setattr(migration,'project_manifest',lambda p: original['template'])
    monkeypatch.setattr(migration,'analyze_bundle',lambda p: SimpleNamespace(quality_ok=True,
        worst_impedance_ohm_per_m=400000.,to_dict=lambda:{'modes':[]}))
    migration.import_serial(config,store,source,source/'original.json',4)
    assert store.state['solve_count']==8
    assert store.state['records']==[record]
    assert store.max_solves-store.state['solve_count']==32
    assert json.loads((source/'state.json').read_text())==old


def test_new_budget_grants_denied_after_another_node_passes(setup,monkeypatch):
    c=make_coordinator(setup,monkeypatch)
    c.tick()
    local=next(j for j in c.active() if j['node']=='local')
    remote=next(j for j in c.active() if j['node']=='remote')
    c.nodes['local'].snapshot['jobs'][local['id']]={'requests':[],'outcome':{'fake':'pass'}}
    c.nodes['remote'].snapshot['jobs'][remote['id']]={'requests':[request(remote['id'],'second')],'outcome':None}
    def accept(job,outcome):
        job['state']='finished'
        c.store.state['target_reached']=True
    monkeypatch.setattr(c,'accept',accept)
    c.tick()
    responses=[v for k,v in c.nodes['remote'].sent if '/grants/' in k]
    assert responses[-1]['denied']=='Target already reached'
    assert c.store.state['solve_count']==0
