"""WF7 execution contract: geometry mm/degrees, RF quantities in SI units."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any

NAMES = ('selfangle1', 'Lin1', 'projection1', 'FolkHeight', 'DownHeight',
         'selfangle2', 'Lin2', 'projection2', 'FolkHeight2',
         'PortR1', 'SPortR1', 'SPortR2', 'TopGap', 'TopGap2', 'coaxr2')
BOUNDS = dict(zip(NAMES, ((0.,180.),(1.,50.),(5.43,19.57),(5.43,30.),(50.,180.),
                         (0.,180.),(1.,50.),(5.43,19.57),(5.43,30.),
                         (2.03,19.99),(2.02,19.98),(2.01,19.97),(5.,45.),(5.,45.),(5.430001,21.99))))

@dataclass(frozen=True)
class Paths:
    """Explicit local paths. No remote station or implicit source overwrite."""
    template: str
    output_dir: str
    artifact_dir: str
    gpu_python: str
    wakis_source: str
    cst_library_path: str

@dataclass(frozen=True)
class Physics:
    """Hz, ohm, ohm/metre, peak volts, CW watts; beta=1 and copper 5.8e7 S/m."""
    band_hz: tuple[float, float] = (550e6, 1462734895.6992505)
    longitudinal_limit: float = 1800.
    transverse_limit: float = 150000.
    leakage_limit_w: float = 75.
    voltage_peak_v: float = 500000.
    power_reference_w: float = 150.
    thermal_band_hz: tuple[float, float] = (498e6, 502e6)
    sigma_m: float = .07
    wake_length_m: float = 35.
    offset_m: float = .002
    beta: float = 1.
    conductivity_s_per_m: float = 5.8e7
    thermal_solids: tuple[str, str] = ('component5:solid1', 'component6:solid1')
    thermal_z_range_mm: tuple[float, float] = (-235.050544, 235.050544)
    power_relative_uncertainty_floor: float = .20

@dataclass(frozen=True)
class Reconstruction:
    """Unchanged WF6 measured-tail/local-consensus reconstruction controls."""
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
    pencil_ranks: tuple[int, ...] = (24, 32, 48)
    pencil_spacing_m: float = .02
    pencil_rows: int = 500
    pole_min_hz: float = 100e6
    frequency_width_hz: float = 10e6
    decay_bounds_per_m: tuple[float, float] = (1e-9, 4.)
    holdout_fraction: float = .8
    bound_tail_fraction: float = .05

@dataclass(frozen=True)
class Search:
    """Round cap counts active wall seconds; a running stage drains at the cap."""
    hours: float = 48.
    transverse_admission_ohm: float = 3000.
    exploration_fraction: float = .20
    initial_points: int = 16
    seed: int = 20261014
    pool: int = 2048
    gp_min_samples: int = 6
    radius: float = .25
    min_radius: float = .05
    max_radius: float = .5
    bound_clearance_mm: float = .01
    fixed_radius_mm: float = 25.
    native_relative_noise: float = .02
    history_relative_noise: float = .20
    uncertain_log_noise: float = math.log(1.5)
    unbounded_log_noise: float = math.log(3.)
    absolute_noise_fraction: float = .05
    unbounded_max_scale_ratio: float = 4.
    unbounded_max_relative: float = 3.
    acquisition_beta: float = .75
    radius_successes: int = 2
    radius_failures: int = 3
    radius_expand: float = 1.5
    radius_contract: float = .7

@dataclass(frozen=True)
class Runtime:
    """One GPU plus at most one CPU preparation; seconds/GiB, wall-time budget."""
    heartbeat_s: float = 15.
    mesh_timeout_s: float = 900.
    solve_timeout_s: float = 2700.
    postprocess_timeout_s: float = 1800.
    retries: int = 2
    start_free_ram_gib: float = 16.
    running_free_ram_gib: float = 6.
    minimum_free_disk_gib: float = 15.
    port_layer_m: float = .02
    precision: str = 'float32'
    copper_terms: int = 96
    upstream_revision: str = 'e0d8f2f1e0e2b58e0f675ded71b32917a18dadfe'
    prefetch: bool = True
    prefetch_free_ram_gib: float = 24.
    prefetch_running_free_ram_gib: float = 12.

@dataclass(frozen=True)
class Config:
    """Fifteen coordinates; the revised fixed geometry has a distinct contract."""
    paths: Paths
    physics: Physics = field(default_factory=Physics)
    reconstruction: Reconstruction = field(default_factory=Reconstruction)
    search: Search = field(default_factory=Search)
    runtime: Runtime = field(default_factory=Runtime)
    bounds: dict[str, tuple[float, float]] = field(default_factory=lambda: BOUNDS.copy())
    fixed_parameters: dict[str, float] = field(default_factory=lambda: dict(UpperHeight1=170., UpperHeight2=170., DownHeight2=-30.))
    port_outer_policy: str = 'follow_wall'
    port_wall_mm: float = 2.
    fixed_port_outer_mm: float = 31./3.
    cooling_clearance_mm: float = 0.
    coax_inner_radius_mm: float = 5.43
    compact_retention: bool = False
    retained_best_count: int = 5
    retained_candidate_ids: tuple[str, ...] = ('candidate_0000',)

    @property
    def active_names(self) -> tuple[str, ...]:
        return NAMES

    def as_dict(self) -> dict[str, Any]:
        result=asdict(self)
        # Preserve existing round digests for the unchanged, opt-out policy.
        defaults=dict(cooling_clearance_mm=0.,coax_inner_radius_mm=5.43,
                      compact_retention=False,retained_best_count=5,
                      retained_candidate_ids=('candidate_0000',))
        for key,value in defaults.items():
            if result[key]==value or key=='retained_candidate_ids' and tuple(result[key])==value:
                result.pop(key)
        return result

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.as_dict(),sort_keys=True,allow_nan=False).encode()).hexdigest()

    def validate(self, *, live: bool = False) -> None:
        """Fail before process launch on ambiguity, unsafe ownership or drift."""
        if set(self.bounds)!=set(NAMES) or len(NAMES)!=15:
            raise ValueError('WF7 requires exactly fifteen active coordinates')
        if self.fixed_parameters!=dict(UpperHeight1=170.,UpperHeight2=170.,DownHeight2=-30.):
            raise ValueError('Revised geometry fixes UpperHeight=170 mm and DownHeight2=-30 mm')
        if not 50. <= self.bounds['DownHeight'][0] < self.bounds['DownHeight'][1] <= 180.:
            raise ValueError('DownHeight search domain must lie inside 50 to 180 mm')
        if (not math.isfinite(self.cooling_clearance_mm) or self.cooling_clearance_mm < 0
                or self.coax_inner_radius_mm != 5.43 or self.retained_best_count < 1):
            raise ValueError('Invalid reviewed cooling/retention policy')
        if any(not n.startswith('candidate_') or not n[10:].isdigit() for n in self.retained_candidate_ids):
            raise ValueError('Invalid raw-retention candidate id')
        for n,(lo,hi) in self.bounds.items():
            if lo < BOUNDS[n][0] or hi > BOUNDS[n][1]:
                raise ValueError('Search domain must remain inside reviewed physical domain')
        for n,(lo,hi) in self.bounds.items():
            if not all(map(math.isfinite,(lo,hi))) or not lo<hi:
                raise ValueError(f'Invalid bounds: {n}')
        if self.port_outer_policy not in ('unconfirmed','fixed','follow_wall'):
            raise ValueError('Unknown PortR2 policy')
        if live and self.port_outer_policy=='unconfirmed':
            raise ValueError('PortR2 ownership decision is pending')
        p=self.physics;r=self.reconstruction;s=self.search
        if not (0<p.band_hz[0]<p.band_hz[1] and 0<p.thermal_band_hz[0]<p.thermal_band_hz[1]):
            raise ValueError('Invalid frequency bands in Hz')
        if p.beta!=1 or p.sigma_m!=.07 or p.wake_length_m!=35 or p.offset_m!=.002:
            raise ValueError('Unapproved excitation/tail change')
        if tuple(p.thermal_solids)!=('component5:solid1','component6:solid1'):
            raise ValueError('Only the two requested solid1 surfaces may count')
        if s.hours!=48 or s.transverse_admission_ohm<p.longitudinal_limit:
            raise ValueError('Invalid budget/admission contract')
        if not 0<s.exploration_fraction<1 or not 0<s.min_radius<=s.radius<=s.max_radius<=1:
            raise ValueError('Invalid exploration policy')
        if not (0<s.uncertain_log_noise<=s.unbounded_log_noise and 0<s.absolute_noise_fraction<1
                and s.unbounded_max_scale_ratio>1 and s.unbounded_max_relative>=1
                and 0<=s.acquisition_beta<=3 and s.radius_successes>=1 and s.radius_failures>=1
                and s.radius_expand>1 and 0<s.radius_contract<1):
            raise ValueError('Invalid robust search/trust-region policy')
        if self.runtime.prefetch_free_ram_gib<self.runtime.start_free_ram_gib:
            raise ValueError('Overlapped preparation needs at least the ordinary RAM reserve')
        if not self.runtime.running_free_ram_gib<self.runtime.prefetch_running_free_ram_gib<self.runtime.prefetch_free_ram_gib:
            raise ValueError('Prefetch must release memory before the foreground guard')
        if not (0<r.max_error<1 and 0<r.min_correlation<=1 and 0<r.peak_spread<1):
            raise ValueError('Invalid quality thresholds')
        if max(r.starts_m)>=p.wake_length_m or r.pencil_spacing_m>=299792458./(2*(p.band_hz[1]+r.frequency_width_hz)):
            raise ValueError('Reconstruction would omit the tail or alias')
        if p.power_relative_uncertainty_floor<.20:
            raise ValueError('Power approximation uncertainty cannot be hidden')
        if self.runtime.precision!='float32' or self.runtime.copper_terms!=96:
            raise ValueError('Frozen fast backend precision/copper law changed')
        paths=[Path(v).absolute() for v in (self.paths.template,self.paths.output_dir,self.paths.artifact_dir)]
        source,out,bulk=paths
        for dest in (out,bulk):
            if source==dest or source.is_relative_to(dest) or dest.is_relative_to(source.with_suffix('')):
                raise ValueError('Output overlaps source template')
        if out==bulk or out.is_relative_to(bulk) or bulk.is_relative_to(out):
            raise ValueError('Lightweight and bulk evidence roots must be separate')
        if live:
            for f in (source,Path(self.paths.gpu_python)):
                if not f.is_file():raise ValueError(f'Missing runtime input: {f}')
            for d in (source.with_suffix(''),Path(self.paths.wakis_source),Path(self.paths.cst_library_path)):
                if not d.is_dir():raise ValueError(f'Missing runtime directory: {d}')

def load_config(path: str | Path) -> Config:
    """Load JSON with strict dataclass field ownership, without silent defaults."""
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    for name,cls in (('paths',Paths),('physics',Physics),('reconstruction',Reconstruction),('search',Search),('runtime',Runtime)):
        data[name]=cls(**data.get(name,{}))
    value=Config(**data);value.validate();return value
