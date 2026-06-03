"""Workflow 1 evaluator -- single-project single-pass frequency-domain solver.

Extracted from ``src/cst_optimization/factory.py::build_workflow_1()``
during Phase 5 refactoring.  Behaviour is identical to the original
closure.
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
import time as _time
from typing import Any

import numpy as np

from cst_optimization.core.project import CSTProject
from cst_optimization.core.results import ResultReader
from cst_optimization.physics.formulas import (
    half_power_bandwidth,
    loaded_q_from_bandwidth,
    coupling_beta as _coupling_beta_formula,
    intrinsic_q0,
)
from cst_optimization.physics.heating import (
    max_h_from_field_file,
    pulsed_heating_delta_t,
)
from cst_optimization.physics.poynting import (
    discover_field_files,
    max_modified_poynting,
)
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


class Workflow1Evaluator:
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
        """Run one CST simulation and return raw metrics, penalties, status.

        Parameters
        ----------
        param_dict : dict[str, float]
            Parameter name -> value mapping.
        iteration : int
            Evaluation index (for logging).

        Returns
        -------
        raw_metrics : dict[str, float]
            Physical quantities computed from CST results.
        penalties : dict[str, float]
            Per-objective penalty values (from ``obj.mode.compute``).
        solver_ok : bool
            Whether the solver completed and all physics computed.
        status : EvaluationStatus
            Classified outcome (SUCCESS / COM_LOST / SOLVER_FAILED).
        error : str
            Error message (empty on success).
        """
        self._last_diagnostics = {}
        raw_metrics: dict[str, float] = {}
        penalties: dict[str, float] = {}
        solver_ok = False
        error = ""
        project = None

        try:
            project = self._conn.open_project(self._project_path)
            ok = project.update_parameters(param_dict, use_full_rebuild=True)
            if not ok:
                raise RuntimeError("Parameter update failed")
            _logger.info("Workflow 1: rebuild done for iteration %d", iteration)

            solver_result = self._runner.run(project)
            if not solver_result.success:
                if solver_result.error_type == "com":
                    return raw_metrics, penalties, False, _ES.COM_LOST, "COM connection lost"

            try:
                project.save()
            except Exception:
                pass

            # Wait for field-export files (up to 3 x 5s)
            for _ in range(3):
                _time.sleep(5.0)
                e_file, _ = discover_field_files(self._project_dir)
                if e_file:
                    break

            reader = ResultReader(project.filename, allow_interactive=True)
            s11 = reader.get_s_parameter()
            mag = np.abs(s11.s_complex)

            # --- Resonant frequency via half-power bandwidth ---
            f0, f1, f2, gamma_min = half_power_bandwidth(
                s11.frequencies, mag, target_freq=11.424,
            )
            raw_metrics["resonant_freq"] = float(f0)

            # --- Coupling beta ---
            coupling = float(_coupling_beta_formula(gamma_min))
            raw_metrics["coupling_beta"] = coupling

            # --- Intrinsic Q0 ---
            raw_metrics["q0"] = float(intrinsic_q0(
                loaded_q_from_bandwidth(f0, f1, f2), coupling,
            ))

            # --- Peak E field ---
            e_max = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
            e_sim = float(e_max.value)
            raw_metrics["peak_e_field"] = e_sim

            # --- Field flatness ---
            try:
                e1 = reader.get_scalar(reader.TREEPATH_MAX_E_Z1).value
                e2 = reader.get_scalar(reader.TREEPATH_MAX_E_Z2).value
                emx = max(e_sim, e1, e2)
                emn = min(e_sim, e1, e2)
                raw_metrics["field_flatness"] = 1.0 - emn / emx if emx > 0 else 1.0
            except Exception:
                raw_metrics["field_flatness"] = np.nan

            # --- Modified Poynting & pulsed heating ---
            e_file, h_file = discover_field_files(self._project_dir)
            if e_file and h_file and e_sim > 0:
                scale = 200e6 / e_sim
                raw_metrics["max_modified_poynting"] = float(
                    max_modified_poynting(e_file, h_file, gc=0.125, field_scale=scale)
                )
                h_peak = max_h_from_field_file(h_file)
                raw_metrics["pulsed_heating"] = float(pulsed_heating_delta_t(
                    h_peak_sim=h_peak, e_peak_sim=e_sim,
                    e_target=200e6, pulse_width_ns=300,
                    frequency_hz=11.424e9, rrr=5.5,
                ))

            # --- Penalty computation (role-aware) ---
            penalties = compute_role_penalties(
                metric_specs=self._metric_specs,
                objectives_by_name=self._objectives_by_name,
                raw_metrics=raw_metrics,
            )

            # --- Report-only diagnostics ---
            self._last_diagnostics = report_only_diagnostics(
                metric_specs=self._metric_specs,
                raw_metrics=raw_metrics,
            )

            solver_ok = True
            _logger.info(
                "Workflow 1 iter %d done: %s", iteration,
                ", ".join(
                    f"{k}={v:.6g}" for k, v in sorted(raw_metrics.items())
                    if np.isfinite(v)
                ),
            )

        except Exception as exc:
            error = str(exc)[:200]
            if any(w in error.lower() for w in ("com", "connection", "designenvironment")):
                return raw_metrics, penalties, False, _ES.COM_LOST, error
            _logger.warning("Workflow 1 eval failed iter %d: %s", iteration, error)

        finally:
            if project is not None:
                try:
                    project.close(save=False)
                except Exception:
                    pass

        status = _ES.SUCCESS if solver_ok else _ES.SOLVER_FAILED
        return raw_metrics, penalties, solver_ok, status, error

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
            diagnostics=dict(self._last_diagnostics),
        )
