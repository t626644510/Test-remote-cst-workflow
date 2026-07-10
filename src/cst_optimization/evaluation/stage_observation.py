"""Shared stage-observation contracts for database warm starts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageCandidateStatus(str, Enum):
    """Taxonomy for one candidate's outcome inside a search stage."""

    COMPLETED = "completed"
    GATE_REJECTED = "gate_rejected"
    CALIBRATION_FAILED = "calibration_failed"
    SOLVER_FAILED = "solver_failed"
    TRANSIENT_FAILED = "transient_failed"
    UNKNOWN_FAILED = "unknown_failed"
    DATABASE_REUSED = "database_reused"


@dataclass
class StageObservation:
    """One physical-space candidate observation supplied to stage logic."""

    x: list[float]
    status: StageCandidateStatus = StageCandidateStatus.UNKNOWN_FAILED
    objective_value: float | None = None
    gate_pass: bool | None = None
    calibration_pass: bool | None = None
    solver_ok: bool | None = None
    retry_attempts: int = 0
    reused: bool = False
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
