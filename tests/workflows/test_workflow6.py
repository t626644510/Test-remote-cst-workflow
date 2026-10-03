"""WF6 scientific invariants and expensive-task isolation, without CST."""
from dataclasses import replace
from pathlib import Path
import json,sys
import numpy as np
import pytest
from workflows.rfgun_wake_thermal.config import Config,Paths,Reconstruction,Physics,Runtime,NAMES,load_config
from workflows.rfgun_wake_thermal.geometry import Geometry
from workflows.rfgun_wake_thermal.reconstruction import transverse_norm,align_transverse,basis,resonators,direct_spectrum,form_factor,reconstruct,C
from workflows.rfgun_wake_thermal.thermal import analyze_thermal,losses_vba
from workflows.rfgun_wake_thermal.repair import bad_ports,next_ports
from workflows.rfgun_wake_thermal.io import atomic_json,digest
from workflows.rfgun_wake_thermal.storage import Store,retained_candidates,prune_native,verify_evidence
from workflows.rfgun_wake_thermal.search import Controller
from workflows.rfgun_wake_thermal.campaign import Campaign

pytestmark=pytest.mark.no_cst


def fixed_tail_log():
    return ('2026-10-03 21:13:17 Maximum number of pulse widths simulated, solver stopped.\n'
            'Simulated number of time steps: 132966\nMaximum number of time steps: 132966\n'
            '2026-10-03 21:13:17 Time Domain: WakefieldSolver finished at: 2026-10-03 21:13:17 +0800')


def test_fixed_tail_completion_is_success_without_successful_phrase():
    from datetime import datetime
    from workflows.rfgun_wake_thermal.completion import validate_completion
    proof=validate_completion('axis',{'success':True},fixed_tail_log(),[],int(datetime(2026,10,3,20,14,10).timestamp()*1e9))
    assert proof['calculated_steps']==proof['planned_steps']==132966


@pytest.mark.parametrize('change',['incomplete','zero','no_counts','error','abort','wrapper','stale','secondary_only'])
def test_completion_rejects_false_success(change):
    from datetime import datetime
    from workflows.rfgun_wake_thermal.completion import validate_completion
    log=fixed_tail_log();messages=[];solver={'success':True};start=datetime(2026,10,3,20,14,10)
    if change=='incomplete':log=log.replace('Simulated number of time steps: 132966','Simulated number of time steps: 123')
    if change=='zero':log=log.replace('132966','0')
    if change=='no_counts':log='\n'.join(s for s in log.splitlines() if 'steps:' not in s)
    if change=='error':messages=[{'type':'ERROR','text':'Port 3 mesh failure'}]
    if change=='abort':log+='\nAborted by user'
    if change=='wrapper':solver={'success':False}
    if change=='stale':start=datetime(2026,10,4)
    if change=='secondary_only':log='2026-10-03 21:13:17 Successfully finished Secondary Quantity Evaluation.'
    with pytest.raises(ValueError):validate_completion('axis',solver,log,messages,int(start.timestamp()*1e9))


def test_saved_wake_recovery_never_solves(cfg,point,tmp_path,monkeypatch):
    from datetime import datetime
    from workflows.rfgun_wake_thermal import runtime,supervision
    folder=tmp_path/'attempt';folder.mkdir()
    task=dict(directory=str(folder),template='axis.cst',stage='axis',ports=[20,22],parameters=point,identity='same-solve')
    path=folder/'project/axis.cst';path.parent.mkdir();path.write_text('native result')
    log=path.with_suffix('')/'Result/Model.log';log.parent.mkdir(parents=True);log.write_text(fixed_tail_log())
    (folder/'Model.log').write_text(fixed_tail_log());(folder/'messages.txt').write_text('[]')
    actual=dict(parameters=dict(Geometry(cfg).expand(point),**dict(zip(cfg.runtime.port_parameters,task['ports']))))
    for name,value in [('task',task),('solve_started',dict(identity=task['identity'],started_ns=int(datetime(2026,10,3,20).timestamp()*1e9))),('solver_result',{'success':True}),('effective_settings',actual),('worker_result',{'status':'failed','error':'old recognition error'})]:
        atomic_json(folder/(name+'.json'),value)
    monkeypatch.setattr(supervision,'check_recovery',lambda p:None)
    monkeypatch.setattr(runtime,'effective_settings',lambda *a:actual)
    worker=runtime.CSTWorker(cfg)
    monkeypatch.setattr(worker,'_project',lambda *a:pytest.fail('Recovery must not open CST'))
    monkeypatch.setattr(worker,'_extract',lambda *a:dict(status='valid'))
    old=digest(folder/'worker_result.json');native=digest(path)
    assert worker.recover_saved_wake(task)['status']=='complete'
    assert digest(path)==native and digest(folder/'worker_result.json')==old
    assert json.loads((folder/'recovered_completion.json').read_text())['new_solver_calls']==0
    wrong=dict(task,ports=[20,24])
    with pytest.raises(ValueError,match='task identity'):worker.recover_saved_wake(wrong)
    actual['parameters'][cfg.runtime.port_parameters[0]]=30
    with pytest.raises(ValueError,match='parameters or port'):worker.recover_saved_wake(task)


def test_charge_default_is_distance(cfg):
    assert cfg.results.charge.endswith('Charge distribution (distance)')


def test_saved_thermal_recovery_copies_native_without_solver(cfg,point,tmp_path,monkeypatch):
    from datetime import datetime
    from workflows.rfgun_wake_thermal import runtime,supervision
    folder=tmp_path/'thermal_attempt';folder.mkdir()
    task=dict(directory=str(folder),template='thermal.cst',stage='thermal',ports=[20,22],parameters=point,identity='saved-thermal')
    native=folder/'project/thermal.cst';native.parent.mkdir();native.write_text('native result')
    log='2026-10-04 00:59:00 Eigenmode solver results:\n1 499.659 MHz 1.076e4 4.062e-16'
    log_path=native.with_suffix('')/'Result/Model.log';log_path.parent.mkdir(parents=True);log_path.write_text(log)
    (folder/'Model.log').write_text(log)
    actual=dict(parameters=Geometry(cfg).expand(point))
    for name,value in [('task',task),('solve_started',dict(identity=task['identity'],started_ns=int(datetime(2026,10,4,0,53).timestamp()*1e9))),
            ('solver_result',{'success':True}),('effective_settings',actual),('messages',[dict(type='INFO',text='Eigenmode solver successful')])]:
        atomic_json(folder/(name+'.json'),value)
    monkeypatch.setattr(supervision,'check_recovery',lambda _:None)
    monkeypatch.setattr(runtime,'effective_settings',lambda *a:actual)
    def copy(source,dest):
        import shutil
        dest.mkdir();shutil.copy2(source,dest/source.name)
        shutil.copytree(source.with_suffix(''),dest/source.stem)
    monkeypatch.setattr(runtime,'copy_verified_project',copy)
    worker=runtime.CSTWorker(cfg)
    monkeypatch.setattr(worker,'_project',lambda *a:pytest.fail('Only isolated extraction is allowed'))
    def extract(path,directory,stage,passed):
        assert path!=native and path.read_text()==native.read_text() and stage=='thermal'
        path.write_text('derived data in copy only')
        return dict(status='valid',power5=388.,power6=519.)
    monkeypatch.setattr(worker,'_extract',extract)
    before=digest(native)
    assert worker.recover_saved_thermal(task)['result']['power6']==519
    assert digest(native)==before
    assert json.loads((folder/'thermal_recovery/recovered_completion.json').read_text())['new_solver_calls']==0


def test_screening_uses_consistent_finite_tail_proxy_without_qualifying(cfg,point):
    from workflows.rfgun_wake_thermal.screening import search_metrics,screening_admission
    from workflows.rfgun_wake_thermal.campaign import baseline_admission
    c=dict(parameters=point,complete=True,failed=False,metrics={'power5':388.,'power6':519.},details={
        'longitudinal':dict(status='uncertain',diagnostics={'direct_peak':1177.}),
        'transverse':dict(status='uncertain',diagnostics={'direct_peak':157655.}),
        'thermal':dict(status='valid')})
    screening=replace(cfg,search=replace(cfg.search,observation_mode='finite_tail_screening'))
    assert 'longitudinal' not in search_metrics(cfg,c)
    assert search_metrics(screening,c)['longitudinal']==1177
    assert screening_admission(c)['ready'] and not baseline_admission(c)['ready']
    # Even a reliable reconstructed peak must use the same proxy in this GP.
    c['metrics']['longitudinal']=9000
    assert search_metrics(screening,c)['longitudinal']==1177
    c['details']['transverse']['diagnostics']['direct_peak']=float('nan')
    assert not screening_admission(c)['ready']
    assert 'transverse' not in search_metrics(screening,c)


@pytest.mark.parametrize('failed',[False,True])
def test_tail_validation_three_stages_budget_exemption_and_no_replay(cfg,point,tmp_path,monkeypatch,failed):
    from workflows.rfgun_wake_thermal import tail_validation as tv
    from workflows.rfgun_wake_thermal.config import Config
    original=Store(cfg,'original');original.state.update(status='paused',active_seconds=1234.)
    original.state['candidates']=[dict(id='base',parameters=point,ports=[20,22],revision=1,stages={},metrics={},details={})]
    original.save();original.close()
    state_path=Path(cfg.paths.output_dir)/'state.json';before=state_path.read_bytes()
    output=tmp_path/'validation_state';bulk=tmp_path/'validation_bulk'
    derived=tv.validation_config(cfg,output,bulk,50)
    assert derived.physics.wake_length_m==50 and cfg.physics.wake_length_m==35
    assert derived.physics.band_hz==cfg.physics.band_hz and derived.physics.sigma_m==cfg.physics.sigma_m
    with pytest.raises(ValueError):tv.validation_config(cfg,Path(cfg.paths.output_dir)/'nested',bulk,50)
    monkeypatch.setattr(Config,'validate',lambda *a,**k:None)
    monkeypatch.setattr(tv,'project_manifest',lambda _:dict(source='immutable'))
    monkeypatch.setattr(tv,'check_recovery',lambda _:None)
    monkeypatch.setattr(tv,'offline_candidate',lambda *a:dict(metrics={},details={'transverse':{'status':'uncertain'}}))
    calls=[]
    def backend(config,job,store,timeout):
        calls.append(job['stage']);assert job['ports']==[20,22]
        raw=Path(job['directory'])/'raw';raw.mkdir(parents=True)
        (raw/'curve').write_text('data');atomic_json(raw/'manifest.json',{'curve':digest(raw/'curve')})
        result=dict(status='failed' if failed and job['stage']=='x' else 'complete',raw=str(raw),identity=job['identity'])
        atomic_json(raw.parent/'worker_result.json',result)
        return result
    report=tv.run_validation(cfg,output,bulk,50,backend=backend)
    assert calls==(['axis','x'] if failed else ['axis','x','y'])
    assert report['excluded_from_campaign_budget'] and state_path.read_bytes()==before
    assert report['status']==('validation_failed' if failed else 'validation_complete')
    assert report['solver_starts']==len(calls)
    resumed=tv.run_validation(cfg,output,bulk,50,resume=True,backend=lambda *a:pytest.fail('Duplicate solve'))
    assert resumed['solver_starts']==len(calls) and state_path.read_bytes()==before


def test_screening_gp_leaves_qualified_observations_empty(cfg,point):
    cfg=replace(cfg,search=replace(cfg.search,observation_mode='finite_tail_screening'))
    st=state(cfg)
    for i in range(7):
        st['candidates'].append(dict(parameters=dict(point,selfangle1=10+i),metrics={},details={
            'longitudinal':{'diagnostics':{'direct_peak':1000.+i}}}))
    model=Controller(cfg,st);model.fit()
    assert 'longitudinal' in model.models
    assert all(c['metrics']=={} for c in st['candidates'])


def test_eigenmode_success_in_structured_messages_still_requires_fresh_result_log():
    from datetime import datetime
    from workflows.rfgun_wake_thermal.completion import validate_completion
    log='2026-10-04 00:59:00 Eigenmode solver results:\nMode Frequency Total Q Accuracy\n1 499.659 MHz 1.076e4 4.062e-16'
    messages=[dict(type='INFO',text='Eigenmode solver successful')]
    start=int(datetime(2026,10,4,0,53).timestamp()*1e9)
    assert validate_completion('thermal',{'success':True},log,messages,start)['kind']=='thermal'
    with pytest.raises(ValueError):validate_completion('thermal',{'success':True},log,[],start)
    with pytest.raises(ValueError):validate_completion('thermal',{'success':True},log.replace('Eigenmode solver results:','Meshing successful'),messages,start)
    with pytest.raises(ValueError):validate_completion('thermal',{'success':True},log,messages,start+3600*10**9)


def test_pole_seeding_does_not_count_strong_workmode_sidelobes_as_homs():
    from scipy.signal import find_peaks
    from workflows.rfgun_wake_thermal.reconstruction import seed_spectrum
    # Strong, unresolved 500 MHz working pole plus a 100x weaker 1.3 GHz HOM.
    # Seed taper must preserve the HOM without inventing rectangular-tail poles.
    s=np.linspace(1,35,8192);f=np.linspace(55e6,2048e6,4096)
    wake=basis(s,np.array([500e6,1300e6]),np.array([50000.,300.]),'longitudinal')@np.array([[1.],[.01]])
    original=wake.copy()
    direct=abs(direct_spectrum(s,wake,f,.05,'longitudinal')[:,0])
    seeded=abs(seed_spectrum(s,wake,f,.05,'longitudinal')[:,0])
    p,_=find_peaks(seeded,prominence=seeded.max()*.001,distance=2)
    rectangular,_=find_peaks(direct,prominence=direct.max()*.001,distance=2)
    assert len(rectangular)>24 and len(p)==2
    assert f[p]/1e6==pytest.approx([500,1300],abs=1)
    assert np.array_equal(wake,original)

@pytest.fixture
def cfg(tmp_path):
    return Config(Paths({s:str(tmp_path/'sources'/(s+'.cst')) for s in ('axis','x','y','thermal')},str(tmp_path/'state'),str(tmp_path/'bulk')))

@pytest.fixture
def point(cfg):
    p={n:sum(cfg.bounds[n])/2 for n in NAMES}
    p['DownHeight1']=-15;p['DownHeight2']=10
    return p

def state(cfg):
    return dict(candidates=[],rng=None,radius=.25,improving=0,not_improving=0)

def test_roundtrip_negative_height_and_antenna_signs(cfg,point):
    g=Geometry(cfg);native=g.expand(point)
    assert native['inner_r']==-25 and native['inner_r2']==25
    assert native['inner_angle']<0<native['inner_angle3']
    assert 'Lin1' not in native and native['Lin']==point['Lin1']
    assert g.collapse(native)==pytest.approx(point)

@pytest.mark.parametrize('projection',[5.43,19.57])
def test_projection_limits(cfg,point,projection):
    point['projection1']=projection;point['projection2']=projection
    assert not Geometry(cfg).violations(point)
    native=Geometry(cfg).expand(point)
    assert 2*abs(native['inner_r'])*(1-np.cos(np.deg2rad(native['inner_angle'])))==pytest.approx(projection)

@pytest.mark.parametrize('change',[{'projection1':19.5701},{'DownHeight1':-50},{'Lin2':9},{'projection2':5.42}])
def test_combination_rejections(cfg,point,change):
    point.update(change);assert Geometry(cfg).violations(point)

def test_config_type_and_path_validation(cfg):
    cfg.validate()
    with pytest.raises(ValueError):replace(cfg,search=replace(cfg.search,initial_points=1.5)).validate()
    with pytest.raises(ValueError):replace(cfg,search=replace(cfg.search,hours=True)).validate()
    with pytest.raises(ValueError):replace(cfg,paths=replace(cfg.paths,artifact_dir=cfg.paths.output_dir)).validate()
    with pytest.raises(ValueError):replace(cfg,reconstruction=replace(cfg.reconstruction,min_correlation=1.1)).validate()

def test_full_complex_matrix_real_direction_not_diagonal_shortcut():
    z=np.array([[1,1],[1j,1j]])*120000
    assert transverse_norm(z)==pytest.approx(240000)
    assert max(abs(z.diagonal()))<150000
    angles=np.linspace(0,np.pi,100001);u=np.array([np.cos(angles),np.sin(angles)])
    assert transverse_norm(z)==pytest.approx(np.linalg.norm(z@u,axis=0).max(),rel=1e-9)
    assert transverse_norm(z*np.exp(.82j))==pytest.approx(transverse_norm(z))
    # A complex unit vector is not an admissible beam offset direction.
    z=np.array([[1,1j],[0,0]])
    assert transverse_norm(z)==pytest.approx(1)

def test_signed_alignment_and_port_identity():
    s=np.linspace(-1,35,200)
    axis=dict(s_m=s,wake=np.column_stack([s,s*2,s*3]),ports=[20,20])
    x=dict(axis,wake=axis['wake']+np.array([.004,-.006,0]))
    y=dict(axis,wake=axis['wake']+np.array([-.008,.01,0]))
    _,k=align_transverse(axis,x,y,.002)
    assert k[40]==pytest.approx(np.array([[2,-4],[-3,5]]))
    with pytest.raises(ValueError):align_transverse(axis,x,dict(y,ports=[22,20]),.002)

@pytest.mark.parametrize('direction',['longitudinal','transverse'])
def test_wf2_resonator_and_fourier_normalization_regression(direction):
    # WF2 conventions: A=2*pi*f*(R/Q)*bunch_factor/1e12, f Hz.
    f=np.array([8e8]);q=np.array([20.]);rq=1.3
    amplitude=2*np.pi*f*rq*form_factor(f,.05)/1e12
    out=resonators(f,f,q,amplitude[:,None],.05,direction)
    assert out[0,0]==pytest.approx(26+0j)
    s=np.linspace(0,100,100000)
    wake=basis(s,f,q,direction)@amplitude[:,None]
    # Finite tail of this low-Q mode is negligible; direct FT recovers peak.
    direct=direct_spectrum(s,wake,f,.05,direction)
    assert abs(direct[0,0])==pytest.approx(26,rel=.002)
    assert resonators(f,f,q,-amplitude[:,None],.05,direction)==pytest.approx(-out)

def test_uncertain_data_never_zero(cfg):
    s=np.linspace(-.2,35,400)
    result=reconstruct(s,np.zeros(len(s)),cfg.physics,replace(cfg.reconstruction,spectrum_points=128,fit_points=64),'longitudinal',2000)
    assert result.status=='uncertain' and result.value is None
    with pytest.raises(ValueError):reconstruct(s[:-100],np.zeros(len(s)-100),cfg.physics,cfg.reconstruction,'longitudinal',2000)
    bad=np.zeros(len(s));bad[20]=np.nan
    with pytest.raises(ValueError):reconstruct(s,bad,cfg.physics,cfg.reconstruction,'longitudinal',2000)

def test_joint_signed_shared_pole_synthetic():
    p=replace(Physics(),band_hz=(700e6,900e6),sigma_m=.01)
    r=replace(Reconstruction(),seeds=(17,43,109),starts_m=(1.,3.),spectrum_points=1200,fit_points=400,max_nfev=90,max_modes=3,peak_prominence_fraction=.15)
    s=np.linspace(-.1,35,10000);f=np.array([8e8]);q=np.array([100.]);amps=np.array([[.03,-.02,.01,.04]])
    w=basis(np.maximum(s,0),f,q,'transverse')@amps;w[s<0]=0
    result=reconstruct(s,w,p,r,'transverse',150000)
    assert result.status=='valid',result.reasons
    assert len(result.diagnostics['fits'])==6
    truth=transverse_norm(resonators(f,f,q,amps,.01,'transverse').reshape(2,2))
    assert result.value==pytest.approx(truth,rel=.03)

def test_thermal_voltage_scaling_and_dynamic_solids(tmp_path):
    p=replace(Physics(),thermal_z_samples=101,thermal_z_range_mm=(-100,100))
    f=500e6;z=np.linspace(-.1,.1,101);ez=100*np.exp(-2j*np.pi*f*z/C)
    (tmp_path/'losses.txt').write_text('Frequency/Hz 5e8\nEnergy/J 1\n component5:arbitrary 2 100\n component5:another 3 100\n component6:anything 7 100\n unrelated:solid 1000 100\n')
    np.savetxt(tmp_path/'voltage.csv',np.column_stack([ez.real,ez.imag,np.ones(101)]),delimiter=',',header='a,b,c',comments='')
    a=analyze_thermal(tmp_path,f,p);assert a['voltage_peak_v']==pytest.approx(20)
    assert a['power5']==pytest.approx(5*(500000/20)**2)
    b=analyze_thermal(tmp_path,f,replace(p,voltage_peak_v=250000));assert b['power6']==pytest.approx(a['power6']/4)
    with pytest.raises(ValueError):analyze_thermal(tmp_path,f*1.01,p)

def test_port_repair_is_narrow_and_bounded():
    assert bad_ports('The mesh at port 2 is inhomogeneous.')==(2,)
    assert bad_ports('Port 2 and port 3 have non-uniform mesh')==(2,3)
    assert bad_ports('Port 2 solver failed to converge')==()
    assert bad_ports('Geometry self intersection')==()
    assert bad_ports('ERROR: Waveguide for port number 3 is too short. The waveguide must be homogeneous for at least three equidistant mesh planes along propagation direction.')==(3,)
    c=Runtime();assert next_ports((20,20),(3,),[[20,20]],0,0,c)==(20,22)
    assert next_ports((20,20),(2,3),[[20,20]],0,0,c)==(22,22)
    assert next_ports((20,20),(2,),[],10,0,c) is None
    assert next_ports((20,20),(2,),[],0,7200,c) is None

def test_partial_gp_failure_not_observation_or_radius_shrink(cfg,point):
    st=state(cfg)
    for i in range(7):
        p=dict(point);p['selfangle1']+=i
        st['candidates'].append(dict(parameters=p,metrics={'longitudinal':2000-i*20},failed=False))
    st['candidates'].append(dict(parameters=point,metrics={},failed=True))
    model=Controller(cfg,st);model.fit()
    assert set(model.models)=={'longitudinal'}
    model.update_radius({'longitudinal':1000},{})
    assert st['radius']==.25 and st['not_improving']==0
    for _ in range(6):model.update_radius({'longitudinal':1000,'transverse':100000},{'longitudinal':1100,'transverse':110000})
    assert st['radius']==pytest.approx(.175)

def test_global_pool_and_rng_resume(cfg,point):
    cfg=replace(cfg,search=replace(cfg.search,pool=32));st=state(cfg)
    model=Controller(cfg,st);p,_=model.propose();assert not Geometry(cfg).violations(p)
    saved=json.loads(json.dumps(st));a,_=model.propose();b,_=Controller(cfg,saved).propose();assert a==b
    bad=replace(cfg,bounds={**cfg.bounds,'DownHeight1':(45.,50.),'UpperHeight1':(5.01,6.)})
    with pytest.raises(ValueError):Controller(bad,state(bad)).pool()

def test_journal_budget_shared_db_and_no_duplicate_worker(cfg,point,monkeypatch):
    store=Store(cfg,'contract');candidate=dict(id='c',parameters=point,stages={},metrics={})
    store.state['candidates'].append(candidate)
    task=dict(identity='same',directory=str(Path(cfg.paths.artifact_dir)/'c'/'attempt_0'))
    j=store.reserve(candidate,'axis',task,'near')
    with pytest.raises(ValueError):store.reserve(candidate,'axis',task,None)
    store.complete_job(j,dict(status='complete'));store.mirror();assert len(store.db.get_all_records())==1
    times=iter([10.,20.,25.]);monkeypatch.setattr('workflows.rfgun_wake_thermal.storage.time.monotonic',lambda:next(times))
    store.start_clock();store.exploration='near';store.tick();store.exploration=None;store.tick()
    assert store.state['active_seconds']==15 and store.state['exploration_seconds']['near']==10
    store.last_tick=None;store.close()
    resumed=Store(cfg,'contract');assert resumed.state['active_seconds']==15
    resumed.state['active_seconds']=96*3600-200;assert not resumed.can_start(60)
    resumed.close()

def test_retention_only_owned_verified_bulk(cfg,tmp_path):
    root=Path(cfg.paths.artifact_dir);root.mkdir()
    atomic_json(root/'owner.json',{'contract':'own'})
    attempt=root/'candidates/c/attempt_0';(attempt/'project').mkdir(parents=True);(attempt/'project'/'result').write_text('bulk')
    raw=attempt/'raw';raw.mkdir();(raw/'curve').write_text('permanent')
    atomic_json(raw/'manifest.json',{'curve':digest(raw/'curve')})
    state={'contract':'own','candidates':[{'id':'c','complete':True,'metrics':{}}],
           'jobs':[{'candidate':'c','status':'complete','directory':str(attempt)}]}
    cfg=replace(cfg,runtime=replace(cfg.runtime,retain_recent=0,retain_pareto=0))
    assert verify_evidence(raw);assert prune_native(cfg,state)==[str(attempt/'project')]
    assert (raw/'curve').is_file()
    atomic_json(root/'owner.json',{'contract':'foreign'})
    with pytest.raises(ValueError):prune_native(cfg,state)

def test_baseline_best_and_pareto_retention():
    rows=[dict(id='baseline',source='baseline',complete=True,metrics={})]
    for i in range(8):rows.append(dict(id=str(i),complete=True,feasible=True,metrics=dict(longitudinal=1000,transverse=100000,power5=100+i,power6=100+i)))
    assert retained_candidates(rows,2,5)=={'baseline','0','6','7'}

def test_offline_import_does_not_load_cst():
    assert not any(k=='cst' or k.startswith('cst.') for k in sys.modules)


def test_port_repair_invalidates_trio_preserves_evidence(cfg,point,monkeypatch):
    campaign=Campaign(cfg,Path('local.yaml'),'contract',{'baseline':point,'templates':cfg.paths.templates})
    c=campaign.state['candidates'][0]
    c['stages']={'axis':{'identity':'old','raw':'old_bundle'}};c['metrics']={'longitudinal':1000.}
    task=campaign.task(c,'x');j=campaign.store.reserve(c,'x',task,None)
    campaign.receive(c,j,{'status':'failed','category':'solver_failed','error':'Non-uniform mesh at port 3'})
    assert c['ports']==[20,22] and c['revision']==1 and c['stages']=={} and c['metrics']=={}
    assert j['outcome']['error'] and campaign.next_stage(c)=='axis'
    assert campaign.task(c,'axis')['identity']!=j['identity']
    campaign.store.close()


def test_failed_ordinary_solver_does_not_repair_or_shrink(cfg,point):
    campaign=Campaign(cfg,Path('local.yaml'),'contract',{'baseline':point,'templates':cfg.paths.templates})
    c=campaign.state['candidates'][0];j=campaign.store.reserve(c,'axis',campaign.task(c,'axis'),None)
    campaign.receive(c,j,{'status':'failed','category':'solver_failed','error':'Convergence failed'})
    assert c['failed'] and c['ports']==[20,20] and c['repair_attempts']==0
    assert campaign.state['radius']==.25
    campaign.store.close()


def test_crash_recovery_ingests_completed_stage_without_resolving(cfg,point,monkeypatch):
    campaign=Campaign(cfg,Path('local.yaml'),'contract',{'baseline':point,'templates':cfg.paths.templates})
    c=campaign.state['candidates'][0];task=campaign.task(c,'axis');j=campaign.store.reserve(c,'axis',task,None)
    # Crash occurred after output publication but before coordinator ingestion.
    folder=Path(j['directory']);folder.mkdir(parents=True)
    result=dict(status='complete',identity=j['identity'],raw=str(folder/'raw'),result={})
    atomic_json(folder/'worker_result.json',result)
    monkeypatch.setattr('workflows.rfgun_wake_thermal.campaign.check_recovery',lambda _:None)
    monkeypatch.setattr('workflows.rfgun_wake_thermal.campaign.offline_candidate',lambda *a:dict(metrics={'longitudinal':1900},details={}))
    campaign.backend=lambda *a:pytest.fail('Duplicate expensive worker launch')
    campaign.recover()
    assert c['metrics']['longitudinal']==1900 and j['applied'] and campaign.state['pending'] is None
    with pytest.raises(ValueError):campaign.task(c,'axis')
    campaign.store.close()


def test_solved_postprocess_failure_resume_only_extraction(cfg,point,monkeypatch):
    campaign=Campaign(cfg,Path('local.yaml'),'contract',{'baseline':point,'templates':cfg.paths.templates})
    c=campaign.state['candidates'][0];j=campaign.store.reserve(c,'axis',campaign.task(c,'axis'),None)
    folder=Path(j['directory']);folder.mkdir(parents=True);atomic_json(folder/'solved.json',{'identity':j['identity']})
    campaign.receive(c,j,dict(status='failed',category='postprocess_failed',error='export missing'))
    monkeypatch.setattr('workflows.rfgun_wake_thermal.campaign.check_recovery',lambda _:None)
    monkeypatch.setattr('workflows.rfgun_wake_thermal.campaign.offline_candidate',lambda *a:dict(metrics={'longitudinal':1900},details={}))
    calls=[]
    def backend(config,task,store,timeout):
        calls.append(task);assert task['identity']==j['identity'] and task['result_filename'].startswith('worker_result_pp')
        return dict(status='complete',identity=j['identity'],raw='retained',result={})
    campaign.backend=backend;campaign.recover()
    assert len(calls)==1 and not c['failed'] and 'axis' in c['stages']
    campaign.store.close()


def test_native_success_requires_fresh_explicit_evidence(cfg,point,tmp_path):
    from workflows.rfgun_wake_thermal.runtime import CSTWorker,EvaluationFailure
    # A solve-start marker alone can never authorize implicit restart or stale result reuse.
    folder=tmp_path/'candidate'/'attempt_0';folder.mkdir(parents=True)
    atomic_json(folder/'solve_started.json',{'identity':'same'})
    with pytest.raises(EvaluationFailure,match='no implicit repeat'):
        CSTWorker(cfg).run(dict(directory=str(folder),template='template.cst',stage='axis',parameters=point,ports=[20,20],identity='same'))


def test_only_own_runtime_budget_excludes_pause(cfg,monkeypatch):
    s=Store(cfg,'budget');s.state['active_seconds']=12.;s.save();s.close()
    fresh=Store(cfg,'budget');assert fresh.state['active_seconds']==12
    fresh.close()


def test_windows_watchdog_kills_owned_worker_tree_not_just_venv_launcher(cfg,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from workflows.rfgun_wake_thermal.supervision import launch_worker
    import cst_optimization.core.cleanup as cleanup
    killed=[]
    class Process:
        pid=42
        def poll(self):return None
        def wait(self,timeout):return 0
        def terminate(self):pytest.fail('Must stop owned worker tree including venv child')
    monkeypatch.setattr('workflows.rfgun_wake_thermal.supervision.subprocess.Popen',lambda *a,**k:Process())
    monkeypatch.setattr('workflows.rfgun_wake_thermal.supervision.process_birth',lambda p:100)
    monkeypatch.setattr('workflows.rfgun_wake_thermal.supervision.time.sleep',lambda _:None)
    values=iter([0,2]);monkeypatch.setattr('workflows.rfgun_wake_thermal.supervision.time.monotonic',lambda:next(values))
    monkeypatch.setattr(cleanup,'force_kill_cst',lambda pid:killed.append(pid) or True)
    store=SimpleNamespace(root=tmp_path,config=cfg,state={'active_seconds':0},tick=lambda:None)
    task=dict(id='owned',identity='identity',directory=str(tmp_path/'candidate'/'attempt_0'))
    result=launch_worker(Path('local.yaml'),task,store,1)
    assert killed==[42] and result['category']=='watchdog_timeout'


def test_successful_port_repair_does_not_time_limit_normal_downstream(cfg,point,monkeypatch):
    # Once the repaired axis succeeded, normal X/Y/thermal stages must not share
    # the nearly exhausted repair watchdog. Actual active time remains charged.
    seen=[]
    def backend(config_path,job,store,timeout):
        seen.append(timeout)
        return dict(status='complete',identity=job['identity'],raw='unused',result={})
    campaign=Campaign(cfg,Path('local.yaml'),'repair-test',{'baseline':point,'templates':cfg.paths.templates},backend=backend)
    Path(cfg.paths.artifact_dir).mkdir(parents=True,exist_ok=True)
    c=campaign.state['candidates'][0];c.update(repair_attempts=1,repair_seconds=7199.,repair_stage=None)
    monkeypatch.setattr('workflows.rfgun_wake_thermal.campaign.offline_candidate',lambda *a:dict(metrics={},details={}))
    assert campaign.action(c,'x',None)
    assert seen==[cfg.runtime.stage_timeout_s+cfg.runtime.postprocess_timeout_s+600.]
    assert c['repair_seconds']==7199.
    campaign.store.close()
