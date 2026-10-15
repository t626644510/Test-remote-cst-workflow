"""Uncertainty, evidence quarantine and adaptive radius require meaningful data."""
from dataclasses import replace
import numpy as np
import pytest
from workflows.rfgun_wakis.config import Config,Paths
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.observations import Observation
from workflows.rfgun_wakis.search import Proposer,Sample
from workflows.rfgun_wakis.trust import reference,update_trust

@pytest.fixture
def config(tmp_path):
    return Config(Paths(*(str(tmp_path/n) for n in ('source','light','bulk','python','wakis','cst'))))

def obs(value,relative=.05):
    return Observation(value,relative,lower=value*(1-relative),upper=value*(1+relative),qualified=True)

def axis(l=1000,h=200):
    return dict(longitudinal=obs(l),heat_1=obs(h),heat_2=obs(h))

def test_gigantic_unbounded_peak_and_contradiction_do_not_steer_gp(config):
    points=Geometry(config).sample(np.random.default_rng(9),4)
    observations=[obs(1500),Observation(16.45e9,1.259,lower=10027.5),
                  Observation(800,1,lower=600),Observation(1400,.2,lower=1200,upper=1600,contradictory=True)]
    samples=[Sample(p,{'longitudinal':o}) for p,o in zip(points,observations)]
    before=[s.observations.copy() for s in samples]
    _,y,noise=Proposer(config).training(samples,'longitudinal')
    assert np.expm1(y)==pytest.approx([1500,800])
    assert noise[1]>=np.log(3)
    assert [s.observations for s in samples]==before
    assert Proposer(config).training_reason(observations[1])=='unbounded_scale_unidentified'

def test_noise_floor_protects_tiny_power_and_unqualified_bounded_points(config):
    points=Geometry(config).sample(np.random.default_rng(1),2)
    samples=[Sample(points[0],{'leak_2':obs(.0001)}),
             Sample(points[1],{'leak_2':Observation(40,.001,lower=39,upper=41)})]
    _,_,n=Proposer(config).training(samples,'leak_2')
    assert n[0]>1 and n[1]>=config.search.uncertain_log_noise
    assert Proposer(config).training_reason(Observation(.0001,1,lower=0))=='unbounded_scale_unidentified'

def test_partial_axis_can_seed_local_search_and_proposals_are_reproducible(config):
    config=replace(config,search=replace(config.search,pool=64,initial_points=1))
    points=Geometry(config).sample(np.random.default_rng(17),8)
    samples=[Sample(p,axis(1000+50*i,200+10*i)) for i,p in enumerate(points)]
    a,audit=Proposer(config).choose(samples,sequence=30,radius=.2,explore=False)
    b,_=Proposer(config).choose(samples,sequence=30,radius=.2,explore=False)
    assert a==b and audit['center_parameters'] in points
    assert audit['method']=='robust_partial_GP_confidence_utility'
    assert audit['training']['transverse_x']['independent_points']==0
    assert all(s.observations.keys()==axis().keys() for s in samples)
    if not audit['local_proposal']:assert audit['trust_reference'] is None

def candidate(i,values,ref,generation=0):
    return dict(id=str(i),axis_directory='axis',observations={k:v.as_dict() for k,v in values.items()},
        proposal=dict(trust_reference=reference(ref),trust_generation=generation))

def test_radius_uses_disjoint_intervals_and_replay_once(config):
    state={'radius':.25};ref=axis(h=300)
    for i in range(2):
        c=candidate(i,axis(h=100),ref);update_trust(state,c,config);update_trust(state,c,config)
    assert state['radius']==pytest.approx(.375) and len(state['trust']['events'])==2
    update_trust(state,candidate(3,axis(h=900),ref),config)
    assert state['trust']['events'][-1]['decision']=='stale_radius_generation'
    for i in range(4,7):update_trust(state,candidate(i,axis(h=900),ref,1),config)
    assert state['radius']==pytest.approx(.2625)

def test_overlap_unknown_and_failed_results_do_not_shrink(config):
    state={'radius':.25};ref=axis()
    update_trust(state,candidate(0,axis(),ref),config)
    bad=axis();bad['longitudinal']=Observation(16000,1,lower=100)
    update_trust(state,candidate(1,bad,ref),config)
    failed=candidate(2,{},ref);failed.pop('axis_directory');update_trust(state,failed,config)
    assert state['radius']==.25
    assert state['trust']['failures']==state['trust']['successes']==0
    assert [e['decision'] for e in state['trust']['events']]==['overlapping_envelopes','incomparable_bounds']

@pytest.mark.parametrize('start,heat,expected',[(.49,100,.5),(.051,900,.05)])
def test_radius_is_clamped(config,start,heat,expected):
    state={'radius':start}
    for i in range(3):update_trust(state,candidate(i,axis(h=heat),axis(h=300)),config)
    assert state['radius']==pytest.approx(expected)
