"""Separate search estimates from qualified feasibility (SI RF quantities)."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from typing import Mapping
from .config import Config

METRICS = ('longitudinal', 'transverse_x', 'heat_1', 'heat_2', 'leak_2', 'leak_3')

@dataclass(frozen=True)
class Observation:
    """Heuristic model sensitivity, never a calibrated confidence interval.

    Values/limits use ohm, ohm/metre or CW watts at 500 kV peak. None means
    unknown; it must not become zero or a synthetic failed-point penalty.
    """
    estimate: float
    relative_uncertainty: float
    lower: float | None = None
    upper: float | None = None
    qualified: bool = False
    full_coverage: bool = True
    contradictory: bool = False
    source: str = 'native'

    def __post_init__(self):
        for value in (self.estimate, self.relative_uncertainty):
            if not math.isfinite(value) or value < 0:raise ValueError('Invalid observation')
        if self.source not in ('native', 'reference'):raise ValueError('Unknown observation provenance')
        if self.lower is not None and (not math.isfinite(self.lower) or not 0 <= self.lower <= self.estimate):
            raise ValueError('Invalid lower sensitivity envelope')
        if self.upper is not None and (not math.isfinite(self.upper) or self.upper < self.estimate):
            raise ValueError('Invalid upper sensitivity envelope')
        if self.qualified and (not self.full_coverage or self.upper is None or self.contradictory):
            raise ValueError('Qualification requires coverage and bounded, consistent evidence')

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def search_eligible(self) -> bool:
        return self.source == 'native' and self.full_coverage

    @property
    def ranking_value(self) -> float:
        # An unbounded penalty is explicitly NOT a physical upper bound.
        return self.upper if self.upper is not None else self.estimate*(1+max(1.,self.relative_uncertainty))

    def below(self, threshold: float) -> bool:
        return self.qualified and self.upper is not None and self.upper <= threshold

def from_reconstruction(summary: dict) -> Observation | None:
    """Use full-band reconstructed peaks; direct FT remains diagnostic only."""
    p=summary.get('diagnostics',{}).get('reconstructed_peak',{})
    if p.get('estimate') is None or not p.get('full_band_coverage'):return None
    return Observation(estimate=p['estimate'],relative_uncertainty=p['relative_uncertainty'],
        lower=p.get('lower'),upper=p.get('upper'),qualified=bool(p.get('qualified')),
        full_coverage=True,contradictory=bool(p.get('contradictory_evidence')))

def transverse_admission(longitudinal: Observation | None, config: Config, *, forced: bool) -> bool:
    """3000-ohm broad gate; forced exploration may cross unresolved/high gates."""
    if forced:return True
    return bool(longitudinal and longitudinal.search_eligible and not longitudinal.contradictory
                and longitudinal.upper is not None
                and longitudinal.upper <= config.search.transverse_admission_ohm)

def feasibility(obs: Mapping[str,Observation], config: Config) -> dict:
    """Never call X-only screening a measured full transverse matrix."""
    p=config.physics
    limits={'longitudinal':p.longitudinal_limit,'transverse_x':p.transverse_limit,
            'leak_2':p.leakage_limit_w,'leak_3':p.leakage_limit_w}
    missing=[name for name in METRICS if name not in obs]
    passes={k:(k in obs and obs[k].below(v)) for k,v in limits.items()}
    # Leakage is strictly less than 75 W, as requested.
    for k in ('leak_2','leak_3'):
        passes[k]=passes[k] and obs[k].upper < limits[k]
    return dict(qualified_X_screening=not missing and all(passes.values())
                and all(obs[k].qualified for k in ('heat_1','heat_2')),
                full_transverse_feasibility=False,missing=missing,passes=passes,
                scope='X drive column only; Y remains unmeasured until explicitly evaluated')
