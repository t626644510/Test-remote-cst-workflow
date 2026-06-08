"""Workflow 1 evaluator -- single-project single-pass frequency-domain solver.

Reference implementation owned by the ``rfgun_single_pass`` workflow package.
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
from cst_optimization.workflows.recovery import (
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
    ) -> None:
        self._conn = connection
        self._project_path = project_path
        self._project_dir = project_path.rsplit(".", 1)[0]
        self._runner = solver_runner
        self._objectives = objectives
        self._param_names = list(param_names)
        self._metric_names = list(metric_names)

    # ------------------------------------------------------------------
    # Reconnect hook
    # ------------------------------------------------------------------

    def on_reconnect(self, new_conn) -> None:
        """Replace the internal connection reference after retry reconnect."""
        self._conn = new_conn

    # ------------------------------------------------------------------
    # Main evaluation
    # ------------------------------------------------------------------

    def evaluate_single_pass(
        self,
        param_dict: dict[str, float],
        iteration: int,
    ) -> tuple[dict[str, float], dict[str, float], bool, _ES, str]:
        """Delegate to base class shared physics evaluation."""
        return super().evaluate_single_pass(param_dict, iteration, _ES)

    def _compute_penalties(self, raw_metrics: dict[str, float]) -> dict[str, float]:
        """Simple per-objective penalty computation (single_pass reference)."""
        penalties: dict[str, float] = {}
        for obj in self._objectives:
            val = raw_metrics.get(obj.name, np.nan)
            penalties[obj.name] = (
                float(obj.mode.compute(float(val))) if np.isfinite(val) else 1.0
            )
        return penalties

    # ------------------------------------------------------------------
    # Retry adapter
    # ------------------------------------------------------------------

    def adapt_for_retry(
        self, params: np.ndarray, iteration: int,
    ) -> EvaluationResult:
        """Wrap ``evaluate_single_pass`` for ``EvaluationRetryHandler``.

        Parameters
        ----------
        params : np.ndarray
            Physical-space parameter vector.
        iteration : int
            Evaluation index.

        Returns
        -------
        EvaluationResult
            Structured result with status, raw_metrics, penalty_values.
        """
        param_dict = dict(zip(self._param_names, params))
        raw, pen, ok, status, err = self.evaluate_single_pass(param_dict, iteration)
        return EvaluationResult(
            status=status,
            error=err,
            f0_ghz=float(raw.get("resonant_freq", np.nan)),
            raw_metrics=raw,
            penalty_values=pen,
            objective_values={k: raw.get(k, np.nan) for k in self._metric_names},
        )
