"""Conservative candidate-specific CFL bound for lossless FIT leapfrog."""
from __future__ import annotations
import numpy as np

def choose_timestep(metrics: dict,safety: float=.90) -> tuple[float,dict]:
    """Bound sigma_max(S) with sqrt(||S||_1 ||S||_inf), S=sqrt(Mh)C sqrt(Me).

Me=ds/(epsilon0*dad), Mh=dsd/(mu0*dA); SI units give S in 1/s.
The exact incidence stencil matches Wakis' flattened forward differences.
Boundary deletion cannot increase this absolute-entry bound. This proves a
lossless leapfrog CFL margin; CPML/SIBC still have separate live guards.
"""
    if not 0<safety<1:raise ValueError('CFL safety must be below one')
    me=np.sqrt(np.asarray(metrics['Eps'],dtype='f8'))
    mh=np.sqrt(np.asarray(metrics['Mue'],dtype='f8'))
    shape=[len(metrics[k]) for k in 'xyz'];n=int(np.prod(shape))
    if me.shape!=(3,n) or mh.shape!=me.shape:raise ValueError('Tensor shape mismatch')
    rs=np.zeros_like(me);cs=np.zeros_like(me)
    for out,inp,d in ((0,1,2),(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)):
        stride=(1,shape[0],shape[0]*shape[1])[d]
        a=mh[out]*me[inp];rs[out]+=a;cs[inp]+=a
        a=mh[out,:-stride]*me[inp,stride:]
        rs[out,:-stride]+=a;cs[inp,stride:]+=a
    bound=float(np.sqrt(rs.max()*cs.max()))
    if not np.isfinite(bound) or bound<=0:raise ValueError('Invalid operator bound')
    dt=2*safety/bound
    return dt,dict(dt_s=dt,safety=safety,singular_value_upper_bound_per_s=bound,
                   method='absolute 1/infinity norms of energy-scaled incidence curl')
