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
import logging
import numpy as np
from scipy.optimize import least_squares, lsq_linear
from scipy.signal import find_peaks, windows
from .config import Physics, Reconstruction

C = 299792458.
LOG=logging.getLogger(__name__)


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
    trig=np.sin(phase) if direction.startswith('transverse') else -(np.cos(phase)-np.sin(phase)/np.sqrt(4*q*q-1))
    return np.exp(-np.pi*f*t/q)*trig


def resonators(grid: np.ndarray,f: np.ndarray,q:np.ndarray,amplitudes:np.ndarray,
               sigma_m:float,direction:str) -> np.ndarray:
    """Complex Ω or Ω/m from WF2 amplitude normalization, with signed residues."""
    rq=amplitudes*1e12/(form_factor(f,sigma_m)[:,None]*2*np.pi*f[:,None])
    factor=1/(1-1j*q[None,:]*(f[None,:]/grid[:,None]-grid[:,None]/f[None,:]))
    if direction.startswith('transverse'):factor*=f[None,:]/grid[:,None]
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


def seed_spectrum(s: np.ndarray,wake: np.ndarray,grid: np.ndarray,sigma_m: float,direction: str) -> np.ndarray:
    """Suppress finite-tail sidelobes only when locating initial pole frequencies.

    Four-term Blackman-Harris taper; s is metres, f Hz, wake V/pC or V/pC/m.
    This tapered spectrum is NEVER a reported impedance or threshold bound.
    Fits still use untapered signed wakes; direct evidence remains untapered.
    Closely spaced poles unresolved by this seed must pass the original residual,
    correlation and multi-fit stability tests; a seed is not mode identification.
    """
    w=np.asarray(wake).reshape(len(s),-1)
    return direct_spectrum(s,w*windows.blackmanharris(len(s))[:,None],grid,sigma_m,direction)


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
    """Preserve all measured samples and complete only the missing tail (SI units)."""
    from .tail_ensemble import reconstruct_measured
    return reconstruct_measured(s,wake,physics,settings,direction,threshold)


def read_bundle(path:Path)->dict:
    """Read numeric NPZ only; never deserialize object arrays."""
    import json
    meta=json.loads((path/'bundle.json').read_text(encoding='utf-8'))
    with np.load(path/'curves.npz',allow_pickle=False) as data:meta.update({k:data[k] for k in data.files})
    return meta
