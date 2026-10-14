"""Experimental energy-paired copper boundary on imported FIT metrics.

H trace [A/m] is interpolated on CAD triangles and projected tangentially.
The passive causal Z(s) maps it to tangential E [V/m]. The adjoint trace feeds
the surface voltage back into Faraday's law: M_H dH/dt = ... - T^T A Z T H,
M_H=mu0*dA*dsd [H*m^2]. Hence boundary power is H_t^T A E_t [W].
This is a weak surface discretization; it must pass independent cavity loss
tests and trace-resolution checks before acceptance. No CST wake curve fit.
"""
from pathlib import Path
import json
import numpy as np
import scipy.sparse as sp
from scipy.spatial import cKDTree
from scipy.constants import mu_0
import pyvista as pv
import cupy as cp
from cupyx.scipy.sparse import csr_matrix
from .copper_impedance import CopperSurfaceImpedance

class SurfaceCopper:
    def __init__(self,solver,metrics,surface_path,out,neighbors=4,conductivity=5.8e7):
        self.solver=solver;self.neighbors=neighbors
        surface=pv.read(surface_path).triangulate()
        tri=surface.points[surface.faces.reshape(-1,4)[:,1:]]
        centers=tri.mean(axis=1)
        cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        norm=np.linalg.norm(cross,axis=1);normals=cross/norm[:,None];area=norm/2
        # The end disks close the exported vacuum but are PEC computational
        # end boundaries, not copper material. Do not assign copper there.
        end=(np.abs(np.abs(centers[:,2])-float(metrics['z'][-1]))<1e-6)&(abs(normals[:,2])>.9999)
        keep=(area>1e-15)&~end
        self.surface_indices=np.flatnonzero(keep)
        centers,normals,area=centers[keep],normals[keep],area[keep]
        ns=len(area);shape=(solver.Nx,solver.Ny,solver.Nz);N=solver.N
        axes=[metrics[k] for k in 'xyz']
        mids=[np.r_[.5*(a[:-1]+a[1:]),a[-1]+.5*(a[-1]-a[-2])] for a in axes]
        rows=[];cols=[];vals=[];maxdist=[]
        fullarea=[np.outer(solver.dy,solver.dz)[None,:,:],np.outer(solver.dx,solver.dz)[:,None,:],np.outer(solver.dx,solver.dy)[:,:,None]]
        for d in range(3):
            xyz=np.meshgrid(*[axes[k] if k==d else mids[k] for k in range(3)],indexing='ij')
            points=np.column_stack([v.ravel(order='F') for v in xyz])
            af=metrics['dA'][d].reshape(shape,order='F')/fullarea[d]
            valid=(af.ravel(order='F')>.15)&(metrics['dsd'][d]>0)
            ids=np.flatnonzero(valid)
            dist,idx=cKDTree(points[ids]).query(centers,k=neighbors)
            if neighbors==1:dist=dist[:,None];idx=idx[:,None]
            weights=1/np.maximum(dist,1e-9)**2;weights/=weights.sum(axis=1)[:,None]
            maxdist.append(float(dist.max()))
            for e in range(3):
                projection=(float(d==e)-normals[:,e]*normals[:,d])
                rows.extend(np.repeat(np.arange(ns)*3+e,neighbors))
                cols.extend((ids[idx]+d*N).ravel())
                vals.extend((weights*projection[:,None]).ravel())
        T=sp.csr_matrix((vals,(rows,cols)),shape=(3*ns,3*N),dtype=np.float32)
        masses=(mu_0*metrics['dA'].astype('f8')*metrics['dsd'].astype('f8')).ravel()
        inv=np.divide(1.,masses,out=np.zeros_like(masses),where=masses>0)
        back=sp.diags(inv.astype('f4'))@T.T@sp.diags(np.repeat(area,3).astype('f4'))
        law=CopperSurfaceImpedance(conductivity_S_per_m=conductivity)
        alpha,beta,R=law.recurrence(float(solver.dt))
        # Conservative infinity-norm bound on dt*Z_discrete*adjoint*trace.
        bound=float(solver.dt)*float(np.dot(R,beta))*float(np.max(abs(back)@np.asarray(abs(T).sum(axis=1)).ravel()))
        if bound>=.5:raise RuntimeError(f'Surface explicit coupling bound too large: {bound}')
        self.T=csr_matrix(T);self.back=csr_matrix(back)
        self.alpha=cp.asarray(alpha.astype('f4')[:,None]);self.beta=cp.asarray(beta.astype('f4')[:,None])
        self.R=cp.asarray(R.astype('f4'));self.state=cp.zeros((len(R),3*ns),dtype='f4')
        self.old=cp.zeros(3*ns,dtype='f4')
        self.audit=dict(triangles=ns,area_m2=float(area.sum()),neighbors=neighbors,
            conductivity_S_per_m=conductivity,explicit_coupling_bound=bound,
            max_trace_distance_m=maxdist,constitutive='passive 96-pole Z(s)=sqrt(mu0/sigma)*sqrt(s)',
            spatial='adjoint-paired tangential surface trace and magnetic energy metric',
            excluded_endcap_triangles=int(end.sum()),validated=False)
        (out/'surface_copper.json').write_text(json.dumps(self.audit,indent=2))

    def step(self):
        # Apply after the lossless step, with H at its native half time. This
        # first-order splitting must be checked with dt/2; loss is very small.
        value=self.T@self.solver.H.array
        self.state=self.alpha*self.state+self.beta*(value-self.old)[None,:]
        self.old=value
        electric=self.R@self.state
        self.solver.H.array-=self.solver.dt*(self.back@electric)
