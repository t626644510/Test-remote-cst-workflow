"""Fixed-tail shared-pole wake inversion and honest ensemble diagnostics.

Resonator conventions are migrated from WF2 pso_wake_fit.py at 6a6c99d,
functions wake_from_parameters, resonator_sum and amplitude-to-R/Q conversion.
Input wake units V/pC (longitudinal), V/pC/m (transverse); s in m, f in Hz.
The fitted resonators are one ensemble-compatible explanation, not a unique
physical modal decomposition. No CST APIs are imported by this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares, lsq_linear
from scipy.signal import find_peaks
from .config import Physics, Reconstruction

C = 299792458.


def transverse_norm(z: np.ndarray) -> np.ndarray:
    """Maximum ||Z u|| for real unit u; Z[..., output, input] is complex Ω/m."""
    z=np.asarray(z,complex)
    if z.shape[-2:]!=(2,2) or not np.isfinite(z).all():raise ValueError('Finite 2x2 matrix required')
    gram=np.einsum('...ki,...kj->...ij',z.conj(),z).real
    return np.sqrt(np.maximum(0,np.linalg.eigvalsh(gram)[...,-1]))


def align_transverse(axis: dict, x: dict, y: dict, offset_m: float) -> tuple[np.ndarray,np.ndarray]:
    """Forward source-offset differences at a common on-axis witness; no extrapolation."""
    if not offset_m>0:raise ValueError('Positive offset in metres required')
    curves=[d for d in (axis,x,y)]
    if len({tuple(d['ports']) for d in curves})!=1:raise ValueError('Different port geometries cannot be subtracted')
    for d in curves:
        s=np.asarray(d['s_m'])
        if len(s)<8 or not np.isfinite(s).all() or np.any(np.diff(s)<=0):raise ValueError('Invalid wake coordinates')
        if np.asarray(d['wake']).shape!=(len(s),3):raise ValueError('Missing signed XYZ wakes')
    lo=max(d['s_m'][0] for d in curves);hi=min(d['s_m'][-1] for d in curves)
    s=np.asarray(axis['s_m']);s=s[(s>=lo)&(s<=hi)]
    if len(s)<8:raise ValueError('Insufficient common wake interval')
    ref=np.column_stack([np.interp(s,axis['s_m'],axis['wake'][:,i]) for i in range(2)])
    k=np.empty((len(s),2,2))
    for j,d in enumerate((x,y)):
        k[:,:,j]=(np.column_stack([np.interp(s,d['s_m'],d['wake'][:,i]) for i in range(2)])-ref)/offset_m
    if not np.isfinite(k).all():raise ValueError('Invalid transverse differences')
    return s,k


def form_factor(f: np.ndarray,sigma_m:float) -> np.ndarray:
    """Gaussian bunch Fourier amplitude, normalized to unity at DC (beta=1)."""
    return np.exp(-.5*(2*np.pi*np.asarray(f)*sigma_m/C)**2)


def basis(s: np.ndarray,f: np.ndarray,q: np.ndarray,direction:str) -> np.ndarray:
    """WF2 damped resonator wake basis; amplitudes retain input wake units."""
    t=np.asarray(s)[:,None]/C;f=np.asarray(f)[None,:];q=np.asarray(q)[None,:]
    phase=2*np.pi*f*np.sqrt(1-1/(4*q*q))*t
    trig=np.sin(phase) if direction=='transverse' else -(np.cos(phase)-np.sin(phase)/np.sqrt(4*q*q-1))
    return np.exp(-np.pi*f*t/q)*trig


def resonators(grid: np.ndarray,f: np.ndarray,q:np.ndarray,amplitudes:np.ndarray,
               sigma_m:float,direction:str) -> np.ndarray:
    """Complex Ω or Ω/m from WF2 amplitude normalization, with signed residues."""
    rq=amplitudes*1e12/(form_factor(f,sigma_m)[:,None]*2*np.pi*f[:,None])
    factor=1/(1-1j*q[None,:]*(f[None,:]/grid[:,None]-grid[:,None]/f[None,:]))
    if direction=='transverse':factor*=f[None,:]/grid[:,None]
    return factor @ (q[:,None]*rq)


def direct_spectrum(s:np.ndarray,wake:np.ndarray,grid:np.ndarray,sigma_m:float,direction:str) -> np.ndarray:
    """Finite-tail Fourier evidence, divided by Gaussian spectrum; no zero padding claim."""
    w=np.asarray(wake).reshape(len(s),-1);t=np.asarray(s)/C
    weights=np.empty(len(t));weights[0]=(t[1]-t[0])/2;weights[-1]=(t[-1]-t[-2])/2
    weights[1:-1]=(t[2:]-t[:-2])/2
    values=[]
    for fs in np.array_split(grid,max(1,int(np.ceil(len(grid)/128)))):
        values.append(np.exp(-2j*np.pi*fs[:,None]*t[None,:]) @ (w*weights[:,None]*1e12))
    z=np.concatenate(values)/form_factor(grid,sigma_m)[:,None]
    # WF2 Fourier convention: longitudinal -FT, transverse i*FT.
    return z*(-1 if direction=='longitudinal' else 1j)


@dataclass
class FitResult:
    """Reliable scalar observations or explicit uncertainty, never a fabricated zero."""
    status:str
    value:float|None
    reasons:list[str]
    diagnostics:dict
    arrays:dict[str,np.ndarray]

    def summary(self)->dict:
        return dict(status=self.status,value=self.value,reasons=self.reasons,diagnostics=self.diagnostics)


def reconstruct(s:np.ndarray,wake:np.ndarray,physics:Physics,settings:Reconstruction,
                direction:str,threshold:float) -> FitResult:
    """Joint variable-projection least squares with 3 starts and 2 fixed-tail windows.

    Shared f/Q poles fit all four signed transverse components together. Linear
    amplitudes are eliminated at every nonlinear step. Longitudinal amplitudes
    are nonnegative. Frequency windows are bounded by detected-peak midpoints.
    Only full-band, ensemble-stable, non-boundary fits can yield a GP observation.
    """
    s=np.asarray(s,float);w=np.asarray(wake,float).reshape(len(s),-1)
    expected=4 if direction=='transverse' else 1
    if w.shape[1]!=expected or len(s)<32 or not np.isfinite(w).all() or not np.isfinite(s).all() or np.any(np.diff(s)<=0):
        raise ValueError('Incomplete or nonfinite signed wake bundle')
    if s[-1]<physics.wake_length_m*.98:raise ValueError('Wake tail shorter than configured 35 m')
    if s[0]>-3*physics.sigma_m:raise ValueError('Wake origin/leading bunch missing')
    lo,hi=physics.band_hz
    if form_factor(np.array([hi]),physics.sigma_m)[0]<settings.min_bunch_spectrum:
        return FitResult('uncertain',None,['insufficient_bunch_spectrum'],{}, {})
    # Fit the working mode too; masking only applies to the objective.
    coarse=np.linspace(max(1e6,lo/10),hi,settings.spectrum_points)
    # Interpolate onto a bounded uniform grid for integration; preserve charge head.
    ss=np.linspace(s[0],s[-1],max(settings.fit_points,8192))
    ww=np.column_stack([np.interp(ss,s,w[:,i]) for i in range(expected)])
    z=direct_spectrum(ss,ww,coarse,physics.sigma_m,direction)
    score=transverse_norm(z.reshape(-1,2,2)) if expected==4 else abs(z[:,0])
    peaks,_=find_peaks(score,prominence=max(float(score.max())*settings.peak_prominence_fraction,1e-15),distance=2)
    reasons=[]
    if len(peaks)==0:return FitResult('uncertain',None,['no_resolvable_poles'],{}, {'frequency_hz':coarse,'direct':z})
    if len(peaks)>settings.max_modes:
        reasons.append('pole_capacity_exceeded')
        peaks=np.sort(peaks[np.argsort(score[peaks])[-settings.max_modes:]])
    centers=coarse[peaks];df=C/(s[-1]-s[0]);half=df*.65
    low=np.maximum(coarse[0],centers-half);high=np.minimum(hi,centers+half)
    if len(centers)>1:
        mid=(centers[1:]+centers[:-1])/2
        high[:-1]=np.minimum(high[:-1],mid);low[1:]=np.maximum(low[1:],mid)
    n=len(centers);qlo,qhi=settings.q_bounds;fits=[];fit_arrays={}
    for start in settings.starts_m:
        ts=np.linspace(start,s[-1],settings.fit_points)
        data=np.column_stack([np.interp(ts,s,w[:,i]) for i in range(expected)])
        # Global norm retains physically small cross components without dividing by zero.
        scale=max(float(np.linalg.norm(data)),1e-30)
        def decode(v):return low+(high-low)*v[:n],np.exp(v[n:])
        def linear(v):
            f,q=decode(v);a=basis(ts,f,q,direction)
            if expected==1:
                amp=lsq_linear(a,data[:,0],bounds=(0,np.inf),tol=1e-9).x[:,None]
            else:amp=np.linalg.lstsq(a,data,rcond=1e-10)[0]
            return a@amp,amp
        def residual(v):return ((linear(v)[0]-data)/scale).ravel()
        for seed in settings.seeds:
            rng=np.random.default_rng(seed)
            loglo,loghi=np.log(qlo),np.log(qhi)
            x0=np.r_[np.clip((centers-low)/(high-low)+rng.normal(0,.04,n),.01,.99),rng.uniform(loglo+.1*(loghi-loglo),loglo+.8*(loghi-loglo),n)]
            opt=least_squares(residual,x0,bounds=(np.r_[np.zeros(n),np.full(n,np.log(qlo))],np.r_[np.ones(n),np.full(n,np.log(qhi))]),max_nfev=settings.max_nfev,ftol=1e-8,xtol=1e-8,gtol=1e-8)
            f,q=decode(opt.x);prediction,amp=linear(opt.x)
            err=float(np.linalg.norm(prediction-data)/scale)
            a0=data.ravel()-data.mean();b0=prediction.ravel()-prediction.mean()
            correlation=float(np.dot(a0,b0)/max(np.linalg.norm(a0)*np.linalg.norm(b0),1e-30))
            # Include every pole centre and a linewidth-resolved local grid.
            grid=np.unique(np.concatenate([np.linspace(lo,hi,settings.spectrum_points)]+[np.clip(fi+np.linspace(-4,4,161)*fi/qi,lo,hi) for fi,qi in zip(f,q)]))
            rz=resonators(grid,f,q,amp,physics.sigma_m,direction)
            values=transverse_norm(rz.reshape(-1,2,2)) if expected==4 else abs(rz[:,0])
            peak=float(values.max())
            boundary=bool(np.any(q>qhi*.98) or np.any(q<qlo*1.02) or np.any(opt.x[:n]<.005) or np.any(opt.x[:n]>.995))
            columns=basis(ts,f,q,direction)
            normalized=columns/np.maximum(np.linalg.norm(columns,axis=0),1e-30)
            similarity=abs(normalized.T@normalized);np.fill_diagonal(similarity,0)
            inseparable=bool(np.any(similarity>.995))
            valid=bool(opt.success and err<=settings.max_error and correlation>=settings.min_correlation and not boundary and not inseparable)
            row=dict(start_m=start,seed=seed,error=err,correlation=correlation,boundary=boundary,inseparable_poles=inseparable,optimizer_success=bool(opt.success),valid=valid,peak=peak,frequency_hz=f.tolist(),q=q.tolist(),amplitudes=amp.tolist())
            fits.append(row);index=len(fits)-1
            fit_arrays.update({f'fit_{index}_s_m':ts,f'fit_{index}_wake':prediction,f'fit_{index}_frequency_hz':grid,f'fit_{index}_impedance':rz})
    valid=[x for x in fits if x['valid']]
    band=(coarse>=lo)&(coarse<=hi);direct_peak=float(score[band].max())
    if len(valid)!=len(fits):reasons.append('incomplete_or_unidentifiable_ensemble')
    spread=None
    if valid:
        peaks_v=[x['peak'] for x in valid];spread=(max(peaks_v)-min(peaks_v))/max(max(peaks_v),1e-30)
        if spread>settings.peak_spread:reasons.append('unstable_peak')
        if min(peaks_v)<=threshold<max(peaks_v):reasons.append('threshold_straddled')
    # Boundary rise means a peak could be clipped by the configured band.
    if score[-1]>score[-2] and score[-1]>.1*threshold:reasons.append('upper_band_edge_peak')
    edge=int(np.searchsorted(coarse,lo))
    if score[edge]>score[edge+1] and score[edge]>.1*threshold:reasons.append('lower_band_edge_peak')
    value=max(direct_peak,max(x['peak'] for x in valid)) if valid and not reasons else None
    return FitResult('valid' if value is not None else 'uncertain',value,reasons,
                     dict(fits=fits,direct_peak=direct_peak,peak_spread=spread,base_resolution_hz=df,
                          lower_evidence_exceeds=direct_peak>threshold,
                          identifiability='ensemble-compatible, not unique'),
                     dict(frequency_hz=coarse,direct=z,**fit_arrays))


def read_bundle(path:Path)->dict:
    """Read numeric NPZ only; never deserialize object arrays."""
    import json
    meta=json.loads((path/'bundle.json').read_text(encoding='utf-8'))
    with np.load(path/'curves.npz',allow_pickle=False) as data:meta.update({k:data[k] for k in data.files})
    return meta
