"""No-CST regression of WF7 contracts and failure boundaries."""
import numpy as np
import pytest
from workflows.rfgun_wakis.config import Config, Paths, NAMES
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.observations import Observation, from_reconstruction, feasibility, transverse_admission
from workflows.rfgun_wakis.search import Sample, Proposer, comparable_improvement
from workflows.rfgun_wakis.state import RoundStore
from workflows.rfgun_wakis.io import atomic_json, validate_manifest

@pytest.fixture
def config(tmp_path):
    return Config(Paths(str(tmp_path/'template.cst'),str(tmp_path/'light'),str(tmp_path/'bulk'),
                        str(tmp_path/'python.exe'),str(tmp_path/'wakis'),str(tmp_path/'cst')))

def test_fifteen_dimensions_and_derived_wall(config):
    g=Geometry(config);points=g.sample(np.random.default_rng(4),500)
    assert len(NAMES)==15 and 'DownHeight2' not in NAMES
    for p in points:
        expanded=g.expand(p)
        assert expanded['UpperHeight1']==expanded['UpperHeight2']==170
        assert expanded['PortR2']-expanded['PortR1']==pytest.approx(2)
        assert 5.43<p['coaxr2']<22 and p['coaxr2']>=expanded['PortR2']
        assert expanded['DownHeight2']==-30 and 50<p['DownHeight']<180
        assert 2<p['SPortR2']<p['SPortR1']<p['PortR1']<22
        assert expanded['inner_angle']<0<expanded['inner_angle3']
        assert g.from_template(expanded)==pytest.approx(p)

def test_local_sampling_has_no_clipped_boundary_mass(config):
    g=Geometry(config);center=g.sample(np.random.default_rng(5),1)[0]
    points=np.array([g.normalize(p) for p in g.sample(np.random.default_rng(6),500,center,.15)])
    assert np.all(points>0) and np.all(points<1)
    assert np.all(abs(points-g.normalize(center))<=.15)

def test_direct_FT_cannot_enter_search(config):
    assert from_reconstruction({'value':1.,'diagnostics':{'direct_peak':1.}}) is None
    bad={'estimate':3.,'full_band_coverage':False,'relative_uncertainty':.1}
    assert from_reconstruction({'diagnostics':{'reconstructed_peak':bad}}) is None
    p=Geometry(config).sample(np.random.default_rng(1),1)[0]
    reference=Sample(p,{'longitudinal':Observation(1,.2,source='reference')})
    assert len(Proposer(config).training([reference],'longitudinal')[1])==0

def test_uncertainty_is_not_zero_or_false_feasibility(config):
    o=Observation(1500,1.,lower=100,upper=None)
    assert not o.below(1800)
    assert o.ranking_value==3000
    assert not transverse_admission(o,config,forced=False)
    assert transverse_admission(o,config,forced=True)
    assert not comparable_improvement(o,Observation(1000,.25,upper=1250))
    assert not feasibility({'longitudinal':o},config)['qualified_X_screening']

def test_broad_gate_and_strict_leakage(config):
    l=Observation(2500,.1,lower=2250,upper=2750)
    assert transverse_admission(l,config,forced=False)
    obs={k:Observation(v,.2,lower=.8*v,upper=1.2*v,qualified=True)
         for k,v in [('longitudinal',1000),('transverse_x',100000),('heat_1',200),('heat_2',200),('leak_2',62.5),('leak_3',50)]}
    assert not feasibility(obs,config)['passes']['leak_2']
    assert not feasibility(obs,config)['full_transverse_feasibility']

def test_duplicate_metric_coordinates_and_noise(config):
    p=Geometry(config).sample(np.random.default_rng(1),1)[0]
    a=Sample(p,{'longitudinal':Observation(1000,.02,lower=980,upper=1020,qualified=True)})
    b=Sample(p,{'longitudinal':Observation(1200,1.,lower=900)})
    x,y,n=Proposer(config).training([a,b],'longitudinal')
    assert len(y)==1 and np.expm1(y[0])==pytest.approx(1200)
    assert n[0]==pytest.approx(config.search.unbounded_log_noise)
    assert len(Proposer(config).training([a,b],'transverse_x')[1])==0

def test_budget_drains_running_stage_and_never_resets(tmp_path):
    store=RoundStore(tmp_path/'state.json','abc');store.activate(0)
    store.begin({'key':'axis1'});store.tick(48*3600+10)
    assert not store.may_dispatch and store.data['pending']['key']=='axis1'
    store.drain('budget')
    result=tmp_path/'result.json';atomic_json(result,{'job_key':'axis1','status':'completed'})
    assert store.register('axis1',result)
    assert not store.register('axis1',result)
    store.pause(now=48*3600+20)
    reloaded=RoundStore(store.path,'abc')
    assert reloaded.data['active_seconds']==48*3600+20
    with pytest.raises(RuntimeError):reloaded.activate(500000)
    with pytest.raises(RuntimeError):RoundStore(store.path,'changed')

def test_pause_idle_free_and_pending_identity(tmp_path):
    store=RoundStore(tmp_path/'state.json','x');store.activate(0);store.tick(10);store.pause(now=12)
    store.activate(1000);store.tick(1005)
    assert store.data['active_seconds']==17
    store.begin({'key':'x'})
    with pytest.raises(RuntimeError):store.pause(now=1006)
    with pytest.raises(RuntimeError):store.register('other',tmp_path/'missing')

def test_manifest_rejects_parent_paths(tmp_path):
    with pytest.raises(ValueError):validate_manifest(tmp_path,{'../other':{'bytes':0,'sha256':'x'}})
