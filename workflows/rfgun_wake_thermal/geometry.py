"""Double-bend physical coordinates: lengths mm, angles degrees."""
from __future__ import annotations
import math
from typing import Mapping
from .config import Config,NAMES


class Geometry:
    """Round-trip CST's signed fourteen parameters through twelve coordinates."""
    def __init__(self, config: Config): self.config=config

    def violations(self, p: Mapping[str,float]) -> list[str]:
        errors=[]
        for n in NAMES:
            v=p.get(n,float('nan'));lo,hi=self.config.bounds[n]
            if not math.isfinite(v) or not lo<=v<=hi:errors.append(f'{n}: outside [{lo},{hi}]')
        if errors:return errors
        gap=self.config.search.bound_clearance_mm
        for i in (1,2):
            if abs(p[f'DownHeight{i}'])>p[f'UpperHeight{i}']-gap:errors.append(f'antenna{i}: absolute height')
            if p[f'Lin{i}']-p[f'DownHeight{i}']<gap:errors.append(f'antenna{i}: linear clearance')
        return errors

    def expand(self,p: Mapping[str,float]) -> dict[str,float]:
        errors=self.violations(p)
        if errors:raise ValueError('; '.join(errors))
        v={self.config.parameter_mapping.get(k,k):float(x) for k,x in p.items() if not k.startswith('projection')}
        R=self.config.search.fixed_radius_mm
        for i,an,rn,sign in [(1,'inner_angle','inner_r',-1),(2,'inner_angle3','inner_r2',1)]:
            v[an]=sign*math.degrees(math.acos(1-p[f'projection{i}']/(2*R)))
            v[rn]=sign*R
        return v

    def collapse(self,p: Mapping[str,float]) -> dict[str,float]:
        v={n:float(p[self.config.parameter_mapping.get(n,n)]) for n in NAMES if not n.startswith('projection')}
        for i,an,rn in [(1,'inner_angle','inner_r'),(2,'inner_angle3','inner_r2')]:
            v[f'projection{i}']=2*abs(p[rn])*(1-math.cos(math.radians(p[an])))
        return {n:v[n] for n in NAMES}
