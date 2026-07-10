# Calibration primitives for the RF gun SAO workflow.
# Pure Python dataclasses and helpers for two-pass calibration.

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any
import numpy as np

_logger = logging.getLogger(__name__)

@dataclass
class CalibrationResult:
    success: bool = False
    f0_ghz: float = np.nan
    s11_min_db: float = np.nan
    error: str = ""
    method: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass
class MeasurementPlan:
    f_data_ghz: float
    reason: str = "calibrated_resonance"
    meta: dict[str, Any] = field(default_factory=dict)

def make_measurement_plan(calibration, fallback_ghz):
    if calibration.success and np.isfinite(calibration.f0_ghz):
        return MeasurementPlan(
            f_data_ghz=calibration.f0_ghz,
            reason="calibrated_resonance",
            meta={"calibration_method": calibration.method},
        )
    _logger.warning(
        "Calibration failed (success=%s, f0=%s), falling back to %.6f GHz",
        calibration.success, calibration.f0_ghz, fallback_ghz,
    )
    return MeasurementPlan(f_data_ghz=fallback_ghz, reason="fallback")

def s11_min_db_from_magnitude(magnitude):
    gamma_min = float(np.min(np.abs(magnitude)))
    gamma_min = max(gamma_min, 1e-12)
    return float(20.0 * np.log10(gamma_min))
