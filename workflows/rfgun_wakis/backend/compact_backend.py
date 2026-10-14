"""Algebraically compact FIT tail evolution, retaining the entire vacuum domain.

SI units and original FP32 coefficients/time step are retained. Active sets
are the union of every row/column touched by curl, wall trace, CPML, source,
absorber, diagnostics and nonzero initial fields. Only uncoupled zero DOFs
are omitted; no spatial radius cut, mesh coarsening or new boundary is used.
Native TF/SF injection is completed on the full layout before switching.
"""
from __future__ import annotations
import time
import numpy as np
import cupy as cp
from cupyx.scipy.sparse import csr_matrix
from .optimized_backend import FullEngine,RECURRENCE

class CompactEngine(FullEngine):
    """Keep E/H on reduced algebraic index sets after native injection finishes."""
    def __init__(self,*args):
        super().__init__(*args)
        self.active=False

    def activate(self):
        """Prove coupling closure before constructing reduced CSR matrices."""
        assert not self.active
        s=self.solver;c=self.copper
        assert s.injection_done and not s.use_conductivity and not s.step_0
        start=time.perf_counter()
        hc,ec=s.tDsiDmuiDaC,s.itDaiDepsDstC
        mats={name:mat.get().tocsr() for name,mat in dict(A=hc.base,B=ec.base,
            DH=hc.D,DE=ec.D,T=c.T,W=c.back,ME=self.monitor.E,MH=self.monitor.H).items()}
        for mat in mats.values():mat.eliminate_zeros();mat.sort_indices()
        n=3*s.N
        e=np.zeros(n,dtype=bool);h=e.copy()
        def rows(mask,mat):mask[np.flatnonzero(np.diff(mat.indptr))]=True
        def cols(mask,mat):mask[mat.indices]=True
        rows(h,mats['A']);cols(e,mats['A'])
        rows(e,mats['B']);cols(h,mats['B'])
        cols(e,mats['DH']);cols(h,mats['DE'])
        cols(h,mats['T']);rows(h,mats['W'])
        cols(e,mats['ME']);cols(h,mats['MH'])
        e[cp.asnumpy(ec.rows)]=True;h[cp.asnumpy(hc.rows)]=True
        e[cp.asnumpy(self.line)]=True
        for key,mask in [('E',e),('H',h)]:
            mask[cp.asnumpy(self.absorber.data[key][0])]=True
        e[cp.asnumpy(cp.flatnonzero(s.E.array))]=True
        h[cp.asnumpy(cp.flatnonzero(s.H.array))]=True
        e[cp.asnumpy(cp.flatnonzero(s.J.array))]=True
        # Include every source-line cell even when its instantaneous J is zero.
        beam=self.beam
        source_ids=2*s.N+beam.ixs+beam.iys*s.Nx+np.arange(beam.j_start,beam.j_stop)*s.Nx*s.Ny
        e[source_ids]=True
        ei,hi=np.flatnonzero(e),np.flatnonzero(h)
        emap=np.full(n,-1,dtype='i4');hmap=emap.copy()
        emap[ei]=np.arange(len(ei),dtype='i4');hmap[hi]=np.arange(len(hi),dtype='i4')
        def map_indices(mapping,index):
            result=mapping[cp.asnumpy(index)]
            assert np.all(result>=0)
            return cp.asarray(result,dtype='i4')
        reduced=dict(A=mats['A'][hi][:,ei],B=mats['B'][ei][:,hi],
            DH=mats['DH'][:,ei],DE=mats['DE'][:,hi],T=mats['T'][:,hi],
            W=mats['W'][hi],ME=mats['ME'][:,ei],MH=mats['MH'][:,hi])
        assert all(reduced[k].nnz==mats[k].nnz for k in mats), 'Nonzero coupling lost'
        self.ei=cp.asarray(ei,dtype='i4');self.hi=cp.asarray(hi,dtype='i4')
        self.E=s.E.array[self.ei].copy();self.H=s.H.array[self.hi].copy()
        # Omitted field values must be exactly zero, not merely small.
        assert int(cp.count_nonzero(s.E.array))==int(cp.count_nonzero(self.E))
        assert int(cp.count_nonzero(s.H.array))==int(cp.count_nonzero(self.H))
        self.ieps=s.ieps.array[self.ei]
        self.m={k:csr_matrix(v) for k,v in reduced.items()}
        self.scaled_A=s.dt*self.m['A']
        self.hr=map_indices(hmap,hc.rows);self.er=map_indices(emap,ec.rows)
        self.hpsi=hc.psi.copy();self.epsi=ec.psi.copy()
        self.ha=hc.a;self.hb=hc.b;self.ea=ec.a;self.eb=ec.b
        self.line_compact=map_indices(emap,self.line)
        self.layers={k:(map_indices(emap if k=='E' else hmap,index),factor)
            for k,(index,factor) in self.absorber.data.items()}
        cp.cuda.Stream.null.synchronize()
        self.active=True
        self.compaction_audit=dict(method='exact nonzero coupling closure; full-domain tail',
            E_full=n,H_full=n,E_active=len(ei),H_active=len(hi),
            E_fraction=len(ei)/n,H_fraction=len(hi)/n,
            matrix_nonzeros={k:dict(before=int(mats[k].nnz),after=int(reduced[k].nnz)) for k in mats},
            omitted_fields_exact_zero=True,all_nonzero_couplings_retained=True,
            activation_seconds=time.perf_counter()-start,
            retained_full_source_J=True,native_injection_finished=True,
            full_shadow_retained_for_diagnostics=True,memory_saving_not_claimed=True,
            input_field_bytes=int(2*n*4),active_field_bytes=int((len(ei)+len(hi))*4))
        from ..io import atomic_json as save_json
        save_json(self.out/'compaction.json',self.compaction_audit)

    def update_source(self,step:int):
        # Geometry-specific dt changes the injection duration. Preserve the
        # source's own completion condition, not the old pilot step number.
        if not self.active and self.solver.injection_done and not self.solver.step_0:self.activate()
        super().update_source(step)

    def record(self,step:int):
        if not self.active:return super().record(step)
        m=self.monitor
        if step%m.stride==0:
            m.data[m.count]=self.m['ME']@self.E+self.m['MH']@self.H
            m.count+=1
        self.buffer[step%256]=self.E[self.line_compact]

    def half_step(self):
        for key,(index,factor) in self.layers.items():getattr(self,key)[index]*=factor

    def step(self):
        if not self.active:return super().step()
        s=self.solver;c=self.copper
        self.half_step()
        dh=self.scaled_A@self.E
        self.hpsi=self.hb*self.hpsi+self.ha*(self.m['DH']@self.E)
        dh[self.hr]+=s.dt*self.hpsi
        self.H=self.H-dh
        de=self.m['B']@self.H
        self.epsi=self.eb*self.epsi+self.ea*(self.m['DE']@self.H)
        de[self.er]+=self.epsi
        self.E=self.E+s.dt*(de-self.ieps*s.J.array[self.ei])
        value=self.m['T']@self.H
        RECURRENCE(c.alpha,c.beta,(value-c.old)[None,:],c.state)
        c.old=value
        electric=c.R@c.state
        self.H-=s.dt*(self.m['W']@electric)
        self.half_step()

    def max_e(self):
        if not self.active:return super().max_e()
        return float(cp.max(cp.abs(self.E)))
