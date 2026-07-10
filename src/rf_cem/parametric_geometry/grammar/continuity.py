"""Profile continuity checks."""

from __future__ import annotations


def check_profile_continuity(segments: list[dict], tolerance_mm: float = 1e-6) -> dict:
    """Check C0 continuity between ordered segments."""
    gaps = []
    for left, right in zip(segments, segments[1:]):
        dz = float(left["end"]["z"]) - float(right["start"]["z"])
        dr = float(left["end"]["r"]) - float(right["start"]["r"])
        gap = (dz * dz + dr * dr) ** 0.5
        if gap > tolerance_mm:
            gaps.append({"left": left["id"], "right": right["id"], "gap_mm": gap})
    return {"c0_pass": not gaps, "gaps": gaps}
