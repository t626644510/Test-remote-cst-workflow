"""Shared evaluation types used by all workflows.

Phase 11: ``RecoveryWorkflowEvaluator`` moved to
``workflows/rfgun_recovery/evaluator.py`` (WF3 package).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

# ── Lazy re-export for backward compat ─────────────────────────────────
_RecoveryWorkflowEvaluator = None
_clone_metric_specs = None


def _lazy_import_evaluator():
    """Deferred import to avoid circular: recovery → rfgun_recovery.evaluator."""
    global _RecoveryWorkflowEvaluator, _clone_metric_specs
    if _RecoveryWorkflowEvaluator is None:
        from workflows.rfgun_recovery.evaluator import (  # noqa: E402
            RecoveryWorkflowEvaluator as _RWE,
            clone_metric_specs as _CMS,
        )
        _RecoveryWorkflowEvaluator = _RWE
        _clone_metric_specs = _CMS
    return _RecoveryWorkflowEvaluator, _clone_metric_specs


@dataclass
class MetricSpec:
    """Configuration for one metric."""

    name: str
    role: str
    priority: int = 1
    enabled: bool = True
    report_as: str | None = None
    objective: Any | None = None
    threshold: float | None = None
    sigma: float | None = None
    direction: str = "less_than"
    obj_params: dict[str, Any] | None = None

    @property
    def output_name(self) -> str:
        return self.report_as or self.name


@dataclass
class FrequencyGate:
    """Early-rejection rule based on calibrated resonance."""

    enabled: bool = True
    target_ghz: float = 11.424
    max_abs_offset_mhz: float = 20.0

    @property
    def max_abs_offset_ghz(self) -> float:
        return self.max_abs_offset_mhz / 1000.0

    def accepts(self, f0_ghz: float) -> bool:
        return abs(float(f0_ghz) - self.target_ghz) <= self.max_abs_offset_ghz


class EvaluationStatus(Enum):
    """Classification of an evaluation outcome."""

    SUCCESS = "success"
    PHYSICS_INVALID = "physics_invalid"
    FREQUENCY_GATE = "frequency_gate"
    SOLVER_FAILED = "solver_failed"
    COM_LOST = "com_lost"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class EvaluationResult:
    """One evaluation record — canonical type shared across all workflows."""

    status: EvaluationStatus = EvaluationStatus.UNKNOWN_ERROR
    error: str = ""
    f0_ghz: float = np.nan
    frequency_gate_passed: bool = False
    raw_metrics: dict[str, float] | None = None
    objective_values: dict[str, float] | None = None
    penalty_values: dict[str, float] | None = None
    pass_log: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None
    elapsed_s: float = 0.0

    @property
    def solver_ok(self) -> bool:
        return self.status == EvaluationStatus.SUCCESS

    @solver_ok.setter
    def solver_ok(self, value: bool) -> None:
        pass
