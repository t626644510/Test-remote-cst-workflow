"""Typed records for RF-CEM 500 MHz parametric optimization scans."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EvaluationStatus(str, Enum):
    """Evaluation status for RF-CEM parametric optimization."""

    SUCCESS = "SUCCESS"
    GEOMETRY_INVALID = "GEOMETRY_INVALID"
    POSTPROCESS_TEMPLATE_MISSING = "POSTPROCESS_TEMPLATE_MISSING"
    SOLVER_NOT_RUN = "SOLVER_NOT_RUN"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass(frozen=True)
class EvaluationRecord:
    """One no-CST or live-CST evaluation record."""

    index: int
    status: EvaluationStatus
    parameter_values: dict[str, float]
    objective_values: dict[str, float] = field(default_factory=dict)
    generated_package: str = ""
    generated_step: str = ""
    geometry_validation: str = ""
    cst_payload: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return JSON-serializable data."""
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
