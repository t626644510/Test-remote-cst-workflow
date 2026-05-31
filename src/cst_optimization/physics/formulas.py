"""Pure mathematical utilities for accelerator cavity physics.

Functions in this module have **no** CST dependency and are independently
testable with synthetic data.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import brentq


def resonance_from_dip(
    frequencies: np.ndarray,
    magnitude_response: np.ndarray,
    target_freq: float | None = None,
    search_width: float = 0.05,
) -> tuple[float, float]:
    """Return the resonance frequency from the dip minimum only."""
    frequencies = np.asarray(frequencies, dtype=float)
    magnitude_response = np.asarray(magnitude_response, dtype=float)
    if frequencies.size == 0 or magnitude_response.size == 0:
        raise ValueError("Empty resonance data")
    if frequencies.size != magnitude_response.size:
        raise ValueError("Frequency and magnitude arrays must have the same size")

    if target_freq is not None:
        mask = np.abs(frequencies - target_freq) <= float(search_width)
        if np.any(mask):
            local_idx = int(np.argmin(magnitude_response[mask]))
            global_indices = np.where(mask)[0]
            idx = int(global_indices[local_idx])
            return float(frequencies[idx]), float(magnitude_response[idx])

    idx = int(np.argmin(magnitude_response))
    return float(frequencies[idx]), float(magnitude_response[idx])


def half_power_bandwidth(
    frequencies: np.ndarray,
    magnitude_response: np.ndarray,
    min_idx: int | None = None,
    target_freq: float | None = None,
    search_width: float = 0.05,
) -> tuple[float, float, float, float]:
    """Compute resonant frequency and half-power (-3 dB) bandwidth points.

    Given a resonance dip in the magnitude response |S11(f)|, locates
    the minimum and finds the frequencies *f1* and *f2* on either side
    where the magnitude crosses the half-power (critical coupling) threshold.

    Derivation
    ----------
    For a reflection-type measurement the half-power condition relative
    to the minimum |S11| = Γ_min is::

        Γ_target = √((1 + Γ_min²) / 2)

    The loaded Q is then::

        QL = f0 / (f2 - f1)

    Parameters
    ----------
    frequencies : np.ndarray
        Frequency points (typically GHz).
    magnitude_response : np.ndarray
        |S| at each frequency (linear magnitude, not dB).
    min_idx : int or None
        Index of the resonance dip.  If ``None``, ``argmin`` is used.
    target_freq : float or None
        If provided, restricts the search to ``±search_width`` around
        this frequency.  Useful for avoiding spurious higher-order-mode
        dips when the solver band is wide.
    search_width : float
        Half-width of the search window around *target_freq*.  Default 0.05
        (50 MHz in GHz units).  Only used if *target_freq* is set.

    Returns
    -------
    f0 : float
        Resonant frequency (same units as *frequencies*).
    f1 : float
        Lower half-power frequency.
    f2 : float
        Upper half-power frequency.
    gamma_min : float
        Minimum |S11| value (linear).
    """
    if target_freq is not None:
        # Restrict to frequencies near the target
        mask = np.abs(frequencies - target_freq) <= search_width
        if mask.sum() < 5:
            raise ValueError(
                f"Fewer than 5 frequency points within ±{search_width} GHz "
                f"of target {target_freq} GHz — resonance likely outside band"
            )
        freqs_subset = frequencies[mask]
        mag_subset = magnitude_response[mask]
        local_min_idx = int(np.argmin(mag_subset))
        # Map back to global index
        global_indices = np.where(mask)[0]
        min_idx = global_indices[local_min_idx]
    elif min_idx is None:
        min_idx = int(np.argmin(magnitude_response))

    f0 = float(frequencies[min_idx])
    gamma_min = float(magnitude_response[min_idx])

    # Half-power reflection target
    gamma_target = np.sqrt((1.0 + gamma_min**2) / 2.0)

    # Build interpolant of (|S11| - gamma_target) for root-finding
    diff = magnitude_response - gamma_target

    # ---- Helper: find root crossing with brentq fallback ----
    def _find_root(freq_subset: np.ndarray, bracket_lo: float, bracket_hi: float) -> float:
        """Find where |S11| = gamma_target within the given bracket.

        Tries cubic-spline brentq first; falls back to linear scan if the
        root is not bracketed (e.g. frequency range too narrow for the
        half-power point to appear).
        """
        interp = interp1d(frequencies, diff, kind="cubic")

        # Check if root is bracketed
        if diff[frequencies <= bracket_lo].size == 0 or diff[frequencies >= bracket_hi].size == 0:
            raise ValueError("Bracket outside frequency range")

        lo_val = interp(bracket_lo)
        hi_val = interp(bracket_hi)

        if lo_val * hi_val > 0:
            # Root not bracketed — fall back to linear scan for sign change
            d_subset = diff[(frequencies >= freq_subset[0]) & (frequencies <= freq_subset[-1])]
            f_subset = frequencies[(frequencies >= freq_subset[0]) & (frequencies <= freq_subset[-1])]
            sign_changes = np.where(np.diff(np.sign(d_subset)))[0]
            if len(sign_changes) == 0:
                raise ValueError(
                    "Half-power threshold not reached within frequency range — "
                    "the |S11| dip may be too shallow or the span too narrow"
                )
            # Use the sign change closest to f0
            idx = sign_changes[0]
            bracket_lo = float(f_subset[idx])
            bracket_hi = float(f_subset[idx + 1])

        try:
            return brentq(interp, bracket_lo, bracket_hi)
        except ValueError:
            # Last resort: linear interpolation between the bracketing points
            lo_val2 = interp(bracket_lo)
            hi_val2 = interp(bracket_hi)
            return bracket_lo - lo_val2 * (bracket_hi - bracket_lo) / (hi_val2 - lo_val2)

    # ---- Find f1 (left of resonance) ----
    f_left = frequencies[frequencies < f0]
    if len(f_left) < 2:
        raise ValueError("Not enough frequency points left of resonance")
    f1 = _find_root(f_left, float(f_left[0]), f0)

    # ---- Find f2 (right of resonance) ----
    f_right = frequencies[frequencies > f0]
    if len(f_right) < 2:
        raise ValueError("Not enough frequency points right of resonance")
    f2 = _find_root(f_right, f0, float(f_right[-1]))

    return f0, f1, f2, gamma_min


def loaded_q_from_bandwidth(f0: float, f1: float, f2: float) -> float:
    """Compute loaded quality factor from half-power bandwidth.

    Derivation
    ----------
    QL = f0 / BW,  where BW = f2 - f1  (3-dB bandwidth)

    Parameters
    ----------
    f0 : float
        Resonant frequency.
    f1 : float
        Lower half-power frequency.
    f2 : float
        Upper half-power frequency.

    Returns
    -------
    float
        Loaded quality factor QL (dimensionless).
    """
    return f0 / (f2 - f1)


def coupling_beta(gamma_min: float, over_coupled: bool = True) -> float:
    """Compute the input coupling parameter Beta from |S11| at resonance.

    Derivation
    ----------
    For an over-coupled cavity (Beta > 1)::

        Beta = (1 + |S11|) / (1 - |S11|)

    For an under-coupled cavity (Beta < 1)::

        Beta = (1 - |S11|) / (1 + |S11|)

    Accelerator cavities are typically operated over-coupled.

    Parameters
    ----------
    gamma_min : float
        Linear magnitude of S11 at resonance.
    over_coupled : bool
        If ``True``, use the over-coupled formula (default).

    Returns
    -------
    float
        Coupling parameter Beta (dimensionless).
    """
    if gamma_min >= 1.0:
        raise ValueError(f"|S11| = {gamma_min} >= 1; cannot compute Beta")
    if over_coupled:
        return (1.0 + gamma_min) / (1.0 - gamma_min)
    return (1.0 - gamma_min) / (1.0 + gamma_min)


def intrinsic_q0(ql: float, beta: float) -> float:
    """Compute unloaded (intrinsic) quality factor Q0.

    Derivation
    ----------
    Q0 = QL * (1 + Beta)

    This follows from the definition of coupling::

        1/QL = 1/Q0 + 1/Qext
        Beta = Q0 / Qext  ⇒  Q0 = QL * (1 + Beta)

    Parameters
    ----------
    ql : float
        Loaded quality factor (dimensionless).
    beta : float
        Coupling parameter.

    Returns
    -------
    float
        Intrinsic quality factor Q0 (dimensionless).
    """
    return ql * (1.0 + beta)


def normalize_field_to_stored_energy(
    field_value: float,
    stored_energy_sim: float,
    target_energy: float = 1.0,
) -> float:
    """Normalise a field amplitude to a different stored-energy level.

    Derivation
    ----------
    Field scales as sqrt(U), so::

        E_norm = E_sim * √(U_target / U_sim)

    Used to normalise CST field results (which use a default 1 W input
    power) to a standard reference (typically 1 J stored energy).

    Parameters
    ----------
    field_value : float
        Peak field at the simulation excitation level (V/m).
    stored_energy_sim : float
        Stored electromagnetic energy from the simulation (J).
    target_energy : float
        Desired stored energy reference (J); default 1 J.

    Returns
    -------
    float
        Normalised field (V/m).
    """
    return field_value * np.sqrt(target_energy / stored_energy_sim)


def power_scaling(
    e_sim: float,
    e_target: float,
    p_in_sim: float = 1.0,
) -> tuple[float, float]:
    """Compute the power scaling needed to reach a target gradient.

    Derivation
    ----------
    E ∝ √P  ⇒  K = E_target / E_sim

    P_in_target = P_in_sim * K²
    P_ref_target = P_in_target * |S11|²   (reflected power fraction)

    Parameters
    ----------
    e_sim : float
        Peak field from simulation (V/m), at input power *p_in_sim*.
    e_target : float
        Desired peak / accelerating field (V/m).
    p_in_sim : float
        Input (forward) power used in simulation (W); default 1 W.

    Returns
    -------
    scale_factor : float
        Field scaling factor K = E_target / E_sim.
    power_scale : float
        Power scaling factor K².
    """
    k = e_target / e_sim
    return k, k * k
