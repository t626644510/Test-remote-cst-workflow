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
    # None retains the exact conservative semantics of pre-v2 records/power.
    quality: str | None = None
    sensitive_upper: float | None = None
    consensus_main_lower: float | None = None
    non_dominant_sensitive: bool = False
    band_edge_unresolved: bool = False
    direct_evidence_peak: float | None = None
    quality_version: str | None = None
    search_scale_lower: float | None = None  # Noisy-trend scale only, NEVER an acceptance bound.

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
        if self.quality not in (None,'consensus','bounded_sensitive','unsupported'):
            raise ValueError('Unknown reconstruction quality')
        for value in (self.sensitive_upper,self.consensus_main_lower,self.direct_evidence_peak,self.search_scale_lower):
            if value is not None and (not math.isfinite(value) or value<0):raise ValueError('Invalid quality evidence')
        versions=('local-reconstructed-quality-v2','local-reconstructed-quality-v3')
        if self.search_scale_lower is not None and (self.quality_version not in versions
                or self.search_scale_lower>self.estimate):raise ValueError('Invalid search-only scale evidence')
        if self.non_dominant_sensitive and not (
            self.quality=='bounded_sensitive' and self.quality_version in versions
            and self.full_coverage and self.upper is not None and not self.contradictory
            and not self.band_edge_unresolved and self.sensitive_upper is not None
            and self.consensus_main_lower is not None and self.lower is not None
            and self.sensitive_upper<self.consensus_main_lower<=self.lower<=self.upper
        ):raise ValueError('GP exemption requires bounded non-dominance evidence')

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
        return self.acceptance(threshold) in ('qualified_pass','consensus_pass','envelope_pass')

    def acceptance(self, threshold: float) -> str:
        """Engineering decision, separate from numerical fit quality.

        Threshold uses the same ohm, ohm/m or CW W units as this observation.
        Bounded-sensitive windows require 10% headroom; this is not a CI.
        """
        from .peak_consensus import SENSITIVE_MARGIN
        if (not self.full_coverage or self.upper is None or self.band_edge_unresolved
                or self.quality=='unsupported'):return 'unresolved'
        if self.lower is not None and self.lower>threshold:return 'exceeds'
        if self.contradictory or (self.direct_evidence_peak is not None and self.direct_evidence_peak>threshold):
            return 'unresolved'
        if self.upper>threshold:return 'unresolved'
        if self.quality=='consensus':return 'consensus_pass'
        if self.quality=='bounded_sensitive':
            return ('envelope_pass' if self.sensitive_upper is not None
                    and self.sensitive_upper<=(1-SENSITIVE_MARGIN)*threshold else 'unresolved')
        return 'qualified_pass' if self.qualified else 'unresolved'

    @property
    def gp_quality_penalty_exempt(self) -> bool:
        """Only a proven non-dominant sensitive peak earns the extra exemption."""
        return self.non_dominant_sensitive

def from_reconstruction(summary: dict) -> Observation | None:
    """Use full-band reconstructed peaks; direct FT remains diagnostic only."""
    p=summary.get('diagnostics',{}).get('reconstructed_peak',{})
    if p.get('estimate') is None or not p.get('full_band_coverage'):return None
    return Observation(estimate=p['estimate'],relative_uncertainty=p['relative_uncertainty'],
        lower=p.get('lower'),upper=p.get('upper'),qualified=bool(p.get('qualified')),
        full_coverage=True,contradictory=bool(p.get('contradictory_evidence')),
        quality=p.get('quality'),sensitive_upper=p.get('sensitive_upper'),
        consensus_main_lower=p.get('consensus_main_lower'),
        non_dominant_sensitive=bool(p.get('non_dominant_sensitive')),
        band_edge_unresolved=bool(p.get('band_edge_unresolved')),
        direct_evidence_peak=p.get('direct_evidence_peak'),
        search_scale_lower=p.get('search_scale_lower'),
        quality_version=p.get('method') if p.get('quality') is not None else None)

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
    decisions={k:obs[k].acceptance(v) if k in obs else 'missing' for k,v in limits.items()}
    for k in ('leak_2','leak_3'):
        if k in obs and obs[k].upper==limits[k]:decisions[k]='unresolved'
    return dict(qualified_X_screening=not missing and all(passes.values())
                and all(obs[k].qualified for k in ('heat_1','heat_2')),
                full_transverse_feasibility=False,missing=missing,passes=passes,decisions=decisions,
                scope='X drive column only; Y remains unmeasured until explicitly evaluated')
