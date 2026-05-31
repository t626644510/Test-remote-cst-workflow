"""Unit conversion constants and utilities for accelerator cavity physics.

All quantities follow the SI base-unit convention internally.
Display-friendly conversions (GHz, MV/m, MW) are provided as functions
and constants.
"""

# Fundamental conversions
GHz: float = 1.0e9  # Hz per GHz
MV_per_m: float = 1.0e6  # V/m per MV/m
MW: float = 1.0e6  # W per MW
kV: float = 1.0e3  # V per kV
mA: float = 1.0e-3  # A per mA


def to_ghz(freq_hz: float) -> float:
    """Convert frequency from Hz to GHz.

    Parameters
    ----------
    freq_hz : float
        Frequency in Hz.

    Returns
    -------
    float
        Frequency in GHz (freq_hz / 1e9).
    """
    return freq_hz / GHz


def from_ghz(freq_ghz: float) -> float:
    """Convert frequency from GHz to Hz."""
    return freq_ghz * GHz


def to_mv_per_m(field_v_per_m: float) -> float:
    """Convert electric field from V/m to MV/m."""
    return field_v_per_m / MV_per_m


def from_mv_per_m(field_mv_per_m: float) -> float:
    """Convert electric field from MV/m to V/m."""
    return field_mv_per_m * MV_per_m


def to_mw(power_w: float) -> float:
    """Convert power from W to MW."""
    return power_w / MW


def from_mw(power_mw: float) -> float:
    """Convert power from MW to W."""
    return power_mw * MW
