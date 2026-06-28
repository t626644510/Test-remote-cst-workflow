"""No-CST tests for Workflow 2 PSO wake fitting integration."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for _p in (str(_PROJECT_ROOT), _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from workflows.rfgun_hom_antenna import pso_wake_fit
from workflows.rfgun_hom_antenna.pso_wake_fit import (
    ModeFit,
    PeakDetectionSettings,
    PSOBounds,
    PSOSettings,
    WakeDerivedImpedanceSettings,
    WakeFitInput,
    WakeFitResult,
    build_wake_fit_input_from_config,
    derive_impedance_from_wake,
    detect_impedance_peaks,
    estimate_sigma_z_from_charge_distribution,
    fit_wake_with_pso,
    resonator_sum,
    wake_from_parameters,
)
import workflows.rfgun_hom_antenna.wakefield_objective as wake_obj_mod
from workflows.rfgun_hom_antenna.wakefield_objective import (
    LongitudinalImpedanceObjective,
    TransverseImpedanceObjective,
)


Z_PATH = r"1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z"
REF_IMP_X = r"1D Results\Particle Beams\ParticleBeam1\Wake impedance\X"
REF_IMP_Y = r"1D Results\Particle Beams\ParticleBeam1\Wake impedance\Y"
OFF_IMP_X = r"1D Results\Particle Beams\ParticleBeam2\Wake impedance\X"
OFF_IMP_Y = r"1D Results\Particle Beams\ParticleBeam2\Wake impedance\Y"
OFF_IMP_Z = r"1D Results\Particle Beams\ParticleBeam2\Wake impedance\Z"
WAKE_PATH = r"1D Results\Particle Beams\ParticleBeam1\Wake potential\Z"
REF_WAKE_X = r"1D Results\Particle Beams\ParticleBeam1\Wake potential\X"
REF_WAKE_Y = r"1D Results\Particle Beams\ParticleBeam1\Wake potential\Y"
OFF_WAKE_X = r"1D Results\Particle Beams\ParticleBeam2\Wake potential\X"
OFF_WAKE_Y = r"1D Results\Particle Beams\ParticleBeam2\Wake potential\Y"
OFF_PEAK_Y = OFF_IMP_Y


class _ResultItem:
    def __init__(self, xlabel: str = "Frequency / Hz") -> None:
        self.xlabel = xlabel
        self.ylabel = ""


class _DictReader:
    def __init__(
        self,
        curves: dict[str, tuple[np.ndarray, np.ndarray] | tuple[np.ndarray, np.ndarray, str]],
    ) -> None:
        self._curves = curves

    def get_1d_result(self, tree_path: str, run_id: int = 0):
        entry = self._curves[tree_path]
        return np.asarray(entry[0]), np.asarray(entry[1])

    def get_result_item(self, tree_path: str, run_id: int = 0):
        entry = self._curves.get(tree_path)
        xlabel = entry[2] if entry is not None and len(entry) >= 3 else "Frequency / Hz"
        return _ResultItem(str(xlabel))


def _exact_optimizer(x_expected: np.ndarray):
    def _optimizer(objective, lb, ub, settings):
        assert np.all(x_expected >= lb)
        assert np.all(x_expected <= ub)
        return x_expected.copy(), objective(x_expected), {"algorithm": "test_exact"}

    return _optimizer


def _single_mode_synthetic(direction: str = "longitudinal"):
    fr_hz = np.array([1.0e9])
    q = np.array([30.0])
    amplitude = np.array([2.5])
    x_best = np.array([amplitude[0], q[0]])
    s_m = np.linspace(0.01, 0.25, 160)
    wake = wake_from_parameters(x_best, fr_hz, s_m / 299_792_458.0, direction)
    f_hz = np.linspace(0.7e9, 1.3e9, 301)
    impedance = np.abs(resonator_sum(f_hz, fr_hz, q, np.array([20.0]), direction))
    return fr_hz, x_best, s_m, wake, f_hz, impedance


def test_detect_impedance_peaks_uses_sampled_grid_only() -> None:
    f_hz = np.array([1.0, 2.0, 3.0, 4.0, 5.0]) * 1.0e9
    z = np.array([0.0, 10.0, 0.0, 0.0, 0.0])

    peaks = detect_impedance_peaks(
        f_hz,
        z,
        PeakDetectionSettings(min_peak_height=1.0),
    )

    assert [peak.frequency_hz for peak in peaks] == [2.0e9]


def test_fit_wake_with_pso_reconstructs_synthetic_mode_with_fixed_optimizer() -> None:
    _, x_best, s_m, wake, f_hz, impedance = _single_mode_synthetic()
    fit_input = WakeFitInput(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=wake,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=0.003,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=2.0,
            amplitude_max=3.0,
            q_min=10.0,
            q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0,
            freq_min_hz=0.8e9,
            freq_max_hz=1.2e9,
        ),
        pso_settings=PSOSettings(seed=7),
        max_normalized_error=1.0e-18,
    )

    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_best))

    assert result.status == "ok"
    assert result.normalized_error < 1.0e-24
    assert len(result.modes) == 1
    assert result.modes[0].frequency_hz == pytest.approx(1.0e9)
    assert result.modes[0].amplitude == pytest.approx(2.5)
    assert result.modes[0].q == pytest.approx(30.0)
    assert len(result.impedance_abs) == len(f_hz)


def test_fit_window_config_uses_tail_only_with_units() -> None:
    _, _, s_m, wake, f_hz, impedance = _single_mode_synthetic()

    fit_input = build_wake_fit_input_from_config(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=wake,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        config={
            "sigma_z_m": 0.003,
            "fit_window": {
                "start_value": float(s_m[50] * 1.0e3),
                "start_unit": "mm",
                "end": "auto",
            },
            "fit_point_count": 25,
            "bounds": {
                "amplitude_min": 0.0,
                "amplitude_max": 5.0,
                "q_min": 1.0,
                "q_max": 50.0,
            },
        },
    )

    assert fit_input.fit_start_m == pytest.approx(float(s_m[50]))
    assert fit_input.fit_end_m == pytest.approx(float(s_m[-1]))


def test_fit_peak_range_is_independent_from_scalarization_defaults() -> None:
    _, _, s_m, wake, f_hz, impedance = _single_mode_synthetic()

    fit_input = build_wake_fit_input_from_config(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=wake,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        config={
            "sigma_z_m": 0.003,
            "fit_peak_freq_min_hz": 0.4e9,
            "fit_peak_freq_max_hz": 1.4e9,
            "bounds": {
                "amplitude_min": 0.0,
                "amplitude_max": 5.0,
                "q_min": 1.0,
                "q_max": 50.0,
            },
        },
        default_freq_min_hz=1.1e9,
        default_freq_max_hz=1.2e9,
    )

    assert fit_input.peak_settings.freq_min_hz == pytest.approx(0.4e9)
    assert fit_input.peak_settings.freq_max_hz == pytest.approx(1.4e9)


def test_estimate_sigma_z_from_charge_distribution_uses_abs_density() -> None:
    distance_m = np.array([-0.002, 0.0, 0.002])
    charge_density = np.array([-1.0, -2.0, -1.0])

    sigma = estimate_sigma_z_from_charge_distribution(distance_m, charge_density)

    assert sigma == pytest.approx(np.sqrt(2.0e-6))


def test_wake_derived_impedance_records_refined_visible_peaks() -> None:
    fr_hz = np.array([1.03e9])
    x_best = np.array([2.0, 35.0])
    s_m = np.linspace(0.0, 1.2, 900)
    wake = wake_from_parameters(x_best, fr_hz, s_m / 299_792_458.0, "longitudinal")

    derived = derive_impedance_from_wake(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=wake,
        sigma_z_m=0.02,
        peak_settings=PeakDetectionSettings(
            freq_min_hz=0.6e9,
            freq_max_hz=1.4e9,
            selection_strategy="top_amplitude",
            max_selected_modes=1,
        ),
        settings=WakeDerivedImpedanceSettings(
            freq_min_hz=0.5e9,
            freq_max_hz=1.5e9,
            wake_point_count=500,
            freq_point_count=121,
            adaptive_refine_factor=20,
            adaptive_half_width_bins=3,
            adaptive_max_freq_point_count=5000,
        ),
    )

    selected = [peak for peak in derived.peaks if peak.use]
    assert derived.local_grid_refinement_active
    assert len(selected) == 1
    assert selected[0].coarse_frequency_hz is not None
    assert selected[0].refined_frequency_hz is not None
    assert selected[0].source == "wake_derived_refined"


def test_fit_wake_with_pso_quality_gate_can_fail_on_poor_correlation() -> None:
    _, _, s_m, wake, f_hz, impedance = _single_mode_synthetic()
    poor_x = np.array([0.0, 10.0])
    fit_input = WakeFitInput(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=wake,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=0.003,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=0.0,
            amplitude_max=3.0,
            q_min=1.0,
            q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(min_peak_height=1.0),
        max_normalized_error=0.2,
        min_wake_corr=0.8,
    )

    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(poor_x))

    assert result.status == "failed"
    assert "exceeds max_normalized_error" in result.failure_reason


def test_longitudinal_default_path_still_uses_cst_impedance_curve() -> None:
    f_hz = np.array([0.8e9, 1.0e9, 1.2e9])
    z_ohm = np.array([1.0, 10.0, 2.0])
    reader = _DictReader({Z_PATH: (f_hz, z_ohm, "Frequency / Hz")})

    obj = LongitudinalImpedanceObjective(
        lambda: reader,
        strategy="peak_exceedance",
        z_threshold_ohm=7.0,
        freq_min_hz=0.7e9,
        freq_max_hz=1.3e9,
    )

    assert obj.raw_value() == pytest.approx(3.0)


def test_longitudinal_pso_source_scalarizes_reconstructed_impedance(monkeypatch) -> None:
    _, x_best, s_m, wake, f_hz, impedance = _single_mode_synthetic()
    reader = _DictReader({
        WAKE_PATH: (s_m, wake, "Distance / m"),
        Z_PATH: (f_hz, impedance, "Frequency / Hz"),
    })

    monkeypatch.setattr(
        pso_wake_fit,
        "_run_pymoo_pso",
        _exact_optimizer(x_best),
    )

    obj = LongitudinalImpedanceObjective(
        lambda: reader,
        strategy="peak_exceedance",
        z_threshold_ohm=0.0,
        freq_min_hz=0.8e9,
        freq_max_hz=1.2e9,
        fit_source="pso_wake",
        pso_fit={
            "wake_tree_path": WAKE_PATH,
            "wake_x_unit": "m",
            "wake_y_unit": "V/pC",
            "peak_source": "cst_impedance",
            "sigma_z_m": 0.003,
            "fit_start_m": float(s_m[0]),
            "fit_end_m": float(s_m[-1]),
            "fit_point_count": len(s_m),
            "bounds": {
                "amplitude_min": 2.0,
                "amplitude_max": 3.0,
                "q_min": 10.0,
                "q_max": 50.0,
            },
            "peak_settings": {
                "min_peak_height": 1.0,
                "freq_min_hz": 0.8e9,
                "freq_max_hz": 1.2e9,
            },
            "max_normalized_error": 1.0e-18,
        },
    )

    raw = obj.raw_value()

    assert obj.last_fit_result is not None
    assert raw == pytest.approx(float(np.max(obj.last_fit_result.impedance_abs)))


def test_longitudinal_pso_requires_explicit_wake_tree_path() -> None:
    reader = _DictReader({})
    obj = LongitudinalImpedanceObjective(
        lambda: reader,
        fit_source="pso_wake",
        pso_fit={
            "wake_x_unit": "m",
            "wake_y_unit": "V/pC",
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 1.0,
                "amplitude_max": 2.0,
                "q_min": 1.0,
                "q_max": 10.0,
            },
        },
    )

    with pytest.raises(ValueError, match="wake_tree_path"):
        obj.raw_value()


def test_transverse_pso_requires_offset_wake_tree_path() -> None:
    f_hz = np.array([0.8e9, 1.0e9, 1.2e9])
    z_ohm = np.array([1.0, 10.0, 2.0])
    reader = _DictReader({Z_PATH: (f_hz, z_ohm, "Frequency / Hz")})
    obj = TransverseImpedanceObjective(
        lambda: reader,
        reference_beam="ParticleBeam1",
        offset_beams=[{"name": "ParticleBeam2", "offset_x_mm": 2.0}],
        fit_source="pso_wake",
        pso_fit={
            "wake_x_unit": "m",
            "wake_y_unit": "V/pC/m",
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 1.0,
                "amplitude_max": 2.0,
                "q_min": 1.0,
                "q_max": 10.0,
            },
        },
    )

    with pytest.raises(ValueError, match="wake_tree_paths"):
        obj.raw_value()


def test_transverse_pso_uses_reference_offset_wake_difference(monkeypatch) -> None:
    s_m = np.array([0.0, 0.05, 0.10])
    ref_x = np.array([1.0, 2.0, 3.0])
    ref_y = np.array([0.5, 1.0, 1.5])
    off_x = np.array([2.0, 4.0, 6.0])
    off_y = np.array([1.0, 2.0, 3.0])
    f_hz = np.array([0.8e9, 1.0e9, 1.2e9])
    peak_z = np.array([1.0, 10.0, 1.0])
    zero_z = np.zeros_like(peak_z)
    ref_reader = _DictReader({
        REF_WAKE_X: (s_m, ref_x, "s / m"),
        REF_WAKE_Y: (s_m, ref_y, "s / m"),
        Z_PATH: (f_hz, zero_z, "Frequency / Hz"),
        REF_IMP_X: (f_hz, zero_z, "Frequency / Hz"),
        REF_IMP_Y: (f_hz, zero_z, "Frequency / Hz"),
    })
    offset_reader = _DictReader({
        OFF_WAKE_X: (s_m, off_x, "s / m"),
        OFF_WAKE_Y: (s_m, off_y, "s / m"),
        OFF_IMP_X: (f_hz, peak_z, "Frequency / Hz"),
        OFF_IMP_Y: (f_hz, zero_z, "Frequency / Hz"),
        OFF_IMP_Z: (f_hz, zero_z, "Frequency / Hz"),
    })
    captured = {}
    expected_x = (off_x - ref_x) / 0.002
    expected_y = (off_y - ref_y) / 0.002

    def _fake_fit(fit_input):
        if np.allclose(fit_input.wake, expected_x):
            component = "x"
            impedance_abs = np.array([1.0, 3.0, 1.0])
        else:
            component = "y"
            impedance_abs = np.zeros_like(f_hz, dtype=float)
        captured[component] = fit_input.wake.copy()
        return WakeFitResult(
            modes=(ModeFit(1.0e9, 1.0, 10.0, 2.0, 20.0),),
            fit_s_m=s_m,
            fit_t_s=s_m / 299_792_458.0,
            fit_wake=fit_input.wake.copy(),
            wake_fit=fit_input.wake.copy(),
            impedance_frequency_hz=f_hz,
            impedance_complex=impedance_abs.astype(complex),
            impedance_abs=impedance_abs,
            normalized_error=0.0,
            wake_corr=1.0,
            objective_value=0.0,
            selected_peaks=(),
            all_peaks=(),
        )

    monkeypatch.setattr(wake_obj_mod, "fit_wake_with_pso", _fake_fit)

    obj = TransverseImpedanceObjective(
        lambda: offset_reader,
        ref_reader_factory=lambda: ref_reader,
        strategy="peak_exceedance",
        z_threshold_ohm_per_m=0.0,
        reference_beam="ParticleBeam1",
        offset_beams=[{"name": "ParticleBeam2", "offset_x_mm": 2.0}],
        fit_source="pso_wake",
        pso_fit={
            "wake_x_unit": "m",
            "wake_y_unit": "V/pC",
            "peak_source": "cst_impedance",
            "sigma_z_m": 0.003,
            "fit_start_m": 0.0,
            "fit_end_m": 0.1,
            "fit_point_count": 3,
            "wake_tree_paths": {
                "ParticleBeam2": {"x": OFF_WAKE_X, "y": OFF_WAKE_Y},
            },
            "reference_wake_tree_paths": {
                "x": REF_WAKE_X,
                "y": REF_WAKE_Y,
            },
            "bounds": {
                "amplitude_min": 0.1,
                "amplitude_max": 10.0,
                "q_min": 1.0,
                "q_max": 100.0,
            },
        },
    )

    raw = obj.raw_value()

    np.testing.assert_allclose(captured["x"], expected_x)
    np.testing.assert_allclose(captured["y"], expected_y)
    assert raw == pytest.approx(3.0)
