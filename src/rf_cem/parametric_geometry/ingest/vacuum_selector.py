"""Target RF vacuum body selection."""

from __future__ import annotations

from rf_cem.parametric_geometry.core.types import BodySelection


def select_target_body(manifest: dict, target_body_index: int) -> BodySelection:
    """Select the target vacuum solid, preferring explicit body index."""
    solid_count = int(manifest.get("model_summary", {}).get("solid_count") or 0)
    if target_body_index < 0 or target_body_index >= max(solid_count, 1):
        raise ValueError(f"target body index {target_body_index} is out of range for {solid_count} solid(s)")
    return BodySelection(
        mode="manual_index",
        body_ref=f"solid:S{target_body_index + 1:04d}",
        body_index=target_body_index,
        confidence=1.0,
        notes=["manual target body selection is the MVP default"],
    )
