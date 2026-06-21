"""Offline HOM eigenmode voltage, transverse R/Q, matching, and deduplication."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .models import ComplexLineField, EigenmodeCandidate

SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
REQUIRED_FIELD_POINTS = ("center", "x_plus", "x_minus", "y_plus", "y_minus")


@dataclass(frozen=True)
class TransverseMetrics:
    """First-order dipole coupling derived from five longitudinal trajectories."""

    voltages: dict[str, complex]
    gradient_x_v_per_m: complex
    gradient_y_v_per_m: complex
    a_x_ohm_per_m2: float
    a_y_ohm_per_m2: float
    a_total_ohm_per_m2: float
    transverse_r_over_q_ohm_per_m: float
    circuit_transverse_r_over_q_ohm: float
    kick_factor_v_per_c_per_m: float
    polarization_deg: float
    offline_center_r_over_q_ohm: float


def integrate_longitudinal_voltage(
    field: ComplexLineField,
    *,
    frequency_hz: float,
    beta: float = 1.0,
) -> complex:
    """Integrate ``Ez exp(+j omega z / beta c) dz``.

    ``z`` is in metres, ``Ez`` in V/m, and the returned peak voltage is volts.
    The positive phase convention matches the audited CST 2026 eigenmode
    result template.
    """

    if not (math.isfinite(frequency_hz) and frequency_hz > 0):
        raise ValueError("frequency_hz must be finite and positive")
    if not (math.isfinite(beta) and 0 < beta <= 1):
        raise ValueError("beta must satisfy 0 < beta <= 1")
    z = np.asarray(field.z_m, dtype=float)
    ez = np.asarray(field.ez_v_per_m, dtype=np.complex128)
    phase = np.exp(
        1j * 2.0 * math.pi * frequency_hz * z
        / (beta * SPEED_OF_LIGHT_M_PER_S)
    )
    return complex(np.trapezoid(ez * phase, z))


def _polarization_angle(gradient_x: complex, gradient_y: complex) -> float:
    """Return the principal real-axis angle of a complex gradient, in degrees."""

    matrix = np.array(
        [
            [
                abs(gradient_x) ** 2,
                (gradient_x * gradient_y.conjugate()).real,
            ],
            [
                (gradient_y * gradient_x.conjugate()).real,
                abs(gradient_y) ** 2,
            ],
        ],
        dtype=float,
    )
    _, eigenvectors = np.linalg.eigh(matrix)
    vector = eigenvectors[:, -1]
    angle = math.degrees(math.atan2(float(vector[1]), float(vector[0])))
    while angle < 0:
        angle += 180.0
    while angle >= 180.0:
        angle -= 180.0
    return angle


def calculate_transverse_metrics(
    fields: dict[str, ComplexLineField],
    *,
    frequency_hz: float,
    stored_energy_j: float,
    offset_mm: float = 2.0,
    beta: float = 1.0,
) -> TransverseMetrics:
    """Calculate unambiguous dipole coefficient and conventional conversions."""

    missing = [point for point in REQUIRED_FIELD_POINTS if point not in fields]
    if missing:
        raise ValueError(f"missing field points: {', '.join(missing)}")
    if not (math.isfinite(stored_energy_j) and stored_energy_j > 0):
        raise ValueError("stored_energy_j must be finite and positive")
    if not (math.isfinite(offset_mm) and offset_mm > 0):
        raise ValueError("offset_mm must be finite and positive")

    voltages = {
        point: integrate_longitudinal_voltage(
            fields[point], frequency_hz=frequency_hz, beta=beta
        )
        for point in REQUIRED_FIELD_POINTS
    }
    offset_m = offset_mm * 1e-3
    gradient_x = (voltages["x_plus"] - voltages["x_minus"]) / (2.0 * offset_m)
    gradient_y = (voltages["y_plus"] - voltages["y_minus"]) / (2.0 * offset_m)
    omega = 2.0 * math.pi * frequency_hz
    wave_number = omega / SPEED_OF_LIGHT_M_PER_S
    a_x = abs(gradient_x) ** 2 / (omega * stored_energy_j)
    a_y = abs(gradient_y) ** 2 / (omega * stored_energy_j)
    a_total = a_x + a_y
    center_rq = abs(voltages["center"]) ** 2 / (omega * stored_energy_j)
    return TransverseMetrics(
        voltages=voltages,
        gradient_x_v_per_m=gradient_x,
        gradient_y_v_per_m=gradient_y,
        a_x_ohm_per_m2=a_x,
        a_y_ohm_per_m2=a_y,
        a_total_ohm_per_m2=a_total,
        transverse_r_over_q_ohm_per_m=a_total / wave_number,
        circuit_transverse_r_over_q_ohm=a_total / (wave_number ** 2),
        kick_factor_v_per_c_per_m=SPEED_OF_LIGHT_M_PER_S * a_total / 4.0,
        polarization_deg=_polarization_angle(gradient_x, gradient_y),
        offline_center_r_over_q_ohm=center_rq,
    )


def relative_error(actual: float, reference: float) -> float:
    if not math.isfinite(actual) or not math.isfinite(reference):
        return math.inf
    denominator = max(abs(reference), 1e-300)
    return abs(actual - reference) / denominator


def apply_transverse_metrics(
    candidate: EigenmodeCandidate,
    metrics: TransverseMetrics,
    *,
    validation_tolerance: float = 0.02,
) -> EigenmodeCandidate:
    """Populate a candidate and enforce native Voltage/RQ cross-validation."""

    candidate.voltages = metrics.voltages
    candidate.gradient_x_v_per_m = metrics.gradient_x_v_per_m
    candidate.gradient_y_v_per_m = metrics.gradient_y_v_per_m
    candidate.polarization_deg = metrics.polarization_deg

    errors: list[str] = []
    if candidate.voltage_v is None:
        errors.append("missing_native_voltage")
    else:
        candidate.voltage_relative_error = relative_error(
            abs(metrics.voltages["center"]), candidate.voltage_v
        )
        if candidate.voltage_relative_error > validation_tolerance:
            errors.append("native_voltage_crosscheck_failed")
    if candidate.r_over_q_ohm is None:
        errors.append("missing_native_r_over_q")
    else:
        candidate.r_over_q_relative_error = relative_error(
            metrics.offline_center_r_over_q_ohm, candidate.r_over_q_ohm
        )
        if candidate.r_over_q_relative_error > validation_tolerance:
            errors.append("native_r_over_q_crosscheck_failed")

    if errors:
        candidate.derived_valid = False
        candidate.data_availability_reason = ";".join(errors)
        return candidate

    candidate.dipole_a_x_ohm_per_m2 = metrics.a_x_ohm_per_m2
    candidate.dipole_a_y_ohm_per_m2 = metrics.a_y_ohm_per_m2
    candidate.dipole_a_total_ohm_per_m2 = metrics.a_total_ohm_per_m2
    candidate.transverse_r_over_q_ohm_per_m = (
        metrics.transverse_r_over_q_ohm_per_m
    )
    candidate.circuit_transverse_r_over_q_ohm = (
        metrics.circuit_transverse_r_over_q_ohm
    )
    candidate.transverse_kick_factor_v_per_c_per_m = (
        metrics.kick_factor_v_per_c_per_m
    )
    candidate.derived_valid = True
    candidate.data_availability_reason = ""
    return candidate


def phase_insensitive_field_correlation(
    first: ComplexLineField,
    second: ComplexLineField,
) -> float:
    """Return normalized ``|<a,b>|`` after interpolation onto a common grid."""

    first_z = np.asarray(first.z_m, dtype=float)
    second_z = np.asarray(second.z_m, dtype=float)
    low = max(float(first_z.min()), float(second_z.min()))
    high = min(float(first_z.max()), float(second_z.max()))
    if high <= low:
        return 0.0
    size = max(16, min(len(first_z), len(second_z)))
    grid = np.linspace(low, high, size)

    def interpolate(field: ComplexLineField) -> np.ndarray:
        z = np.asarray(field.z_m, dtype=float)
        values = np.asarray(field.ez_v_per_m, dtype=np.complex128)
        return np.interp(grid, z, values.real) + 1j * np.interp(
            grid, z, values.imag
        )

    a = interpolate(first)
    b = interpolate(second)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 0:
        return 0.0
    return float(abs(np.vdot(a, b)) / denominator)


def deduplicate_modes(
    candidates: Iterable[EigenmodeCandidate],
    center_fields: dict[str, ComplexLineField],
    *,
    frequency_tolerance_hz: float = 0.5e6,
    field_correlation_threshold: float = 0.98,
    r_over_q_relative_tolerance: float = 0.05,
) -> list[EigenmodeCandidate]:
    """Merge overlapping-window duplicates only when complex fields agree."""

    ordered = sorted(candidates, key=lambda item: item.frequency_hz)
    consumed: set[str] = set()
    result: list[EigenmodeCandidate] = []
    for candidate in ordered:
        if candidate.mode_id in consumed:
            continue
        members = [candidate]
        for other in ordered:
            if other.mode_id == candidate.mode_id or other.mode_id in consumed:
                continue
            if abs(other.frequency_hz - candidate.frequency_hz) > frequency_tolerance_hz:
                continue
            first_field = center_fields.get(candidate.mode_id)
            second_field = center_fields.get(other.mode_id)
            if first_field is None or second_field is None:
                continue
            correlation = phase_insensitive_field_correlation(
                first_field, second_field
            )
            if correlation < field_correlation_threshold:
                continue
            if candidate.r_over_q_ohm is not None and other.r_over_q_ohm is not None:
                if relative_error(other.r_over_q_ohm, candidate.r_over_q_ohm) > (
                    r_over_q_relative_tolerance
                ):
                    continue
            members.append(other)
            consumed.add(other.mode_id)
        candidate.duplicate_member_ids = [item.mode_id for item in members]
        candidate.dedup_confidence = (
            "high_field_correlation" if len(members) > 1 else "unique"
        )
        result.append(candidate)
    return result
