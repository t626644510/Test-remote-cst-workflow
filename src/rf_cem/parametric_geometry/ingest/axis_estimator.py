"""Axis verification for the axisymmetric RF vacuum MVP."""

from __future__ import annotations

from rf_cem.parametric_geometry.core.types import AxisReport


def verify_axis(manifest: dict, axis: str) -> AxisReport:
    """Verify the requested axis against helper2 geometry evidence."""
    detected = str(manifest.get("model_summary", {}).get("detected_axis") or "")
    bbox = manifest.get("model_summary", {}).get("bbox", {})
    x_span = abs(float(bbox.get("xmax", 0.0)) + float(bbox.get("xmin", 0.0)))
    y_span = abs(float(bbox.get("ymax", 0.0)) + float(bbox.get("ymin", 0.0)))
    accepted = detected.lower() == axis.lower() and x_span < 1e-3 and y_span < 1e-3
    return AxisReport(
        requested_axis=axis,  # type: ignore[arg-type]
        detected_axis=detected,
        accepted=accepted,
        confidence=0.99 if accepted else 0.4,
        max_section_delta_mm=0.0 if accepted else max(x_span, y_span),
        notes=["axis verified from helper2 model_summary bbox symmetry"],
    )
