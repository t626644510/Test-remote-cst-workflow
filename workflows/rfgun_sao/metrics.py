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
    GATE = "gate"

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
        raw_direction = _resolve_threshold_field(entry, "direction") or "less_than"
        if role in (MetricRole.THRESHOLD, MetricRole.GATE):
            direction = _validate_direction(raw_direction)
        else:
            direction = str(raw_direction).strip().lower()
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


def gate_metric_names(specs: list[MetricSpec]) -> list[str]:
    """Return metric names with role ``GATE``."""
    return [
        s.name for s in specs
        if s.enabled and s.role == MetricRole.GATE
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


# ---------------------------------------------------------------------------
# Gate pass/fail helpers
# ---------------------------------------------------------------------------


def compute_gate_pass(spec: MetricSpec, value: float) -> bool:
    """Evaluate whether a single gate metric value passes its constraint.

    Parameters
    ----------
    spec : MetricSpec
        The metric specification (must have ``role == GATE``).
    value : float
        The raw physics value for this metric.

    Returns
    -------
    bool
        ``True`` if the value passes the gate constraint, ``False`` otherwise.

    Raises
    ------
    TypeError
        If ``spec.role`` is not ``GATE``.

    Notes
    -----
    - Non-finite *value* → ``False``.
    - Missing or non-finite *threshold* → ``False``.
    - ``"less_than"``: pass if ``value <= threshold``.
    - ``"greater_than"``: pass if ``value >= threshold``.
    - *sigma* is parsed for future use but not used in pass/fail.
    """
    if spec.role != MetricRole.GATE:
        raise TypeError(
            f"compute_gate_pass called on a "
            f"'{spec.role.value}' metric (name={spec.name!r}). "
            f"Expected role 'gate'.",
        )

    if not np.isfinite(value):
        return False

    threshold = spec.threshold
    if threshold is None or not np.isfinite(threshold):
        return False

    threshold_f = float(threshold)

    if spec.direction == "less_than":
        return bool(value <= threshold_f)
    elif spec.direction == "greater_than":
        return bool(value >= threshold_f)
    else:
        raise ValueError(
            f"Unexpected direction {spec.direction!r} in gate pass/fail. "
            f"This should have been validated during spec construction.",
        )


def compute_gate_results(
    metric_specs: list[MetricSpec],
    raw_metrics: dict[str, float],
) -> dict[str, bool]:
    """Evaluate gate pass/fail for all enabled ``GATE`` specs.

    Parameters
    ----------
    metric_specs : list[MetricSpec]
        All metric specifications (in config order).
    raw_metrics : dict[str, float]
        Raw physics values keyed by metric name.

    Returns
    -------
    dict[str, bool]
        Gate results keyed by output name (``report_as`` or source name).

    Raises
    ------
    ValueError
        If two ``GATE`` specs would produce the same output key.

    Notes
    -----
    - Only enabled ``GATE`` specs are included.
    - Missing raw values produce ``False``.
    - Duplicate output keys raise ``ValueError``.
    - *raw_metrics* is not mutated.
    """
    from collections import Counter

    candidates: list[tuple[str, bool]] = []
    for spec in metric_specs:
        if not spec.enabled or spec.role != MetricRole.GATE:
            continue
        output_key = str(spec.report_as or spec.name)
        passed = compute_gate_pass(
            spec, raw_metrics.get(spec.name, np.nan),
        )
        candidates.append((output_key, passed))

    keys = [k for k, _ in candidates]
    dupes = {k for k, cnt in Counter(keys).items() if cnt > 1}
    if dupes:
        raise ValueError(
            f"Duplicate gate result key(s): {sorted(dupes)}. "
            f"Use 'report_as' to disambiguate.",
        )

    return dict(candidates)


def summarize_gate_results(
    gate_results: dict[str, bool],
) -> tuple[bool, str]:
    """Summarise gate pass/fail results into a single pass/fail + error string.

    Parameters
    ----------
    gate_results : dict[str, bool]
        Output key → pass (True) / fail (False).

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` if empty or all pass.
        ``(False, "gate_reject:<key1,key2>")`` if any fail.
        Keys are sorted for deterministic order.
    """
    if not gate_results:
        return True, ""
    failing = sorted(k for k, v in gate_results.items() if not v)
    if not failing:
        return True, ""
    return False, "gate_reject:" + ",".join(failing)


# ---------------------------------------------------------------------------
# Role-based penalty computation
# ---------------------------------------------------------------------------


def compute_role_penalties(
    *,
    metric_specs: list[MetricSpec],
    objectives_by_name: dict[str, Any],
    raw_metrics: dict[str, float],
) -> dict[str, float]:
    """Compute penalties for all active metrics based on their role.

    Parameters
    ----------
    metric_specs : list[MetricSpec]
        All metric specifications (in config order).
    objectives_by_name : dict[str, ObjectiveFunction]
        Objective instances keyed by metric name (for ``optimize`` role).
    raw_metrics : dict[str, float]
        Raw physics values keyed by metric name.

    Returns
    -------
    dict[str, float]
        Penalty values keyed by source metric name, aligned with
        ``objective_metric_names(specs)``.  ``REPORT_ONLY`` metrics
        are excluded.

    Notes
    -----
    - ``OPTIMIZE``: delegates to ``obj.mode.compute(value)``.
    - ``THRESHOLD``: delegates to ``compute_threshold_penalty(spec, value)``.
    - ``REPORT_ONLY``: skipped (not returned).
    - Disabled specs are skipped.
    - Missing or non-finite raw values produce penalty ``1.0``.
    """
    penalties: dict[str, float] = {}
    for spec in metric_specs:
        if not spec.enabled:
            continue
        if spec.role in (MetricRole.REPORT_ONLY, MetricRole.GATE):
            continue

        raw_val = raw_metrics.get(spec.name, np.nan)

        if not np.isfinite(raw_val):
            penalties[spec.name] = 1.0
            continue

        if spec.role == MetricRole.OPTIMIZE:
            obj = objectives_by_name.get(spec.name)
            if obj is not None:
                penalties[spec.name] = float(obj.mode.compute(float(raw_val)))
            else:
                penalties[spec.name] = 1.0
        elif spec.role == MetricRole.THRESHOLD:
            penalties[spec.name] = compute_threshold_penalty(spec, float(raw_val))
        else:
            raise ValueError(
                f"Unexpected metric role {spec.role!r} for metric "
                f"{spec.name!r} in compute_role_penalties.",
            )

    return penalties


# ---------------------------------------------------------------------------
# Report-only diagnostic extraction
# ---------------------------------------------------------------------------


def report_only_output_names(specs: list[MetricSpec]) -> list[str]:
    """Return output names for ``REPORT_ONLY`` metrics.

    Uses ``spec.report_as`` if set, otherwise ``spec.name``.
    This may differ from ``report_metric_names(specs)`` which always
    returns the source metric name.
    """
    result: list[str] = []
    for spec in specs:
        if spec.enabled and spec.role == MetricRole.REPORT_ONLY:
            result.append(spec.report_as or spec.name)
    return result


def report_only_diagnostics(
    *,
    metric_specs: list[MetricSpec],
    raw_metrics: dict[str, float],
) -> dict[str, float]:
    """Extract diagnostics from ``raw_metrics`` for ``REPORT_ONLY`` specs.

    Parameters
    ----------
    metric_specs : list[MetricSpec]
        All metric specifications (in config order).
    raw_metrics : dict[str, float]
        Raw physics values keyed by metric name.

    Returns
    -------
    dict[str, float]
        Diagnostic values keyed by output name (``report_as`` or source name).

    Raises
    ------
    ValueError
        If two ``REPORT_ONLY`` specs would produce the same output key.

    Notes
    -----
    - Only enabled ``REPORT_ONLY`` specs are included.
    - Missing or non-finite raw values produce ``numpy.nan``.
    - ``OPTIMIZE`` and ``THRESHOLD`` roles are excluded.
    """
    from collections import Counter

    candidates: list[tuple[str, float]] = []
    for spec in metric_specs:
        if not spec.enabled or spec.role != MetricRole.REPORT_ONLY:
            continue
        output_key = str(spec.report_as or spec.name)
        raw_val = raw_metrics.get(spec.name, np.nan)
        if np.isfinite(raw_val):
            candidates.append((output_key, float(raw_val)))
        else:
            candidates.append((output_key, float(np.nan)))

    # Check for duplicate output keys
    keys = [k for k, _ in candidates]
    dupes = {k for k, count in Counter(keys).items() if count > 1}
    if dupes:
        raise ValueError(
            f"Duplicate report_only diagnostic key(s): {sorted(dupes)}. "
            f"Use 'report_as' to disambiguate.",
        )

    return dict(candidates)
