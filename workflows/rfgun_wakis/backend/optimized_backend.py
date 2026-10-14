"""Verified caching/fusion mechanisms applied to candidate-specific FIT tensors.

All quantities use SI: E V/m, H A/m, time s, wall conductivity S/m.
Caching and fusion retain the accepted discretization. Reducing the number
of positive copper poles changes the constitutive approximation and needs
independent comparison. No changes to native Wakis or accepted scripts.
"""
from __future__ import annotations
import types
import numpy as np
import cupy as cp
from .copper_impedance import CopperSurfaceImpedance

RECURRENCE=cp.ElementwiseKernel('float32 a, float32 b, float32 delta',
    'float32 state','state = a * state + b * delta;',
    'wf61_copper_recurrence_no_fma',options=('--fmad=false',))

def install_fusion(solver, copper, terms:int=96) -> dict:
    """Cache dt*curl_H and fuse copper state update without FMA contraction."""
    assert solver.dtype==np.float32 and terms in (48,96)
    assert float(cp.max(cp.abs(copper.state)))==0., 'Install before any field evolution'
    if terms!=96:
        law=CopperSurfaceImpedance(terms=terms)
        a,b,R=law.recurrence(float(solver.dt))
        copper.alpha=cp.asarray(a.astype('f4')[:,None]);copper.beta=cp.asarray(b.astype('f4')[:,None])
        copper.R=cp.asarray(R.astype('f4'))
        copper.state=cp.zeros((terms,copper.old.size),dtype='f4')
        oldlaw=CopperSurfaceImpedance();_,ob,orr=oldlaw.recurrence(float(solver.dt))
        bound=copper.audit['explicit_coupling_bound']*float(np.dot(R,b)/np.dot(orr,ob))
        assert bound<.5
    else:bound=copper.audit['explicit_coupling_bound']
    hc=solver.tDsiDmuiDaC
    scaled=solver.dt*hc.base
    def apply(self,value,scale=None):
        if scale is not None:assert scale==solver.dt
        full=self.base*value if scale is None else scaled*value
        self.psi=self.b*self.psi+self.a*(self.D@value)
        full[self.rows]+=self.psi if scale is None else scale*self.psi
        return full
    hc.apply=types.MethodType(apply,hc)
    def step(self):
        value=self.T@self.solver.H.array
        RECURRENCE(self.alpha,self.beta,(value-self.old)[None,:],self.state)
        self.old=value
        electric=self.R@self.state
        self.solver.H.array-=self.solver.dt*(self.back@electric)
    copper.step=types.MethodType(step,copper)
    return dict(cached_H_curl=True,fused_copper_recurrence=True,fmad=False,
        copper_terms=terms,explicit_coupling_bound=bound,
        copper_state_bytes=int(copper.state.nbytes),native_source_unchanged=True)

class FullEngine:
    """Accepted update ordering with the optional cache/recurrence optimization."""
    def __init__(self,solver,copper,absorber,beam,monitor,line,buffer,out):
        self.solver=solver;self.copper=copper;self.absorber=absorber
        self.beam=beam;self.monitor=monitor;self.line=line;self.buffer=buffer;self.out=out
    def update_source(self,step:int):self.beam.update(self.solver,step*self.solver.dt)
    def record(self,step:int):
        self.monitor.record(step)
        self.buffer[step%256]=self.solver.E.array[self.line]
    def step(self):
        self.absorber.half_step();self.solver.one_step();self.copper.step();self.absorber.half_step()
    def max_e(self):return float(cp.max(cp.abs(self.solver.E.array)))
