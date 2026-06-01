# Metric role definitions for the RF gun SAO workflow.
# Lightweight skeleton — local only, no imports from legacy workflow modules.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class MetricRole(str, Enum):
    """Classification of a metric in the SAO objective vector.

    Maps directly to the legacy Workflow 3 role semantics but is
    defined locally — no import from legacy workflow modules.
    """
    OPTIMIZE = "optimize"
    THRESHOLD = "threshold"
    REPORT_ONLY = "report_only"

    @classmethod
    def from_value(cls, value: str | None) -> MetricRole:
        """Parse a config role string, defaulting to ``OPTIMIZE``.

        Parameters
        ----------
        value : str or None
            Raw role string from config (``None`` or missing → ``OPTIMIZE``).

        Returns
        -------
        MetricRole

        Raises
        ------
        ValueError
            If *value* is not ``None`` and not a recognised role.
        """
        if value is None:
            return cls.OPTIMIZE
        stripped = str(value).strip().lower()
        for member in cls:
            if member.value == stripped:
                return member
        raise ValueError(
            f"Unknown metric role: {value!r}. "
            f"Expected one of {[m.value for m in cls]}.",
        )

    @classmethod
    def accept_roles(cls) -> list[str]:
        return [m.value for m in cls]


@dataclass
class MetricSpec:
    """Declarative specification for one metric entry.

    Parameters
    ----------
    name : str
        Metric name (matches the CST objective name).
    role : MetricRole
        Classification for the SAO objective vector.
    enabled : bool
        Whether the metric is active in the workflow.
    threshold : float or None
        Threshold value for threshold-role metrics.
    sigma : float or None
        Width parameter for threshold penalty (must be positive when used).
    direction : str
        ``"less_than"`` or ``"greater_than"`` — meaning of the threshold.
    report_as : str or None
        Optional output-name alias (not yet wired into live extraction).
    raw_config : dict or None
        The full config entry dict.
    """
    name: str
    role: MetricRole = MetricRole.OPTIMIZE
    enabled: bool = True
    threshold: float | None = None
    sigma: float | None = None
    direction: str = "less_than"
    report_as: str | None = None
    raw_config: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Direction validation
# ---------------------------------------------------------------------------

_ACCEPTED_DIRECTIONS = frozenset({"less_than", "greater_than"})


def _validate_direction(value: str) -> str:
    """Normalise and validate a threshold direction string."""
    v = str(value).strip().lower()
    if v not in _ACCEPTED_DIRECTIONS:
        raise ValueError(
            f"Unknown threshold direction: {value!r}. "
            f"Expected one of {sorted(_ACCEPTED_DIRECTIONS)}.",
        )
    return v


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def normalize_metric_role(value: str | None) -> str:
    """Normalise a config role string to its canonical form.

    Returns ``"optimize"`` for ``None`` / missing.
    Raises ``ValueError`` for unknown roles.

    This is an alias for ``parse_metric_role_config``.
    """
    return parse_metric_role_config(value)


def parse_metric_role_config(value: str | None) -> str:
    """Normalise a config role string to its canonical form.

    Returns ``"optimize"`` for ``None`` / missing.
    Raises ``ValueError`` for unknown roles.
    """
    return MetricRole.from_value(value).value


def _resolve_threshold_field(
    entry: dict[str, Any],
    field_name: str,
) -> Any | None:
    """Read *field_name* from the entry top-level, falling back to
    ``mode_params.<field_name>`` if present.
    """
    if field_name in entry:
        return entry[field_name]
    mode_params = entry.get("mode_params", {})
    if isinstance(mode_params, dict) and field_name in mode_params:
        return mode_params[field_name]
    if field_name == "direction":
        return "less_than"
    return None


def build_metric_specs(
    objective_entries: list[dict[str, Any]],
) -> list[MetricSpec]:
    """Convert raw config objective entries into ``MetricSpec`` list.

    Parameters
    ----------
    objective_entries : list[dict]
        Raw YAML objective entries (as in ``config.yaml``).

    Returns
    -------
    list[MetricSpec]
    """
    specs: list[MetricSpec] = []
    for entry in objective_entries:
        name = entry.get("name", "")
        if not name:
            continue
        enabled = bool(entry.get("enabled", True))
        role = MetricRole.from_value(entry.get("role"))

        # Parse threshold fields for any role (only meaningful for THRESHOLD)
        threshold = _resolve_threshold_field(entry, "threshold")
        sigma = _resolve_threshold_field(entry, "sigma")
        direction = _validate_direction(
            _resolve_threshold_field(entry, "direction") or "less_than",
        )
        report_as = entry.get("report_as")

        specs.append(MetricSpec(
            name=name,
            role=role,
            enabled=enabled,
            threshold=float(threshold) if threshold is not None else None,
            sigma=float(sigma) if sigma is not None else None,
            direction=direction,
            report_as=str(report_as) if report_as is not None else None,
            raw_config=dict(entry),
        ))
    return specs


def objective_metric_names(specs: list[MetricSpec]) -> list[str]:
    """Return metric names that participate in the objective vector.

    Includes ``OPTIMIZE`` and ``THRESHOLD`` roles.
    Excludes disabled entries and ``REPORT_ONLY``.
    """
    return [
        s.name for s in specs
        if s.enabled and s.role in (MetricRole.OPTIMIZE, MetricRole.THRESHOLD)
    ]


def report_metric_names(specs: list[MetricSpec]) -> list[str]:
    """Return metric names that are ``REPORT_ONLY`` (diagnostics only)."""
    return [
        s.name for s in specs
        if s.enabled and s.role == MetricRole.REPORT_ONLY
    ]


def optimize_metric_names(specs: list[MetricSpec]) -> list[str]:
    """Return metric names with role ``OPTIMIZE``."""
    return [
        s.name for s in specs
        if s.enabled and s.role == MetricRole.OPTIMIZE
    ]


def threshold_metric_names(specs: list[MetricSpec]) -> list[str]:
    """Return metric names with role ``THRESHOLD``."""
    return [
        s.name for s in specs
        if s.enabled and s.role == MetricRole.THRESHOLD
    ]


# ---------------------------------------------------------------------------
# Threshold penalty computation
# ---------------------------------------------------------------------------


def _safe_sigma(sigma: float | None) -> float:
    """Return a positive sigma value for threshold penalty computation."""
    if sigma is None or not np.isfinite(sigma):
        return 1.0
    return max(abs(float(sigma)), 1e-12)


def compute_threshold_penalty(spec: MetricSpec, value: float) -> float:
    """Compute the threshold penalty for a single metric value.

    Parameters
    ----------
    spec : MetricSpec
        The metric specification (must have ``role == THRESHOLD``).
    value : float
        The raw physics value for this metric.

    Returns
    -------
    float
        Penalty in ``[0.0, 1.0]``.

    Raises
    ------
    TypeError
        If ``spec.role`` is not ``THRESHOLD``.

    Notes
    -----
    Legacy Workflow 3 formula, adapted::

        direction == "less_than":
            value <= threshold  →  0.0
            value >  threshold  →  1.0 - exp(-(value - threshold) / sigma)

        direction == "greater_than":
            value >= threshold  →  0.0
            value <  threshold  →  1.0 - exp(-(threshold - value) / sigma)

    Non-finite *value* returns 1.0.
    """
    if spec.role != MetricRole.THRESHOLD:
        raise TypeError(
            f"compute_threshold_penalty called on a "
            f"'{spec.role.value}' metric (name={spec.name!r}). "
            f"Expected role 'threshold'.",
        )

    if not np.isfinite(value):
        return 1.0

    threshold = float(spec.threshold) if spec.threshold is not None else 0.0
    sigma = _safe_sigma(spec.sigma)

    if spec.direction == "less_than":
        if value <= threshold:
            return 0.0
        delta = (value - threshold) / sigma
    elif spec.direction == "greater_than":
        if value >= threshold:
            return 0.0
        delta = (threshold - value) / sigma
    else:
        raise ValueError(
            f"Unexpected direction {spec.direction!r} in threshold penalty. "
            f"This should have been validated during spec construction.",
        )

    penalty = 1.0 - np.exp(-delta)
    return float(np.clip(penalty, 0.0, 1.0))
