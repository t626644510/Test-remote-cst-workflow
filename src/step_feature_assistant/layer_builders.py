"""Build review layers for the Helper2 geometry subsystem."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence


LOW_CONFIDENCE_THRESHOLD = 0.6


def build_geometry_graph(geometry_manifest: dict, adjacency_graph: dict) -> dict:
    """Build a normalized geometry graph from STEP geometry facts."""
    faces = geometry_manifest.get("faces", [])
    summary = geometry_manifest.get("model_summary", {})
    nodes = []
    for face in faces:
        face_id = str(face.get("face_id", ""))
        nodes.append(
            {
                "id": f"face:{face_id}",
                "kind": "face",
                "source_id": face_id,
                "surface_type": face.get("surface_type", "unknown"),
                "area": face.get("area"),
                "centroid": face.get("centroid"),
                "bbox": face.get("bbox"),
                "axis_relation": face.get("axis_relation", {}),
                "stable_hash": face.get("fingerprint"),
                "adjacent_geometry_refs": [f"face:{value}" for value in face.get("adjacent_faces", [])],
            }
        )

    solid_count = int(summary.get("solid_count", 0) or 0)
    for index in range(1, solid_count + 1):
        nodes.append(
            {
                "id": f"solid:S{index:04d}",
                "kind": "solid",
                "source_id": f"S{index:04d}",
                "stable_hash": None,
            }
        )

    surface_counts = Counter(str(face.get("surface_type", "unknown")) for face in faces)
    axisymmetric_count = sum(1 for face in faces if face.get("axis_relation", {}).get("is_axisymmetric"))
    return {
        "schema_version": "geometry_graph.v0",
        "source_geometry_manifest": "geometry_manifest.json",
        "source_step": geometry_manifest.get("source_step"),
        "model_summary": summary,
        "geometry_index": {
            "surface_counts": dict(sorted(surface_counts.items())),
            "axisymmetric_face_count": axisymmetric_count,
            "detected_axis": summary.get("detected_axis"),
            "bbox": summary.get("bbox", {}),
        },
        "nodes": nodes,
        "topology_graph": {
            "nodes": adjacency_graph.get("nodes", []),
            "edges": adjacency_graph.get("edges", []),
            "adjacency": adjacency_graph.get("adjacency", {}),
        },
    }


def build_feature_candidates(feature_graph_draft: dict) -> dict:
    """Adapt draft features into a UDSG-facing candidate list."""
    candidates = []
    for feature in feature_graph_draft.get("features", []):
        confidence = float(feature.get("confidence", 0.0) or 0.0)
        refs = list(feature.get("geometry_refs", []))
        diagnostics = []
        if not refs:
            diagnostics.append("missing_refs")
        if confidence < LOW_CONFIDENCE_THRESHOLD:
            diagnostics.append("low_confidence")
        candidates.append(
            {
                "id": feature.get("id"),
                "type": feature.get("type"),
                "geometry_refs": refs,
                "confidence": confidence,
                "evidence": list(feature.get("evidence", [])),
                "status": feature.get("status", "candidate"),
                "requires_human_review": bool(feature.get("requires_human_review", True)),
                "default_boundary_role": feature.get("default_boundary_role"),
                "metadata": feature.get("metadata", {}),
                "diagnostics": diagnostics,
            }
        )

    return {
        "schema_version": "feature_candidates.v0",
        "source_feature_graph_draft": "feature_graph_draft.json",
        "model_type": feature_graph_draft.get("model_type"),
        "axis": feature_graph_draft.get("axis"),
        "feature_candidates": candidates,
    }


def build_udsg_geometry_layer(
    geometry_graph: dict,
    feature_candidates: dict,
    face_groups: Sequence[Mapping[str, object]] | None = None,
) -> dict:
    """Build a geometry-only partial UDSG layer for review and handoff."""
    geometry_nodes = list(geometry_graph.get("nodes", []))
    for group in face_groups or []:
        group_id = str(group.get("group_id", ""))
        if not group_id:
            continue
        geometry_nodes.append(
            {
                "id": f"face_group:{group_id}",
                "kind": "face_group",
                "source_id": group_id,
                "member_geometry_refs": [f"face:{value}" for value in group.get("member_faces", [])],
                "group_type_candidate": group.get("group_type_candidate"),
            }
        )

    geometry_ids = {str(node.get("id")) for node in geometry_nodes}
    feature_ids = {str(item.get("id")) for item in feature_candidates.get("feature_candidates", [])}
    bindings = []
    warnings = []
    for candidate in feature_candidates.get("feature_candidates", []):
        feature_id = str(candidate.get("id"))
        refs = candidate.get("geometry_refs", [])
        if not refs:
            warnings.append(f"feature {feature_id} has no geometry refs")
        for ref in refs:
            ref_text = str(ref)
            binding_status = "candidate"
            if ref_text not in geometry_ids:
                binding_status = "broken_binding"
                warnings.append(f"feature {feature_id} references missing geometry {ref_text}")
            elif candidate.get("requires_human_review", True):
                binding_status = "requires_review"
            bindings.append(
                {
                    "binding_id": f"bind_{_slug(feature_id)}_{_slug(ref_text)}",
                    "feature_id": feature_id,
                    "geometry_node_id": ref_text,
                    "binding_type": "feature_to_geometry",
                    "confidence": candidate.get("confidence", 0.0),
                    "evidence": list(candidate.get("evidence", [])),
                    "status": binding_status,
                }
            )

    return {
        "schema_version": "udsg_geometry_layer.v0",
        "source_geometry_graph": "geometry_graph.json",
        "source_feature_candidates": "feature_candidates.json",
        "geometry_nodes": geometry_nodes,
        "feature_candidates": feature_candidates.get("feature_candidates", []),
        "topology_graph": geometry_graph.get("topology_graph", {}),
        "bindings": bindings,
        "validation": {
            "status": "partial_ok" if not any(binding.get("status") == "broken_binding" for binding in bindings) else "requires_review",
            "warnings": warnings,
            "errors": [],
        },
        "notes": [
            "This is a geometry-only partial UDSG layer produced by Helper2.",
            "CST history and simulation recipe merging belong to the downstream RF-CEM UDSG builder.",
        ],
    }


def detect_review_issues(feature_candidates: dict, udsg_geometry_layer: dict) -> dict:
    """Precompute review issues shown by the HTML reviewer."""
    face_memberships: dict[str, set[str]] = {}
    feature_issues: dict[str, list[str]] = {}
    for candidate in feature_candidates.get("feature_candidates", []):
        feature_id = str(candidate.get("id"))
        issues = list(candidate.get("diagnostics", []))
        for ref in candidate.get("geometry_refs", []):
            if str(ref).startswith("face:"):
                face_memberships.setdefault(str(ref), set()).add(str(candidate.get("type")))
        if issues:
            feature_issues[feature_id] = issues

    overlap_refs = sorted(ref for ref, types in face_memberships.items() if len(types) > 1)
    for candidate in feature_candidates.get("feature_candidates", []):
        feature_id = str(candidate.get("id"))
        if any(ref in overlap_refs for ref in candidate.get("geometry_refs", [])):
            feature_issues.setdefault(feature_id, []).append("overlap")

    broken_bindings = [
        binding
        for binding in udsg_geometry_layer.get("bindings", [])
        if binding.get("status") == "broken_binding"
    ]
    for binding in broken_bindings:
        feature_id = str(binding.get("feature_id"))
        feature_issues.setdefault(feature_id, []).append("broken_binding")

    return {
        "schema_version": "review_issues.v0",
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "feature_issues": {key: sorted(set(values)) for key, values in sorted(feature_issues.items())},
        "overlap_geometry_refs": overlap_refs,
        "broken_bindings": broken_bindings,
    }


def _slug(value: str) -> str:
    chars = []
    for char in value:
        chars.append(char.lower() if char.isalnum() else "_")
    return "_".join(part for part in "".join(chars).split("_") if part)
