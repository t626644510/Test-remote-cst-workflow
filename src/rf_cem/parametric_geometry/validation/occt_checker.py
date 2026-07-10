"""OCCT validation report composition."""

from __future__ import annotations

from rf_cem.parametric_geometry.core.types import GeometryThresholds
from rf_cem.parametric_geometry.validation.geometry_metrics import compare_geometry
from rf_cem.parametric_geometry.validation.profile_error import zero_profile_error
from rf_cem.parametric_geometry.validation.self_intersection import all_r_nonnegative, profile_is_simple


def build_validation_report(
    kernel_report: dict,
    profile_points: list[tuple[float, float]],
    thresholds: GeometryThresholds | None = None,
) -> dict:
    """Build the geometry_validation.v0 report."""
    comparison = compare_geometry(kernel_report, thresholds)
    profile_checks = {
        "profile_is_simple": profile_is_simple(profile_points),
        "all_r_ge_0": all_r_nonnegative(profile_points),
        "min_curvature_check": "not_evaluated_for_polyline_mvp",
    }
    blocking = list(comparison["blocking_errors"])
    if not profile_checks["profile_is_simple"]:
        blocking.append("profile is not simple")
    if not profile_checks["all_r_ge_0"]:
        blocking.append("profile crosses the rotation axis")
    return {
        "schema_version": "geometry_validation.v0",
        "baseline": kernel_report["baseline"],
        "generated": kernel_report["generated"],
        "source_kernel_curve_generation_mode": kernel_report.get("curve_generation", {}).get("mode"),
        "source_kernel_curve_generation_fallbacks": kernel_report.get("curve_generation", {}).get("fallbacks", []),
        "comparison": {
            **comparison,
            **zero_profile_error(),
            "key_dimensions": {},
        },
        "profile_checks": profile_checks,
        "pass": not blocking,
        "blocking_errors": blocking,
        "warnings": comparison["warnings"],
    }
