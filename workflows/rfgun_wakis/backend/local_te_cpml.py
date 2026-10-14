"""Port-local normal-derivative CPML on the saved FIT mesh (SI units).

Only TE port apertures are stretched; TEM ports retain their old sponge.
kappa=1, complex frequency shift=0; alpha [1/s] follows the old 20 mm
quadratic profile. For each NORMAL curl contribution D, psi=b*psi+(b-1)*D,
b=exp(-alpha*dt); use D+psi. This is the kappa=1, unshifted specialization
of Wakis' convolutional derivative update, applied to internal apertures.
Whole FIT coefficients, source injection and copper correction are retained.
This experimental implementation requires measured reflection validation.
"""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from .staggered_ports import build_rates

class ConvolutionalCurl:
    """Wrap a native GPU CSR curl with local normal-derivative memories."""
    def __init__(self,base,rows,normal_components,alpha,dt,N):
        import cupy as cp
        from cupyx.scipy.sparse import csr_matrix
        self.base=base;self.rows=cp.asarray(rows,dtype=cp.int32)
        # Off-diagonal curl block fixes the derivative direction uniquely:
        # output component r, normal d -> input component 3-r-d.
        selected=base[self.rows,:].get().tocoo()
        keep=(selected.col//N)==normal_components[selected.row]
        sparse=sp.csr_matrix((selected.data[keep],(selected.row[keep],selected.col[keep])),shape=selected.shape)
        assert sparse.nnz>0 and np.all(np.isfinite(sparse.data))
        self.D=csr_matrix(sparse)
        # Keep the accepted zero-shift constitutive law. New cut-cell aperture
        # support is handled by the spatial stencil halo below, not by fitting
        # extra loss to the cavity response.
        shift=0.
        self.b=cp.asarray(np.exp(-(alpha+shift)*dt).astype('f4'))
        self.a=cp.asarray((alpha/(alpha+shift)*np.expm1(-(alpha+shift)*dt)).astype('f4'))
        self.psi=cp.zeros(len(rows),dtype=cp.float32)
        self.audit=dict(rows=len(rows),normal_derivative_nonzeros=sparse.nnz,max_alpha_per_s=float(alpha.max()),frequency_shift_per_s=shift)
    def __mul__(self,value):
        return self.apply(value)
    def __rmul__(self,scale):
        # Native H update evaluates (dt * curl) * E, while the E update
        # evaluates dt * (curl * H). Preserve both expression orders.
        if not np.isscalar(scale):return NotImplemented
        return ScaledCurl(self,scale)
    def apply(self,value,scale=None):
        full=self.base*value if scale is None else (scale*self.base)*value
        self.psi=self.b*self.psi+self.a*(self.D@value)
        full[self.rows]+=self.psi if scale is None else scale*self.psi
        return full

class ScaledCurl:
    """Scalar-prefixed native sparse update; one memory update per step."""
    def __init__(self,curl,scale):self.curl=curl;self.scale=scale
    def __mul__(self,value):return self.curl.apply(value,self.scale)

def attach(solver,metrics,faces,strength=10.):
    """Attach only TE tangential curl memories, with no global API changes."""
    te=[f for f in faces if f['name'] not in ('port_2','port_3')]
    audit={};N=solver.N
    for field,attr in [('H','tDsiDmuiDaC'),('E','itDaiDepsDstC')]:
        ids=[];alphas=[];inputs=[]
        for face in te:
            # Port 1 has the coarsest normal spacing and lower cutoff.
            # Reduced-mode reflection preflight selects 6 there, 10 at
            # ports 4/5/6; these values are not fitted to the cavity wake.
            local_strength=min(6.,strength) if face['name']=='port_1' else strength
            rates,_=build_rates(metrics,[face],strength=local_strength,aperture_halo_cells=1)
            rows,alpha=rates[field];comp=rows//N;keep=(comp!=face['axis'])&(alpha>0)
            rows,alpha,comp=rows[keep],alpha[keep],comp[keep]
            ids.extend(rows);alphas.extend(alpha);inputs.extend(3-comp-face['axis'])
        ids=np.asarray(ids,dtype=np.int64);assert len(ids)==len(np.unique(ids))
        wrapper=ConvolutionalCurl(getattr(solver,attr),ids,np.asarray(inputs),np.asarray(alphas),float(solver.dt),N)
        setattr(solver,attr,wrapper);audit[field]=wrapper.audit
    return dict(method='normal derivative convolution; kappa=1; cut-cell aperture stencil halo',strength=strength,
                aperture_halo_cells=1,
                port_strengths={f['name']:min(6.,strength) if f['name']=='port_1' else strength for f in te},
                layer_m=.02,ports=[f['name'] for f in te],operators=audit)
