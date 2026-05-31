"""Antenna fundamental-mode absorption optimisation objectives.

Each class reads S-parameters at a specific HOM antenna port and computes
the absorption at the fundamental mode resonance peak.

Example YAML usage::

    objectives:
      - name: antenna1_absorption
        mode: less_than
        mode_params: {threshold: -30.0, sigma: 2.0}
        obj_params: {antenna_port: 2}
      - name: antenna2_absorption
        mode: less_than
        mode_params: {threshold: -30.0, sigma: 2.0}
        obj_params: {antenna_port: 3}
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from .base import ObjectiveFunction
from .registry import register_objective
from ..physics.formulas import half_power_bandwidth, resonance_from_dip


def _tree_path_for_port(port: int) -> str:
    """Return the CST S-parameter tree path for transmission from port 1.

    Reads the transmission S-parameter from the cavity input port (port 1)
    to the given antenna port.  Port 2 → ``"S2(1),1(2)"``, Port 3 → ``"S3(1),1(2)"``.
    """
    return f"1D Results\\S-Parameters\\S{port}(1),1(2)"


@register_objective
class AntennaAbsorptionObjective(ObjectiveFunction):
    """Fundamental-mode absorption at a HOM antenna port.

    Reads the transmission S-parameter S_{port},1 from the CST 1D results
    (cavity port 1 → antenna port *port*), finds the **maximum** |S|
    (transmission peak at the fundamental-mode frequency), and returns
    the absorption in **dB**:

    .. math::

        A = 20 \\cdot \\log_{10}(|S_{port,1}(f_{\\text{peak}})|)

    where *f_peak* is the frequency of the |S| maximum within the
    fundamental-mode search band.  Higher |S| = more fundamental-mode
    power leaking into the antenna = worse.

    More negative values mean **better** (less fundamental-mode power
    extracted by the HOM antenna).

    Typical mode: ``less_than`` with ``threshold=-30`` dB.
    Absorption ≤ -30 dB → penalty = 0.

    Parameters
    ----------
    reader_factory : callable
    mode : OptimizationMode
    antenna_port : int
        CST port number (≥ 1).  Default 2.
    search_freq_ghz : float or None
        Target fundamental-mode frequency for restricting the resonance
        search window.  If ``None`` (default), the global |S| minimum is
        used, which may pick up higher-order modes if the solver band is
        wide.  Set to your cavityʼs f0 (e.g. 0.5 for 500 MHz) to lock onto
        the correct dip.
    search_width_ghz : float
        Half-width of the search window around *search_freq_ghz*.
        Default 0.01 (10 MHz for a 500 MHz cavity).
    """

    name: ClassVar[str] = "antenna_absorption"
    unit: ClassVar[str] = "dB"

    def __init__(
        self,
        reader_factory,
        mode=None,
        antenna_port: int = 2,
        search_freq_ghz: float | None = None,
        search_width_ghz: float = 0.01,
        tree_path: str = "",
        **kwargs,
    ) -> None:
        super().__init__(reader_factory, mode)
        if antenna_port < 1:
            raise ValueError(f"antenna_port must be ≥ 1, got {antenna_port}")
        self._antenna_port = int(antenna_port)
        self._search_freq_ghz = search_freq_ghz
        self._search_width_ghz = float(search_width_ghz)
        self._tree_path = str(tree_path) if tree_path else _tree_path_for_port(self._antenna_port)

    def raw_value(self) -> float:
        """Return the transmission peak in dB (more negative = better).

        For transmission S-parameters (S_{port},1), the fundamental mode
        appears as a **peak** — we locate the maximum |S| within the
        search band, then convert to dB.

        Returns
        -------
        float
            Absorption in dB.  -30 dB = 0.1% power leakage into antenna.
        """
        reader = self._reader_factory()
        s_data = reader.get_s_parameter(tree_path=self._tree_path)

        mag = np.abs(s_data.s_complex)

        if self._search_freq_ghz is not None:
            f_target = self._search_freq_ghz
            half_w = self._search_width_ghz
            mask = np.abs(s_data.frequencies - f_target) <= half_w
            if mask.sum() < 3:
                # Fall back to global maximum if window is too narrow
                idx = int(np.argmax(mag))
            else:
                idx = int(np.argmax(mag[mask]))
                global_indices = np.where(mask)[0]
                idx = global_indices[idx]
        else:
            idx = int(np.argmax(mag))

        s_peak = float(mag[idx])

        # Absorption in dB: 20·log10(|S_peak|)
        # |S| → 0  ⇔  A → -∞  (no coupling to antenna)
        # |S| → 1  ⇔  A →  0  (full coupling, all power to antenna)
        if s_peak <= 0.0:
            return -300.0

        absorption_db = 20.0 * np.log10(s_peak)
        return float(absorption_db)


@register_objective
class AntennaAbsorptionDB(AntennaAbsorptionObjective):
    """Alias for ``AntennaAbsorptionObjective`` with a distinct registered name.

    Use when you need to distinguish multiple antenna ports in the same
    config (e.g. ``antenna1_db`` and ``antenna2_db``).
    """

    name: ClassVar[str] = "antenna_absorption_db"


@register_objective
class TransmissionAtResonance(ObjectiveFunction):
    """Transmission S-parameter at the resonant frequency, reported in dB.

    The resonant frequency is identified from ``S1,1`` first, then the
    corresponding transmission magnitude is read from ``S{port},1`` at
    the closest frequency sample (or within a narrow search window if
    requested).

    This is useful for constraints such as requiring ``S21(f0)`` to stay
    near a specified attenuation level.
    """

    name: ClassVar[str] = "s21_at_f0_db"
    unit: ClassVar[str] = "dB"

    def __init__(
        self,
        reader_factory,
        mode=None,
        transmission_port: int = 2,
        search_width_ghz: float = 0.01,
        tree_path: str = "",
        **kwargs,
    ) -> None:
        super().__init__(reader_factory, mode)
        if transmission_port < 1:
            raise ValueError(
                f"transmission_port must be >= 1, got {transmission_port}"
            )
        self._transmission_port = int(transmission_port)
        self._search_width_ghz = float(search_width_ghz)
        self._tree_path = str(tree_path) if tree_path else _tree_path_for_port(self._transmission_port)

    def raw_value(self) -> float:
        reader = self._reader_factory()

        s11 = reader.get_s_parameter(tree_path=reader.TREEPATH_S11)
        s21 = reader.get_s_parameter(tree_path=self._tree_path)

        try:
            f0, _, _, _ = half_power_bandwidth(
                s11.frequencies,
                np.abs(s11.s_complex),
            )
        except Exception:
            f0, _ = resonance_from_dip(
                s11.frequencies,
                np.abs(s11.s_complex),
            )

        mask = np.abs(s21.frequencies - f0) <= self._search_width_ghz
        if mask.sum() >= 1:
            local_mag = np.abs(s21.s_complex[mask])
            local_freqs = s21.frequencies[mask]
            idx_local = int(np.argmin(np.abs(local_freqs - f0)))
            s_mag = float(local_mag[idx_local])
        else:
            idx = int(np.argmin(np.abs(s21.frequencies - f0)))
            s_mag = float(np.abs(s21.s_complex[idx]))

        if s_mag <= 0.0:
            return -300.0

        return float(20.0 * np.log10(s_mag))
