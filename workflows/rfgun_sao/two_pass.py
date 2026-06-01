# Two-pass orchestration skeleton for the RF gun SAO workflow.
# Pure Python decision logic, no CST dependency.

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import numpy as np
from workflows.rfgun_sao.calibration import CalibrationResult, MeasurementPlan, make_measurement_plan
from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate, MultiDipDetector

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
