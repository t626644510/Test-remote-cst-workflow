"""Offline, retryable objectives with permanent raw and reconstruction evidence."""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
import json,time
import numpy as np
from .config import Config
from .io import atomic_json,digest,manifest,validate_manifest
from .observations import Observation,from_reconstruction
from .reconstruction import reconstruct
from .wake import source_difference

def recover_lines(directory: Path) -> dict:
    """Finish numeric line integration from a proven full field acquisition."""
    import h5py
    from .wake import integrate_line,pw_transverse
    meta=json.loads((directory/'field_complete.json').read_text())
    with h5py.File(directory/'Ez_lines.h5','r') as f:
        if int(f.attrs['written_steps'])!=meta['steps'] or meta['complete_steps']!=meta['steps']:
            raise ValueError('Incomplete acquisition cannot be recovered')
    if not (directory/'wake.npz').exists():
        waves=[]
        with h5py.File(directory/'Ez_lines.h5','r') as f:
            if int(f.attrs['written_steps'])!=meta['steps'] or meta['complete_steps']!=meta['steps']:
                raise ValueError('Incomplete acquisition cannot be recovered')
            nz=meta['shape'][2];z=f['z_mid_m'][:];dz=f['dz_m'][:]
            for j in range(5):
                s,w=integrate_line(f['Ez_V_per_m'][:,j*nz:(j+1)*nz-1],z[:-1],dz[:-1],f.attrs['dt_s'],f.attrs['ti_s'],f.attrs['q_C'],35.)
                waves.append(w)
        waves=np.column_stack(waves)
        np.savez_compressed(directory/'wake.npz',s_m=s,longitudinal_V_per_pC=waves[:,0],witness_wakes_V_per_pC=waves,
                            transverse_V_per_pC=pw_transverse(s,waves,np.asarray(meta['witness_positions_m'])))
    return meta

def heating_and_leakage(directory: Path,config: Config,parameters: dict) -> tuple[dict,dict]:
    """Fit one working-mode pole per window; peak fields normalize to 500 kV.

Net physical Poynting flux is the leakage objective, not Qe from unmeasured
stored energy. Uncertainty is empirical window/plane sensitivity with a 20%
floor, not a calibrated confidence interval. A failed fit stays unknown.
"""
    import h5py
    from .modal_power import fit_pole,project,voltage,power_w,copper_resistance
    from scipy.constants import mu_0,c
    with h5py.File(directory/'thermal_traces.h5','r') as f:
        te=f['t_E_s'][:];th=f['t_H_s'][:];ez=f['Ez_V_per_m'][:];ht=f['Ht_A_per_m'][:]
        area=f['area_m2'][:];comp=f['component'][:];z=f['z_mid_m'][:];dz=f['dz_m'][:]
    with h5py.File(directory/'port_traces.h5','r') as f:
        pe=f['t_E_s'][:];ph=f['t_H_s'][:];pv=f['fields'][:];width=int(f.attrs['width'])
    planes=json.loads((directory/'port_planes.json').read_text())
    start=30e-9;end=min(te[-1],pe[-1]);middle=(start+end)/2
    windows={};errors={}
    for name,(a,b) in dict(early=(start,middle),late=(middle,end),full=(start,end)).items():
        try:
            select=(te>=a)&(te<=b);selh=(th>=a)&(th<=b)
            if min(select.sum(),selh.sum())<64:raise ValueError('Insufficient working-mode cycles')
            pole=fit_pole(te[select],ez[select]);ep,_=project(te[select],ez[select],pole)
            hp,_=project(th[selh],ht[selh],pole)
            v=abs(voltage(ep,z,dz,pole.frequency_hz))
            if v<=1e-12 or not np.isfinite(v):raise ValueError('Working-mode voltage unresolved')
            rs=copper_resistance(pole.frequency_hz,config.physics.conductivity_s_per_m)
            heat={f'heat_{i+1}':power_w(hp.reshape(-1,3)[comp==i],area[comp==i],rs,v,config.physics.voltage_peak_v) for i in range(2)}
            se=(pe>=a)&(pe<=b);sh=(ph>=a)&(ph<=b)
            efield,_=project(pe[se],pv[se,:width],pole);hfield,_=project(ph[sh],pv[sh,width:],pole)
            flux={};details={}
            for port in ('port_2','port_3'):
                rows=[]
                for p in planes:
                    if p['port']!=port:continue
                    q=slice(p['start'],p['stop']);e=efield[q];h=hfield[q]
                    w=np.asarray(p['weight_m2']);sign=np.asarray(p['sign']);er=np.asarray(p['radial_e']);hr=np.asarray(p['radial_h'])
                    norm=(config.physics.voltage_peak_v/v)**2
                    raw=.5*np.real(np.sum(w*sign*e*np.conj(h)))*norm
                    ea=np.sum(w*er*e)/np.sum(w*er**2);ha=np.sum(w*hr*h)/np.sum(w*hr**2)
                    en=np.sum(w*abs(e)**2);hn=np.sum(w*abs(h)**2)
                    err_e=float(np.sqrt(np.sum(w*abs(e-ea*er)**2)/en)) if en>0 else None
                    err_h=float(np.sqrt(np.sum(w*abs(h-ha*hr)**2)/hn)) if hn>0 else None
                    log=np.log(parameters['SPortR1']/parameters['SPortR2']);zc=mu_0*c*log/(2*np.pi)
                    volt=log*ea;current=2*np.pi*ha;forward=(volt+zc*current)/2;back=(volt-zc*current)/2
                    rows.append(dict(distance_m=p['distance_m'],power_w=float(raw),E_profile_error=err_e,H_profile_error=err_h,
                                     reflection_amplitude=float(abs(back)/abs(forward)) if abs(forward)>0 else None))
                if len(rows)!=3:raise ValueError('Missing leakage plane evidence')
                flux['leak_'+port[-1]]=rows[0]['power_w'];details[port]=rows
            windows[name]=dict(pole=asdict(pole),voltage_peak_v=v,values=dict(heat,**flux),ports=details)
        except (ValueError,RuntimeError,np.linalg.LinAlgError) as exc:errors[name]=str(exc)
    obs={}
    if 'full' in windows:
        full=windows['full'];freq=full['pole']['frequency_hz']
        base_quality=(len(windows)==3 and config.physics.thermal_band_hz[0]<=freq<=config.physics.thermal_band_hz[1]
                      and all(w['pole']['relative_residual']<=.20 for w in windows.values()))
        for name,estimate in full['values'].items():
            if not np.isfinite(estimate) or estimate<=0:continue
            values=[w['values'][name] for w in windows.values()]
            spread=(max(values)-min(values))/estimate
            uncertainty=max(.20,spread,max(w['pole']['relative_residual'] for w in windows.values()))
            quality=base_quality and spread<=.20
            if name.startswith('leak'):
                rows=full['ports']['port_'+name[-1]];v=np.array([r['power_w'] for r in rows])
                plane_spread=float(np.ptp(v)/estimate);uncertainty=max(uncertainty,plane_spread)
                profile=max((r[k] if r[k] is not None else 1.) for r in rows for k in ('E_profile_error','H_profile_error'))
                uncertainty=max(uncertainty,profile)
                quality=quality and plane_spread<=.20 and profile<=.20 and all(x>0 for x in v)
            if not quality:uncertainty=max(uncertainty,1.)
            obs[name]=Observation(estimate,uncertainty,max(0.,estimate*(1-uncertainty)),estimate*(1+uncertainty) if quality else None,quality)
    audit=dict(windows=windows,failures=errors,assumptions='same isolated mode; native E/H time staggering; peak 500 kV CW beta=1',
               uncertainty='20% floor plus measured sensitivity; not calibrated bounds',Qe_computed=False)
    return obs,audit

def analyze(config: Config,directory: Path,out: Path,stage: str,parameters: dict,axis_directory: Path|None=None) -> dict:
    """Preserve all fitted curves and rejected explanations, plus separate scalars."""
    out.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    metadata=recover_lines(directory);raw=np.load(directory/'wake.npz')
    raw_manifest=directory/'raw_manifest.json'
    if raw_manifest.exists():validate_manifest(directory,json.loads(raw_manifest.read_text()))
    else:
        files=[directory/name for name in ('run.json','field_complete.json','Ez_lines.h5','wake.npz','port_traces.h5','port_planes.json')]
        if stage=='axis':files.append(directory/'thermal_traces.h5')
        atomic_json(raw_manifest,manifest(directory,files))
    observations={}
    if stage=='axis':
        s=raw['s_m'];w=raw['longitudinal_V_per_pC'];direction='longitudinal';threshold=config.physics.longitudinal_limit
        try:
            powers,power_audit=heating_and_leakage(directory,config,parameters);observations.update(powers)
            atomic_json(out/'power_analysis.json',power_audit)
        except (ValueError,RuntimeError,np.linalg.LinAlgError,OSError) as exc:
            atomic_json(out/'power_analysis.json',dict(status='unresolved',error=str(exc)))
    else:
        if axis_directory is None:raise ValueError('X analysis requires same-geometry axis evidence')
        a_meta=recover_lines(axis_directory);a_raw=np.load(axis_directory/'wake.npz')
        a=dict(a_meta,s_m=a_raw['s_m'],transverse_V_per_pC=a_raw['transverse_V_per_pC'])
        x=dict(metadata,s_m=raw['s_m'],transverse_V_per_pC=raw['transverse_V_per_pC'])
        s,w=source_difference(a,x);direction='transverse_x';threshold=config.physics.transverse_limit
    fit=reconstruct(s,w,config.physics,config.reconstruction,direction,threshold)
    atomic_json(out/'reconstruction.json',fit.summary());np.savez_compressed(out/'reconstruction.npz',**fit.arrays)
    obs=from_reconstruction(fit.summary())
    if obs:observations[direction]=obs
    result=dict(stage=stage,parameters=parameters,observations={k:v.as_dict() for k,v in observations.items()},
                raw_sha256=digest(directory/'wake.npz'),field_directory=str(directory),seconds=time.perf_counter()-start,
                reconstruction_status=fit.status)
    atomic_json(out/'result.json',result)
    files=[p for p in out.iterdir() if p.is_file() and p.name!='manifest.json']
    atomic_json(out/'manifest.json',manifest(out,files));return result
