"""Normalize v0 literature claims for consistent human review.

This module is a display adapter only.  It does not mutate the source
``literature_semantics.v0`` package or turn a reviewed claim into executable
geometry.  Missing values remain JSON ``null``; explicit non-applicability is
represented separately by ``applicability.status``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SEMANTIC_VIEW_SCHEMA_VERSION = "literature_semantic_candidate_view.v1"

_SECTION_CLAIMS = {
    "classification": ("cavity_classification", "classifies_as"),
    "named_features": ("feature_presence", "has_feature"),
    "shape_motifs": ("shape_motif", "has_shape_motif"),
    "curve_priors": ("curve_policy", "allows_curve_representation"),
    "parameter_ranges": ("parameter_range", "has_parameter_range"),
    "optimization_objectives": ("optimization_objective", "optimizes_for"),
    "physical_constraints": ("physical_constraint", "is_constrained_by"),
    "draft_prior_patch": ("proposed_patch", "proposes_change"),
}


def build_semantic_candidate_view(
    section: str,
    value: Mapping[str, Any],
    *,
    paper_id: str,
    semantic_path: str,
    request_context: Mapping[str, Any],
    classification: Mapping[str, Any],
    feature_aliases: Mapping[str, Any] | None = None,
    parameter_aliases: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one uniform, JSON-compatible human-review view.

    Frequency is carried as MHz and geometry parameters retain the explicit
    unit supplied by the source claim.  No RF quantity is converted here.
    """

    item = deepcopy(dict(value))
    claim_kind, predicate = _SECTION_CLAIMS.get(
        section, ("unclassified_claim", "states")
    )
    subject_id, entity_type, aliases = _subject(
        section,
        item,
        feature_aliases=feature_aliases or {},
        parameter_aliases=parameter_aliases or {},
    )
    source_refs = list(item.get("source_refs") or item.get("evidence_refs") or [])
    applicability = item.get("applicability")
    applicability = dict(applicability) if isinstance(applicability, Mapping) else {}
    raw_applicability_status = applicability.pop(
        "status", item.get("applicability_status", "applicable")
    )
    applicability_status = str(raw_applicability_status or "applicable")

    return {
        "schema_version": SEMANTIC_VIEW_SCHEMA_VERSION,
        "id": str(item.get("id") or item.get("item_id") or semantic_path),
        "section": section,
        "subject": {
            "canonical_id": subject_id,
            "entity_type": entity_type,
            "aliases": aliases,
        },
        "claim": {
            "kind": claim_kind,
            "predicate": predicate,
            "value": _claim_value(section, item),
            "unit": item.get("unit"),
        },
        "applicability": {
            "status": applicability_status,
            "operating_regime": applicability.get(
                "operating_regime", request_context.get("operating_regime")
            ),
            "cavity_family": applicability.get(
                "cavity_family", classification.get("cavity_family")
            ),
            "cell_count": applicability.get(
                "cell_count", classification.get("cell_count")
            ),
            "beta_class": applicability.get(
                "beta_class", classification.get("beta_class")
            ),
            "geometry_scope": applicability.get(
                "geometry_scope", request_context.get("geometry_scope")
            ),
            # Source frequency is defined by literature_semantics.v0 in MHz.
            "frequency_mhz": applicability.get(
                "frequency_mhz", request_context.get("frequency_target_mhz")
            ),
            "scope": item.get("scope"),
        },
        "provenance": {
            "paper_id": paper_id,
            "source_refs": source_refs,
            "semantic_path": semantic_path,
        },
        "assessment": {
            "confidence": item.get("confidence"),
            "human_review_status": item.get("human_review_status", "pending"),
            "review_note": item.get("review_note", ""),
        },
        "geometry_binding": _geometry_binding(section, item, subject_id),
        "extension": item,
    }


def _subject(
    section: str,
    item: Mapping[str, Any],
    *,
    feature_aliases: Mapping[str, Any],
    parameter_aliases: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    if section == "classification":
        return "cavity", "rf_cavity", []
    if section == "draft_prior_patch":
        return str(item.get("target_path") or "draft_prior"), "configuration_path", []

    raw = _first_text(
        item,
        "feature_name",
        "curve_region",
        "parameter_name",
        "motif_name",
        "objective_name",
        "constraint_id",
        "name",
        "id",
    ) or "unclassified"
    aliases: list[str] = []
    canonical = raw

    if section in {"named_features", "curve_priors"}:
        canonical, aliases = _canonical_feature(raw, feature_aliases)
    elif section == "parameter_ranges":
        canonical_parameter = str(parameter_aliases.get(raw, raw))
        aliases = [raw] if canonical_parameter != raw else []
        canonical = _parameter_subject(canonical_parameter)

    entity_types = {
        "named_features": "geometry_region",
        "shape_motifs": "geometry_motif",
        "curve_priors": "geometry_region",
        "parameter_ranges": "geometry_parameter",
        "optimization_objectives": "rf_objective",
        "physical_constraints": "physical_constraint",
    }
    return canonical, entity_types.get(section, "semantic_subject"), aliases


def _canonical_feature(
    raw: str, feature_aliases: Mapping[str, Any]
) -> tuple[str, list[str]]:
    folded = raw.casefold()
    for canonical, raw_aliases in feature_aliases.items():
        aliases = [str(alias) for alias in raw_aliases or []]
        candidates = [str(canonical), *aliases]
        if folded in {candidate.casefold() for candidate in candidates}:
            return str(canonical), [alias for alias in aliases if alias != canonical]
    return raw, []


def _parameter_subject(parameter_name: str) -> str:
    folded = parameter_name.casefold()
    for marker, subject in (
        ("equator", "equator"),
        ("iris", "iris"),
        ("beam_pipe", "beam_pipe"),
        ("beam-pipe", "beam_pipe"),
    ):
        if marker in folded:
            return subject
    return parameter_name


def _claim_value(section: str, item: Mapping[str, Any]) -> object:
    if section == "classification":
        return {
            key: item.get(key)
            for key in ("cavity_family", "cell_count", "beta_class")
        }
    if section == "named_features":
        return {
            "presence": item.get("presence"),
            "description": item.get("description"),
        }
    if section == "shape_motifs":
        return {
            "motif_name": item.get("motif_name"),
            "description": item.get("description"),
        }
    if section == "curve_priors":
        return {
            "allowed": list(item.get("allowed_curve_types") or []),
            "preferred": list(item.get("preferred_forms") or []),
            "forbidden": list(item.get("forbidden_forms") or []),
        }
    if section == "parameter_ranges":
        return {
            "range": deepcopy(item.get("range")),
            "range_type": item.get("range_type"),
            "interpretation": item.get("interpretation"),
        }
    if section == "optimization_objectives":
        return {
            "objective_name": item.get("objective_name"),
            "description": item.get("description"),
        }
    if section == "physical_constraints":
        return {
            "constraint_type": item.get("constraint_type"),
            "statement": item.get("statement"),
        }
    if section == "draft_prior_patch":
        return {
            "target_path": item.get("target_path"),
            "value": deepcopy(item.get("value")),
        }
    return deepcopy(dict(item))


def _geometry_binding(
    section: str, item: Mapping[str, Any], subject_id: str
) -> dict[str, Any]:
    parameter_names = []
    if section == "parameter_ranges" and item.get("parameter_name"):
        parameter_names.append(str(item["parameter_name"]))
    feature_types = []
    if section == "named_features" and item.get("feature_name"):
        feature_types.append(str(item["feature_name"]))
    return {
        "grammar_region": subject_id
        if section in {"named_features", "curve_priors", "parameter_ranges"}
        else None,
        "parameter_names": parameter_names,
        "feature_types": feature_types,
        "binding_status": "unbound",
    }


def _first_text(item: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return str(value)
    return ""
