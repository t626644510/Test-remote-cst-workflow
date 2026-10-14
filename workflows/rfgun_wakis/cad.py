"""Read resolved CST metadata; these are files, not invented CST API calls."""
from __future__ import annotations
import json
from pathlib import Path
import re
import numpy as np

def parameters(project: Path) -> dict[str,float]:
    data=json.loads((project.with_suffix('')/'Model/Parameters.json').read_text(encoding='utf-8-sig'))
    return {p['name']:float(p['value']) for p in data['parameters']}

def material_properties(mif: Path) -> dict:
    text=mif.read_text(encoding='utf-8',errors='strict')
    return {name:{key:re.findall(r'\.'+key+r'\s+"([^"]+)"',body) for key in ('Type','Epsilon','Mu','Sigma')}
            for name,body in re.findall(r'\[MATERIAL: (.*?)\](.*?)\[ENDMATERIAL\]',text,re.S)}

def port_faces(mif: Path) -> list[dict]:
    """Resolved orthogonal aperture planes in metres; fail on oblique ports."""
    text=mif.read_text(encoding='utf-8');faces=[]
    for number,body in re.findall(r'\[WAVEGUIDE: (\d+)\](.*?)\[ENDWAVEGUIDE\]',text,re.S):
        match=re.search(r'\(TRANSFORM\)(.*?)\|(.*?)\(ENDTRANSFORM\)',body,re.S)
        if not match:raise ValueError(f'Missing resolved transform at port {number}')
        matrix=np.array([float(v) for v in re.findall(r'"([^"]+)"',match[1])]).reshape(3,3)
        origin=np.array([float(v) for v in re.findall(r'"([^"]+)"',match[2])])*1e-3
        ranges=[np.array([float(v) for v in re.search(r'\.'+d+r'range "([^"]+)", "([^"]+)"',body).groups()])*1e-3 for d in 'XYZ']
        corners=np.array([[x,y,z] for x in ranges[0] for y in ranges[1] for z in ranges[2]])@matrix+origin
        normal=(-1 if '.Orientation "zmin"' in body else 1)*matrix[2]
        d=int(np.argmax(abs(normal)))
        if np.count_nonzero(abs(normal)>1e-9)!=1 or not np.isclose(abs(normal[d]),1):
            raise ValueError(f'Oblique port {number} requires a separately validated absorber')
        faces.append(dict(name='port_'+number,axis=d,sign=int(normal[d]),low=corners.min(axis=0).tolist(),high=corners.max(axis=0).tolist()))
    names=[f['name'] for f in faces]
    if len(set(names))!=len(names) or not {'port_2','port_3'}.issubset(names):
        raise ValueError('Two leakage ports missing or duplicated')
    return faces
