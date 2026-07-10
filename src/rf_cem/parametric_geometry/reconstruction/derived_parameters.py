"""Derived curve parameters for parametric geometry audit and optimization."""

from __future__ import annotations


def derive_curve_parameters(segments: list[dict], *, variant_name: str) -> dict:
    """Promote segment curve controls into named, optimization-ready parameters."""
    derived: dict[str, dict] = {}
    _add_shared_parameters(derived, segments, variant_name)
    for segment in segments:
        segment_id = str(segment["id"])
        curve = segment.get("curve", {})
        curve_type = str(curve.get("type", segment.get("kind", "")))
        _add(
            derived,
            f"curve_type__{segment_id}",
            curve_type,
            "categorical",
            segment,
            variant_name,
            provenance="segment.curve.type",
        )
        if curve_type == "arc":
            center = curve.get("center", {})
            _add(derived, f"arc_center_z__{segment_id}", center.get("z"), "mm", segment, variant_name, provenance="segment.curve.center.z")
            _add(derived, f"arc_center_r__{segment_id}", center.get("r"), "mm", segment, variant_name, provenance="segment.curve.center.r")
            _add(derived, f"arc_radius__{segment_id}", curve.get("radius"), "mm", segment, variant_name, provenance="segment.curve.radius")
            _add(derived, f"arc_start_angle_rad__{segment_id}", curve.get("start_angle_rad"), "rad", segment, variant_name, provenance="segment.curve.start_angle_rad")
            _add(derived, f"arc_end_angle_rad__{segment_id}", curve.get("end_angle_rad"), "rad", segment, variant_name, provenance="segment.curve.end_angle_rad")
        elif curve_type == "nurbs":
            control_points = curve.get("control_points", [])
            _add(derived, f"nurbs_degree__{segment_id}", curve.get("degree"), "dimensionless", segment, variant_name, provenance="segment.curve.degree")
            _add(derived, f"nurbs_control_count__{segment_id}", len(control_points), "count", segment, variant_name, provenance="segment.curve.control_points")
            for index, point in enumerate(control_points):
                _add(derived, f"nurbs_cp{index}_z__{segment_id}", point.get("z"), "mm", segment, variant_name, provenance=f"segment.curve.control_points[{index}].z")
                _add(derived, f"nurbs_cp{index}_r__{segment_id}", point.get("r"), "mm", segment, variant_name, provenance=f"segment.curve.control_points[{index}].r")
    return derived


def _add_shared_parameters(target: dict, segments: list[dict], variant_name: str) -> None:
    arc_radii = _arc_radii_by_feature(segments)
    if "NoseCone" in arc_radii:
        nose_radii = sorted(set(round(value, 9) for value in arc_radii["NoseCone"]))
        if len(nose_radii) == 1:
            _add_shared(target, "shared_nose_arc_radius_mm", nose_radii[0], "mm", "NoseCone", variant_name, "normalized common NoseCone arc radius")
    if "TransitionBlend" in arc_radii:
        blend_radii = sorted(set(round(value, 9) for value in arc_radii["TransitionBlend"]))
        if len(blend_radii) == 1:
            _add_shared(target, "shared_blend_arc_radius_mm", blend_radii[0], "mm", "TransitionBlend", variant_name, "normalized common TransitionBlend arc radius")
    equator = next((segment for segment in segments if segment["id"] == "seg_equator_free_crown"), None)
    if equator:
        points = equator.get("curve", {}).get("control_points", [])
        if len(points) >= 5:
            endpoint_r = float(points[0]["r"])
            crown_r = float(points[2]["r"])
            shoulder_z = abs(float(points[1]["z"]))
            crown_delta_r_mm = crown_r - endpoint_r
            # STEP/NURBS reconstruction can leave sub-nanometer roundoff in
            # millimeter coordinates; values below 1e-6 mm are physically zero.
            if abs(crown_delta_r_mm) < 1.0e-6:
                crown_delta_r_mm = 0.0
            _add_shared(target, "shared_equator_crown_delta_r_mm", crown_delta_r_mm, "mm", "EquatorRegion", variant_name, "normalized crown radius offset from equator endpoint radius")
            _add_shared(target, "shared_equator_crown_shoulder_z_abs_mm", shoulder_z, "mm", "EquatorRegion", variant_name, "normalized symmetric equator crown shoulder z")


def _arc_radii_by_feature(segments: list[dict]) -> dict[str, list[float]]:
    radii: dict[str, list[float]] = {}
    for segment in segments:
        if segment.get("kind") != "arc":
            continue
        radius = segment.get("curve", {}).get("radius")
        if radius is None:
            continue
        for feature_ref in segment.get("feature_refs", []):
            radii.setdefault(str(feature_ref), []).append(float(radius))
    return radii


def _add_shared(
    target: dict,
    parameter_id: str,
    value: object,
    unit: str,
    feature_ref: str,
    variant_name: str,
    provenance: str,
) -> None:
    target[parameter_id] = {
        "value": value,
        "unit": unit,
        "parameter_role": "derived_curve_control",
        "normalization": "shared_symmetric_parameter",
        "variant": variant_name,
        "segment_id": "shared",
        "feature_refs": [feature_ref],
        "face_refs": [],
        "provenance": provenance,
        "prior_rule_id": f"grammar.curve_policy.{variant_name}",
        "affects_generated_step": True,
        "affects_translator": False,
        "confidence": 0.85,
        "optimization_candidate": True,
    }


def _add(
    target: dict,
    parameter_id: str,
    value: object,
    unit: str,
    segment: dict,
    variant_name: str,
    *,
    provenance: str,
) -> None:
    if value is None:
        return
    target[parameter_id] = {
        "value": value,
        "unit": unit,
        "parameter_role": "derived_curve_control",
        "variant": variant_name,
        "segment_id": segment["id"],
        "feature_refs": segment.get("feature_refs", []),
        "face_refs": segment.get("face_refs", []),
        "provenance": provenance,
        "prior_rule_id": f"grammar.curve_policy.{variant_name}",
        "affects_generated_step": True,
        "affects_translator": False,
        "confidence": segment.get("confidence", 0.75),
        "optimization_candidate": True,
    }
