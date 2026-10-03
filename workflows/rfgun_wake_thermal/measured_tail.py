"""Measured wake plus missing tail, migrated from the September 25 validation.

Sources: analysis_sigma50/analyze_four.py (fit/predict/tail/raw_uniform) and
QuickCal_sigma70_20260925/quickcal.py (matrix pencil). See RECONSTRUCTION.md.
No old geometry's frequencies or bunch length are carried over. Frequencies
are Hz externally, MHz inside the nonlinear fit; distance m, decay 1/m,
wake V/pC or V/pC/m. The transverse Fourier convention is +i FT, axial -FT.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.linalg import hankel, svd, eigvals, qr, solve_triangular
from scipy.optimize import least_squares
from scipy.signal import czt

C = 299792458.
VERSION = 'measured-tail-joint-v1'


def raw_transform(s: np.ndarray, wake: np.ndarray, frequency: np.ndarray,
                  sigma_m: float, direction: str) -> np.ndarray:
    """Full measured trapezoidal FT; CZT only when both grids are uniform.

    No decimation of the charge head or replacement by a fitted time trace.
    Output complex ohm / ohm per metre, including Gaussian deconvolution.
    """
    s=np.asarray(s);f=np.asarray(frequency);w=np.asarray(wake).reshape(len(s),-1)
    ds=(s[-1]-s[0])/(len(s)-1)
    if len(f)>1 and np.allclose(s,np.linspace(s[0],s[-1],len(s)),rtol=0,atol=ds*1e-5) and np.allclose(np.diff(f),f[1]-f[0],rtol=1e-8,atol=1e-5):
        v=w.copy();v[[0,-1]]*=.5
        z=czt(v,m=len(f),w=np.exp(-2j*np.pi*(f[1]-f[0])*ds/C),
              a=np.exp(2j*np.pi*f[0]*ds/C),axis=0)*ds
        z*=np.exp(-2j*np.pi*f*s[0]/C)[:,None]
    else:
        weights=np.r_[np.diff(s)[0],s[2:]-s[:-2],np.diff(s)[-1]]/2
        z=np.concatenate([np.exp(-2j*np.pi*part[:,None]*s[None,:]/C)@(w*weights[:,None])
                          for part in np.array_split(f,max(1,int(np.ceil(len(f)/64))))])
    return z*(1e12/C)*(-1 if direction=='longitudinal' else 1j)/np.exp(-.5*(2*np.pi*f*sigma_m/C)**2)[:,None]


def pencil_seeds(s: np.ndarray, wake: np.ndarray, ranks: tuple[int,...],
                 band_hz: tuple[float,float], decay_bounds: tuple[float,float],
                 spacing_m: float=.02, rows: int=500) -> list[tuple[np.ndarray,np.ndarray]]:
    """Shared temporal subspace from concatenated signed-channel Hankel blocks.

    No channel-wise amplitude normalization: preserve small cross components
    without giving numerical noise in a vanishing component unit weight.
    """
    step=max(1,round(spacing_m/np.median(np.diff(s))))
    ss=s[::step];w=np.asarray(wake).reshape(len(s),-1)[::step]
    nr=min(rows,len(ss)//2)
    h=np.concatenate([hankel(w[:nr,j],w[nr-1:,j]) for j in range(w.shape[1])],axis=1)
    u,values,_=svd(h,full_matrices=False,check_finite=False)
    numerical_rank=int(np.sum(values>max(values[0]*1e-10,1e-30)))
    out=[]
    for rank in ranks:
        r=min(rank,numerical_rank,nr-1)
        if r<2:out.append((np.array([]),np.array([])));continue
        a=u[:,:r];p=eigvals(np.linalg.lstsq(a[:-1],a[1:],rcond=1e-12)[0])
        logs=np.log(p.astype(complex))/(ss[1]-ss[0]);f=logs.imag*C/(2*np.pi);alpha=-logs.real
        take=(f>band_hz[0])&(f<band_hz[1])&(alpha>decay_bounds[0])&(alpha<decay_bounds[1])
        order=np.argsort(f[take]);out.append((f[take][order],alpha[take][order]))
    return out


class ProjectedResidual:
    """Joint free-phase variable projection with the full analytic Jacobian.

    Linear cos/sin coefficients have signed wake units and are anchored at the
    first observed fit sample. The DC nuisance term is NOT extended to infinity.
    """
    def __init__(self,s:np.ndarray,wake:np.ndarray):
        self.s=np.asarray(s);self.y=np.asarray(wake).reshape(len(s),-1)
        self.start=float(s[0]);self.mid=float((s[0]+s[-1])/2);self.cached={}

    def calculate(self,p:np.ndarray)->dict:
        if 'p' in self.cached and np.array_equal(self.cached['p'],p):return self.cached
        n=len(p)//2;u=self.s-self.mid;v=self.s-self.start;k=2*np.pi*1e6/C
        e=np.exp(-v[:,None]*p[n:]);phase=u[:,None]*k*p[:n]
        xc=e*np.cos(phase);xs=e*np.sin(phase)
        x=np.column_stack((xc,xs,np.ones(len(u))))
        q,r=qr(x,mode='economic',check_finite=False)
        if np.min(abs(np.diag(r)))<np.max(abs(np.diag(r)))*1e-12:
            raise np.linalg.LinAlgError('Indistinguishable fit columns')
        co=solve_triangular(r,q.T@self.y,check_finite=False);res=x@co-self.y
        jac=[]
        for ch in range(self.y.shape[1]):
            d=np.column_stack(((-xs*co[:n,ch]+xc*co[n:2*n,ch])*u[:,None]*k,
                               -(xc*co[:n,ch]+xs*co[n:2*n,ch])*v[:,None]))
            e2=np.zeros((2*n+1,2*n));j=np.arange(n)
            e2[j,j]=(-xs*u[:,None]*k).T@res[:,ch]
            e2[n+j,j]=(xc*u[:,None]*k).T@res[:,ch]
            e2[j,n+j]=(-xc*v[:,None]).T@res[:,ch]
            e2[n+j,n+j]=(-xs*v[:,None]).T@res[:,ch]
            jac.append(d-q@(q.T@d)-q@solve_triangular(r.T,e2,lower=True,check_finite=False))
        self.cached=dict(p=p.copy(),coeff=co,residual=res,jacobian=np.stack(jac,axis=1).reshape(-1,2*n))
        return self.cached


@dataclass
class TailFit:
    """One common-pole explanation; no claim of unique electromagnetic modes."""
    frequency_hz:np.ndarray
    alpha:np.ndarray
    coeff:np.ndarray
    start_m:float
    mid_m:float
    boundary:np.ndarray
    success:bool
    error:float
    correlation:float

    def predict(self,s:np.ndarray)->np.ndarray:
        phase=(s-self.mid_m)[:,None]*2*np.pi*self.frequency_hz/C
        e=np.exp(-(s-self.start_m)[:,None]*self.alpha)
        return np.column_stack((e*np.cos(phase),e*np.sin(phase),np.ones(len(s))))@self.coeff

    def tail(self,length_m:float,f:np.ndarray,sigma_m:float,direction:str,
             indices:np.ndarray|None=None)->np.ndarray:
        """Integral ONLY from measured endpoint L to infinity, stable at large decay."""
        n=len(self.alpha);indices=np.arange(n) if indices is None else np.asarray(indices)
        kf=2*np.pi*np.asarray(f)/C;out=np.zeros((len(f),self.coeff.shape[1]),complex)
        for j in indices:
            a=self.alpha[j];k=2*np.pi*self.frequency_hz[j]/C
            at_l=(self.coeff[j]-1j*self.coeff[n+j])*np.exp(-a*(length_m-self.start_m)+1j*k*(length_m-self.mid_m))
            out+=.5*np.exp(-1j*kf*length_m)[:,None]*(at_l/(a+1j*(kf-k))[:,None]+at_l.conj()/(a+1j*(kf+k))[:,None])
        return out*(1e12/C)*(-1 if direction=='longitudinal' else 1j)/np.exp(-.5*(kf*sigma_m)**2)[:,None]


def fit_tail(s:np.ndarray,wake:np.ndarray,centers_hz:np.ndarray,alpha:np.ndarray,
             width_hz:float,decay_bounds:tuple[float,float],max_nfev:int)->TailFit:
    """Fit observed data with signed cos/sin coefficients, shared poles in all channels."""
    centers=np.asarray(centers_hz)/1e6;n=len(centers);model=ProjectedResidual(s,wake)
    if not n:raise ValueError('No resolvable poles')
    lo=np.r_[centers-width_hz/1e6,np.full(n,decay_bounds[0])]
    hi=np.r_[centers+width_hz/1e6,np.full(n,decay_bounds[1])]
    opt=least_squares(lambda p:model.calculate(p)['residual'].ravel(),np.clip(np.r_[centers,alpha],lo+1e-10,hi-1e-10),
        jac=lambda p:model.calculate(p)['jacobian'],bounds=(lo,hi),x_scale=np.r_[np.ones(n),np.full(n,.02)],
        max_nfev=max_nfev,ftol=1e-10,xtol=1e-10,gtol=1e-11)
    co=model.calculate(opt.x)['coeff'];res=model.calculate(opt.x)['residual'];y=model.y;pred=y+res
    yc=y-y.mean(axis=0);pc=pred-pred.mean(axis=0)
    error=float(np.linalg.norm(res)/max(np.linalg.norm(y),1e-30))
    corr=float(np.sum(yc*pc)/max(np.linalg.norm(yc)*np.linalg.norm(pc),1e-30))
    boundary=(abs(opt.x[:n]-centers)>.995*width_hz/1e6)|(opt.x[n:]<=decay_bounds[0]*1.01)|(opt.x[n:]>=decay_bounds[1]*.9975)
    return TailFit(opt.x[:n]*1e6,opt.x[n:],co,model.start,model.mid,boundary,bool(opt.success),error,corr)
