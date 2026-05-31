"""Accelerator-cavity physics quantities.

Each class implements a single derived observable computed from raw CST
results.  All mathematics and unit handling stay in Python — no CST
post-processing templates are required for new quantities.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from .formulas import (
    coupling_beta,
    half_power_bandwidth,
    intrinsic_q0,
    loaded_q_from_bandwidth,
    power_scaling,
)
from .quantities import PhysicsQuantity
from ..core.results import ResultBundle
from ..utils.units import MW, MV_per_m

_FREQ_UNIT_MAP: dict[str, float] = {
    "hz": 1.0, "khz": 1.0e3, "mhz": 1.0e6, "ghz": 1.0e9, "thz": 1.0e12,
}


def _freq_multiplier_from_xlabel(xlabel: str) -> float:
    """Parse a CST xlabel like ``\"Frequency / MHz\"`` → return Hz multiplier."""
    if "/" in xlabel:
        unit = xlabel.rsplit("/", 1)[-1].strip().lower()
        return _FREQ_UNIT_MAP.get(unit, 1.0)
    return 1.0


class ResonantFrequency(PhysicsQuantity):
    """Resonant frequency f0 determined from the |S11| minimum.

    .. math::

        f_0 = \\arg\\min_f |S_{11}(f)|

    Unit: Hz
    """

    name: ClassVar[str] = "f_res"
    unit: ClassVar[str] = "Hz"
    description: ClassVar[str] = "Resonant frequency from S11 minimum"

    def compute(self, bundle: ResultBundle) -> float:
        s11 = bundle.s_parameters.get("S1,1")
        if s11 is None:
            raise KeyError("S1,1 not found in ResultBundle")
        mag = np.abs(s11.s_complex)
        idx = int(np.argmin(mag))
        # Auto-detect frequency unit from CST xlabel ("Frequency / MHz" etc.)
        return float(s11.frequencies[idx]) * _freq_multiplier_from_xlabel(s11.xlabel)


class LoadedQ(PhysicsQuantity):
    """Loaded quality factor QL from the half-power (-3 dB) bandwidth.

    .. math::

        Q_L = \\frac{f_0}{\\Delta f_{-3\\,\\text{dB}}}

    where the -3 dB points are determined relative to |S11| at resonance
    using cubic-spline interpolation and Brent root-finding.

    Unit: dimensionless
    """

    name: ClassVar[str] = "q_loaded"
    unit: ClassVar[str] = "dimensionless"
    description: ClassVar[str] = "Loaded Q from half-power bandwidth"

    def compute(self, bundle: ResultBundle) -> float:
        s11 = bundle.s_parameters.get("S1,1")
        if s11 is None:
            raise KeyError("S1,1 not found in ResultBundle")

        mag = np.abs(s11.s_complex)
        f0, f1, f2, _ = half_power_bandwidth(s11.frequencies, mag)
        return loaded_q_from_bandwidth(f0, f1, f2)


class CouplingBeta(PhysicsQuantity):
    """Input coupling parameter Beta.

    .. math::

        \\beta = \\frac{1 + |S_{11}|}{1 - |S_{11}|}
        \\qquad (\\text{over-coupled})

    Unit: dimensionless
    """

    name: ClassVar[str] = "beta"
    unit: ClassVar[str] = "dimensionless"
    description: ClassVar[str] = "Input coupling parameter (over-coupled)"

    def compute(self, bundle: ResultBundle) -> float:
        s11 = bundle.s_parameters.get("S1,1")
        if s11 is None:
            raise KeyError("S1,1 not found in ResultBundle")
        _, _, _, gamma_min = half_power_bandwidth(
            s11.frequencies, np.abs(s11.s_complex)
        )
        return coupling_beta(gamma_min, over_coupled=True)


class IntrinsicQ(PhysicsQuantity):
    """Unloaded (intrinsic) quality factor Q0.

    .. math::

        Q_0 = Q_L (1 + \\beta)

    Unit: dimensionless
    """

    name: ClassVar[str] = "q0"
    unit: ClassVar[str] = "dimensionless"
    description: ClassVar[str] = "Intrinsic (unloaded) quality factor"

    def compute(self, bundle: ResultBundle) -> float:
        s11 = bundle.s_parameters.get("S1,1")
        if s11 is None:
            raise KeyError("S1,1 not found in ResultBundle")

        mag = np.abs(s11.s_complex)
        f0, f1, f2, gamma_min = half_power_bandwidth(s11.frequencies, mag)
        ql = loaded_q_from_bandwidth(f0, f1, f2)
        beta = coupling_beta(gamma_min, over_coupled=True)
        return intrinsic_q0(ql, beta)


class MinS11(PhysicsQuantity):
    """Minimum |S11| at resonance (linear magnitude).

    Unit: dimensionless
    """

    name: ClassVar[str] = "s11_min"
    unit: ClassVar[str] = "dimensionless"
    description: ClassVar[str] = "Minimum |S11| at resonance"

    def compute(self, bundle: ResultBundle) -> float:
        s11 = bundle.s_parameters.get("S1,1")
        if s11 is None:
            raise KeyError("S1,1 not found in ResultBundle")
        mag = np.abs(s11.s_complex)
        _, _, _, gamma_min = half_power_bandwidth(s11.frequencies, mag)
        return gamma_min


class PeakSurfaceField(PhysicsQuantity):
    """Peak surface electric field from the ``MaxE_Z0`` 0D result.

    The CST result is assumed to be normalised to 1 W input power.
    If the simulation used a different excitation the caller must
    scale accordingly before passing the value into the bundle.

    Unit: V/m
    """

    name: ClassVar[str] = "e_peak"
    unit: ClassVar[str] = "V/m"
    description: ClassVar[str] = "Peak surface electric field"

    def compute(self, bundle: ResultBundle) -> float:
        scalar = bundle.scalars.get("MaxE_Z0")
        if scalar is None:
            # Try alternate key
            for key in bundle.scalars:
                if "MaxE" in key or "E_Z0" in key:
                    scalar = bundle.scalars[key]
                    break
        if scalar is None:
            raise KeyError("MaxE_Z0 not found in ResultBundle")
        # CST typically outputs these in V/m already
        return float(scalar.value)


class InputPower(PhysicsQuantity):
    """Required input power to reach a target accelerating gradient.

    Derivation
    ----------
    Given the peak field E_sim at P_in = 1 W (CST default) and a target
    accelerating gradient E_acc_target::

        K = E_acc_target / E_sim
        P_in_target = P_in_sim * K²

    Unit: W
    """

    name: ClassVar[str] = "p_input"
    unit: ClassVar[str] = "W"
    description: ClassVar[str] = "Input power for target gradient"

    _target_e_acc: float = 200.0 * MV_per_m  # 200 MV/m default

    def __init__(self, target_e_acc_vm: float = 200.0 * MV_per_m) -> None:
        self._target_e_acc = float(target_e_acc_vm)

    def compute(self, bundle: ResultBundle) -> float:
        e_peak = PeakSurfaceField().compute(bundle)
        _, p_scale = power_scaling(e_peak, self._target_e_acc, p_in_sim=1.0)
        return 1.0 * p_scale  # W


class ReflectedPower(PhysicsQuantity):
    """Reflected power at the target accelerating gradient.

    .. math::

        P_{\\text{ref}} = P_{\\text{in}} \\cdot |S_{11}|^2

    Unit: W
    """

    name: ClassVar[str] = "p_reflected"
    unit: ClassVar[str] = "W"
    description: ClassVar[str] = "Reflected power at target gradient"

    _target_e_acc: float = 200.0 * MV_per_m

    def __init__(self, target_e_acc_vm: float = 200.0 * MV_per_m) -> None:
        self._target_e_acc = float(target_e_acc_vm)

    def compute(self, bundle: ResultBundle) -> float:
        s11 = bundle.s_parameters.get("S1,1")
        e_peak = PeakSurfaceField().compute(bundle)

        mag = np.abs(s11.s_complex)
        _, _, _, gamma_min = half_power_bandwidth(s11.frequencies, mag)

        _, p_scale = power_scaling(e_peak, self._target_e_acc, p_in_sim=1.0)
        p_in_target = 1.0 * p_scale
        return p_in_target * (gamma_min**2)
