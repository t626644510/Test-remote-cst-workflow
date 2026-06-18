"""Generate reviewable RF feature candidates from a geometry manifest."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set

from .adjacency_builder import connected_components
from .model_profiles import load_model_profile
from .topology_analyzer import face_groups_by_surface_and_adjacency


def generate_feature_graph_draft(
    geometry_manifest: dict,
    model_type: str,
    axis: str,
    hints: Optional[Mapping[str, object]] = None,
    rules: Optional[Mapping[str, object]] = None,
) -> dict:
    """Generate candidate RF features from objective geometry facts."""
    hints = hints or {}
    profile = dict(rules or load_model_profile(model_type))
    faces = geometry_manifest.get("faces", [])
    face_map = {face["face_id"]: face for face in faces}
    adjacency = {face["face_id"]: face.get("adjacent_faces", []) for face in faces}
    bbox = geometry_manifest.get("model_summary", {}).get("bbox", {})
    axis_min, axis_max = _axis_bounds(bbox, axis)
    axis_span = max(axis_max - axis_min, 1e-9)
    max_radius = _max_radius(faces)
    axisymmetric_max_radius = _max_radius(
        [face for face in faces if face.get("axis_relation", {}).get("is_axisymmetric")]
    ) or max_radius

    features: List[dict] = []
    assigned_faces: Set[str] = set()
    id_counts: defaultdict[str, int] = defaultdict(int)

    def add_feature(
        feature_type: str,
        geometry_refs: Sequence[str],
        confidence: float,
        evidence: Sequence[str],
        default_boundary_role: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        refs = sorted(set(geometry_refs))
        if not refs:
            return
        id_counts[feature_type] += 1
        feature_id = f"{_slug(feature_type)}_candidate_{id_counts[feature_type]:02d}"
        record = {
            "id": feature_id,
            "type": feature_type,
            "geometry_refs": [_geometry_ref(value) for value in refs],
            "confidence": round(float(confidence), 3),
            "evidence": list(evidence),
            "status": "candidate",
            "requires_human_review": True,
        }
        if default_boundary_role is not None:
            record["default_boundary_role"] = default_boundary_role
        if metadata:
            record["metadata"] = metadata
        features.append(record)
        assigned_faces.update(value for value in refs if value.startswith("F"))

    if geometry_manifest.get("model_summary", {}).get("solid_count", 0):
        add_feature(
            "RFVacuumVolume",
            [f"solid:S{i + 1:04d}" for i in range(geometry_manifest["model_summary"]["solid_count"])],
            0.8,
            ["STEP model contains manifold solid body/bodies"],
        )

    _add_beam_pipe_candidates(
        faces,
        adjacency,
        axis_min,
        axis_max,
        axis_span,
        axisymmetric_max_radius,
        profile,
        add_feature,
    )
    _add_end_face_candidates(
        faces,
        axis_min,
        axis_max,
        axis_span,
        model_type,
        profile,
        add_feature,
    )
    _add_axisymmetric_wall_candidates(faces, adjacency, axisymmetric_max_radius, profile, add_feature)
    _add_iris_and_equator_candidates(faces, adjacency, axis_min, axis_max, axis_span, axisymmetric_max_radius, profile, add_feature)
    _add_blend_candidates(faces, adjacency, axisymmetric_max_radius, profile, add_feature)
    if bool(profile.get("enable_side_ports", True)):
        _add_coupler_candidates(faces, adjacency, max_radius, profile, add_feature)
    _add_hint_candidates(face_map, hints, axis_min, axis_max, add_feature)

    face_groups = face_groups_by_surface_and_adjacency(geometry_manifest)
    face_ids = {face["face_id"] for face in faces}
    unassigned_faces = sorted(face_ids - assigned_faces)
    detected_types = {feature["type"] for feature in features}
    expected = [str(value) for value in hints.get("expected_features", [])] if isinstance(hints.get("expected_features"), list) else []
    missing_expected = [value for value in expected if not _expected_feature_present(value, detected_types)]
    return {
        "schema_version": "0.1",
        "source_geometry_manifest": "geometry_manifest.json",
        "model_type": model_type,
        "axis": axis.lower(),
        "rules_profile": profile,
        "features": features,
        "face_groups": face_groups,
        "unassigned_faces": unassigned_faces,
        "missing_expected_features": missing_expected,
        "notes": [
            "All feature classifications are candidates until reviewed by a human.",
            "geometry_manifest.json is the source of objective geometry facts; this file contains engineering semantics.",
        ],
    }


def _add_beam_pipe_candidates(
    faces: Sequence[dict],
    adjacency: Mapping[str, Sequence[str]],
    axis_min: float,
    axis_max: float,
    axis_span: float,
    max_radius: float,
    profile: Mapping[str, object],
    add_feature,
) -> None:
    left = []
    right = []
    for face in faces:
        relation = face.get("axis_relation", {})
        center_axis = _center_axis(face)
        radius = _radius_mean(face)
        if face.get("surface_type") != "cylinder":
            continue
        if not relation.get("is_axisymmetric"):
            continue
        if radius is None or radius > float(profile["beam_pipe_radius_max_ratio"]) * max_radius:
            continue
        evidence = [
            "cylindrical face aligned with beam axis",
            "radius smaller than main cavity radius",
        ]
        end_fraction = float(profile["beam_pipe_end_fraction"])
        if center_axis <= axis_min + end_fraction * axis_span:
            left.append(face["face_id"])
        elif center_axis >= axis_max - end_fraction * axis_span:
            right.append(face["face_id"])
    for side, refs in (("Left", left), ("Right", right)):
        if not refs:
            continue
        for component in connected_components(refs, adjacency):
            add_feature(
                f"BeamPipe{side}",
                component,
                0.78,
                [
                    "cylindrical faces aligned with z axis",
                    f"located near {'z_min' if side == 'Left' else 'z_max'}",
                    "radius smaller than main cavity radius",
                ],
                default_boundary_role="open_or_electric_by_recipe",
            )


def _add_end_face_candidates(
    faces: Sequence[dict],
    axis_min: float,
    axis_max: float,
    axis_span: float,
    model_type: str,
    profile: Mapping[str, object],
    add_feature,
) -> None:
    for face in faces:
        if face.get("surface_type") != "plane":
            continue
        center_axis = _center_axis(face)
        end_fraction = float(profile["end_face_fraction"])
        near_min = center_axis <= axis_min + end_fraction * axis_span
        near_max = center_axis >= axis_max - end_fraction * axis_span
        if not (near_min or near_max):
            continue
        if near_min and bool(profile.get("enable_cathode_at_axis_min", False)):
            add_feature(
                "CathodeSurface",
                [face["face_id"]],
                0.72,
                ["planar face near z_min", "xband gun model type suggests cathode end"],
                default_boundary_role="electric",
            )
        else:
            add_feature(
                "BeamAperture" if near_min else "BeamExit",
                [face["face_id"]],
                0.64,
                [f"planar end face near {'z_min' if near_min else 'z_max'}"],
                default_boundary_role="open_or_electric_by_recipe",
            )


def _add_axisymmetric_wall_candidates(
    faces: Sequence[dict],
    adjacency: Mapping[str, Sequence[str]],
    max_radius: float,
    profile: Mapping[str, object],
    add_feature,
) -> None:
    refs = [
        face["face_id"]
        for face in faces
        if face.get("surface_type") in {"cylinder", "torus", "cone", "surface_of_revolution", "bspline"}
        and face.get("axis_relation", {}).get("is_axisymmetric")
        and (_r_max(face) or 0.0) >= float(profile["wall_radius_min_ratio"]) * max_radius
    ]
    for component in connected_components(refs, adjacency):
        add_feature(
            "ConductingWall",
            component,
            0.7,
            ["axisymmetric cavity wall-like faces", "large radius relative to model"],
            default_boundary_role="electric",
            metadata={"suggested_material": "copper_or_conducting_wall"},
        )


def _add_iris_and_equator_candidates(
    faces: Sequence[dict],
    adjacency: Mapping[str, Sequence[str]],
    axis_min: float,
    axis_max: float,
    axis_span: float,
    max_radius: float,
    profile: Mapping[str, object],
    add_feature,
) -> None:
    iris_refs = []
    equator_refs = []
    for face in faces:
        if not face.get("axis_relation", {}).get("is_axisymmetric"):
            continue
        center_axis = _center_axis(face)
        margin = float(profile["interior_margin_fraction"])
        if center_axis <= axis_min + margin * axis_span or center_axis >= axis_max - margin * axis_span:
            continue
        rmax = _r_max(face) or 0.0
        if rmax <= float(profile["iris_radius_max_ratio"]) * max_radius:
            iris_refs.append(face["face_id"])
        elif rmax >= float(profile["equator_radius_min_ratio"]) * max_radius:
            equator_refs.append(face["face_id"])
    for component in connected_components(iris_refs, adjacency):
        add_feature(
            "Iris",
            component,
            0.62,
            ["axisymmetric constriction candidate", "small radius relative to cavity body", "not located at model end"],
        )
    for component in connected_components(equator_refs, adjacency):
        add_feature(
            "EquatorRegion",
            component,
            0.6,
            ["axisymmetric large-radius region", "interior location"],
        )


def _add_blend_candidates(
    faces: Sequence[dict],
    adjacency: Mapping[str, Sequence[str]],
    max_radius: float,
    profile: Mapping[str, object],
    add_feature,
) -> None:
    refs = []
    for face in faces:
        surface_type = face.get("surface_type")
        radius = face.get("secondary_radius") or face.get("radius") or _radius_mean(face)
        if surface_type not in {"torus", "cone", "bspline", "cylinder"}:
            continue
        if radius is None:
            continue
        if radius <= float(profile["blend_radius_max_ratio"]) * max_radius and len(face.get("adjacent_faces", [])) >= 2:
            refs.append(face["face_id"])
    for component in connected_components(refs, adjacency):
        add_feature(
            "TransitionBlend",
            component,
            0.58,
            ["small-radius curved or conical face", "connects at least two adjacent faces"],
        )


def _add_coupler_candidates(
    faces: Sequence[dict],
    adjacency: Mapping[str, Sequence[str]],
    max_radius: float,
    profile: Mapping[str, object],
    add_feature,
) -> None:
    refs = []
    for face in faces:
        relation = face.get("axis_relation", {})
        if relation.get("is_axisymmetric"):
            continue
        radius = _radius_mean(face) or 0.0
        normal = face.get("normal_estimate") or [0.0, 0.0, 0.0]
        normal_not_z = abs(float(normal[2])) < 0.85
        if radius >= float(profile["side_port_radius_min_ratio"]) * max_radius and normal_not_z:
            refs.append(face["face_id"])
    for component in connected_components(refs, adjacency):
        add_feature(
            "UnknownSidePort",
            component,
            0.5,
            ["non-axisymmetric side-wall face group", "normal not parallel to beam axis"],
            default_boundary_role="port_or_open_by_recipe",
        )


def _add_hint_candidates(
    face_map: Mapping[str, dict],
    hints: Mapping[str, object],
    axis_min: float,
    axis_max: float,
    add_feature,
) -> None:
    known_faces = hints.get("known_faces", {}) if isinstance(hints, Mapping) else {}
    if not isinstance(known_faces, Mapping):
        return
    for label, spec in known_faces.items():
        if not isinstance(spec, Mapping):
            continue
        approx = spec.get("approximate_location")
        feature_type = _hint_label_to_feature_type(str(label))
        refs = []
        if approx in {"z_min", "axis_min"}:
            refs = _faces_near_axis_value(face_map.values(), axis_min)
        elif approx in {"z_max", "axis_max"}:
            refs = _faces_near_axis_value(face_map.values(), axis_max)
        explicit = spec.get("geometry_refs")
        if isinstance(explicit, list):
            refs = [str(value).replace("face:", "") for value in explicit]
        add_feature(
            feature_type,
            refs,
            0.55,
            [f"user hint known_faces.{label}", f"approximate_location={approx}"],
        )


def _faces_near_axis_value(faces: Iterable[dict], axis_value: float) -> List[str]:
    scored = []
    for face in faces:
        center = _center_axis(face)
        scored.append((abs(center - axis_value), face["face_id"]))
    return [face_id for _, face_id in sorted(scored)[:3]]


def _hint_label_to_feature_type(label: str) -> str:
    return {
        "cathode": "CathodeSurface",
        "beam_exit": "BeamExit",
        "beam_aperture": "BeamAperture",
        "coupler": "UnknownSidePort",
    }.get(label.lower(), label.title().replace("_", ""))


def _axis_bounds(box: Mapping[str, object], axis: str) -> tuple[float, float]:
    prefix = axis.lower()
    min_value = box.get(f"{prefix}min")
    max_value = box.get(f"{prefix}max")
    return float(min_value or 0.0), float(max_value or 0.0)


def _max_radius(faces: Sequence[dict]) -> float:
    values = [float(_r_max(face) or 0.0) for face in faces]
    return max(values) if values else 1.0


def _center_axis(face: Mapping[str, object]) -> float:
    relation = face.get("axis_relation", {})
    if isinstance(relation, Mapping):
        values = relation.get("z_range")
        if isinstance(values, list) and len(values) == 2 and values[0] is not None and values[1] is not None:
            return (float(values[0]) + float(values[1])) / 2.0
    center = face.get("centroid", [0.0, 0.0, 0.0])
    return float(center[2]) if isinstance(center, list) and len(center) >= 3 else 0.0


def _radius_mean(face: Mapping[str, object]) -> Optional[float]:
    relation = face.get("axis_relation", {})
    if isinstance(relation, Mapping) and relation.get("radius_mean") is not None:
        return float(relation["radius_mean"])
    radius = face.get("radius")
    return float(radius) if radius is not None else None


def _r_max(face: Mapping[str, object]) -> Optional[float]:
    relation = face.get("axis_relation", {})
    if isinstance(relation, Mapping):
        values = relation.get("r_range")
        if isinstance(values, list) and len(values) == 2 and values[1] is not None:
            return float(values[1])
    return _radius_mean(face)


def _slug(value: str) -> str:
    chars = []
    previous_lower = False
    for char in value:
        if char.isupper() and previous_lower:
            chars.append("_")
        if char.isalnum():
            chars.append(char.lower())
            previous_lower = char.islower() or char.isdigit()
        else:
            chars.append("_")
            previous_lower = False
    return "_".join(part for part in "".join(chars).split("_") if part)


def _expected_feature_present(expected: str, detected: Set[str]) -> bool:
    aliases = {
        "BeamPipe": {"BeamPipeLeft", "BeamPipeRight"},
        "CavityWall": {"ConductingWall"},
        "CouplerPort": {"UnknownSidePort", "InputCouplerPort", "WaveguidePort", "CoaxialPort"},
    }
    return expected in detected or bool(aliases.get(expected, set()) & detected)


def _geometry_ref(value: str) -> str:
    if value.startswith(("face:", "face_group:", "solid:")):
        return value
    if value.startswith("F"):
        return f"face:{value}"
    if value.startswith("G"):
        return f"face_group:{value}"
    return value
