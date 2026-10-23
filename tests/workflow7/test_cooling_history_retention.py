"""No-CST validation of narrowed acquisition, history and exact retirement."""
from dataclasses import replace
import numpy as np
import pytest
from workflows.rfgun_wakis.config import Config,Paths,BOUNDS
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.search import Proposer,Sample
from workflows.rfgun_wakis.observations import Observation
from workflows.rfgun_wakis.io import atomic_json,manifest,read_json,validate_manifest,digest
from workflows.rfgun_wakis.retention import retire_manifest_files,validate_retained_manifest,retained_candidates,RAW_NAMES,safe_file
from workflows.rfgun_wakis.history import validate_seed,load_samples,compatibility

@pytest.fixture
def cfg(tmp_path):
    c=Config(Paths(*(str(tmp_path/n) for n in ('source','light','bulk','python','wakis','cst'))))
    return replace(c,bounds=dict(BOUNDS,DownHeight=(160.,180.),coaxr2=(10.44,21.99)),cooling_clearance_mm=5.)

def value(x):return Observation(x,.02,lower=x*.98,upper=x*1.02,qualified=True)

def test_cooling_strict_radius_and_all_proposals(cfg):
    cfg.validate();g=Geometry(cfg);points=g.sample(np.random.default_rng(4),200)
    assert all(160<=p['DownHeight']<=180 and p['coaxr2']>10.43 and p['coaxr2']>=p['PortR1']+2 for p in points)
    p=dict(points[0],coaxr2=10.43)
    assert g.violations(p)
    with pytest.raises(ValueError):replace(cfg,bounds=dict(cfg.bounds,DownHeight=(160,181))).validate()

def test_history_outside_acquisition_invariant_coordinates_and_current_wins(cfg):
    g=Geometry(cfg);current=g.sample(np.random.default_rng(2),1)[0];old=dict(current,DownHeight=77.,coaxr2=max(current['PortR1']+2,10.))
    p=Proposer(cfg)
    x,y,n=p.training([Sample(old,{'longitudinal':value(1200)},True)],'longitudinal')
    assert len(y)==1 and x[0,4]==pytest.approx((77.-50)/130)
    assert n[0]>=np.log1p(1200*1.2)-np.log1p(1200)
    assert len(p.training([Sample(old,{'longitudinal':value(1200)})],'longitudinal')[1])==0
    history=Sample(current,{'longitudinal':value(1000),'leak_2':value(10)},True)
    native=Sample(current,{'longitudinal':value(1500)})
    for samples in ([history,native],[native,history]):
        assert np.expm1(p.training(samples,'longitudinal')[1])==pytest.approx([1500])
        assert np.expm1(p.training(samples,'leak_2')[1])==pytest.approx([10])
    bad=Sample(current,{'longitudinal':Observation(1500,1,lower=10)})
    assert len(p.training([history,bad],'longitudinal')[1])==0

def test_history_does_not_become_center_or_trust_reference(cfg):
    cfg=replace(cfg,search=replace(cfg.search,pool=64,initial_points=1))
    points=Geometry(cfg).sample(np.random.default_rng(6),8);seed=points[0]
    samples=[Sample(dict(p,DownHeight=70.),{'longitudinal':value(1100+i*20)},True) for i,p in enumerate(points)]
    proposal,audit=Proposer(cfg).choose(samples,sequence=6,radius=.2,explore=False,preferred_center=seed)
    assert not Geometry(cfg).violations(proposal)
    assert audit['center_parameters']==seed and audit['trust_reference'] is None
    assert audit['training']['longitudinal']['independent_points']==8

def test_retirement_replay_and_strict_recovery(tmp_path):
    for n in ('Ez_lines.h5','wake.npz','field_complete.json'):(tmp_path/n).write_bytes(n.encode())
    entries=manifest(tmp_path,[tmp_path/n for n in ('Ez_lines.h5','wake.npz','field_complete.json')]);atomic_json(tmp_path/'raw_manifest.json',entries)
    before=digest(tmp_path/'raw_manifest.json')
    dry=retire_manifest_files(tmp_path,'raw_manifest.json',RAW_NAMES,execute=False)
    assert dry['bytes'] and (tmp_path/'Ez_lines.h5').exists()
    retire_manifest_files(tmp_path,'raw_manifest.json',RAW_NAMES,execute=True)
    assert validate_retained_manifest(tmp_path,entries)==['Ez_lines.h5']
    assert digest(tmp_path/'raw_manifest.json')==before
    assert retire_manifest_files(tmp_path,'raw_manifest.json',RAW_NAMES,execute=True)['bytes']==0
    with pytest.raises(ValueError):validate_manifest(tmp_path,entries)
    (tmp_path/'wake.npz').write_bytes(b'corrupt')
    with pytest.raises(ValueError):validate_retained_manifest(tmp_path,entries)

def test_retirement_protects_pending_pins_and_forbids_escape(cfg,tmp_path):
    state=dict(candidates=[dict(id='candidate_0000',status='axis_only',observations={}),dict(id='candidate_0001',status='x_pending',observations={}),dict(id='candidate_0002',status='completed',observations={})],pending={'candidate_index':2})
    assert retained_candidates(cfg,state)=={'candidate_0000','candidate_0001','candidate_0002'}
    with pytest.raises(ValueError):safe_file(tmp_path,'../foreign')

def test_seed_changed_geometry_never_imports_old_values(cfg,tmp_path):
    p=Geometry(cfg).sample(np.random.default_rng(2),1)[0];old=dict(p,DownHeight=157.)
    path=tmp_path/'parent.json';atomic_json(path,dict(candidates=[dict(id='candidate_0038',parameters=old,observations={'longitudinal':value(4500).as_dict()})]))
    record=dict(parent_state=str(path),parent_state_sha256=digest(path),candidate_id='candidate_0038',changes={'DownHeight':160.})
    validate_seed(record,dict(old,DownHeight=160.),cfg)
    with pytest.raises(ValueError):validate_seed(record,dict(old,DownHeight=161.),cfg)

def test_existing_default_contract_digest_stays_compatible(tmp_path):
    import json,hashlib
    c=Config(Paths(*(str(tmp_path/n) for n in ('source','light','bulk','python','wakis','cst'))))
    d=c.as_dict()
    assert 'cooling_clearance_mm' not in d and 'compact_retention' not in d
    assert c.digest()==hashlib.sha256(json.dumps(d,sort_keys=True,allow_nan=False).encode()).hexdigest()

def test_permanent_numeric_wake_cannot_be_retired_even_by_bad_call(tmp_path):
    (tmp_path/'wake.npz').write_bytes(b'permanent numeric wake')
    atomic_json(tmp_path/'raw_manifest.json',manifest(tmp_path,[tmp_path/'wake.npz']))
    with pytest.raises(ValueError):retire_manifest_files(tmp_path,'raw_manifest.json',{'wake.npz'},execute=True)
    assert (tmp_path/'wake.npz').exists() and not (tmp_path/'retention.json').exists()

def test_full_compaction_preserves_project_fit_and_pending(cfg,tmp_path):
    from workflows.rfgun_wakis.retention import compact_campaign
    cfg=replace(cfg,retained_best_count=1)
    bulk=tmp_path/'bulk';candidates=[];results=[]
    for i in range(3):
        cid=f'candidate_{i:04}';folder=bulk/cid;field=folder/'axis_00';field.mkdir(parents=True)
        for n in ('Ez_lines.h5','wake.npz','field_complete.json'):(field/n).write_bytes(n.encode())
        atomic_json(field/'raw_manifest.json',manifest(field,[field/n for n in ('Ez_lines.h5','wake.npz','field_complete.json')]))
        params={'DownHeight':170.};observations={k:value(1000+i*100).as_dict() for k in ('longitudinal','leak_2','leak_3')}
        result=dict(candidate_index=i,stage='axis',parameters=params,observations=observations,raw_sha256=digest(field/'wake.npz'),field_directory=str(field))
        analysis=field/'analysis_00';atomic_json(analysis/'result.json',result);atomic_json(analysis/'manifest.json',manifest(analysis,[analysis/'result.json']))
        saved=tmp_path/'light'/f'result{i}.json';atomic_json(saved,result);results.append(dict(result_path=str(saved),result_sha256=digest(saved)))
        prep=folder/'preparation_00'/'prepared';prep.mkdir(parents=True);(prep/'effective_metrics.npz').write_bytes(b'grid')
        (prep/'preparation.json').write_text('{}');atomic_json(prep/'manifest.json',manifest(prep,[prep/'effective_metrics.npz',prep/'preparation.json']))
        project=folder/'preparation_00'/'cst'/'project'/'test.cst';project.parent.mkdir(parents=True);project.write_bytes(b'editable')
        matrix=project.with_suffix('')/'Result';matrix.mkdir(parents=True);(matrix/'MCalc.fmp').write_bytes(b'matrix')
        candidates.append(dict(id=cid,status='axis_only' if i<2 else 'x_pending',parameters=params,observations=observations,axis_directory=str(field),prepared=str(prep),cst={'project':str(project)}))
    state=dict(candidates=candidates,results=results)
    answer=compact_campaign(cfg,state)
    retired=bulk/'candidate_0001'
    assert answer['reclaimed_bytes']>0
    assert not (retired/'axis_00/Ez_lines.h5').exists()
    assert (retired/'axis_00/wake.npz').exists()
    assert (retired/'preparation_00/cst/project/test.cst').exists()
    assert not (retired/'preparation_00/cst/project/test/Result/MCalc.fmp').exists()
    assert (bulk/'candidate_0002/axis_00/Ez_lines.h5').exists()
    assert compact_campaign(cfg,state)['reclaimed_bytes']==0
