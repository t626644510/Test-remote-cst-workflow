# Metric role definitions for the RF gun SAO workflow.
# Lightweight skeleton — local only, no imports from legacy workflow modules.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    raw_config : dict or None
        The full config entry dict (for future threshold/report_only use).
    """
    name: str
    role: MetricRole = MetricRole.OPTIMIZE
    enabled: bool = True
    raw_config: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_metric_role_config(value: str | None) -> str:
    """Normalise a config role string to its canonical form.

    Returns ``"optimize"`` for ``None`` / missing.
    Raises ``ValueError`` for unknown roles.
    """
    return MetricRole.from_value(value).value


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
        specs.append(MetricSpec(
            name=name,
            role=role,
            enabled=enabled,
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
