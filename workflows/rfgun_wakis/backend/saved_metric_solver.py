"""Use CST's decoded FIT metric coefficients on this candidate's geometry.

ds/dsd [m], dA/dad [m^2]. Copper is supplied by the accepted passive surface
law, not by treating its skin depth as a volumetric Cartesian cell.
"""
from __future__ import annotations
import numpy as np
from scipy.sparse import diags
from scipy.constants import epsilon_0,mu_0
from wakis import SolverFIT3D

class SavedMetricSolver(SolverFIT3D):
    """Inject verified candidate metrics without any frozen-0001 shape/path."""
    def __init__(self,grid,wake,*,metrics,**kwargs):
        self.saved_metrics=metrics
        super().__init__(grid,wake,**kwargs)

    def _apply_stl_materials(self):
        p=self.saved_metrics
        if (self.Nx,self.Ny,self.Nz)!=tuple(len(p[k]) for k in 'xyz'):
            raise ValueError('Grid dimensions do not match saved metrics')
        flat={k:p[k].astype(self.dtype).ravel() for k in ('ds','dsd','dA','dad')}
        inv=lambda a:np.divide(1.,a,out=np.zeros_like(a),where=a>0)
        self.Ds=diags(flat['ds']);self.iDa=diags(inv(flat['dA']))
        self.tDs=diags(flat['dsd']);self.itDa=diags(inv(flat['dad']))
        self.ieps.array[:]=(flat['ds']>0).astype(self.dtype)/epsilon_0
        self.imu.array[:]=1/mu_0
        self.L.array[:]=flat['ds'];self.tL.array[:]=flat['dsd']
        self.iA.array[:]=inv(flat['dA']);self.itA.array[:]=inv(flat['dad'])
        self.use_conductivity=False
