from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from workflows.rfgun_hom_eigenmode.models import (
    ComplexLineField,
    EigenmodeCandidate,
)
from workflows.rfgun_hom_eigenmode.physics import (
    SPEED_OF_LIGHT_M_PER_S,
    apply_transverse_metrics,
    calculate_transverse_metrics,
    deduplicate_modes,
    phase_insensitive_field_correlation,
)


def _field(scale: complex) -> ComplexLineField:
    z = np.linspace(-0.03, 0.03, 301)
    profile = np.cos(math.pi * z / 0.06)
    return ComplexLineField(z_m=z, ez_v_per_m=scale * profile)


def test_five_line_complex_voltage_produces_all_transverse_conventions() -> None:
    frequency = 1.0e9
    energy = 1.0
    offset_m = 0.002
    center = 2.0 + 0.5j
    dx = 30.0 - 10.0j
    dy = -20.0 + 5.0j
    fields = {
        "center": _field(center),
        "x_plus": _field(center + dx * offset_m),
        "x_minus": _field(center - dx * offset_m),
        "y_plus": _field(center + dy * offset_m),
        "y_minus": _field(center - dy * offset_m),
    }

    metrics = calculate_transverse_metrics(
        fields,
        frequency_hz=frequency,
        stored_energy_j=energy,
        offset_mm=2.0,
    )

    assert metrics.a_total_ohm_per_m2 > 0
    k = 2 * math.pi * frequency / SPEED_OF_LIGHT_M_PER_S
    assert metrics.transverse_r_over_q_ohm_per_m == pytest.approx(
        metrics.a_total_ohm_per_m2 / k
    )
    assert metrics.circuit_transverse_r_over_q_ohm == pytest.approx(
        metrics.a_total_ohm_per_m2 / k**2
    )
    assert metrics.kick_factor_v_per_c_per_m == pytest.approx(
        SPEED_OF_LIGHT_M_PER_S * metrics.a_total_ohm_per_m2 / 4
    )


def test_native_crosscheck_controls_derived_validity() -> None:
    frequency = 1.0e9
    fields = {point: _field(1.0) for point in (
        "center", "x_plus", "x_minus", "y_plus", "y_minus"
    )}
    metrics = calculate_transverse_metrics(
        fields,
        frequency_hz=frequency,
        stored_energy_j=1.0,
    )
    candidate = EigenmodeCandidate(
        mode_id="M1",
        solver_window_id="W1",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=frequency,
        voltage_v=abs(metrics.voltages["center"]),
        r_over_q_ohm=metrics.offline_center_r_over_q_ohm,
        total_energy_j=1.0,
    )

    apply_transverse_metrics(candidate, metrics)
    assert candidate.derived_valid is True

    candidate.r_over_q_ohm *= 2
    apply_transverse_metrics(candidate, metrics)
    assert candidate.derived_valid is False
    assert "native_r_over_q_crosscheck_failed" in candidate.data_availability_reason


def test_field_correlation_is_invariant_to_global_complex_phase() -> None:
    first = _field(1.0 + 0.2j)
    second = _field((1.0 + 0.2j) * np.exp(1j * 1.7))

    assert phase_insensitive_field_correlation(first, second) == pytest.approx(1.0)


def test_mode_dedup_requires_field_agreement_not_frequency_alone() -> None:
    first = EigenmodeCandidate(
        mode_id="M1",
        solver_window_id="W1",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1.0e9,
        r_over_q_ohm=10.0,
    )
    duplicate = EigenmodeCandidate(
        mode_id="M2",
        solver_window_id="W2",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1.0001e9,
        r_over_q_ohm=10.1,
    )
    different = EigenmodeCandidate(
        mode_id="M3",
        solver_window_id="W3",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1.0002e9,
        r_over_q_ohm=10.0,
    )
    z = np.linspace(-0.03, 0.03, 301)
    base = ComplexLineField(z_m=z, ez_v_per_m=np.cos(30 * z))
    phase_rotated = ComplexLineField(
        z_m=z,
        ez_v_per_m=np.cos(30 * z) * np.exp(1j * 1.2),
    )
    orthogonal = ComplexLineField(z_m=z, ez_v_per_m=np.sin(30 * z))

    result = deduplicate_modes(
        [first, duplicate, different],
        {"M1": base, "M2": phase_rotated, "M3": orthogonal},
    )

    assert len(result) == 2
    assert result[0].duplicate_member_ids == ["M1", "M2"]
    assert result[1].mode_id == "M3"
