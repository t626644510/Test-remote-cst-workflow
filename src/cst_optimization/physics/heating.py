"""Pulsed heating calculation for SRF cavities.

The temperature rise :math:`\\Delta T` on the cavity surface during a
single RF pulse is a critical limit for superconducting cavities — too
high a :math:`\\Delta T` can trigger a quench.

Physics
-------
For a semi-infinite solid with constant surface heat flux *q''*, the
surface temperature rise after time *τ* is::

    ΔT = 2 · q'' · √τ / √(π · ρ · c · κ)

The surface heat flux is driven by the peak magnetic field at the surface::

    q'' = ½ · R_s · |H_peak|²

where *R_s* is the RF surface resistance (anomalous skin effect at
cryogenic temperatures)::

    R_s = √(π · f · μ₀ / σ)

    σ_77K = σ_300K · RRR        (conductivity at operating temperature)

The H-field scales linearly with the applied accelerating gradient
(``E ∝ H ∝ √P``), so for a target gradient *E_target*::

    H_target = H_sim · (E_target / E_sim)

Combining everything::

    ΔT = H_sim² · (E_target / E_sim)² · √τ · R_s / √(π · ρ · c · κ)

Reference
---------
This formula follows the standard 1D transient heat-conduction solution
for pulsed RF heating (see e.g. Padamsee, "RF Superconductivity for
Accelerators", Ch. 10).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ── Physical constants ─────────────────────────────────────────────────

MU_0: float = np.pi * 4e-7          # vacuum permeability (H/m)

# Copper properties at cryogenic temperature (~ 77 K)
# (values from the original DeltaT.m — typical for OFHC copper)
CU_DENSITY: float = 8960.0           # ρ — density (kg/m³)
CU_HEAT_CAPACITY: float = 188.0      # c — specific heat (J/(kg·K))
CU_THERMAL_CONDUCTIVITY: float = 547.0  # κ — thermal conductivity (W/(m·K))
CU_CONDUCTIVITY_300K: float = 5.8e7  # σ at 300 K (S/m)


# ── Computation ────────────────────────────────────────────────────────


def surface_resistance(
    frequency_hz: float,
    conductivity_sm: float,
) -> float:
    """Compute RF surface resistance (anomalous skin effect regime).

    .. math::

        R_s = \\sqrt{\\frac{\\pi \\cdot f \\cdot \\mu_0}{\\sigma}}

    Parameters
    ----------
    frequency_hz : float
        RF frequency in Hz (e.g. 11.424e9).
    conductivity_sm : float
        Electrical conductivity in S/m at the operating temperature.

    Returns
    -------
    float
        Surface resistance in Ω.
    """
    return float(np.sqrt(np.pi * frequency_hz * MU_0 / conductivity_sm))


def pulsed_heating_delta_t(
    h_peak_sim: float,
    e_peak_sim: float,
    e_target: float = 200e6,
    pulse_width_ns: float = 300.0,
    frequency_hz: float = 11.424e9,
    rrr: float = 5.5,
) -> float:
    """Compute pulsed-heating temperature rise for one RF pulse.

    Derivation
    ----------
    .. math::

        \\Delta T = \\frac{H_{sim}^2 \\cdot (E_{target} / E_{sim})^2
                       \\cdot \\sqrt{\\tau} \\cdot R_s}
                       {\\sqrt{\\pi \\cdot \\rho \\cdot c \\cdot \\kappa}}

    where *H_sim* and *E_sim* are the peak fields extracted from the
    simulation, and *E_target* is the desired operating gradient.

    Parameters
    ----------
    h_peak_sim : float
        Peak |H| from simulation (A/m).  Typically the maximum across
        all surfaces, especially the cathode region.
    e_peak_sim : float
        Peak |E| from simulation (V/m), at the same excitation level.
    e_target : float
        Target accelerating gradient (V/m).  Default 200 MV/m.
    pulse_width_ns : float
        RF pulse duration in ns.  Default 300 ns.
    frequency_hz : float
        RF frequency in Hz.  Default 11.424 GHz.
    rrr : float
        Residual Resistivity Ratio.  Default 5.5.
        Conductivity at operating temperature = σ_300K × RRR.

    Returns
    -------
    float
        Temperature rise ΔT in K.
    """
    # Conductivity at operating temperature
    sigma_op = CU_CONDUCTIVITY_300K * rrr

    # Surface resistance
    rs = surface_resistance(frequency_hz, sigma_op)

    # Field scaling to reach target gradient
    scale = e_target / e_peak_sim

    # Pulsed heating
    tau_s = pulse_width_ns * 1e-9  # ns → s
    denom = np.sqrt(np.pi * CU_DENSITY * CU_HEAT_CAPACITY * CU_THERMAL_CONDUCTIVITY)

    delta_t = (h_peak_sim * scale) ** 2 * np.sqrt(tau_s) * rs / denom

    return float(delta_t)


def max_h_from_field_file(h_field_file: str) -> float:
    """Extract the peak |H| magnitude from a CST H-field export file.

    Parameters
    ----------
    h_field_file : str
        Path to the H-field ASCII export (9-column format).

    Returns
    -------
    float
        Maximum |H| (A/m) across all field sample points.
    """
    from .poynting import parse_cst_field_export

    h_data = parse_cst_field_export(h_field_file)
    # Columns: 0=x, 1=y, 2=z, 3=HxRe, 4=HxIm, 5=HyRe, 6=HyIm, 7=HzRe, 8=HzIm
    h_mag = np.sqrt(
        h_data[:, 3] ** 2 + h_data[:, 4] ** 2
        + h_data[:, 5] ** 2 + h_data[:, 6] ** 2
        + h_data[:, 7] ** 2 + h_data[:, 8] ** 2
    )
    return float(np.max(h_mag))
