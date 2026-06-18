"""CadQuery worker process for exact STEP geometry measurements."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import sys
from typing import Iterable, Mapping, Optional, Sequence

from .adjacency_builder import build_face_adjacency
from .surface_classifier import axis_relation, face_fingerprint, unique_points


SURFACE_TYPE_MAP = {
    "PLANE": "plane",
    "CYLINDER": "cylinder",
    "CONE": "cone",
    "SPHERE": "sphere",
    "TORUS": "torus",
    "BSPLINE": "bspline",
    "BEZIER": "bspline",
    "REVOLUTION": "surface_of_revolution",
    "OFFSET": "unknown",
    "OTHER": "unknown",
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="step_feature_assistant.cadquery_worker")
    parser.add_argument("--step-file", type=Path, required=True)
    parser.add_argument("--axis", choices=("x", "y", "z"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mesh-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        manifest = build_cadquery_geometry_manifest(args.step_file, args.axis, args.mesh_output)
        args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    except BaseException as exc:
        print(f"CadQuery worker failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        sys.stderr.flush()
        os._exit(1)


def build_cadquery_geometry_manifest(
    step_file: Path,
    axis: str,
    mesh_output: Optional[Path] = None,
) -> dict:
    import cadquery as cq

    workplane = cq.importers.importStep(str(step_file))
    shape = workplane.val()
    solids = list(shape.Solids())
    shells = list(shape.Shells())
    faces = list(shape.Faces())
    edges = list(shape.Edges())
    model_bbox = _bbox_dict(shape.BoundingBox())
    tolerance = _mesh_tolerance(model_bbox)

    edge_hash_to_ref = {
        _shape_hash(edge): f"E{index:04d}"
        for index, edge in enumerate(edges, start=1)
    }
    face_membership = _build_face_membership(solids)
    face_edges = {}
    face_records = []
    face_meshes = []
    for index, face in enumerate(faces, start=1):
        face_id = f"F{index:04d}"
        edge_refs = [_edge_ref(edge, edge_hash_to_ref) for edge in face.Edges()]
        face_edges[face_id] = edge_refs
        record = _build_face_record(face_id, index, face, edge_refs, axis, face_membership)
        face_records.append(record)
        if mesh_output is not None:
            face_meshes.append(_tessellate_face(face_id, face, tolerance))

    adjacency = build_face_adjacency(face_edges)
    for face in face_records:
        face["adjacent_faces"] = adjacency.get(face["face_id"], [])

    manifest = {
        "schema_version": "0.1",
        "source_step": str(step_file),
        "reader": {
            "backend": "cadquery_ocp",
            "cadquery_version": cq.__version__,
            "units": _parse_length_unit(step_file),
            "measurement_quality": "cad_kernel",
            "limitations": [
                "CadQuery/OCP provides CAD-kernel measurements; semantic feature labels remain candidates.",
                "Face ids are stable within this import, but may change after STEP re-export; use fingerprints for matching.",
            ],
            "backend_notes": [
                "CadQuery backend executed in isolated worker process to avoid local Windows interpreter shutdown crash.",
            ],
        },
        "model_summary": {
            "solid_count": len(solids),
            "shell_count": len(shells),
            "face_count": len(faces),
            "edge_count": len(edges),
            "bbox": model_bbox,
            "detected_axis": axis.lower(),
            "entity_counts": {},
        },
        "faces": face_records,
    }
    if mesh_output is not None:
        mesh_output.parent.mkdir(parents=True, exist_ok=True)
        mesh_output.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "source_step": str(step_file),
                    "tolerance": tolerance,
                    "faces": face_meshes,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    return manifest


def _build_face_record(face_id: str, index: int, face, edge_refs: Sequence[str], axis: str, membership: Mapping[int, dict]) -> dict:
    surface_step_type = _safe_geom_type(face)
    surface_type = SURFACE_TYPE_MAP.get(surface_step_type.upper(), "unknown")
    surface_props = _surface_properties(face, surface_type)
    center = _vector_tuple(face.Center())
    bbox = _bbox_dict(face.BoundingBox())
    vertices = unique_points(_vertex_points(face.Vertices()))
    if not vertices:
        vertices = _bbox_corner_points(bbox)
    relation = axis_relation(
        vertices,
        axis,
        surface_type,
        placement_axis=surface_props.get("axis"),
        placement_origin=surface_props.get("origin"),
        declared_radius=surface_props.get("radius"),
    )
    normal = _safe_normal(face)
    area = float(face.Area())
    fingerprint = face_fingerprint(surface_type, area, center, bbox, len(edge_refs))
    member = membership.get(_shape_hash(face), {})
    return {
        "face_id": face_id,
        "occ_index": index,
        "step_face_id": None,
        "surface_step_id": None,
        "surface_type": surface_type,
        "step_surface_type": surface_step_type,
        "area": area,
        "area_method": "cadquery_ocp_area",
        "area_confidence": 0.95,
        "measurement_quality": "cad_kernel",
        "centroid": list(center),
        "normal_estimate": list(normal),
        "principal_axis": _principal_axis_from_vector(surface_props.get("axis")),
        "surface_axis": list(surface_props["axis"]) if surface_props.get("axis") else None,
        "surface_origin": list(surface_props["origin"]) if surface_props.get("origin") else None,
        "radius": surface_props.get("radius") or _radius_from_relation_or_bbox(relation, surface_type),
        "secondary_radius": surface_props.get("secondary_radius"),
        "semi_angle": surface_props.get("semi_angle"),
        "bbox": bbox,
        "axis_relation": relation,
        "edge_count": len(edge_refs),
        "edge_refs": list(edge_refs),
        "adjacent_faces": [],
        "fingerprint": fingerprint,
        "cadquery_hash": _shape_hash(face),
        "solid_refs": member.get("solid_refs", []),
        "shell_refs": member.get("shell_refs", []),
        "backend_notes": [],
    }


def _build_face_membership(solids: Sequence[object]) -> dict[int, dict]:
    membership: dict[int, dict] = defaultdict(lambda: {"solid_refs": [], "shell_refs": []})
    shell_counter = 0
    for solid_index, solid in enumerate(solids, start=1):
        solid_ref = f"solid:S{solid_index:04d}"
        for shell in solid.Shells():
            shell_counter += 1
            shell_ref = f"shell:H{shell_counter:04d}"
            for face in shell.Faces():
                entry = membership[_shape_hash(face)]
                if solid_ref not in entry["solid_refs"]:
                    entry["solid_refs"].append(solid_ref)
                if shell_ref not in entry["shell_refs"]:
                    entry["shell_refs"].append(shell_ref)
    return dict(membership)


def _safe_geom_type(shape) -> str:
    try:
        return str(shape.geomType())
    except Exception:
        return "UNKNOWN"


def _safe_normal(face) -> tuple[float, float, float]:
    try:
        return _vector_tuple(face.normalAt())
    except Exception:
        return (0.0, 0.0, 0.0)


def _surface_properties(face, surface_type: str) -> dict:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        surface = BRepAdaptor_Surface(face.wrapped, True)
        if surface_type == "plane":
            plane = surface.Plane()
            axis, origin = _axis_origin_from_position(plane.Position())
            return {"axis": axis, "origin": origin, "radius": None, "secondary_radius": None, "semi_angle": None}
        if surface_type == "cylinder":
            cylinder = surface.Cylinder()
            axis, origin = _axis_origin_from_position(cylinder.Position())
            return {
                "axis": axis,
                "origin": origin,
                "radius": float(cylinder.Radius()),
                "secondary_radius": None,
                "semi_angle": None,
            }
        if surface_type == "cone":
            cone = surface.Cone()
            axis, origin = _axis_origin_from_position(cone.Position())
            return {
                "axis": axis,
                "origin": origin,
                "radius": float(cone.RefRadius()),
                "secondary_radius": None,
                "semi_angle": float(cone.SemiAngle()),
            }
        if surface_type == "sphere":
            sphere = surface.Sphere()
            axis, origin = _axis_origin_from_position(sphere.Position())
            return {
                "axis": axis,
                "origin": origin,
                "radius": float(sphere.Radius()),
                "secondary_radius": None,
                "semi_angle": None,
            }
        if surface_type == "torus":
            torus = surface.Torus()
            axis, origin = _axis_origin_from_position(torus.Position())
            return {
                "axis": axis,
                "origin": origin,
                "radius": float(torus.MajorRadius()),
                "secondary_radius": float(torus.MinorRadius()),
                "semi_angle": None,
            }
    except Exception:
        pass
    return {"axis": None, "origin": None, "radius": None, "secondary_radius": None, "semi_angle": None}


def _axis_origin_from_position(position) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    direction = position.Direction()
    location = position.Location()
    axis = (float(direction.X()), float(direction.Y()), float(direction.Z()))
    origin = (float(location.X()), float(location.Y()), float(location.Z()))
    return axis, origin


def _principal_axis_from_vector(vector: Optional[Sequence[float]]) -> Optional[str]:
    if vector is None:
        return None
    values = [abs(float(value)) for value in vector]
    if not values or max(values) < 0.95:
        return None
    return ("x", "y", "z")[values.index(max(values))]


def _radius_from_relation_or_bbox(relation: Mapping[str, object], surface_type: str) -> Optional[float]:
    if surface_type not in {"cylinder", "cone", "sphere", "torus", "surface_of_revolution"}:
        return None
    value = relation.get("radius_mean")
    return float(value) if value is not None else None


def _bbox_dict(bound_box) -> dict:
    return {
        "xmin": float(bound_box.xmin),
        "xmax": float(bound_box.xmax),
        "ymin": float(bound_box.ymin),
        "ymax": float(bound_box.ymax),
        "zmin": float(bound_box.zmin),
        "zmax": float(bound_box.zmax),
    }


def _bbox_corner_points(box: Mapping[str, float]) -> list[tuple[float, float, float]]:
    return [
        (float(box[x]), float(box[y]), float(box[z]))
        for x in ("xmin", "xmax")
        for y in ("ymin", "ymax")
        for z in ("zmin", "zmax")
    ]


def _vertex_points(vertices: Iterable[object]) -> list[tuple[float, float, float]]:
    points = []
    for vertex in vertices:
        try:
            points.append(_vector_tuple(vertex.Center()))
        except Exception:
            continue
    return points


def _vector_tuple(vector) -> tuple[float, float, float]:
    values = vector.toTuple()
    return (float(values[0]), float(values[1]), float(values[2]))


def _shape_hash(shape) -> int:
    return int(shape.hashCode())


def _edge_ref(edge, mapping: Mapping[int, str]) -> str:
    key = _shape_hash(edge)
    if key in mapping:
        return mapping[key]
    center = _vector_tuple(edge.Center())
    box = _bbox_dict(edge.BoundingBox())
    payload = (
        round(float(edge.Length()), 6),
        tuple(round(value, 6) for value in center),
        tuple(round(float(box[key_name]), 6) for key_name in sorted(box)),
        _safe_geom_type(edge),
    )
    return f"EH{abs(hash(payload)) % 10**12:012d}"


def _parse_length_unit(step_file: Path) -> Optional[str]:
    text = step_file.read_text(encoding="utf-8", errors="replace").upper()
    if "MILLIMETRE" in text or ".MILLI.,.METRE." in text:
        return "mm"
    if ".METRE." in text or ".METER." in text:
        return "m"
    return None


def _mesh_tolerance(box: Mapping[str, float]) -> float:
    diagonal = math.sqrt(
        (box["xmax"] - box["xmin"]) ** 2
        + (box["ymax"] - box["ymin"]) ** 2
        + (box["zmax"] - box["zmin"]) ** 2
    )
    return min(1.0, max(0.03, diagonal * 0.001))


def _tessellate_face(face_id: str, face, tolerance: float) -> dict:
    vertices, triangles = face.tessellate(tolerance, 0.15)
    return {
        "face_id": face_id,
        "vertices": [list(_vector_tuple(vertex)) for vertex in vertices],
        "triangles": [list(map(int, triangle)) for triangle in triangles],
    }


if __name__ == "__main__":
    main()
