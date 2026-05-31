"""Field-related optimisation objectives (peak E, E/E_acc, modified Poynting).

Each class only defines ``raw_value()`` — the optimisation strategy
(minimise / maximise / tolerance) is injected via ``mode`` at construction.
"""

from __future__ import annotations

import os
from typing import ClassVar

from .base import ObjectiveFunction
from .registry import register_objective
from ..core.results import ResultBundle
from ..physics.cavity import PeakSurfaceField
from ..physics.poynting import max_modified_poynting, discover_field_files
from ..physics.heating import pulsed_heating_delta_t, max_h_from_field_file


@register_objective
class PeakElectricField(ObjectiveFunction):
    """Peak surface electric field (MaxE_Z0).

    Raw value: V/m (normalised to 1 W input power by CST).
    Typical mode: ``minimize`` (suppress field emission).
    """

    name: ClassVar[str] = "peak_e_field"
    unit: ClassVar[str] = "V/m"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        raw = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
        bundle = ResultBundle(scalars={"MaxE_Z0": raw})
        return PeakSurfaceField().compute(bundle)


@register_objective
class PeakSurfaceFieldRatio(ObjectiveFunction):
    """Ratio of peak surface E to accelerating gradient, E_peak / E_acc.

    Lower ratio → better field distribution.
    Typical SRF values: 1.5–3.0.

    Raw value: dimensionless.
    Typical mode: ``minimize``.
    """

    name: ClassVar[str] = "e_peak_over_e_acc"
    unit: ClassVar[str] = "dimensionless"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        raw_e = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
        return float(raw_e.value)


@register_objective
class MaxModifiedPoynting(ObjectiveFunction):
    """Peak modified Poynting vector :math:`\\max S_c`.

    .. math::

        S_c = |\\Re(\\mathbf{S})| + g_c \\cdot |\\Im(\\mathbf{S})|

    where :math:`\\mathbf{S} = \\tfrac{1}{2} \\mathbf{E} \\times \\mathbf{H}^*`
    is the complex Poynting vector.

    Lower ``max(Sc)`` → lower RF breakdown risk.
    Typical *gc* values: 0.1–0.5 (default 0.125).

    Reads from **CST ASCII field exports** (E-field and H-field monitor
    data exported in 9-column format).  These exports must be configured
    in the CST project as a post-processing step (VBA ``ASCIIExport``).

    Parameters
    ----------
    reader_factory : callable
        (Unused — this objective reads field export files directly.)
    mode : OptimizationMode
    e_file : str
        Path to the E-field export file.
    h_file : str
        Path to the H-field export file.
    gc : float
        Reactive weighting factor (default 0.125).

    Raw value: W/m².
    Typical mode: ``minimize`` or ``less_than``.

    YAML Example
    ------------
    .. code-block:: yaml

        objectives:
          - name: max_modified_poynting
            mode: minimize
            obj_params:
              e_file: "D:/Results/E_field.txt"
              h_file: "D:/Results/H_field.txt"
              gc: 0.125
    """

    name: ClassVar[str] = "max_modified_poynting"
    unit: ClassVar[str] = "W/m^2"

    def __init__(
        self,
        reader_factory,
        mode=None,
        e_file: str = "",
        h_file: str = "",
        project_dir: str = "",
        gc: float = 0.125,
        e_target: float = 200e6,
        **kwargs,
    ) -> None:
        super().__init__(reader_factory, mode)
        self._e_file = str(e_file)
        self._h_file = str(h_file)
        self._project_dir = str(project_dir)
        self._gc = float(gc)
        self._e_target = float(e_target)

    def raw_value(self) -> float:
        e_file = self._e_file
        h_file = self._h_file

        # Auto-discovery from project export directory
        if (not e_file or not h_file) and self._project_dir:
            from ..physics.poynting import discover_field_files
            e_file, h_file = discover_field_files(self._project_dir)

        if not e_file or not h_file:
            raise ValueError(
                "Cannot locate field export files for MaxModifiedPoynting.  "
                "Either set e_file + h_file explicitly, or provide project_dir "
                "pointing to the unpacked CST project folder (whose Export/3d/ "
                "contains the field monitor ASCII exports)."
            )
        if not os.path.exists(e_file):
            raise FileNotFoundError(f"E-field export not found: {e_file}")
        if not os.path.exists(h_file):
            raise FileNotFoundError(f"H-field export not found: {h_file}")

        # --- Normalise to target gradient ---
        # CST simulates at 1 W input power; the field export values
        # correspond to whatever gradient that yields.  We scale to the
        # target operating gradient (200 MV/m default):
        #   E ∝ √P  ⇒  K = E_target / E_sim  ⇒  S_scaled = K² · S
        reader = self._reader_factory()
        e_sim = reader.get_scalar(reader.TREEPATH_MAX_E_Z0).value
        if e_sim <= 0:
            raise ValueError(f"MaxE_Z0 = {e_sim:.3e} — cannot compute field scale")
        field_scale = self._e_target / e_sim

        return max_modified_poynting(e_file, h_file, gc=self._gc, field_scale=field_scale)


@register_objective
class FieldFlatness(ObjectiveFunction):
    """Cell-to-cell field flatness for multi-cell cavities.

    .. math::

        f = 1 - \\frac{\\min(E_i)}{\\max(E_i)}

    where *E_i* are the peak surface fields of each cell (MaxE_Z0,
    MaxE_Z1, MaxE_Z2 from 0D post-processing templates).

    ======  ========  =======================
    f       E_min     Meaning
    ======  ========  =======================
    0.000   100%      Perfectly balanced
    0.025    97.5%    Acceptable (user spec)
    0.050    95.0%    Marginal
    0.100    90.0%    Poor
    ======  ========  =======================

    Raw value: dimensionless (0 = perfect).
    Typical mode: ``tolerance`` with ``{target: 0, sigma: 0.0085}``
    (3σ ≈ 2.56%, matching the 97.5% requirement).

    Reads ``MaxE_Z0``, ``MaxE_Z1``, ``MaxE_Z2`` from
    ``Tables\0D Results\`` — these must be set up as CST
    post-processing templates (one per cell).

    YAML Example
    ------------
    .. code-block:: yaml

        objectives:
          - name: field_flatness
            mode: tolerance
            mode_params:
              target: 0.0
              sigma: 0.0085     # 3σ ≈ 2.55%  (97.5% spec)
    """

    name: ClassVar[str] = "field_flatness"
    unit: ClassVar[str] = "dimensionless"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        e0 = reader.get_scalar(reader.TREEPATH_MAX_E_Z0).value
        e1 = reader.get_scalar(reader.TREEPATH_MAX_E_Z1).value
        e2 = reader.get_scalar(reader.TREEPATH_MAX_E_Z2).value

        e_max = max(e0, e1, e2)
        e_min = min(e0, e1, e2)

        if e_max <= 0:
            raise ValueError(
                f"All peak fields are zero or negative: "
                f"E0={e0:.3e}, E1={e1:.3e}, E2={e2:.3e}"
            )

        return 1.0 - e_min / e_max


@register_objective
class PulsedHeating(ObjectiveFunction):
    """Pulsed-heating temperature rise :math:`\\Delta T` on the cavity surface.

    .. math::

        \\Delta T = \\frac{H_{sim}^2 \\cdot (E_{target}/E_{sim})^2
                       \\cdot \\sqrt{\\tau} \\cdot R_s}
                       {\\sqrt{\\pi \\cdot \\rho \\cdot c \\cdot \\kappa}}

    where:

    - *H_sim* = peak |H| from the simulation (read from H-field export)
    - *E_sim* = peak |E| from the simulation (``MaxE_Z0`` 0D template)
    - *E_target* = target accelerating gradient
    - *τ* = RF pulse width
    - *Rs* = surface resistance (anomalous skin effect at cryo temp)

    Physical constants for OFHC copper at ~77 K are used.

    Lower ΔT → lower quench risk.

    Parameters
    ----------
    reader_factory : callable
    mode : OptimizationMode
    project_dir : str
        Path to the unpacked CST project directory (for H-field discovery).
    e_target : float
        Target accelerating gradient in V/m (default 200 MV/m).
    pulse_width_ns : float
        RF pulse width in ns (default 300 ns).
    frequency_hz : float
        RF frequency in Hz (default 11.424 GHz).
    rrr : float
        Residual Resistivity Ratio (default 5.5).

    Raw value: K.
    Typical mode: ``less_than`` or ``minimize``.

    YAML Example
    ------------
    .. code-block:: yaml

        objectives:
          - name: pulsed_heating
            mode: less_than
            mode_params: {threshold: 10.0, sigma: 2.0}
            obj_params: {project_dir: "D:/ModelData/...", pulse_width_ns: 300}
    """

    name: ClassVar[str] = "pulsed_heating"
    unit: ClassVar[str] = "K"

    def __init__(
        self,
        reader_factory,
        mode=None,
        project_dir: str = "",
        e_target: float = 200e6,
        pulse_width_ns: float = 300.0,
        frequency_hz: float = 11.424e9,
        rrr: float = 5.5,
        **kwargs,
    ) -> None:
        super().__init__(reader_factory, mode)
        self._project_dir = str(project_dir)
        self._e_target = float(e_target)
        self._pulse_width_ns = float(pulse_width_ns)
        self._frequency_hz = float(frequency_hz)
        self._rrr = float(rrr)

    def raw_value(self) -> float:
        # 1. E_peak from CST 0D template
        reader = self._reader_factory()
        e_peak_sim = reader.get_scalar(reader.TREEPATH_MAX_E_Z0).value

        # 2. H_peak from exported H-field file (auto-discovered)
        if not self._project_dir:
            raise ValueError(
                "project_dir must be set for PulsedHeating.  "
                "The H-field peak is read from the CST field export in "
                "<project_dir>/Export/3d/.  Pass it via obj_params in YAML."
            )
        _, h_file = discover_field_files(self._project_dir)
        if not h_file:
            raise FileNotFoundError(
                f"No H-field export found in {self._project_dir}/Export/3d/.  "
                f"Ensure the CST post-processing template exports the H-field monitor."
            )
        h_peak_sim = max_h_from_field_file(h_file)

        # 3. Compute ΔT
        return pulsed_heating_delta_t(
            h_peak_sim=h_peak_sim,
            e_peak_sim=e_peak_sim,
            e_target=self._e_target,
            pulse_width_ns=self._pulse_width_ns,
            frequency_hz=self._frequency_hz,
            rrr=self._rrr,
        )
