"""Round accounting and transverse policy regression tests; no CST."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pytest
from workflows.rfgun_wake_thermal.config import Config,Paths,NAMES
from workflows.rfgun_wake_thermal.campaign import Campaign
from workflows.rfgun_wake_thermal.policy import transverse_admitted,thermal_shortlist
from workflows.rfgun_wake_thermal.rounds import inherit_state,validate_transition
from workflows.rfgun_wake_thermal.storage import Store,prune_native
from workflows.rfgun_wake_thermal.io import atomic_json,digest

pytestmark=pytest.mark.no_cst

@pytest.fixture
def campaign(tmp_path):
    cfg=Config(Paths({s:str(tmp_path/'sources'/(s+'.cst')) for s in ('axis','x','y','thermal')},str(tmp_path/'state'),str(tmp_path/'bulk')))
    cfg=replace(cfg,search=replace(cfg.search,policy='transverse_coverage',observation_mode='reconstructed_peak_screening'))
    point={n:sum(cfg.bounds[n])/2 for n in NAMES}
    Path(cfg.paths.artifact_dir).mkdir()
    c=Campaign(cfg,tmp_path/'config.yaml','test',dict(baseline=point,templates=cfg.paths.templates))
    yield c
    if c.store.db is not None:
        c.store.last_tick=None
        c.store.db.close()


def observe(c,metric,value,upper=None,**extra):
    u=dict(method='local-reconstructed-consensus-v1',estimate=value,upper=value if upper is None else upper,
           full_band_coverage=True,unbounded=False,relative_uncertainty=.02,contradictory_evidence=False)
    u.update(extra)
    c['details'][metric]=dict(status='uncertain',diagnostics={'reconstructed_peak':u})


@pytest.mark.parametrize('upper,unbounded,coverage,contradiction,admitted',[
    (2000,False,True,False,True),(3000,False,True,False,True),(3000.01,False,True,False,False),
    (1500,True,True,False,False),(1500,False,False,False,False),(1500,False,True,True,False)])
def test_admission_preserves_quality_and_final_targets(campaign,upper,unbounded,coverage,contradiction,admitted):
    c=campaign.state['candidates'][0]
    observe(c,'longitudinal',1500,upper,unbounded=unbounded,full_band_coverage=coverage,contradictory_evidence=contradiction)
    assert transverse_admitted(campaign.config,c)==admitted
    assert campaign.gated(c,'x')is (not admitted)
    assert not campaign.gated(c,'thermal')
    assert campaign.config.physics.longitudinal_limit==2000 and not c['feasible']


def test_protected_exploration_completes_y_and_balances_actual_time(campaign,monkeypatch):
    c=campaign.state['candidates'][0];c['stages']={'axis':{}}
    observe(c,'longitudinal',6000)
    d=campaign.new_candidate(dict(c['parameters'],selfangle1=10),'test');d['stages']={'axis':{},'x':{}}
    observe(d,'longitudinal',6000)
    campaign.state['active_seconds']=30000
    monkeypatch.setattr(campaign.controller,'fit',lambda:None)
    monkeypatch.setattr(campaign.controller,'score',lambda x,cost,*a:np.ones(len(x))/cost)
    monkeypatch.setattr(campaign.controller,'propose',lambda:pytest.fail('Protected allowance must not compete with new GP proposals'))
    assert campaign.select()==(d,'y','near')
    campaign.state['exploration_seconds']['near']=1800
    assert campaign.select()[2]=='global'


def test_no_exploration_credit_does_not_bypass_gate(campaign,monkeypatch):
    c=campaign.state['candidates'][0];c['stages']={'axis':{}}
    observe(c,'longitudinal',5000)
    monkeypatch.setattr(campaign.controller,'fit',lambda:None)
    monkeypatch.setattr(campaign.controller,'propose',lambda:(dict(c['parameters'],selfangle1=10),'test'))
    assert campaign.select()[1:] == ('axis',None)


def test_thermal_shortlist_does_not_charge_exploration(campaign,monkeypatch):
    c=campaign.state['candidates'][0];c['stages']={s:{} for s in ('axis','x','y')}
    observe(c,'longitudinal',2500);observe(c,'transverse',200000)
    assert thermal_shortlist(campaign)=={c['id']}
    monkeypatch.setattr(campaign.controller,'fit',lambda:None)
    monkeypatch.setattr(campaign.controller,'score',lambda x,cost,*a:np.ones(len(x))/cost)
    monkeypatch.setattr(campaign.controller,'propose',lambda:(dict(c['parameters'],selfangle1=10),'test'))
    assert campaign.select()==(c,'thermal',None)


def test_gp_reward_saturates_at_longitudinal_target(campaign,monkeypatch):
    x=np.zeros((1,12))
    def score(l,t):
        monkeypatch.setattr(campaign.controller,'predictions',lambda x:{k:(np.array([np.log1p(v)]),np.zeros(1)) for k,v in zip(('longitudinal','transverse','power5','power6'),(l,t,4,4))})
        return campaign.controller.score(x,1)[0]
    assert score(.1,2)==score(.9,2)
    assert score(.9,1.5)>score(.9,2)
    assert score(2,1)<score(1,2) # Longitudinal violation has greater penalty.


def test_budget_finishes_inflight_stage_then_blocks_next(campaign,monkeypatch):
    from workflows.rfgun_wake_thermal import campaign as module
    c=campaign.state['candidates'][0]
    c['complete']=True;c['stages']={s:{} for s in ('axis','x','y','thermal')}
    c['metrics']={'power5':200,'power6':200};c['details']['thermal']={'status':'valid'}
    observe(c,'longitudinal',1500);observe(c,'transverse',200000)
    d=campaign.new_candidate(dict(c['parameters'],selfangle1=10),'test')
    campaign.state['active_seconds']=48*3600-1
    ticks=[100.]
    monkeypatch.setattr('time.monotonic',lambda:ticks[0])
    calls=[]
    def backend(config,job,store,timeout):
        calls.append(job['id']);ticks[0]+=500;store.tick()
        assert store.state['active_seconds']>48*3600
        return dict(status='complete',identity=job['identity'],raw='saved',result={})
    campaign.backend=backend
    monkeypatch.setattr(module,'offline_candidate',lambda *a:dict(metrics={},details={}))
    monkeypatch.setattr(module,'prune_native',lambda *a:[])
    monkeypatch.setattr(campaign,'select',lambda:(d,'axis',None))
    campaign.run('resume')
    assert len(calls)==1 and 'axis' in d['stages'] and campaign.state['pending'] is None
    assert campaign.state['status']=='budget_exhausted'
    assert (campaign.store.root/'STOP').exists()
    report=json.loads((campaign.store.root/'report.json').read_text())
    assert report['round']['overshoot_hours']==pytest.approx(499/3600)
    with pytest.raises(ValueError,match='Round is closed'):campaign.run('resume')


def test_selection_time_cannot_admit_after_deadline(campaign,monkeypatch):
    campaign.state['active_seconds']=48*3600-1
    campaign.store.last_tick=100.
    monkeypatch.setattr('time.monotonic',lambda:102.)
    campaign.backend=lambda *a:pytest.fail('Deadline expired before dispatch')
    assert not campaign.action(campaign.state['candidates'][0],'axis',None)


def test_inheritance_separates_clocks_preserves_failures_and_replay_guard(campaign):
    c=campaign.state['candidates'][0];c['failed']=True;c['failure']={'category':'solver_failed'}
    j=campaign.store.reserve(c,'axis',campaign.task(c,'axis'),None)
    j.update(status='failed',applied=True);campaign.state.update(pending=None,status='paused',active_seconds=180000.)
    campaign.state['exploration_seconds']['near']=1234
    original=deepcopy(campaign.state)
    new=inherit_state(original,'next')
    assert original==campaign.state and new['candidates']==original['candidates']
    assert new['active_seconds']==0 and new['prior_active_seconds']==180000
    assert new['round_number']==2 and sum(new['exploration_seconds'].values())==0
    assert new['jobs'][0]['inherited']
    campaign.state['contract']='next';campaign.state['jobs']=new['jobs']
    with pytest.raises(ValueError,match='already dispatched'):campaign.task(c,'axis')
    new['active_seconds']=172900
    newer=inherit_state(new,'third')
    assert newer['prior_active_seconds']==352900 and newer['active_seconds']==0 and newer['round_number']==3


@pytest.mark.parametrize('change',[{'status':'running'},{'pending':'job_1'},{'jobs':[{'status':'complete','applied':False}]}])
def test_round_refuses_unfinished_source(campaign,change):
    s=deepcopy(campaign.state);s['status']='paused';s.update(change)
    with pytest.raises(ValueError):inherit_state(s,'next')


def test_transition_blocks_overlap_changed_physics_and_wrong_budget(campaign,tmp_path):
    cfg=campaign.config;campaign.state['status']='paused';campaign.store.save()
    with pytest.raises(ValueError,match='overlaps'):validate_transition(cfg,cfg,campaign.store.root)
    nxt=replace(cfg,paths=replace(cfg.paths,output_dir=str(tmp_path/'next'),artifact_dir=str(tmp_path/'next_bulk')))
    validate_transition(nxt,cfg,campaign.store.root)
    with pytest.raises(ValueError,match='scientific'):validate_transition(replace(nxt,physics=replace(cfg.physics,sigma_m=.07)),cfg,campaign.store.root)
    with pytest.raises(ValueError,match='48 hour'):validate_transition(replace(nxt,search=replace(cfg.search,hours=49)),cfg,campaign.store.root)


def test_retention_never_touches_inherited_native(campaign,tmp_path):
    foreign=tmp_path/'old_round/project';foreign.mkdir(parents=True)
    (foreign/'keep').write_text('old evidence')
    campaign.state['jobs']=[dict(inherited=True,status='complete',candidate='old',directory=str(foreign.parent))]
    atomic_json(campaign.artifacts/'owner.json',{'contract':'test'})
    assert prune_native(campaign.config,campaign.state)==[]
    assert (foreign/'keep').exists()


def test_prepare_round_copies_cache_without_charging_or_modifying_source(campaign,tmp_path,monkeypatch):
    import yaml
    from workflows.rfgun_wake_thermal import rounds
    from workflows.rfgun_wake_thermal import campaign as module
    cfg=campaign.config;source=campaign.store.root
    raw=campaign.artifacts/'raw';raw.mkdir();(raw/'curve.txt').write_text('numerical evidence')
    atomic_json(raw/'manifest.json',{'curve.txt':digest(raw/'curve.txt')})
    c=campaign.state['candidates'][0];c['stages']['axis']={'raw':str(raw),'identity':'original'}
    cache=campaign.artifacts/'evidence'/c['id']/'revision_000';cache.mkdir(parents=True)
    (cache/'analysis.json').write_text('{}');atomic_json(cache/'manifest.json',{'analysis.json':digest(cache/'analysis.json')})
    campaign.state.update(status='paused',active_seconds=1234.)
    campaign.store.save();before=digest(source/'state.json')
    (source/'effective_config.yaml').write_text(yaml.safe_dump({'workflow_6':cfg.as_dict()}))
    nxt=replace(cfg,paths=replace(cfg.paths,output_dir=str(tmp_path/'next'),artifact_dir=str(tmp_path/'next_bulk')))
    monkeypatch.setattr(Config,'validate',lambda *a,**k:None)
    monkeypatch.setattr(rounds,'project_manifest',lambda p:{'same':'content'})
    def initialize(config):
        Path(config.paths.artifact_dir).mkdir()
        atomic_json(Path(config.paths.artifact_dir)/'owner.json',{'contract':'next'})
        return 'next',dict(baseline=c['parameters'],templates=config.paths.templates)
    monkeypatch.setattr(module,'initialize',initialize)
    result=rounds.prepare_round(nxt,tmp_path/'next.yaml',source)
    assert result['solver_starts']==0 and result['active_seconds']==0 and result['prior_active_seconds']==1234
    assert digest(source/'state.json')==before
    target=Path(nxt.paths.output_dir)
    assert (target/'STOP').exists()
    inherited=json.loads((target/'state.json').read_text())
    assert inherited['candidates'][0]['stages']==c['stages']
    assert (Path(nxt.paths.artifact_dir)/'evidence'/c['id']/'revision_000/analysis.json').read_text()=='{}'
    with pytest.raises(ValueError,match='empty'):rounds.prepare_round(nxt,tmp_path/'next.yaml',source)


def test_manual_transverse_backlog_precedes_gp_and_exploration(campaign,monkeypatch):
    first=campaign.state['candidates'][0];first['stages']={'axis':{}}
    observe(first,'longitudinal',2300)
    second=campaign.new_candidate(dict(first['parameters'],selfangle1=10),'test')
    second['stages']={'axis':{}};observe(second,'longitudinal',2600)
    campaign.state['priority_transverse']=[first['id'],second['id']]
    campaign.state['active_seconds']=30000
    monkeypatch.setattr(campaign.controller,'fit',lambda:pytest.fail('Backlog must precede GP work'))
    assert campaign.select()==(first,'x',None)
    first['stages']['x']={}
    assert campaign.select()==(first,'y',None)
    first['stages']['y']={}
    assert campaign.select()==(second,'x',None)
    # Queue survives persistence/recovery; a failure is not a fabricated completion.
    campaign.store.save()
    assert json.loads(campaign.store.file.read_text())['priority_transverse']==[first['id'],second['id']]


@pytest.mark.parametrize('failed,upper',[(True,2300),(False,3100)])
def test_manual_backlog_does_not_override_failure_or_changed_gate(campaign,monkeypatch,failed,upper):
    first=campaign.state['candidates'][0];first['stages']={'axis':{}};first['failed']=failed
    observe(first,'longitudinal',upper)
    second=campaign.new_candidate(dict(first['parameters'],selfangle1=10),'test')
    second['stages']={'axis':{}};observe(second,'longitudinal',2600)
    campaign.state['priority_transverse']=[first['id'],second['id']]
    monkeypatch.setattr(campaign.controller,'fit',lambda:pytest.fail('Eligible backlog should be chosen'))
    assert campaign.select()==(second,'x',None)
