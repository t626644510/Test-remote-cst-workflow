"""Common-band GP-only historical observations; no CST or invented feasibility."""
from dataclasses import replace
import copy,json
import numpy as np
import pytest
from workflows.rfgun_wake_thermal.config import Config,Paths,NAMES
from workflows.rfgun_wake_thermal.search import Controller

pytestmark=pytest.mark.no_cst

@pytest.fixture
def setup(tmp_path):
    cfg=Config(Paths({s:str(tmp_path/'source'/(s+'.cst')) for s in ('axis','x','y','thermal')},str(tmp_path/'state'),str(tmp_path/'bulk')))
    cfg=replace(cfg,search=replace(cfg.search,observation_mode='finite_tail_screening',gp_min_samples=2))
    point={n:sum(cfg.bounds[n])/2 for n in NAMES}
    st=dict(candidates=[],rng=None,radius=.25,improving=0,not_improving=0)
    return cfg,point,st

def history(cfg,p,**metrics):
    return dict(parameters=dict(p),metrics=metrics,source_kind='common_band_history',evidence_verified=True,
                band_hz=list(cfg.physics.band_hz),wake_length_m=cfg.physics.wake_length_m,source_sigma_m=.05)

def native(p,**metrics):
    return dict(parameters=dict(p),metrics={k:v for k,v in metrics.items() if k.startswith('power')},
        details={k:dict(diagnostics=dict(direct_peak=v)) for k,v in metrics.items() if not k.startswith('power')})

def test_native_replaces_history_per_metric_without_losing_partial_observations(setup):
    cfg,p,s=setup;s['historical_observations']=[history(cfg,p,longitudinal=900,transverse=120000,power5=300)]
    s['candidates']=[native(p,longitudinal=1000,power5=310)]
    c=Controller(cfg,s)
    assert [(v,h) for _,v,_,h in c.training_rows('longitudinal')]==[(1000,False)]
    assert [(v,h) for _,v,_,h in c.training_rows('transverse')]==[(120000,True)]
    assert c.training_rows('power5')[0][1:]==(310,cfg.search.native_relative_noise,False)
    s['candidates'][0]['details']['transverse']=dict(diagnostics=dict(direct_peak=130000))
    assert c.training_rows('transverse')[0][1:]==(130000,cfg.search.native_relative_noise,False)

def test_history_only_training_does_not_create_native_incumbents_or_coverage(setup):
    cfg,p,s=setup;s['historical_observations']=[history(cfg,p,longitudinal=900,transverse=100000,power5=100,power6=110),history(cfg,dict(p,selfangle1=120),longitudinal=1100)]
    before=copy.deepcopy(s);c=Controller(cfg,s);c.fit()
    assert 'longitudinal' in c.models and c.candidates==[]
    assert s==before and len(c.training_rows('power5'))==1
    assert c.training_rows('power5')[0][2]==cfg.search.native_relative_noise
    restored=Controller(cfg,json.loads(json.dumps(s)))
    assert len(restored.training_rows('longitudinal'))==2

@pytest.mark.parametrize('change',[{'band_hz':[550e6,3e9]},{'wake_length_m':50},{'evidence_verified':False},{'source_kind':'unverified'}])
def test_wrong_contract_history_rejected(setup,change):
    cfg,p,s=setup;h=history(cfg,p,longitudinal=900);h.update(change);s['historical_observations']=[h]
    assert Controller(cfg,s).training_rows('longitudinal')==[]

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1])
def test_invalid_historical_values_cannot_train(setup,value):
    cfg,p,s=setup;s['historical_observations']=[history(cfg,p,longitudinal=value)]
    assert Controller(cfg,s).training_rows('longitudinal')==[]

def test_qualified_mode_and_outside_geometry_exclude_history(setup):
    cfg,p,s=setup;s['historical_observations']=[history(cfg,p,longitudinal=900)]
    q=replace(cfg,search=replace(cfg.search,observation_mode='qualified'))
    assert Controller(q,s).training_rows('longitudinal')==[]
    s['historical_observations'][0]['parameters']['projection1']=26
    assert Controller(cfg,s).training_rows('longitudinal')==[]

def test_alpha_respects_log_transform_and_sklearn_y_normalization(setup):
    cfg,p,s=setup;s['historical_observations']=[history(cfg,p,longitudinal=1000)]
    s['candidates']=[native(dict(p,selfangle1=120),longitudinal=1100)]
    c=Controller(cfg,s);c.fit();model=c.models['longitudinal']
    ratio=np.array([.5,.55]);y=np.log1p(ratio)
    expected=((np.log1p(ratio*(1+np.array([.2,.02])))-y)/np.std(y))**2
    assert model.alpha==pytest.approx(expected)
    assert model.alpha[0]>model.alpha[1]*50

def test_duplicate_historical_coordinates_do_not_fake_sample_count(setup):
    cfg,p,s=setup;s['historical_observations']=[history(cfg,p,longitudinal=1000)]*8
    c=Controller(cfg,s);c.fit();assert 'longitudinal' not in c.models

def test_history_persists_and_database_mirror_is_idempotent_without_budget_charge(setup):
    from workflows.rfgun_wake_thermal.storage import Store
    cfg,p,_=setup;store=Store(cfg,'test-history')
    row=history(cfg,p,longitudinal=1000);row['id']='old_point'
    store.state['historical_observations']=[row];store.save();store.mirror();store.mirror()
    records=store.db.get_all_records()
    assert len(records)==1
    assert records[0]['source']=='wf6.historical_screening_only'
    assert store.state['active_seconds']==0 and store.state['jobs']==[]
    assert store.checkpoint.rng_state['historical_observations'][0][0]=='old_point'
    store.close();restored=Store(cfg,'test-history')
    assert restored.state['historical_observations']==[row]
    assert len(restored.db.get_all_records())==1
    restored.close()

@pytest.mark.parametrize('noise',[.01,1.,float('nan')])
def test_noise_configuration_validated(setup,noise):
    cfg,_,_=setup
    with pytest.raises(ValueError):replace(cfg,search=replace(cfg.search,history_relative_noise=noise)).validate()
