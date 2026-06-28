"""Workflow-2 local PSO wake fitting utilities.

This module ports the non-GUI core of ``PSO-Fitting-GUI-Retest`` into a
Python interface that can be used by Workflow 2 objectives.  It deliberately
does not call CST APIs and does not guess CST result-tree paths; callers must
provide already-read 1D arrays with explicit units.

Units used internally:

* frequency: Hz
* wake abscissa: m, converted to time by ``t = s / c``
* longitudinal impedance: Ohm
* transverse impedance: Ohm/m
* Q: dimensionless
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Sequence, Union

import numpy as np

C_LIGHT_M_PER_S = 299_792_458.0
Direction = Literal["longitudinal", "transverse"]


class WakeFitError(ValueError):
    """Raised when PSO wake fitting cannot produce a scientific result."""


@dataclass(frozen=True)
class PeakInfo:
    """One visible impedance-grid peak used as a fixed resonator frequency.

    ``frequency_hz`` is the frequency actually used by PSO.  When the peak
    came from the wake-derived refined grid, ``coarse_frequency_hz`` records
    the first-pass visible peak and ``refined_frequency_hz`` records the
    local-grid maximum.  Refinement can improve a visible sampled peak, but it
    still cannot recover a completely missed/invisible narrow peak.
    """

    index: int
    frequency_hz: float
    value: float
    use: bool = True
    status: str = "Use"
    coarse_frequency_hz: float | None = None
    refined_frequency_hz: float | None = None
    coarse_index: int | None = None
    source: str = "sampled_impedance"


@dataclass(frozen=True)
class PeakDetectionSettings:
    """Controls visible-peak detection and selection.

    ``min_peak_distance_points`` is a sample-count distance, matching the
    MATLAB implementation's ``MinPeakDistance`` usage.  It is not a Hz span.

    ``freq_min_hz``/``freq_max_hz`` define the fitting peak search range.
    They are intentionally independent from Workflow-2 scalarization masks.
    """

    min_peak_height: float | None = None
    min_peak_distance_points: int = 1
    freq_min_hz: float | None = None
    freq_max_hz: float | None = None
    delete_first_n: int = 0
    max_peaks: int | None = None
    min_peak_count: int = 1
    selection_strategy: Literal["all_visible", "top_amplitude"] = "all_visible"
    max_selected_modes: int | None = None

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any] | None,
        *,
        default_freq_min_hz: float | None = None,
        default_freq_max_hz: float | None = None,
    ) -> "PeakDetectionSettings":
        cfg = config or {}
        return cls(
            min_peak_height=_optional_float(
                _get_any(cfg, "min_peak_height", "minPeakHeight")
            ),
            min_peak_distance_points=max(
                1,
                int(
                    round(
                        _optional_float(
                            _get_any(
                                cfg,
                                "min_peak_distance_points",
                                "min_peak_distance",
                                "minPeakDistance",
                                default=1,
                            )
                        )
                        or 1
                    )
                ),
            ),
            freq_min_hz=_optional_float(
                _get_any(
                    cfg,
                    "freq_min_hz",
                    "freqMin_Hz",
                    default=default_freq_min_hz,
                )
            ),
            freq_max_hz=_optional_float(
                _get_any(
                    cfg,
                    "freq_max_hz",
                    "freqMax_Hz",
                    default=default_freq_max_hz,
                )
            ),
            delete_first_n=max(
                0, int(_get_any(cfg, "delete_first_n", "deleteFirstN", default=0))
            ),
            max_peaks=_optional_int(_get_any(cfg, "max_peaks", "maxPeaks")),
            min_peak_count=max(
                1, int(_get_any(cfg, "min_peak_count", "minPeakCount", default=1))
            ),
            selection_strategy=str(
                _get_any(
                    cfg,
                    "selection_strategy",
                    "peak_selection",
                    "strategy",
                    default="all_visible",
                )
            ).strip().lower(),  # type: ignore[arg-type]
            max_selected_modes=_optional_int(
                _get_any(
                    cfg,
                    "max_selected_modes",
                    "maxSelectedModes",
                    "selected_count",
                    default=None,
                )
            ),
        )


@dataclass(frozen=True)
class FitWindowSettings:
    """Unit-explicit tail fitting window.

    Supported units:
    - ``m`` or ``mm`` are distance along CST's wake ``s`` axis.
    - ``ns`` is converted with ``s = c * t``.
    - ``auto`` for the end uses the last available wake sample.
    """

    start_value: float | None = None
    start_unit: Literal["m", "mm", "ns"] = "m"
    end_value: float | None = None
    end_unit: Literal["m", "mm", "ns", "auto"] = "auto"

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any] | None,
        *,
        legacy_start_m: float | None = None,
        legacy_end_m: float | None = None,
    ) -> "FitWindowSettings":
        cfg = config or {}
        if "fit_window" in cfg and isinstance(cfg["fit_window"], dict):
            window = cfg["fit_window"]
            end_raw = _get_any(window, "end", "end_value", default="auto")
            end_unit_raw = _get_any(window, "end_unit", default=None)
            if isinstance(end_raw, str) and end_raw.strip().lower() == "auto":
                end_value = None
                end_unit = "auto"
            else:
                end_value = _optional_float(end_raw)
                end_unit = str(end_unit_raw or window.get("start_unit", "m")).lower()
            return cls(
                start_value=_optional_float(
                    _get_any(window, "start_value", "start", default=None)
                ),
                start_unit=str(
                    _get_any(window, "start_unit", "unit", default="m")
                ).strip().lower(),  # type: ignore[arg-type]
                end_value=end_value,
                end_unit=end_unit,  # type: ignore[arg-type]
            )
        return cls(
            start_value=legacy_start_m,
            start_unit="m",
            end_value=legacy_end_m,
            end_unit="m" if legacy_end_m is not None else "auto",
        )

    def resolve_m(self, wake_s_m: np.ndarray) -> tuple[float, float]:
        wake_s = _as_1d_float(wake_s_m, "wake_s_m")
        start = (
            float(np.nanmin(wake_s))
            if self.start_value is None
            else _window_value_to_m(self.start_value, self.start_unit)
        )
        end = (
            float(np.nanmax(wake_s))
            if self.end_unit == "auto" or self.end_value is None
            else _window_value_to_m(self.end_value, self.end_unit)
        )
        return start, end


@dataclass(frozen=True)
class WakeDerivedImpedanceSettings:
    """Settings for author-style wake-to-impedance peak-source generation.

    The wake input is expected in V/pC for longitudinal and V/pC/m for
    transverse; it is converted to SI by multiplying by ``1e12`` before the
    frequency-domain integration.
    """

    enabled: bool = True
    freq_min_hz: float = 1.0e3
    freq_max_hz: float | None = None
    wake_point_count: int = 10000
    freq_point_count: int = 10000
    adaptive_refine_factor: int = 50
    adaptive_half_width_bins: int = 10
    adaptive_max_freq_point_count: int = 20000

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "WakeDerivedImpedanceSettings":
        cfg = config or {}
        source_cfg = cfg.get("derived_impedance", cfg.get("wake_to_impedance", {}))
        if not isinstance(source_cfg, dict):
            source_cfg = {}
        return cls(
            enabled=bool(_get_any(source_cfg, "enabled", default=True)),
            freq_min_hz=float(_get_any(source_cfg, "freq_min_hz", "fMin_Hz", default=1.0e3)),
            freq_max_hz=_optional_float(_get_any(source_cfg, "freq_max_hz", "fMax_Hz", default=None)),
            wake_point_count=max(
                100,
                int(_get_any(source_cfg, "wake_point_count", "convertWakePointCount", default=10000)),
            ),
            freq_point_count=max(
                100,
                int(_get_any(source_cfg, "freq_point_count", "convertFreqPointCount", default=10000)),
            ),
            adaptive_refine_factor=max(
                2,
                int(_get_any(source_cfg, "adaptive_refine_factor", "adaptiveRefineFactor", default=50)),
            ),
            adaptive_half_width_bins=max(
                1,
                int(_get_any(source_cfg, "adaptive_half_width_bins", "adaptiveHalfWidthBins", default=10)),
            ),
            adaptive_max_freq_point_count=max(
                100,
                int(_get_any(source_cfg, "adaptive_max_freq_point_count", "adaptiveMaxFreqPointCount", default=20000)),
            ),
        )


@dataclass(frozen=True)
class WakeDerivedImpedanceResult:
    """Wake-derived impedance curves and refined visible peak table."""

    coarse_frequency_hz: np.ndarray
    coarse_impedance_complex: np.ndarray
    refined_frequency_hz: np.ndarray
    refined_impedance_complex: np.ndarray
    peaks: tuple[PeakInfo, ...]
    settings: WakeDerivedImpedanceSettings
    base_df_hz: float
    local_grid_refinement_active: bool


@dataclass(frozen=True)
class PSOBounds:
    """Bounds for ``[A1, Q1, A2, Q2, ...]``.

    ``A`` has the same wake unit as the fitted wake curve.  ``Q`` is
    dimensionless.  Scalars apply to every selected mode; sequences must have
    length equal to the number of selected peaks.
    """

    amplitude_min: float | Sequence[float]
    amplitude_max: float | Sequence[float]
    q_min: float | Sequence[float]
    q_max: float | Sequence[float]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PSOBounds":
        cfg = config or {}
        missing = [
            name
            for name in ("amplitude_min", "amplitude_max", "q_min", "q_max")
            if _get_bound_value(cfg, name) is None
        ]
        if missing:
            raise WakeFitError(
                "PSO fitting requires explicit bounds for "
                + ", ".join(missing)
                + " under pso_fit.bounds."
            )
        return cls(
            amplitude_min=_get_bound_value(cfg, "amplitude_min"),
            amplitude_max=_get_bound_value(cfg, "amplitude_max"),
            q_min=_get_bound_value(cfg, "q_min"),
            q_max=_get_bound_value(cfg, "q_max"),
        )

    def expand(self, n_modes: int, direction: Direction) -> tuple[np.ndarray, np.ndarray]:
        a_min = _expand_bound(self.amplitude_min, n_modes, "amplitude_min")
        a_max = _expand_bound(self.amplitude_max, n_modes, "amplitude_max")
        q_min = _expand_bound(self.q_min, n_modes, "q_min")
        q_max = _expand_bound(self.q_max, n_modes, "q_max")

        if direction == "longitudinal" and np.any(q_min <= 0.5):
            raise WakeFitError(
                "Longitudinal wake fitting requires q_min > 0.5 because the "
                "resonator formula contains sqrt(4*Q^2 - 1)."
            )
        if np.any(a_max < a_min):
            raise WakeFitError("PSO amplitude bounds must satisfy min <= max.")
        if np.any(q_max < q_min):
            raise WakeFitError("PSO Q bounds must satisfy min <= max.")

        lb = np.empty(2 * n_modes, dtype=float)
        ub = np.empty(2 * n_modes, dtype=float)
        lb[0::2] = a_min
        ub[0::2] = a_max
        lb[1::2] = q_min
        ub[1::2] = q_max
        return lb, ub


@dataclass(frozen=True)
class PSOSettings:
    """Runtime settings for the PSO solver."""

    swarm_size: int = 80
    max_iterations: int = 100
    function_tolerance: float = 1.0e-8
    seed: int = 42

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "PSOSettings":
        cfg = config or {}
        return cls(
            swarm_size=max(
                1,
                int(_get_any(cfg, "swarm_size", "swarmSize", default=80)),
            ),
            max_iterations=max(
                1,
                int(_get_any(cfg, "max_iterations", "maxIterations", default=100)),
            ),
            function_tolerance=float(
                _get_any(
                    cfg,
                    "function_tolerance",
                    "functionTolerance",
                    default=1.0e-8,
                )
            ),
            seed=int(_get_any(cfg, "seed", default=42)),
        )


@dataclass(frozen=True)
class PreparedWakeFitData:
    """Wake samples used in the PSO objective."""

    s_m: np.ndarray
    t_s: np.ndarray
    wake: np.ndarray
    start_m: float
    end_m: float
    point_count: int
    step_m: float


@dataclass(frozen=True)
class WakeFitInput:
    """Complete array-level input needed by the PSO wake fitter."""

    direction: Direction
    wake_s_m: np.ndarray
    wake: np.ndarray
    impedance_frequency_hz: np.ndarray
    impedance: np.ndarray
    sigma_z_m: float
    fit_start_m: float
    fit_end_m: float
    fit_point_count: int
    bounds: PSOBounds
    peak_settings: PeakDetectionSettings = field(default_factory=PeakDetectionSettings)
    pso_settings: PSOSettings = field(default_factory=PSOSettings)
    wake_charge_scale: float = 1.0e12
    max_normalized_error: float | None = None
    min_wake_corr: float | None = None
    peak_source_frequency_hz: np.ndarray | None = None
    peak_source_impedance: np.ndarray | None = None
    precomputed_peaks: tuple[PeakInfo, ...] | None = None
    peak_source_label: str = "sampled_impedance"
    known_modes: tuple[KnownMode, ...] = ()


@dataclass(frozen=True)
class ModeFit:
    """One fitted resonator mode."""

    frequency_hz: float
    amplitude: float
    q: float
    r_over_q: float
    shunt_impedance: float


@dataclass(frozen=True)
class KnownMode:
    """One fixed/known resonator mode not optimised by PSO.

    The wake amplitude is derived from ``r_over_q_ohm`` using the same
    form-factor convention as :func:`fit_wake_with_pso`::

        amplitude = (R/Q) * form_factor(f, sigma_z) * 2*pi*f / wake_charge_scale

    When ``include_in_reconstructed_impedance`` is True (default), the
    known mode is included in the reconstructed impedance of the result.
    """

    label: str
    frequency_hz: float
    q: float
    r_over_q_ohm: float
    include_in_reconstructed_impedance: bool = True
    frequency_tolerance_hz: float = 0.0


@dataclass(frozen=True)
class WakeFitResult:
    """Output of the PSO wake fit and reconstructed impedance."""

    modes: tuple[ModeFit, ...]
    fit_s_m: np.ndarray
    fit_t_s: np.ndarray
    fit_wake: np.ndarray
    wake_fit: np.ndarray
    impedance_frequency_hz: np.ndarray
    impedance_complex: np.ndarray
    impedance_abs: np.ndarray
    normalized_error: float
    wake_corr: float
    objective_value: float
    selected_peaks: tuple[PeakInfo, ...]
    all_peaks: tuple[PeakInfo, ...]
    status: str = "ok"
    failure_reason: str = ""
    optimizer_info: dict[str, Any] = field(default_factory=dict)
    known_modes: tuple[KnownMode, ...] = ()
    known_mode_wake: np.ndarray | None = None
    unknown_mode_wake: np.ndarray | None = None
    residual_wake: np.ndarray | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


OptimizerFn = Callable[
    [Callable[[np.ndarray], float], np.ndarray, np.ndarray, PSOSettings],
    Union[tuple[np.ndarray, float], tuple[np.ndarray, float, dict[str, Any]]],
]


def _known_modes_from_config(
    cfg: dict[str, Any],
    fitting_direction: Direction,
) -> tuple[KnownMode, ...]:
    """Parse ``known_modes`` from a ``pso_fit`` config block.

    Expected per-mode keys (under ``cfg["known_modes"]``):

    ===============================  =========  ================================
    Key                              Required   Notes
    ===============================  =========  ================================
    ``frequency_hz``                 Yes        Positive, in Hz.
    ``q``                            Yes        Positive; >0.5 for longitudinal.
    ``r_over_q_ohm``                 Yes        Finite, in ohm.
    ``label``                        No         Defaults to ``"known_<index>"``.
    ``direction``                    No         Must be longitudinal when provided.
    ``frequency_tolerance_hz``       No         Finite, non-negative; default 0.0.
    ``include_in_reconstructed_      No         Default True.
     impedance``
    ===============================  =========  ================================

    Returns an empty tuple when ``known_modes`` is absent or empty.
    """

    raw_list = cfg.get("known_modes")
    if not raw_list:
        return ()
    if not isinstance(raw_list, (list, tuple)):
        raise WakeFitError(
            "pso_fit.known_modes must be a list of mode definitions."
        )

    direction_norm = _normalize_direction(fitting_direction)
    if direction_norm != "longitudinal":
        raise WakeFitError(
            "pso_fit.known_modes currently supports only longitudinal fitting. "
            f"Got fitting direction {direction_norm!r}; remove known_modes from "
            "transverse PSO config until transverse known-mode physics is "
            "validated."
        )

    parsed: list[KnownMode] = []
    for i, entry in enumerate(raw_list):
        if not isinstance(entry, dict):
            raise WakeFitError(
                f"pso_fit.known_modes[{i}] must be a dict, "
                f"got {type(entry).__name__}."
            )

        prefix = f"pso_fit.known_modes[{i}]"

        # --- required fields ---
        frequency_hz = _get_known_required_float(entry, "frequency_hz", prefix)
        q = _get_known_required_float(entry, "q", prefix)
        r_over_q_ohm = _get_known_required_float(entry, "r_over_q_ohm", prefix)

        if frequency_hz <= 0.0:
            raise WakeFitError(
                f"{prefix}.frequency_hz must be positive; got {frequency_hz}."
            )
        if q <= 0.0:
            raise WakeFitError(
                f"{prefix}.q must be positive; got {q}."
            )
        if q <= 0.5:
            raise WakeFitError(
                f"{prefix}.q must be > 0.5 for longitudinal known modes; "
                f"got {q}."
            )
        if not np.isfinite(r_over_q_ohm):
            raise WakeFitError(
                f"{prefix}.r_over_q_ohm must be finite; got {r_over_q_ohm}."
            )

        # --- optional fields ---
        label = str(entry.get("label", f"known_{i}"))
        entry_direction_raw = entry.get("direction", direction_norm)
        if entry_direction_raw is not None:
            entry_direction = _normalize_direction(str(entry_direction_raw))
            if entry_direction != direction_norm:
                raise WakeFitError(
                    f"{prefix}.direction={entry_direction!r} does not match "
                    f"fitting direction {direction_norm!r}.  Only "
                    f"'{direction_norm}' known modes are supported in this "
                    "fitting path."
                )

        try:
            tolerance = float(entry.get("frequency_tolerance_hz", 0.0))
        except (TypeError, ValueError) as exc:
            raise WakeFitError(
                f"{prefix}.frequency_tolerance_hz must be a finite, "
                f"non-negative float; got {entry.get('frequency_tolerance_hz')!r}."
            ) from exc
        if not np.isfinite(tolerance) or tolerance < 0.0:
            raise WakeFitError(
                f"{prefix}.frequency_tolerance_hz must be finite and non-negative; "
                f"got {tolerance}."
            )

        include = bool(entry.get("include_in_reconstructed_impedance", True))

        parsed.append(KnownMode(
            label=label,
            frequency_hz=frequency_hz,
            q=q,
            r_over_q_ohm=r_over_q_ohm,
            include_in_reconstructed_impedance=include,
            frequency_tolerance_hz=tolerance,
        ))
    return tuple(parsed)


def _get_known_required_float(entry: dict[str, Any], key: str, prefix: str) -> float:
    """Extract a required float field from a known-mode config entry."""
    value = entry.get(key)
    if value is None:
        raise WakeFitError(
            f"{prefix}.{key} is required but missing."
        )
    try:
        fv = float(value)
    except (TypeError, ValueError) as exc:
        raise WakeFitError(
            f"{prefix}.{key} must be a float; got {value!r}."
        ) from exc
    if not np.isfinite(fv):
        raise WakeFitError(
            f"{prefix}.{key} must be finite; got {fv}."
        )
    return fv


def build_wake_fit_input_from_config(
    *,
    direction: Direction,
    wake_s_m: np.ndarray,
    wake: np.ndarray,
    impedance_frequency_hz: np.ndarray,
    impedance: np.ndarray,
    config: dict[str, Any],
    default_freq_min_hz: float | None = None,
    default_freq_max_hz: float | None = None,
    peak_source_frequency_hz: np.ndarray | None = None,
    peak_source_impedance: np.ndarray | None = None,
    precomputed_peaks: tuple[PeakInfo, ...] | None = None,
    peak_source_label: str = "sampled_impedance",
) -> WakeFitInput:
    """Build typed fitting input from a Workflow-2 ``pso_fit`` config block."""

    cfg = config or {}
    bounds_cfg = cfg.get("bounds", {})
    peak_cfg = cfg.get("peak_settings", cfg.get("peaks", {}))
    if not isinstance(peak_cfg, dict):
        peak_cfg = {}
    peak_cfg = dict(peak_cfg)
    fit_peak_min = _optional_float(
        _get_any(cfg, "fit_peak_freq_min_hz", "fitPeakFreqMin_Hz", default=None)
    )
    fit_peak_max = _optional_float(
        _get_any(cfg, "fit_peak_freq_max_hz", "fitPeakFreqMax_Hz", default=None)
    )
    if fit_peak_min is not None and not any(
        key in peak_cfg for key in ("freq_min_hz", "freqMin_Hz")
    ):
        peak_cfg["freq_min_hz"] = fit_peak_min
    if fit_peak_max is not None and not any(
        key in peak_cfg for key in ("freq_max_hz", "freqMax_Hz")
    ):
        peak_cfg["freq_max_hz"] = fit_peak_max
    pso_cfg = cfg.get("pso", cfg)

    wake_s_arr = _as_1d_float(wake_s_m, "wake_s_m")
    sigma_z_m = _required_float(cfg, "sigma_z_m")
    legacy_fit_start_m = _optional_float(
        _get_any(cfg, "fit_start_m", "start_m", default=None)
    )
    legacy_fit_end_m = _optional_float(_get_any(cfg, "fit_end_m", "end_m", default=None))
    fit_window = FitWindowSettings.from_config(
        cfg,
        legacy_start_m=legacy_fit_start_m,
        legacy_end_m=legacy_fit_end_m,
    )
    fit_start_m, fit_end_m = fit_window.resolve_m(wake_s_arr)

    fit_point_count = int(
        _get_any(
            cfg,
            "fit_point_count",
            "point_count",
            "pointCount",
            default=len(wake_s_arr),
        )
    )

    return WakeFitInput(
        direction=_normalize_direction(direction),
        wake_s_m=wake_s_arr,
        wake=_as_1d_float(wake, "wake"),
        impedance_frequency_hz=_as_1d_float(
            impedance_frequency_hz, "impedance_frequency_hz"
        ),
        impedance=_as_1d_magnitude(impedance, "impedance"),
        sigma_z_m=sigma_z_m,
        fit_start_m=float(fit_start_m),
        fit_end_m=float(fit_end_m),
        fit_point_count=fit_point_count,
        bounds=PSOBounds.from_config(bounds_cfg),
        peak_settings=PeakDetectionSettings.from_config(
            peak_cfg,
            default_freq_min_hz=None,
            default_freq_max_hz=None,
        ),
        pso_settings=PSOSettings.from_config(pso_cfg),
        wake_charge_scale=float(cfg.get("wake_charge_scale", 1.0e12)),
        max_normalized_error=_optional_float(cfg.get("max_normalized_error")),
        min_wake_corr=_optional_float(cfg.get("min_wake_corr")),
        peak_source_frequency_hz=(
            None
            if peak_source_frequency_hz is None
            else _as_1d_float(peak_source_frequency_hz, "peak_source_frequency_hz")
        ),
        peak_source_impedance=(
            None
            if peak_source_impedance is None
            else _as_1d_magnitude(peak_source_impedance, "peak_source_impedance")
        ),
        precomputed_peaks=precomputed_peaks,
        peak_source_label=str(peak_source_label),
        known_modes=_known_modes_from_config(cfg, direction),
    )


def prepare_wake_fit_data(
    wake_s_m: np.ndarray,
    wake: np.ndarray,
    *,
    start_m: float,
    end_m: float,
    point_count: int,
) -> PreparedWakeFitData:
    """Interpolate wake data onto a uniform fitting grid.

    ``s_m`` is distance in meters.  The resonator formulas use time in
    seconds, so the returned ``t_s`` is ``s_m / c``.
    """

    wake_s = _as_1d_float(wake_s_m, "wake_s_m")
    wake_v = _as_1d_float(wake, "wake")
    if len(wake_s) != len(wake_v):
        raise WakeFitError("wake_s_m and wake must have the same length.")
    if point_count < 2:
        raise WakeFitError("PSO wake fitting requires at least 2 sample points.")
    if end_m <= start_m:
        raise WakeFitError("fit_end_m must be greater than fit_start_m.")

    order = np.argsort(wake_s)
    wake_s = wake_s[order]
    wake_v = wake_v[order]
    fit_s = np.linspace(float(start_m), float(end_m), int(point_count))
    fit_wake = _interp_linear_extrapolate(fit_s, wake_s, wake_v)
    fit_t = fit_s / C_LIGHT_M_PER_S
    return PreparedWakeFitData(
        s_m=fit_s,
        t_s=fit_t,
        wake=fit_wake,
        start_m=float(start_m),
        end_m=float(end_m),
        point_count=int(point_count),
        step_m=float(np.mean(np.diff(fit_s))),
    )


def estimate_sigma_z_from_charge_distribution(
    distance_m: np.ndarray,
    charge_density: np.ndarray,
) -> float:
    """Estimate RMS bunch length from a CST charge-distribution curve.

    ``distance_m`` is the CST charge distribution abscissa in meters.  The
    ordinate may be signed; ``abs(charge_density)`` is used as the statistical
    weight so negative density conventions do not produce a negative variance.
    The returned ``sigma_z_m`` is a positive RMS length in meters.
    """

    x = _as_1d_float(distance_m, "distance_m")
    rho = _as_1d_float(charge_density, "charge_density")
    if len(x) != len(rho):
        raise WakeFitError("distance_m and charge_density must have the same length.")
    weights = np.abs(rho)
    total = float(np.sum(weights))
    if not np.isfinite(total) or total <= 0.0:
        raise WakeFitError("Charge distribution has zero usable weight.")
    mean = float(np.sum(weights * x) / total)
    variance = float(np.sum(weights * (x - mean) ** 2) / total)
    if not np.isfinite(variance) or variance <= 0.0:
        raise WakeFitError("Estimated sigma_z_m is not positive.")
    return float(np.sqrt(variance))


def derive_impedance_from_wake(
    *,
    direction: Direction,
    wake_s_m: np.ndarray,
    wake: np.ndarray,
    sigma_z_m: float,
    peak_settings: PeakDetectionSettings | None = None,
    settings: WakeDerivedImpedanceSettings | None = None,
) -> WakeDerivedImpedanceResult:
    """Convert a CST wake-potential curve into a refined impedance peak source.

    This ports the non-GUI MATLAB ``wakeFileToImpedanceFile`` semantics:

    1. sort/unique wake samples and interpolate to a uniform ``s`` grid;
    2. compute impedance on a coarse frequency grid by linear integration;
    3. detect visible coarse peaks;
    4. add a local refined frequency grid around those already-visible peaks;
    5. recompute impedance and record the refined local maximum per coarse peak.

    The method refines frequencies only around peaks visible in step 3.  It
    cannot infer a high-Q mode whose peak is absent from the coarse grid.
    """

    direction_norm = _normalize_direction(direction)
    cfg = settings or WakeDerivedImpedanceSettings()
    peak_cfg = peak_settings or PeakDetectionSettings()
    if not np.isfinite(sigma_z_m) or sigma_z_m <= 0.0:
        raise WakeFitError("sigma_z_m must be positive for wake-to-impedance conversion.")

    s_uniform, wake_uniform = _uniform_wake_samples(
        wake_s_m,
        wake,
        point_count=cfg.wake_point_count,
    )
    wake_si = wake_uniform * 1.0e12
    f_min = float(cfg.freq_min_hz)
    f_max = (
        float(cfg.freq_max_hz)
        if cfg.freq_max_hz is not None
        else C_LIGHT_M_PER_S / (3.0 * float(sigma_z_m))
    )
    if not np.isfinite(f_max) or f_max <= f_min:
        raise WakeFitError("Derived impedance frequency range is invalid.")

    f_coarse = np.linspace(f_min, f_max, int(cfg.freq_point_count))
    z_coarse = _wake_to_impedance_linear(
        direction_norm,
        s_uniform,
        wake_si,
        f_coarse,
        sigma_z_m,
    )
    z_coarse_abs = np.abs(z_coarse)

    coarse_peaks = _detect_impedance_peaks_unlimited(
        f_coarse,
        z_coarse_abs,
        peak_cfg,
        source="wake_derived_coarse",
    )
    selected_for_refine = _select_peaks_for_pso(coarse_peaks, peak_cfg)
    if not selected_for_refine:
        return WakeDerivedImpedanceResult(
            coarse_frequency_hz=f_coarse,
            coarse_impedance_complex=z_coarse,
            refined_frequency_hz=f_coarse,
            refined_impedance_complex=z_coarse,
            peaks=(),
            settings=cfg,
            base_df_hz=float(np.median(np.diff(f_coarse))),
            local_grid_refinement_active=False,
        )

    base_df = float(np.median(np.diff(f_coarse)))
    f_refined = _build_refined_frequency_grid(
        f_coarse,
        np.array([peak.frequency_hz for peak in selected_for_refine], dtype=float),
        base_df,
        refine_factor=cfg.adaptive_refine_factor,
        half_width_bins=cfg.adaptive_half_width_bins,
        max_point_count=cfg.adaptive_max_freq_point_count,
    )
    z_refined = _wake_to_impedance_linear(
        direction_norm,
        s_uniform,
        wake_si,
        f_refined,
        sigma_z_m,
    )
    z_refined_abs = np.abs(z_refined)
    half_width_hz = cfg.adaptive_half_width_bins * base_df
    refined_selected = _refine_coarse_peaks(
        selected_for_refine,
        f_refined,
        z_refined_abs,
        half_width_hz=half_width_hz,
    )
    refined_by_coarse = {
        peak.coarse_index: peak
        for peak in refined_selected
    }
    refined_peaks: list[PeakInfo] = []
    for coarse_peak in coarse_peaks:
        refined_peak = refined_by_coarse.get(coarse_peak.index)
        if refined_peak is None:
            refined_peaks.append(
                replace(
                    coarse_peak,
                    use=False,
                    status="VisibleNotSelected",
                    source="wake_derived_coarse_unselected",
                )
            )
        else:
            refined_peaks.append(refined_peak)
    local_refinement_active = len(f_refined) > len(f_coarse)
    return WakeDerivedImpedanceResult(
        coarse_frequency_hz=f_coarse,
        coarse_impedance_complex=z_coarse,
        refined_frequency_hz=f_refined,
        refined_impedance_complex=z_refined,
        peaks=tuple(sorted(refined_peaks, key=lambda peak: peak.frequency_hz)),
        settings=cfg,
        base_df_hz=base_df,
        local_grid_refinement_active=local_refinement_active,
    )


def detect_impedance_peaks(
    frequency_hz: np.ndarray,
    impedance: np.ndarray,
    settings: PeakDetectionSettings | None = None,
) -> tuple[PeakInfo, ...]:
    """Detect visible peaks on the sampled impedance grid.

    This mirrors the MATLAB tool's key limitation: frequencies are taken from
    sampled local maxima.  A high-Q peak that never appears in the sampled
    input array cannot be recovered here.
    """

    cfg = _validate_peak_settings(settings or PeakDetectionSettings())
    peaks = _detect_impedance_peaks_unlimited(
        frequency_hz,
        impedance,
        cfg,
        source="sampled_impedance",
    )
    if cfg.max_peaks is None or cfg.max_peaks <= 0:
        return peaks
    return peaks[: cfg.max_peaks]


def _detect_impedance_peaks_unlimited(
    frequency_hz: np.ndarray,
    impedance: np.ndarray,
    settings: PeakDetectionSettings,
    *,
    source: str,
) -> tuple[PeakInfo, ...]:
    cfg = _validate_peak_settings(settings)
    f_hz = _as_1d_float(frequency_hz, "frequency_hz")
    z = _as_1d_magnitude(impedance, "impedance")
    if len(f_hz) != len(z):
        raise WakeFitError("frequency_hz and impedance must have the same length.")

    lo = -np.inf if cfg.freq_min_hz is None else float(cfg.freq_min_hz)
    hi = np.inf if cfg.freq_max_hz is None else float(cfg.freq_max_hz)
    mask = np.isfinite(f_hz) & np.isfinite(z) & (f_hz >= lo) & (f_hz <= hi)
    if not np.any(mask):
        return ()

    f_sub = f_hz[mask]
    z_sub = z[mask]
    global_idx = np.flatnonzero(mask)
    locs_sub, pks = _find_peaks_1d(
        z_sub,
        min_peak_height=cfg.min_peak_height,
        min_peak_distance_points=cfg.min_peak_distance_points,
    )
    if len(locs_sub) == 0:
        return ()

    locs_global = global_idx[locs_sub]
    order = np.argsort(f_hz[locs_global])
    locs_global = locs_global[order]
    pks = pks[order]

    if cfg.delete_first_n > 0:
        locs_global = locs_global[cfg.delete_first_n :]
        pks = pks[cfg.delete_first_n :]
    return tuple(
        PeakInfo(
            index=int(idx),
            frequency_hz=float(f_hz[idx]),
            value=float(pk),
            coarse_frequency_hz=float(f_hz[idx]),
            refined_frequency_hz=float(f_hz[idx]),
            coarse_index=int(idx),
            source=source,
        )
        for idx, pk in zip(locs_global, pks)
    )


def _select_peaks_for_pso(
    peaks: Sequence[PeakInfo],
    settings: PeakDetectionSettings,
) -> tuple[PeakInfo, ...]:
    cfg = _validate_peak_settings(settings)
    candidates = tuple(peak for peak in peaks if peak.use)
    max_modes = cfg.max_selected_modes
    if max_modes is None and cfg.max_peaks is not None and cfg.max_peaks > 0:
        max_modes = cfg.max_peaks
    if cfg.selection_strategy == "top_amplitude":
        ordered = tuple(sorted(candidates, key=lambda peak: peak.value, reverse=True))
        if max_modes is not None and max_modes > 0:
            ordered = ordered[:max_modes]
        return tuple(sorted(ordered, key=lambda peak: peak.frequency_hz))
    if max_modes is not None and max_modes > 0:
        return candidates[:max_modes]
    return candidates


def _mark_selected_peaks(
    all_peaks: Sequence[PeakInfo],
    selected: Sequence[PeakInfo],
) -> tuple[PeakInfo, ...]:
    selected_keys = {
        (
            round(float(peak.frequency_hz), 6),
            round(float(peak.coarse_frequency_hz or peak.frequency_hz), 6),
        )
        for peak in selected
    }
    marked: list[PeakInfo] = []
    for peak in all_peaks:
        key = (
            round(float(peak.frequency_hz), 6),
            round(float(peak.coarse_frequency_hz or peak.frequency_hz), 6),
        )
        is_selected = key in selected_keys
        marked.append(
            replace(
                peak,
                use=is_selected,
                status="Use" if is_selected else "VisibleNotSelected",
            )
        )
    return tuple(marked)


def _filter_known_mode_peaks(
    peaks: Sequence[PeakInfo],
    known_modes: tuple[KnownMode, ...],
) -> tuple[tuple[PeakInfo, ...], tuple[PeakInfo, ...]]:
    """Split *peaks* into unknown peaks and known-mode-matched peaks.

    A peak is considered to match a known mode when its frequency is within
    ``max(known.frequency_tolerance_hz, 1.0)`` Hz of the known mode's
    ``frequency_hz``.  The 1 Hz floor prevents float-rounding mismatches
    when the caller intends an exact-frequency match (tolerance = 0.0).

    Returns ``(unknown_peaks, filtered_peaks)``.
    """

    if not known_modes:
        return tuple(peaks), ()

    unknown: list[PeakInfo] = []
    filtered: list[PeakInfo] = []
    for peak in peaks:
        is_known = False
        for km in known_modes:
            tol = max(float(km.frequency_tolerance_hz), 1.0)
            if abs(float(peak.frequency_hz) - float(km.frequency_hz)) <= tol:
                is_known = True
                break
        if is_known:
            filtered.append(peak)
        else:
            unknown.append(peak)
    return tuple(unknown), tuple(filtered)


def _validate_peak_settings(settings: PeakDetectionSettings) -> PeakDetectionSettings:
    strategy = str(settings.selection_strategy).strip().lower()
    if strategy not in ("all_visible", "top_amplitude"):
        raise WakeFitError(
            "peak_selection.strategy must be 'all_visible' or 'top_amplitude'."
        )
    if strategy == settings.selection_strategy:
        return settings
    return replace(settings, selection_strategy=strategy)  # type: ignore[arg-type]


def wake_from_parameters(
    x: np.ndarray,
    resonant_frequency_hz: np.ndarray,
    t_s: np.ndarray,
    direction: Direction,
) -> np.ndarray:
    """Evaluate the resonator wake model.

    ``x`` is ``[A1, Q1, A2, Q2, ...]``.  ``A`` carries the fitted wake unit
    supplied by the caller, while ``Q`` is dimensionless.
    """

    fr_hz = _as_1d_float(resonant_frequency_hz, "resonant_frequency_hz")
    params = _as_1d_float(x, "x")
    t_arr = _as_1d_float(t_s, "t_s")
    direction_norm = _normalize_direction(direction)
    if len(params) != 2 * len(fr_hz):
        raise WakeFitError("Parameter vector length must be 2 * n_modes.")

    wake = np.zeros_like(t_arr, dtype=float)
    for i, fr in enumerate(fr_hz):
        amplitude = float(params[2 * i])
        q = float(params[2 * i + 1])
        if q <= 0:
            raise WakeFitError("Q must be positive.")
        coef_im = np.sqrt(max(0.0, 1.0 - 1.0 / (4.0 * q * q)))
        phase = 2.0 * np.pi * fr * coef_im * t_arr
        envelope = amplitude * np.exp(-np.pi * fr * t_arr / q)

        if direction_norm == "transverse":
            wake = wake + envelope * np.sin(phase)
        else:
            if q <= 0.5:
                raise WakeFitError("Longitudinal wake formula requires Q > 0.5.")
            wake = wake - envelope * (
                np.cos(phase)
                - (1.0 / np.sqrt(4.0 * q * q - 1.0)) * np.sin(phase)
            )
    return wake


def compute_known_mode_wake(
    known_modes: tuple[KnownMode, ...],
    t_s: np.ndarray,
    direction: Direction,
    sigma_z_m: float,
    wake_charge_scale: float,
) -> np.ndarray:
    """Compute wake contribution from fixed known resonator modes.

    Each known mode's ``r_over_q_ohm`` is converted to a wake amplitude
    using the same form-factor convention as the PSO fit path::

        amplitude = (R/Q) * form_factor(f, sigma_z) * 2*pi*f / wake_charge_scale

    The resonator wake model is then evaluated on the time grid ``t_s``
    and summed over all known modes.

    Returns
    -------
    total_wake : ndarray
        Total wake from all known modes, same shape as ``t_s`` and in the
        same unit as the fitted wake (e.g. V/pC for longitudinal).
        Zero array when ``known_modes`` is empty.
    """

    t_arr = _as_1d_float(t_s, "t_s")
    direction_norm = _normalize_direction(direction)
    if not known_modes:
        return np.zeros_like(t_arr)

    total_wake = np.zeros_like(t_arr, dtype=float)
    for km in known_modes:
        ff = _gaussian_form_factor(sigma_z_m, np.array([km.frequency_hz]))
        amplitude = (
            km.r_over_q_ohm
            * float(ff[0])
            * (2.0 * np.pi * km.frequency_hz)
            / wake_charge_scale
        )
        params = np.array([amplitude, km.q])
        fr = np.array([km.frequency_hz])
        mode_wake = wake_from_parameters(params, fr, t_arr, direction_norm)
        total_wake = total_wake + mode_wake
    return total_wake


def wake_objective(
    x: np.ndarray,
    resonant_frequency_hz: np.ndarray,
    t_s: np.ndarray,
    wake: np.ndarray,
    direction: Direction,
) -> float:
    """Sum-of-squares wake residual objective minimized by PSO."""

    try:
        fit = wake_from_parameters(x, resonant_frequency_hz, t_s, direction)
        residual = fit.reshape(-1) - _as_1d_float(wake, "wake").reshape(-1)
        value = float(np.sum(residual * residual))
    except Exception:
        return float(np.finfo(float).max)
    return value if np.isfinite(value) else float(np.finfo(float).max)


def _wake_objective_with_known(
    x: np.ndarray,
    resonant_frequency_hz: np.ndarray,
    t_s: np.ndarray,
    wake: np.ndarray,
    direction: Direction,
    known_wake: np.ndarray,
) -> float:
    """Sum-of-squares wake residual with fixed known-mode contribution.

    The total model is ``known_wake + fitted_unknown_wake``; the residual
    is ``total_model - target_wake``.
    """

    try:
        unknown_fit = wake_from_parameters(x, resonant_frequency_hz, t_s, direction)
        total_fit = unknown_fit + known_wake
        residual = total_fit.reshape(-1) - _as_1d_float(wake, "wake").reshape(-1)
        value = float(np.sum(residual * residual))
    except Exception:
        return float(np.finfo(float).max)
    return value if np.isfinite(value) else float(np.finfo(float).max)


def calc_form_factor(
    tau_s: np.ndarray,
    normalized_density: np.ndarray,
    frequency_hz: np.ndarray,
    flag: Literal["scalar", "full"] = "scalar",
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate bunch form factor on a frequency grid.

    The density is normalized in 1/s.  The returned magnitude is
    dimensionless; it scales fitted wake amplitudes into ``R/Q``.
    """

    tau = _as_1d_float(tau_s, "tau_s")
    rho = _as_1d_float(normalized_density, "normalized_density")
    freqs = _as_1d_float(frequency_hz, "frequency_hz")
    if len(tau) != len(rho):
        raise WakeFitError("tau_s and normalized_density length mismatch.")
    if len(tau) < 2:
        raise WakeFitError("Form factor needs at least 2 time samples.")

    out = np.empty_like(freqs, dtype=float)
    phase = np.zeros_like(freqs, dtype=float)
    for i, freq in enumerate(freqs):
        fourier = rho * np.exp(-1j * 2.0 * np.pi * freq * tau)
        integral = np.trapezoid(fourier, tau)
        out[i] = float(abs(integral))
        if flag == "full":
            phase[i] = float(np.arctan2(np.imag(integral), np.real(integral)))
        elif flag != "scalar":
            raise WakeFitError(f"Unknown form-factor flag: {flag!r}")
    return out, phase


def resonator_sum(
    frequency_hz: np.ndarray,
    resonant_frequency_hz: np.ndarray,
    q: np.ndarray,
    r_over_q: np.ndarray,
    direction: Direction,
) -> np.ndarray:
    """Reconstruct complex impedance from fitted resonator modes.

    ``R = Q * (R/Q)`` is in Ohm for longitudinal impedance and Ohm/m for
    transverse impedance when the caller's wake units are consistent.
    """

    freqs = _as_1d_float(frequency_hz, "frequency_hz").astype(float)
    freqs = freqs.copy()
    freqs[freqs == 0.0] = np.finfo(float).eps
    fr_hz = _as_1d_float(resonant_frequency_hz, "resonant_frequency_hz")
    q_arr = _as_1d_float(q, "q")
    rq_arr = _as_1d_float(r_over_q, "r_over_q")
    direction_norm = _normalize_direction(direction)
    if not (len(fr_hz) == len(q_arr) == len(rq_arr)):
        raise WakeFitError("fr_hz, q, and r_over_q must have the same length.")

    z_complex = np.zeros_like(freqs, dtype=complex)
    shunt = q_arr * rq_arr
    for fr, qi, ri in zip(fr_hz, q_arr, shunt):
        denom = 1.0 - 1j * qi * (fr / freqs - freqs / fr)
        if direction_norm == "transverse":
            z_complex = z_complex + ri / denom * fr / freqs
        else:
            z_complex = z_complex + ri / denom
    return z_complex


def fit_wake_with_pso(
    fit_input: WakeFitInput,
    *,
    optimizer: OptimizerFn | None = None,
) -> WakeFitResult:
    """Fit wake data and reconstruct the impedance curve.

    Frequencies are fixed to visible peaks in the supplied impedance curve;
    PSO optimizes only amplitude ``A`` and quality factor ``Q`` for each mode.
    """

    direction = _normalize_direction(fit_input.direction)
    if fit_input.precomputed_peaks is not None:
        peaks = tuple(fit_input.precomputed_peaks)
    else:
        source_f = (
            fit_input.impedance_frequency_hz
            if fit_input.peak_source_frequency_hz is None
            else fit_input.peak_source_frequency_hz
        )
        source_z = (
            fit_input.impedance
            if fit_input.peak_source_impedance is None
            else fit_input.peak_source_impedance
        )
        peaks = _detect_impedance_peaks_unlimited(
            source_f,
            source_z,
            fit_input.peak_settings,
            source=fit_input.peak_source_label,
        )
    selected = _select_peaks_for_pso(peaks, fit_input.peak_settings)
    all_peaks = _mark_selected_peaks(peaks, selected)

    # Filter out selected peaks that match a known mode's frequency.
    has_known = bool(fit_input.known_modes)
    if has_known:
        selected_unknown, filtered_known = _filter_known_mode_peaks(
            selected, fit_input.known_modes
        )
        if filtered_known:
            filtered_freqs = {round(float(p.frequency_hz), 6) for p in filtered_known}
            all_peaks = tuple(
                replace(p, use=False, status="KnownModeFiltered")
                if round(float(p.frequency_hz), 6) in filtered_freqs and p.use
                else p
                for p in all_peaks
            )
        selected = selected_unknown

    # Allow zero unknown peaks when known modes exist.
    if len(selected) < fit_input.peak_settings.min_peak_count:
        if not (has_known and len(selected) == 0):
            raise WakeFitError(
                "PSO wake fitting found "
                f"{len(selected)} visible peak(s), below min_peak_count="
                f"{fit_input.peak_settings.min_peak_count}."
            )

    fit_data = prepare_wake_fit_data(
        fit_input.wake_s_m,
        fit_input.wake,
        start_m=fit_input.fit_start_m,
        end_m=fit_input.fit_end_m,
        point_count=fit_input.fit_point_count,
    )
    target_wake = fit_data.wake

    # Compute known-mode wake (if any).
    known_mode_wake_arr = compute_known_mode_wake(
        fit_input.known_modes,
        fit_data.t_s,
        direction,
        fit_input.sigma_z_m,
        fit_input.wake_charge_scale,
    )

    if len(selected) == 0 and has_known:
        # ---- zero unknown modes: known wake only ---------------------------
        fr_hz = np.array([], dtype=float)
        x_best = np.array([], dtype=float)
        optimizer_info: dict[str, Any] = {}
        wake_fit_unknown = np.zeros_like(fit_data.t_s, dtype=float)
        amplitudes = np.array([], dtype=float)
        q_values = np.array([], dtype=float)
        r_over_q = np.array([], dtype=float)
    else:
        # ---- normal PSO path for unknown modes -----------------------------
        fr_hz = np.array([peak.frequency_hz for peak in selected], dtype=float)
        lb, ub = fit_input.bounds.expand(len(fr_hz), direction)

        if has_known:
            objective = lambda x: _wake_objective_with_known(  # noqa: E731
                x, fr_hz, fit_data.t_s, target_wake, direction, known_mode_wake_arr,
            )
        else:
            objective = lambda x: wake_objective(  # noqa: E731
                x, fr_hz, fit_data.t_s, target_wake, direction,
            )

        run_optimizer = optimizer or _run_pymoo_pso
        opt_result = run_optimizer(objective, lb, ub, fit_input.pso_settings)
        if len(opt_result) == 2:
            x_best, objective_value = opt_result  # type: ignore[misc]
            optimizer_info = {}
        else:
            x_best, objective_value, optimizer_info = opt_result  # type: ignore[misc]
        x_best = _as_1d_float(x_best, "x_best")

        wake_fit_unknown = wake_from_parameters(x_best, fr_hz, fit_data.t_s, direction)

        form_factor = _gaussian_form_factor(fit_input.sigma_z_m, fr_hz)
        amplitudes = x_best[0::2]
        q_values = x_best[1::2]
        if np.any(form_factor <= 0.0):
            raise WakeFitError("Form factor is zero for at least one fitted mode.")

        r_over_q = (
            amplitudes
            / form_factor
            / (2.0 * np.pi * fr_hz)
            * float(fit_input.wake_charge_scale)
        )

    # ---- common: total wake and error metrics ------------------------------
    wake_fit_total = wake_fit_unknown + known_mode_wake_arr
    denom = max(float(np.sum(target_wake * target_wake)), np.finfo(float).eps)
    normalized_error = float(np.sum((wake_fit_total - target_wake) ** 2) / denom)
    wake_corr = _correlation_or_nan(target_wake, wake_fit_total)
    # objective_value is the residual sum-of-squares (SSE).
    objective_value = float(np.sum((wake_fit_total - target_wake) ** 2))

    # ---- common: impedance reconstruction -----------------------------------
    if len(fr_hz) > 0:
        impedance_complex = resonator_sum(
            fit_input.impedance_frequency_hz,
            fr_hz,
            q_values,
            r_over_q,
            direction,
        )
    else:
        impedance_complex = np.zeros_like(
            fit_input.impedance_frequency_hz, dtype=complex
        )

    # Add known-mode contributions to reconstructed impedance when configured.
    if has_known:
        known_include = [
            km for km in fit_input.known_modes
            if km.include_in_reconstructed_impedance
        ]
        if known_include:
            known_fr = np.array([km.frequency_hz for km in known_include], dtype=float)
            known_q = np.array([km.q for km in known_include], dtype=float)
            known_rq = np.array([km.r_over_q_ohm for km in known_include], dtype=float)
            known_z = resonator_sum(
                fit_input.impedance_frequency_hz,
                known_fr,
                known_q,
                known_rq,
                direction,
            )
            impedance_complex = impedance_complex + known_z

    impedance_abs = np.abs(impedance_complex)
    modes = tuple(
        ModeFit(
            frequency_hz=float(fr),
            amplitude=float(amplitude),
            q=float(qi),
            r_over_q=float(rq),
            shunt_impedance=float(qi * rq),
        )
        for fr, amplitude, qi, rq in zip(fr_hz, amplitudes, q_values, r_over_q)
    )

    # ---- common: additional result fields ----------------------------------
    unknown_mode_wake_arr = wake_fit_unknown if has_known else None
    residual_wake_arr = (target_wake - wake_fit_total).copy()

    diagnostics: dict[str, Any] = {
        "known_mode_count": len(fit_input.known_modes),
        "fitted_mode_count": len(modes),
        "known_mode_labels": [km.label for km in fit_input.known_modes],
    }
    if len(target_wake) > 0:
        diagnostics["target_wake_rms"] = float(np.sqrt(np.mean(target_wake ** 2)))
    else:
        diagnostics["target_wake_rms"] = 0.0
    if has_known and len(known_mode_wake_arr) > 0:
        diagnostics["known_mode_wake_rms"] = float(
            np.sqrt(np.mean(known_mode_wake_arr ** 2))
        )
    else:
        diagnostics["known_mode_wake_rms"] = 0.0
    diagnostics["unknown_mode_wake_rms"] = float(
        np.sqrt(np.mean(wake_fit_unknown ** 2))
    ) if len(wake_fit_unknown) > 0 else 0.0
    diagnostics["residual_wake_rms"] = float(
        np.sqrt(np.mean(residual_wake_arr ** 2))
    ) if len(residual_wake_arr) > 0 else 0.0
    diagnostics["normalized_error"] = normalized_error
    diagnostics["wake_corr"] = wake_corr
    diagnostics["known_mode_filtered_peak_count"] = len(
        [p for p in all_peaks if p.status == "KnownModeFiltered"]
    )

    status = "ok"
    failure_reason = ""
    if (
        fit_input.max_normalized_error is not None
        and normalized_error > fit_input.max_normalized_error
    ):
        status = "failed"
        failure_reason = (
            "PSO wake fit normalized error "
            f"{normalized_error:.6g} exceeds max_normalized_error="
            f"{fit_input.max_normalized_error:.6g}."
        )
    if (
        status == "ok"
        and fit_input.min_wake_corr is not None
        and (
            not np.isfinite(wake_corr)
            or wake_corr < float(fit_input.min_wake_corr)
        )
    ):
        status = "failed"
        failure_reason = (
            "PSO wake fit correlation "
            f"{wake_corr:.6g} is below min_wake_corr="
            f"{fit_input.min_wake_corr:.6g}."
        )

    return WakeFitResult(
        modes=modes,
        fit_s_m=fit_data.s_m,
        fit_t_s=fit_data.t_s,
        fit_wake=target_wake,
        wake_fit=wake_fit_total,
        impedance_frequency_hz=fit_input.impedance_frequency_hz.copy(),
        impedance_complex=impedance_complex,
        impedance_abs=impedance_abs,
        normalized_error=normalized_error,
        wake_corr=wake_corr,
        objective_value=float(objective_value),
        selected_peaks=selected,
        all_peaks=all_peaks,
        status=status,
        failure_reason=failure_reason,
        optimizer_info=optimizer_info,
        known_modes=fit_input.known_modes,
        known_mode_wake=known_mode_wake_arr if has_known else None,
        unknown_mode_wake=unknown_mode_wake_arr,
        residual_wake=residual_wake_arr,
        diagnostics=diagnostics,
    )


def _uniform_wake_samples(
    wake_s_m: np.ndarray,
    wake: np.ndarray,
    *,
    point_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    s = _as_1d_float(wake_s_m, "wake_s_m")
    w = _as_1d_float(wake, "wake")
    if len(s) != len(w):
        raise WakeFitError("wake_s_m and wake must have the same length.")
    order = np.argsort(s)
    s = s[order]
    w = w[order]
    s_unique, unique_idx = np.unique(s, return_index=True)
    w_unique = w[unique_idx]
    if len(s_unique) < 2:
        raise WakeFitError("Wake-to-impedance conversion needs at least 2 samples.")
    if np.any(np.diff(s_unique) <= 0.0):
        raise WakeFitError("Wake coordinates must be strictly increasing.")
    s_uniform = np.linspace(float(s_unique[0]), float(s_unique[-1]), int(point_count))
    w_uniform = np.interp(s_uniform, s_unique, w_unique)
    return s_uniform, w_uniform


def _wake_to_impedance_linear(
    direction: Direction,
    s_m: np.ndarray,
    wake_si: np.ndarray,
    frequency_hz: np.ndarray,
    sigma_z_m: float,
) -> np.ndarray:
    """Linear-segment wake-to-impedance integration from the MATLAB tool.

    ``wake_si`` is V/C for longitudinal and V/C/m for transverse.  The
    Gaussian charge distribution uses ``sigma_z_m`` in meters.
    """

    direction_norm = _normalize_direction(direction)
    s = _as_1d_float(s_m, "s_m")
    wake = _as_1d_float(wake_si, "wake_si")
    freqs = _as_1d_float(frequency_hz, "frequency_hz")
    if len(s) != len(wake):
        raise WakeFitError("s_m and wake_si must have the same length.")
    ds = np.diff(s)
    if np.any(ds <= 0.0) or not np.all(np.isfinite(ds)):
        raise WakeFitError("Wake-position array must be strictly increasing.")

    omega = 2.0 * np.pi * freqs
    charge = (
        1.0
        / np.sqrt(2.0 * np.pi)
        / float(sigma_z_m)
        * np.exp(-(s**2) / (2.0 * float(sigma_z_m) ** 2))
    )
    wake_slope = np.diff(wake) / ds
    charge_slope = np.diff(charge) / ds
    imp_wp = np.zeros_like(freqs, dtype=complex)
    imp_cg = np.zeros_like(freqs, dtype=complex)
    for i in range(len(wake_slope)):
        s0 = float(s[i])
        s1 = float(s[i + 1])
        imp_wp = imp_wp + _linear_antiderivative_space(
            omega,
            float(wake[i + 1]),
            s1,
            float(wake_slope[i]),
        ) - _linear_antiderivative_space(
            omega,
            float(wake[i]),
            s0,
            float(wake_slope[i]),
        )
        imp_cg = imp_cg + _linear_antiderivative_space(
            omega,
            float(charge[i + 1]),
            s1,
            float(charge_slope[i]),
        ) - _linear_antiderivative_space(
            omega,
            float(charge[i]),
            s0,
            float(charge_slope[i]),
        )

    den = np.real(imp_cg)
    tol = np.finfo(float).eps * max(1.0, float(np.nanmax(np.abs(den))))
    den = den.copy()
    den[np.abs(den) < tol] = np.nan
    if direction_norm == "transverse":
        return 1j * imp_wp / den / C_LIGHT_M_PER_S
    return -imp_wp / den / C_LIGHT_M_PER_S


def _linear_antiderivative_space(
    omega: np.ndarray,
    y_at_s: float,
    s_m: float,
    slope: float,
) -> np.ndarray:
    omega_arr = np.asarray(omega, dtype=float).reshape(-1)
    lam = -1j * omega_arr / C_LIGHT_M_PER_S
    out = np.zeros_like(lam, dtype=complex)
    zero = np.abs(lam) < np.finfo(float).eps
    if np.any(zero):
        b = y_at_s - slope * s_m
        out[zero] = 0.5 * slope * s_m**2 + b * s_m
    if np.any(~zero):
        lam_nz = lam[~zero]
        out[~zero] = np.exp(lam_nz * s_m) * (
            y_at_s / lam_nz - slope / (lam_nz**2)
        )
    return out


def _build_refined_frequency_grid(
    f_hz_first: np.ndarray,
    peak_freq_hz: np.ndarray,
    base_df_hz: float,
    *,
    refine_factor: int,
    half_width_bins: int,
    max_point_count: int,
) -> np.ndarray:
    f_first = _as_1d_float(f_hz_first, "f_hz_first")
    peak_freqs = np.asarray(peak_freq_hz, dtype=float).reshape(-1)
    if peak_freqs.size == 0 or not np.isfinite(base_df_hz) or base_df_hz <= 0.0:
        return f_first
    f_min = float(np.min(f_first))
    f_max = float(np.max(f_first))
    extras: list[np.ndarray] = []
    for fp in peak_freqs:
        if not np.isfinite(fp):
            continue
        half_width = int(half_width_bins) * float(base_df_hz)
        local_min = max(f_min, float(fp) - half_width)
        local_max = min(f_max, float(fp) + half_width)
        if local_max <= local_min:
            continue
        local_n = max(
            3,
            int(round((local_max - local_min) / (base_df_hz / int(refine_factor)))) + 1,
        )
        extras.append(np.linspace(local_min, local_max, local_n))
    if not extras:
        return f_first
    f_all = np.unique(np.concatenate([f_first, *extras]))
    f_all.sort()
    if len(f_all) <= int(max_point_count):
        return f_all

    extra_unique = np.setdiff1d(f_all, f_first, assume_unique=False)
    available = int(max_point_count) - len(f_first)
    if available <= 0:
        return f_first
    if len(extra_unique) > available:
        idx = np.round(np.linspace(0, len(extra_unique) - 1, available)).astype(int)
        extra_unique = extra_unique[idx]
    f_limited = np.unique(np.concatenate([f_first, extra_unique]))
    f_limited.sort()
    return f_limited


def _refine_coarse_peaks(
    coarse_peaks: Sequence[PeakInfo],
    refined_frequency_hz: np.ndarray,
    refined_impedance_abs: np.ndarray,
    *,
    half_width_hz: float,
) -> tuple[PeakInfo, ...]:
    f_ref = _as_1d_float(refined_frequency_hz, "refined_frequency_hz")
    z_ref = _as_1d_magnitude(refined_impedance_abs, "refined_impedance_abs")
    out: list[PeakInfo] = []
    for coarse in coarse_peaks:
        coarse_freq = float(coarse.frequency_hz)
        mask = (
            np.isfinite(f_ref)
            & np.isfinite(z_ref)
            & (f_ref >= coarse_freq - half_width_hz)
            & (f_ref <= coarse_freq + half_width_hz)
        )
        if not np.any(mask):
            idx = int(np.argmin(np.abs(f_ref - coarse_freq)))
        else:
            local_idx = np.flatnonzero(mask)
            idx = int(local_idx[int(np.argmax(z_ref[local_idx]))])
        refined_freq = float(f_ref[idx])
        out.append(
            PeakInfo(
                index=idx,
                frequency_hz=refined_freq,
                value=float(z_ref[idx]),
                use=True,
                status="Use",
                coarse_frequency_hz=float(coarse.frequency_hz),
                refined_frequency_hz=refined_freq,
                coarse_index=coarse.index,
                source="wake_derived_refined",
            )
        )
    return tuple(sorted(out, key=lambda peak: peak.frequency_hz))


def _correlation_or_nan(a: np.ndarray, b: np.ndarray) -> float:
    a_arr = _as_1d_float(a, "a")
    b_arr = _as_1d_float(b, "b")
    if len(a_arr) != len(b_arr):
        return float("nan")
    if float(np.std(a_arr)) <= 0.0 or float(np.std(b_arr)) <= 0.0:
        return float("nan")
    return float(np.corrcoef(a_arr, b_arr)[0, 1])


def _run_pymoo_pso(
    objective: Callable[[np.ndarray], float],
    lb: np.ndarray,
    ub: np.ndarray,
    settings: PSOSettings,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    """Run pymoo's PSO implementation.

    ``pymoo`` is imported lazily so importing Workflow 2 does not fail in
    environments that have not installed project dependencies yet.
    """

    try:
        from pymoo.algorithms.soo.nonconvex.pso import PSO
        from pymoo.core.problem import ElementwiseProblem
        from pymoo.optimize import minimize
    except Exception as exc:  # pragma: no cover - depends on local env
        raise WakeFitError(
            "pymoo is required for production PSO wake fitting. Install the "
            "project dependencies or pass an explicit optimizer in tests."
        ) from exc

    class _WakeProblem(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(n_var=len(lb), n_obj=1, xl=lb, xu=ub)

        def _evaluate(self, x, out, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            out["F"] = objective(np.asarray(x, dtype=float))

    algorithm = PSO(pop_size=int(settings.swarm_size))
    termination: Any = ("n_gen", int(settings.max_iterations))
    try:  # pymoo termination APIs vary a little across 0.6.x releases.
        from pymoo.termination.default import DefaultSingleObjectiveTermination

        termination = DefaultSingleObjectiveTermination(
            ftol=float(settings.function_tolerance),
            n_max_gen=int(settings.max_iterations),
        )
    except Exception:
        termination = ("n_gen", int(settings.max_iterations))

    result = minimize(
        _WakeProblem(),
        algorithm,
        termination,
        seed=int(settings.seed),
        verbose=False,
    )
    if result.X is None:
        raise WakeFitError("pymoo PSO did not return a best solution.")
    x_best = np.asarray(result.X, dtype=float).reshape(-1)
    f_best = float(np.asarray(result.F, dtype=float).reshape(-1)[0])
    return x_best, f_best, {
        "algorithm": "pymoo.PSO",
        "n_gen": getattr(result.algorithm, "n_gen", None),
    }


def _gaussian_form_factor(sigma_z_m: float, frequency_hz: np.ndarray) -> np.ndarray:
    if not np.isfinite(sigma_z_m) or sigma_z_m <= 0.0:
        raise WakeFitError("sigma_z_m must be a positive finite length in meters.")
    sigma_t_s = float(sigma_z_m) / C_LIGHT_M_PER_S
    tau_s = np.linspace(-6.0 * sigma_t_s, 6.0 * sigma_t_s, 12001)
    density = (
        1.0
        / np.sqrt(2.0 * np.pi)
        / sigma_t_s
        * np.exp(-0.5 * (tau_s / sigma_t_s) ** 2)
    )
    form_factor, _ = calc_form_factor(tau_s, density, frequency_hz, "scalar")
    return form_factor


def _find_peaks_1d(
    values: np.ndarray,
    *,
    min_peak_height: float | None,
    min_peak_distance_points: int,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        from scipy.signal import find_peaks

        kwargs: dict[str, Any] = {"distance": max(1, int(min_peak_distance_points))}
        if min_peak_height is not None and np.isfinite(min_peak_height):
            kwargs["height"] = float(min_peak_height)
        locs, props = find_peaks(values, **kwargs)
        if "peak_heights" in props:
            pks = np.asarray(props["peak_heights"], dtype=float)
        else:
            pks = values[locs]
        return np.asarray(locs, dtype=int), np.asarray(pks, dtype=float)
    except Exception:
        pass

    if len(values) < 3:
        return np.array([], dtype=int), np.array([], dtype=float)
    locs = np.flatnonzero((values[1:-1] > values[:-2]) & (values[1:-1] >= values[2:]))
    locs = locs + 1
    if min_peak_height is not None and np.isfinite(min_peak_height):
        locs = locs[values[locs] >= float(min_peak_height)]
    if len(locs) == 0:
        return np.array([], dtype=int), np.array([], dtype=float)

    distance = max(1, int(min_peak_distance_points))
    if distance > 1 and len(locs) > 1:
        chosen: list[int] = []
        for idx in sorted(locs, key=lambda i: values[i], reverse=True):
            if all(abs(int(idx) - int(prev)) >= distance for prev in chosen):
                chosen.append(int(idx))
        locs = np.array(sorted(chosen), dtype=int)
    return locs, values[locs].astype(float)


def _interp_linear_extrapolate(
    x_new: np.ndarray,
    x_old: np.ndarray,
    y_old: np.ndarray,
) -> np.ndarray:
    if len(x_old) < 2:
        raise WakeFitError("Linear interpolation requires at least 2 wake samples.")
    y_new = np.interp(x_new, x_old, y_old)
    left = x_new < x_old[0]
    right = x_new > x_old[-1]
    if np.any(left):
        slope = (y_old[1] - y_old[0]) / (x_old[1] - x_old[0])
        y_new[left] = y_old[0] + slope * (x_new[left] - x_old[0])
    if np.any(right):
        slope = (y_old[-1] - y_old[-2]) / (x_old[-1] - x_old[-2])
        y_new[right] = y_old[-1] + slope * (x_new[right] - x_old[-1])
    return y_new


def _normalize_direction(direction: str) -> Direction:
    norm = str(direction).strip().lower()
    if norm not in ("longitudinal", "transverse"):
        raise WakeFitError(
            f"Unknown wake fitting direction {direction!r}; expected "
            "'longitudinal' or 'transverse'."
        )
    return norm  # type: ignore[return-value]


def _window_value_to_m(value: float, unit: str) -> float:
    unit_norm = str(unit).strip().lower()
    if unit_norm in ("m", "meter", "meters"):
        return float(value)
    if unit_norm in ("mm", "millimeter", "millimeters"):
        return float(value) * 1.0e-3
    if unit_norm in ("ns", "nanosecond", "nanoseconds"):
        return float(value) * 1.0e-9 * C_LIGHT_M_PER_S
    raise WakeFitError("fit_window units must be one of m, mm, or ns.")


def _as_1d_float(value: Any, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float).reshape(-1)
    if arr.size == 0:
        raise WakeFitError(f"{name} must not be empty.")
    if not np.all(np.isfinite(arr)):
        raise WakeFitError(f"{name} contains non-finite values.")
    return arr


def _as_1d_magnitude(value: Any, name: str) -> np.ndarray:
    arr = np.asarray(value).reshape(-1)
    if arr.size == 0:
        raise WakeFitError(f"{name} must not be empty.")
    if np.issubdtype(arr.dtype, np.complexfloating):
        out = np.abs(arr)
    else:
        out = np.asarray(arr, dtype=float)
    if not np.all(np.isfinite(out)):
        raise WakeFitError(f"{name} contains non-finite values.")
    return out


def _get_any(
    config: dict[str, Any],
    *names: str,
    default: Any = None,
) -> Any:
    for name in names:
        if name in config:
            return config[name]
    return default


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _required_float(config: dict[str, Any], name: str) -> float:
    value = config.get(name)
    if value is None:
        raise WakeFitError(f"pso_fit.{name} is required.")
    out = float(value)
    if not np.isfinite(out):
        raise WakeFitError(f"pso_fit.{name} must be finite.")
    return out


def _get_bound_value(config: dict[str, Any], canonical: str) -> Any:
    aliases = {
        "amplitude_min": ("amplitude_min", "A_min", "a_min"),
        "amplitude_max": ("amplitude_max", "A_max", "a_max"),
        "q_min": ("q_min", "Q_min"),
        "q_max": ("q_max", "Q_max"),
    }[canonical]
    return _get_any(config, *aliases, default=None)


def _expand_bound(value: Any, n_modes: int, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float).reshape(-1)
    if arr.size == 1:
        arr = np.full(n_modes, float(arr[0]))
    if arr.size != n_modes:
        raise WakeFitError(
            f"PSO bound {name!r} must be scalar or length {n_modes}; "
            f"got length {arr.size}."
        )
    if not np.all(np.isfinite(arr)):
        raise WakeFitError(f"PSO bound {name!r} contains non-finite values.")
    return arr
