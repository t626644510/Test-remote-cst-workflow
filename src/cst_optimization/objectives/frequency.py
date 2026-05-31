"""Frequency-related optimisation objectives.

Each class only defines ``raw_value()`` returning the physical quantity.
The optimisation strategy (tolerance, minimize, etc.) is injected as a
``mode`` at construction time.

Example YAML usage::

    objectives:
      - name: resonant_freq        # ← ResonantFreqObjective
        mode: tolerance            # ← GaussianTolerance
        mode_params:
          target: 11.424            # GHz
          sigma: 3.33               # MHz ≈ 10 MHz tolerance / 3
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from .base import ObjectiveFunction
from .registry import register_objective
from ..physics.formulas import half_power_bandwidth


@register_objective
class ResonantFreqObjective(ObjectiveFunction):
    """Resonant frequency f0 from the S11 minimum.

    Raw value: **GHz** (as returned by the CST frequency axis).
    Typical modes:

    - ``tolerance`` — Gaussian band around target (recommended for BO).
    - ``minimize`` — drive frequency as low as possible (rarely useful alone).

    Parameters
    ----------
    reader_factory : callable
    mode : OptimizationMode
        Penalty strategy (injected by config or code).
    """

    name: ClassVar[str] = "resonant_freq"
    unit: ClassVar[str] = "GHz"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        s11 = reader.get_s_parameter()
        mag = np.abs(s11.s_complex)
        # half_power_bandwidth returns f0 in the same unit as the CST
        # x-axis, which is typically GHz.
        f0_ghz, _, _, _ = half_power_bandwidth(s11.frequencies, mag)
        return float(f0_ghz)
