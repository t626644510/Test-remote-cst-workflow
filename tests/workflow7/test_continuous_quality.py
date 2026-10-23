"""Regressions for measured CW watts, weak edges and empirical missing ranks."""
from dataclasses import replace
import copy
import numpy as np
import pytest
from workflows.rfgun_wakis.config import Config,Paths
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.observations import Observation,from_reconstruction
from workflows.rfgun_wakis.postprocess import power_observations
from workflows.rfgun_wakis.search import Proposer,Sample
from workflows.rfgun_wakis.peak_consensus import summarize
from test_quality_decision import evidence,paused_fixture


@pytest.fixture
def config(tmp_path):
    return Config(Paths(*(str(tmp_path/n) for n in ('source','light','bulk','python','wakis','cst'))))


def powers(value=5.98,variation=.0063,profile=.439):
    """Synthetic 500 kV CW watt evidence with an isolated 500 MHz pole."""
    return dict(windows={name:dict(pole=dict(frequency_hz=500e6,relative_residual=.0144),
                values=dict(heat_2=value*scale,leak_2=value*scale),
                ports={'port_2':[dict(power_w=value*scale*(1+i*.00045),
                    E_profile_error=profile,H_profile_error=profile) for i in range(3)]})
                for name,scale in [('early',1+variation),('late',1.01),('full',1.)]})


def test_tem_shape_never_changes_net_flux_observation(config):
    a=power_observations(powers(),config)['leak_2']
    b=power_observations(powers(profile=.99),config)['leak_2']
    assert a==b and a.qualified and a.estimate==5.98
    assert a.upper==pytest.approx(5.98*1.2) and a.below(75)


def test_crossing_twenty_percent_has_continuous_watt_envelope(config):
    a=power_observations(powers(343.836,variation=.1999),config)['heat_2']
    b=power_observations(powers(343.836,variation=.204076),config)['heat_2']
    assert a.qualified and b.qualified and b.relative_uncertainty==pytest.approx(.204076)
    assert b.upper-a.upper==pytest.approx(343.836*.004076)
    assert Proposer(config).training_reason(b) is None


def test_large_relative_milliwatt_variation_stays_small_in_watts(config):
    o=power_observations(powers(.000804765,variation=11.4339),config)['leak_2']
    assert o.qualified and o.lower==0 and o.upper<.011 and o.below(75)
    assert Proposer(config).training_reason(o) is None
    assert o.relative_uncertainty>11  # Uncertainty is retained, not clipped away.


@pytest.mark.parametrize('failure',['window','frequency','residual','negative_plane','nonpositive_full'])
def test_unresolved_physics_stays_unknown(config,failure):
    data=powers()
    if failure=='window':data['windows'].pop('early')
    elif failure=='frequency':data['windows']['full']['pole']['frequency_hz']=520e6
    elif failure=='residual':data['windows']['full']['pole']['relative_residual']=.3
    elif failure=='negative_plane':data['windows']['full']['ports']['port_2'][1]['power_w']=-1
    else:data['windows']['full']['values']['leak_2']=0
    o=power_observations(data,config).get('leak_2')
    assert o is None or (not o.qualified and o.upper is None and not o.below(75))


def edge_evidence(config,last=30000,main=690000):
    detail=evidence(small=[last]*6,main=main)
    for w in detail['diagnostics']['windows']:w['direct_peak']=0.
    detail['diagnostics']['base_resolution_hz']=10e6
    f=np.linspace(*config.physics.band_hz,100)
    arrays={}
    for i in range(6):
        arrays[f'fit_{i}_frequency_hz']=f
        arrays[f'fit_{i}_impedance']=np.column_stack([np.linspace(last*.5,last,len(f)),np.zeros(len(f))])
    return detail,arrays


def test_bounded_weak_edge_no_longer_invalidates_stronger_main_peak(config):
    detail,arrays=edge_evidence(config)
    result=summarize(detail,config.physics,config.reconstruction,'transverse_x',arrays)
    p=result['diagnostics']['reconstructed_peak'];o=from_reconstruction(result)
    assert p['band_edge_rising'] and not o.band_edge_unresolved
    assert o.estimate==690000 and o.upper==pytest.approx(690000*1.02)
    assert o.qualified and o.acceptance(150000)=='exceeds'
    point=Geometry(config).sample(np.random.default_rng(7),1)[0]
    noise=Proposer(config).training([Sample(point,{'transverse_x':o})],'transverse_x')[2][0]
    assert noise<.1


@pytest.mark.parametrize('failure',['dominant','missing_curve','unsupported'])
def test_dominant_or_unmeasured_edge_still_blocks(config,failure):
    detail,arrays=edge_evidence(config,last=700000 if failure=='dominant' else 30000)
    if failure=='missing_curve':arrays.pop('fit_0_impedance')
    if failure=='unsupported':detail['diagnostics']['windows'][-1]['boundary_tail_peaks']=[1e9]*3+[0]*3
    o=from_reconstruction(summarize(detail,config.physics,config.reconstruction,'transverse_x',arrays))
    assert o.upper is None and not o.qualified


def test_historical_median_prior_is_not_a_synthetic_training_point(config):
    points=Geometry(config).sample(np.random.default_rng(2),6)
    def obs(v):return Observation(v,.05,v*.95,v*1.05,True)
    history=[Sample(p,{'transverse_x':obs(v)},True) for p,v in zip(points,[500000,700000,900000])]
    native=[]
    for p in points[3:5]:native.append(Sample(p,dict(longitudinal=obs(1000),heat_1=obs(200),heat_2=obs(200))))
    native[1].observations['transverse_x']=obs(400000)
    samples=history+native;before=copy.deepcopy(samples);proposer=Proposer(config)
    prior=proposer.ranking_priors(samples)
    assert prior['transverse_x']==pytest.approx(700000) and prior['heat_1']==pytest.approx(200)
    assert proposer.ranked_centers(samples)[0][0] is native[1]
    assert len(proposer.training(samples,'transverse_x')[1])==4 and samples==before
    # A repeated geometry does not weight the empirical median twice.
    assert proposer.ranking_priors(samples+[history[0]])==prior


def test_sequential_revision_reassesses_saved_power_and_replays(config,tmp_path,monkeypatch):
    from workflows.rfgun_wakis.io import read_json,atomic_json,digest,manifest
    from workflows.rfgun_wakis.quality_revision import prepare,adopt
    from workflows.rfgun_wakis.campaign import Campaign
    path,campaign,rp=paused_fixture(config,tmp_path)
    result=read_json(rp);analysis=__import__('pathlib').Path(result['field_directory'])/'analysis_00'
    old=Observation(5.98,1,0,None,False).as_dict()
    result['observations']['leak_2']=old
    atomic_json(rp,result);atomic_json(analysis/'result.json',result)
    atomic_json(analysis/'power_analysis.json',powers())
    atomic_json(analysis/'manifest.json',manifest(analysis,[p for p in analysis.iterdir() if p.name!='manifest.json']))
    campaign.store.data['results'][0]['result_sha256']=digest(rp)
    campaign.store.data['candidates'][0]['observations']['leak_2']=old;campaign.store.save()
    raw=rp.read_bytes()
    monkeypatch.setattr(Campaign,'execute_stage',lambda *a:pytest.fail('No new solve'))
    first=prepare(path,tmp_path/'first');adopt(path,first)
    second=prepare(path,tmp_path/'second');adopt(path,second);adopt(path,second)
    final=Campaign(path);final.apply_results()
    o=Observation(**final.store.data['candidates'][0]['observations']['leak_2'])
    assert o.qualified and o.estimate==5.98 and o.upper==pytest.approx(5.98*1.2)
    assert rp.read_bytes()==raw and final.store.data['active_seconds']==1234 and final.store.data['status']=='paused'
    assert read_json(second)['previous_revision']['path']==str(first)
    # Replaying must detect tampering of the original power evidence.
    atomic_json(analysis/'power_analysis.json',powers(value=1))
    with pytest.raises(ValueError,match='power source'):final.apply_results()
