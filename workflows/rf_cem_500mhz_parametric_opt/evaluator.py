"""No-CST evaluator for RF-CEM 500 MHz parametric geometry candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import numpy as np

from cst_optimization.parameters.base import ParameterSet
from rf_cem.parametric_geometry.optimization_adapter import generate_candidate_package
from workflows.rf_cem_500mhz_parametric_opt.types import EvaluationRecord, EvaluationStatus


class RfCemParametricEvaluator:
    """Generate and validate RF-CEM geometry candidates from optimizer vectors."""

    def __init__(
        self,
        *,
        appendix: Path,
        output_dir: Path,
        parameter_set: ParameterSet,
        selected_variant: str = "free_equator_smooth",
        target_body_index: int = 0,
        axis: str = "z",
        deflection_mm: float = 0.25,
    ) -> None:
        self.appendix = appendix
        self.output_dir = output_dir
        self.parameter_set = parameter_set
        self.selected_variant = selected_variant
        self.target_body_index = target_body_index
        self.axis = axis
        self.deflection_mm = deflection_mm

    def evaluate_no_cst(self, values: np.ndarray, *, index: int) -> EvaluationRecord:
        """Generate one candidate package and return a no-CST evaluation record."""
        parameter_values = self.parameter_set.to_dict(values)
        candidate_dir = self.output_dir / f"candidate_{index:03d}"
        try:
            result = generate_candidate_package(
                appendix=self.appendix,
                output_dir=candidate_dir,
                parameter_values=parameter_values,
                selected_variant=self.selected_variant,
                target_body_index=self.target_body_index,
                axis=self.axis,
                deflection_mm=self.deflection_mm,
            )
            validation_path = Path(result["geometry_validation"])
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            translator_report_path = candidate_dir / "translator" / "rf_cem_artifacts" / "generated" / "translator_report.json"
            postprocessing_verified = False
            if translator_report_path.exists():
                translator_report = json.loads(translator_report_path.read_text(encoding="utf-8"))
                postprocessing_verified = bool(translator_report.get("postprocessing_summary", {}).get("verified"))
            if not validation.get("pass"):
                status = EvaluationStatus.GEOMETRY_INVALID
            elif not postprocessing_verified:
                status = EvaluationStatus.POSTPROCESS_TEMPLATE_MISSING
            else:
                status = EvaluationStatus.SOLVER_NOT_RUN
            return EvaluationRecord(
                index=index,
                status=status,
                parameter_values=parameter_values,
                generated_package=str(candidate_dir),
                generated_step=str(result["generated_step"]),
                geometry_validation=str(validation_path),
                cst_payload=str(result.get("cst_payload", candidate_dir / "translator" / "cst_payload.json")),
                metadata={
                    "schema_version": "rf_cem_parametric_evaluation.v0",
                    "selected_variant": self.selected_variant,
                    "no_cst_geometry_pass": bool(validation.get("pass")),
                    "blocking_errors": validation.get("blocking_errors", []),
                    "postprocess_status": "verified_not_run" if postprocessing_verified else "template_missing",
                    "translator_report": str(translator_report_path),
                },
            )
        except Exception as exc:
            return EvaluationRecord(
                index=index,
                status=EvaluationStatus.UNKNOWN_ERROR,
                parameter_values=parameter_values,
                generated_package=str(candidate_dir),
                error=f"{type(exc).__name__}: {exc}",
            )


def scalar_penalty(
    values: Mapping[str, float],
    *,
    target_frequency_mhz: float = 500.0,
    frequency_window_mhz: tuple[float, float] = (490.0, 510.0),
    q_soft_floor: float = 30000.0,
    novelty_score: float = 0.0,
) -> float:
    """Compute a placeholder scalar penalty from live-CST objective values.

    Frequency is in MHz. R/Q is in Ohm. Q is dimensionless. The returned
    scalar is minimized; lower values favor in-band frequency, larger R/Q,
    larger shunt impedance R = (R/Q) * Q, and modest geometry novelty.
    """
    if not values:
        return float("nan")
    frequency = float(values.get("frequency_mhz", target_frequency_mhz))
    r_over_q = float(values.get("r_over_q_ohm", 0.0))
    q_factor = float(values.get("q_factor", 0.0))
    shunt_impedance = r_over_q * q_factor
    frequency_error = abs(frequency - target_frequency_mhz)
    if not (frequency_window_mhz[0] <= frequency <= frequency_window_mhz[1]):
        frequency_error += min(abs(frequency - frequency_window_mhz[0]), abs(frequency - frequency_window_mhz[1]))
    q_penalty = max(0.0, q_soft_floor - q_factor) / max(q_soft_floor, 1.0)
    return frequency_error + 10.0 * q_penalty - 1e-3 * r_over_q - 1e-8 * shunt_impedance - 0.1 * float(novelty_score)
