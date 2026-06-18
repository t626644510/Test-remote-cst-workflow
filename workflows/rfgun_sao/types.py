from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class EvaluationStatus(Enum):
    """Classification of a WF1 evaluation outcome.

    Replicated from the shared recovery types module to decouple
    ``rfgun_sao`` from the shared workflow module.
    """
    SUCCESS = "success"
    PHYSICS_INVALID = "physics_invalid"
    FREQUENCY_GATE = "frequency_gate"
    SOLVER_FAILED = "solver_failed"
    COM_LOST = "com_lost"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class EvaluationResult:
    """One evaluation record for retry handler and checkpoint.

    Replicated from ``legacy workflow types`` to decouple
    ``rfgun_sao`` from the legacy workflow module.

    Attributes
    ----------
    status : EvaluationStatus
    error : str
    f0_ghz : float
        Resonant frequency from the calibration solve (GHz).
    raw_metrics : dict[str, float] | None
    objective_values : dict[str, float] | None
    penalty_values : dict[str, float] | None
    diagnostics : dict[str, Any] | None
        Report-only metric values for diagnostic / side-channel use.
    elapsed_s : float
    """
    status: EvaluationStatus = EvaluationStatus.UNKNOWN_ERROR
    error: str = ""
    f0_ghz: float = np.nan
    frequency_gate_passed: bool = False
    raw_metrics: dict[str, float] | None = None
    objective_values: dict[str, float] | None = None
    penalty_values: dict[str, float] | None = None
    diagnostics: dict[str, Any] | None = None
    pass_log: dict[str, Any] | None = None
    elapsed_s: float = 0.0

    @property
    def solver_ok(self) -> bool:
        return self.status == EvaluationStatus.SUCCESS
