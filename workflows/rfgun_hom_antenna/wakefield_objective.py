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

from cst_optimization.objectives.base import ObjectiveFunction
from cst_optimization.objectives.registry import register_objective
from cst_optimization.physics.wakefield import (
    ParticleBeam,
    WakeImpedanceData,
    read_beam_impedance,
    compute_transverse_impedance,
    scalarize,
    aggregate_over_beams,
    StrategyName,
    AggregationMode,
)

_logger = logging.getLogger(__name__)


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
        - ``quadratic_peak_barrier``      -> dimensionless

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
        peak_barrier_scale_ohm: float | None = None,
        peak_barrier_scale: float | None = None,
        integral_weight: float = 0.0,
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
        scale = peak_barrier_scale_ohm
        if scale is None:
            scale = peak_barrier_scale
        self._peak_barrier_scale = float(scale) if scale is not None else None
        self._integral_weight = float(integral_weight)

    def raw_value(self) -> float:
        reader = self._reader_factory()

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
                peak_barrier_scale=self._peak_barrier_scale,
                integral_weight=self._integral_weight,
            )
        )


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
        - ``quadratic_peak_barrier``      -> dimensionless

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
        peak_barrier_scale_ohm_per_m: float | None = None,
        peak_barrier_scale: float | None = None,
        integral_weight: float = 0.0,
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
        scale = peak_barrier_scale_ohm_per_m
        if scale is None:
            scale = peak_barrier_scale
        self._peak_barrier_scale = float(scale) if scale is not None else None
        self._integral_weight = float(integral_weight)
        self._ref_reader_factory = ref_reader_factory

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
                peak_barrier_scale=self._peak_barrier_scale,
                integral_weight=self._integral_weight,
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
