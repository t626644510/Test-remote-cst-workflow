"""Typed records for the RF-CEM parametric vacuum geometry MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


AxisName = Literal["x", "y", "z"]


@dataclass(frozen=True)
class GeometryThresholds:
    """No-CST geometry validation thresholds in project units (mm).

    Baseline-difference severities are configurable because exploratory
    geometry generation should not be blocked merely for differing from the
    seed cavity.  Hard topology checks still live in ``occt_checker``.
    """

    bbox_abs_mm: float = 0.3
    bbox_rel: float = 0.002
    volume_rel: float = 0.01
    surface_area_rel: float = 0.01
    profile_rms_mm: float = 0.15
    profile_max_mm: float = 0.50
    key_dimension_abs_mm: float = 0.20
    local_blend_max_mm: float = 0.30
    baseline_difference_policy: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineInputs:
    appendix: Path
    output_dir: Path
    target_body_index: int = 0
    axis: AxisName = "z"
    deflection_mm: float = 0.25
    expert_prior: Path | None = None


@dataclass(frozen=True)
class BodySelection:
    mode: str
    body_ref: str
    body_index: int
    confidence: float
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AxisReport:
    requested_axis: AxisName
    detected_axis: str
    accepted: bool
    confidence: float
    max_section_delta_mm: float
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeatureBinding:
    feature_id: str
    feature_type: str
    geometry_refs: list[str]
    parameter_ids: list[str]
    segment_ids: list[str]
    confidence: float
    provenance: str


def to_plain(value: Any) -> Any:
    """Return JSON-serializable plain data for dataclass-heavy records."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    return value
