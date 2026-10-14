"""Local passive absorber sampled at each FIT E edge and H face.

Coordinates and layer thickness are metres. alpha [1/s] = 10*c/L*(1-d/L)^2.
E_d lies at the d-edge midpoint, H_d at its normal face centre. Positive
diagonal multipliers cannot increase energy for positive diagonal FIT masses.
This remains an approximate absorber, not a modal port or validated PML.
"""
from __future__ import annotations
from pathlib import Path
import json,sys
import numpy as np
from scipy.constants import c

def build_rates(metrics, faces, *, staggered=True, tolerance_m=1e-12, strength=10.,aperture_halo_cells=0):
    """Return sparse per-field damping rates and six-port sampling evidence."""
    assert np.isfinite(strength) and strength>0
    axes=[metrics[k] for k in 'xyz'];shape=tuple(map(len,axes));N=int(np.prod(shape))
    mids=[np.r_[.5*(a[:-1]+a[1:]),a[-1]+.5*(a[-1]-a[-2])] for a in axes]
    collected={k:[] for k in ('E','H')};rows=[]
    for face in faces:
        d,sign=face['axis'],face['sign'];position=face['low'][d];L=.02
        row=dict(name=face['name'],components={})
        for field in ('E','H'):
            for component in range(3):
                coordinates=[(mids[j] if (j==component)==(field=='E') else axes[j]) if staggered else axes[j] for j in range(3)]
                ids=[]
                for j in range(3):
                    if j==d:
                        dist=sign*(position-coordinates[j]);ids.append(np.flatnonzero((dist>=-tolerance_m)&(dist<=L+tolerance_m)))
                    else:
                        selected=np.flatnonzero((coordinates[j]>=face['low'][j]-tolerance_m)&(coordinates[j]<=face['high'][j]+tolerance_m))
                        # FIT cut edges can carry nonzero material support even
                        # when their nominal midpoint lies just beyond a CAD
                        # aperture. Include their adjoining stencil cells;
                        # the positive material metric still removes metal.
                        if len(selected) and aperture_halo_cells:
                            selected=np.arange(max(0,selected[0]-aperture_halo_cells),min(shape[j],selected[-1]+aperture_halo_cells+1))
                        ids.append(selected)
                coords=np.meshgrid(*ids,indexing='ij')
                flat=np.ravel_multi_index(tuple(v.ravel() for v in coords),shape,order='F')
                distance=sign*(position-coordinates[d][coords[d].ravel()])
                if staggered:
                    valid=metrics['ds'][component,flat]>0 if field=='E' else (metrics['dA'][component,flat]>0)&(metrics['dsd'][component,flat]>0)
                else:valid=metrics['ds'][0,flat]>0
                flat,distance=flat[valid],np.clip(distance[valid],0,L)
                alpha=strength*c/L*(1-distance/L)**2
                collected[field].append((flat+component*N,alpha))
                row['components'][field+'xyz'[component]]=dict(samples=len(flat),planes=int(len(np.unique(distance))),
                    max_alpha_per_s=float(alpha.max()) if len(alpha) else 0,nearest_face_distance_m=float(distance.min()) if len(distance) else None)
        rows.append(row)
    result={}
    for field,parts in collected.items():
        indices=np.concatenate([v[0] for v in parts]);values=np.concatenate([v[1] for v in parts])
        unique,inverse=np.unique(indices,return_inverse=True);rates=np.zeros(len(unique));np.add.at(rates,inverse,values)
        result[field]=(unique,rates)
    return result,rows

class StaggeredPortLayers:
    """Apply the same 20 mm quadratic loss profile at proper E/H locations."""
    def __init__(self,solver,metrics,faces,staggered=True,strength=10.):
        import cupy as cp
        rates,self.audit=build_rates(metrics,faces,staggered=staggered,strength=strength)
        self.solver=solver;self.data={}
        for key,(indices,alpha) in rates.items():
            factor=np.exp(-alpha*float(solver.dt)/2).astype('f4')
            assert np.all((factor>0)&(factor<=1))
            self.data[key]=(cp.asarray(indices,dtype=cp.int32),cp.asarray(factor))
    def half_step(self):
        for key,(index,factor) in self.data.items():getattr(self.solver,key).array[index]*=factor
