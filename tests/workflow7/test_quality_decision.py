"""Scientific quality, engineering acceptance, GP influence and immutable replay."""
from dataclasses import replace
import copy
from pathlib import Path

import numpy as np
import pytest

from workflows.rfgun_wakis.config import Config,Paths
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.io import atomic_json,digest,manifest,read_json
from workflows.rfgun_wakis.observations import Observation,from_reconstruction
from workflows.rfgun_wakis.peak_consensus import summarize
from workflows.rfgun_wakis.search import Proposer,Sample


@pytest.fixture
def config(tmp_path):
    return Config(Paths(*(str(tmp_path/n) for n in ('template.cst','light','bulk','python','wakis','cst'))))


def evidence(small=(744.56,734.04,1053.31,817.07,834.16,794.27),main=1217.05):
    fits=[dict(start_m=start,rank=rank,peak=main,valid=True,error=.005,holdout_error=.007,
               correlation=.999,optimizer_success=True,holdout_success=True)
          for start in (1.,3.) for rank in (24,32,48)]
    windows=[dict(band_hz=[550e6,1e9],fit_indices=list(range(6)),peaks=[main]*6,
                  boundary_tail_peaks=[0.]*6,direct_peak=main*.9),
             dict(band_hz=[1e9,1462734895.6992505],fit_indices=list(range(6)),peaks=list(small),
                  boundary_tail_peaks=[0.]*6,direct_peak=900.)]
    return dict(reasons=[],diagnostics=dict(fits=fits,windows=windows))


def assess(config,detail=None,threshold=1800):
    return summarize(detail or evidence(),config.physics,config.reconstruction,'longitudinal',threshold=threshold)


def test_0157_subpeak_retains_quality_but_passes_and_normal_gp_noise(config):
    summary=assess(config);o=from_reconstruction(summary)
    assert o.quality=='bounded_sensitive' and not o.qualified
    assert o.non_dominant_sensitive and o.sensitive_upper<o.consensus_main_lower
    assert o.acceptance(1800)=='envelope_pass' and o.below(1500)
    p=Geometry(config).sample(np.random.default_rng(1),1)[0]
    proposer=Proposer(config)
    _,y,noise=proposer.training([Sample(p,{'longitudinal':o})],'longitudinal')
    assert np.expm1(y[0])==pytest.approx(1217.05)
    assert noise[0]==pytest.approx(np.log1p(1217.05+90)-np.log1p(1217.05))
    historical=Sample(p,{'longitudinal':o},historical=True)
    assert proposer.training([historical],'longitudinal')[2][0]>=np.log1p(1217.05*1.2)-np.log1p(1217.05)
    assert Observation(**o.as_dict())==o


def test_quality_is_independent_of_threshold_crossing(config):
    detail=evidence(small=[400]*6,main=1700)
    a=from_reconstruction(assess(config,detail,1710));b=from_reconstruction(assess(config,detail,1800))
    assert a.quality==b.quality=='consensus' and a.qualified and b.qualified
    assert a.estimate==b.estimate and a.upper==b.upper
    assert a.acceptance(1710)=='unresolved' and a.acceptance(1800)=='consensus_pass'
    assert a.acceptance(1600)=='exceeds'


def test_disagreeing_majority_groups_use_whole_valid_union(config):
    detail=evidence(small=[218.61,222.09,226.72,234.08,237.75,251.23])
    summary=assess(config,detail);window=summary['diagnostics']['local_consensus_windows'][-1]
    assert window['incompatible_majorities'] and window['quality']=='bounded_sensitive'
    assert set(window['fit_indices'])==set(range(6))
    assert window['estimate']==pytest.approx(np.median(detail['diagnostics']['windows'][-1]['peaks']))
    assert window['upper']>=251.23


def test_invalid_fits_cannot_establish_finite_envelope(config):
    detail=evidence()
    for f in detail['diagnostics']['fits'][3:]:f['holdout_success']=False
    o=from_reconstruction(assess(config,detail))
    assert o.quality=='unsupported' and o.upper is None and not o.non_dominant_sensitive
    assert not o.below(1800)


def test_failed_quality_keeps_noisy_trend_only_when_scale_identified(config):
    detail=evidence(small=[300]*6,main=500000)
    for f in detail['diagnostics']['fits']:
        f.update(valid=False,error=.15,holdout_error=.28)
    o=from_reconstruction(assess(config,detail,150000))
    assert o.upper is None and o.lower==0 and o.search_scale_lower==pytest.approx(360000)
    assert not o.below(1800000) and not o.gp_quality_penalty_exempt
    assert Proposer(config).training_reason(o) is None
    p=Geometry(config).sample(np.random.default_rng(5),1)[0]
    _,y,noise=Proposer(config).training([Sample(p,{'longitudinal':o})],'longitudinal')
    assert np.expm1(y[0])==pytest.approx(500000) and noise[0]>=np.log(3)
    assert Proposer(config).training_reason(replace(o,search_scale_lower=10000))=='unbounded_scale_unidentified'


def test_bounded_dominant_peak_has_margin_but_no_gp_exemption(config):
    o=from_reconstruction(assess(config,evidence(small=[500,600,700,800,900,1000],main=100)))
    assert o.quality=='bounded_sensitive' and o.acceptance(1800)=='envelope_pass'
    assert not o.non_dominant_sensitive
    assert not o.below(o.sensitive_upper/.9-1)
    p=Geometry(config).sample(np.random.default_rng(2),1)[0]
    assert Proposer(config).training([Sample(p,{'longitudinal':o})],'longitudinal')[2][0]>=np.log(1.5)


@pytest.mark.parametrize('problem',['edge','contradiction','gap','boundary'])
def test_unsafe_evidence_never_earns_acceptance_or_gp_exemption(config,problem):
    detail=evidence()
    if problem=='edge':detail['reasons']=['band_edge_peak']
    elif problem=='contradiction':detail['diagnostics']['windows'][-1]['direct_peak']=1900
    elif problem=='gap':detail['diagnostics']['windows'][-1]['band_hz'][0]+=100
    else:detail['diagnostics']['windows'][-1]['boundary_tail_peaks']=[10000]*3+[0]*3
    o=from_reconstruction(assess(config,detail))
    assert o is None or (not o.below(1800) and not o.non_dominant_sensitive)


def test_legacy_uncertain_record_stays_conservative_and_forged_exemption_rejected():
    o=Observation(1200,.02,lower=1176,upper=1224)
    assert not o.below(1800) and not o.gp_quality_penalty_exempt
    with pytest.raises(ValueError,match='exemption'):replace(o,non_dominant_sensitive=True)


def paused_fixture(config,tmp_path):
    from workflows.rfgun_wakis.campaign import Campaign,code_manifest
    path=tmp_path/'config.json';atomic_json(path,config.as_dict())
    Path(config.paths.template).write_bytes(b'unchanged template')
    campaign=Campaign(path);root=campaign.root;bulk=campaign.bulk
    p=Geometry(config).sample(np.random.default_rng(1),1)[0]
    old=Observation(1217.05,.02,lower=1192.709,upper=1241.391).as_dict()
    c=dict(id='candidate_0000',parameters=p,observations={'longitudinal':old},status='axis_only',
           requested_stages=['axis'],forced_transverse=False,axis_directory=str(bulk/'candidate_0000/axis_00'))
    field=Path(c['axis_directory']);analysis=field/'analysis_00';analysis.mkdir(parents=True)
    (field/'wake.npz').write_bytes(b'original signed wake')
    result=dict(stage='axis',parameters=p,observations=c['observations'],field_directory=str(field),
                raw_sha256=digest(field/'wake.npz'),candidate_index=0,status='completed',job_key='candidate_0000_axis')
    atomic_json(analysis/'result.json',result);atomic_json(analysis/'reconstruction.json',evidence())
    arrays={}
    for i in range(6):
        arrays[f'fit_{i}_frequency_hz']=np.array([550e6,1e9,1462734895.6992505])
        arrays[f'fit_{i}_impedance']=np.array([[100.],[90.],[80.]])
    np.savez(analysis/'reconstruction.npz',**arrays)
    atomic_json(analysis/'manifest.json',manifest(analysis,[p for p in analysis.iterdir() if p.is_file()]))
    rp=root/'jobs/candidate_0000_axis/stage_result.json';atomic_json(rp,result)
    item=dict(key='candidate_0000_axis',result_path=str(rp),result_sha256=digest(rp))
    campaign.store.data.update(status='paused',candidates=[c],results=[item],completed_stage_keys=[item['key']],
        active_seconds=1234.,trust=dict(generation=0,successes=0,failures=0,processed=['candidate_0000'],events=[]))
    campaign.store.save();(root/'STOP').write_text('user pause')
    atomic_json(root/'provenance.json',dict(template_sha256=digest(config.paths.template),config_digest=config.digest(),code=code_manifest()))
    return path,campaign,rp


def test_revision_survives_replay_without_resolve_or_budget_change(config,tmp_path,monkeypatch):
    from workflows.rfgun_wakis.campaign import Campaign
    from workflows.rfgun_wakis.quality_revision import prepare,adopt,load_revision
    path,campaign,original=paused_fixture(config,tmp_path)
    monkeypatch.setattr(Campaign,'execute_stage',lambda *a:pytest.fail('No solver authorized'))
    original_bytes=original.read_bytes();before=(campaign.root/'state.json').read_bytes()
    index=prepare(path,tmp_path/'revision')
    assert (campaign.root/'state.json').read_bytes()==before
    receipt=adopt(path,index)
    assert receipt['active_seconds']==1234. and receipt['paused']
    resumed=Campaign(path);resumed.apply_results();resumed.apply_results()
    o=Observation(**resumed.store.data['candidates'][0]['observations']['longitudinal'])
    assert o.non_dominant_sensitive and o.below(1800)
    assert original.read_bytes()==original_bytes and (campaign.root/'STOP').exists()
    assert resumed.store.data['status']=='paused' and resumed.store.data['active_seconds']==1234.
    atomic_json(campaign.root/'config.snapshot.json',config.as_dict())
    from workflows.rfgun_wakis.history import build_bundle
    transferred=build_bundle(campaign.root,config)
    assert transferred['candidates'][0]['observations']['longitudinal']==o.as_dict()
    assert 'observation_revision' in transferred['evidence'][0]
    adopt(path,index)  # Same prepared revision may complete/replay without double work.
    changed=read_json(index);changed['stages']['candidate_0000_axis']['metric']='transverse_x';atomic_json(index,changed)
    with pytest.raises(ValueError,match='revision changed'):load_revision(resumed.store.data)


def test_revision_refuses_running_campaign(config,tmp_path):
    from workflows.rfgun_wakis.quality_revision import prepare
    path,campaign,_=paused_fixture(config,tmp_path)
    campaign.store.data['status']='running';campaign.store.save()
    with pytest.raises(RuntimeError,match='paused'):prepare(path,tmp_path/'forbidden')
