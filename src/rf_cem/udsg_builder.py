"""Build a minimal UDSG v0 payload for the 500 MHz baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import yaml

from step_feature_assistant.review_merger import merge_reviewed_labels

from .design_package import BaselineDesignPackage, BaselinePaths


REQUIRED_FEATURE_TYPES = {
    "RFVacuumVolume",
    "ConductingWall",
    "BeamPipeLeft",
    "BeamPipeRight",
    "BeamAperture",
    "BeamExit",
}


def build_baseline_udsg(
    paths: BaselinePaths,
    package: BaselineDesignPackage | None = None,
    history_recipe: Mapping[str, object] | None = None,
) -> tuple[dict, dict]:
    """Build UDSG v0 and a review-session diff report.

    Frequency values in the package are expressed in MHz, matching the CST
    baseline project unit settings.
    """
    package = package or BaselineDesignPackage()
    geometry_graph = _read_json(paths.geometry_graph)
    feature_graph_draft = _read_json(paths.feature_graph_draft)
    geometry_manifest = _read_json(paths.geometry_manifest)
    review_data = yaml.safe_load(paths.reviewed_feature_labels.read_text(encoding="utf-8")) or {}
    resolved = merge_reviewed_labels(feature_graph_draft, review_data, geometry_manifest)
    review_diff = build_review_session_diff(paths.review_session, resolved)
    symmetry = check_xy_symmetry(geometry_graph)

    confirmed = [
        feature
        for feature in resolved.get("features", [])
        if feature.get("status") in {"confirmed", "modified"}
    ]
    missing_types = sorted(REQUIRED_FEATURE_TYPES - {str(feature.get("type")) for feature in confirmed})
    warnings = []
    if missing_types:
        warnings.append(f"missing required feature types: {', '.join(missing_types)}")
    if not symmetry["is_xy_symmetric"]:
        warnings.append("geometry bbox is not symmetric about both X=0 and Y=0; history boundary is still preserved")

    udsg = {
        "schema_version": "udsg.v0",
        "design_package": package.to_dict(),
        "sources": {
            "step_file": str(paths.step_file),
            "geometry_graph": str(paths.geometry_graph),
            "feature_graph_draft": str(paths.feature_graph_draft),
            "reviewed_feature_labels": str(paths.reviewed_feature_labels),
            "model_history_json": str(paths.model_history_json),
        },
        "geometry": {
            "source_geometry_graph": "geometry_graph.json",
            "model_summary": geometry_graph.get("model_summary", {}),
            "geometry_index": geometry_graph.get("geometry_index", {}),
            "nodes": geometry_graph.get("nodes", []),
            "topology_graph": geometry_graph.get("topology_graph", {}),
            "symmetry": symmetry,
        },
        "features": resolved.get("features", []),
        "bindings": _build_bindings(resolved),
        "simulation_recipe": _simulation_recipe_from_history(history_recipe or {}),
        "validation": {
            "status": "ok" if not missing_types else "requires_review",
            "warnings": warnings,
            "errors": [],
        },
        "notes": [
            "reviewed_feature_labels.yaml is the authoritative semantic input for v0.",
            "review_session.json is recorded only as audit metadata and does not drive CST actions.",
            "CST history evidence is preserved as setup template source, not as geometry truth.",
        ],
    }
    return udsg, review_diff


def check_xy_symmetry(geometry_graph: Mapping[str, object], tolerance: float = 1e-6) -> dict:
    """Check whether the model bbox is symmetric about X=0 and Y=0.

    The check is intentionally conservative and records numeric evidence rather
    than changing boundary conditions automatically.
    """
    bbox = (
        geometry_graph.get("model_summary", {})
        if isinstance(geometry_graph.get("model_summary"), Mapping)
        else {}
    ).get("bbox", {})
    if not isinstance(bbox, Mapping):
        bbox = {}
    x_error = abs(float(bbox.get("xmin", 0.0)) + float(bbox.get("xmax", 0.0)))
    y_error = abs(float(bbox.get("ymin", 0.0)) + float(bbox.get("ymax", 0.0)))
    scale = max(
        1.0,
        abs(float(bbox.get("xmin", 0.0))),
        abs(float(bbox.get("xmax", 0.0))),
        abs(float(bbox.get("ymin", 0.0))),
        abs(float(bbox.get("ymax", 0.0))),
    )
    limit = tolerance * scale
    return {
        "method": "bbox_about_zero",
        "tolerance": tolerance,
        "x_error": x_error,
        "y_error": y_error,
        "limit": limit,
        "x_symmetric": x_error <= limit,
        "y_symmetric": y_error <= limit,
        "is_xy_symmetric": x_error <= limit and y_error <= limit,
    }


def build_review_session_diff(review_session_path: Path | None, resolved_feature_graph: Mapping[str, object]) -> dict:
    """Summarize review-session edits without consuming them as truth."""
    if review_session_path is None or not review_session_path.exists():
        return {
            "schema_version": "review_session_diff.v0",
            "source_review_session": None,
            "deleted_bindings": [],
            "rewired_bindings": [],
            "notes": ["review_session.json was not present"],
        }
    session = _read_json(review_session_path)
    deleted = []
    rewired = []
    for binding_id, binding in (session.get("bindings", {}) or {}).items():
        if not isinstance(binding, Mapping):
            continue
        entry = {
            "binding_id": binding_id,
            "original_feature_id": binding.get("original_feature_id"),
            "original_geometry_node_id": binding.get("original_geometry_node_id"),
            "feature_id": binding.get("feature_id"),
            "geometry_node_id": binding.get("geometry_node_id"),
        }
        if binding.get("deleted") or str(binding.get("status")).lower() == "deleted":
            deleted.append(entry)
        elif (
            binding.get("feature_id") != binding.get("original_feature_id")
            or binding.get("geometry_node_id") != binding.get("original_geometry_node_id")
        ):
            rewired.append(entry)

    return {
        "schema_version": "review_session_diff.v0",
        "source_review_session": str(review_session_path),
        "deleted_bindings": sorted(deleted, key=lambda item: str(item["binding_id"])),
        "rewired_bindings": sorted(rewired, key=lambda item: str(item["binding_id"])),
        "resolved_feature_count": len(resolved_feature_graph.get("features", [])),
        "notes": [
            "review_session.json is a browser audit trail; reviewed_feature_labels.yaml remains authoritative.",
        ],
    }


def _build_bindings(resolved_feature_graph: Mapping[str, object]) -> list[dict]:
    bindings = []
    for feature in resolved_feature_graph.get("features", []):
        if feature.get("status") not in {"confirmed", "modified"}:
            continue
        feature_id = str(feature.get("id"))
        for geometry_ref in feature.get("geometry_refs", []):
            bindings.append(
                {
                    "binding_id": f"bind_{_slug(feature_id)}_{_slug(str(geometry_ref))}",
                    "feature_id": feature_id,
                    "feature_type": feature.get("type"),
                    "geometry_node_id": geometry_ref,
                    "binding_type": "feature_to_geometry",
                    "confidence": feature.get("confidence", 1.0),
                    "evidence": feature.get("evidence", []),
                    "status": "accepted",
                }
            )
    return sorted(bindings, key=lambda item: item["binding_id"])


def _simulation_recipe_from_history(history_recipe: Mapping[str, object]) -> dict:
    project = history_recipe.get("project", {}) if isinstance(history_recipe, Mapping) else {}
    solver = history_recipe.get("solver", {}) if isinstance(history_recipe, Mapping) else {}
    boundaries = history_recipe.get("boundaries", {}) if isinstance(history_recipe, Mapping) else {}
    return {
        "schema_version": "simulation_recipe.v0",
        "units": project.get("units") if isinstance(project, Mapping) else None,
        "solver": solver,
        "boundaries": boundaries,
        "boundary_policy": {
            "open_or_electric_by_recipe": "electric",
            "scope": "global_boundary_only_v0",
        },
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _slug(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "_" for char in value]
    return "_".join(part for part in "".join(chars).split("_") if part)
