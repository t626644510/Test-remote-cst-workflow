"""Wakefield impedance physics — beam model, 1D curve reading, scalarization.

All functions are **pure**: no CST dependency at runtime; they operate on
``np.ndarray`` inputs.  This makes them independently unit-testable with
synthetic impedance curves.

CST tree paths (user-confirmed)::

    1D Results\\Particle Beams\\{beam_name}\\Wake impedance\\X
    1D Results\\Particle Beams\\{beam_name}\\Wake impedance\\Y
    1D Results\\Particle Beams\\{beam_name}\\Wake impedance\\Z
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

_logger = logging.getLogger(__name__)

from ..core.results import ResultReader

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class ParticleBeam:
    """One particle beam in the wakefield simulation.

    Attributes
    ----------
    name : str
        CST beam name (e.g. ``"ParticleBeam1"``).
    offset_x_mm : float
        Horizontal offset in mm (0 = on-axis).
    offset_y_mm : float
        Vertical offset in mm (0 = on-axis).
    is_reference : bool
        ``True`` for the on-axis reference beam used in transverse
        impedance subtraction.
    """

    name: str = ""
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    is_reference: bool = False

    @property
    def offset_distance_mm(self) -> float:
        """Euclidean offset distance in mm — sqrt(dx² + dy²)."""
        return float(np.sqrt(self.offset_x_mm**2 + self.offset_y_mm**2))


@dataclass
class WakeImpedanceData:
    """One wakefield impedance curve extracted from a CST 1D result.

    Attributes
    ----------
    frequencies : np.ndarray
        Frequency points in **Hz** (converted from CST's GHz axis).
    impedance : np.ndarray
        Impedance magnitude at each frequency:
        - Longitudinal: **Ω**  (Z_‖)
        - Transverse:   **Ω/m** (Z_⊥ / offset)
    direction : str
        ``"x"``, ``"y"``, or ``"z"``.
    beam_offset : float
        Transverse beam offset in **mm** (0.0 for longitudinal / on-axis).
    impedance_type : str
        ``"longitudinal"`` or ``"transverse"``.
    label : str
        Human-readable identifier (e.g. ``"Z_long_on_axis"``).
    beam_name : str
        CST particle beam name this curve was read from.
    """

    frequencies: np.ndarray
    impedance: np.ndarray
    direction: str = "z"
    beam_offset: float = 0.0
    impedance_type: str = "longitudinal"
    label: str = ""
    beam_name: str = ""

    def __post_init__(self) -> None:
        if len(self.frequencies) != len(self.impedance):
            raise ValueError(
                f"Length mismatch: frequencies ({len(self.frequencies)}) vs "
                f"impedance ({len(self.impedance)})"
            )
        if len(self.frequencies) < 2:
            raise ValueError("Need at least 2 frequency points")

    @property
    def frequency_span_hz(self) -> float:
        """Frequency range covered by this curve (Hz)."""
        return float(self.frequencies[-1] - self.frequencies[0])


@dataclass
class BeamImpedanceSet:
    """All three wake impedance components for one particle beam.

    Attributes
    ----------
    beam : ParticleBeam
        The beam definition.
    z_long : WakeImpedanceData or None
        Longitudinal (Z-direction) impedance curve.
    z_x : WakeImpedanceData or None
        X-direction transverse impedance curve.
    z_y : WakeImpedanceData or None
        Y-direction transverse impedance curve.
    """

    beam: ParticleBeam
    z_long: WakeImpedanceData | None = None
    z_x: WakeImpedanceData | None = None
    z_y: WakeImpedanceData | None = None


# ---------------------------------------------------------------------------
# CST 1D result reading
# ---------------------------------------------------------------------------

# Template for the wakefield tree path
_TREEPATH_WAKE_TEMPLATE = (
    r"1D Results\Particle Beams\{beam_name}\Wake impedance\{direction}"
)

_FREQ_UNIT_MAP: dict[str, float] = {
    "hz": 1.0,
    "khz": 1.0e3,
    "mhz": 1.0e6,
    "ghz": 1.0e9,
    "thz": 1.0e12,
}


def _freq_to_hz(xdata: object, reader: ResultReader, tree_path: str) -> "np.ndarray":
    """Convert CST frequency-axis data to Hz using the xlabel unit.

    The CST ``ResultItem.xlabel`` contains the unit string
    (e.g. ``"Frequency / MHz"``).  We parse it and apply the
    appropriate multiplier.
    """
    import re
    import numpy as np

    arr = np.asarray(xdata, dtype=float)
    try:
        item = reader.get_result_item(tree_path)
        xlabel = getattr(item, "xlabel", "") or ""
    except Exception:
        xlabel = ""

    # Extract unit token after the last "/"
    if "/" in xlabel:
        unit_candidate = xlabel.rsplit("/", 1)[-1].strip()
    else:
        unit_candidate = ""

    multiplier = _FREQ_UNIT_MAP.get(unit_candidate.lower(), 1.0)
    if multiplier == 1.0 and unit_candidate:
        # Unknown unit — log a warning and return unchanged
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(
            "Unrecognised frequency unit '%s' in xlabel '%s' — "
            "assuming Hz (multiplier=1)",
            unit_candidate, xlabel,
        )

    return arr * multiplier


def _make_wake_tree_path(beam_name: str, direction: str) -> str:
    """Build CST tree path for a beam's wake impedance in a given direction.

    Parameters
    ----------
    beam_name : str
        e.g. ``"ParticleBeam1"``.
    direction : str
        ``"X"``, ``"Y"``, or ``"Z"``.

    Returns
    -------
    str
    """
    return _TREEPATH_WAKE_TEMPLATE.format(
        beam_name=beam_name, direction=direction.upper()
    )


def read_wakefield_curve(
    reader: ResultReader,
    tree_path: str = "",
    beam_name: str = "",
    direction: str = "z",
    impedance_type: str = "longitudinal",
    beam_offset: float = 0.0,
    label: str = "",
    run_id: int = 0,
) -> WakeImpedanceData:
    """Read one wakefield impedance curve from a CST 1D result.

    Parameters
    ----------
    reader : ResultReader
        Initialised reader pointing at the correct project file.
    tree_path : str
        Explicit navigation tree path.  If empty, built from
        *beam_name* + *direction* via the standard wakefield template.
    beam_name : str
        CST particle beam name.  Only used when *tree_path* is empty.
    direction : str
        ``"x"``, ``"y"``, or ``"z"``.
    impedance_type : str
        ``"longitudinal"`` or ``"transverse"``.
    beam_offset : float
        Transverse beam offset in mm.
    label : str
        Optional label for identification.
    run_id : int
        Parametric run ID (default 0).

    Returns
    -------
    WakeImpedanceData
    """
    if not tree_path:
        tree_path = _make_wake_tree_path(beam_name, direction)

    xdata, ydata = reader.get_1d_result(tree_path, run_id=run_id)

    # Auto-detect frequency unit from CST xlabel ("Frequency / MHz" etc.)
    freqs_hz = _freq_to_hz(xdata, reader, tree_path)

    # Wake impedance is complex-valued (Z = R + jX).
    # Take magnitude |Z| = √(R² + X²) before casting to float.
    if np.issubdtype(np.asarray(ydata).dtype, np.complexfloating):
        imp = np.abs(np.asarray(ydata))
    else:
        imp = np.asarray(ydata, dtype=float)

    return WakeImpedanceData(
        frequencies=freqs_hz,
        impedance=imp,
        direction=direction.lower(),
        beam_offset=beam_offset,
        impedance_type=impedance_type,
        label=label or f"Z_{direction}_{beam_name or '?'}",
        beam_name=beam_name,
    )


def read_beam_impedance(
    reader: ResultReader,
    beam: ParticleBeam,
    run_id: int = 0,
) -> BeamImpedanceSet:
    """Read X, Y, Z wake impedance curves for one particle beam.

    Parameters
    ----------
    reader : ResultReader
    beam : ParticleBeam
    run_id : int

    Returns
    -------
    BeamImpedanceSet
    """
    imp_type_long = "longitudinal"
    imp_type_trans = "transverse"

    z_long = read_wakefield_curve(
        reader, beam_name=beam.name, direction="z",
        impedance_type=imp_type_long, beam_offset=0.0,
        label=f"Z_long_{beam.name}", run_id=run_id,
    )

    # X/Y transverse wake impedance: CST may not store these for on-axis
    # beams (zero by symmetry).  Fall back to a zero-filled array matching
    # the Z frequency grid so the finite-difference transverse computation
    # can still proceed.
    def _read_or_zero(direction: str, label: str) -> WakeImpedanceData:
        try:
            return read_wakefield_curve(
                reader, beam_name=beam.name, direction=direction,
                impedance_type=imp_type_trans,
                beam_offset=beam.offset_distance_mm,
                label=label, run_id=run_id,
            )
        except Exception:
            if beam.offset_distance_mm < 1e-6:
                _logger.debug(
                    "No %s wake data for on-axis beam '%s' — using zeros",
                    direction, beam.name,
                )
                return WakeImpedanceData(
                    frequencies=z_long.frequencies.copy(),
                    impedance=np.zeros_like(z_long.frequencies),
                    direction=direction,
                    impedance_type=imp_type_trans,
                    beam_offset=0.0,
                    label=label,
                    beam_name=beam.name,
                )
            raise

    z_x = _read_or_zero("x", f"Z_x_{beam.name}")
    z_y = _read_or_zero("y", f"Z_y_{beam.name}")
    return BeamImpedanceSet(beam=beam, z_long=z_long, z_x=z_x, z_y=z_y)


# ---------------------------------------------------------------------------
# Transverse impedance — beam difference computation
# ---------------------------------------------------------------------------


def compute_transverse_impedance(
    ref: BeamImpedanceSet,
    offset: BeamImpedanceSet,
) -> WakeImpedanceData:
    """Compute transverse impedance from two beam-lines via finite difference.

    Derivation
    ----------
    The transverse impedance is the gradient of the longitudinal impedance
    w.r.t. transverse offset, approximated by the central finite difference:

        Z_⊥(f) ≈ |Z_offset(f) − Z_ref(f)| / d

    where *d* is the beam offset distance (mm).

    For each frequency point *f*::

        ΔX(f) = Z_x(offset, f) − Z_x(ref, f)
        ΔY(f) = Z_y(offset, f) − Z_y(ref, f)
        Z_trans(f) = √(ΔX² + ΔY²)  /  d      [Ω/m]

    The output is a ``WakeImpedanceData`` whose ``impedance`` array holds
    Z_trans(f) in **Ω/m** and ``impedance_type="transverse"``.

    Parameters
    ----------
    ref : BeamImpedanceSet
        On-axis reference beam (``is_reference=True``).
    offset : BeamImpedanceSet
        Offset beam (``is_reference=False``).

    Returns
    -------
    WakeImpedanceData
        Transverse impedance curve Z_⊥(f) in Ω/m.

    Raises
    ------
    ValueError
        If either beam is missing X or Y data, or the offset distance is zero.
    """
    if ref.z_x is None or offset.z_x is None:
        raise ValueError("Both beams must have X-direction impedance data")
    if ref.z_y is None or offset.z_y is None:
        raise ValueError("Both beams must have Y-direction impedance data")

    distance_mm = offset.beam.offset_distance_mm
    if distance_mm <= 0.0:
        raise ValueError(
            f"Offset beam '{offset.beam.name}' has zero offset distance; "
            f"cannot compute transverse impedance"
        )

    # Verify frequency grids match
    if not np.allclose(ref.z_x.frequencies, offset.z_x.frequencies, rtol=1e-6):
        raise ValueError(
            "Frequency grids of reference and offset beams do not match"
        )

    freqs = ref.z_x.frequencies.copy()

    delta_x = offset.z_x.impedance - ref.z_x.impedance
    delta_y = offset.z_y.impedance - ref.z_y.impedance

    # Z_trans = |ΔZ_vector| / d   [Ω/m]
    # d is in mm; convert to m for Ω/m output
    z_trans = np.sqrt(delta_x**2 + delta_y**2) / (distance_mm * 1e-3)

    return WakeImpedanceData(
        frequencies=freqs,
        impedance=z_trans,
        direction="transverse",
        beam_offset=distance_mm,
        impedance_type="transverse",
        label=f"Z_trans_{offset.beam.name}_wrt_{ref.beam.name}",
        beam_name=offset.beam.name,
    )


# ---------------------------------------------------------------------------
# Scalarization strategies
# ---------------------------------------------------------------------------

StrategyName = Literal[
    "threshold_exceedance_integral", "peak_exceedance", "composite"
]


def _apply_freq_mask(
    frequencies: np.ndarray,
    impedance: np.ndarray,
    freq_min_hz: float | None,
    freq_max_hz: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Slice frequency and impedance arrays to the requested range.

    Parameters
    ----------
    frequencies : np.ndarray
    impedance : np.ndarray
    freq_min_hz : float or None
        Lower bound (inclusive).  ``None`` → use ``frequencies[0]``.
    freq_max_hz : float or None
        Upper bound (inclusive).  ``None`` → use ``frequencies[-1]``.

    Returns
    -------
    f_masked : np.ndarray
    z_masked : np.ndarray
    """
    lo = freq_min_hz if freq_min_hz is not None else frequencies[0]
    hi = freq_max_hz if freq_max_hz is not None else frequencies[-1]

    mask = (frequencies >= lo) & (frequencies <= hi)
    if mask.sum() < 2:
        raise ValueError(
            f"Frequency mask [{lo:.3e}, {hi:.3e}] Hz contains fewer than "
            f"2 data points — cannot scalarize"
        )
    return frequencies[mask], impedance[mask]


def scalarize(
    frequencies: np.ndarray,
    impedance: np.ndarray,
    z_threshold: float,
    strategy: StrategyName = "threshold_exceedance_integral",
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
    freq_min_hz: float | None = None,
    freq_max_hz: float | None = None,
    normalize: bool = False,
    square_exceedance: bool = False,
) -> float:
    """Map a 1D impedance curve to a scalar exceedance metric.

    Parameters
    ----------
    frequencies : np.ndarray
        Frequency points in **Hz**.
    impedance : np.ndarray
        Impedance magnitude at each frequency (Ω or Ω/m).
    z_threshold : float
        Maximum allowed impedance in the same unit as *impedance*.
    strategy : str
        ``"threshold_exceedance_integral"``, ``"peak_exceedance"``,
        or ``"composite"``.
    weights : tuple[float, float, float]
        Only used for ``"composite"``.  Order: (w_integral, w_peak, w_margin).
    freq_min_hz : float or None
        Lower frequency bound for HOM filtering (e.g. ``550e6`` for 550 MHz).
        ``None`` → start of band.
    freq_max_hz : float or None
        Upper frequency bound.  ``None`` → end of band.

    Returns
    -------
    float
        Scalar exceedance metric.  0.0 means the entire curve (within the
        selected frequency band) is at or below *z_threshold*.
    """
    _validate_inputs(frequencies, impedance)

    f, z = _apply_freq_mask(frequencies, impedance, freq_min_hz, freq_max_hz)

    if strategy == "threshold_exceedance_integral":
        return _scalarize_integral(f, z, z_threshold, normalize=normalize, square_exceedance=square_exceedance)
    elif strategy == "peak_exceedance":
        return _scalarize_peak(z, z_threshold)
    elif strategy == "composite":
        return _scalarize_composite(f, z, z_threshold, weights, normalize=normalize)
    else:
        raise ValueError(
            f"Unknown strategy '{strategy}'.  "
            f"Available: threshold_exceedance_integral, peak_exceedance, composite"
        )


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


def _scalarize_integral(
    frequencies: np.ndarray,
    impedance: np.ndarray,
    z_threshold: float,
    normalize: bool = False,
    square_exceedance: bool = False,
) -> float:
    """Threshold-exceedance integral — ∫ max(0, Z(f) - Z_th) df.

    Unit: Ω·Hz (longitudinal) or Ω/m·Hz (transverse).

    If *square_exceedance* is True, use ∫ max(0, Z-Z_th)²/Z_th df.
    This heavily penalises single-point peaks.

    If *normalize* is True, divide by ``z_threshold × frequency_span``
    to produce a dimensionless value in [0, ~1] range.
    """
    exceedance = np.maximum(0.0, impedance - z_threshold)
    if square_exceedance and z_threshold > 0:
        exceedance = exceedance ** 2 / z_threshold
    integral = float(np.trapezoid(exceedance, frequencies))
    if normalize:
        freq_span = frequencies[-1] - frequencies[0]
        if freq_span > 0 and z_threshold > 0:
            integral = integral / (z_threshold * freq_span)
    return integral


def _scalarize_peak(
    impedance: np.ndarray,
    z_threshold: float,
) -> float:
    """Peak exceedance — max(0, max_f Z(f) - Z_th).

    Unit: Ω or Ω/m (same as impedance).
    """
    return float(np.maximum(0.0, np.max(impedance) - z_threshold))


def _scalarize_composite(
    frequencies: np.ndarray,
    impedance: np.ndarray,
    z_threshold: float,
    weights: tuple[float, float, float],
    normalize: bool = False,
) -> float:
    """Composite scalarization — normalised weighted combination.

    .. math::

        S = w_I·I_norm + w_P·P_norm + w_M·M

    All components are dimensionless — the integral and peak are normalised
    by *z_threshold* and the frequency span.
    """
    w_i, w_p, w_m = weights

    integral = _scalarize_integral(frequencies, impedance, z_threshold)
    freq_span = frequencies[-1] - frequencies[0]
    i_norm = integral / (z_threshold * freq_span) if freq_span > 0 else 0.0

    p_norm = _scalarize_peak(impedance, z_threshold) / z_threshold

    n_violations = int(np.sum(impedance > z_threshold))
    margin = n_violations / len(impedance)

    return float(w_i * i_norm + w_p * p_norm + w_m * margin)


# ---------------------------------------------------------------------------
# Multi-beam aggregation
# ---------------------------------------------------------------------------


AggregationMode = Literal["worst_case", "rms", "mean"]


def aggregate_over_beams(
    scalar_values: list[float],
    mode: AggregationMode = "worst_case",
) -> float:
    """Aggregate scalar exceedance values from multiple offset beams.

    Parameters
    ----------
    scalar_values : list[float]
        One scalarized value per offset beam.
    mode : str
        ``"worst_case"`` — max(values)
        ``"rms"``       — sqrt(mean(values²))
        ``"mean"``      — arithmetic mean

    Returns
    -------
    float
        Aggregated scalar.
    """
    if not scalar_values:
        return 0.0

    if mode == "worst_case":
        return float(np.max(scalar_values))
    elif mode == "rms":
        return float(np.sqrt(np.mean(np.array(scalar_values) ** 2)))
    elif mode == "mean":
        return float(np.mean(scalar_values))
    else:
        raise ValueError(
            f"Unknown aggregation mode '{mode}'.  "
            f"Choose 'worst_case', 'rms', or 'mean'."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_inputs(frequencies: np.ndarray, impedance: np.ndarray) -> None:
    """Internal parameter validation."""
    frequencies = np.asarray(frequencies, dtype=float)
    impedance = np.asarray(impedance, dtype=float)
    if frequencies.ndim != 1 or impedance.ndim != 1:
        raise ValueError("frequencies and impedance must be 1-D arrays")
    if len(frequencies) != len(impedance):
        raise ValueError(
            f"Length mismatch: {len(frequencies)} vs {len(impedance)}"
        )
    if len(frequencies) < 2:
        raise ValueError("Need at least 2 frequency points")
