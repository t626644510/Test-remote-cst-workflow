"""Curve sampling helpers."""

from __future__ import annotations


def profile_rms_and_max(reference: list[tuple[float, float]], candidate: list[tuple[float, float]]) -> tuple[float, float]:
    """Return RMS/max pointwise distance for equal-length r-z profiles."""
    if len(reference) != len(candidate) or not reference:
        return 0.0, 0.0
    distances = [((za - zb) ** 2 + (ra - rb) ** 2) ** 0.5 for (za, ra), (zb, rb) in zip(reference, candidate)]
    rms = (sum(value * value for value in distances) / len(distances)) ** 0.5
    return rms, max(distances)
