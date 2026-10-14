"""Two independent fast Wakis wakes on one candidate-specific FIT mesh.

Axis provides Wz and passive CW estimates. X source is +0.002 m; witnesses
stay on axis and its derivative stencil. Full 35 m wake, SI fields, q=-1 nC.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
from .config import Config
from .io import atomic_json,digest,validate_manifest

_DLL_HANDLES=[]
def runtime(config: Config,out: Path) -> None:
    """Use the pinned source and process-local CUDA DLL paths only."""
    os.environ.setdefault('MPLBACKEND','Agg')
    os.environ.setdefault('CUPY_CACHE_DIR',str(out.parent/'cupy_cache'))
    command=['git','-c','safe.directory='+Path(config.paths.wakis_source).as_posix(),'-C',config.paths.wakis_source]
    revision=subprocess.check_output(command+['rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(command+['status','--porcelain','--untracked-files=no'],text=True).strip()
    if revision!=config.runtime.upstream_revision or dirty:raise RuntimeError('Pinned Wakis source has changed')
    site=Path(config.paths.gpu_python).parent.parent/'Lib/site-packages'
    for p in (site/'nvidia/cuda_runtime/bin',site/'nvidia/cuda_nvrtc/bin',Path(config.paths.cst_library_path).parent):
        if p.is_dir():
            _DLL_HANDLES.append(os.add_dll_directory(str(p)))
            os.environ['PATH']=str(p)+os.pathsep+os.environ.get('PATH','')
    sys.path.insert(0,config.paths.wakis_source)

def run(config: Config,prepared: Path,out: Path,stage: str) -> dict:
    """Run one whole wake; no partial field trace can become an observation."""
    if stage not in ('axis','x'):raise ValueError('Only axis and X are automatic')
    out.mkdir(parents=True,exist_ok=False);runtime(config,out)
    import numpy as np,cupy as cp,h5py,psutil
    from scipy.constants import c
    from wakis import GridFIT3D,WakeSolver
    from wakis.sources import Beam
    from .backend.saved_metric_solver import SavedMetricSolver
    from .backend.surface_copper import SurfaceCopper
    from .backend.staggered_ports import StaggeredPortLayers
    from .backend.local_te_cpml import attach
    from .backend.optimized_backend import install_fusion
    from .backend.compact_backend import CompactEngine
    from .timestep import choose_timestep
    from .monitors import PassiveMonitor,ThermalMonitor
    from .wake import integrate_line,pw_transverse
    started=time.perf_counter()
    validate_manifest(prepared,json.loads((prepared/'manifest.json').read_text()))
    if psutil.virtual_memory().available<config.runtime.start_free_ram_gib*2**30:raise MemoryError('Insufficient RAM before GPU setup')
    atomic_json(out/'status.json',dict(phase='GPU_initialization',at=time.time()))
    metrics=dict(np.load(prepared/'effective_metrics.npz'))
    dt,audit=choose_timestep(metrics);atomic_json(out/'timestep.json',audit)
    axes=[np.r_[metrics[k],2*metrics[k][-1]-metrics[k][-2]] for k in 'xyz']
    grid=GridFIT3D(x=axes[0],y=axes[1],z=axes[2],verbose=0)
    offset=[0.,0.] if stage=='axis' else [config.physics.offset_m,0.]
    positions=np.array([[0,0],[-.002,0],[.002,0],[0,-.002],[0,.002]])
    source_indices=[int(np.argmin(abs(metrics[k]-v))) for k,v in zip('xy',offset)]
    wake=WakeSolver(q=-1e-9,sigmaz=.07,beta=1.,xsource=offset[0],ysource=offset[1],xtest=0.,ytest=0.,
                    wakelength=35.,compute_plane='longitudinal',fmax=config.physics.band_hz[1],save=False)
    solver=SavedMetricSolver(grid,wake,metrics=metrics,use_stl=True,use_gpu=True,use_sibc=False,
               fmax=config.physics.band_hz[1],dtype=np.float32,bg=[1,1,0],bc_low=['pec']*3,bc_high=['pec']*3,
               dt=dt,cfln=.5,source_type='tfsf',verbose=0)
    solver.tDsiDmuiDaC=solver.tDsiDmuiDaC.tocsr();solver.itDaiDepsDstC=solver.itDaiDepsDstC.tocsr()
    copper=SurfaceCopper(solver,metrics,prepared/'copper_surface.vtp',out,neighbors=4,conductivity=config.physics.conductivity_s_per_m)
    faces=json.loads((prepared/'port_faces.json').read_text())
    absorber=StaggeredPortLayers(solver,metrics,[f for f in faces if f['name'] in ('port_2','port_3')],strength=10.)
    cpml=attach(solver,metrics,faces,strength=10.)
    fusion=install_fusion(solver,copper,96)
    beam=Beam(xsource=offset[0],ysource=offset[1],q=wake.q,sigmaz=.07,beta=1.,ti=wake.ti)
    nx,ny,nz=solver.Nx,solver.Ny,solver.Nz
    lines=[]
    for x,y in positions:
        ix=int(np.argmin(abs(metrics['x']-x)));iy=int(np.argmin(abs(metrics['y']-y)))
        if abs(metrics['x'][ix]-x)+abs(metrics['y'][iy]-y)>1e-12:raise ValueError('Exact witness node missing')
        lines.extend(2*solver.N+ix+iy*nx+np.arange(nz)*nx*ny)
    line=cp.asarray(lines,dtype=cp.int32)
    nt=int(np.ceil((35.+wake.ti*c+np.ptp(solver.z))/(c*float(solver.dt))))
    monitor=PassiveMonitor(solver,metrics,faces,out,nt,enabled=stage=='axis')
    buffer=cp.empty((256,5*nz),dtype='f4')
    engine=CompactEngine(solver,copper,absorber,beam,monitor,line,buffer,out)
    thermal=ThermalMonitor(engine,prepared/'thermal_surface.npz',out) if stage=='axis' else None
    prep=json.loads((prepared/'preparation.json').read_text())
    meta=dict(stage=stage,source_offset_m=offset,witness_positions_m=positions.tolist(),geometry_sha256=prep['geometry_sha256'],
              metrics_sha256=digest(prepared/'effective_metrics.npz'),sigma_m=.07,wake_length_m=35.,
              shape=[nx,ny,nz],dt_s=float(solver.dt),steps=nt,precision='float32',cpml=cpml,fusion=fusion,
              startup_seconds=time.perf_counter()-started,pid=os.getpid(),created=psutil.Process().create_time())
    files=[Path(__file__),Path(__file__).with_name('monitors.py'),Path(__file__).with_name('timestep.py')]
    files+=sorted(Path(__file__).with_name('backend').glob('*.py'))
    contract=dict(code={p.name:digest(p) for p in files},physics=config.as_dict()['physics'],upstream=config.runtime.upstream_revision)
    meta['solver_contract_sha256']=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
    atomic_json(out/'run.json',meta)
    t0=time.perf_counter();last=0.
    with h5py.File(out/'Ez_lines.h5','x') as f:
        data=f.create_dataset('Ez_V_per_m',(nt,5*nz),dtype='f4',chunks=(256,5*nz))
        f['z_mid_m']=solver.z;f['dz_m']=solver.dz
        f.attrs['dt_s']=float(solver.dt);f.attrs['ti_s']=wake.ti;f.attrs['q_C']=wake.q
        try:
            for step in range(nt):
                engine.update_source(step)
                if step==0 and [int(beam.ixs),int(beam.iys)]!=source_indices:raise ValueError('Source placement mismatch')
                engine.record(step);engine.step()
                if thermal:thermal.record_after_step(step)
                if (step+1)%256==0 or step+1==nt:
                    count=step%256+1;cp.cuda.Stream.null.synchronize();host=cp.asnumpy(buffer[:count]);em=engine.max_e()
                    if not np.isfinite(host).all() or not np.isfinite(em) or em>1e9:
                        field=engine.E if engine.active else solver.E.array
                        index=int(cp.argmax(cp.abs(field)))
                        if engine.active:index=int(engine.ei[index])
                        comp,cell=divmod(index,solver.N);iz,rem=divmod(cell,nx*ny);iy,ix=divmod(rem,nx)
                        atomic_json(out/'stability_failure.json',dict(step=step+1,max_E=str(em),component=comp,
                            cell=[ix,iy,iz],position_m=[float(metrics[k][i]) for k,i in zip('xyz',(ix,iy,iz))]))
                        raise FloatingPointError('Field stability guard')
                    data[step+1-count:step+1]=host;f.attrs['written_steps']=step+1
                    elapsed=time.perf_counter()-t0
                    if elapsed-last>=config.runtime.heartbeat_s or step+1==nt:
                        last=elapsed;f.flush()
                        atomic_json(out/'status.json',dict(phase='wake',at=time.time(),step=step+1,total=nt,elapsed_s=elapsed,
                                  max_E_V_per_m=em,host_free_gib=psutil.virtual_memory().available/2**30,
                                  gpu_allocated_gib=cp.get_default_memory_pool().total_bytes()/2**30))
                    if psutil.virtual_memory().available<config.runtime.running_free_ram_gib*2**30:raise MemoryError('GPU solve host RAM guard')
                    if elapsed>config.runtime.solve_timeout_s:raise TimeoutError('Wake stage time guard')
                    if (out/'ABORT').exists():raise RuntimeError('Explicit emergency abort')
        finally:
            if thermal:thermal.close()
    monitor.save();meta['solve_seconds']=time.perf_counter()-t0
    # A separate completion certificate makes postprocessing retryable without
    # spending another field solve if reconstruction is interrupted.
    atomic_json(out/'field_complete.json',dict(meta,complete_steps=nt))
    wakes=[]
    with h5py.File(out/'Ez_lines.h5','r') as f:
        for j in range(5):
            s,w=integrate_line(f['Ez_V_per_m'][:,j*nz:(j+1)*nz-1],solver.z[:-1],solver.dz[:-1],float(solver.dt),wake.ti,wake.q,35.)
            wakes.append(w)
    longitudinal=np.column_stack(wakes);transverse=pw_transverse(s,longitudinal,positions)
    np.savez_compressed(out/'wake.npz',s_m=s,longitudinal_V_per_pC=longitudinal[:,0],witness_wakes_V_per_pC=longitudinal,
                        transverse_V_per_pC=transverse)
    meta.update(status='complete',total_seconds=time.perf_counter()-started)
    atomic_json(out/'result.json',meta);return meta
