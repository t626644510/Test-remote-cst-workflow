"""Build geometry manifests from recovered STEP topology."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .adjacency_builder import build_face_adjacency
from .step_reader import StepFace, StepTopology
from .surface_classifier import (
    axis_relation,
    bbox,
    centroid,
    estimate_area,
    estimate_normal,
    face_fingerprint,
    principal_axis,
    unique_points,
)


def build_geometry_manifest(topology: StepTopology, axis: str) -> dict:
    """Build a versioned geometry manifest from STEP topology."""
    face_edges = {face.face_id: face.edge_curve_refs for face in topology.faces}
    adjacency = build_face_adjacency(face_edges)
    all_points = list(topology.vertices.values())
    model_bbox = bbox(all_points)

    faces = []
    for face in topology.faces:
        face_record = build_face_record(face, axis, adjacency.get(face.face_id, []))
        faces.append(face_record)

    return {
        "schema_version": "0.1",
        "source_step": topology.source_step,
        "reader": {
            "backend": topology.parser_backend,
            "units": topology.units,
            "limitations": topology.limitations,
        },
        "model_summary": {
            "solid_count": len(topology.solids),
            "shell_count": len(topology.shells),
            "face_count": len(topology.faces),
            "edge_count": len(topology.edges),
            "bbox": model_bbox,
            "detected_axis": axis.lower(),
            "entity_counts": topology.entity_counts,
        },
        "faces": faces,
    }


def build_face_record(face: StepFace, axis: str, adjacent_faces: Sequence[str]) -> dict:
    """Build one manifest face record."""
    points = unique_points(face.boundary_points)
    center = centroid(points)
    box = bbox(points)
    area, area_method = estimate_area(
        points,
        face.surface.surface_type,
        axis,
        declared_radius=face.surface.radius,
        secondary_radius=face.surface.secondary_radius,
    )
    normal = estimate_normal(
        points,
        face.surface.surface_type,
        center,
        face.surface.axis,
        face.surface.origin,
    )
    if not face.same_sense:
        normal = (-normal[0], -normal[1], -normal[2])
    relation = axis_relation(
        points,
        axis,
        face.surface.surface_type,
        face.surface.axis,
        face.surface.origin,
        declared_radius=face.surface.radius,
    )
    fingerprint = face_fingerprint(
        face.surface.surface_type,
        area,
        center,
        box,
        len(face.edge_curve_refs),
    )
    return {
        "face_id": face.face_id,
        "occ_index": face.occ_index,
        "step_face_id": f"#{face.step_id}",
        "surface_step_id": f"#{face.surface.surface_id}",
        "surface_type": face.surface.surface_type,
        "step_surface_type": face.surface.step_type,
        "area": area,
        "area_method": area_method,
        "area_confidence": 0.45 if area_method != "newell_polygon_from_boundary_vertices" else 0.65,
        "centroid": list(center),
        "normal_estimate": list(normal),
        "principal_axis": principal_axis(face.surface.axis),
        "surface_axis": list(face.surface.axis) if face.surface.axis is not None else None,
        "surface_origin": list(face.surface.origin) if face.surface.origin is not None else None,
        "radius": face.surface.radius,
        "secondary_radius": face.surface.secondary_radius,
        "semi_angle": face.surface.semi_angle,
        "bbox": box,
        "axis_relation": relation,
        "edge_count": len(face.edge_curve_refs),
        "edge_refs": list(face.edge_curve_refs),
        "adjacent_faces": sorted(adjacent_faces),
        "fingerprint": fingerprint,
    }


def build_adjacency_graph(manifest: dict) -> dict:
    """Build an adjacency graph payload from a geometry manifest."""
    faces = manifest.get("faces", [])
    adjacency = {face["face_id"]: face.get("adjacent_faces", []) for face in faces}
    edges = []
    seen = set()
    for face_id, neighbors in adjacency.items():
        for neighbor in neighbors:
            key = tuple(sorted((face_id, neighbor)))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": key[0], "target": key[1]})
    return {
        "schema_version": "0.1",
        "source_geometry_manifest": "geometry_manifest.json",
        "nodes": [{"id": face["face_id"], "surface_type": face["surface_type"]} for face in faces],
        "edges": edges,
        "adjacency": adjacency,
    }


def build_face_inventory_rows(manifest: dict) -> List[dict]:
    """Flatten manifest faces into CSV-friendly rows."""
    rows: List[dict] = []
    for face in manifest.get("faces", []):
        relation = face.get("axis_relation", {})
        center = face.get("centroid", [None, None, None])
        normal = face.get("normal_estimate", [None, None, None])
        box = face.get("bbox", {})
        rows.append(
            {
                "face_id": face.get("face_id"),
                "occ_index": face.get("occ_index"),
                "surface_type": face.get("surface_type"),
                "step_surface_type": face.get("step_surface_type"),
                "area": face.get("area"),
                "area_method": face.get("area_method"),
                "centroid_x": center[0],
                "centroid_y": center[1],
                "centroid_z": center[2],
                "normal_x": normal[0],
                "normal_y": normal[1],
                "normal_z": normal[2],
                "radius": face.get("radius"),
                "secondary_radius": face.get("secondary_radius"),
                "radius_mean": relation.get("radius_mean"),
                "r_min": _list_value(relation.get("r_range"), 0),
                "r_max": _list_value(relation.get("r_range"), 1),
                "z_min": _list_value(relation.get("z_range"), 0),
                "z_max": _list_value(relation.get("z_range"), 1),
                "is_axisymmetric": relation.get("is_axisymmetric"),
                "edge_count": face.get("edge_count"),
                "adjacent_faces": " ".join(face.get("adjacent_faces", [])),
                "fingerprint": face.get("fingerprint"),
                "bbox_xmin": box.get("xmin"),
                "bbox_xmax": box.get("xmax"),
                "bbox_ymin": box.get("ymin"),
                "bbox_ymax": box.get("ymax"),
                "bbox_zmin": box.get("zmin"),
                "bbox_zmax": box.get("zmax"),
            }
        )
    return rows


def face_groups_by_surface_and_adjacency(manifest: dict) -> List[dict]:
    """Group adjacent faces with the same surface type."""
    from .adjacency_builder import connected_components

    faces = manifest.get("faces", [])
    adjacency = {face["face_id"]: face.get("adjacent_faces", []) for face in faces}
    by_type: Dict[str, List[str]] = defaultdict(list)
    for face in faces:
        by_type[face.get("surface_type", "unknown")].append(face["face_id"])

    groups = []
    counter = 1
    for surface_type, face_ids in sorted(by_type.items()):
        for component in connected_components(face_ids, adjacency):
            groups.append(
                {
                    "group_id": f"G{counter:04d}",
                    "group_type_candidate": f"{surface_type}_adjacent_faces",
                    "member_faces": component,
                    "confidence": 0.55,
                    "evidence": [
                        f"{len(component)} adjacent face(s)",
                        f"shared surface_type={surface_type}",
                    ],
                }
            )
            counter += 1
    return groups


def _list_value(values: object, index: int) -> object:
    if isinstance(values, list) and len(values) > index:
        return values[index]
    return None
