"""Geometry comparison metrics."""

from __future__ import annotations

from rf_cem.parametric_geometry.core.types import GeometryThresholds


def compare_geometry(kernel_report: dict, thresholds: GeometryThresholds | None = None) -> dict:
    """Compare baseline and generated geometry metrics."""
    thresholds = thresholds or GeometryThresholds()
    baseline = kernel_report["baseline"]
    generated = kernel_report["generated"]
    bbox_error = {
        key: abs(float(generated["bbox_mm"][key]) - float(baseline["bbox_mm"][key]))
        for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")
    }
    bbox_pass = all(
        error <= max(thresholds.bbox_abs_mm, abs(float(baseline["bbox_mm"][key])) * thresholds.bbox_rel)
        for key, error in bbox_error.items()
    )
    volume_rel = _relative_error(generated["volume_mm3"], baseline["volume_mm3"])
    area_rel = _relative_error(generated["surface_area_mm2"], baseline["surface_area_mm2"])
    blocking = []
    warnings = []
    if not baseline["brep_valid"] or not generated["brep_valid"]:
        blocking.append("baseline or generated BRep is invalid")
    if not bbox_pass:
        _record_threshold(
            "bbox",
            "bbox difference exceeds threshold",
            thresholds,
            blocking,
            warnings,
        )
    if volume_rel > thresholds.volume_rel:
        _record_threshold(
            "volume",
            "volume relative error exceeds threshold",
            thresholds,
            blocking,
            warnings,
        )
    if area_rel > thresholds.surface_area_rel:
        _record_threshold(
            "surface_area",
            "surface area differs beyond threshold; baseline STEP contains face partitions not reproduced by the clean grammar profile",
            thresholds,
            blocking,
            warnings,
        )
    return {
        "bbox_error_mm": bbox_error,
        "bbox_pass": bbox_pass,
        "volume_relative_error": volume_rel,
        "surface_area_relative_error": area_rel,
        "surface_area_pass": area_rel <= thresholds.surface_area_rel,
        "blocking_errors": blocking,
        "warnings": warnings,
    }


def _relative_error(candidate: float, reference: float) -> float:
    reference_f = abs(float(reference))
    if reference_f == 0.0:
        return 0.0
    return abs(float(candidate) - float(reference)) / reference_f


def _record_threshold(
    metric: str,
    message: str,
    thresholds: GeometryThresholds,
    blocking: list[str],
    warnings: list[str],
) -> None:
    severity = str(thresholds.baseline_difference_policy.get(metric, "blocking")).lower()
    if severity == "ignore":
        return
    if severity == "warning":
        warnings.append(message)
        return
    blocking.append(message)
