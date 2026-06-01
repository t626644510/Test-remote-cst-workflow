# CST-backed calibration and measurement runner adapters for two-pass SAO.
# These factories close over CST objects and return callables compatible
# with ``make_two_pass_runtime_evaluator`` from two_pass.py.

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

from cst_optimization.core.results import ResultReader
from cst_optimization.physics.formulas import half_power_bandwidth
from workflows.rfgun_sao.calibration import (
    CalibrationResult,
    MeasurementPlan,
    s11_min_db_from_magnitude,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

_logger = logging.getLogger(__name__)


def _make_calibration_meta(
    iteration: int,
    calibration_guess_ghz: float,
) -> dict[str, Any]:
    """Build a fresh calibration meta dict with common fields."""
    return {
        "iteration": iteration,
        "calibration_guess_ghz": calibration_guess_ghz,
    }


def _safe_str_meta(value: object, max_len: int = 200) -> str:
    """Short string representation for meta fields (prevents huge values)."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def make_cst_calibration_runner(
    *,
    connection: Any,
    project_path: str,
    solver_runner: Any,
    calibration_guess_ghz: float,
) -> Callable[[dict[str, float], int], CalibrationResult]:
    """Return a CST-based calibration runner for two-pass.

    Opens the CST project, sets ``f_data`` to *calibration_guess_ghz*,
    runs the solver, reads S11, extracts resonant frequency / dip depth,
    and returns a ``CalibrationResult`` with detailed diagnostic *meta*.

    Parameters
    ----------
    connection : CSTConnection
        Active CST DesignEnvironment connection.
    project_path : str
        Path to the ``.cst`` file.
    solver_runner : SolverRunner
        Synchronous solver runner.
    calibration_guess_ghz : float
        Target frequency for the calibration solve (sets ``f_data``).

    Returns
    -------
    Callable[[dict[str, float], int], CalibrationResult]
    """
    def _runner(
        param_dict: dict[str, float],
        iteration: int,
    ) -> CalibrationResult:
        project = None
        meta: dict[str, Any] = _make_calibration_meta(
            iteration, calibration_guess_ghz,
        )
        try:
            project = connection.open_project(project_path)
            meta["project_filename"] = _safe_str_meta(
                getattr(project, "filename", project_path),
            )

            params = dict(param_dict)
            params["f_data"] = calibration_guess_ghz
            ok = project.update_parameters(params, use_full_rebuild=True)
            meta["update_ok"] = ok
            if not ok:
                return CalibrationResult(
                    success=False,
                    error="Parameter update failed",
                    method="cst_s11",
                    meta=meta,
                )

            solver_result = solver_runner.run(project)
            meta["solver_success"] = solver_result.success
            meta["solver_error_type"] = str(
                getattr(solver_result, "error_type", "") or "",
            )
            err_msg = getattr(solver_result, "error_message", None)
            meta["solver_error_message"] = _safe_str_meta(err_msg) if err_msg else ""
            if hasattr(solver_result, "elapsed_s") and solver_result.elapsed_s is not None:
                meta["solver_elapsed_s"] = float(solver_result.elapsed_s)
            if hasattr(solver_result, "mesh_cells") and solver_result.mesh_cells is not None:
                meta["solver_mesh_cells"] = int(solver_result.mesh_cells)

            if not solver_result.success:
                err_type = str(
                    getattr(solver_result, "error_type", "") or "",
                ).lower()
                if "com" in err_type:
                    return CalibrationResult(
                        success=False,
                        error="COM connection lost during calibration",
                        method="cst_s11",
                        meta=meta,
                    )
                return CalibrationResult(
                    success=False,
                    error=(
                        f"Calibration solver failed: "
                        f"{getattr(solver_result, 'error_message', None) or 'unknown'}"
                    ),
                    method="cst_s11",
                    meta=meta,
                )

            try:
                project.save()
            except Exception:
                pass

            # --- S11 read --------------------------------------------------
            try:
                reader = ResultReader(project.filename, allow_interactive=True)
                meta["result_reader_ok"] = True
                s11 = reader.get_s_parameter()
            except Exception as read_exc:
                meta["result_reader_ok"] = False
                return CalibrationResult(
                    success=False,
                    error=f"S11 read failed: {str(read_exc)[:200]}",
                    method="cst_s11",
                    meta=meta,
                )

            mag = np.abs(s11.s_complex)
            s11_min = s11_min_db_from_magnitude(mag)

            # S11 summary (not full arrays)
            meta["s11_points"] = int(len(mag))
            meta["s11_freq_min_ghz"] = float(np.min(s11.frequencies))
            meta["s11_freq_max_ghz"] = float(np.max(s11.frequencies))
            meta["s11_min_db"] = float(s11_min)

            # --- Half-power bandwidth; fall back to dip minimum ------------
            try:
                f0, _f1, _f2, _gamma_min = half_power_bandwidth(
                    s11.frequencies, mag,
                    target_freq=calibration_guess_ghz,
                )
                if not np.isfinite(f0):
                    raise ValueError(
                        f"half_power_bandwidth returned non-finite f0: {f0}",
                    )
                method = "cst_s11_hpbw"
                meta["hpbw_ok"] = True
            except Exception as hpbw_exc:
                meta["hpbw_ok"] = False
                meta["hpbw_error"] = str(hpbw_exc)[:200]
                idx = int(np.argmin(mag))
                f0 = float(s11.frequencies[idx])
                method = "cst_s11_dip_min"
                meta["fallback_used"] = "dip_minimum"

            return CalibrationResult(
                success=True,
                f0_ghz=float(f0),
                s11_min_db=float(s11_min),
                method=method,
                meta=meta,
            )

        except Exception as exc:
            meta.setdefault("result_reader_ok", False)
            meta["exception_type"] = type(exc).__name__
            meta["exception_message"] = str(exc)[:200]
            error = str(exc)[:200]
            if any(w in error.lower() for w in ("com", "connection",
                                                 "designenvironment")):
                error = "COM connection lost during calibration"
            return CalibrationResult(
                success=False, error=error, method="cst_s11",
                meta=meta,
            )

        finally:
            if project is not None:
                try:
                    project.close(save=False)
                except Exception:
                    pass

    return _runner


def make_cst_measurement_runner(
    *,
    wf1_evaluator: Any,
    metric_names: list[str],
) -> Callable[
    [dict[str, float], MeasurementPlan, int], EvaluationResult,
]:
    """Return a CST-based measurement runner for two-pass.

    Sets ``f_data`` from the ``MeasurementPlan``, then delegates to
    ``wf1_evaluator.evaluate_single_pass`` to reuse all single-pass
    post-processing (resonant frequency, Q0, coupling beta, field
    quantities, penalties).  No physics logic is duplicated here.

    Parameters
    ----------
    wf1_evaluator : Workflow1Evaluator
        Fully-constructed evaluator (requires CST connection, solver,
        objectives).
    metric_names : list[str]
        Ordered metric names for ``EvaluationResult.objective_values``.

    Returns
    -------
    Callable[[dict[str, float], MeasurementPlan, int], EvaluationResult]
    """
    def _runner(
        param_dict: dict[str, float],
        measurement_plan: MeasurementPlan,
        iteration: int,
    ) -> EvaluationResult:
        params = dict(param_dict)
        params["f_data"] = float(measurement_plan.f_data_ghz)
        raw, pen, _ok, status, err = wf1_evaluator.evaluate_single_pass(
            params, iteration,
        )
        return EvaluationResult(
            status=status,
            error=err,
            f0_ghz=float(raw.get("resonant_freq", np.nan)),
            raw_metrics=raw,
            penalty_values=pen,
            objective_values={
                name: raw.get(name, np.nan) for name in metric_names
            },
        )

    return _runner
