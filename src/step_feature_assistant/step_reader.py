"""STEP AP242 fallback reader for topology-oriented RF geometry review.

The preferred future backend is an exact CAD kernel such as OpenCASCADE,
FreeCAD, or CadQuery.  The current implementation intentionally uses only STEP
text entities so it can run in the repository's default Python environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from .surface_classifier import Point3, Vector3, classify_step_surface_type, normalize


@dataclass(frozen=True)
class StepEntity:
    """A single parsed STEP entity."""

    step_id: int
    entity_type: str
    raw: str


@dataclass(frozen=True)
class StepEdge:
    """A STEP edge curve between two vertex points."""

    edge_id: int
    start_vertex: int
    end_vertex: int
    curve_id: Optional[int]


@dataclass(frozen=True)
class StepSurface:
    """A parsed surface definition and its placement metadata."""

    surface_id: int
    step_type: str
    surface_type: str
    placement_id: Optional[int]
    origin: Optional[Point3]
    axis: Optional[Vector3]
    ref_direction: Optional[Vector3]
    radius: Optional[float]
    secondary_radius: Optional[float]
    semi_angle: Optional[float]


@dataclass(frozen=True)
class StepFace:
    """A face with recovered boundary references."""

    face_id: str
    step_id: int
    occ_index: int
    surface: StepSurface
    same_sense: bool
    bound_ids: List[int]
    edge_ids: List[int]
    edge_curve_refs: List[str]
    vertex_ids: List[int]
    boundary_points: List[Point3]


@dataclass(frozen=True)
class StepTopology:
    """Recovered STEP topology used by the analyzer."""

    source_step: str
    parser_backend: str
    units: Optional[str]
    entity_counts: Dict[str, int]
    solids: List[int]
    shells: List[int]
    faces: List[StepFace]
    edges: Dict[int, StepEdge]
    vertices: Dict[int, Point3]
    limitations: List[str]


def read_step_topology(step_file: Path) -> StepTopology:
    """Read a STEP file into a conservative topology model."""
    entities = parse_step_entities(step_file)
    entity_counts: Dict[str, int] = {}
    for entity in entities.values():
        entity_counts[entity.entity_type] = entity_counts.get(entity.entity_type, 0) + 1

    vertices = _parse_vertices(entities)
    edges = _parse_edges(entities)
    oriented_edges = _parse_oriented_edges(entities)
    edge_loops = _parse_edge_loops(entities)
    bounds = _parse_face_bounds(entities)
    placements = _parse_axis_placements(entities)
    surfaces = _parse_surfaces(entities, placements)
    solid_ids = sorted(entity.step_id for entity in entities.values() if entity.entity_type == "MANIFOLD_SOLID_BREP")
    shell_ids = sorted(entity.step_id for entity in entities.values() if entity.entity_type == "CLOSED_SHELL")
    units = _parse_length_unit_from_file(step_file) or _parse_length_unit(entities)

    faces: List[StepFace] = []
    face_entities = sorted(
        (entity for entity in entities.values() if entity.entity_type == "ADVANCED_FACE"),
        key=lambda entity: entity.step_id,
    )
    for occ_index, entity in enumerate(face_entities, start=1):
        parsed = _parse_advanced_face(entity)
        if parsed is None:
            continue
        bound_ids, surface_id, same_sense = parsed
        surface = surfaces.get(surface_id) or StepSurface(
            surface_id=surface_id,
            step_type="UNKNOWN",
            surface_type="unknown",
            placement_id=None,
            origin=None,
            axis=None,
            ref_direction=None,
            radius=None,
            secondary_radius=None,
            semi_angle=None,
        )
        edge_ids: List[int] = []
        vertex_ids: List[int] = []
        ordered_points: List[Point3] = []
        for bound_id in bound_ids:
            loop_id = bounds.get(bound_id)
            if loop_id is None:
                continue
            for oriented_edge_id in edge_loops.get(loop_id, []):
                edge_ref, orientation = oriented_edges.get(oriented_edge_id, (None, True))
                if edge_ref is None:
                    continue
                edge = edges.get(edge_ref)
                if edge is None:
                    continue
                edge_ids.append(edge.edge_id)
                start, end = (
                    (edge.start_vertex, edge.end_vertex)
                    if orientation
                    else (edge.end_vertex, edge.start_vertex)
                )
                if not vertex_ids:
                    vertex_ids.append(start)
                vertex_ids.append(end)
                if start in vertices and not ordered_points:
                    ordered_points.append(vertices[start])
                if end in vertices:
                    ordered_points.append(vertices[end])

        faces.append(
            StepFace(
                face_id=f"F{occ_index:04d}",
                step_id=entity.step_id,
                occ_index=occ_index,
                surface=surface,
                same_sense=same_sense,
                bound_ids=bound_ids,
                edge_ids=_unique_ints(edge_ids),
                edge_curve_refs=[f"E{edge_id:04d}" for edge_id in _unique_ints(edge_ids)],
                vertex_ids=_unique_ints(vertex_ids),
                boundary_points=ordered_points,
            )
        )

    limitations = [
        "Fallback STEP AP242 text parser is active; face areas and normals are approximate.",
        "Install an OpenCASCADE, FreeCAD, or CadQuery backend for exact CAD-kernel measurements.",
    ]
    return StepTopology(
        source_step=str(step_file),
        parser_backend="step_ap242_text_fallback",
        units=units,
        entity_counts=entity_counts,
        solids=solid_ids,
        shells=shell_ids,
        faces=faces,
        edges=edges,
        vertices=vertices,
        limitations=limitations,
    )


def parse_step_entities(step_file: Path) -> Dict[int, StepEntity]:
    """Parse STEP entity records into an id-indexed dictionary."""
    text = step_file.read_text(encoding="utf-8", errors="replace")
    records: List[str] = []
    buffer: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        buffer.append(line)
        if line.endswith(";"):
            records.append(" ".join(buffer)[:-1])
            buffer = []

    entities: Dict[int, StepEntity] = {}
    for record in records:
        match = re.match(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\(", record)
        if not match:
            continue
        step_id = int(match.group(1))
        entity_type = match.group(2)
        entities[step_id] = StepEntity(step_id=step_id, entity_type=entity_type, raw=record)
    return entities


def _parse_vertices(entities: Dict[int, StepEntity]) -> Dict[int, Point3]:
    points = {
        entity.step_id: _parse_cartesian_point(entity.raw)
        for entity in entities.values()
        if entity.entity_type == "CARTESIAN_POINT"
    }
    vertices: Dict[int, Point3] = {}
    for entity in entities.values():
        if entity.entity_type != "VERTEX_POINT":
            continue
        refs = _refs(entity.raw)
        if refs and refs[0] in points:
            vertices[entity.step_id] = points[refs[0]]
    return vertices


def _parse_edges(entities: Dict[int, StepEntity]) -> Dict[int, StepEdge]:
    edges: Dict[int, StepEdge] = {}
    for entity in entities.values():
        if entity.entity_type != "EDGE_CURVE":
            continue
        refs = _refs(entity.raw)
        if len(refs) >= 2:
            edges[entity.step_id] = StepEdge(
                edge_id=entity.step_id,
                start_vertex=refs[0],
                end_vertex=refs[1],
                curve_id=refs[2] if len(refs) >= 3 else None,
            )
    return edges


def _parse_oriented_edges(entities: Dict[int, StepEntity]) -> Dict[int, Tuple[Optional[int], bool]]:
    oriented: Dict[int, Tuple[Optional[int], bool]] = {}
    for entity in entities.values():
        if entity.entity_type != "ORIENTED_EDGE":
            continue
        refs = _refs(entity.raw)
        orientation = _last_bool(entity.raw, default=True)
        oriented[entity.step_id] = (refs[-1] if refs else None, orientation)
    return oriented


def _parse_edge_loops(entities: Dict[int, StepEntity]) -> Dict[int, List[int]]:
    loops: Dict[int, List[int]] = {}
    for entity in entities.values():
        if entity.entity_type == "EDGE_LOOP":
            loops[entity.step_id] = _refs(entity.raw)
    return loops


def _parse_face_bounds(entities: Dict[int, StepEntity]) -> Dict[int, int]:
    bounds: Dict[int, int] = {}
    for entity in entities.values():
        if entity.entity_type not in {"FACE_OUTER_BOUND", "FACE_BOUND"}:
            continue
        refs = _refs(entity.raw)
        if refs:
            bounds[entity.step_id] = refs[0]
    return bounds


def _parse_axis_placements(entities: Dict[int, StepEntity]) -> Dict[int, dict]:
    cartesian_points = {
        entity.step_id: _parse_cartesian_point(entity.raw)
        for entity in entities.values()
        if entity.entity_type == "CARTESIAN_POINT"
    }
    directions = {
        entity.step_id: _parse_direction(entity.raw)
        for entity in entities.values()
        if entity.entity_type == "DIRECTION"
    }
    placements: Dict[int, dict] = {}
    for entity in entities.values():
        if entity.entity_type != "AXIS2_PLACEMENT_3D":
            continue
        refs = _refs(entity.raw)
        origin = cartesian_points.get(refs[0]) if refs else None
        axis = normalize(directions.get(refs[1], (0.0, 0.0, 1.0))) if len(refs) >= 2 else (0.0, 0.0, 1.0)
        ref_direction = normalize(directions.get(refs[2], (1.0, 0.0, 0.0))) if len(refs) >= 3 else (1.0, 0.0, 0.0)
        placements[entity.step_id] = {
            "origin": origin,
            "axis": axis,
            "ref_direction": ref_direction,
        }
    return placements


def _parse_surfaces(entities: Dict[int, StepEntity], placements: Dict[int, dict]) -> Dict[int, StepSurface]:
    surfaces: Dict[int, StepSurface] = {}
    for entity in entities.values():
        surface_type = classify_step_surface_type(entity.entity_type)
        if surface_type == "unknown":
            continue
        refs = _refs(entity.raw)
        placement_id = refs[0] if refs else None
        placement = placements.get(placement_id or -1, {})
        numbers = _numeric_literals(entity.raw)
        radius = None
        secondary_radius = None
        semi_angle = None
        if entity.entity_type in {"CYLINDRICAL_SURFACE", "SPHERICAL_SURFACE"} and numbers:
            radius = numbers[-1]
        elif entity.entity_type == "CONICAL_SURFACE" and len(numbers) >= 2:
            radius = numbers[-2]
            semi_angle = numbers[-1]
        elif entity.entity_type == "TOROIDAL_SURFACE" and len(numbers) >= 2:
            radius = numbers[-2]
            secondary_radius = numbers[-1]
        surfaces[entity.step_id] = StepSurface(
            surface_id=entity.step_id,
            step_type=entity.entity_type,
            surface_type=surface_type,
            placement_id=placement_id,
            origin=placement.get("origin"),
            axis=placement.get("axis"),
            ref_direction=placement.get("ref_direction"),
            radius=radius,
            secondary_radius=secondary_radius,
            semi_angle=semi_angle,
        )
    return surfaces


def _parse_advanced_face(entity: StepEntity) -> Optional[Tuple[List[int], int, bool]]:
    match = re.search(
        r"ADVANCED_FACE\s*\([^,]*,\s*\((.*?)\)\s*,\s*#(\d+)\s*,\s*(\.[TF]\.)",
        entity.raw,
        flags=re.IGNORECASE,
    )
    if not match:
        refs = _refs(entity.raw)
        if len(refs) < 2:
            return None
        return refs[:-1], refs[-1], _last_bool(entity.raw, default=True)
    bound_ids = [int(value) for value in re.findall(r"#(\d+)", match.group(1))]
    surface_id = int(match.group(2))
    same_sense = match.group(3).upper() == ".T."
    return bound_ids, surface_id, same_sense


def _parse_cartesian_point(raw: str) -> Point3:
    match = re.search(r"CARTESIAN_POINT\s*\([^,]*,\s*\((.*?)\)\s*\)", raw)
    if not match:
        return (0.0, 0.0, 0.0)
    values = [float(value) for value in match.group(1).split(",")[:3]]
    while len(values) < 3:
        values.append(0.0)
    return (values[0], values[1], values[2])


def _parse_direction(raw: str) -> Vector3:
    match = re.search(r"DIRECTION\s*\([^,]*,\s*\((.*?)\)\s*\)", raw)
    if not match:
        return (0.0, 0.0, 0.0)
    values = [float(value) for value in match.group(1).split(",")[:3]]
    while len(values) < 3:
        values.append(0.0)
    return normalize((values[0], values[1], values[2]))


def _parse_length_unit(entities: Dict[int, StepEntity]) -> Optional[str]:
    for entity in entities.values():
        if "MILLIMETRE" in entity.raw.upper() or ".MILLI.,.METRE." in entity.raw.upper():
            return "mm"
    return None


def _parse_length_unit_from_file(step_file: Path) -> Optional[str]:
    text = step_file.read_text(encoding="utf-8", errors="replace").upper()
    if "MILLIMETRE" in text or ".MILLI.,.METRE." in text:
        return "mm"
    if ".METRE." in text or ".METER." in text:
        return "m"
    return None


def _refs(raw: str) -> List[int]:
    refs = [int(value) for value in re.findall(r"#(\d+)", raw)]
    owner = re.match(r"#(\d+)\s*=", raw)
    if owner and refs and refs[0] == int(owner.group(1)):
        return refs[1:]
    return refs


def _last_bool(raw: str, default: bool) -> bool:
    matches = re.findall(r"\.(T|F)\.", raw, flags=re.IGNORECASE)
    if not matches:
        return default
    return matches[-1].upper() == "T"


def _numeric_literals(raw: str) -> List[float]:
    cleaned = re.sub(r"#[0-9]+", "", raw)
    return [
        float(value)
        for value in re.findall(r"(?<![A-Za-z_])[-+]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[Ee][-+]?\d+)?", cleaned)
    ]


def _unique_ints(values: List[int]) -> List[int]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
