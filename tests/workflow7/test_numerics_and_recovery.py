"""Numerical identities and crash boundaries; no CST process is constructed."""
import json
from dataclasses import asdict
from pathlib import Path
import numpy as np
import pytest
from workflows.rfgun_wakis.config import Config,Paths
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.timestep import choose_timestep
from workflows.rfgun_wakis.wake import pw_transverse,source_difference
from workflows.rfgun_wakis.cst_prepare import ProcessIdentity,valid_child,verify_wake_history
from workflows.rfgun_wakis.modal_power import Pole,project,power_w
from workflows.rfgun_wakis.io import atomic_json,digest
from workflows.rfgun_wakis.campaign import Campaign
from workflows.rfgun_wakis.backend.staggered_ports import build_rates
from workflows.rfgun_wakis.processes import matches_worker

def test_cfl_bounds_actual_incidence_singular_value():
    # Positive diagonal FIT metrics; the bound must dominate even unequal
    # cell sizes/cut faces. S has units 1/s in physical input.
    rng=np.random.default_rng(50);shape=(3,2,2);n=np.prod(shape)
    me=rng.uniform(.1,5,(3,n));mh=rng.uniform(.1,5,(3,n))
    c=np.zeros((3*n,3*n))
    for out,inp,d,sign in ((0,1,2,-1),(0,2,1,1),(1,0,2,1),(1,2,0,-1),(2,0,1,-1),(2,1,0,1)):
        stride=(1,shape[0],shape[0]*shape[1])[d]
        for i in range(n):
            c[out*n+i,inp*n+i]-=sign
            if i+stride<n:c[out*n+i,inp*n+i+stride]+=sign
    s=np.sqrt(mh.ravel())[:,None]*c*np.sqrt(me.ravel())[None,:]
    dt,a=choose_timestep(dict(Eps=me,Mue=mh,**{k:np.arange(q) for k,q in zip('xyz',shape)}))
    spectral=np.linalg.svd(s,compute_uv=False)[0]
    assert a['singular_value_upper_bound_per_s']>=spectral
    assert dt*spectral<2

def test_pw_exact_quadratic_and_source_offset_units():
    s=np.linspace(-1,4,501);pos=np.array([[0,0],[-.002,0],[.002,0],[0,-.002],[0,.002]])
    # Wz=3x+7y+200x^2; witness gradient is [3,7] V/pC/m.
    waves=np.tile(3*pos[:,0]+7*pos[:,1]+200*pos[:,0]**2,(len(s),1))
    w=pw_transverse(s,waves,pos)
    assert np.allclose(w,-(s-s[0])[:,None]*[3,7])
    common=dict(geometry_sha256='a',metrics_sha256='b',solver_contract_sha256='c',dt_s=1e-12,
                precision='float32',cpml={'shift':1},sigma_m=.07,wake_length_m=35,witness_positions_m=pos.tolist(),s_m=s)
    a=dict(common,source_offset_m=[0.,0.],transverse_V_per_pC=w)
    x=dict(common,source_offset_m=[.002,0.],transverse_V_per_pC=w+.002*np.array([12.,-5.]))
    _,delta=source_difference(a,x)
    assert np.allclose(delta,[12.,-5.])
    for key in ('geometry_sha256','solver_contract_sha256','dt_s','cpml'):
        bad=dict(x);bad[key]='changed'
        with pytest.raises(ValueError):source_difference(a,bad)

def test_native_time_staggering_preserves_power():
    dt=1.1e-11;t=np.arange(1200)*dt;pole=Pole(500e6,1e5,0.,0.)
    expected=np.array([2.+3j,-4.+2j])
    def samples(time):return np.real(np.exp((-pole.decay_per_s+2j*np.pi*pole.frequency_hz)*time[:,None])*expected)
    e,_=project(t,samples(t),pole);h,_=project(t-dt/2,samples(t-dt/2),pole)
    assert np.allclose(e,expected) and np.allclose(h,expected)
    assert power_w(np.array([[3+4j,0,0]]),np.array([.1]),.02,500000)==pytest.approx(.025)

def test_reused_pid_and_birth_order_never_establish_ownership():
    parent=ProcessIdentity(10,1,100,('parent',))
    assert valid_child(parent,ProcessIdentity(11,10,101,('child',)))
    assert not valid_child(parent,ProcessIdentity(11,10,99,('older',)))
    assert not valid_child(parent,ProcessIdentity(11,9,101,('foreign',)))

def test_explicit_wake_length_uses_final_saved_command(tmp_path):
    project=tmp_path/'copy.cst';p=project.with_suffix('')/'Model/3D/ModelHistory.json'
    atomic_json(p,{'history':['Solver.WakeLength "-1"','Solver.WakeLength "35000"']})
    verify_wake_history(project)
    atomic_json(p,{'history':['Solver.WakeLength "35000"','Solver.WakeLength "0"']})
    with pytest.raises(ValueError):verify_wake_history(project)

def test_thick_radius_equality_and_saved_parameter_alias(tmp_path):
    config=Config(Paths('s',str(tmp_path/'o'),str(tmp_path/'b'),'p','w','c'));g=Geometry(config)
    p=g.sample(np.random.default_rng(3),1)[0];p['coaxr2']=p['PortR1']+2
    assert not g.violations(p)
    assert g.expand(p)['coax_r2']==p['coaxr2']
    p['coaxr2']-=.0001
    assert g.violations(p)

def test_result_replay_keeps_completed_axis_and_is_idempotent(tmp_path):
    c=Config(Paths('s',str(tmp_path/'o'),str(tmp_path/'b'),'p','w','c'))
    path=tmp_path/'config.json';atomic_json(path,c.as_dict());campaign=Campaign(path)
    p=Geometry(c).sample(np.random.default_rng(1),1)[0]
    candidate=dict(id='candidate_0000',parameters=p,observations={},status='axis_pending',forced_transverse=True)
    campaign.store.data['candidates']=[candidate];campaign.store.activate(0)
    campaign.store.begin(dict(key='candidate_0000_axis',stage='axis',candidate_index=0))
    result=tmp_path/'result.json';atomic_json(result,dict(status='completed',job_key='candidate_0000_axis',stage='axis',
         candidate_index=0,parameters=p,observations={'longitudinal':dict(estimate=2400,relative_uncertainty=.25,
         lower=1800,upper=3000,qualified=False)},field_directory='retained_axis'))
    campaign.store.register('candidate_0000_axis',result)
    campaign.apply_results();campaign.apply_results()
    assert len(campaign.store.data['completed_stage_keys'])==1
    assert candidate['status']=='x_pending' and candidate['axis_directory']=='retained_axis'
    assert candidate['observations']['longitudinal']['estimate']==2400
    result.write_text('{}')
    with pytest.raises(RuntimeError):campaign.apply_results()

def test_cpml_halo_retains_partial_edge_support_at_aperture():
    # An Ey midpoint at y=2.5 mm lies beyond the CAD y=2 mm face boundary,
    # but a nonzero FIT edge fraction still carries vacuum support there.
    axes=np.arange(5)*.001;n=125
    metrics=dict(x=axes,y=axes,z=axes,ds=np.ones((3,n)),dsd=np.ones((3,n)),dA=np.ones((3,n)))
    face=dict(name='port_6',axis=0,sign=1,low=[.004,0,0],high=[.004,.002,.003])
    old,_=build_rates(metrics,[face]);halo,_=build_rates(metrics,[face],aperture_halo_cells=1)
    edge=n+2+2*5+2*25
    assert edge not in old['E'][0] and edge in halo['E'][0]
    metrics['ds'][1,edge-n]=0
    metal,_=build_rates(metrics,[face],aperture_halo_cells=1)
    assert edge not in metal['E'][0]

def test_duplicate_phase_detection_excludes_supervisor(tmp_path):
    request=tmp_path/'phase.json'
    assert not matches_worker(['python','supervisor.py',str(request)],request)
    assert matches_worker(['python','-m','workflows.rfgun_wakis.worker',str(request)],request)
    assert not matches_worker(['python','-m','workflows.rfgun_wakis.worker','other.json'],request)

def test_completed_fields_are_not_resolved_when_postprocessing_retries(tmp_path,monkeypatch):
    c=Config(Paths('s',str(tmp_path/'o'),str(tmp_path/'b'),'p','w','c'))
    path=tmp_path/'config.json';atomic_json(path,c.as_dict());campaign=Campaign(path)
    p=Geometry(c).sample(np.random.default_rng(1),1)[0]
    prepared=tmp_path/'prepared';prepared.mkdir();atomic_json(prepared/'manifest.json',{})
    candidate=dict(id='candidate_0000',parameters=p,prepared=str(prepared),observations={},status='axis_pending',forced_transverse=True)
    campaign.store.data['candidates']=[candidate];campaign.store.activate(0)
    campaign.store.begin(dict(key='candidate_0000_axis',stage='axis',candidate_index=0))
    field=campaign.bulk/'candidate_0000/axis_00';field.mkdir(parents=True)
    atomic_json(field/'field_complete.json',{'steps':100,'complete_steps':100})
    calls=[]
    def phase(name,request,timeout):
        calls.append(name)
        assert request['phase']=='analyze'
        return dict(stage='axis',parameters=p,observations={},field_directory=str(field))
    monkeypatch.setattr(campaign,'phase',phase)
    campaign.execute_stage()
    assert calls==['axis_analysis_00']
    assert campaign.store.data['pending'] is None and candidate['axis_directory']==str(field)

def test_partial_hdf5_rejected_even_if_wake_file_exists(tmp_path,monkeypatch):
    import sys,types
    from workflows.rfgun_wakis.postprocess import recover_lines
    atomic_json(tmp_path/'field_complete.json',dict(steps=100,complete_steps=100))
    (tmp_path/'wake.npz').touch()
    class Partial:
        attrs={'written_steps':99}
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setitem(sys.modules,'h5py',types.SimpleNamespace(File=lambda *a:Partial()))
    with pytest.raises(ValueError,match='Incomplete acquisition'):recover_lines(tmp_path)

def test_native_baseline_import_is_idempotent_and_does_not_charge_again(tmp_path,monkeypatch):
    from workflows.rfgun_wakis import bootstrap
    c=Config(Paths('s',str(tmp_path/'o'),str(tmp_path/'b'),'p','w','c'))
    path=tmp_path/'config.json';atomic_json(path,c.as_dict());campaign=Campaign(path)
    p=Geometry(c).sample(np.random.default_rng(1),1)[0]
    campaign.store.data['candidates']=[dict(id='candidate_0000',parameters=p,observations={},status='axis_pending',forced_transverse=True)]
    values={s:dict(stage=s,parameters=p,observations={},field_directory='retained_'+s) for s in ('axis','x')}
    monkeypatch.setattr(campaign,'check_provenance',lambda:None)
    monkeypatch.setattr(bootstrap,'validate_baseline',lambda *a:dict(results=values,prepared='retained_mesh',project='retained.cst'))
    spec=dict(prepared='retained_mesh',project='retained.cst',analyses=dict(axis='a',x='x'))
    campaign.import_baseline(spec);campaign.import_baseline(spec)
    assert campaign.store.data['active_seconds']==0
    assert len(campaign.store.data['results'])==2
    assert campaign.store.data['candidates'][0]['status']=='completed'
    campaign.store.activate(0)
    with pytest.raises(RuntimeError,match='fresh prepared round'):campaign.import_baseline(spec)
