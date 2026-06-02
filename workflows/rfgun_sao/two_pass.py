# Two-pass orchestration skeleton for the RF gun SAO workflow.
# Pure Python decision logic, no CST dependency.

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import numpy as np
from workflows.rfgun_sao.calibration import CalibrationResult, MeasurementPlan, make_measurement_plan
from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate, MultiDipDetector
from workflows.rfgun_sao.metrics import (
    MetricSpec,
    compute_gate_results,
    summarize_gate_results,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

_logger = logging.getLogger(__name__)

@dataclass
class TwoPassDecision:
    accepted: bool
    reason: str = ""
    calibration: CalibrationResult | None = None
    measurement_plan: MeasurementPlan | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

def evaluate_two_pass_decision(
    calibration: CalibrationResult,
    fallback_ghz: float,
    frequency_gate: FrequencyGate | None = None,
    s11_depth_gate: S11DepthGate | None = None,
    multi_dip_detector: MultiDipDetector | None = None,
    frequencies_ghz=None,
    s11_magnitude=None,
) -> TwoPassDecision:
    measurement_plan = make_measurement_plan(calibration, fallback_ghz)
    diagnostics: dict[str, Any] = {}
    if not calibration.success:
        return TwoPassDecision(accepted=False, reason="calibration_failed", calibration=calibration, measurement_plan=measurement_plan, diagnostics=diagnostics)
    if frequency_gate is not None and not frequency_gate.accepts(calibration.f0_ghz):
        return TwoPassDecision(accepted=False, reason="frequency_gate_reject", calibration=calibration, measurement_plan=measurement_plan, diagnostics=diagnostics)
    if s11_depth_gate is not None and not s11_depth_gate.accepts(calibration.s11_min_db):
        return TwoPassDecision(accepted=False, reason="s11_depth_gate_reject", calibration=calibration, measurement_plan=measurement_plan, diagnostics=diagnostics)
    if multi_dip_detector is not None and multi_dip_detector.enabled and frequencies_ghz is not None and s11_magnitude is not None:
        diagnostics["multi_dip_detected"] = multi_dip_detector.has_multiple_dips(frequencies_ghz, s11_magnitude)
        if diagnostics["multi_dip_detected"]:
            _logger.info("TwoPassDecision: multi-dip detected, candidate accepted but flagged for review")
    return TwoPassDecision(accepted=True, reason="accepted", calibration=calibration, measurement_plan=measurement_plan, diagnostics=diagnostics)

def _decision_error_message(decision: TwoPassDecision) -> str:
    """Build a descriptive error string from a rejected ``TwoPassDecision``.

    For ``calibration_failed`` the calibration.error is appended so the
    caller can distinguish "solver crashed" from "S11 had no dip" without
    digging into the decision object.  Gate rejections pass through their
    reason, optionally augmented with calibration.error when present.

    Parameters
    ----------
    decision : TwoPassDecision
        A rejected (or accepted) decision with optional calibration detail.

    Returns
    -------
    str
        Human-readable error string for logging and checkpoint.
    """
    if decision.reason == "calibration_failed" and decision.calibration is not None and decision.calibration.error:
        return f"calibration_failed: {decision.calibration.error}"
    if decision.reason in ("frequency_gate_reject", "s11_depth_gate_reject"):
        if decision.calibration is not None and decision.calibration.error:
            return f"{decision.reason}: {decision.calibration.error}"
        return decision.reason
    return (
        decision.reason
        or (decision.calibration.error if decision.calibration else "")
        or "unknown"
    )


def _safe_meta_str(meta: dict[str, Any]) -> str:
    """Compact string representation of a meta dict for logging.

    Floats are formatted with ``.6g``; long strings are truncated at 80
    characters.  The result is guaranteed to be reasonably short and free
    of huge arrays or nested structures.
    """
    if not meta:
        return "{}"
    items: list[str] = []
    for k, v in meta.items():
        if isinstance(v, float):
            items.append(f"{k}={v:.6g}")
        elif isinstance(v, str) and len(v) > 80:
            items.append(f"{k}={v[:80]}...")
        else:
            items.append(f"{k}={v}")
    return "{" + ", ".join(items) + "}"


def make_two_pass_placeholder_evaluator(
    fallback_ghz: float = 11.424,
    frequency_gate: FrequencyGate | None = None,
    s11_depth_gate: S11DepthGate | None = None,
    multi_dip_detector: MultiDipDetector | None = None,
) -> Callable[[np.ndarray], float]:
    """Return a placeholder two-pass evaluator (no CST connection).

    This is a runtime skeleton only.  Every candidate receives a
    penalty of 1.0, simulating a failed calibration.  No CST solver
    or result reading is performed.
    """
    def _evaluator(x_phys: np.ndarray) -> float:
        calibration = CalibrationResult(
            success=False,
            f0_ghz=np.nan,
            error="two_pass_runtime_not_implemented",
        )
        evaluate_two_pass_decision(
            calibration=calibration,
            fallback_ghz=fallback_ghz,
            frequency_gate=frequency_gate,
            s11_depth_gate=s11_depth_gate,
            multi_dip_detector=multi_dip_detector,
        )
        return 1.0
    return _evaluator


# ---- Raw extraction helpers -------------------------------------------------


def _extract_raw_array(
    result: EvaluationResult,
    metric_names: list[str],
) -> np.ndarray:
    """Extract raw metric array from an ``EvaluationResult`` with fallback.

    For each metric name in order:

    1. Try ``result.objective_values[name]``.
    2. Fall back to ``result.raw_metrics[name]``.
    3. Fall back to ``numpy.nan``.

    Non-finite or unconvertible values are replaced with ``numpy.nan``.

    Parameters
    ----------
    result : EvaluationResult
        The evaluation result from a measurement runner.
    metric_names : list[str]
        Ordered metric names.

    Returns
    -------
    np.ndarray
        Float array of length ``len(metric_names)``.
    """
    raw_arr: list[float] = []
    for name in metric_names:
        val: float = np.nan
        if result.objective_values is not None and name in result.objective_values:
            val = result.objective_values[name]
        elif result.raw_metrics is not None and name in result.raw_metrics:
            val = result.raw_metrics[name]
        try:
            fv = float(val)
            if not np.isfinite(fv):
                fv = np.nan
        except (TypeError, ValueError):
            fv = np.nan
        raw_arr.append(fv)
    return np.array(raw_arr, dtype=float)


def make_placeholder_calibration_runner(
) -> Callable[[dict[str, float], int], CalibrationResult]:
    """Return a calibration runner that always fails.

    This is a placeholder for the CST-based calibration runner.
    Every call returns ``CalibrationResult(success=False)``.
    """
    def _runner(param_dict: dict[str, float], iteration: int) -> CalibrationResult:
        return CalibrationResult(
            success=False,
            f0_ghz=np.nan,
            error="placeholder_calibration_runner",
            method="placeholder",
        )
    return _runner


def make_placeholder_measurement_runner(
) -> Callable[[dict[str, float], MeasurementPlan, int], EvaluationResult]:
    """Return a measurement runner that always fails.

    This is a placeholder for the CST-based measurement runner.
    Every call returns ``EvaluationResult(status=SOLVER_FAILED)``.
    """
    def _runner(
        param_dict: dict[str, float],
        plan: MeasurementPlan,
        iteration: int,
    ) -> EvaluationResult:
        return EvaluationResult(
            status=EvaluationStatus.SOLVER_FAILED,
            error="placeholder_measurement_runner",
            f0_ghz=np.nan,
        )
    return _runner


def make_two_pass_runtime_evaluator(
    *,
    param_names: list[str],
    metric_names: list[str],
    objectives: list,
    weights: np.ndarray,
    fallback_ghz: float = 11.424,
    frequency_gate: FrequencyGate | None = None,
    s11_depth_gate: S11DepthGate | None = None,
    multi_dip_detector: MultiDipDetector | None = None,
    calibration_runner: Callable[[dict[str, float], int], CalibrationResult],
    measurement_runner: Callable[[dict[str, float], MeasurementPlan, int], EvaluationResult],
    checkpoint_callback: Callable[
        [np.ndarray, np.ndarray, np.ndarray, bool, str], None
    ] | None = None,
    metric_specs: list[MetricSpec] | None = None,
    evaluation_record_callback: Callable[..., None] | None = None,
) -> Callable[[np.ndarray], float]:
    """Return a two-pass runtime evaluator with injectable runners.

    This factory creates a callable ``f(x_phys) -> float`` suitable for
    passing as the ``evaluator`` argument to
    ``SurrogateAssistedOptimizer.optimize()``.

    The internal control flow is:

    1. Convert ``x_phys`` to ``param_dict`` via ``param_names``.
    2. **Calibration pass:** invoke ``calibration_runner``.
    3. **Decision gate:** ``evaluate_two_pass_decision`` checks gates.
    4. **Rejected path:** return penalty=1.0, no measurement runner call.
    5. **Accepted path:** invoke ``measurement_runner``.
    6. **Penalty extraction:** build ``penalties_arr`` from result.
    7. **Checkpoint:** call ``checkpoint_callback`` if provided.
    8. **Weighted scalar:** return ``dot(penalties_arr, weights)``.

    Parameters are keyword-only.

    Parameters
    ----------
    param_names : list[str]
        Ordered parameter names (maps ``x_phys`` index to name).
    metric_names : list[str]
        Ordered metric (objective) names for penalty extraction.
    objectives : list
        Objective function list (forward-compat, not used in control flow yet).
    weights : np.ndarray
        Normalised weight vector aligned with ``metric_names``.
    fallback_ghz : float
        Fallback frequency if calibration fails.
    frequency_gate : FrequencyGate | None
    s11_depth_gate : S11DepthGate | None
    multi_dip_detector : MultiDipDetector | None
    calibration_runner : callable
        ``(param_dict, iteration) -> CalibrationResult``
    measurement_runner : callable
        ``(param_dict, measurement_plan, iteration) -> EvaluationResult``
    checkpoint_callback : callable or None
        ``(x_phys, raw_values, penalties, solver_ok, error) -> None``

    Returns
    -------
    callable
        ``f(x_phys: np.ndarray) -> float``
    """
    def _evaluator(x_phys: np.ndarray, _it: list[int] = [0]) -> float:
        iteration = int(_it[0])
        _it[0] += 1

        param_dict = dict(zip(param_names, x_phys))

        # Calibration pass
        calibration = calibration_runner(param_dict, iteration)

        # Decision gate
        decision = evaluate_two_pass_decision(
            calibration=calibration,
            fallback_ghz=fallback_ghz,
            frequency_gate=frequency_gate,
            s11_depth_gate=s11_depth_gate,
            multi_dip_detector=multi_dip_detector,
        )

        n_metrics = len(metric_names)

        if not decision.accepted:
            penalties_arr = np.full(n_metrics, 1.0, dtype=float)
            raw_arr = np.full(n_metrics, np.nan, dtype=float)
            if np.isfinite(calibration.f0_ghz) and "resonant_freq" in metric_names:
                raw_arr[metric_names.index("resonant_freq")] = calibration.f0_ghz

            error_msg = _decision_error_message(decision)
            cal = decision.calibration
            if cal is not None:
                _logger.warning(
                    "Two-pass rejected: reason=%s cal_success=%s "
                    "f0_ghz=%s s11_min_db=%s cal_method=%s "
                    "cal_error=%s meta=%s",
                    decision.reason, cal.success, cal.f0_ghz,
                    cal.s11_min_db, cal.method, cal.error,
                    _safe_meta_str(cal.meta),
                )
            else:
                _logger.warning(
                    "Two-pass rejected: reason=%s", decision.reason,
                )

            if checkpoint_callback is not None:
                checkpoint_callback(
                    x_phys, raw_arr, penalties_arr,
                    False,
                    error_msg,
                )

            # Enriched evaluation record (rejected path)
            if evaluation_record_callback is not None:
                try:
                    cal_diag = getattr(cal, "meta", None) or None
                    evaluation_record_callback(
                        x_phys=x_phys,
                        raw_values=raw_arr,
                        penalties=penalties_arr,
                        solver_ok=False,
                        error=error_msg,
                        diagnostics=cal_diag,
                        gate_results=None,
                        metadata={
                            "two_pass_phase": "rejected",
                            "reject_reason": decision.reason,
                        },
                    )
                except Exception:
                    _logger.warning(
                        "Evaluation record callback failed (rejected path)",
                        exc_info=True,
                    )

            return float(np.dot(penalties_arr, weights))

        # Accepted — log calibration success details
        cal = decision.calibration
        if cal is not None:
            _logger.info(
                "Two-pass accepted: reason=%s cal_success=%s "
                "f0_ghz=%s s11_min_db=%s cal_method=%s meta=%s",
                decision.reason, cal.success, cal.f0_ghz,
                cal.s11_min_db, cal.method,
                _safe_meta_str(cal.meta),
            )
        else:
            _logger.info(
                "Two-pass accepted: reason=%s (no calibration object)",
                decision.reason,
            )

        # Measurement pass
        result = measurement_runner(
            param_dict, decision.measurement_plan, iteration,
        )

        # Log report-only diagnostics (if any) without persisting to checkpoint
        if result.diagnostics is not None and result.diagnostics:
            _logger.info(
                "Two-pass measurement diagnostics: %s",
                _safe_meta_str(result.diagnostics),
            )

        # Gate rejection (only after successful measurement with metric_specs)
        gate_reject_error: str = ""
        gate_results: dict[str, bool] | None = None
        if (
            metric_specs is not None
            and result.status == EvaluationStatus.SUCCESS
        ):
            gate_results = compute_gate_results(
                metric_specs, result.raw_metrics or {},
            )
            if gate_results:
                _logger.info(
                    "Two-pass gate results: %s",
                    _safe_meta_str(gate_results),
                )
                gate_all_pass, gate_error_str = summarize_gate_results(
                    gate_results,
                )
                if not gate_all_pass:
                    gate_reject_error = gate_error_str

        if (
            result.status == EvaluationStatus.SUCCESS
            and result.penalty_values is not None
        ):
            penalties_arr = np.array(
                [float(result.penalty_values.get(name, 1.0)) for name in metric_names],
                dtype=float,
            )
            raw_arr = _extract_raw_array(result, metric_names)
        else:
            penalties_arr = np.full(n_metrics, 1.0, dtype=float)
            raw_arr = _extract_raw_array(result, metric_names)

        solver_ok = result.status == EvaluationStatus.SUCCESS
        error_for_ckpt = result.error or ""
        if gate_reject_error:
            penalties_arr = np.full(n_metrics, 1.0, dtype=float)
            raw_arr = _extract_raw_array(result, metric_names)
            solver_ok = False
            error_for_ckpt = gate_reject_error
        if checkpoint_callback is not None:
            checkpoint_callback(
                x_phys, raw_arr, penalties_arr, solver_ok, error_for_ckpt,
            )

        # Enriched evaluation record (diagnostics + gate_results)
        if evaluation_record_callback is not None:
            try:
                measurement_diag = (
                    result.diagnostics if result.diagnostics else None
                )
                measurement_gate = (
                    gate_results if gate_results else None
                )
                evaluation_record_callback(
                    x_phys=x_phys,
                    raw_values=raw_arr,
                    penalties=penalties_arr,
                    solver_ok=solver_ok,
                    error=error_for_ckpt,
                    diagnostics=measurement_diag,
                    gate_results=measurement_gate,
                    metadata={
                        "two_pass_phase": "measurement",
                        "gate_reject": bool(gate_reject_error),
                    },
                )
            except Exception:
                _logger.warning(
                    "Evaluation record callback failed (measurement path)",
                    exc_info=True,
                )

        return float(np.dot(penalties_arr, weights))

    return _evaluator
