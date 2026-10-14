"""Axis longitudinal wake and on-axis PW response to a +2 mm X drive.

Wz is the signed integral Ez/q in V/pC. With distance s behind the bunch,
the same Wakis convention gives W_perp=-integral(gradient_witness Wz) ds.
Source differencing yields the X column [Zxx,Zyx] in ohm/m. It is not a full
2x2 transverse matrix, and missing Y excitation is never replaced by zero.
"""
from __future__ import annotations
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.constants import c

def integrate_line(ezt: np.ndarray,z: np.ndarray,dz: np.ndarray,dt: float,ti: float,q: float,length: float) -> tuple[np.ndarray,np.ndarray]:
    """Frozen Wakis integer-time retarded integral; metres, seconds, C, V/pC."""
    if dt<=0 or q==0 or not np.isfinite(ezt).all():raise ValueError('Invalid line trace')
    s=np.arange(-ti*c,length,dt*c);wake=np.zeros_like(s)
    for start in range(0,len(s),4096):
        ss=s[start:start+4096]
        ts=(z[None,:]+ss[:,None])/c-z.min()/c+ti
        it=np.trunc(ts/dt).astype(np.int64)
        valid=(it>=0)&(it<len(ezt))
        sample=ezt[np.clip(it,0,len(ezt)-1),np.arange(len(z))[None,:]]
        wake[start:start+len(ss)]=np.sum(np.where(valid,sample,0)*dz,axis=1)/(q*1e12)
    return s,wake

def pw_transverse(s: np.ndarray,witness_wakes: np.ndarray,positions_m: np.ndarray) -> np.ndarray:
    """Second-order centered witness derivatives followed by causal PW integration.

Expected line order: axis, x-minus, x-plus, y-minus, y-plus. Offsets can be
asymmetric; the three-point derivative is evaluated exactly at zero. Leading
integration constant is zero at the acquired pre-bunch start, as in Wakis.
"""
    s=np.asarray(s,float);w=np.asarray(witness_wakes,float);p=np.asarray(positions_m,float)
    if w.shape!=(len(s),5) or p.shape!=(5,2) or np.any(np.diff(s)<=0) or not np.isfinite(w).all():
        raise ValueError('Incomplete PW witness bundle')
    if not np.allclose(p[0],0,atol=1e-12,rtol=0):raise ValueError('Witness must be on axis')
    derivatives=[]
    for axis,minus,plus in ((0,1,2),(1,3,4)):
        a,b=p[minus,axis],p[plus,axis]
        if not a<0<b or abs(p[minus,1-axis])+abs(p[plus,1-axis])>1e-12:
            raise ValueError('Witness derivative is not centered on axis')
        coefficients=np.array([-b/(a*(a-b)), -(a+b)/(a*b), -a/(b*(b-a))])
        # Lagrange derivative order here is [minus,axis,plus].
        derivative=w[:,[minus,0,plus]]@coefficients
        derivatives.append(-cumulative_trapezoid(derivative,s,initial=0.))
    return np.column_stack(derivatives)

def source_difference(axis: dict,x: dict,offset_m: float=.002) -> tuple[np.ndarray,np.ndarray]:
    """Subtract only identical geometry/grid/excitation contracts; V/pC/m."""
    for name in ('geometry_sha256','metrics_sha256','solver_contract_sha256','dt_s','precision','cpml',
                 'sigma_m','wake_length_m','witness_positions_m'):
        if axis[name]!=x[name]:raise ValueError(f'Mismatched {name}')
    if axis['source_offset_m']!=[0.,0.] or x['source_offset_m']!=[offset_m,0.]:
        raise ValueError('Incorrect axis/X source offsets')
    s=np.asarray(axis['s_m']);sx=np.asarray(x['s_m'])
    if not np.array_equal(s,sx):raise ValueError('Identical time grid required for source difference')
    first=np.asarray(axis['transverse_V_per_pC']);second=np.asarray(x['transverse_V_per_pC'])
    if first.shape!=second.shape or first.shape!=(len(s),2):raise ValueError('Both signed transverse components required')
    return s,(second-first)/offset_m
