"""Stable feature extraction shared by calibration and classifiers."""

from __future__ import annotations

from typing import Mapping


NUMERIC_FEATURES = [
    "area",
    "area_ratio",
    "radius_mean",
    "radius_ratio",
    "axis_center_norm",
    "axis_span_norm",
    "radial_span",
    "edge_count",
    "adjacent_count",
    "axisymmetric",
    "normal_axis_abs",
    "bbox_dx",
    "bbox_dy",
    "bbox_dz",
]
CATEGORICAL_FEATURES = ["surface_type"]


def face_feature_row(manifest: dict, face: Mapping[str, object], project_id: str) -> dict:
    """Return normalized, model-size-independent features for one face."""
    summary = manifest.get("model_summary", {})
    box = summary.get("bbox", {})
    axis = str(summary.get("detected_axis", "z"))
    axis_min = float(box.get(f"{axis}min") or 0.0)
    axis_max = float(box.get(f"{axis}max") or 0.0)
    axis_span = max(axis_max - axis_min, 1e-12)
    model_area = _bbox_surface_area(box)
    model_radius = _model_radius(box, axis)
    relation = face.get("axis_relation", {}) if isinstance(face.get("axis_relation"), Mapping) else {}
    z_range = relation.get("z_range", [None, None])
    axis_low = float(z_range[0]) if isinstance(z_range, list) and z_range[0] is not None else _centroid_axis(face, axis)
    axis_high = float(z_range[1]) if isinstance(z_range, list) and z_range[1] is not None else axis_low
    r_range = relation.get("r_range", [None, None])
    r_min = float(r_range[0]) if isinstance(r_range, list) and r_range[0] is not None else 0.0
    r_max = float(r_range[1]) if isinstance(r_range, list) and r_range[1] is not None else r_min
    radius_mean = float(relation.get("radius_mean") or face.get("radius") or 0.0)
    normal = face.get("normal_estimate", [0.0, 0.0, 0.0])
    axis_index = {"x": 0, "y": 1, "z": 2}[axis]
    face_box = face.get("bbox", {}) if isinstance(face.get("bbox"), Mapping) else {}
    return {
        "project_id": project_id,
        "face_id": str(face.get("face_id")),
        "surface_type": str(face.get("surface_type", "unknown")),
        "area": float(face.get("area") or 0.0),
        "area_ratio": float(face.get("area") or 0.0) / max(model_area, 1e-12),
        "radius_mean": radius_mean,
        "radius_ratio": radius_mean / max(model_radius, 1e-12),
        "axis_center_norm": (((axis_low + axis_high) / 2.0) - axis_min) / axis_span,
        "axis_span_norm": (axis_high - axis_low) / axis_span,
        "radial_span": r_max - r_min,
        "edge_count": int(face.get("edge_count") or 0),
        "adjacent_count": len(face.get("adjacent_faces", []) or []),
        "axisymmetric": int(bool(relation.get("is_axisymmetric"))),
        "normal_axis_abs": abs(float(normal[axis_index])) if isinstance(normal, list) and len(normal) > axis_index else 0.0,
        "bbox_dx": _extent(face_box, "x"),
        "bbox_dy": _extent(face_box, "y"),
        "bbox_dz": _extent(face_box, "z"),
    }


def _bbox_surface_area(box: Mapping[str, object]) -> float:
    dx, dy, dz = _extent(box, "x"), _extent(box, "y"), _extent(box, "z")
    return 2.0 * (dx * dy + dy * dz + dx * dz)


def _model_radius(box: Mapping[str, object], axis: str) -> float:
    radial = [name for name in ("x", "y", "z") if name != axis]
    return max(_extent(box, radial[0]), _extent(box, radial[1])) / 2.0


def _extent(box: Mapping[str, object], axis: str) -> float:
    return abs(float(box.get(f"{axis}max") or 0.0) - float(box.get(f"{axis}min") or 0.0))


def _centroid_axis(face: Mapping[str, object], axis: str) -> float:
    center = face.get("centroid", [0.0, 0.0, 0.0])
    return float(center[{"x": 0, "y": 1, "z": 2}[axis]])
