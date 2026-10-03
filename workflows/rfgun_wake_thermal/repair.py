"""Narrow port-mesh retry policy; never labels arbitrary failures as geometry."""
from __future__ import annotations
import re
from .config import Runtime


def bad_ports(message:str)->tuple[int,...]:
    """Require a port index plus an explicit nonuniform/inhomogeneous mesh diagnosis."""
    parts=re.split(r'[\r\n]+',message.lower())
    found=set()
    for i,line in enumerate(parts):
        # CST 2026 live diagnostic, observed during the first WF6 baseline.
        short=re.findall(r'waveguide for port (?:number\s+)?([23]) is too short\.\s*the waveguide must be homogeneous for at least three equidistant mesh planes',line)
        if short:
            found.update(map(int,short));continue
        context=' '.join(parts[max(0,i-1):i+2])
        if re.search(r'(inhomogen|non[- ]?uniform|not (?:sufficiently )?homogen|不均匀)',context) and re.search(r'mesh|网格',context):
            for n in re.findall(r'(?:port|端口)\s*([23])\b',context):found.add(int(n))
    return tuple(sorted(found))


def next_ports(current:tuple[float,float],ports:tuple[int,...],tried:list,
               attempts:int,elapsed:float,config:Runtime)->tuple[float,float]|None:
    """Bounded candidate-wide repair count and seconds; change diagnosed ports only."""
    if not ports or attempts>=config.repair_retries or elapsed>=config.repair_timeout_s:return None
    visited={tuple(x) for x in tried}
    for length in config.port_values_mm[1:]:
        v=list(current)
        for port in ports:v[port-2]=length
        if tuple(v)!=tuple(current) and tuple(v) not in visited:return tuple(v)
    return None
