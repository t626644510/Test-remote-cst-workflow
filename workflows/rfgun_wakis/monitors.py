"""Passive shared-wake sampling of solid1 H and port2/3 Poynting flux.

SI units; no field feedback or extra excitation. Native E/H half timesteps
are retained for same-pole fits. Three planes per coax exclude the absorber.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import scipy.sparse as sp

def coordinates(metrics,field: str,component: int):
    axes=[metrics[k] for k in 'xyz']
    mids=[np.r_[.5*(a[:-1]+a[1:]),a[-1]+.5*(a[-1]-a[-2])] for a in axes]
    return [mids[j] if (j==component)==(field=='E') else axes[j] for j in range(3)]

def flux_operators(metrics,faces) -> tuple:
    """Collocate tangential E/H at +Z coax planes, using FIT edge areas."""
    shape=[len(metrics[k]) for k in 'xyz'];n=int(np.prod(shape))
    er=[];ecol=[];hv=[];hr=[];hcol=[];planes=[];count=0
    for face in faces:
        if face['name'] not in ('port_2','port_3'):continue
        if face['axis']!=2 or face['sign']!=1:raise ValueError('Leakage monitor requires +Z coax ports')
        choices=[]
        for k,z in enumerate(metrics['z'][:-1]):
            zh=coordinates(metrics,'H',0)[2];j1=int(np.searchsorted(zh,z));j0=j1-1
            if j0<0 or j1>=shape[2]:continue
            d=face['low'][2]-z
            if .020<d<.060 and face['low'][2]-zh[j1]>=.020:choices.append((d,k,j0,j1))
        choices.sort()
        if len(choices)<3:raise ValueError('Three physical coax planes outside absorber are required')
        for d,k,j0,j1 in choices[:3]:
            start=count;weights=[];signs=[];radial_e=[];radial_h=[]
            center=.5*(np.array(face['low'])+face['high'])
            for ei,hi,sign in ((0,1,1.),(1,0,-1.)):
                xe=coordinates(metrics,'E',ei);xh=coordinates(metrics,'H',hi)
                ids=[np.flatnonzero((xe[j]>=face['low'][j]-1e-12)&(xe[j]<=face['high'][j]+1e-12)) for j in (0,1)]
                ix,iy=np.meshgrid(*ids,indexing='ij');ix=ix.ravel();iy=iy.ravel()
                ef=ix+iy*shape[0]+k*shape[0]*shape[1]
                h0=ix+iy*shape[0]+j0*shape[0]*shape[1];h1=ix+iy*shape[0]+j1*shape[0]*shape[1]
                fraction=(metrics['z'][k]-xh[2][j0])/(xh[2][j1]-xh[2][j0])
                w=metrics['ds'][ei,ef]*((1-fraction)*metrics['dsd'][hi,h0]+fraction*metrics['dsd'][hi,h1])
                x=xe[0][ix]-center[0];y=xe[1][iy]-center[1];r2=x*x+y*y
                good=(w>0)&(r2>1e-14);ef,h0,h1,w,x,y,r2=[v[good] for v in (ef,h0,h1,w,x,y,r2)]
                rows=np.arange(count,count+len(ef));count+=len(ef)
                er.extend(rows);ecol.extend(ef+ei*n)
                hr.extend(rows);hcol.extend(h0+hi*n);hv.extend(np.full(len(rows),1-fraction))
                hr.extend(rows);hcol.extend(h1+hi*n);hv.extend(np.full(len(rows),fraction))
                weights.extend(w);signs.extend(np.full(len(w),sign))
                radial_e.extend((x if ei==0 else y)/r2);radial_h.extend((x if hi==1 else -y)/r2)
            if count==start:raise ValueError('Empty leakage cross section')
            planes.append(dict(port=face['name'],distance_m=float(d),z_m=float(metrics['z'][k]),start=start,stop=count,
                               weight_m2=np.asarray(weights).tolist(),sign=np.asarray(signs).tolist(),
                               radial_e=np.asarray(radial_e).tolist(),radial_h=np.asarray(radial_h).tolist()))
    e=sp.csr_matrix((np.ones(len(er)),(er,ecol)),shape=(count,3*n))
    h=sp.csr_matrix((hv,(hr,hcol)),shape=(count,3*n))
    return e,h,planes

class PassiveMonitor:
    """Sparse port traces participate in exact compact-index closure."""
    def __init__(self,solver,metrics,faces,out: Path,nt: int,enabled: bool=True,stride: int=64):
        import cupy as cp
        from cupyx.scipy.sparse import csr_matrix
        self.solver=solver;self.out=out;self.stride=stride;self.count=0;self.enabled=enabled
        if enabled:e,h,self.planes=flux_operators(metrics,faces)
        else:e=h=sp.csr_matrix((0,3*solver.N));self.planes=[]
        self.width=e.shape[0]
        self.E=csr_matrix(sp.vstack((e,sp.csr_matrix(h.shape))))
        self.H=csr_matrix(sp.vstack((sp.csr_matrix(e.shape),h)))
        self.data=cp.zeros(((nt+stride-1)//stride,2*self.width),dtype=cp.float32)

    def record(self,step: int) -> None:
        if step%self.stride==0:
            self.data[self.count]=self.E@self.solver.E.array+self.H@self.solver.H.array
            self.count+=1

    def save(self) -> None:
        import cupy as cp,h5py
        from .io import atomic_json
        with h5py.File(self.out/'port_traces.h5','x') as f:
            f['fields']=cp.asnumpy(self.data[:self.count]);f.attrs['width']=self.width
            steps=np.arange(self.count)*self.stride
            f['t_E_s']=steps*float(self.solver.dt);f['t_H_s']=(steps-.5)*float(self.solver.dt)
        atomic_json(self.out/'port_planes.json',self.planes)

class ThermalMonitor:
    """Decimate pre-SIBC tangential H and post-step axis E, without field changes."""
    def __init__(self,engine,surface_path: Path,out: Path,stride: int=64):
        import cupy as cp,h5py
        self.engine=engine;self.stride=stride;self.count=0;self.pending=0;self.steps=[]
        data=dict(np.load(surface_path));selected=data['triangle_index']
        mapping={int(original):i for i,original in enumerate(engine.copper.surface_indices)}
        keep=np.array([int(i) in mapping for i in selected])
        coverage=float(data['area_m2'][keep].sum()/data['area_m2'].sum())
        if not keep.all():raise ValueError(f'Thermal surface lost in copper interpolation: area coverage={coverage}')
        ids=np.array([mapping[int(i)] for i in selected])
        self.ids=cp.asarray((3*ids[:,None]+np.arange(3)).ravel())
        self.buffer=cp.empty((32,len(self.ids)),dtype='f4');self.ebuffer=cp.empty((32,engine.solver.Nz),dtype='f4')
        self.file=h5py.File(out/'thermal_traces.h5','x')
        self.hdata=self.file.create_dataset('Ht_A_per_m',(0,len(self.ids)),maxshape=(None,len(self.ids)),dtype='f4',chunks=(32,len(self.ids)))
        self.edata=self.file.create_dataset('Ez_V_per_m',(0,engine.solver.Nz),maxshape=(None,engine.solver.Nz),dtype='f4',chunks=(32,engine.solver.Nz))
        for k,v in data.items():self.file[k]=v
        self.file['z_mid_m']=engine.solver.z;self.file['dz_m']=engine.solver.dz
        self.file.attrs['dt_s']=float(engine.solver.dt);self.file.attrs['area_coverage']=coverage

    def record_after_step(self,step:int):
        if step%self.stride:return
        e=self.engine;self.buffer[self.pending]=e.copper.old[self.ids]
        values=e.E[e.line_compact] if e.active else e.solver.E.array[e.line]
        self.ebuffer[self.pending]=values[:e.solver.Nz]
        self.steps.append(step);self.pending+=1
        if self.pending==32:self.flush()

    def flush(self):
        import cupy as cp
        if not self.pending:return
        end=self.count+self.pending;self.hdata.resize(end,axis=0);self.edata.resize(end,axis=0)
        self.hdata[self.count:end]=cp.asnumpy(self.buffer[:self.pending]);self.edata[self.count:end]=cp.asnumpy(self.ebuffer[:self.pending])
        self.file.flush();self.count=end;self.pending=0

    def close(self):
        self.flush();dt=self.file.attrs['dt_s'];s=np.asarray(self.steps)
        self.file['t_E_s']=(s+1)*dt;self.file['t_H_s']=(s+.5)*dt;self.file.close()
