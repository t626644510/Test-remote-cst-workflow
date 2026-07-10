"""Single-cell axisymmetric RF vacuum grammar v0."""

from __future__ import annotations

import math

from rf_cem.parametric_geometry.expert_prior import load_expert_prior


VARIANT_IRIS_TORUS_EXACT = "iris_torus_exact"
VARIANT_EXPANDED_SMOOTH_NOSE = "expanded_smooth_nose"
VARIANT_FREE_EQUATOR_SMOOTH = "free_equator_smooth"
VARIANT_MANUAL_EQUATOR_INSET = "manual_equator_inset_3mm"
VARIANT_MANUAL_EQUATOR_BULGE = "manual_equator_bulge_3mm"
VARIANT_MANUAL_EQUATOR_WIDE = "manual_equator_wide_soft"
DEFAULT_VARIANTS = [
    VARIANT_IRIS_TORUS_EXACT,
    VARIANT_EXPANDED_SMOOTH_NOSE,
    VARIANT_FREE_EQUATOR_SMOOTH,
    VARIANT_MANUAL_EQUATOR_INSET,
    VARIANT_MANUAL_EQUATOR_BULGE,
    VARIANT_MANUAL_EQUATOR_WIDE,
]
DEFAULT_SELECTED_VARIANT = VARIANT_FREE_EQUATOR_SMOOTH


def build_single_cell_profile(
    parameters: dict,
    prior: dict | None = None,
    *,
    variant_name: str = DEFAULT_SELECTED_VARIANT,
) -> tuple[list[tuple[float, float]], list[dict]]:
    """Build an r-z profile with explicit curve segments for nose/blend regions."""
    prior = prior or load_expert_prior()[0]
    primitives = parameters.get("_profile_primitives", {})
    if primitives.get("primitives"):
        segments = _build_curve_segments(parameters, prior, variant_name)
        return _sample_profile(segments), segments
    return _build_template_profile(parameters, prior)


def _build_curve_segments(parameters: dict, prior: dict, variant_name: str) -> list[dict]:
    control = parameters["_profile_control"]
    zmin = float(control["zmin"])
    zmax = float(control["zmax"])
    beam_r = float(control["beam_radius"])
    equator_r = float(control["equator_radius"])
    primitives = parameters["_profile_primitives"]
    nose_left = _pick_arc(primitives, "NoseCone", side="left", major_radius=54.0)
    nose_left_outer = _pick_arc(primitives, "NoseCone", side="left", major_radius=74.0)
    nose_right = _pick_arc(primitives, "NoseCone", side="right", major_radius=54.0)
    nose_right_outer = _pick_arc(primitives, "NoseCone", side="right", major_radius=74.0)
    blend_left = _pick_arc(primitives, "TransitionBlend", side="left")
    blend_right = _pick_arc(primitives, "TransitionBlend", side="right")
    bridge_left = _pick_bridge(primitives, side="left")
    bridge_right = _pick_bridge(primitives, side="right")
    if not all((nose_left, nose_left_outer, nose_right, nose_right_outer, blend_left, blend_right)):
        missing = [
            name
            for name, value in {
                "nose_left": nose_left,
                "nose_left_outer": nose_left_outer,
                "nose_right": nose_right,
                "nose_right_outer": nose_right_outer,
                "blend_left": blend_left,
                "blend_right": blend_right,
            }.items()
            if not value
        ]
        raise ValueError(f"required nose/blend torus primitives are missing: {', '.join(missing)}")

    left_bridge_r = _bridge_inner_radius(bridge_left, fallback=157.14235271385)
    right_bridge_r = _bridge_inner_radius(bridge_right, fallback=157.14235271385)
    blend_parameters = _curve_parameters(prior, variant_name, "blend")
    blend_left_segment = _arc_from_angles(
        "seg_blend_left",
        blend_left,
        math.pi,
        math.pi / 2,
        ["TransitionBlend", "EquatorRegion"],
        radius_delta=float(blend_parameters.get("left_radius_delta_mm", 0.0)),
    )
    blend_right_segment = _arc_from_angles(
        "seg_blend_right",
        blend_right,
        math.pi / 2,
        0.0,
        ["TransitionBlend", "EquatorRegion"],
        radius_delta=float(blend_parameters.get("right_radius_delta_mm", 0.0)),
    )
    left_blend_start = _segment_point(blend_left_segment, "start")
    left_blend_end = _segment_point(blend_left_segment, "end")
    right_blend_start = _segment_point(blend_right_segment, "start")
    right_blend_end = _segment_point(blend_right_segment, "end")
    segments: list[dict] = []
    segments.append(_line("seg_beam_pipe_left", (zmin, beam_r), (_arc_center(nose_left)[0], beam_r), ["BeamPipeLeft"], ["F0002", "F0019"]))
    segments.extend(_left_nose_segments(variant_name, prior, nose_left, nose_left_outer, left_bridge_r, left_blend_start))
    segments.append(blend_left_segment)
    segments.extend(_equator_segments(variant_name, prior, equator_r, left_blend_end, right_blend_start))
    segments.append(blend_right_segment)
    segments.extend(_right_nose_segments(variant_name, prior, nose_right, nose_right_outer, right_bridge_r, right_blend_end))
    segments.append(_line("seg_beam_pipe_right", (_arc_center(nose_right)[0], beam_r), (zmax, beam_r), ["BeamPipeRight"], ["F0001", "F0022"]))
    return _with_fit_metrics(segments, variant_name)


def variants_from_prior(prior: dict | None = None) -> list[str]:
    prior = prior or load_expert_prior()[0]
    variants = prior.get("grammar", {}).get("variant_policy", {}).get("enabled_variants", DEFAULT_VARIANTS)
    return [str(variant) for variant in variants]


def selected_variant_from_prior(prior: dict | None = None) -> str:
    prior = prior or load_expert_prior()[0]
    return str(prior.get("grammar", {}).get("variant_policy", {}).get("default_selected_variant", DEFAULT_SELECTED_VARIANT))


def _curve_choice(prior: dict, variant_name: str, region: str) -> str:
    return str(
        prior.get("grammar", {})
        .get("variant_policy", {})
        .get("curve_selection", {})
        .get(region, {})
        .get(variant_name, "cylinder" if region == "equator" else "local_nurbs_smooth_fallback")
    )


def _curve_parameters(prior: dict, variant_name: str, region: str) -> dict:
    value = (
        prior.get("grammar", {})
        .get("variant_policy", {})
        .get("curve_parameters", {})
        .get(region, {})
        .get(variant_name, {})
    )
    return value if isinstance(value, dict) else {}


def _left_nose_segments(
    variant_name: str,
    prior: dict,
    inner_arc: dict,
    outer_arc: dict,
    bridge_r: float,
    blend_anchor: tuple[float, float],
) -> list[dict]:
    inner_cz, inner_cr = _arc_center(inner_arc)
    outer_cz, outer_cr = _arc_center(outer_arc)
    if variant_name == VARIANT_IRIS_TORUS_EXACT:
        return [
            _arc_from_angles("seg_nose_left_inner_semicircle", inner_arc, -math.pi / 2, math.pi / 2, ["NoseCone"]),
            _arc_from_angles("seg_nose_left_outer_quarter", outer_arc, -math.pi / 2, -math.pi, ["NoseCone"]),
            _line("seg_nose_left_bridge_02", (outer_cz - 10.0, outer_cr), blend_anchor, ["NoseCone", "TransitionBlend"], _bridge_face_refs(outer_arc)),
        ]
    nose_parameters = _curve_parameters(prior, variant_name, "nose")
    control_points = _apply_nose_offsets(
        [
            _point(inner_cz, inner_cr, 10.0, -math.pi / 2),
            _point(inner_cz, inner_cr, 10.0, 0.0),
            (outer_cz - 10.0, outer_cr),
            blend_anchor,
        ],
        nose_parameters,
        side="left",
    )
    return [
        _nurbs(
            "seg_nose_left_smooth_nurbs",
            control_points,
            ["NoseCone", "TransitionBlend"],
            _bridge_face_refs(inner_arc) + _bridge_face_refs(outer_arc),
            "smoothness_priority=prefer_g1_with_evidence_anchors",
        ),
    ]


def _equator_segments(
    variant_name: str,
    prior: dict,
    equator_r: float,
    left_anchor: tuple[float, float],
    right_anchor: tuple[float, float],
) -> list[dict]:
    equator_choice = _curve_choice(prior, variant_name, "equator")
    if equator_choice == "local_nurbs_crown":
        rules = prior.get("grammar", {}).get("equator_design_rules", {}).get("local_nurbs_crown", {})
        variant_parameters = _curve_parameters(prior, variant_name, "equator")
        crown_z_mid = float(variant_parameters.get("crown_z_mid_mm", rules.get("default_crown_z_mid", 0.0)))
        shoulder_z = float(variant_parameters.get("shoulder_z_abs_mm", rules.get("default_shoulder_z_abs_mm", 30.0)))
        left_shoulder_z = float(variant_parameters.get("left_shoulder_z_abs_mm", shoulder_z))
        right_shoulder_z = float(variant_parameters.get("right_shoulder_z_abs_mm", shoulder_z))
        radius_scale = float(variant_parameters.get("crown_radius_scale", rules.get("default_crown_radius_scale", 1.0)))
        radius_delta = float(variant_parameters.get("crown_radius_delta_mm", rules.get("default_crown_radius_delta_mm", 0.0)))
        left_shoulder_delta_r = float(variant_parameters.get("left_shoulder_delta_r_mm", 0.0))
        right_shoulder_delta_r = float(variant_parameters.get("right_shoulder_delta_r_mm", 0.0))
        crown_r = equator_r * radius_scale + radius_delta
        left_endpoint_r = float(left_anchor[1])
        right_endpoint_r = float(right_anchor[1])
        left_shoulder_r = left_endpoint_r + radius_delta + left_shoulder_delta_r
        right_shoulder_r = right_endpoint_r + radius_delta + right_shoulder_delta_r
        return [
            _nurbs(
                "seg_equator_free_crown",
                [
                    left_anchor,
                    (-left_shoulder_z, left_shoulder_r),
                    (crown_z_mid, crown_r),
                    (right_shoulder_z, right_shoulder_r),
                    right_anchor,
                ],
                ["EquatorRegion"],
                ["F0006", "F0014"],
                "equator_curve_selection=local_nurbs_crown",
            )
        ]
    return [_line("seg_equator", left_anchor, right_anchor, ["EquatorRegion"], ["F0006", "F0014"], confidence=0.9)]


def _right_nose_segments(
    variant_name: str,
    prior: dict,
    inner_arc: dict,
    outer_arc: dict,
    bridge_r: float,
    blend_anchor: tuple[float, float],
) -> list[dict]:
    inner_cz, inner_cr = _arc_center(inner_arc)
    outer_cz, outer_cr = _arc_center(outer_arc)
    if variant_name == VARIANT_IRIS_TORUS_EXACT:
        return [
            _line("seg_nose_right_bridge_02", blend_anchor, (outer_cz + 10.0, outer_cr), ["TransitionBlend", "NoseCone"], _bridge_face_refs(outer_arc)),
            _arc_from_angles("seg_nose_right_outer_quarter", outer_arc, 0.0, -math.pi / 2, ["NoseCone"]),
            _arc_from_angles("seg_nose_right_inner_semicircle", inner_arc, math.pi / 2, 3.0 * math.pi / 2, ["NoseCone"]),
        ]
    nose_parameters = _curve_parameters(prior, variant_name, "nose")
    control_points = _apply_nose_offsets(
        [
            blend_anchor,
            (outer_cz + 10.0, outer_cr),
            _point(inner_cz, inner_cr, 10.0, math.pi),
            _point(inner_cz, inner_cr, 10.0, -math.pi / 2),
        ],
        nose_parameters,
        side="right",
    )
    return [
        _nurbs(
            "seg_nose_right_smooth_nurbs",
            control_points,
            ["TransitionBlend", "NoseCone"],
            _bridge_face_refs(outer_arc) + _bridge_face_refs(inner_arc),
            "smoothness_priority=prefer_g1_with_evidence_anchors",
        ),
    ]


def _build_template_profile(parameters: dict, prior: dict) -> tuple[list[tuple[float, float]], list[dict]]:
    control = parameters["_profile_control"]
    controls = {
        "zmin": float(control["zmin"]),
        "zmax": float(control["zmax"]),
        "beam_radius": float(control["beam_radius"]),
        "transition_radius": float(control["transition_radius"]),
        "equator_radius": float(control["equator_radius"]),
    }
    templates = prior.get("grammar", {}).get("segment_templates", {})
    segments = []
    for segment_id in prior.get("grammar", {}).get("segment_order", []):
        template = templates[str(segment_id)]
        start = _resolve_point(template["start"], controls)
        end = _resolve_point(template["end"], controls)
        segments.append(
            _line(
                str(segment_id),
                start,
                end,
                [str(item) for item in template.get("feature_refs", [])],
                [],
                confidence=float(template.get("confidence", 0.85)),
            )
        )
    return _sample_profile(segments), segments


def _pick_arc(primitives: dict, feature_type: str, *, side: str, major_radius: float | None = None) -> dict | None:
    candidates = [
        primitive
        for primitive in primitives.get("primitives", [])
        if primitive.get("feature_type") == feature_type and primitive.get("kind") == "arc"
    ]
    if side == "left":
        candidates = [item for item in candidates if float(item["center"]["z"]) < 0.0]
    else:
        candidates = [item for item in candidates if float(item["center"]["z"]) > 0.0]
    if major_radius is not None:
        candidates = [item for item in candidates if abs(float(item["major_radius"]) - major_radius) < 1e-3]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (abs(float(item["major_radius"]) - (major_radius or float(item["major_radius"]))), item["face_id"]))[0]


def _pick_bridge(primitives: dict, *, side: str) -> dict | None:
    candidates = primitives.get("bridge_evidence", [])
    if side == "left":
        candidates = [item for item in candidates if float(item["z_range"][0]) < 0.0]
    else:
        candidates = [item for item in candidates if float(item["z_range"][0]) > 0.0]
    return candidates[0] if candidates else None


def _bridge_inner_radius(bridge: dict | None, *, fallback: float) -> float:
    if not bridge:
        return fallback
    return float(max(bridge.get("r_range", [fallback, fallback])))


def _bridge_face_refs(primitive: dict) -> list[str]:
    return [str(primitive.get("face_id", ""))] if primitive.get("face_id") else []


def _arc_center(primitive: dict) -> tuple[float, float]:
    return float(primitive["center"]["z"]), float(primitive["center"]["r"])


def _point(center_z: float, center_r: float, radius: float, angle: float) -> tuple[float, float]:
    return (center_z + radius * math.cos(angle), center_r + radius * math.sin(angle))


def _arc_from_angles(
    segment_id: str,
    primitive: dict,
    start_angle: float,
    end_angle: float,
    feature_refs: list[str],
    *,
    radius_delta: float = 0.0,
) -> dict:
    center_z, center_r = _arc_center(primitive)
    radius = max(1.0, float(primitive["minor_radius"]) + float(radius_delta))
    start = _point(center_z, center_r, radius, start_angle)
    end = _point(center_z, center_r, radius, end_angle)
    mid = _point(center_z, center_r, radius, (start_angle + end_angle) / 2.0)
    return {
        "id": segment_id,
        "kind": "arc",
        "start": {"z": start[0], "r": start[1]},
        "end": {"z": end[0], "r": end[1]},
        "curve": {
            "type": "arc",
            "center": {"z": center_z, "r": center_r},
            "radius": radius,
            "start_angle_rad": start_angle,
            "end_angle_rad": end_angle,
            "mid": {"z": mid[0], "r": mid[1]},
        },
        "feature_refs": feature_refs,
        "face_refs": [primitive["face_id"]],
        "continuity_start": "G1_evidence",
        "continuity_end": "G1_evidence",
        "evidence_refs": [f"face:{primitive['face_id']}"],
        "confidence": 0.92,
    }


def _apply_nose_offsets(points: list[tuple[float, float]], parameters: dict, *, side: str) -> list[tuple[float, float]]:
    result = list(points)
    if side == "left":
        index = 1
    else:
        index = 2
    z, r = result[index]
    result[index] = (
        z + float(parameters.get(f"{side}_inner_delta_z_mm", 0.0)),
        max(1.0, r + float(parameters.get(f"{side}_inner_delta_r_mm", 0.0))),
    )
    return result


def _segment_point(segment: dict, key: str) -> tuple[float, float]:
    point = segment[key]
    return float(point["z"]), float(point["r"])


def _line(
    segment_id: str,
    start: tuple[float, float],
    end: tuple[float, float],
    feature_refs: list[str],
    face_refs: list[str],
    *,
    confidence: float = 0.85,
) -> dict:
    return {
        "id": segment_id,
        "kind": "line",
        "start": {"z": float(start[0]), "r": float(start[1])},
        "end": {"z": float(end[0]), "r": float(end[1])},
        "curve": {"type": "line"},
        "feature_refs": feature_refs,
        "face_refs": face_refs,
        "continuity_start": "G0",
        "continuity_end": "G0",
        "evidence_refs": [f"face:{face_id}" for face_id in face_refs],
        "confidence": confidence,
    }


def _nurbs(
    segment_id: str,
    control_points: list[tuple[float, float]],
    feature_refs: list[str],
    face_refs: list[str],
    fallback_reason: str,
) -> dict:
    return {
        "id": segment_id,
        "kind": "nurbs",
        "start": {"z": float(control_points[0][0]), "r": float(control_points[0][1])},
        "end": {"z": float(control_points[-1][0]), "r": float(control_points[-1][1])},
        "curve": {
            "type": "nurbs",
            "degree": 3,
            "control_points": [{"z": float(z), "r": float(r)} for z, r in control_points],
            "max_control_points": 6,
            "endpoints_fixed": True,
        },
        "feature_refs": feature_refs,
        "face_refs": face_refs,
        "continuity_start": "G1_preferred",
        "continuity_end": "G1_preferred",
        "fallback_reason": fallback_reason,
        "evidence_refs": [f"face:{face_id}" for face_id in face_refs],
        "confidence": 0.76,
    }


def _with_fit_metrics(segments: list[dict], variant_name: str) -> list[dict]:
    for segment in segments:
        segment["variant"] = variant_name
        segment["sampled_points"] = [{"z": z, "r": r} for z, r in _sample_segment(segment)]
        segment["fit_metrics"] = {
            "rms_mm": 0.0 if segment["kind"] == "arc" else None,
            "max_mm": 0.0 if segment["kind"] == "arc" else None,
            "deviation_policy": "evidence_exact" if segment["kind"] == "arc" else "smoothness_preferred_or_bridge",
        }
    return segments


def _sample_profile(segments: list[dict]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for segment in segments:
        sampled = _sample_segment(segment)
        if points and sampled:
            sampled = sampled[1:]
        points.extend(sampled)
    return points


def _sample_segment(segment: dict, samples: int = 12) -> list[tuple[float, float]]:
    kind = segment.get("kind")
    if kind == "arc":
        curve = segment["curve"]
        center = curve["center"]
        return [
            _point(float(center["z"]), float(center["r"]), float(curve["radius"]), angle)
            for angle in _linspace(float(curve["start_angle_rad"]), float(curve["end_angle_rad"]), samples)
        ]
    if kind == "nurbs":
        controls = [(float(point["z"]), float(point["r"])) for point in segment["curve"]["control_points"]]
        return _bezier_points(controls, samples)
    return [
        (float(segment["start"]["z"]), float(segment["start"]["r"])),
        (float(segment["end"]["z"]), float(segment["end"]["r"])),
    ]


def _linspace(start: float, end: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    return [start + (end - start) * i / (count - 1) for i in range(count)]


def _bezier_points(points: list[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points
    result = []
    for t in _linspace(0.0, 1.0, count):
        work = list(points)
        while len(work) > 1:
            work = [
                (a[0] * (1.0 - t) + b[0] * t, a[1] * (1.0 - t) + b[1] * t)
                for a, b in zip(work, work[1:])
            ]
        result.append(work[0])
    return result


def _resolve_point(items: list[object], controls: dict[str, float]) -> tuple[float, float]:
    if len(items) != 2:
        raise ValueError(f"profile point template must contain [z, r], got {items!r}")
    return (_resolve_value(items[0], controls), _resolve_value(items[1], controls))


def _resolve_value(value: object, controls: dict[str, float]) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    value_s = str(value)
    if value_s not in controls:
        raise ValueError(f"unknown profile control token: {value_s}")
    return float(controls[value_s])
