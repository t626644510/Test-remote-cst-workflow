"""Workflow 1 evaluator -- single-project single-pass frequency-domain solver.

Canonical WF1 evaluator owned by the ``rfgun_sao`` workflow package.
Behaviour is identical to the original closure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup (must be before cst_optimization imports)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import logging
from typing import Any

import numpy as np

from cst_optimization.workflows.base_evaluator import BaseWorkflow1Evaluator
from workflows.rfgun_sao.metrics import (
    MetricSpec,
    compute_role_penalties,
    report_only_diagnostics,
)
from workflows.rfgun_sao.types import (
    EvaluationResult,
    EvaluationStatus as _ES,
)

_logger = logging.getLogger(__name__)


class Workflow1Evaluator(BaseWorkflow1Evaluator):
    """Single-pass frequency-domain CST evaluation for the RF gun cavity.

    Wraps one CST solve + result reading + physics post-processing +
    objective penalty computation.

    Parameters
    ----------
    connection : CSTConnection
        The active CST DesignEnvironment connection.
    project_path : str
        Path to the ``.cst`` file.
    solver_runner : SolverRunner
        Synchronous solver runner.
    objectives : list[ObjectiveFunction]
        Objective instances (used for penalty computation via ``.mode``).
    param_names : list[str]
        Ordered parameter names from the config.
    metric_names : list[str]
        Ordered metric (objective) names.
    """

    def __init__(
        self,
        connection,
        project_path: str,
        solver_runner,
        objectives: list,
        param_names: list[str],
        metric_names: list[str],
        metric_specs: list[MetricSpec] | None = None,
    ) -> None:
        self._conn = connection
        self._project_path = project_path
        self._project_dir = project_path.rsplit(".", 1)[0]
        self._runner = solver_runner
        self._objectives = objectives
        self._param_names = list(param_names)
        self._metric_names = list(metric_names)
        self._objectives_by_name = {obj.name: obj for obj in objectives}
        if metric_specs is not None:
            self._metric_specs = metric_specs
        else:
            # Fallback: treat all metric_names as optimize specs
            from workflows.rfgun_sao.metrics import MetricRole, MetricSpec
            self._metric_specs = [
                MetricSpec(name=n, role=MetricRole.OPTIMIZE)
                for n in metric_names
            ]
        self._last_diagnostics: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Reconnect hook
    # ------------------------------------------------------------------

    def on_reconnect(self, new_conn) -> None:
        """Replace the internal connection reference after retry reconnect."""
        self._conn = new_conn

    # ------------------------------------------------------------------
    # Diagnostics accessor
    # ------------------------------------------------------------------

    def last_diagnostics(self) -> dict[str, float]:
        """Return report-only diagnostics from the most recent evaluation.

        Returns an empty dict if no evaluation has succeeded or if the
        last evaluation failed before diagnostics were computed.
        """
        return dict(self._last_diagnostics)

    # ------------------------------------------------------------------
    # Main evaluation
    # ------------------------------------------------------------------

    def evaluate_single_pass(
        self,
        param_dict: dict[str, float],
        iteration: int,
    ) -> tuple[dict[str, float], dict[str, float], bool, _ES, str]:
        """Run one CST simulation (delegates to shared base class)."""
        self._last_diagnostics = {}
        raw_metrics, penalties, solver_ok, status, error = (
            super().evaluate_single_pass(param_dict, iteration, _ES)
        )
        if solver_ok:
            self._last_diagnostics = report_only_diagnostics(
                metric_specs=self._metric_specs,
                raw_metrics=raw_metrics,
            )
        return raw_metrics, penalties, solver_ok, status, error

    def _compute_penalties(self, raw_metrics: dict[str, float]) -> dict[str, float]:
        """Role-aware penalty computation (SAO version)."""
        return compute_role_penalties(
            metric_specs=self._metric_specs,
            objectives_by_name=self._objectives_by_name,
            raw_metrics=raw_metrics,
        )

    # ------------------------------------------------------------------
    # Retry adapter
    # ------------------------------------------------------------------

    def adapt_for_retry(
        self, params: np.ndarray, iteration: int,
    ) -> EvaluationResult:
        """Delegate to base class shared implementation."""
        return super().adapt_for_retry(params, iteration, EvaluationResult, _ES)

    def _extra_result_fields(self) -> dict[str, Any]:
        """Include diagnostics in evaluation result."""
        return {"diagnostics": dict(self._last_diagnostics)}

