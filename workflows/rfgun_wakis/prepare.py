"""Candidate-specific FIT metrics and exposed copper/solid1 surface preparation.

All coordinates become metres. Epsilon and mu must equal vacuum values in
every explicit material; conducting interfaces use the accepted surface law.
This cannot silently handle a newly introduced dielectric or magnetic body.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np
from scipy.constants import epsilon_0,mu_0
from .backend.decode_metrics import read_tensor
from .cad import material_properties,port_faces
from .io import atomic_json,digest,manifest

def decode(result: Path) -> tuple[dict,dict]:
    """Read a candidate's complete CST tensor set with strict format checks."""
    source=result/'Model.msh';b=source.read_bytes()
    n=np.frombuffer(b,dtype='<i4',count=3,offset=8)
    if len(n)!=3 or np.any(n<4) or np.prod(n,dtype='i8')>30000000 or len(b)!=32+sum(n)*8:
        raise ValueError('Unsupported or excessive Cartesian mesh')
    v=np.frombuffer(b,dtype='<f8',offset=32);arrays={};off=0
    for k,nn in zip('xyz',n):
        a=v[off:off+nn].copy();off+=nn
        if not np.isfinite(a).all() or np.any(np.diff(a)<=0):raise ValueError('Nonmonotone mesh')
        arrays[k]=a
    total=int(np.prod(n));audit=dict(shape=n.tolist(),mesh_sha256=digest(source),tensors={})
    for name in ('ds','dsd','dA','dad','Eps','Mue'):
        arrays[name],audit['tensors'][name]=read_tensor(result/(name+'.mat'),total)
        if np.any(arrays[name]<0):raise ValueError(f'Negative diagonal metric {name}')
    for k in 'xy':
        for value in (-.002,0.,.002):
            if np.min(abs(arrays[k]-value))>1e-12:raise ValueError(f'Required witness/source node {k}={value} m missing')
    identities={}
    for name,l,ar,k in (('Eps','ds','dad',epsilon_0),('Mue','dsd','dA',mu_0)):
        a=arrays;v=np.divide(a[l].astype('f8'),k*a[ar],out=np.zeros_like(a[l],dtype='f8'),where=a[ar]>0)
        mask=a[name]>0;ratio=v[mask]/a[name][mask]
        identities[name]=dict(nonzero=int(mask.sum()),mismatched=int(np.count_nonzero(abs(ratio-1)>1e-5)),max_relative_error=float(abs(ratio-1).max()))
        if name=='Eps' and np.any(abs(ratio-1)>1e-5):raise ValueError('Unsupported electric metric/material identity')
    a=arrays
    relative=np.divide(a['dsd'],mu_0*a['dA'],out=np.zeros_like(a['dsd']),where=a['dA']>0)/np.maximum(a['Mue'],1)-1
    mismatch=(a['Mue']>0)&(abs(relative)>1e-5)
    effective=np.divide(a['dsd'].astype('f8'),mu_0*a['Mue'],out=np.zeros_like(a['dsd'],dtype='f8'),where=a['Mue']>0)
    a['dA']=a['dA'].copy();a['dA'][mismatch]=effective[mismatch]
    audit.update(identities=identities,regularized_magnetic_faces=int(mismatch.sum()),regularization='algebraically preserve native CST Mue coefficient')
    return arrays,audit

def prepare(project: Path,geometry: Path,out: Path,thermal_solids: tuple[str,str]) -> dict:
    """Build complete immutable metrics/surface evidence before any GPU solve."""
    import pyvista as pv
    out.mkdir(parents=True,exist_ok=True)
    metrics,audit=decode(project.with_suffix('')/'Result')
    mif=project.with_suffix('')/'ModelCache/Model.mif'
    props=material_properties(mif)
    # CST modal ports are omitted only during matrix assembly. Their resolved
    # geometry is archived immediately before that change for Wakis absorbers.
    port_mif=geometry/'ported_Model.mif'
    faces=port_faces(port_mif if port_mif.is_file() else mif)
    rows=list(csv.DictReader((geometry/'solids.tsv').open(encoding='utf-8-sig'),delimiter='\t'))
    if not set(thermal_solids).issubset(r['name'] for r in rows):raise ValueError('Requested solid1 body missing after rebuild')
    solids=[];triangles=[];origins=[];names=[]
    # Prefer a conductor's own tessellation when a vacuum interface duplicates
    # it, so solid1 ownership survives deduplication without counting twice.
    def metal(row):
        p=props[row['material']]
        if float(p['Epsilon'][-1])!=1 or float(p['Mu'][-1])!=1:raise ValueError('New dielectric/magnetic body unsupported')
        return p['Type'][-1].lower()=='pec' or float((p['Sigma'] or ['0'])[-1])>0
    rows.sort(key=lambda r:(0 if r['name'] in thermal_solids else 1 if metal(r) else 2,r['name']))
    for row in rows:
        if row['name']=='air_0:brick':continue
        mesh=pv.read(geometry/('solid_'+row['index']+'.stl')).clean().triangulate()
        if mesh.n_open_edges:raise ValueError('STL is not closed: '+row['name'])
        solids.append((mesh,metal(row)))
        tri=mesh.points[mesh.faces.reshape(-1,4)[:,1:]].astype('f8')
        index=len(names);names.append(row['name']);triangles.append(tri);origins.extend([index]*len(tri))
    tri=np.concatenate(triangles);origins=np.asarray(origins)
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);norm=np.linalg.norm(cross,axis=1)
    good=norm>1e-15;tri,origins,cross,norm=tri[good],origins[good],cross[good],norm[good]
    normals=cross/norm[:,None];centers=tri.mean(axis=1)
    def vacuum(points):
        cloud=pv.PolyData(points);inside=np.zeros(len(points),bool)
        for mesh,is_metal in sorted(solids,key=lambda x:x[1]):
            selected=np.asarray(cloud.select_enclosed_points(mesh,tolerance=1e-8,check_surface=True)['SelectedPoints'],bool)
            if is_metal:inside[selected]=False
            else:inside|=selected
        return inside
    inside=vacuum(np.concatenate((centers+normals*1e-4,centers-normals*1e-4)))
    keep=inside[:len(tri)]!=inside[len(tri):]
    for face in faces:
        d=face['axis'];on=abs(centers[:,d]-face['low'][d])<1e-6
        for j in range(3):
            if j!=d:on&=(centers[:,j]>=face['low'][j]-1e-6)&(centers[:,j]<=face['high'][j]+1e-6)
        keep&=~on
    for end in (metrics['z'][0],metrics['z'][-1]):keep&=abs(centers[:,2]-end)>1e-6
    tri,origins=tri[keep],origins[keep]
    seen=set();unique=[]
    for i,t in enumerate(tri):
        key=tuple(sorted(tuple(v) for v in np.round(t,9)))
        if key not in seen:seen.add(key);unique.append(i)
    tri,origins=tri[unique],origins[unique]
    mesh=pv.PolyData(tri.reshape(-1,3),np.c_[np.full(len(tri),3),np.arange(3*len(tri)).reshape(-1,3)].ravel())
    mesh.cell_data['solid_index']=origins
    mesh.save(out/'copper_surface.vtp')
    areas=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
    selected=np.array([names[i] in thermal_solids for i in origins])
    components=np.array([thermal_solids.index(names[i]) if names[i] in thermal_solids else -1 for i in origins])
    if any(not np.any(components==i) for i in range(2)):raise ValueError('No exposed thermal surface on a requested solid1')
    np.savez_compressed(out/'thermal_surface.npz',triangle_index=np.flatnonzero(selected),component=components[selected],area_m2=areas[selected],centers_m=tri.mean(axis=1)[selected])
    np.savez_compressed(out/'effective_metrics.npz',**metrics)
    atomic_json(out/'port_faces.json',faces)
    atomic_json(out/'materials.json',props)
    audit.update(thermal_solids=list(thermal_solids),thermal_areas_m2=[float(areas[components==i].sum()) for i in range(2)],
                 triangles=len(tri),source_solids=names,classification_probe_m=1e-4,ports=faces,
                 source_template_copy=str(project),project_sha256=digest(project),geometry_sha256=digest(mif))
    atomic_json(out/'preparation.json',audit)
    atomic_json(out/'manifest.json',manifest(out,[out/n for n in ('effective_metrics.npz','copper_surface.vtp','thermal_surface.npz','port_faces.json','materials.json','preparation.json')]))
    return audit
