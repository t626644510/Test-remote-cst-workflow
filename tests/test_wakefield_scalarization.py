"""No-CST tests for wakefield impedance scalarization."""

from __future__ import annotations

import numpy as np

from cst_optimization.physics.wakefield import scalarize


def test_quadratic_peak_barrier_masks_fundamental_peak() -> None:
    frequencies = np.array([500.0e6, 600.0e6, 700.0e6])
    impedance = np.array([9000.0, 1800.0, 1900.0])

    penalty = scalarize(
        frequencies,
        impedance,
        z_threshold=2000.0,
        strategy="quadratic_peak_barrier",
        freq_min_hz=550.0e6,
        peak_barrier_scale=500.0,
    )

    assert penalty == 0.0


def test_quadratic_peak_barrier_penalizes_peak_excess() -> None:
    frequencies = np.array([600.0e6, 700.0e6, 800.0e6])
    impedance = np.array([1800.0, 2500.0, 3000.0])

    penalty = scalarize(
        frequencies,
        impedance,
        z_threshold=2000.0,
        strategy="quadratic_peak_barrier",
        peak_barrier_scale=500.0,
    )

    assert penalty == 4.0


def test_quadratic_peak_barrier_can_add_area_tie_breaker() -> None:
    frequencies = np.array([600.0e6, 700.0e6, 800.0e6])
    impedance = np.array([2000.0, 2500.0, 3000.0])

    penalty = scalarize(
        frequencies,
        impedance,
        z_threshold=2000.0,
        strategy="quadratic_peak_barrier",
        peak_barrier_scale=500.0,
        integral_weight=0.2,
    )

    normalized_area = np.trapezoid(
        [0.0, 500.0, 1000.0],
        frequencies,
    ) / (2000.0 * (800.0e6 - 600.0e6))
    np.testing.assert_allclose(penalty, 4.0 + 0.2 * normalized_area)


def test_soft_quadratic_peak_barrier_is_bounded() -> None:
    frequencies = np.array([600.0e6, 700.0e6, 800.0e6])
    impedance = np.array([1800.0, 2500.0, 3000.0])

    penalty = scalarize(
        frequencies,
        impedance,
        z_threshold=2000.0,
        strategy="soft_quadratic_peak_barrier",
        peak_barrier_scale=500.0,
    )

    assert penalty == 0.8


def test_soft_quadratic_peak_barrier_masks_fundamental_peak() -> None:
    frequencies = np.array([500.0e6, 600.0e6, 700.0e6])
    impedance = np.array([9000.0, 1800.0, 1900.0])

    penalty = scalarize(
        frequencies,
        impedance,
        z_threshold=2000.0,
        strategy="soft_quadratic_peak_barrier",
        freq_min_hz=550.0e6,
        peak_barrier_scale=500.0,
    )

    assert penalty == 0.0
