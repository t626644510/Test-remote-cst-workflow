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
    and returns a ``CalibrationResult``.

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
        try:
            project = connection.open_project(project_path)
            params = dict(param_dict)
            params["f_data"] = calibration_guess_ghz
            ok = project.update_parameters(params, use_full_rebuild=True)
            if not ok:
                return CalibrationResult(
                    success=False,
                    error="Parameter update failed",
                    method="cst_s11",
                )

            solver_result = solver_runner.run(project)
            if not solver_result.success:
                err_type = str(getattr(solver_result, "error_type", "")).lower()
                if "com" in err_type:
                    return CalibrationResult(
                        success=False,
                        error="COM connection lost during calibration",
                        method="cst_s11",
                    )
                return CalibrationResult(
                    success=False,
                    error=(
                        f"Calibration solver failed: "
                        f"{getattr(solver_result, 'error_message', None) or 'unknown'}"
                    ),
                    method="cst_s11",
                )

            try:
                project.save()
            except Exception:
                pass

            reader = ResultReader(project.filename, allow_interactive=True)
            s11 = reader.get_s_parameter()
            mag = np.abs(s11.s_complex)
            s11_min = s11_min_db_from_magnitude(mag)

            # Try half-power bandwidth first; fall back to dip minimum.
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
            except Exception:
                idx = int(np.argmin(mag))
                f0 = float(s11.frequencies[idx])
                method = "cst_s11_dip_min"

            return CalibrationResult(
                success=True,
                f0_ghz=float(f0),
                s11_min_db=float(s11_min),
                method=method,
                meta={"iteration": iteration},
            )

        except Exception as exc:
            error = str(exc)[:200]
            if any(w in error.lower() for w in ("com", "connection",
                                                 "designenvironment")):
                error = "COM connection lost during calibration"
            return CalibrationResult(
                success=False, error=error, method="cst_s11",
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
