"""Wakefield-impedance optimisation objectives (WF2-local).

Longitudinal and transverse beam-coupling impedance objectives for the
HOM antenna optimisation workflow (Phase 2).

Each objective reads 1D impedance curves from the CST wakefield solver
results via the particle-beam tree paths, applies scalarization with
optional HOM frequency masking, and passes the exceedance value to the
penalty mode.

Example YAML::

    objectives:
      # Longitudinal: HOM only (>550 MHz), <1.5 kohm
      - name: z_longitudinal
        mode: less_than
        mode_params: {threshold: 0.0, sigma: 1.0}
        obj_params:
          strategy: threshold_exceedance_integral
          z_threshold_ohm: 1500.0
          freq_min_hz: 550.0e6
          reference_beam: ParticleBeam1
          project: wakefield

      # Transverse: beam subtraction + magnitude, <50 kohm/m
      - name: z_transverse
        mode: less_than
        mode_params: {threshold: 0.0, sigma: 1.0}
        obj_params:
          strategy: threshold_exceedance_integral
          z_threshold_ohm_per_m: 50000.0
          aggregation: worst_case
          reference_beam: ParticleBeam1
          offset_beams:
            - {name: ParticleBeam2, offset_x_mm: 2.0, offset_y_mm: 0.0}
          project: wakefield
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np

from cst_optimization.objectives.base import ObjectiveFunction
from cst_optimization.objectives.registry import register_objective
from cst_optimization.physics.wakefield import (
    ParticleBeam,
    WakeImpedanceData,
    read_wakefield_curve,
    read_beam_impedance,
    compute_transverse_impedance,
    scalarize,
    aggregate_over_beams,
    StrategyName,
    AggregationMode,
)
from workflows.rfgun_hom_antenna.pso_wake_fit import (
    C_LIGHT_M_PER_S,
    PeakDetectionSettings,
    WakeFitError,
    WakeFitResult,
    WakeDerivedImpedanceResult,
    WakeDerivedImpedanceSettings,
    build_wake_fit_input_from_config,
    derive_impedance_from_wake,
    estimate_sigma_z_from_charge_distribution,
    fit_wake_with_pso,
)

_logger = logging.getLogger(__name__)

_DIRECT_FIT_SOURCES = {"", "cst_impedance", "direct", "legacy"}
_PSO_FIT_SOURCE = "pso_wake"

_LENGTH_UNIT_TO_M = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "mm": 1.0e-3,
    "millimeter": 1.0e-3,
    "millimeters": 1.0e-3,
    "cm": 1.0e-2,
    "centimeter": 1.0e-2,
    "centimeters": 1.0e-2,
    "ns": C_LIGHT_M_PER_S * 1.0e-9,
    "nanosecond": C_LIGHT_M_PER_S * 1.0e-9,
    "nanoseconds": C_LIGHT_M_PER_S * 1.0e-9,
}


def _normalize_fit_source(fit_source: str | None) -> str:
    source = str(fit_source or "cst_impedance").strip().lower()
    if source in _DIRECT_FIT_SOURCES:
        return "cst_impedance"
    if source == _PSO_FIT_SOURCE:
        return source
    raise ValueError(
        f"Unknown wakefield fit_source '{fit_source}'. "
        "Use 'cst_impedance' or 'pso_wake'."
    )


def _require_pso_config_value(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise ValueError(
            f"fit_source='pso_wake' requires obj_params.pso_fit.{key}. "
            "CST wake-potential result paths and units must be explicit."
        )
    return value


def _length_unit_scale_to_m(unit_name: str) -> float:
    key = str(unit_name).strip().lower()
    try:
        return _LENGTH_UNIT_TO_M[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported wake_x_unit '{unit_name}'. "
            "Use one of: m, mm, cm, ns."
        ) from exc


def _read_configured_wake_curve(
    reader: Any,
    config: dict[str, Any],
    *,
    tree_path: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Read a real wake-potential curve with explicit configured units."""

    resolved_tree_path = tree_path or str(_require_pso_config_value(
        config, "wake_tree_path"
    ))
    x_unit = str(_require_pso_config_value(config, "wake_x_unit"))
    _require_pso_config_value(config, "wake_y_unit")
    y_scale = float(config.get("wake_y_scale", 1.0))

    xdata, ydata = reader.get_1d_result(resolved_tree_path)
    x_arr = np.asarray(xdata, dtype=float) * _length_unit_scale_to_m(x_unit)
    y_arr_raw = np.asarray(ydata)
    if np.issubdtype(y_arr_raw.dtype, np.complexfloating):
        if not np.allclose(np.imag(y_arr_raw), 0.0, rtol=1e-9, atol=1e-12):
            raise ValueError(
                f"Wake curve '{resolved_tree_path}' is complex-valued; "
                "PSO wake fitting expects a real wake potential curve."
            )
        y_arr = np.real(y_arr_raw).astype(float)
    else:
        y_arr = np.asarray(y_arr_raw, dtype=float)
    return x_arr, y_arr * y_scale


def _read_sigma_z_m(reader: Any, config: dict[str, Any]) -> tuple[float, str]:
    """Resolve bunch RMS length in meters from override or CST charge curve."""

    override = config.get("sigma_z_m")
    if override not in (None, ""):
        sigma = float(override)
        if sigma <= 0.0 or not np.isfinite(sigma):
            raise ValueError("pso_fit.sigma_z_m must be positive and finite.")
        return sigma, "config_override"

    tree_path = str(_require_pso_config_value(config, "charge_distribution_tree_path"))
    x_unit = str(_require_pso_config_value(config, "charge_x_unit"))
    xdata, ydata = reader.get_1d_result(tree_path)
    distance_m = np.asarray(xdata, dtype=float) * _length_unit_scale_to_m(x_unit)
    charge_density = np.asarray(ydata, dtype=float)
    sigma = estimate_sigma_z_from_charge_distribution(distance_m, charge_density)
    return sigma, tree_path


def _pso_config_with_sigma_z(reader: Any, config: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(config or {})
    sigma_z_m, source = _read_sigma_z_m(reader, cfg)
    cfg["sigma_z_m"] = sigma_z_m
    cfg["_sigma_z_source"] = source
    cfg.setdefault("max_normalized_error", 0.2)
    cfg.setdefault("min_wake_corr", 0.8)
    return cfg


def _peak_settings_from_pso_config(config: dict[str, Any]) -> PeakDetectionSettings:
    peak_cfg = config.get("peak_settings", config.get("peaks", {}))
    if not isinstance(peak_cfg, dict):
        peak_cfg = {}
    peak_cfg = dict(peak_cfg)
    fit_peak_min = config.get("fit_peak_freq_min_hz")
    fit_peak_max = config.get("fit_peak_freq_max_hz")
    if fit_peak_min is not None and not any(
        key in peak_cfg for key in ("freq_min_hz", "freqMin_Hz")
    ):
        peak_cfg["freq_min_hz"] = fit_peak_min
    if fit_peak_max is not None and not any(
        key in peak_cfg for key in ("freq_max_hz", "freqMax_Hz")
    ):
        peak_cfg["freq_max_hz"] = fit_peak_max
    return PeakDetectionSettings.from_config(peak_cfg)


def _build_wake_derived_peak_source(
    *,
    direction: str,
    wake_s_m: np.ndarray,
    wake: np.ndarray,
    config: dict[str, Any],
) -> WakeDerivedImpedanceResult:
    return derive_impedance_from_wake(
        direction=direction,  # type: ignore[arg-type]
        wake_s_m=wake_s_m,
        wake=wake,
        sigma_z_m=float(config["sigma_z_m"]),
        peak_settings=_peak_settings_from_pso_config(config),
        settings=WakeDerivedImpedanceSettings.from_config(config),
    )


def _peak_source_mode(config: dict[str, Any]) -> str:
    return str(config.get("peak_source", "wake_derived_refined")).strip().lower()


def _read_explicit_impedance_curve(
    reader: Any,
    tree_path: str,
    *,
    direction: str,
    impedance_type: str,
    beam_name: str,
    beam_offset: float,
) -> WakeImpedanceData:
    return read_wakefield_curve(
        reader,
        tree_path=tree_path,
        beam_name=beam_name,
        direction=direction,
        impedance_type=impedance_type,
        beam_offset=beam_offset,
        label=f"PSO_peak_source_{beam_name}_{direction}",
    )


def _component_paths_for_offset(
    config: dict[str, Any],
    beam_name: str,
    *,
    single_offset: bool,
) -> dict[str, str]:
    paths = config.get("wake_tree_paths", {})
    if isinstance(paths, dict):
        beam_entry = paths.get(beam_name)
        if isinstance(beam_entry, dict):
            return {
                str(k).lower(): str(v)
                for k, v in beam_entry.items()
                if v
            }
        if single_offset and all(k in paths for k in ("x", "y")):
            return {
                "x": str(paths["x"]),
                "y": str(paths["y"]),
            }
    return {}


def _reference_component_paths(config: dict[str, Any]) -> dict[str, str]:
    paths = config.get("reference_wake_tree_paths", {})
    if isinstance(paths, dict):
        return {
            str(k).lower(): str(v)
            for k, v in paths.items()
            if v
        }
    return {}


def _read_transverse_signed_component_wakes(
    offset_reader: Any,
    ref_reader: Any,
    config: dict[str, Any],
    off_beam: ParticleBeam,
    *,
    single_offset: bool,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Read signed X/Y transverse wake components normalized by offset.

    CST smoke templates label wake potentials as V/pC.  For PSO fitting the
    transverse resonator formula expects signed wake components, so each
    component is fitted as ``(offset - reference) / offset_m`` in V/pC/m.
    Magnitude combination is deferred until after reconstructing Zx/Zy(f).
    """

    offset_paths = _component_paths_for_offset(
        config,
        off_beam.name,
        single_offset=single_offset,
    )
    ref_paths = _reference_component_paths(config)
    if not all(component in offset_paths for component in ("x", "y")):
        raise ValueError(
            "fit_source='pso_wake' for transverse signed wake fitting "
            "requires pso_fit.wake_tree_paths with X/Y paths for the offset beam."
        )
    if not all(component in ref_paths for component in ("x", "y")):
        raise ValueError(
            "fit_source='pso_wake' for transverse signed wake fitting "
            "requires pso_fit.reference_wake_tree_paths with X/Y paths."
        )

    offset_m = off_beam.offset_distance_mm * 1.0e-3
    if offset_m <= 0.0:
        raise ValueError(
            f"Offset beam '{off_beam.name}' has zero offset distance; "
            "cannot normalize transverse wake to V/pC/m."
        )

    components: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for component in ("x", "y"):
        off_s, off_wake = _read_configured_wake_curve(
            offset_reader, config, tree_path=offset_paths[component],
        )
        ref_s, ref_wake = _read_configured_wake_curve(
            ref_reader, config, tree_path=ref_paths[component],
        )
        ref_interp = np.interp(off_s, ref_s, ref_wake)
        components[component] = (off_s, (off_wake - ref_interp) / offset_m)
    if not np.allclose(
        components["x"][0],
        components["y"][0],
        rtol=1.0e-8,
        atol=1.0e-12,
    ):
        raise ValueError("Offset X/Y transverse wake grids do not match.")
    return components


# ---------------------------------------------------------------------------
# Longitudinal Impedance
# ---------------------------------------------------------------------------


@register_objective
class LongitudinalImpedanceObjective(ObjectiveFunction):
    """Longitudinal beam-coupling impedance Z_parallel(f).

    Reads the Z-direction wake impedance from the on-axis reference beam,
    applies an optional HOM frequency mask (to exclude the fundamental-mode
    peak), scalarizes against a user-specified threshold, and passes the
    exceedance value to the penalty mode.

    Derivation
    ----------
    From ParticleBeam1 (on-axis), read ``Wake impedance\\Z``.
    Exclude the fundamental-mode band (<= *freq_min_hz*), keep HOM region.
    Scalarize with chosen strategy -> exceedance metric.

    Raw value unit: depends on *strategy*:
        - ``threshold_exceedance_integral`` -> ohm*Hz
        - ``peak_exceedance``             -> ohm
        - ``composite``                   -> dimensionless

    Typical mode: ``less_than`` with ``threshold=0``.

    Parameters
    ----------
    reader_factory : callable
    mode : OptimizationMode
    reference_beam : str
        Name of the on-axis reference beam (e.g. ``"ParticleBeam1"``).
    z_threshold_ohm : float
        Maximum allowed longitudinal impedance (1.5 kohm = 1500 ohm).
    strategy : str
        Scalarization strategy name.
    weights : tuple[float, float, float] or None
        Weights for ``composite`` strategy.
    freq_min_hz : float or None
        HOM lower bound in Hz (e.g. ``550e6`` for 550 MHz).
        Frequencies below this are excluded from scalarization.
    freq_max_hz : float or None
        HOM upper bound in Hz.
    """

    name: ClassVar[str] = "z_longitudinal"
    unit: ClassVar[str] = "ohm*Hz | ohm | dimensionless"

    def __init__(
        self,
        reader_factory,
        mode=None,
        reference_beam: str = "ParticleBeam1",
        z_threshold_ohm: float = 1500.0,
        strategy: str = "threshold_exceedance_integral",
        weights: tuple[float, float, float] | None = None,
        freq_min_hz: float | None = None,
        freq_max_hz: float | None = None,
        normalize: bool = False,
        square_exceedance: bool = False,
        fit_source: str = "cst_impedance",
        pso_fit: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(reader_factory, mode)
        self._ref_beam_name = str(reference_beam)
        self._z_threshold = float(z_threshold_ohm)
        self._strategy = strategy
        self._weights = weights or (0.4, 0.4, 0.2)
        self._freq_min_hz = float(freq_min_hz) if freq_min_hz is not None else None
        self._freq_max_hz = float(freq_max_hz) if freq_max_hz is not None else None
        self._normalize = bool(normalize)
        self._square_exceedance = bool(square_exceedance)
        self._fit_source = _normalize_fit_source(fit_source)
        self._pso_fit = dict(pso_fit or {})
        self.last_fit_result: WakeFitResult | None = None

    def raw_value(self) -> float:
        reader = self._reader_factory()
        if self._fit_source == _PSO_FIT_SOURCE:
            return self._raw_value_from_pso_wake(reader)
        return self._raw_value_from_cst_impedance(reader)

    def _raw_value_from_cst_impedance(self, reader: Any) -> float:
        """Legacy WF2 path: scalarize CST's sampled wake impedance curve."""

        beam = ParticleBeam(
            name=self._ref_beam_name,
            offset_x_mm=0.0,
            offset_y_mm=0.0,
            is_reference=True,
        )

        imp_set = read_beam_impedance(reader, beam)
        if imp_set.z_long is None:
            raise ValueError(
                f"No longitudinal (Z) impedance data for beam '{self._ref_beam_name}'"
            )

        return float(
            scalarize(
                imp_set.z_long.frequencies,
                imp_set.z_long.impedance,
                z_threshold=self._z_threshold,
                strategy=self._strategy,  # type: ignore[arg-type]
                weights=self._weights,
                freq_min_hz=self._freq_min_hz,
                freq_max_hz=self._freq_max_hz,
                normalize=self._normalize,
                square_exceedance=self._square_exceedance,
            )
        )

    def _raw_value_from_pso_wake(self, reader: Any) -> float:
        """Fit a wake-potential curve and scalarize reconstructed impedance."""

        try:
            pso_cfg = _pso_config_with_sigma_z(reader, self._pso_fit)
            wake_s_m, wake = _read_configured_wake_curve(reader, pso_cfg)
            reference_impedance = read_wakefield_curve(
                reader,
                beam_name=self._ref_beam_name,
                direction="z",
                impedance_type="longitudinal",
                beam_offset=0.0,
                label=f"PSO_reference_{self._ref_beam_name}_z",
            )
            precomputed_peaks = None
            peak_source_frequency_hz = None
            peak_source_impedance = None
            reconstruction_frequency_hz = reference_impedance.frequencies
            reconstruction_impedance = reference_impedance.impedance
            peak_source_label = "sampled_impedance"

            if _peak_source_mode(pso_cfg) in (
                "wake_derived",
                "wake_derived_refined",
                "derived",
            ):
                derived = _build_wake_derived_peak_source(
                    direction="longitudinal",
                    wake_s_m=wake_s_m,
                    wake=wake,
                    config=pso_cfg,
                )
                peak_source_frequency_hz = derived.refined_frequency_hz
                peak_source_impedance = np.abs(derived.refined_impedance_complex)
                reconstruction_frequency_hz = derived.refined_frequency_hz
                reconstruction_impedance = np.abs(derived.refined_impedance_complex)
                precomputed_peaks = derived.peaks
                peak_source_label = "wake_derived_refined"
            else:
                peak_path = str(pso_cfg.get("peak_tree_path", "") or "")
                if peak_path:
                    peak_source = _read_explicit_impedance_curve(
                        reader,
                        peak_path,
                        direction="z",
                        impedance_type="longitudinal",
                        beam_name=self._ref_beam_name,
                        beam_offset=0.0,
                    )
                else:
                    peak_source = reference_impedance
                peak_source_frequency_hz = peak_source.frequencies
                peak_source_impedance = peak_source.impedance

            fit_input = build_wake_fit_input_from_config(
                direction="longitudinal",
                wake_s_m=wake_s_m,
                wake=wake,
                impedance_frequency_hz=reconstruction_frequency_hz,
                impedance=reconstruction_impedance,
                config=pso_cfg,
                default_freq_min_hz=self._freq_min_hz,
                default_freq_max_hz=self._freq_max_hz,
                peak_source_frequency_hz=peak_source_frequency_hz,
                peak_source_impedance=peak_source_impedance,
                precomputed_peaks=precomputed_peaks,
                peak_source_label=peak_source_label,
            )
            result = fit_wake_with_pso(fit_input)
            self.last_fit_result = result
            if result.status != "ok":
                raise WakeFitError(result.failure_reason or "PSO wake fit failed.")

            return float(
                scalarize(
                    result.impedance_frequency_hz,
                    result.impedance_abs,
                    z_threshold=self._z_threshold,
                    strategy=self._strategy,  # type: ignore[arg-type]
                    weights=self._weights,
                    freq_min_hz=self._freq_min_hz,
                    freq_max_hz=self._freq_max_hz,
                    normalize=self._normalize,
                    square_exceedance=self._square_exceedance,
                )
            )
        except Exception as exc:
            return self._handle_pso_failure(exc, reader)

    def _handle_pso_failure(self, exc: Exception, reader: Any) -> float:
        action = str(
            self._pso_fit.get("on_fit_failure", "fail_evaluation")
        ).strip().lower()
        if action == "fallback_to_cst_impedance":
            _logger.warning(
                "z_longitudinal PSO wake fit failed; falling back to CST "
                "impedance path: %s",
                exc,
            )
            return self._raw_value_from_cst_impedance(reader)
        raise ValueError(f"z_longitudinal PSO wake fit failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Transverse Impedance
# ---------------------------------------------------------------------------


@register_objective
class TransverseImpedanceObjective(ObjectiveFunction):
    """Transverse beam-coupling impedance Z_perp(f).

    Computes the transverse impedance from one or more offset beam-lines
    via finite-difference subtraction against the on-axis reference beam,
    then scalarizes and aggregates across beams.

    Derivation
    ----------
    For each offset beam *i* with offset distance *d_i*::

        dX_i(f) = Z_x(offset_i, f) - Z_x(ref, f)
        dY_i(f) = Z_y(offset_i, f) - Z_y(ref, f)
        Z_trans,i(f) = sqrt(dX_i^2 + dY_i^2) / d_i   [ohm/m]

    Each Z_trans,i is scalarized.  Results are aggregated across
    offset beams (worst-case by default).

    Raw value unit: depends on *strategy*:
        - ``threshold_exceedance_integral`` -> ohm/m*Hz
        - ``peak_exceedance``             -> ohm/m
        - ``composite``                   -> dimensionless

    Typical mode: ``less_than`` with ``threshold=0``.

    Parameters
    ----------
    reader_factory : callable
    mode : OptimizationMode
    reference_beam : str
        Name of the on-axis reference beam (e.g. ``"ParticleBeam1"``).
    offset_beams : list[dict]
        Each dict with keys ``name``, ``offset_x_mm``, ``offset_y_mm``.
    z_threshold_ohm_per_m : float
        Maximum allowed transverse impedance (50 kohm/m).
    strategy : str
    aggregation : str
        ``"worst_case"`` (default), ``"rms"``, or ``"mean"``.
    freq_min_hz / freq_max_hz : float or None
        Optional frequency mask.
    """

    name: ClassVar[str] = "z_transverse"
    unit: ClassVar[str] = "ohm/m*Hz | ohm/m | dimensionless"

    def __init__(
        self,
        reader_factory,
        mode=None,
        ref_reader_factory=None,
        reference_beam: str = "ParticleBeam1",
        offset_beams: list[dict[str, Any]] | None = None,
        z_threshold_ohm_per_m: float = 50000.0,
        strategy: str = "threshold_exceedance_integral",
        weights: tuple[float, float, float] | None = None,
        aggregation: str = "worst_case",
        freq_min_hz: float | None = None,
        freq_max_hz: float | None = None,
        normalize: bool = False,
        square_exceedance: bool = False,
        fit_source: str = "cst_impedance",
        pso_fit: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(reader_factory, mode)
        self._ref_beam_name = str(reference_beam)
        self._z_threshold = float(z_threshold_ohm_per_m)
        self._strategy = strategy
        self._weights = weights or (0.4, 0.4, 0.2)
        self._aggregation = aggregation
        self._freq_min_hz = float(freq_min_hz) if freq_min_hz is not None else None
        self._freq_max_hz = float(freq_max_hz) if freq_max_hz is not None else None
        self._normalize = bool(normalize)
        self._square_exceedance = bool(square_exceedance)
        self._ref_reader_factory = ref_reader_factory
        self._fit_source = _normalize_fit_source(fit_source)
        self._pso_fit = dict(pso_fit or {})
        self.last_fit_results: dict[str, WakeFitResult] = {}

        # Parse offset beam configs
        self._offset_beams: list[ParticleBeam] = []
        if offset_beams:
            for entry in offset_beams:
                self._offset_beams.append(ParticleBeam(
                    name=str(entry["name"]),
                    offset_x_mm=float(entry.get("offset_x_mm", 0.0)),
                    offset_y_mm=float(entry.get("offset_y_mm", 0.0)),
                    is_reference=False,
                ))

    def raw_value(self) -> float:
        if not self._offset_beams:
            _logger.warning(
                "TransverseImpedanceObjective: no offset beams configured.  "
                "Returning 0.0 (no transverse data to penalise)."
            )
            return 0.0

        offset_reader = self._reader_factory()

        # Read reference beam (from separate file if configured)
        ref_reader = (
            self._ref_reader_factory() if self._ref_reader_factory
            else offset_reader
        )
        if self._fit_source == _PSO_FIT_SOURCE:
            return self._raw_value_from_pso_wake(offset_reader, ref_reader)
        return self._raw_value_from_cst_impedance(offset_reader, ref_reader)

    def _raw_value_from_cst_impedance(self, offset_reader: Any, ref_reader: Any) -> float:
        """Legacy WF2 path: finite-difference sampled CST impedance curves."""

        ref_beam = ParticleBeam(
            name=self._ref_beam_name,
            offset_x_mm=0.0,
            offset_y_mm=0.0,
            is_reference=True,
        )
        ref_set = read_beam_impedance(ref_reader, ref_beam)

        # Read each offset beam, compute Z_trans, scalarize
        scalar_values: list[float] = []
        for off_beam in self._offset_beams:
            off_set = read_beam_impedance(offset_reader, off_beam)
            try:
                z_trans = compute_transverse_impedance(ref_set, off_set)
            except ValueError as exc:
                _logger.error(
                    "Failed to compute transverse impedance for '%s': %s",
                    off_beam.name, exc,
                )
                continue

            val = scalarize(
                z_trans.frequencies,
                z_trans.impedance,
                z_threshold=self._z_threshold,
                strategy=self._strategy,  # type: ignore[arg-type]
                weights=self._weights,
                freq_min_hz=self._freq_min_hz,
                freq_max_hz=self._freq_max_hz,
                normalize=self._normalize,
                square_exceedance=self._square_exceedance,
            )
            scalar_values.append(val)

        if not scalar_values:
            _logger.warning(
                "TransverseImpedanceObjective: all offset beams failed.  "
                "Returning 0.0."
            )
            return 0.0

        return aggregate_over_beams(
            scalar_values,
            mode=self._aggregation,  # type: ignore[arg-type]
        )

    def _raw_value_from_pso_wake(self, offset_reader: Any, ref_reader: Any) -> float:
        scalar_values: list[float] = []
        self.last_fit_results = {}
        try:
            pso_cfg = _pso_config_with_sigma_z(ref_reader, self._pso_fit)
            ref_set = None
            single_offset = len(self._offset_beams) == 1
            for off_beam in self._offset_beams:
                signed_wakes = _read_transverse_signed_component_wakes(
                    offset_reader,
                    ref_reader,
                    pso_cfg,
                    off_beam,
                    single_offset=single_offset,
                )
                if ref_set is None:
                    ref_set = self._read_reference_set(ref_reader)
                off_set = read_beam_impedance(offset_reader, off_beam)
                legacy_reference = compute_transverse_impedance(ref_set, off_set)

                derived_by_component: dict[str, WakeDerivedImpedanceResult] = {}
                if _peak_source_mode(pso_cfg) in (
                    "wake_derived",
                    "wake_derived_refined",
                    "derived",
                ):
                    for component, (wake_s_m, wake) in signed_wakes.items():
                        derived_by_component[component] = _build_wake_derived_peak_source(
                            direction="transverse",
                            wake_s_m=wake_s_m,
                            wake=wake,
                            config=pso_cfg,
                        )
                    reconstruction_frequency_hz = np.unique(
                        np.concatenate(
                            [
                                derived.refined_frequency_hz
                                for derived in derived_by_component.values()
                            ]
                        )
                    )
                    reconstruction_frequency_hz.sort()
                else:
                    reconstruction_frequency_hz = legacy_reference.frequencies

                component_results: dict[str, WakeFitResult] = {}
                for component, (wake_s_m, wake) in signed_wakes.items():
                    precomputed_peaks = None
                    peak_source_frequency_hz = None
                    peak_source_impedance = None
                    reconstruction_impedance = np.zeros_like(
                        reconstruction_frequency_hz,
                        dtype=float,
                    )
                    peak_source_label = "sampled_impedance"

                    if component in derived_by_component:
                        derived = derived_by_component[component]
                        peak_source_frequency_hz = derived.refined_frequency_hz
                        peak_source_impedance = np.abs(derived.refined_impedance_complex)
                        reconstruction_impedance = np.interp(
                            reconstruction_frequency_hz,
                            derived.refined_frequency_hz,
                            np.abs(derived.refined_impedance_complex),
                        )
                        precomputed_peaks = derived.peaks
                        peak_source_label = f"wake_derived_refined_{component}"
                    else:
                        peak_source_frequency_hz = legacy_reference.frequencies
                        peak_source_impedance = self._component_impedance_source(
                            ref_set,
                            off_set,
                            component,
                        )
                        reconstruction_impedance = peak_source_impedance

                    fit_input = build_wake_fit_input_from_config(
                        direction="transverse",
                        wake_s_m=wake_s_m,
                        wake=wake,
                        impedance_frequency_hz=reconstruction_frequency_hz,
                        impedance=reconstruction_impedance,
                        config=pso_cfg,
                        default_freq_min_hz=self._freq_min_hz,
                        default_freq_max_hz=self._freq_max_hz,
                        peak_source_frequency_hz=peak_source_frequency_hz,
                        peak_source_impedance=peak_source_impedance,
                        precomputed_peaks=precomputed_peaks,
                        peak_source_label=peak_source_label,
                    )
                    result = fit_wake_with_pso(fit_input)
                    self.last_fit_results[f"{off_beam.name}.{component}"] = result
                    component_results[component] = result
                    if result.status != "ok":
                        raise WakeFitError(
                            result.failure_reason
                            or f"PSO transverse {component.upper()} wake fit failed."
                        )

                if not all(component in component_results for component in ("x", "y")):
                    raise WakeFitError("PSO transverse fitting needs X and Y component fits.")
                z_trans = np.sqrt(
                    component_results["x"].impedance_abs**2
                    + component_results["y"].impedance_abs**2
                )
                scalar_values.append(
                    scalarize(
                        reconstruction_frequency_hz,
                        z_trans,
                        z_threshold=self._z_threshold,
                        strategy=self._strategy,  # type: ignore[arg-type]
                        weights=self._weights,
                        freq_min_hz=self._freq_min_hz,
                        freq_max_hz=self._freq_max_hz,
                        normalize=self._normalize,
                        square_exceedance=self._square_exceedance,
                    )
                )
        except Exception as exc:
            return self._handle_pso_failure(exc, offset_reader, ref_reader)

        if not scalar_values:
            raise ValueError("z_transverse PSO wake fit produced no scalar values.")
        return aggregate_over_beams(
            scalar_values,
            mode=self._aggregation,  # type: ignore[arg-type]
        )

    def _read_reference_set(self, ref_reader: Any):
        ref_beam = ParticleBeam(
            name=self._ref_beam_name,
            offset_x_mm=0.0,
            offset_y_mm=0.0,
            is_reference=True,
        )
        return read_beam_impedance(ref_reader, ref_beam)

    def _component_impedance_source(
        self,
        ref_set: Any,
        off_set: Any,
        component: str,
    ) -> np.ndarray:
        """Sampled component impedance magnitude used only for legacy peak source."""

        attr = "z_x" if component == "x" else "z_y"
        ref_curve = getattr(ref_set, attr)
        off_curve = getattr(off_set, attr)
        if ref_curve is None or off_curve is None:
            raise ValueError(f"Missing {component.upper()} impedance component.")
        if not np.allclose(ref_curve.frequencies, off_curve.frequencies, rtol=1e-6):
            raise ValueError(
                f"Reference and offset {component.upper()} impedance grids differ."
            )
        offset_m = off_set.beam.offset_distance_mm * 1.0e-3
        if offset_m <= 0.0:
            raise ValueError("Offset distance must be positive for transverse impedance.")
        return np.abs(off_curve.impedance - ref_curve.impedance) / offset_m

    def _handle_pso_failure(
        self,
        exc: Exception,
        offset_reader: Any,
        ref_reader: Any,
    ) -> float:
        action = str(
            self._pso_fit.get("on_fit_failure", "fail_evaluation")
        ).strip().lower()
        if action == "fallback_to_cst_impedance":
            _logger.warning(
                "z_transverse PSO wake fit failed; falling back to CST "
                "impedance path: %s",
                exc,
            )
            return self._raw_value_from_cst_impedance(offset_reader, ref_reader)
        raise ValueError(f"z_transverse PSO wake fit failed: {exc}") from exc
