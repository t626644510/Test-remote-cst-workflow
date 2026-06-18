"""Merge human-reviewed feature labels into a resolved feature graph."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Mapping, Optional

import yaml


def load_review_yaml(path: Path) -> dict:
    """Load a reviewed feature label YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Review YAML must contain a mapping: {path}")
    return data


def merge_reviewed_labels(
    feature_graph_draft: dict,
    review_data: Mapping[str, object],
    geometry_manifest: Optional[dict] = None,
) -> dict:
    """Merge human labels into a resolved feature graph payload."""
    validate_reviewed_labels(feature_graph_draft, review_data, geometry_manifest)
    features = [deepcopy(feature) for feature in feature_graph_draft.get("features", [])]
    by_id = {feature.get("id"): feature for feature in features}

    for rejected_id in review_data.get("rejected_candidates", []) or []:
        feature = by_id.get(str(rejected_id))
        if feature:
            feature["status"] = "rejected"
            feature["requires_human_review"] = False

    confirmed = review_data.get("confirmed_features", {}) or {}
    if isinstance(confirmed, Mapping):
        for feature_id, spec in confirmed.items():
            if not isinstance(spec, Mapping):
                continue
            _upsert_review_feature(features, by_id, str(feature_id), spec, status="confirmed")

    manual_groups = review_data.get("manual_groups", {}) or {}
    if isinstance(manual_groups, Mapping):
        for feature_id, spec in manual_groups.items():
            if not isinstance(spec, Mapping):
                continue
            _upsert_review_feature(features, by_id, str(feature_id), spec, status="modified")

    resolved_refs = set()
    for feature in features:
        if feature.get("status") in {"confirmed", "modified", "candidate"}:
            resolved_refs.update(feature.get("geometry_refs", []))
    unassigned = [
        face_id
        for face_id in feature_graph_draft.get("unassigned_faces", [])
        if f"face:{face_id}" not in resolved_refs and face_id not in resolved_refs
    ]
    return {
        "schema_version": "0.1",
        "source_feature_graph_draft": "feature_graph_draft.json",
        "features": features,
        "unassigned_faces": unassigned,
        "review_notes": {
            "confirmed_feature_count": sum(1 for feature in features if feature.get("status") == "confirmed"),
            "modified_feature_count": sum(1 for feature in features if feature.get("status") == "modified"),
            "rejected_feature_count": sum(1 for feature in features if feature.get("status") == "rejected"),
        },
    }


def validate_reviewed_labels(
    feature_graph_draft: dict,
    review_data: Mapping[str, object],
    geometry_manifest: Optional[dict] = None,
) -> None:
    """Validate reviewed candidate and geometry references before merging."""
    candidate_ids = {str(feature.get("id")) for feature in feature_graph_draft.get("features", [])}
    face_ids = {
        str(face.get("face_id"))
        for face in (geometry_manifest or {}).get("faces", [])
    } or set(feature_graph_draft.get("unassigned_faces", []))
    for feature in feature_graph_draft.get("features", []):
        face_ids.update(_raw_face_ids(feature.get("geometry_refs", [])))
    group_ids = {str(group.get("group_id")) for group in feature_graph_draft.get("face_groups", [])}
    solid_count = int((geometry_manifest or {}).get("model_summary", {}).get("solid_count", 0))
    solid_ids = {f"S{index:04d}" for index in range(1, solid_count + 1)}

    rejected = review_data.get("rejected_candidates", []) or []
    unknown_candidates = sorted(str(value) for value in rejected if str(value) not in candidate_ids)
    if unknown_candidates:
        raise ValueError(f"Unknown rejected candidate id(s): {', '.join(unknown_candidates)}")

    for section_name in ("confirmed_features", "manual_groups"):
        section = review_data.get(section_name, {}) or {}
        if not isinstance(section, Mapping):
            raise ValueError(f"{section_name} must be a mapping")
        for feature_id, spec in section.items():
            if not isinstance(spec, Mapping):
                raise ValueError(f"{section_name}.{feature_id} must be a mapping")
            if section_name == "confirmed_features" and str(feature_id) not in candidate_ids:
                raise ValueError(
                    f"Unknown confirmed candidate id: {feature_id}. "
                    "Use manual_groups for a new human-defined feature."
                )
            refs = _normalize_geometry_refs(spec.get("geometry_refs", []))
            if not refs:
                raise ValueError(f"{section_name}.{feature_id} must include geometry_refs")
            for ref in refs:
                kind, _, value = ref.partition(":")
                if kind == "face" and value not in face_ids:
                    raise ValueError(f"Unknown face reference: {ref}")
                if kind == "face_group" and value not in group_ids:
                    raise ValueError(f"Unknown face group reference: {ref}")
                if kind == "solid" and solid_ids and value not in solid_ids:
                    raise ValueError(f"Unknown solid reference: {ref}")
                if kind not in {"face", "face_group", "solid"}:
                    raise ValueError(f"Unsupported geometry reference: {ref}")


def build_review_template(feature_graph_draft: dict) -> dict:
    """Build a project-specific YAML template without confirming candidates."""
    candidate_reference = {}
    for feature in feature_graph_draft.get("features", []):
        candidate_reference[str(feature["id"])] = {
            "type": feature.get("type"),
            "geometry_refs": _normalize_geometry_refs(feature.get("geometry_refs", [])),
            "confidence": feature.get("confidence"),
        }
    return {
        "confirmed_features": {},
        "rejected_candidates": [],
        "manual_groups": {},
        "candidate_reference": candidate_reference,
        "unassigned_faces": [f"face:{face_id}" for face_id in feature_graph_draft.get("unassigned_faces", [])],
    }


def write_review_template(path: Path, feature_graph_draft: dict) -> None:
    """Write a project-specific reviewed-label template."""
    path.write_text(
        yaml.safe_dump(build_review_template(feature_graph_draft), sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _upsert_review_feature(features: list, by_id: dict, feature_id: str, spec: Mapping[str, object], status: str) -> None:
    geometry_refs = _normalize_geometry_refs(spec.get("geometry_refs", []))
    record = by_id.get(feature_id)
    if record is None:
        record = {
            "id": feature_id,
            "type": spec.get("type", "UnknownFeature"),
            "geometry_refs": geometry_refs,
            "confidence": 1.0,
            "evidence": ["human reviewed label"],
            "status": status,
            "requires_human_review": False,
        }
        features.append(record)
        by_id[feature_id] = record
    else:
        record["type"] = spec.get("type", record.get("type", "UnknownFeature"))
        record["geometry_refs"] = geometry_refs or _normalize_geometry_refs(record.get("geometry_refs", []))
        record["status"] = status
        record["requires_human_review"] = False
        record["confidence"] = 1.0
        evidence = list(record.get("evidence", []))
        evidence.append("human reviewed label")
        record["evidence"] = _unique(evidence)
    for optional_key in ("default_boundary_role", "material", "metadata"):
        if optional_key in spec:
            record[optional_key] = spec[optional_key]


def _normalize_geometry_refs(values: object) -> list:
    if not isinstance(values, list):
        return []
    refs = []
    for value in values:
        text = str(value)
        if text.startswith(("face:", "face_group:", "solid:")):
            refs.append(text)
        elif text.startswith("F"):
            refs.append(f"face:{text}")
        elif text.startswith("G"):
            refs.append(f"face_group:{text}")
        else:
            refs.append(text)
    return refs


def _raw_face_ids(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    result = set()
    for value in values:
        text = str(value)
        if text.startswith("face:"):
            result.add(text.split(":", 1)[1])
        elif text.startswith("F"):
            result.add(text)
    return result


def _unique(values: list) -> list:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
