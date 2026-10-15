"""Fifteen-dimensional WF7 geometry and exact CST parameter expansion."""
from __future__ import annotations
import math
from typing import Mapping
import numpy as np
from .config import Config, NAMES

class Geometry:
    """Lengths mm, angles degrees; coaxr2 is the thick inner-conductor radius."""
    def __init__(self, config: Config):
        self.config=config
        self.lo=np.array([config.bounds[n][0] for n in NAMES])
        self.hi=np.array([config.bounds[n][1] for n in NAMES])

    def violations(self, p: Mapping[str,float]) -> list[str]:
        errors=[]
        if set(p)!=set(NAMES):return ['Coordinate names do not match fifteen-dimensional contract']
        for n in NAMES:
            v=p[n];lo,hi=self.config.bounds[n]
            if isinstance(v,bool) or not math.isfinite(v) or not lo<=v<=hi:errors.append(f'{n}: bounds')
        if errors:return errors
        gap=self.config.search.bound_clearance_mm
        if abs(self.config.fixed_parameters['DownHeight2'])>=p['DownHeight']-10:errors.append('DownHeight2 clearance')
        if not 2<p['SPortR2']<p['SPortR1']<p['PortR1']<22:errors.append('Nested conductor radii')
        if not 5.43<p['coaxr2']<22 or p['coaxr2']<p['PortR1']+self.config.port_wall_mm:
            errors.append('Thick conductor radius must cover PortR2 and remain below 22 mm')
        if min(p['SPortR1']-p['SPortR2'],p['PortR1']-p['SPortR1'])<gap:errors.append('Radial modeling clearance')
        if self.config.port_outer_policy=='fixed' and p['PortR1']>=self.config.fixed_port_outer_mm-gap:
            errors.append('Fixed PortR2 wall clearance')
        return errors

    def normalize(self,p: Mapping[str,float]) -> np.ndarray:
        return (np.array([p[n] for n in NAMES])-self.lo)/(self.hi-self.lo)

    def denormalize(self,x: np.ndarray) -> dict[str,float]:
        return dict(zip(NAMES,map(float,self.lo+np.asarray(x)*(self.hi-self.lo))))

    def expand(self,p: Mapping[str,float]) -> dict[str,float]:
        """Map projected bends to signed angle/radius; preserve source meanings."""
        errors=self.violations(p)
        if errors:raise ValueError('; '.join(errors))
        result={n:float(v) for n,v in p.items() if n not in ('projection1','projection2','Lin1','coaxr2')}
        result['coax_r2']=p['coaxr2']  # Saved CST spelling; independent radius in mm.
        result['Lin']=p['Lin1'];result.update(self.config.fixed_parameters)
        radius=self.config.search.fixed_radius_mm
        for i,sign,angle,key in ((1,-1,'inner_angle','inner_r'),(2,1,'inner_angle3','inner_r2')):
            result[angle]=sign*math.degrees(math.acos(1-p[f'projection{i}']/(2*radius)))
            result[key]=sign*radius
        if self.config.port_outer_policy=='follow_wall':result['PortR2']=p['PortR1']+self.config.port_wall_mm
        elif self.config.port_outer_policy=='fixed':result['PortR2']=self.config.fixed_port_outer_mm
        else:raise ValueError('PortR2 policy not confirmed')
        return result

    def sample(self,rng: np.random.Generator,count: int,center: Mapping[str,float] | None=None,radius: float | None=None) -> list[dict[str,float]]:
        """Draw directly inside domain intersection; reject infeasible coordinates."""
        lo=np.zeros(len(NAMES));hi=np.ones(len(NAMES))
        if center is not None:
            c=self.normalize(center);r=self.config.search.radius if radius is None else radius
            lo=np.maximum(lo,c-r);hi=np.minimum(hi,c+r)
        answer=[]
        for _ in range(500):
            for x in rng.uniform(lo,hi,size=(max(64,4*(count-len(answer))),len(NAMES))):
                p=self.denormalize(x)
                if not self.violations(p):answer.append(p)
                if len(answer)==count:return answer
        raise RuntimeError('Unable to sample feasible geometry without changing bounds')

    @staticmethod
    def from_template(values: Mapping[str,float]) -> dict[str,float]:
        """Read actual saved template values; never substitute old campaign data."""
        aliases={'Lin1':'Lin','coaxr2':'coax_r2'}
        p={n:float(values[aliases.get(n,n)]) for n in NAMES if not n.startswith('projection')}
        for i,angle,radius in ((1,'inner_angle','inner_r'),(2,'inner_angle3','inner_r2')):
            p[f'projection{i}']=2*abs(values[radius])*(1-math.cos(math.radians(values[angle])))
        return p
