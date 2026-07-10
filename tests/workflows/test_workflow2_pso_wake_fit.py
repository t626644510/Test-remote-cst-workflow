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
    C_LIGHT_M_PER_S,
    KnownMode,
    ModeFit,
    WakeFitError,
    _filter_known_mode_peaks,
    _gaussian_form_factor,
    FrequencyFitSettings,
    PeakDetectionSettings,
    PSOBounds,
    PSOSettings,
    WakeDerivedImpedanceSettings,
    WakeFitInput,
    WakeFitResult,
    build_wake_fit_input_from_config,
    compute_known_mode_wake,
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


def test_detect_impedance_peaks_can_filter_by_estimated_q() -> None:
    f_hz = np.linspace(0.8e9, 1.3e9, 5001)
    broad = 10.0 / (1.0 + ((f_hz - 0.95e9) / 50.0e6) ** 2)
    narrow = 0.8 / (1.0 + ((f_hz - 1.15e9) / 0.8e6) ** 2)
    z = broad + narrow

    peaks = detect_impedance_peaks(
        f_hz,
        z,
        PeakDetectionSettings(
            min_peak_height=None,
            min_peak_distance_points=50,
            min_estimated_q=100.0,
        ),
    )

    assert len(peaks) == 1
    assert peaks[0].frequency_hz == pytest.approx(1.15e9, rel=1e-4)
    assert peaks[0].estimated_q is not None
    assert peaks[0].estimated_q > 100.0
    assert peaks[0].width_hz is not None
    assert peaks[0].q_estimate_status == "ok"


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
    assert result.diagnostics["frequency_fit_enabled"] is False
    assert result.diagnostics["frequency_shift_hz"] == [0.0]


def test_frequency_fit_moves_hom_frequency_within_configured_window() -> None:
    direction = "longitudinal"
    sigma_z_m = 0.003
    true_fr = 1.5e9
    detected_fr = 1.49e9
    hom_amp = 4.0
    hom_q = 45.0
    s_m = np.linspace(0.01, 0.25, 180)
    t_s = s_m / C_LIGHT_M_PER_S
    wake = wake_from_parameters(
        np.array([hom_amp, hom_q]), np.array([true_fr]), t_s, direction
    )
    f_hz = np.linspace(1.4e9, 1.6e9, 401)
    impedance = np.abs(
        resonator_sum(
            f_hz,
            np.array([detected_fr]),
            np.array([hom_q]),
            np.array([50.0]),
            direction,
        )
    )
    expected = np.array([true_fr, hom_amp, hom_q])
    captured: dict[str, np.ndarray] = {}

    def _capture_optimizer(objective, lb, ub, settings):
        captured["lb"] = lb.copy()
        captured["ub"] = ub.copy()
        assert np.all(expected >= lb)
        assert np.all(expected <= ub)
        return expected.copy(), objective(expected), {"algorithm": "test_frequency_fit"}

    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=wake,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=1.0,
            amplitude_max=6.0,
            q_min=20.0,
            q_max=80.0,
        ),
        peak_settings=PeakDetectionSettings(
            freq_min_hz=1.45e9,
            freq_max_hz=1.55e9,
        ),
        pso_settings=PSOSettings(seed=7),
        precomputed_peaks=(pso_wake_fit.PeakInfo(0, detected_fr, 10.0),),
        frequency_fit=FrequencyFitSettings(enabled=True, half_width_hz=20.0e6),
    )

    result = fit_wake_with_pso(fit_input, optimizer=_capture_optimizer)

    assert result.status == "ok"
    assert len(result.modes) == 1
    assert result.modes[0].frequency_hz == pytest.approx(true_fr)
    assert result.modes[0].amplitude == pytest.approx(hom_amp)
    assert result.modes[0].q == pytest.approx(hom_q)
    np.testing.assert_allclose(captured["lb"], np.array([1.47e9, 1.0, 20.0]))
    np.testing.assert_allclose(captured["ub"], np.array([1.51e9, 6.0, 80.0]))
    diag = result.diagnostics
    assert diag["frequency_fit_enabled"] is True
    assert diag["initial_peak_frequency_hz"] == [pytest.approx(detected_fr)]
    assert diag["fitted_frequency_hz"] == [pytest.approx(true_fr)]
    assert diag["frequency_shift_hz"] == [pytest.approx(true_fr - detected_fr)]


def test_frequency_fit_rejects_overlapping_windows() -> None:
    _, _, s_m, wake, f_hz, impedance = _single_mode_synthetic()
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
            amplitude_max=5.0,
            q_min=10.0,
            q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(freq_min_hz=0.9e9, freq_max_hz=1.2e9),
        precomputed_peaks=(
            pso_wake_fit.PeakInfo(0, 1.0e9, 10.0),
            pso_wake_fit.PeakInfo(1, 1.005e9, 9.0),
        ),
        frequency_fit=FrequencyFitSettings(enabled=True, half_width_hz=10.0e6),
    )

    with pytest.raises(WakeFitError, match="overlap"):
        fit_wake_with_pso(fit_input, optimizer=_raises_optimizer)


def test_frequency_fit_rejects_transverse_direction() -> None:
    _, _, s_m, wake, f_hz, impedance = _single_mode_synthetic("transverse")
    fit_input = WakeFitInput(
        direction="transverse",
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
            amplitude_max=5.0,
            q_min=10.0,
            q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(min_peak_height=1.0),
        frequency_fit=FrequencyFitSettings(enabled=True, half_width_hz=5.0e6),
    )

    with pytest.raises(WakeFitError, match="longitudinal"):
        fit_wake_with_pso(fit_input, optimizer=_raises_optimizer)


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


def test_frequency_fit_config_reaches_wake_fit_input() -> None:
    _, _, s_m, wake, f_hz, impedance = _single_mode_synthetic()

    fit_input = build_wake_fit_input_from_config(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=wake,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        config={
            "sigma_z_m": 0.003,
            "fit_point_count": len(s_m),
            "bounds": {
                "amplitude_min": 0.0,
                "amplitude_max": 5.0,
                "q_min": 1.0,
                "q_max": 50.0,
            },
            "peak_settings": {
                "min_estimated_q": 100.0,
            },
            "frequency_fit": {
                "enabled": True,
                "half_width_hz": 5.0e6,
                "overlap_policy": "reject",
            },
        },
    )

    assert fit_input.peak_settings.min_estimated_q == pytest.approx(100.0)
    assert fit_input.frequency_fit.enabled is True
    assert fit_input.frequency_fit.half_width_hz == pytest.approx(5.0e6)
    assert fit_input.frequency_fit.overlap_policy == "reject"


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


# ---------------------------------------------------------------------------
# Known / fixed-mode support
# ---------------------------------------------------------------------------


def test_known_mode_compute_wake_matches_direct_evaluation() -> None:
    """compute_known_mode_wake produces the same wake as a direct
    wake_from_parameters call with amplitude converted from R/Q."""
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    direction = "longitudinal"
    s_m = np.linspace(0.01, 0.25, 160)
    t_s = s_m / C_LIGHT_M_PER_S

    km = KnownMode(label="test", frequency_hz=1.0e9, q=30.0, r_over_q_ohm=20.0)
    computed = compute_known_mode_wake(
        (km,), t_s, direction, sigma_z_m, wake_charge_scale
    )

    # Manually apply the documented conversion formula
    ff = _gaussian_form_factor(sigma_z_m, np.array([km.frequency_hz]))
    amp = km.r_over_q_ohm * float(ff[0]) * (2.0 * np.pi * km.frequency_hz) / wake_charge_scale
    expected = wake_from_parameters(
        np.array([amp, km.q]), np.array([km.frequency_hz]), t_s, direction
    )

    np.testing.assert_allclose(computed, expected)
    assert np.max(np.abs(computed)) > 0.0  # non-zero wake


def test_known_mode_empty_known_modes_produces_zero_wake() -> None:
    """Empty known_modes tuple produces a zero known-mode wake."""
    t_s = np.linspace(0, 1e-9, 50)
    wake = compute_known_mode_wake((), t_s, "longitudinal", 0.003, 1.0e12)
    assert np.all(wake == 0.0)
    assert wake.shape == t_s.shape


def test_known_mode_metadata_in_fit_result() -> None:
    """fit_wake_with_pso includes known-mode metadata in the result."""
    _, x_best, s_m, wake, f_hz, impedance = _single_mode_synthetic()

    known = KnownMode(
        label="fundamental",
        frequency_hz=1.0e9,
        q=30.0,
        r_over_q_ohm=20.0,
    )
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
            amplitude_min=2.0, amplitude_max=3.0, q_min=10.0, q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.8e9, freq_max_hz=1.2e9,
        ),
        pso_settings=PSOSettings(seed=7),
        known_modes=(known,),
    )

    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_best))

    assert result.status == "ok"
    assert len(result.known_modes) == 1
    assert result.known_modes[0].label == "fundamental"
    assert result.known_modes[0].frequency_hz == pytest.approx(1.0e9)
    assert result.known_mode_wake is not None
    assert result.known_mode_wake.shape == s_m.shape
    assert np.max(np.abs(result.known_mode_wake)) > 0.01  # non-trivial wake
    assert result.known_mode_wake is not result.wake_fit  # distinct arrays


def test_known_mode_target_fully_explained_by_known_wake() -> None:
    """When the known mode exactly matches the synthetic wake and fitted
    amplitude is forced to zero, the total fit equals the known-mode wake."""
    direction = "longitudinal"
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    s_m = np.linspace(0.01, 0.25, 160)
    t_s = s_m / C_LIGHT_M_PER_S

    # Build a known mode and convert its R/Q to amplitude for the target
    km = KnownMode(label="fundamental", frequency_hz=1.0e9, q=30.0, r_over_q_ohm=20.0)
    ff = _gaussian_form_factor(sigma_z_m, np.array([km.frequency_hz]))
    amp = km.r_over_q_ohm * float(ff[0]) * (2.0 * np.pi * km.frequency_hz) / wake_charge_scale

    # Synthetic target from the known-mode parameters
    target = wake_from_parameters(
        np.array([amp, km.q]), np.array([km.frequency_hz]), t_s, direction
    )

    f_hz = np.linspace(0.7e9, 1.3e9, 301)
    impedance = np.abs(resonator_sum(
        f_hz, np.array([km.frequency_hz]), np.array([km.q]),
        np.array([km.r_over_q_ohm]), direction,
    ))

    # Fit with known mode and exact optimizer producing zero amplitude
    x_zero = np.array([0.0, km.q])
    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=target,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=0.0, amplitude_max=0.0, q_min=10.0, q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.8e9, freq_max_hz=1.2e9,
        ),
        pso_settings=PSOSettings(seed=7),
        known_modes=(km,),
    )

    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_zero))

    assert result.status == "ok"
    # The known mode alone explains the entire target wake
    np.testing.assert_allclose(result.wake_fit, target, atol=1e-15)
    np.testing.assert_allclose(result.known_mode_wake, target, atol=1e-15)
    assert result.normalized_error == pytest.approx(0.0, abs=1e-24)


def test_known_mode_plus_hom_exact_optimizer() -> None:
    """With fundamental as known mode, exact HOM parameters yield near-zero
    residual when the HOM is the only fitted mode."""
    direction = "longitudinal"
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    s_m = np.linspace(0.01, 0.25, 400)
    t_s = s_m / C_LIGHT_M_PER_S

    # Fundamental (will be supplied as known)
    fund_fr, fund_q, fund_rq = 500.0e6, 100.0, 50.0
    ff_fund = _gaussian_form_factor(sigma_z_m, np.array([fund_fr]))
    fund_amp = (
        fund_rq * float(ff_fund[0]) * (2.0 * np.pi * fund_fr) / wake_charge_scale
    )

    # HOM (will be fitted)
    hom_fr, hom_q, hom_amp = 1.5e9, 50.0, 10.0

    # Combined synthetic target: fundamental + HOM
    all_fr = np.array([fund_fr, hom_fr])
    all_params = np.array([fund_amp, fund_q, hom_amp, hom_q])
    target = wake_from_parameters(all_params, all_fr, t_s, direction)

    # Impedance for HOM peak detection
    f_hz = np.linspace(1.2e9, 1.8e9, 301)
    impedance = np.abs(resonator_sum(
        f_hz, np.array([hom_fr]), np.array([hom_q]),
        np.array([100.0]), direction,
    ))

    known = KnownMode(
        label="fundamental", frequency_hz=fund_fr, q=fund_q,
        r_over_q_ohm=fund_rq,
    )
    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=target,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=5.0, amplitude_max=15.0,
            q_min=20.0, q_max=100.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=1.2e9, freq_max_hz=1.8e9,
        ),
        pso_settings=PSOSettings(seed=42),
        known_modes=(known,),
    )

    # Exact optimizer with the correct HOM parameters
    x_hom = np.array([hom_amp, hom_q])
    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_hom))

    assert result.status == "ok"
    assert len(result.known_modes) == 1
    assert result.known_modes[0].label == "fundamental"
    assert len(result.modes) == 1  # one fitted HOM mode
    # The total fit should match the target very closely
    assert result.normalized_error < 1.0e-24
    assert result.wake_corr == pytest.approx(1.0, abs=1e-12)


def test_known_mode_without_known_falls_back_to_existing_behavior() -> None:
    """When known_modes is not provided, existing test passes identically."""
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
            amplitude_min=2.0, amplitude_max=3.0,
            q_min=10.0, q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.8e9, freq_max_hz=1.2e9,
        ),
        pso_settings=PSOSettings(seed=7),
        max_normalized_error=1.0e-18,
    )

    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_best))

    assert result.status == "ok"
    assert result.normalized_error < 1.0e-24
    assert len(result.modes) == 1
    assert result.modes[0].frequency_hz == pytest.approx(1.0e9)
    assert result.known_modes == ()
    assert result.known_mode_wake is None


# ---------------------------------------------------------------------------
# Known-mode peak filtering (P01 follow-up)
# ---------------------------------------------------------------------------


def _raises_optimizer(objective, lb, ub, settings):
    """Optimizer that must never be called."""
    raise RuntimeError("PSO optimizer was called but all peaks are known modes.")


def test_known_mode_filter_peaks_matches_by_tolerance() -> None:
    """_filter_known_mode_peaks correctly separates known and unknown peaks."""
    from workflows.rfgun_hom_antenna.pso_wake_fit import PeakInfo

    peaks = (
        PeakInfo(0, 500.0e6, 10.0),
        PeakInfo(1, 1.5e9, 5.0),
        PeakInfo(2, 2.0e9, 3.0),
    )
    known = (
        KnownMode(label="fund", frequency_hz=500.0e6, q=100.0, r_over_q_ohm=50.0),
        KnownMode(label="damping", frequency_hz=2.0e9, q=30.0, r_over_q_ohm=10.0),
    )

    unknown, filtered = _filter_known_mode_peaks(peaks, known)

    assert len(unknown) == 1
    assert unknown[0].frequency_hz == pytest.approx(1.5e9)
    assert len(filtered) == 2
    assert filtered[0].frequency_hz == pytest.approx(500.0e6)
    assert filtered[1].frequency_hz == pytest.approx(2.0e9)


def test_known_mode_filter_empty_list() -> None:
    """_filter_known_mode_peaks returns all peaks unchanged when no known modes."""
    from workflows.rfgun_hom_antenna.pso_wake_fit import PeakInfo

    peaks = (PeakInfo(0, 1.0e9, 5.0),)
    unknown, filtered = _filter_known_mode_peaks(peaks, ())
    assert len(unknown) == 1
    assert len(filtered) == 0


def test_known_mode_only_known_peaks_in_source() -> None:
    """When the peak source contains only a known-mode peak, the known mode
    is filtered out, zero unknown peaks remain, and the optimizer is never
    called. The known mode alone explains the target wake."""
    direction = "longitudinal"
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    s_m = np.linspace(0.01, 0.25, 160)
    t_s = s_m / C_LIGHT_M_PER_S

    # Single mode that will be provided as known
    km = KnownMode(label="fund", frequency_hz=1.0e9, q=30.0, r_over_q_ohm=20.0)
    ff = _gaussian_form_factor(sigma_z_m, np.array([km.frequency_hz]))
    amp = km.r_over_q_ohm * float(ff[0]) * (2.0 * np.pi * km.frequency_hz) / wake_charge_scale

    target = wake_from_parameters(
        np.array([amp, km.q]), np.array([km.frequency_hz]), t_s, direction
    )

    # Impedance curve with a visible peak at the known-mode frequency
    f_hz = np.linspace(0.7e9, 1.3e9, 301)
    impedance = np.abs(resonator_sum(
        f_hz, np.array([km.frequency_hz]), np.array([km.q]),
        np.array([km.r_over_q_ohm]), direction,
    ))

    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=target,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=0.0, amplitude_max=0.0,
            q_min=10.0, q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.8e9, freq_max_hz=1.2e9,
        ),
        pso_settings=PSOSettings(seed=7),
        known_modes=(km,),
    )

    # _raises_optimizer ensures the PSO is never called
    result = fit_wake_with_pso(fit_input, optimizer=_raises_optimizer)

    assert result.status == "ok"
    assert len(result.modes) == 0  # no fitted unknown modes
    assert len(result.known_modes) == 1
    assert result.known_modes[0].label == "fund"
    assert result.known_mode_wake is not None
    # Known mode alone explains the target
    np.testing.assert_allclose(result.wake_fit, target, atol=1e-15)
    np.testing.assert_allclose(result.known_mode_wake, target, atol=1e-15)
    # The fundamental peak should be marked as filtered in all_peaks
    filtered_peaks = [p for p in result.all_peaks if p.status == "KnownModeFiltered"]
    assert len(filtered_peaks) >= 1
    assert filtered_peaks[0].frequency_hz == pytest.approx(1.0e9)


def test_known_mode_plus_hom_peak_filtering() -> None:
    """When the peak source contains both a known fundamental peak and an
    unknown HOM peak, only the HOM remains in result.modes after filtering."""
    direction = "longitudinal"
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    s_m = np.linspace(0.01, 0.25, 400)
    t_s = s_m / C_LIGHT_M_PER_S

    # Fundamental (will be supplied as known)
    fund_fr, fund_q, fund_rq = 500.0e6, 100.0, 50.0
    ff_fund = _gaussian_form_factor(sigma_z_m, np.array([fund_fr]))
    fund_amp = (
        fund_rq * float(ff_fund[0]) * (2.0 * np.pi * fund_fr) / wake_charge_scale
    )

    # HOM (will be fitted)
    hom_fr, hom_q, hom_amp = 1.5e9, 50.0, 10.0

    # Combined synthetic target: fundamental + HOM
    all_fr = np.array([fund_fr, hom_fr])
    all_params = np.array([fund_amp, fund_q, hom_amp, hom_q])
    target = wake_from_parameters(all_params, all_fr, t_s, direction)

    # Impedance curve covering BOTH peaks: fundamental + HOM
    f_hz = np.linspace(0.3e9, 1.8e9, 1501)
    impedance = np.abs(resonator_sum(
        f_hz,
        np.array([fund_fr, hom_fr]),
        np.array([fund_q, hom_q]),
        np.array([fund_rq, 100.0]),
        direction,
    ))

    known = KnownMode(
        label="fundamental", frequency_hz=fund_fr, q=fund_q,
        r_over_q_ohm=fund_rq, frequency_tolerance_hz=1.0e6,
    )
    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=target,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=5.0, amplitude_max=15.0,
            q_min=20.0, q_max=100.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.3e9, freq_max_hz=1.8e9,
        ),
        pso_settings=PSOSettings(seed=42),
        known_modes=(known,),
    )

    x_hom = np.array([hom_amp, hom_q])
    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_hom))

    assert result.status == "ok"
    assert len(result.known_modes) == 1
    # Only the HOM should be in fitted modes (fundamental filtered out)
    assert len(result.modes) == 1
    # The fitted mode frequency should be the HOM, not the fundamental
    assert result.modes[0].frequency_hz == pytest.approx(hom_fr, rel=1e-4)
    # The fundamental's peak should appear as "KnownModeFiltered" in all_peaks
    filtered_fund = [
        p for p in result.all_peaks
        if p.status == "KnownModeFiltered"
        and abs(p.frequency_hz - fund_fr) < 1.0e6
    ]
    assert len(filtered_fund) >= 1
    # The HOM peak should be selected as "Use"
    hom_selected = [
        p for p in result.all_peaks
        if p.status == "Use"
        and abs(p.frequency_hz - hom_fr) < 1.0e6
    ]
    assert len(hom_selected) >= 1


# ---------------------------------------------------------------------------
# P02: known_modes config parsing and objective integration
# ---------------------------------------------------------------------------


def test_known_modes_from_config_parses_full_valid_entry() -> None:
    """build_wake_fit_input_from_config parses known_modes correctly."""
    config = {
        "sigma_z_m": 0.003,
        "bounds": {
            "amplitude_min": 0.0, "amplitude_max": 5.0,
            "q_min": 1.0, "q_max": 50.0,
        },
        "known_modes": [
            {
                "label": "fundamental",
                "direction": "longitudinal",
                "frequency_hz": 499.8e6,
                "q": 36500,
                "r_over_q_ohm": 208.6,
                "frequency_tolerance_hz": 0.5e6,
                "include_in_reconstructed_impedance": True,
            }
        ],
    }
    s_m = np.linspace(0.0, 0.1, 50)
    f_hz = np.linspace(0.3e9, 1.8e9, 100)
    fit_input = build_wake_fit_input_from_config(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=np.zeros_like(s_m),
        impedance_frequency_hz=f_hz,
        impedance=np.ones_like(f_hz),
        config=config,
    )

    assert len(fit_input.known_modes) == 1
    km = fit_input.known_modes[0]
    assert km.label == "fundamental"
    assert km.frequency_hz == pytest.approx(499.8e6)
    assert km.q == pytest.approx(36500)
    assert km.r_over_q_ohm == pytest.approx(208.6)
    assert km.frequency_tolerance_hz == pytest.approx(0.5e6)
    assert km.include_in_reconstructed_impedance is True


def test_known_modes_from_config_default_fields() -> None:
    """Optional fields get sensible defaults."""
    config = {
        "sigma_z_m": 0.003,
        "bounds": {
            "amplitude_min": 0.0, "amplitude_max": 5.0,
            "q_min": 1.0, "q_max": 50.0,
        },
        "known_modes": [
            {
                "frequency_hz": 1.0e9,
                "q": 100.0,
                "r_over_q_ohm": 50.0,
            }
        ],
    }
    s_m = np.linspace(0.0, 0.1, 50)
    f_hz = np.linspace(0.3e9, 1.8e9, 100)
    fit_input = build_wake_fit_input_from_config(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=np.zeros_like(s_m),
        impedance_frequency_hz=f_hz,
        impedance=np.ones_like(f_hz),
        config=config,
    )

    assert len(fit_input.known_modes) == 1
    km = fit_input.known_modes[0]
    # label defaults to known_0
    assert km.label == "known_0"
    # tolerance defaults to 0.0
    assert km.frequency_tolerance_hz == pytest.approx(0.0)
    # include defaults to True
    assert km.include_in_reconstructed_impedance is True


def test_known_modes_from_config_empty_when_absent() -> None:
    """Known_modes defaults to () when not in config."""
    config = {
        "sigma_z_m": 0.003,
        "bounds": {
            "amplitude_min": 0.0, "amplitude_max": 5.0,
            "q_min": 1.0, "q_max": 50.0,
        },
    }
    s_m = np.linspace(0.0, 0.1, 50)
    f_hz = np.linspace(0.3e9, 1.8e9, 100)
    fit_input = build_wake_fit_input_from_config(
        direction="longitudinal",
        wake_s_m=s_m,
        wake=np.zeros_like(s_m),
        impedance_frequency_hz=f_hz,
        impedance=np.ones_like(f_hz),
        config=config,
    )
    assert fit_input.known_modes == ()


class TestKnownModesFromConfigRequiredFields:
    """Each missing required field raises a clear WakeFitError."""

    @pytest.mark.parametrize("missing_key", ["frequency_hz", "q", "r_over_q_ohm"])
    def test_missing_required_field(self, missing_key: str) -> None:
        base = {
            "frequency_hz": 1.0e9,
            "q": 100.0,
            "r_over_q_ohm": 50.0,
        }
        del base[missing_key]
        config = {
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 0.0, "amplitude_max": 5.0,
                "q_min": 1.0, "q_max": 50.0,
            },
            "known_modes": [base],
        }
        s_m = np.linspace(0.0, 0.1, 50)
        f_hz = np.linspace(0.3e9, 1.8e9, 100)

        with pytest.raises(WakeFitError) as exc_info:
            build_wake_fit_input_from_config(
                direction="longitudinal",
                wake_s_m=s_m,
                wake=np.zeros_like(s_m),
                impedance_frequency_hz=f_hz,
                impedance=np.ones_like(f_hz),
                config=config,
            )
        msg = str(exc_info.value)
        assert "known_modes" in msg, f"Error should mention known_modes: {msg}"
        assert missing_key in msg, f"Error should mention {missing_key}: {msg}"

    def test_longitudinal_known_mode_q_must_exceed_half(self) -> None:
        """Longitudinal known mode with q=0.5 is rejected at config parsing."""
        config = {
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 0.0, "amplitude_max": 5.0,
                "q_min": 1.0, "q_max": 50.0,
            },
            "known_modes": [
                {
                    "frequency_hz": 1.0e9,
                    "q": 0.5,
                    "r_over_q_ohm": 50.0,
                }
            ],
        }
        s_m = np.linspace(0.0, 0.1, 50)
        f_hz = np.linspace(0.3e9, 1.8e9, 100)

        with pytest.raises(WakeFitError) as exc_info:
            build_wake_fit_input_from_config(
                direction="longitudinal",
                wake_s_m=s_m,
                wake=np.zeros_like(s_m),
                impedance_frequency_hz=f_hz,
                impedance=np.ones_like(f_hz),
                config=config,
            )
        msg = str(exc_info.value)
        assert "known_modes" in msg, f"Error should mention known_modes: {msg}"
        assert ".q" in msg, f"Error should mention .q: {msg}"
        assert "> 0.5" in msg, f"Error should mention > 0.5: {msg}"
        assert "0.5" in msg, f"Error should mention 0.5: {msg}"

    def test_frequency_tolerance_must_be_finite(self) -> None:
        """Known-mode frequency tolerance rejects NaN instead of silently
        disabling peak filtering."""
        config = {
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 0.0, "amplitude_max": 5.0,
                "q_min": 1.0, "q_max": 50.0,
            },
            "known_modes": [
                {
                    "frequency_hz": 1.0e9,
                    "q": 100.0,
                    "r_over_q_ohm": 50.0,
                    "frequency_tolerance_hz": float("nan"),
                }
            ],
        }
        s_m = np.linspace(0.0, 0.1, 50)
        f_hz = np.linspace(0.3e9, 1.8e9, 100)

        with pytest.raises(WakeFitError) as exc_info:
            build_wake_fit_input_from_config(
                direction="longitudinal",
                wake_s_m=s_m,
                wake=np.zeros_like(s_m),
                impedance_frequency_hz=f_hz,
                impedance=np.ones_like(f_hz),
                config=config,
            )
        msg = str(exc_info.value)
        assert "frequency_tolerance_hz" in msg
        assert "finite" in msg


class TestKnownModesFromConfigDirectionValidation:
    """Direction mismatch raises a clear error."""

    def test_transverse_known_mode_in_longitudinal_fit(self) -> None:
        config = {
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 0.0, "amplitude_max": 5.0,
                "q_min": 1.0, "q_max": 50.0,
            },
            "known_modes": [
                {
                    "frequency_hz": 1.0e9,
                    "q": 100.0,
                    "r_over_q_ohm": 50.0,
                    "direction": "transverse",
                }
            ],
        }
        s_m = np.linspace(0.0, 0.1, 50)
        f_hz = np.linspace(0.3e9, 1.8e9, 100)

        with pytest.raises(WakeFitError) as exc_info:
            build_wake_fit_input_from_config(
                direction="longitudinal",
                wake_s_m=s_m,
                wake=np.zeros_like(s_m),
                impedance_frequency_hz=f_hz,
                impedance=np.ones_like(f_hz),
                config=config,
            )
        msg = str(exc_info.value)
        assert "longitudinal" in msg
        assert "transverse" in msg

    def test_known_modes_are_not_implicitly_enabled_for_transverse_fit(self) -> None:
        """Stage S01 known-mode config is longitudinal-only even when the
        per-mode direction is omitted."""
        config = {
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 0.0, "amplitude_max": 5.0,
                "q_min": 1.0, "q_max": 50.0,
            },
            "known_modes": [
                {
                    "frequency_hz": 1.0e9,
                    "q": 100.0,
                    "r_over_q_ohm": 50.0,
                }
            ],
        }
        s_m = np.linspace(0.0, 0.1, 50)
        f_hz = np.linspace(0.3e9, 1.8e9, 100)

        with pytest.raises(WakeFitError) as exc_info:
            build_wake_fit_input_from_config(
                direction="transverse",
                wake_s_m=s_m,
                wake=np.zeros_like(s_m),
                impedance_frequency_hz=f_hz,
                impedance=np.ones_like(f_hz),
                config=config,
            )
        msg = str(exc_info.value)
        assert "known_modes" in msg
        assert "longitudinal" in msg
        assert "transverse" in msg

    def test_known_mode_direction_matches_fitting_direction(self) -> None:
        """Explicit matching direction should not raise."""
        config = {
            "sigma_z_m": 0.003,
            "bounds": {
                "amplitude_min": 0.0, "amplitude_max": 5.0,
                "q_min": 1.0, "q_max": 50.0,
            },
            "known_modes": [
                {
                    "frequency_hz": 1.0e9,
                    "q": 100.0,
                    "r_over_q_ohm": 50.0,
                    "direction": "longitudinal",
                }
            ],
        }
        s_m = np.linspace(0.0, 0.1, 50)
        f_hz = np.linspace(0.3e9, 1.8e9, 100)
        fit_input = build_wake_fit_input_from_config(
            direction="longitudinal",
            wake_s_m=s_m,
            wake=np.zeros_like(s_m),
            impedance_frequency_hz=f_hz,
            impedance=np.ones_like(f_hz),
            config=config,
        )
        assert len(fit_input.known_modes) == 1


class TestLongitudinalObjectiveWithKnownModes:
    """LongitudinalImpedanceObjective passes known_modes to fit_wake_with_pso."""

    def _make_fake_fit_result(self):
        return WakeFitResult(
            modes=(),
            fit_s_m=np.linspace(0, 0.1, 10),
            fit_t_s=np.linspace(0, 3.3e-10, 10),
            fit_wake=np.zeros(10),
            wake_fit=np.zeros(10),
            impedance_frequency_hz=np.array([0.9e9, 1.0e9, 1.1e9]),
            impedance_complex=np.array([0.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j]),
            impedance_abs=np.array([0.0, 0.0, 0.0]),
            normalized_error=0.0,
            wake_corr=1.0,
            objective_value=0.0,
            selected_peaks=(),
            all_peaks=(),
        )

    def test_known_modes_in_config_reaches_fit_input(self, monkeypatch) -> None:
        """When known_modes is in pso_fit config, the WakeFitInput.known_modes
        is populated and reaches fit_wake_with_pso."""

        captured_inputs = []

        def _capture_fit(fit_input):
            captured_inputs.append(fit_input)
            return self._make_fake_fit_result()

        # Patch fit_wake_with_pso in wakefield_objective's namespace (it was
        # imported via "from ... import fit_wake_with_pso").
        monkeypatch.setattr(
            wake_obj_mod, "fit_wake_with_pso", _capture_fit
        )

        s_m = np.linspace(0, 0.1, 10)
        wake = np.zeros_like(s_m)
        f_hz = np.array([0.8e9, 1.0e9, 1.2e9])
        impedance = np.array([1.0, 10.0, 2.0])

        reader = _DictReader({
            WAKE_PATH: (s_m, wake, "Distance / m"),
            Z_PATH: (f_hz, impedance, "Frequency / Hz"),
        })

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
                    "amplitude_min": 1.0,
                    "amplitude_max": 10.0,
                    "q_min": 1.0,
                    "q_max": 100.0,
                },
                "known_modes": [
                    {
                        "label": "fundamental",
                        "frequency_hz": 499.8e6,
                        "q": 36500,
                        "r_over_q_ohm": 208.6,
                    }
                ],
            },
        )

        raw = obj.raw_value()
        assert len(captured_inputs) == 1
        fit_input = captured_inputs[0]
        assert len(fit_input.known_modes) == 1
        km = fit_input.known_modes[0]
        assert km.label == "fundamental"
        assert km.frequency_hz == pytest.approx(499.8e6)

    def test_no_known_modes_in_config_passes_empty(self, monkeypatch) -> None:
        """Without known_modes in config, WakeFitInput.known_modes is empty."""

        captured_inputs = []

        def _capture_fit(fit_input):
            captured_inputs.append(fit_input)
            return self._make_fake_fit_result()

        monkeypatch.setattr(
            wake_obj_mod, "fit_wake_with_pso", _capture_fit
        )

        _, x_best, s_m, wake, f_hz, impedance = _single_mode_synthetic()

        reader = _DictReader({
            WAKE_PATH: (s_m, wake, "Distance / m"),
            Z_PATH: (f_hz, impedance, "Frequency / Hz"),
        })

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
                    "amplitude_min": 1.0,
                    "amplitude_max": 10.0,
                    "q_min": 1.0,
                    "q_max": 100.0,
                },
            },
        )

        raw = obj.raw_value()
        assert len(captured_inputs) == 1
        fit_input = captured_inputs[0]
        assert fit_input.known_modes == ()


# ---------------------------------------------------------------------------
# P03: diagnostics and stage validation
# ---------------------------------------------------------------------------


def test_known_mode_result_diagnostics_separate_known_unknown_residual() -> None:
    """WakeFitResult diagnostics correctly separate known, unknown, and residual."""
    direction = "longitudinal"
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    s_m = np.linspace(0.01, 0.25, 400)
    t_s = s_m / C_LIGHT_M_PER_S

    # Fundamental (known)
    fund_fr, fund_q, fund_rq = 500.0e6, 100.0, 50.0
    ff_fund = _gaussian_form_factor(sigma_z_m, np.array([fund_fr]))
    fund_amp = (
        fund_rq * float(ff_fund[0]) * (2.0 * np.pi * fund_fr) / wake_charge_scale
    )

    # HOM (fitted)
    hom_fr, hom_q, hom_amp = 1.5e9, 50.0, 10.0

    # Combined synthetic target
    all_fr = np.array([fund_fr, hom_fr])
    all_params = np.array([fund_amp, fund_q, hom_amp, hom_q])
    target = wake_from_parameters(all_params, all_fr, t_s, direction)

    # Impedance covering both peaks
    f_hz = np.linspace(0.3e9, 1.8e9, 1501)
    impedance = np.abs(resonator_sum(
        f_hz,
        np.array([fund_fr, hom_fr]),
        np.array([fund_q, hom_q]),
        np.array([fund_rq, 100.0]),
        direction,
    ))

    known = KnownMode(
        label="fundamental", frequency_hz=fund_fr, q=fund_q,
        r_over_q_ohm=fund_rq, frequency_tolerance_hz=1.0e6,
    )
    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=target,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=5.0, amplitude_max=15.0,
            q_min=20.0, q_max=100.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.3e9, freq_max_hz=1.8e9,
        ),
        pso_settings=PSOSettings(seed=42),
        known_modes=(known,),
    )

    x_hom = np.array([hom_amp, hom_q])
    result = fit_wake_with_pso(fit_input, optimizer=_exact_optimizer(x_hom))

    # --- known/fitted mode separation ---
    assert len(result.known_modes) == 1
    assert result.known_modes[0].label == "fundamental"
    assert len(result.modes) == 1
    assert result.modes[0].frequency_hz == pytest.approx(hom_fr, rel=1e-4)

    # --- known_mode_wake ---
    assert result.known_mode_wake is not None
    assert result.known_mode_wake.shape == s_m.shape
    assert np.max(np.abs(result.known_mode_wake)) > 0.01

    # --- unknown_mode_wake ---
    assert result.unknown_mode_wake is not None
    assert result.unknown_mode_wake.shape == s_m.shape
    assert np.max(np.abs(result.unknown_mode_wake)) > 0.01

    # --- wake_fit = known + unknown ---
    np.testing.assert_allclose(
        result.wake_fit,
        result.known_mode_wake + result.unknown_mode_wake,
    )

    # --- residual ---
    assert result.residual_wake is not None
    assert result.residual_wake.shape == s_m.shape
    np.testing.assert_allclose(
        result.residual_wake,
        result.fit_wake - result.wake_fit,
    )

    # --- diagnostics fields ---
    diag = result.diagnostics
    assert diag["known_mode_count"] == 1
    assert diag["fitted_mode_count"] == 1
    assert diag["known_mode_labels"] == ["fundamental"]
    assert diag["known_mode_wake_rms"] > 0.0
    assert diag["unknown_mode_wake_rms"] > 0.0
    assert diag["residual_wake_rms"] < 1e-8  # near-zero for exact match
    assert diag["normalized_error"] < 1e-24
    assert diag["wake_corr"] == pytest.approx(1.0, abs=1e-12)
    assert diag["target_wake_rms"] > 0.0
    # The fundamental peak should be filtered
    assert diag["known_mode_filtered_peak_count"] >= 1


def test_known_only_objective_value_reports_residual_sse() -> None:
    """Known-only imperfect fit reports meaningful objective_value."""
    direction = "longitudinal"
    sigma_z_m = 0.003
    wake_charge_scale = 1.0e12
    s_m = np.linspace(0.01, 0.25, 160)
    t_s = s_m / C_LIGHT_M_PER_S

    # Known mode definition
    km = KnownMode(label="fund", frequency_hz=1.0e9, q=30.0, r_over_q_ohm=20.0)

    # Generate target with DIFFERENT q (imperfect match)
    ff = _gaussian_form_factor(sigma_z_m, np.array([km.frequency_hz]))
    amp = km.r_over_q_ohm * float(ff[0]) * (2.0 * np.pi * km.frequency_hz) / wake_charge_scale
    target_q = km.q * 1.5  # intentionally different Q
    target = wake_from_parameters(
        np.array([amp, target_q]), np.array([km.frequency_hz]), t_s, direction
    )

    f_hz = np.linspace(0.7e9, 1.3e9, 301)
    impedance = np.abs(resonator_sum(
        f_hz, np.array([km.frequency_hz]), np.array([km.q]),
        np.array([km.r_over_q_ohm]), direction,
    ))

    # Use _raises_optimizer to ensure PSO is never called
    fit_input = WakeFitInput(
        direction=direction,
        wake_s_m=s_m,
        wake=target,
        impedance_frequency_hz=f_hz,
        impedance=impedance,
        sigma_z_m=sigma_z_m,
        fit_start_m=float(s_m[0]),
        fit_end_m=float(s_m[-1]),
        fit_point_count=len(s_m),
        bounds=PSOBounds(
            amplitude_min=0.0, amplitude_max=0.0,
            q_min=10.0, q_max=50.0,
        ),
        peak_settings=PeakDetectionSettings(
            min_peak_height=1.0, freq_min_hz=0.8e9, freq_max_hz=1.2e9,
        ),
        pso_settings=PSOSettings(seed=7),
        known_modes=(km,),
    )

    result = fit_wake_with_pso(fit_input, optimizer=_raises_optimizer)

    assert len(result.modes) == 0  # zero fitted modes
    assert result.known_mode_wake is not None
    assert result.residual_wake is not None
    # Residual should be non-zero (imperfect match)
    assert np.max(np.abs(result.residual_wake)) > 1e-6
    # objective_value should equal the sum-of-squares of the residual
    expected_sse = float(np.sum(result.residual_wake ** 2))
    assert result.objective_value == pytest.approx(expected_sse, rel=1e-12)
    assert result.normalized_error > 0.0


def test_longitudinal_objective_exposes_pso_wake_known_mode_diagnostics(
    monkeypatch,
) -> None:
    """LongitudinalImpedanceObjective.last_fit_result contains known-mode
    diagnostics when pso_wake path is used."""
    captured_inputs = []

    def _capture_fit(fit_input):
        captured_inputs.append(fit_input)
        return WakeFitResult(
            modes=(),
            fit_s_m=np.linspace(0, 0.1, 10),
            fit_t_s=np.linspace(0, 3.3e-10, 10),
            fit_wake=np.zeros(10),
            wake_fit=np.zeros(10),
            impedance_frequency_hz=np.array([0.9e9, 1.0e9, 1.1e9]),
            impedance_complex=np.array([0.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j]),
            impedance_abs=np.array([0.0, 0.0, 0.0]),
            normalized_error=0.0,
            wake_corr=1.0,
            objective_value=0.0,
            selected_peaks=(),
            all_peaks=(),
            known_modes=(KnownMode(
                label="fundamental", frequency_hz=499.8e6,
                q=36500, r_over_q_ohm=208.6,
            ),),
            known_mode_wake=np.zeros(10),
            unknown_mode_wake=np.zeros(10),
            residual_wake=np.zeros(10),
            diagnostics={
                "known_mode_count": 1,
                "fitted_mode_count": 0,
                "known_mode_labels": ["fundamental"],
                "target_wake_rms": 0.1,
                "known_mode_wake_rms": 0.05,
                "unknown_mode_wake_rms": 0.0,
                "residual_wake_rms": 0.0,
                "normalized_error": 0.0,
                "wake_corr": 1.0,
                "known_mode_filtered_peak_count": 0,
            },
        )

    monkeypatch.setattr(
        wake_obj_mod, "fit_wake_with_pso", _capture_fit,
    )

    s_m = np.linspace(0, 0.1, 10)
    wake = np.zeros_like(s_m)
    f_hz = np.array([0.8e9, 1.0e9, 1.2e9])
    impedance = np.array([1.0, 10.0, 2.0])

    reader = _DictReader({
        WAKE_PATH: (s_m, wake, "Distance / m"),
        Z_PATH: (f_hz, impedance, "Frequency / Hz"),
    })

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
                "amplitude_min": 1.0,
                "amplitude_max": 10.0,
                "q_min": 1.0,
                "q_max": 100.0,
            },
            "known_modes": [
                {
                    "label": "fundamental",
                    "frequency_hz": 499.8e6,
                    "q": 36500,
                    "r_over_q_ohm": 208.6,
                }
            ],
        },
    )

    raw = obj.raw_value()
    assert obj.last_fit_result is not None
    assert len(obj.last_fit_result.known_modes) == 1
    assert obj.last_fit_result.known_modes[0].label == "fundamental"
    assert obj.last_fit_result.unknown_mode_wake is not None
    assert obj.last_fit_result.residual_wake is not None
    diag = obj.last_fit_result.diagnostics
    assert diag["known_mode_count"] == 1
    assert diag["known_mode_labels"] == ["fundamental"]
