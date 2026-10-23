"""Offline fleet lifecycle and failure-policy regressions; no CST imports."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json, time, zipfile
import pytest
from workflows.rfgun_wake_thermal.config import Config,Paths,NAMES
from workflows.rfgun_wake_thermal.campaign import Campaign
from workflows.rfgun_wake_thermal.fleet.coordinator import FleetCampaign,FleetStore,logical_key
from workflows.rfgun_wake_thermal.fleet.protocol import Node,fingerprint,unpack_evidence,pack_evidence,publish_json
from workflows.rfgun_wake_thermal.fleet.worker import validate_task
from workflows.rfgun_wake_thermal.fleet.transport import validate_relative
from workflows.rfgun_wake_thermal.io import atomic_json,digest
from workflows.rfgun_wake_thermal.rounds import inherit_state

pytestmark=pytest.mark.no_cst

class Relay:
    def __init__(self):self.messages=[];self.snapshot={};self.error=None
    def publish(self,path,data):
        if self.error:raise self.error
        self.messages.append((path,deepcopy(data)))
    def inspect(self):
        if self.error:raise self.error
        return self.snapshot
    def fetch(self,*args):raise AssertionError('Unexpected artifact fetch')

@pytest.fixture
def fleet(tmp_path):
    cfg=Config(Paths({s:str(tmp_path/(s+'.cst')) for s in ('axis','x','y','thermal')},str(tmp_path/'state'),str(tmp_path/'artifacts')))
    cfg=replace(cfg,search=replace(cfg.search,policy='transverse_coverage',observation_mode='reconstructed_peak_screening'))
    point={n:sum(cfg.bounds[n])/2 for n in NAMES}
    c=Campaign(cfg,tmp_path/'cfg','contract',dict(baseline=point,templates=cfg.paths.templates));c.store.db.close()
    nodes=[Node('local',str(tmp_path/'local'),'cfg','python','repo'),Node('remote',str(tmp_path/'remote'),'cfg','python','repo','sshcfg','host')]
    f=FleetCampaign(cfg,tmp_path/'cfg','contract',dict(templates=cfg.paths.templates),nodes,'execution')
    f.transports={n.name:Relay() for n in nodes}
    yield f
    f.store.last_tick=None;f.store.db.close()

def failure(category='solver_failed',error='failure'):
    return dict(status='failed',category=category,error=error,station_recovery_complete=True)

def test_remote_failure_fifo_local_retry_and_only_then_terminal(fleet):
    c=fleet.state['candidates'][0]
    j=fleet.dispatch('remote',c,'axis',None)
    fleet.apply_result(c,j,failure());fleet.state['pending_nodes'].pop('remote')
    assert not c['failed'] and fleet.state['fleet_retry'][0]['node']=='local'
    assert not c['metrics'] and not c.get('screening_metrics')
    assert j['status']=='failed' and j['applied']
    chosen,stage,exp,q=fleet.choose('local');assert chosen is c
    k=fleet.dispatch('local',c,stage,exp,q);fleet.apply_result(c,k,failure())
    assert c['failed'] and not fleet.state['fleet_retry']
    assert len(fleet.state['jobs'])==2

def test_local_failure_also_gets_remote_attempt(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('local',c,'axis',None)
    fleet.apply_result(c,j,failure());assert fleet.state['fleet_retry'][0]['node']=='remote'
    assert not c['failed']

def test_same_candidate_cannot_fly_twice_but_different_can(fleet):
    c=fleet.state['candidates'][0];fleet.dispatch('local',c,'axis',None)
    with pytest.raises(ValueError,match='in flight'):fleet.dispatch('remote',c,'x',None)
    d=fleet.new_candidate(dict(c['parameters'],Lin1=2.),'test')
    fleet.dispatch('remote',d,'axis',None)
    assert len(fleet.state['pending_nodes'])==2

def test_unknown_delivery_and_disconnect_do_not_release_ownership(fleet):
    c=fleet.state['candidates'][0];fleet.transports['remote'].error=ConnectionError('offline')
    with pytest.raises(ConnectionError):fleet.dispatch('remote',c,'axis',None)
    fleet.poll()
    assert 'remote' in fleet.state['pending_nodes'] and not fleet.state['fleet_retry'] and not c['failed']
    assert fleet.state['node_health']['remote']['healthy'] is False

def test_safety_failure_never_queues_another_station(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    with pytest.raises(RuntimeError,match='safety'):fleet.apply_result(c,j,failure('cleanup_failed'))
    assert not fleet.state['fleet_retry'] and fleet.state['pending_nodes']['remote']==j['id']

def test_replay_failure_is_idempotent(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    fleet.apply_result(c,j,failure());fleet.apply_result(c,j,failure())
    assert len(fleet.state['fleet_retry'])==1

def test_port_repair_waits_for_both_stations_and_invalidates_all_stages(fleet):
    c=fleet.state['candidates'][0];c['stages']={'axis':{'evidence':'keep'}}
    error='Waveguide for port 2 is too short. The waveguide must be homogeneous for at least three equidistant mesh planes'
    j=fleet.dispatch('remote',c,'x',None);fleet.apply_result(c,j,failure(error=error))
    assert c['ports']==[20.,20.] and 'axis' in c['stages']
    fleet.state['pending_nodes'].clear();q=fleet.state['fleet_retry'][0]
    k=fleet.dispatch('local',c,'x',None,q);fleet.apply_result(c,k,failure())
    assert c['ports']==[22.,20.] and c['stages']=={} and c['revision']==1
    assert not c['failed'] and j['outcome']['error']==error

def test_budget_blocks_new_dispatch_but_never_discards_pending(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    fleet.state['active_seconds']=48*3600+15
    d=fleet.new_candidate(dict(c['parameters'],Lin1=3.),'test')
    with pytest.raises(ValueError,match='deadline'):fleet.dispatch('local',d,'axis',None)
    assert fleet.state['pending_nodes']['remote']==j['id']

def test_node_success_uses_existing_analysis_path(fleet,monkeypatch):
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    fleet.apply_result(c,j,failure());fleet.state['pending_nodes'].clear()
    q=fleet.state['fleet_retry'][0];k=fleet.dispatch('local',c,'axis',None,q)
    def received(self,candidate,job,result):
        self.store.complete_job(job,result);candidate['stages'][job['stage']]=result;job['applied']=True
    monkeypatch.setattr(Campaign,'receive',received)
    fleet.apply_result(c,k,dict(status='complete',identity=k['identity']))
    assert not c['failed'] and 'axis' in c['stages'] and j['status']=='failed'

def test_expired_admission_is_not_a_solver_failure(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    outcome={k:j[k] for k in ('id','node','identity','execution')};outcome['status']='not_started'
    fleet.accept(j,outcome);assert not c['failed'] and j['status']=='not_started'
    fleet.state['pending_nodes'].clear();q=fleet.state['fleet_retry'][0]
    assert q['node']=='remote'
    fleet.dispatch('remote',c,'axis',None,q)

def test_clock_union_and_no_parallel_double_round_charge(fleet,monkeypatch):
    c=fleet.state['candidates'][0];fleet.dispatch('local',c,'axis','near')
    d=fleet.new_candidate(dict(c['parameters'],Lin1=3.),'test');fleet.dispatch('remote',d,'axis','global')
    fleet.store.last_tick=100.;monkeypatch.setattr('workflows.rfgun_wake_thermal.fleet.coordinator.time.monotonic',lambda:110.)
    fleet.store.tick()
    assert fleet.state['active_seconds']==10
    assert fleet.state['exploration_seconds']=={'near':5.,'global':5.}

def test_paused_clock_does_not_charge_idle_but_pending_resume_does(fleet):
    fleet.state['fleet_clock_at']=time.time()-100
    fleet.store.start_clock();assert fleet.state['active_seconds']==0
    fleet.state['pending_nodes']={'remote':'job'};fleet.state['fleet_clock_at']=time.time()-100
    fleet.store.start_clock();assert 99<fleet.state['active_seconds']<102

def test_task_identity_and_admission_deadline(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None);wire=j['wire']
    validate_task(wire,'remote','execution',wire['admit_before']-1)
    with pytest.raises(TimeoutError):validate_task(wire,'remote','execution',wire['admit_before']+1)
    validate_task(wire,'remote','execution',wire['admit_before']+1,started=True)
    with pytest.raises(ValueError):validate_task(dict(wire,ports=[22,20]),'remote','execution',0)
    with pytest.raises(ValueError):validate_task(wire,'local','execution',0)

@pytest.mark.parametrize('name',['../x','/x','a/../b','C:/a','a\\b','a//b','a\nb','a"b'])
def test_protocol_paths_reject_escape(name):
    with pytest.raises(ValueError):validate_relative(name)

def test_evidence_archive_integrity_and_traversal(tmp_path):
    f=tmp_path/'raw';f.mkdir();(f/'proof').write_text('saved');z=tmp_path/'ok.zip'
    sha=pack_evidence(f,z);unpack_evidence(z,tmp_path/'good',sha)
    with pytest.raises(ValueError,match='digest'):unpack_evidence(z,tmp_path/'bad','0'*64)
    with zipfile.ZipFile(z,'w') as a:a.writestr('../escape','bad')
    with pytest.raises(ValueError,match='Unsafe'):unpack_evidence(z,tmp_path/'bad',digest(z))

def test_immutable_publication(tmp_path):
    p=tmp_path/'job.json';publish_json(p,{'x':1});publish_json(p,{'x':1})
    with pytest.raises(ValueError):publish_json(p,{'x':2})

def test_pending_nodes_block_new_round(fleet):
    fleet.state['status']='paused';fleet.state['pending_nodes']={'remote':'job'}
    with pytest.raises(ValueError,match='unfinished'):inherit_state(fleet.state,'next')

def test_foreign_outcome_cannot_be_applied(fleet):
    c=fleet.state['candidates'][0];j=fleet.dispatch('local',c,'axis',None)
    with pytest.raises(ValueError,match='identity'):fleet.accept(j,dict(id=j['id'],node='remote'))
    assert j['status']=='reserved'

@pytest.mark.parametrize('restart', [False,True])
def test_station_worker_claim_and_replay_never_repeat_solve(fleet,monkeypatch,tmp_path,restart):
    from workflows.rfgun_wake_thermal.fleet import worker as w
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    root=tmp_path/'station';root.mkdir();spec=dict(j['wire'],execution=fingerprint({'test':1}));spec.pop('station_recovery')
    publish_json(root/'inbox'/f'{j["id"]}.json',spec)
    folder=root/'jobs'/j['id']/'attempt_00000'
    monkeypatch.setattr(w,'execution_identity',lambda config:{'test':1})
    monkeypatch.setattr(w,'check_recovery',lambda folder:None)
    monkeypatch.setattr(w,'process_birth',lambda pid:123)
    calls=[]
    def launch(config_path,task,clock,timeout):
        assert (folder.parent/'started.json').exists()
        calls.append(task);(root/'STOP').write_text('stop')
        return failure()
    monkeypatch.setattr(w,'launch_worker',launch)
    if restart:
        folder.mkdir(parents=True)
        publish_json(folder.parent/'started.json',{'time':time.time()-1,'task':spec})
        original_pack=w.pack_evidence
        def pack(path,target):
            (root/'STOP').write_text('stop');return original_pack(path,target)
        monkeypatch.setattr(w,'pack_evidence',pack)
    w.run_worker(fleet.config,tmp_path/'cfg',root,'remote')
    outcome=json.loads((folder.parent/'outcome.json').read_text())
    assert outcome['quiescent'] and outcome['status']=='failed'
    assert len(calls)==(0 if restart else 1)
    if restart:assert outcome['result']['category']=='interrupted'
    assert (folder/'task.json').exists()

def test_station_unsafe_session_holds_task_for_diagnosis(fleet,monkeypatch,tmp_path):
    from workflows.rfgun_wake_thermal.fleet import worker as w
    c=fleet.state['candidates'][0];j=fleet.dispatch('remote',c,'axis',None)
    root=tmp_path/'station';root.mkdir();spec=dict(j['wire'],execution=fingerprint({'test':1}));spec.pop('station_recovery')
    publish_json(root/'inbox'/f'{j["id"]}.json',spec)
    monkeypatch.setattr(w,'execution_identity',lambda config:{'test':1})
    monkeypatch.setattr(w,'process_birth',lambda pid:123)
    monkeypatch.setattr(w,'launch_worker',lambda *a:failure('cleanup_failed'))
    monkeypatch.setattr(w,'check_recovery',lambda folder:None)
    with pytest.raises(RuntimeError,match='Unsafe'):w.run_worker(fleet.config,tmp_path/'cfg',root,'remote')
    assert not (root/'jobs'/j['id']/'outcome.json').exists()
    assert json.loads((root/'status.json').read_text())['status']=='needs_attention'

def test_inflight_and_queued_candidates_are_excluded_from_regular_policy(fleet,monkeypatch):
    c=fleet.state['candidates'][0];fleet.dispatch('remote',c,'axis',None)
    seen=[]
    def select():
        seen.extend(fleet.excluded_candidate_ids)
        return c,'axis',None
    monkeypatch.setattr(fleet,'select',select)
    fleet.choose('local')
    assert c['id'] in seen and not fleet.excluded_candidate_ids

def test_round_inheritance_resets_station_clock_not_legacy_cost(fleet):
    fleet.state.update(status='paused',active_seconds=123.,fleet_clock_at=time.time(),fleet_contract='old',node_seconds={'local':30})
    state=inherit_state(fleet.state,'next')
    assert state['active_seconds']==0 and state['prior_active_seconds']==123
    assert 'fleet_clock_at' not in state and 'fleet_contract' not in state

def test_migration_refuses_live_cst_without_touching_state(fleet,monkeypatch):
    from workflows.rfgun_wake_thermal.fleet import run as r
    fleet.state['status']='paused';fleet.store.save()
    root=fleet.store.root;art=fleet.artifacts;art.mkdir(exist_ok=True)
    atomic_json(art/'owner.json',{'contract':fleet.state['contract']})
    before=(root/'state.json').read_bytes()
    class Result:stdout=b'[{"ProcessId":42,"Name":"CST DESIGN ENVIRONMENT_AMD64.exe"}]'
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**kw:Result())
    with pytest.raises(ValueError,match='processes remain'):
        r.migrate(fleet.config,fleet.config_path,list(fleet.nodes.values()),{'test':1})
    assert (root/'state.json').read_bytes()==before

def test_migration_preserves_round_cost_and_once_only(fleet,monkeypatch):
    from workflows.rfgun_wake_thermal.fleet import run as r
    fleet.state.update(status='paused',active_seconds=500.,prior_active_seconds=100.)
    c=fleet.state['candidates'][0];c.update(failed=True,failure=failure());fleet.store.save()
    fleet.artifacts.mkdir(exist_ok=True);atomic_json(fleet.artifacts/'owner.json',{'contract':'contract'})
    fleet.config_path.write_text('test')
    class Result:stdout=b'[]'
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**kw:Result())
    monkeypatch.setattr(r.shutil,'copytree',lambda *a,**kw:None)
    result=r.migrate(fleet.config,fleet.config_path,list(fleet.nodes.values()),{'test':1})
    state=json.loads(fleet.store.file.read_text())
    assert state['active_seconds']>=500 and state['prior_active_seconds']==100
    assert not state['candidates'][0]['failed'] and state['fleet_retry'][0]['node']=='remote'
    before=fleet.store.file.read_bytes()
    result=r.migrate(fleet.config,fleet.config_path,list(fleet.nodes.values()),{'test':1})
    assert result['status']=='already_migrated' and before==fleet.store.file.read_bytes()


def test_stop_reaches_stations_while_current_attempt_drains(fleet,monkeypatch):
    import workflows.rfgun_wake_thermal.fleet.coordinator as mod
    fleet.dispatch('remote',fleet.state['candidates'][0],'axis',None)
    (fleet.store.root/'STOP').write_text('maintenance')
    calls=[]
    for name,transport in fleet.transports.items():
        transport.stop_when_idle=lambda name=name:calls.append(name)
    monkeypatch.setattr(fleet,'poll',lambda:None)
    monkeypatch.setattr(fleet,'report',lambda:None)
    def finish(_):
        assert set(calls)=={'local','remote'}
        assert fleet.state['pending_nodes']
        fleet.state['pending_nodes'].clear()
    monkeypatch.setattr(mod.time,'sleep',finish)
    fleet.run_fleet()
    assert fleet.state['status']=='paused'


def test_native_prepared_snapshot_stays_on_station(tmp_path):
    folder=tmp_path/'attempt';folder.mkdir()
    (folder/'prepared').mkdir();(folder/'prepared'/'native.cst').write_bytes(b'native')
    (folder/'raw').mkdir();(folder/'raw'/'curve.txt').write_text('numeric')
    target=tmp_path/'evidence.zip';pack_evidence(folder,target)
    with zipfile.ZipFile(target) as z:
        assert z.namelist()==['raw/curve.txt']
