"""WF6.1 invariants using synthetic evidence only; no CST sessions."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pytest
from workflows.rfgun_wake_thermal.config import Config, Paths, NAMES
from workflows.rfgun_wake_thermal.campaign import Campaign
from workflows.rfgun_wake_thermal.geometry import Geometry
from workflows.rfgun_wake_thermal.heat_policy import HeatController, formal_longitudinal
from workflows.rfgun_wake_thermal.search import make_controller
from workflows.rfgun_wake_thermal.fleet.coordinator import FleetCampaign
from workflows.rfgun_wake_thermal.fleet.protocol import Node
from workflows.rfgun_wake_thermal.io import atomic_json, digest

pytestmark = pytest.mark.no_cst


@pytest.fixture
def cfg(tmp_path):
    c = Config(Paths({s:str(tmp_path/(s+'.cst')) for s in ('axis','thermal')},str(tmp_path/'state'),str(tmp_path/'bulk')))
    fixed = dict(UpperHeight1=49.9, UpperHeight2=49.9, DownHeight1=-47., DownHeight2=-47.)
    a = dict(zip(NAMES,[18.,49.9,-47.,3.,18.,9.,121.,49.9,-47.,26.,19.,28.]))
    b = dict(zip(NAMES,[136.,49.9,-47.,2.,8.,29.,15.,49.9,-47.,5.,16.,29.]))
    widths = {k:(20. if 'angle' in k else 10. if 'Lin' in k else 3. if 'projection' in k else 5.) for k in NAMES if k not in fixed}
    c = replace(c,fixed_parameters=fixed,physics=replace(c.physics,longitudinal_limit=1500.),
                search=replace(c.search,policy='longitudinal_heat',observation_mode='reconstructed_peak_screening',
                               seed_points=(a,b),neighborhood_half_widths=widths,pool=32))
    c.validate()
    return c


@pytest.fixture
def campaign(cfg,tmp_path):
    c = Campaign(cfg,tmp_path/'cfg','contract',dict(baseline=cfg.search.seed_points[0],templates=cfg.paths.templates))
    yield c
    c.store.last_tick=None
    c.store.db.close()


def observed(c, qualified=True, heat=(120.,130.), upper=1400.):
    u = dict(method='local-reconstructed-consensus-v1',full_band_coverage=True,estimate=1300.,upper=upper,
             unbounded=False,contradictory_evidence=False,qualified=qualified,relative_uncertainty=.25)
    c['details']={'longitudinal':{'diagnostics':{'reconstructed_peak':u}},'thermal':{'status':'valid'}}
    c['metrics']={'power5':heat[0],'power6':heat[1]}
    if qualified:c['metrics']['longitudinal']=1300.
    c['stages']={'axis':{},'thermal':{}}
    c['complete']=True
    return c


def test_fixed_domain_and_two_neighborhoods(campaign):
    c=campaign;ctl=c.controller
    assert isinstance(ctl,HeatController) and len(ctl.names)==8
    points=ctl.pool()
    assert points.shape==(32,8)
    neighborhoods=set()
    for row in points:
        p=ctl.decode(row)
        assert all(p[k]==v for k,v in c.config.fixed_parameters.items())
        assert not Geometry(c.config).violations(p)
        matching=[i for i,seed in enumerate(c.config.search.seed_points)
                  if all(abs(p[k]-seed[k])<=c.config.search.neighborhood_half_widths[k]+1e-9 for k in ctl.names)]
        assert matching
        neighborhoods.update(matching)
    assert neighborhoods=={0,1}
    with pytest.raises(ValueError):c.new_candidate(dict(c.config.search.seed_points[0],UpperHeight1=50.),'bad')


def test_formal_vs_uncertain_and_no_transverse_dependency(campaign):
    c=observed(campaign.state['candidates'][0],qualified=False)
    assert not formal_longitudinal(campaign.config,c)
    c['complete']=False;c['stages'].pop('thermal')
    # Finish creating the second seed before promoting heat.
    campaign.select()
    second=campaign.state['candidates'][1];second['failed']=True
    chosen,stage,_=campaign.select()
    assert chosen is c and stage=='thermal'
    c=observed(c,qualified=True)
    assert formal_longitudinal(campaign.config,c) and 'transverse' not in c['metrics']
    assert campaign.next_stage(c) is None


def test_old_geometry_never_enters_reduced_gp(campaign):
    c=observed(deepcopy(campaign.state['candidates'][0]))
    c['parameters']=dict(c['parameters'],UpperHeight1=40.)
    c.update(source_kind='common_band_history',evidence_verified=True,
             band_hz=list(campaign.config.physics.band_hz),wake_length_m=campaign.config.physics.wake_length_m)
    campaign.state['historical_observations']=[c]
    assert campaign.controller.training_rows('longitudinal')==[]
    assert campaign.controller.training_rows('power5')==[]


def test_partial_reconstruction_keeps_uncertainty_in_gp(campaign):
    observed(campaign.state['candidates'][0],qualified=False)
    rows=campaign.controller.training_rows('longitudinal')
    assert len(rows)==1 and rows[0][2]==.25
    for i,row in enumerate(campaign.controller.pool()[:6]):
        observed(campaign.new_candidate(campaign.controller.decode(row),'test'),heat=(100.+i,120.+i))
    campaign.controller.fit()
    assert set(campaign.controller.models)=={'longitudinal','power5','power6'}
    assert all(m.n_features_in_==8 for m in campaign.controller.models.values())


def test_heat_improvement_continues_below_150(campaign,monkeypatch):
    observed(campaign.state['candidates'][0],heat=(100.,110.))
    def predictions(x):
        return {'longitudinal':(np.full(2,np.log1p(.5)),np.zeros(2)),
                'power5':(np.log1p(np.array([80.,120.])/150),np.zeros(2)),
                'power6':(np.log1p(np.array([90.,130.])/150),np.zeros(2)),
                'transverse':(np.full(2,1e6),np.zeros(2))}
    monkeypatch.setattr(campaign.controller,'predictions',predictions)
    scores=campaign.controller.score(np.zeros((2,8)),1.)
    assert scores[0]>scores[1]+.1
    assert campaign.store.can_start(0)


def test_report_keeps_multiple_formal_solutions_separate(campaign):
    observed(campaign.state['candidates'][0],heat=(110.,120.))
    observed(campaign.new_candidate(dict(campaign.config.search.seed_points[1]),'wf61_seed'),heat=(100.,105.))
    p=campaign.controller.decode(campaign.controller.pool()[0])
    observed(campaign.new_candidate(p,'test'),qualified=False,heat=(50.,60.))
    campaign.report()
    r=json.loads((campaign.store.root/'report.json').read_text())
    assert r['formal_feasible']==2 and len(r['screening_candidates'])==3
    assert r['best']['id']=='candidate_0001' and r['desired_targets_reached']
    assert not r['transverse_evaluated'] and campaign.state['status']!='budget_exhausted'


def test_receive_finishes_after_axis_thermal_only(campaign,monkeypatch):
    from workflows.rfgun_wake_thermal import campaign as module
    c=campaign.state['candidates'][0];c['stages']={'axis':{}}
    good=observed(deepcopy(c))
    monkeypatch.setattr(module,'offline_candidate',lambda *a:{k:good[k] for k in ('metrics','details')})
    j={'id':'job_00000','stage':'thermal','status':'reserved','candidate':c['id']}
    campaign.state['jobs'].append(j)
    monkeypatch.setattr(campaign.store,'mirror',lambda:None)
    campaign.receive(c,j,dict(status='complete'))
    assert c['complete'] and c['feasible'] and set(c['stages'])=={'axis','thermal'}


def test_fleet_two_seeds_and_cross_station_retry(cfg,tmp_path):
    from tests.workflows.test_workflow6_fleet import Relay,failure
    nodes=[Node('local',str(tmp_path/'local'),'cfg','python','repo'),Node('remote',str(tmp_path/'remote'),'cfg','python','repo','sshcfg','host')]
    f=FleetCampaign(cfg,tmp_path/'cfg','contract',dict(templates=cfg.paths.templates),nodes,'execution')
    f.transports={n.name:Relay() for n in nodes}
    try:
        a,s,e,q=f.choose('remote');j=f.dispatch('remote',a,s,e,q)
        b,s,e,q=f.choose('local');assert b['parameters']==cfg.search.seed_points[1]
        f.dispatch('local',b,s,e,q)
        f.apply_result(a,j,failure());f.state['pending_nodes'].pop('remote')
        assert f.state['fleet_retry'][0]['node']=='local' and not a['failed']
        with pytest.raises(ValueError,match='disabled'):f.dispatch('remote',a,'x',None)
        f.state['active_seconds']=48*3600
        fresh=f.new_candidate(f.controller.decode(f.controller.pool()[0]),'test')
        with pytest.raises(ValueError,match='deadline'):f.dispatch('remote',fresh,'axis',None)
        assert 'local' in f.state['pending_nodes']
    finally:f.store.last_tick=None;f.store.db.close()


def test_worker_rejects_transverse_before_any_session(cfg,tmp_path):
    from workflows.rfgun_wake_thermal.runtime import CSTWorker
    with pytest.raises(ValueError,match='disabled'):CSTWorker(cfg).run({'stage':'x'})


def test_fresh_preparation_is_paused_zero_cost_reference_only(cfg,tmp_path,monkeypatch):
    from workflows.rfgun_wake_thermal import heat_prepare as hp
    source=tmp_path/'old/state.json'
    atomic_json(source,dict(status='running',pending_nodes={'remote':'old_job'},active_seconds=1234.,candidates=[{'old':True}]))
    before=digest(source)
    monkeypatch.setattr(Config,'validate',lambda *a,**k:None)
    monkeypatch.setattr(hp,'initialize',lambda config:('fresh',dict(baseline=config.search.seed_points[0],templates=config.paths.templates)))
    monkeypatch.setattr(hp,'execution_identity',lambda config:{'mock':'offline'})
    nodes=[Node('local','local','cfg','python','repo'),Node('remote','remote','cfg','python','repo','sshcfg','host')]
    result=hp.prepare(cfg,tmp_path/'cfg',nodes,source)
    state=json.loads((Path(cfg.paths.output_dir)/'state.json').read_text())
    assert result['solver_starts']==0 and state['status']=='paused'
    assert state['active_seconds']==0 and state['jobs']==[] and not state['pending_nodes']
    assert len(state['candidates'])==2 and all(not c['stages'] and not c['metrics'] for c in state['candidates'])
    assert not state['historical_observations'] and digest(source)==before
    assert state['reference_history']['source_pending_nodes']=={'remote':'old_job'}
    assert (Path(cfg.paths.output_dir)/'STOP').exists()
    with pytest.raises(ValueError,match='empty'):hp.prepare(cfg,tmp_path/'cfg',nodes,source)
