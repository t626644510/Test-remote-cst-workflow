"""Typed portable configuration. SI physics; geometry mm and angles degrees."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
import math
import os
from typing import Any,get_type_hints,get_origin,get_args
import yaml

STAGES = ('axis', 'x', 'y', 'thermal')
NAMES = tuple(n for i in (1, 2) for n in
              (f'selfangle{i}', f'UpperHeight{i}', f'DownHeight{i}', f'Lin{i}', f'projection{i}',
               'FolkHeight' if i == 1 else 'FolkHeight2'))
DEFAULT_BOUNDS = dict(zip(NAMES, [(0.,180.),(5.01,50.),(-50.,50.),(1.,50.),(5.43,19.57),(5.43,30.)]*2))


@dataclass(frozen=True)
class Paths:
    """Station paths must be supplied in an ignored local configuration."""
    templates: dict[str, str]
    output_dir: str
    artifact_dir: str
    cst_library_path: str = ''


@dataclass(frozen=True)
class Physics:
    """Frequency Hz, impedance ohm / ohm per metre, voltage peak V, power W."""
    band_hz: tuple[float, float] = (550e6, 2047828853.9789505)
    longitudinal_limit: float = 2000.
    transverse_limit: float = 150000.
    power_reference_w: float = 150.
    voltage_peak_v: float = 500000.
    thermal_band_hz: tuple[float, float] = (498e6, 502e6)
    eigen_accuracy: float = 1e-6
    external_q_accuracy: float = 1e-4
    components: tuple[str, str] = ('component5', 'component6')
    beta: float = 1.
    sigma_m: float = .05
    wake_length_m: float = 35.
    offset_m: float = .002
    thermal_z_range_mm: tuple[float, float] = (-235.050544, 235.050544)
    thermal_z_samples: int = 1883
    conductivity_s_per_m: dict[str, float] = field(default_factory=lambda: {
        '**Cond. Enclosure**':5.8e7, 'Copper (annealed)':5.8e7, 'els/Copper (annealed)':5.8e7})


@dataclass(frozen=True)
class Reconstruction:
    """Fixed-tail ensemble controls; no implicit extra CST solves."""
    seeds: tuple[int, ...] = (17, 43, 109)
    starts_m: tuple[float, ...] = (1., 3.)
    max_error: float = .10
    min_correlation: float = .95
    peak_spread: float = .10
    q_bounds: tuple[float, float] = (1., 1e6)
    max_modes: int = 24
    fit_points: int = 4096
    spectrum_points: int = 4096
    max_nfev: int = 400
    min_bunch_spectrum: float = .05
    peak_prominence_fraction: float = .001
    pencil_ranks: tuple[int, ...] = (24,32,48)
    pencil_spacing_m: float = .02
    pencil_rows: int = 500
    pole_min_hz: float = 100e6
    frequency_width_hz: float = 10e6
    decay_bounds_per_m: tuple[float,float] = (1e-9,4.)
    holdout_fraction: float = .8
    bound_tail_fraction: float = .05


@dataclass(frozen=True)
class Search:
    hours: float = 96.
    exploration_fraction: float = .20
    initial_points: int = 12
    seed: int = 20261003
    pool: int = 2048
    gp_min_samples: int = 6
    radius: float = .25
    min_radius: float = .05
    max_radius: float = .5
    bound_clearance_mm: float = .01
    fixed_radius_mm: float = 25.


@dataclass(frozen=True)
class Runtime:
    """All timeouts seconds; retries count expensive starts, not only successes."""
    stage_timeout_s: float = 14400.
    postprocess_timeout_s: float = 1800.
    repair_timeout_s: float = 7200.
    repair_retries: int = 10
    port_values_mm: tuple[float, ...] = (20.,22.,18.,24.,16.,26.,14.,28.,12.,30.,10.)
    port_parameters: tuple[str, str] = ('Port2Length', 'port3Length')
    minimum_free_gib: float = 15.
    retain_pareto: int = 5
    retain_recent: int = 2
    heartbeat_s: float = 15.


@dataclass(frozen=True)
class Results:
    """Explicit native paths and units, never guessed from absent curves."""
    beam: str = 'ParticleBeam1'
    wake: str = r'1D Results\Particle Beams\{beam}\Wake potential\{axis}'
    impedance: str = r'1D Results\Particle Beams\{beam}\Wake impedance\{axis}'
    charge: str = r'1D Results\Particle Beams\{beam}\Charge distribution (distance)'
    wake_x_unit: str = 'mm'
    wake_y_unit: str = 'V/pC'
    frequency_unit: str = 'MHz'
    eigen_frequency: str = r'1D Results\Mode Frequencies\Mode {mode}'
    eigen_q: str = r'1D Results\Q Factors\Total-Q\Mode {mode}'


@dataclass(frozen=True)
class Config:
    paths: Paths
    physics: Physics = field(default_factory=Physics)
    reconstruction: Reconstruction = field(default_factory=Reconstruction)
    search: Search = field(default_factory=Search)
    runtime: Runtime = field(default_factory=Runtime)
    results: Results = field(default_factory=Results)
    bounds: dict[str, tuple[float, float]] = field(default_factory=lambda: DEFAULT_BOUNDS.copy())
    parameter_mapping: dict[str, str] = field(default_factory=lambda: {'Lin1':'Lin'})

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self, live: bool = False) -> None:
        """Reject unsafe or scientifically incomplete execution contracts."""
        def check(value, annotation, name):
            origin=get_origin(annotation);args=get_args(annotation)
            if origin in (tuple,list):
                if not isinstance(value,(list,tuple)):raise ValueError(f'{name} must be a sequence')
                for i,v in enumerate(value):check(v,args[0] if len(args)==2 and args[1] is Ellipsis else args[min(i,len(args)-1)],name)
            elif origin is dict:
                if not isinstance(value,dict):raise ValueError(f'{name} must be a mapping')
                for k,v in value.items():check(k,args[0],name);check(v,args[1],name)
            elif annotation in (int,float):
                if isinstance(value,bool) or not isinstance(value,(int,float) if annotation is float else int):raise ValueError(f'{name} has incorrect numeric type')
            elif annotation is str and not isinstance(value,str):raise ValueError(f'{name} must be text')
        for obj in (self.paths,self.physics,self.reconstruction,self.search,self.runtime,self.results,self):
            for name,annotation in get_type_hints(type(obj)).items():check(getattr(obj,name),annotation,name)
        if set(self.paths.templates) != set(STAGES):
            raise ValueError('Exactly axis/x/y/thermal templates required')
        if set(self.bounds) != set(NAMES):
            raise ValueError('Exactly twelve physical coordinate bounds required')
        for name, b in self.bounds.items():
            if len(b)!=2 or not all(math.isfinite(v) for v in b) or b[0]>=b[1]:
                raise ValueError(f'Invalid bounds for {name}')
        for b in (self.physics.band_hz, self.physics.thermal_band_hz, self.reconstruction.q_bounds):
            if len(b)!=2 or not 0 < b[0] < b[1] or not all(map(math.isfinite,b)):
                raise ValueError('Invalid frequency or Q interval')
        for obj in (self.physics,self.reconstruction,self.search,self.runtime):
            for f in fields(obj):
                v=getattr(obj,f.name)
                if isinstance(v,(int,float)) and (not math.isfinite(v) or v<=0):
                    raise ValueError(f'{f.name} must be positive finite')
        if self.physics.beta!=1 or self.physics.offset_m<=0:
            raise ValueError('Confirmed beta=1 and nonzero source offset required')
        if not 0 < self.search.exploration_fraction < 1:
            raise ValueError('Exploration fraction must be between zero and one')
        if self.search.fixed_radius_mm<=5.43 or self.search.fixed_radius_mm*2 < max(self.bounds[n][1] for n in ('projection1','projection2')):
            raise ValueError('Fixed bend radius incompatible with projection bounds')
        if not self.search.min_radius<=self.search.radius<=self.search.max_radius<=1:
            raise ValueError('Invalid normalized trust radius')
        if len(self.physics.components)!=2 or len(set(self.physics.components))!=2:
            raise ValueError('Two distinct antenna components required')
        if len(self.runtime.port_parameters)!=2 or len(set(self.runtime.port_parameters))!=2:
            raise ValueError('Two distinct port length parameters required')
        if self.results.wake_x_unit not in ('mm','m','ns') or self.results.wake_y_unit!='V/pC' or self.results.frequency_unit not in ('MHz','Hz','GHz'):
            raise ValueError('Unsupported explicit result units')
        if not self.reconstruction.seeds or not self.reconstruction.starts_m or min(self.reconstruction.starts_m)<0 or max(self.reconstruction.starts_m)>=self.physics.wake_length_m:
            raise ValueError('Invalid fixed-tail ensemble')
        if self.physics.thermal_z_samples<5 or self.physics.thermal_z_samples%2!=1:
            raise ValueError('Odd thermal voltage sample count required')
        for p in (self.paths.output_dir,self.paths.artifact_dir):
            if not p: raise ValueError('Output paths are required')
        if not 0<self.reconstruction.max_error<1 or not 0<self.reconstruction.min_correlation<=1 or not 0<self.reconstruction.peak_spread<1:
            raise ValueError('Invalid reconstruction quality thresholds')
        if self.reconstruction.q_bounds[0]<=.5:raise ValueError('Underdamped resonator requires Q>0.5')
        r=self.reconstruction
        if not r.pencil_ranks or any(k<2 for k in r.pencil_ranks) or r.pencil_rows<3:
            raise ValueError('Invalid pencil ranks or rows')
        if len(r.decay_bounds_per_m)!=2 or not 0<r.decay_bounds_per_m[0]<r.decay_bounds_per_m[1] or not all(map(math.isfinite,r.decay_bounds_per_m)):
            raise ValueError('Invalid decay bounds')
        if not .5<=r.holdout_fraction<1 or not 0<r.bound_tail_fraction<1:
            raise ValueError('Invalid holdout or local boundary-tail tolerance')
        if r.pencil_spacing_m>=299792458./(2*(self.physics.band_hz[1]+r.frequency_width_hz)):
            raise ValueError('Pencil samples would alias the configured pole band')
        destinations=[Path(p).resolve() for p in (self.paths.output_dir,self.paths.artifact_dir)]
        sources=[Path(p).resolve() for p in self.paths.templates.values()]
        for dst in destinations:
            if any(dst==s.parent or dst.is_relative_to(s.with_suffix('')) or s.is_relative_to(dst) for s in sources):
                raise ValueError('Source and output locations overlap')
        if destinations[0]==destinations[1] or any(a.is_relative_to(b) for a,b in (destinations,destinations[::-1])):
            raise ValueError('Lightweight and bulk artifact directories must be separate')
        if live:
            for s,p in self.paths.templates.items():
                x=Path(p)
                if not x.is_file() or not x.with_suffix('').is_dir():
                    raise ValueError(f'Missing complete {s} template: {x}')
            if not Path(self.paths.cst_library_path).is_dir():
                raise ValueError('Explicit CST library path or CST_PYTHON_LIB required')


def load_config(path: str | Path) -> Config:
    """Load YAML with strict field ownership and relative path resolution."""
    path=Path(path).resolve()
    raw=yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    if not isinstance(raw,dict) or set(raw)!={'workflow_6'}: raise ValueError('Expected workflow_6 mapping')
    data=dict(raw['workflow_6'])
    for key,cls in [('paths',Paths),('physics',Physics),('reconstruction',Reconstruction),('search',Search),('runtime',Runtime),('results',Results)]:
        value=dict(data.get(key,{}))
        if key=='paths':
            def resolve(p):
                if not isinstance(p,str) or not p.strip():raise ValueError('Empty/non-string path')
                return str((path.parent / os.path.expandvars(p)).resolve())
            value['templates']={k:resolve(v) for k,v in value.get('templates',{}).items()}
            for n in ('output_dir','artifact_dir'):
                if n in value:value[n]=resolve(value[n])
            lib=value.get('cst_library_path') or os.environ.get('CST_PYTHON_LIB','')
            value['cst_library_path']=resolve(lib) if lib else ''
        data[key]=cls(**value)
    c=Config(**data);c.validate();return c
