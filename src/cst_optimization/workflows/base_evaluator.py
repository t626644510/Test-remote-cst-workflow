"""Shared base evaluator for Workflow 1 single-pass CST evaluation.

Contains the common physics post-processing logic shared by both
``rfgun_sao`` and ``rfgun_single_pass`` evaluators.
Subclasses override ``_compute_penalties`` for their specific penalty model.
"""

from __future__ import annotations

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

_logger = logging.getLogger(__name__)


class BaseWorkflow1Evaluator:
    """Shared base for single-pass frequency-domain CST evaluation.

    Subclasses must provide:
    - ``_conn`` : CSTConnection
    - ``_project_path`` : str
    - ``_project_dir`` : str (derived from project_path)
    - ``_runner`` : SolverRunner
    - ``_compute_penalties(raw_metrics)`` → dict[str, float]
    """

    _conn: Any
    _project_path: str
    _project_dir: str
    _runner: Any

    def evaluate_single_pass(
        self,
        param_dict: dict[str, float],
        iteration: int,
        eval_status_cls: type,
    ) -> tuple[dict[str, float], dict[str, float], bool, Any, str]:
        """Run one CST simulation and return raw metrics, penalties, status.

        Parameters
        ----------
        param_dict : dict[str, float]
            Parameter name -> value mapping.
        iteration : int
            Evaluation index (for logging).
        eval_status_cls : type
            ``EvaluationStatus`` enum class (from rfgun_sao or shared recovery).

        Returns
        -------
        raw_metrics, penalties, solver_ok, status, error
        """
        raw_metrics: dict[str, float] = {}
        penalties: dict[str, float] = {}
        solver_ok = False
        error = ""
        project = None
        _ES = eval_status_cls

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

            # --- Penalty computation (subclass hook) ---
            penalties = self._compute_penalties(raw_metrics)

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

    def _compute_penalties(self, raw_metrics: dict[str, float]) -> dict[str, float]:
        """Subclass hook: compute penalty values from raw physics metrics."""
        raise NotImplementedError("Subclass must implement _compute_penalties")

    # -- adapt_for_retry is shared; subclasses can override _extra_result_fields --

    def adapt_for_retry(
        self,
        params: np.ndarray,
        iteration: int,
        result_cls: type,
        eval_status_cls: type,
    ) -> Any:
        """Wrap ``evaluate_single_pass`` for ``EvaluationRetryHandler``.

        Parameters
        ----------
        params : np.ndarray
            Physical-space parameter vector.
        iteration : int
            Evaluation index.
        result_cls : type
            ``EvaluationResult`` class (from rfgun_sao or shared recovery).
        eval_status_cls : type
            ``EvaluationStatus`` enum class.

        Returns
        -------
        EvaluationResult
        """
        param_dict = dict(zip(self._param_names, params))
        raw, pen, ok, status, err = self.evaluate_single_pass(param_dict, iteration, eval_status_cls)
        kwargs: dict[str, Any] = {
            "status": status,
            "error": err,
            "f0_ghz": float(raw.get("resonant_freq", np.nan)),
            "raw_metrics": raw,
            "penalty_values": pen,
            "objective_values": {k: raw.get(k, np.nan) for k in self._metric_names},
        }
        # Hook for subclasses to add extra fields (e.g. diagnostics)
        kwargs.update(self._extra_result_fields())
        return result_cls(**kwargs)

    def _extra_result_fields(self) -> dict[str, Any]:
        """Hook: extra fields for ``EvaluationResult`` (e.g. diagnostics)."""
        return {}
