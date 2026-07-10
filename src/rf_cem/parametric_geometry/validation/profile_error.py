"""Profile error helpers."""

from __future__ import annotations


def zero_profile_error() -> dict:
    """Return MVP profile error for generated profile truth points."""
    return {"profile_rms_error_mm": 0.0, "profile_max_error_mm": 0.0}
