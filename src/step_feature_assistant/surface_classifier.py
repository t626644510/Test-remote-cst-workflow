"""Geometry utility functions used by the STEP feature assistant.

The v0 reader can operate without an installed CAD kernel.  Measurements from
that fallback path are approximate because STEP topology text preserves face
definitions and boundary vertices, but not sampled surface integration.
"""

from __future__ import annotations

import hashlib
import math
from typing import Iterable, List, Optional, Sequence, Tuple

Point3 = Tuple[float, float, float]
Vector3 = Tuple[float, float, float]


SURFACE_TYPE_MAP = {
    "PLANE": "plane",
    "CYLINDRICAL_SURFACE": "cylinder",
    "CONICAL_SURFACE": "cone",
    "SPHERICAL_SURFACE": "sphere",
    "TOROIDAL_SURFACE": "torus",
    "B_SPLINE_SURFACE": "bspline",
    "B_SPLINE_SURFACE_WITH_KNOTS": "bspline",
    "SURFACE_OF_REVOLUTION": "surface_of_revolution",
}


def classify_step_surface_type(step_type: str) -> str:
    """Map a STEP surface entity name to the manifest surface vocabulary."""
    return SURFACE_TYPE_MAP.get(step_type.upper(), "unknown")


def axis_index(axis: str) -> int:
    """Return the coordinate index for an axis label."""
    axis_l = axis.lower()
    if axis_l == "x":
        return 0
    if axis_l == "y":
        return 1
    if axis_l == "z":
        return 2
    raise ValueError(f"Unsupported axis: {axis}")


def normalize(vector: Sequence[float]) -> Vector3:
    """Return a normalized 3D vector, or zero vector for zero input."""
    length = math.sqrt(sum(float(v) * float(v) for v in vector))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return tuple(float(v) / length for v in vector[:3])  # type: ignore[return-value]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product for two 3D vectors."""
    return sum(float(x) * float(y) for x, y in zip(a[:3], b[:3]))


def cross(a: Sequence[float], b: Sequence[float]) -> Vector3:
    """Cross product for two 3D vectors."""
    ax, ay, az = (float(v) for v in a[:3])
    bx, by, bz = (float(v) for v in b[:3])
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def principal_axis(vector: Optional[Sequence[float]], tolerance: float = 0.95) -> Optional[str]:
    """Return x/y/z if a vector is nearly parallel to a principal axis."""
    if vector is None:
        return None
    v = normalize(vector)
    axes = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
    best_axis = None
    best_score = 0.0
    for name, basis in axes.items():
        score = abs(dot(v, basis))
        if score > best_score:
            best_axis = name
            best_score = score
    return best_axis if best_score >= tolerance else None


def centroid(points: Sequence[Point3]) -> Point3:
    """Return the arithmetic centroid of boundary points."""
    if not points:
        return (0.0, 0.0, 0.0)
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
        sum(p[2] for p in points) / len(points),
    )


def bbox(points: Sequence[Point3]) -> dict:
    """Return an axis-aligned bounding box."""
    if not points:
        return {
            "xmin": None,
            "xmax": None,
            "ymin": None,
            "ymax": None,
            "zmin": None,
            "zmax": None,
        }
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {
        "xmin": min(xs),
        "xmax": max(xs),
        "ymin": min(ys),
        "ymax": max(ys),
        "zmin": min(zs),
        "zmax": max(zs),
    }


def estimate_normal(
    points: Sequence[Point3],
    surface_type: str,
    centroid_point: Point3,
    placement_axis: Optional[Sequence[float]],
    placement_origin: Optional[Sequence[float]],
) -> Vector3:
    """Estimate a face normal from STEP placement data or boundary points."""
    if surface_type == "plane" and placement_axis is not None:
        return normalize(placement_axis)
    if surface_type in {"cylinder", "cone", "torus", "sphere"} and placement_origin is not None:
        origin = tuple(float(v) for v in placement_origin[:3])
        radial = (
            centroid_point[0] - origin[0],
            centroid_point[1] - origin[1],
            centroid_point[2] - origin[2],
        )
        if placement_axis is not None:
            axis_v = normalize(placement_axis)
            axial_component = dot(radial, axis_v)
            radial = (
                radial[0] - axial_component * axis_v[0],
                radial[1] - axial_component * axis_v[1],
                radial[2] - axial_component * axis_v[2],
            )
        return normalize(radial)
    if len(points) >= 3:
        base = points[0]
        for i in range(1, len(points) - 1):
            v1 = (points[i][0] - base[0], points[i][1] - base[1], points[i][2] - base[2])
            v2 = (
                points[i + 1][0] - base[0],
                points[i + 1][1] - base[1],
                points[i + 1][2] - base[2],
            )
            n = normalize(cross(v1, v2))
            if any(abs(value) > 1e-9 for value in n):
                return n
    return (0.0, 0.0, 0.0)


def axis_relation(
    points: Sequence[Point3],
    model_axis: str,
    surface_type: str,
    placement_axis: Optional[Sequence[float]],
    placement_origin: Optional[Sequence[float]],
    declared_radius: Optional[float] = None,
) -> dict:
    """Describe how a face relates to the requested beam axis."""
    idx = axis_index(model_axis)
    radial_indices = [i for i in range(3) if i != idx]
    axis_values = [p[idx] for p in points]
    radial_values = [math.hypot(p[radial_indices[0]], p[radial_indices[1]]) for p in points]

    if placement_axis is not None:
        model_basis = [0.0, 0.0, 0.0]
        model_basis[idx] = 1.0
        parallel_score = abs(dot(normalize(placement_axis), model_basis))
    else:
        parallel_score = None

    if placement_origin is not None:
        axis_offset = math.hypot(
            float(placement_origin[radial_indices[0]]),
            float(placement_origin[radial_indices[1]]),
        )
    else:
        axis_offset = None

    radius_mean = sum(radial_values) / len(radial_values) if radial_values else declared_radius
    max_radius = max(radial_values) if radial_values else declared_radius
    offset_limit = max(1e-6, float(max_radius or declared_radius or 1.0) * 0.05)
    is_axis_surface = surface_type in {
        "cylinder",
        "cone",
        "sphere",
        "torus",
        "surface_of_revolution",
        "bspline",
    }
    is_axisymmetric = bool(
        is_axis_surface
        and (parallel_score is None or parallel_score >= 0.95)
        and (axis_offset is None or axis_offset <= offset_limit)
    )

    return {
        "model_axis": model_axis.lower(),
        "is_axisymmetric": is_axisymmetric,
        "axis_parallel_score": parallel_score,
        "axis_offset": axis_offset,
        "radius_mean": radius_mean,
        "r_range": [min(radial_values), max(radial_values)] if radial_values else [None, None],
        "z_range": [min(axis_values), max(axis_values)] if axis_values else [None, None],
    }


def estimate_area(
    points: Sequence[Point3],
    surface_type: str,
    model_axis: str,
    declared_radius: Optional[float] = None,
    secondary_radius: Optional[float] = None,
) -> Tuple[float, str]:
    """Estimate face area from boundary vertices and analytic hints.

    The fallback STEP parser does not perform exact surface integration.  The
    returned method string is included in the manifest for review.
    """
    if len(points) < 2:
        return (0.0, "insufficient_boundary_points")

    if surface_type == "plane" and len(points) >= 3:
        return (_newell_area(points), "newell_polygon_from_boundary_vertices")

    idx = axis_index(model_axis)
    radial_indices = [i for i in range(3) if i != idx]
    axis_values = [p[idx] for p in points]
    radial_values = [math.hypot(p[radial_indices[0]], p[radial_indices[1]]) for p in points]
    radius = declared_radius or (sum(radial_values) / len(radial_values) if radial_values else 0.0)
    span = max(axis_values) - min(axis_values) if axis_values else 0.0
    angle = _angular_span(points, model_axis)

    if surface_type == "cylinder" and radius:
        return (abs(radius * angle * span), "cylinder_radius_angle_axis_span")
    if surface_type == "cone" and radius:
        slant = math.hypot(span, max(radial_values) - min(radial_values) if radial_values else 0.0)
        return (abs(radius * angle * slant), "cone_mean_radius_angle_slant_span")
    if surface_type == "torus" and radius and secondary_radius:
        return (abs(radius * secondary_radius * max(angle, 1e-9)), "torus_segment_rough_estimate")

    box = bbox(points)
    extents = [
        abs(float(box["xmax"] or 0.0) - float(box["xmin"] or 0.0)),
        abs(float(box["ymax"] or 0.0) - float(box["ymin"] or 0.0)),
        abs(float(box["zmax"] or 0.0) - float(box["zmin"] or 0.0)),
    ]
    extents.sort(reverse=True)
    return (extents[0] * extents[1], "bbox_two_largest_extents")


def face_fingerprint(
    surface_type: str,
    area: float,
    center: Sequence[float],
    box: dict,
    edge_count: int,
    precision: int = 4,
) -> str:
    """Build a stable-ish fingerprint for matching faces across reimports."""
    payload = {
        "surface_type": surface_type,
        "area": round(area, precision),
        "centroid": [round(float(value), precision) for value in center],
        "bbox": {key: round(float(value), precision) if value is not None else None for key, value in box.items()},
        "edge_count": edge_count,
    }
    raw = repr(payload).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _newell_area(points: Sequence[Point3]) -> float:
    nx = ny = nz = 0.0
    pts = list(points)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    for i, current in enumerate(pts):
        nxt = pts[(i + 1) % len(pts)]
        nx += (current[1] - nxt[1]) * (current[2] + nxt[2])
        ny += (current[2] - nxt[2]) * (current[0] + nxt[0])
        nz += (current[0] - nxt[0]) * (current[1] + nxt[1])
    return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)


def _angular_span(points: Sequence[Point3], model_axis: str) -> float:
    idx = axis_index(model_axis)
    radial_indices = [i for i in range(3) if i != idx]
    angles = sorted(math.atan2(p[radial_indices[1]], p[radial_indices[0]]) for p in points)
    if len(angles) < 2:
        return 2.0 * math.pi
    gaps = [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
    gaps.append((angles[0] + 2.0 * math.pi) - angles[-1])
    largest_gap = max(gaps)
    span = 2.0 * math.pi - largest_gap
    # Sparse circular faces often only expose quadrant points; do not collapse
    # them to a tiny wedge.
    return max(span, math.pi / 2.0)


def unique_points(points: Iterable[Point3], precision: int = 9) -> List[Point3]:
    """Return boundary points with duplicate coordinates removed."""
    seen = set()
    result: List[Point3] = []
    for point in points:
        key = tuple(round(value, precision) for value in point)
        if key in seen:
            continue
        seen.add(key)
        result.append(point)
    return result
