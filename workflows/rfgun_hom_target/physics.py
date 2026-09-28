"""Portable transverse HOM calculations, derived from cst-hom-audit.

Provenance: cst-hom-audit/scripts/analyze.py and references/workflow.md,
reviewed 2026-09-28. No runtime dependency on the personal skill. Peak complex
Ez is in V/m, coordinates in metres, stored energy in J, frequency in Hz.
The circuit convention includes 1/2; loaded Q already includes modelled loss.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

C_M_PER_S = 299_792_458.0


@dataclass(frozen=True)
class TransverseMetrics:
    """Strongest real transverse direction; R/Q and impedance are in ohm/m."""

    rq_x_ohm_per_m: float
    rq_y_ohm_per_m: float
    rq_principal_ohm_per_m: float
    impedance_x_ohm_per_m: float | None
    impedance_y_ohm_per_m: float | None
    impedance_principal_ohm_per_m: float | None
    principal_angle_deg: float | None
    gradient_method_difference_fraction: float | None
    voltage_half_density_difference_fraction: float | None
    gradient_real_v_per_m: tuple[float, float]
    gradient_imag_v_per_m: tuple[float, float]
    cross_rq_real_ohm_per_m: float
    cross_rq_imag_ohm_per_m: float
    quality_reasons: tuple[str, ...]
    voltages_real_v: tuple[float, ...]
    voltages_imag_v: tuple[float, ...]

    @property
    def quality_ok(self) -> bool:
        return not self.quality_reasons

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe SI metrics and explicit validity."""
        return {**asdict(self), "quality_ok": self.quality_ok}


def calculate_transverse_metrics(
    ez_v_per_m: np.ndarray,
    z_m: np.ndarray,
    xy_mm: np.ndarray,
    *,
    frequency_hz: float,
    energy_j: float,
    q_loaded: float,
    gradient_tolerance: float = 0.02,
    sampling_tolerance: float = 0.01,
    minimum_q: float = 10.0,
    enforce_minimum_q: bool = True,
) -> TransverseMetrics:
    """Integrate peak Ez exp(+i omega z/c), beta=1, on 13 trajectories.

    Three symmetric offsets per axis support cubic and inner-five-point
    gradient crosschecks. The largest eigenvalue of the *real* impedance
    tensor represents a real beam displacement; its trace would overestimate
    elliptically polarized modes. R/Q = c gi gj*/(2 omega² U), in ohm/m.
    By default low-Q isolated-mode estimates are withheld. With the explicit
    user-selected relaxed policy, Q*(R/Q) is a single-mode optimization score;
    it is not a reconstruction of an overlapping broadband impedance spectrum.
    """
    ez = np.asarray(ez_v_per_m, dtype=np.complex128)
    z = np.asarray(z_m, dtype=float)
    xy = np.asarray(xy_mm, dtype=float)
    if not np.isfinite([frequency_hz, energy_j, q_loaded]).all() or min(frequency_hz, energy_j, q_loaded) <= 0:
        raise ValueError("frequency, energy and loaded Q must be finite and positive")
    if z.ndim != 1 or len(z) < 5 or len(z) % 2 != 1 or not np.all(np.diff(z) > 0):
        raise ValueError("z must have an odd number >=5 of increasing samples")
    if xy.shape != (13, 2) or ez.shape != (13, len(z)):
        raise ValueError("expected 13 trajectory coordinates and matching Ez samples")
    if not np.isfinite(ez).all() or not np.isfinite(z).all() or not np.isfinite(xy).all():
        raise ValueError("missing/nonfinite field samples must not be replaced by zero")
    if len(np.unique(xy, axis=0)) != 13 or np.count_nonzero(np.all(xy == 0, axis=1)) != 1:
        raise ValueError("trajectory coordinates must be unique with one beam axis")
    if not np.isfinite([gradient_tolerance, sampling_tolerance, minimum_q]).all() or min(gradient_tolerance, sampling_tolerance, minimum_q) <= 0:
        raise ValueError("quality thresholds must be finite and positive")
    trap = getattr(np, "trapezoid", None) or np.trapz
    omega = 2 * np.pi * frequency_hz
    phase = np.exp(1j * omega / C_M_PER_S * z)
    volts = trap(ez * phase, z, axis=1)
    half = np.unique(np.r_[np.arange(0, len(z), 2), len(z) - 1])
    half_volts = trap(ez[:, half] * phase[half], z[half], axis=1)
    gradients, differences = [], []
    for axis in range(2):
        ids = np.flatnonzero(xy[:, 1 - axis] == 0)
        ids = ids[np.argsort(xy[ids, axis])]
        coord = xy[ids, axis]
        if len(ids) != 7 or not np.allclose(coord, -coord[::-1], rtol=0, atol=1e-12):
            raise ValueError("each axis needs three symmetric positive offsets")
        gradient = np.polynomial.polynomial.polyfit(coord, volts[ids], 3)[1] * 1000
        local = np.polynomial.polynomial.polyfit(coord[1:-1], volts[ids][1:-1], 4)[1] * 1000
        gradients.append(gradient)
        differences.append(abs(local - gradient))
    g = np.asarray(gradients)
    matrix = np.outer(g, g.conj()) * C_M_PER_S / (2 * omega**2 * energy_j)
    values, vectors = np.linalg.eigh(matrix.real)
    norm, vmax = float(np.linalg.norm(g)), float(np.max(abs(volts)))
    grad_error = float(np.linalg.norm(differences) / norm) if norm else None
    sample_error = float(np.max(abs(volts - half_volts)) / vmax) if vmax else None
    reasons = []
    if grad_error is None or grad_error > gradient_tolerance:
        reasons.append("gradient_crosscheck_failed")
    if sample_error is None or sample_error > sampling_tolerance:
        reasons.append("sampling_crosscheck_failed")
    if not isinstance(enforce_minimum_q, bool):
        raise ValueError("enforce_minimum_q must be boolean")
    if enforce_minimum_q and q_loaded < minimum_q:
        reasons.append("low_q_isolated_mode_estimate_withheld")
    high_q = not enforce_minimum_q or q_loaded >= minimum_q
    principal = max(0.0, float(values[-1]))
    return TransverseMetrics(
        float(matrix[0, 0].real), float(matrix[1, 1].real), principal,
        float(matrix[0, 0].real * q_loaded) if high_q else None,
        float(matrix[1, 1].real * q_loaded) if high_q else None,
        principal * q_loaded if high_q else None,
        float(np.degrees(np.arctan2(vectors[1, -1], vectors[0, -1])) % 180) if norm else None,
        grad_error, sample_error, tuple(map(float, g.real)), tuple(map(float, g.imag)),
        float(matrix[0, 1].real), float(matrix[0, 1].imag), tuple(reasons),
        tuple(map(float, volts.real)), tuple(map(float, volts.imag)),
    )


def phase_insensitive_correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Compare equal-grid complex trajectory arrays, insensitive to global phase."""
    a, b = np.asarray(first).ravel(), np.asarray(second).ravel()
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        return 0.0
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.clip(abs(np.vdot(a, b)) / norm, 0, 1)) if norm else 0.0


@dataclass(frozen=True)
class ModeSignature:
    """Supplemental identity evidence from 13 complex trajectory voltages.

    Trajectory order, offsets and integration range MUST be the same in both
    campaigns. This compressed signature is not a full 3D field overlap.
    IDs are opaque labels, never interpreted as stable CST mode numbers.
    """

    mode_id: str
    frequency_hz: float
    voltages: tuple[complex, ...]

    def __post_init__(self) -> None:
        if not self.mode_id or not np.isfinite(self.frequency_hz) or self.frequency_hz <= 0:
            raise ValueError("mode signature needs an ID and positive finite frequency")
        array = np.asarray(self.voltages, dtype=np.complex128)
        if array.shape != (13,) or not np.isfinite(array).all() or np.linalg.norm(array) == 0:
            raise ValueError("mode signature needs 13 finite nonzero complex voltages")

    @classmethod
    def from_metrics(cls, mode_id: str, frequency_hz: float, metrics: TransverseMetrics) -> ModeSignature:
        """Construct a normalized signature from archived field-derived voltages."""
        values = np.asarray(metrics.voltages_real_v) + 1j * np.asarray(metrics.voltages_imag_v)
        norm = float(np.linalg.norm(values))
        if norm == 0:
            raise ValueError("vanishing trajectory voltages cannot identify a mode")
        return cls(mode_id, frequency_hz, tuple(values / norm))


@dataclass(frozen=True)
class ModeMatch:
    """Optional assignment evidence; ambiguity never gates the window objective."""

    current_id: str
    baseline_id: str | None
    overlap: float | None
    frequency_shift_hz: float | None
    ambiguous: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def match_mode_signatures(
    baseline: Sequence[ModeSignature], current: Sequence[ModeSignature], *,
    frequency_gate_hz: float = 20e6, minimum_overlap: float = 0.8,
    ambiguity_margin: float = 0.05,
) -> list[ModeMatch]:
    """Assign frequency-gated signatures using SciPy's linear sum assignment.

    Independent mode phase and field normalization cancel in |<a,b>|.
    Dummy columns allow unmatched modes. Near ties in either direction flag
    degenerate-basis rotations or weak identity evidence instead of claiming
    a fixed identity. This diagnostic MUST NOT select modes for optimization:
    the score still includes every mode in the frequency window.
    """
    from scipy.optimize import linear_sum_assignment

    if not np.isfinite([frequency_gate_hz, minimum_overlap, ambiguity_margin]).all() or frequency_gate_hz <= 0 or not 0 < minimum_overlap <= 1 or not 0 <= ambiguity_margin < 1:
        raise ValueError("invalid matching thresholds")
    for group in (baseline, current):
        if len({item.mode_id for item in group}) != len(group):
            raise ValueError("signature mode IDs must be unique within each campaign")
    if not current:
        return []
    if not baseline:
        return [ModeMatch(item.mode_id, None, None, None, False, "no_baseline_modes") for item in current]
    overlap = np.zeros((len(current), len(baseline)))
    gated = np.zeros_like(overlap, dtype=bool)
    for i, candidate in enumerate(current):
        for j, reference in enumerate(baseline):
            gated[i, j] = abs(candidate.frequency_hz - reference.frequency_hz) <= frequency_gate_hz
            if gated[i, j]:
                overlap[i, j] = phase_insensitive_correlation(np.asarray(candidate.voltages), np.asarray(reference.voltages))
    eligible = gated & (overlap >= minimum_overlap)
    # Maximum-weight one-to-one matching; unmatched dummy choices have zero
    # weight. Ineligible matches have strictly positive cost and cannot win.
    cost = np.zeros((len(current), len(baseline) + len(current)))
    cost[:, :len(baseline)] = np.where(eligible, -overlap, 1.0)
    rows, columns = linear_sum_assignment(cost)
    assignment = dict(zip(rows.tolist(), columns.tolist()))

    def tied(values: np.ndarray) -> bool:
        ordered = np.sort(values)
        return len(ordered) > 1 and ordered[-1] > 0 and ordered[-1] - ordered[-2] <= ambiguity_margin

    matches = []
    for i, candidate in enumerate(current):
        j = assignment[i]
        row_tie = tied(overlap[i, gated[i]])
        if j >= len(baseline):
            matches.append(ModeMatch(candidate.mode_id, None, None, None, row_tie,
                "ambiguous_or_below_overlap" if row_tie else "no_eligible_unique_match"))
            continue
        # A globally optimal match may assign this row away from its strongest
        # candidate. Such an assignment is evidence, not confident identity.
        ambiguous = row_tie or tied(overlap[gated[:, j], j]) or overlap[i, j] < np.max(overlap[i])
        matches.append(ModeMatch(candidate.mode_id, baseline[j].mode_id, float(overlap[i, j]),
            candidate.frequency_hz - baseline[j].frequency_hz, ambiguous,
            "ambiguous_signature_assignment" if ambiguous else "unique_signature_match"))
    return matches
