"""Extract axisymmetric profile primitives from reviewed feature evidence."""

from __future__ import annotations

from collections import defaultdict


PROFILE_FEATURE_TYPES = {"NoseCone", "TransitionBlend", "EquatorRegion", "BeamPipeLeft", "BeamPipeRight"}


def extract_profile_primitives(manifest: dict, labels: dict) -> dict:
    """Return curve-ready r-z primitives derived from manifest face records."""
    face_index = {str(face["face_id"]): face for face in manifest.get("faces", [])}
    feature_refs = _feature_face_refs(labels)
    primitives: list[dict] = []
    for feature_type, face_ids in sorted(feature_refs.items()):
        if feature_type not in PROFILE_FEATURE_TYPES:
            continue
        for face_id in sorted(face_ids):
            face = face_index.get(face_id)
            if not face:
                continue
            primitive = _primitive_from_face(face, feature_type)
            if primitive:
                primitives.append(primitive)
    bridge_faces = _bridge_planes(face_index, feature_refs)
    return {
        "schema_version": "profile_primitives.v0",
        "primitives": _dedupe_primitives(primitives),
        "bridge_evidence": bridge_faces,
    }


def _feature_face_refs(labels: dict) -> dict[str, set[str]]:
    confirmed = labels.get("confirmed_features", {}) if isinstance(labels, dict) else {}
    refs: dict[str, set[str]] = defaultdict(set)
    for feature in confirmed.values():
        feature_type = str(feature.get("type"))
        for ref in feature.get("geometry_refs", []):
            ref_s = str(ref)
            if ref_s.startswith("face:"):
                refs[feature_type].add(ref_s.split(":", 1)[1])
    return refs


def _primitive_from_face(face: dict, feature_type: str) -> dict | None:
    surface_type = str(face.get("surface_type"))
    bbox = face.get("bbox", {})
    relation = face.get("axis_relation", {})
    r_range = relation.get("r_range") if isinstance(relation.get("r_range"), list) else None
    z_range = relation.get("z_range") if isinstance(relation.get("z_range"), list) else None
    base = {
        "face_id": str(face["face_id"]),
        "feature_type": feature_type,
        "surface_type": surface_type,
        "z_range": [float(z_range[0]), float(z_range[1])] if z_range else [float(bbox.get("zmin", 0.0)), float(bbox.get("zmax", 0.0))],
        "r_range": [float(r_range[0]), float(r_range[1])] if r_range else [0.0, _face_rmax(face)],
    }
    if surface_type == "torus" and face.get("radius") is not None and face.get("secondary_radius") is not None:
        origin = face.get("surface_origin") or [0.0, 0.0, 0.0]
        return {
            **base,
            "kind": "arc",
            "center": {"z": float(origin[2]), "r": float(face["radius"])},
            "radius": float(face["secondary_radius"]),
            "major_radius": float(face["radius"]),
            "minor_radius": float(face["secondary_radius"]),
        }
    if surface_type == "cylinder" and face.get("radius") is not None:
        return {
            **base,
            "kind": "line",
            "radius": float(face["radius"]),
        }
    if surface_type == "plane":
        return {
            **base,
            "kind": "bridge",
        }
    return None


def _bridge_planes(face_index: dict[str, dict], feature_refs: dict[str, set[str]]) -> list[dict]:
    nose = feature_refs.get("NoseCone", set())
    blend = feature_refs.get("TransitionBlend", set()) | feature_refs.get("EquatorRegion", set())
    bridge_faces = []
    for face in face_index.values():
        if face.get("surface_type") != "plane":
            continue
        adjacent = set(face.get("adjacent_faces", []))
        if adjacent & nose and adjacent & blend:
            primitive = _primitive_from_face(face, "NoseBlendBridge")
            if primitive:
                primitive["adjacent_nose_faces"] = sorted(adjacent & nose)
                primitive["adjacent_blend_faces"] = sorted(adjacent & blend)
                bridge_faces.append(primitive)
    return sorted(bridge_faces, key=lambda item: (item["z_range"][0], item["face_id"]))


def _dedupe_primitives(primitives: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for primitive in sorted(primitives, key=lambda item: (item["feature_type"], item["surface_type"], item["face_id"])):
        key = (
            primitive.get("feature_type"),
            primitive.get("kind"),
            round(float(primitive.get("center", {}).get("z", primitive["z_range"][0])), 6),
            round(float(primitive.get("center", {}).get("r", primitive["r_range"][0])), 6),
            round(float(primitive.get("radius", 0.0)), 6),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(primitive)
    return result


def _face_rmax(face: dict) -> float:
    bbox = face.get("bbox", {})
    return max(abs(float(bbox.get(key, 0.0))) for key in ("xmin", "xmax", "ymin", "ymax"))
