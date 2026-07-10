# Gate utilities for the RF gun SAO workflow.
# Pure Python dataclasses: frequency gate, S11 depth gate, multi-dip detection.

from __future__ import annotations
import logging
from dataclasses import dataclass
import numpy as np

_logger = logging.getLogger(__name__)

@dataclass
class FrequencyGate:
    enabled: bool = False
    target_ghz: float = 11.424
    max_abs_offset_mhz: float = 20.0

    @property
    def max_abs_offset_ghz(self) -> float:
        return self.max_abs_offset_mhz / 1000.0

    def accepts(self, f0_ghz: float) -> bool:
        if not self.enabled:
            return True
        return abs(float(f0_ghz) - self.target_ghz) <= self.max_abs_offset_ghz

@dataclass
class S11DepthGate:
    enabled: bool = False
    threshold_db: float = -1.0

    def accepts(self, s11_min_db: float) -> bool:
        if not self.enabled:
            return True
        return float(s11_min_db) <= self.threshold_db

class MultiDipDetector:
    def __init__(self, enabled: bool = False, mode_spacing_ghz: float = 0.04) -> None:
        self.enabled = bool(enabled)
        self.mode_spacing_ghz = float(mode_spacing_ghz)

    def has_multiple_dips(self, frequencies_ghz, magnitude):
        if not self.enabled:
            return False
        if len(frequencies_ghz) < 5:
            return False
        try:
            from scipy.signal import find_peaks
            dip_indices, _ = find_peaks(-np.asarray(magnitude), prominence=0.01)
        except ImportError:
            mag_arr = np.asarray(magnitude)
            dip_indices = []
            for i in range(1, len(mag_arr) - 1):
                if mag_arr[i] < mag_arr[i - 1] and mag_arr[i] < mag_arr[i + 1]:
                    dip_indices.append(i)
            dip_indices = np.array(dip_indices) if dip_indices else np.array([])
        if len(dip_indices) < 2:
            return False
        dip_freqs = np.asarray(frequencies_ghz)[dip_indices]
        for i in range(len(dip_freqs)):
            for j in range(i + 1, len(dip_freqs)):
                if abs(dip_freqs[i] - dip_freqs[j]) <= self.mode_spacing_ghz:
                    return True
        return False
