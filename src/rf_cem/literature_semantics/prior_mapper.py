"""Map reviewed literature semantics into auditable expert prior drafts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .types import (
    DRAFT_PRIOR_SCHEMA_VERSION,
    MERGEABLE_REVIEW_STATUSES,
    PriorDraftError,
)
from .validator import assert_valid_semantic_package, load_ontology, validate_semantic_package


MERGE_PRECEDENCE = [
    "reviewed_feature_labels",
    "baseline_geometry",
    "human_accepted_multi_source_text_or_hybrid_literature",
    "single_source_text_literature",
    "image_only_literature",
]

EXECUTABLE_TARGET_PREFIXES = (
    "grammar.variant_policy.default_selected_variant",
    "grammar.variant_policy.enabled_variants",
    "grammar.variant_policy.curve_selection.",
)
ADDITIVE_TARGETS = {"literature_semantics"}


def build_draft_prior(
    package: Mapping[str, Any],
    *,
    base_prior_ref: str | Path = "expert_prior.v0.yaml",
    literature_semantics_ref: str | Path = "literature_semantics.v0.json",
    base_prior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an auditable expert_prior.draft.v0 YAML payload."""
    issues = assert_valid_semantic_package(package)
    ontology = load_ontology()
    enabled_variants = _enabled_variants(base_prior)
    branch = _branch_for(package)
    status = _aggregate_review_status(package)
    source_refs = _all_source_refs(package)
    confidence = _global_confidence(package)
    candidate_shape_priors = _candidate_shape_priors(branch, enabled_variants, status, source_refs, confidence)
    grammar_suggestion = _grammar_suggestion(branch, enabled_variants, source_refs)
    parameter_suggestions = _parameter_range_suggestions(package, ontology)
    audit_metadata = {
        "schema_version": "literature_semantics_prior_metadata.v0",
        "literature_semantics_ref": str(literature_semantics_ref),
        "request_context": copy.deepcopy(package.get("request_context", {})),
        "classification": copy.deepcopy(package.get("classification", {})),
        "candidate_shape_priors": candidate_shape_priors,
        "parameter_range_suggestions": parameter_suggestions,
        "source_evidence": {
            "required_for_all_nonbaseline_fields": True,
            "source_refs": source_refs,
        },
    }
    patch_items = _patch_items(branch, enabled_variants, status, source_refs, confidence, audit_metadata)
    return {
        "schema_version": DRAFT_PRIOR_SCHEMA_VERSION,
        "base_prior_ref": str(base_prior_ref),
        "literature_semantics_ref": str(literature_semantics_ref),
        "merge_policy": {
            "precedence": MERGE_PRECEDENCE,
            "image_only_requires_human_review": True,
            "single_source_numeric_is_soft_only": True,
            "require_source_evidence_for_nonbaseline_fields": True,
        },
        "validation_issues": [issue.__dict__ for issue in issues],
        "candidate_shape_priors": candidate_shape_priors,
        "grammar": grammar_suggestion,
        "derived_parameter_candidates": parameter_suggestions,
        "source_evidence": audit_metadata["source_evidence"],
        "review": {
            "merge_blocked": any(item["human_review_status"] not in MERGEABLE_REVIEW_STATUSES for item in patch_items),
            "allowed_review_statuses": sorted(MERGEABLE_REVIEW_STATUSES),
            "patch_items": patch_items,
        },
    }


def merge_draft_prior(
    base_prior: Mapping[str, Any],
    draft_prior: Mapping[str, Any],
    *,
    require_reviewed: bool = True,
) -> dict[str, Any]:
    """Merge accepted draft prior patch items into an expert_prior.v0 mapping."""
    if draft_prior.get("schema_version") != DRAFT_PRIOR_SCHEMA_VERSION:
        raise PriorDraftError(f"unsupported draft schema_version: {draft_prior.get('schema_version')!r}")
    patch_items = draft_prior.get("review", {}).get("patch_items", [])
    if not isinstance(patch_items, list):
        raise PriorDraftError("draft prior review.patch_items must be a list")
    blocked = [
        item
        for item in patch_items
        if isinstance(item, Mapping) and item.get("human_review_status") not in MERGEABLE_REVIEW_STATUSES
    ]
    if require_reviewed and blocked:
        blocked_ids = ", ".join(str(item.get("id", "?")) for item in blocked)
        raise PriorDraftError(f"draft prior has unreviewed or rejected patch items: {blocked_ids}")

    result: dict[str, Any] = copy.deepcopy(dict(base_prior))
    soft_only: list[dict[str, Any]] = []
    for item in patch_items:
        if not isinstance(item, Mapping):
            raise PriorDraftError("patch item must be a mapping")
        status = item.get("human_review_status")
        if status not in MERGEABLE_REVIEW_STATUSES:
            continue
        _validate_patch_item(item)
        if status == "accepted_as_soft_only" and _is_executable_target(str(item["target_path"])):
            soft_only.append(copy.deepcopy(dict(item)))
            continue
        _set_path(result, str(item["target_path"]).split("."), copy.deepcopy(item.get("value")))
    if soft_only:
        metadata = result.setdefault("literature_semantics", {})
        metadata.setdefault("soft_only_patch_items", []).extend(soft_only)
    return result


def blocking_validation_errors(package: Mapping[str, Any]) -> list[str]:
    """Return formatted blocking validation errors for CLI use."""
    return [
        f"{issue.path}: {issue.message}"
        for issue in validate_semantic_package(package)
        if issue.severity == "error"
    ]


def _patch_items(
    branch: str,
    enabled_variants: Sequence[str],
    status: str,
    source_refs: list[str],
    confidence: float,
    audit_metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if branch == "normal_conducting":
        selected_variant = _first_supported(enabled_variants, ["iris_torus_exact", "expanded_smooth_nose", "free_equator_smooth"])
        allowed_variants = _supported_subset(enabled_variants, ["iris_torus_exact", "expanded_smooth_nose", "free_equator_smooth"])
        curve_target = "grammar.variant_policy.curve_selection.nose.iris_torus_exact"
        curve_value = "smooth_semicircle_then_reverse_quarter_arc"
    else:
        selected_variant = _first_supported(enabled_variants, ["free_equator_smooth", "expanded_smooth_nose"])
        allowed_variants = _supported_subset(
            enabled_variants,
            ["free_equator_smooth", "expanded_smooth_nose", "manual_equator_inset_3mm", "manual_equator_bulge_3mm"],
        )
        curve_target = "grammar.variant_policy.curve_selection.equator.free_equator_smooth"
        curve_value = "local_nurbs_crown"
    return [
        _patch(
            "patch.default_variant",
            "grammar.variant_policy.default_selected_variant",
            selected_variant,
            status,
            source_refs,
            confidence,
            "Select a family-consistent default shape prior candidate.",
        ),
        _patch(
            "patch.enabled_variants",
            "grammar.variant_policy.enabled_variants",
            allowed_variants,
            status,
            source_refs,
            confidence,
            "Limit candidate variants to current supported grammar branches.",
        ),
        _patch(
            "patch.curve_selection",
            curve_target,
            curve_value,
            status,
            source_refs,
            confidence,
            "Use only existing v0 curve-selection names.",
        ),
        _patch(
            "patch.literature_metadata",
            "literature_semantics",
            audit_metadata,
            status,
            source_refs,
            confidence,
            "Preserve non-executable literature provenance and soft suggestions.",
        ),
    ]


def _patch(
    patch_id: str,
    target_path: str,
    value: object,
    status: str,
    source_refs: list[str],
    confidence: float,
    rationale: str,
) -> dict[str, Any]:
    return {
        "id": patch_id,
        "target_path": target_path,
        "value": value,
        "human_review_status": status,
        "source_refs": source_refs,
        "confidence": confidence,
        "rationale": rationale,
    }


def _validate_patch_item(item: Mapping[str, Any]) -> None:
    target = str(item.get("target_path", ""))
    if not target:
        raise PriorDraftError("patch item missing target_path")
    if not item.get("source_refs"):
        raise PriorDraftError(f"patch item {item.get('id', '?')} missing source_refs")
    if target not in ADDITIVE_TARGETS and not _is_executable_target(target):
        raise PriorDraftError(f"patch target is not allowed in v0 merge: {target}")


def _is_executable_target(target: str) -> bool:
    return any(target.startswith(prefix) for prefix in EXECUTABLE_TARGET_PREFIXES)


def _set_path(target: dict[str, Any], parts: list[str], value: object) -> None:
    current = target
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise PriorDraftError(f"cannot merge into non-mapping path: {'.'.join(parts)}")
        current = child
    current[parts[-1]] = value


def _enabled_variants(base_prior: Mapping[str, Any] | None) -> list[str]:
    variants = (
        (base_prior or {})
        .get("grammar", {})
        .get("variant_policy", {})
        .get("enabled_variants", [])
    )
    if isinstance(variants, list) and variants:
        return [str(item) for item in variants]
    return [
        "iris_torus_exact",
        "expanded_smooth_nose",
        "free_equator_smooth",
        "manual_equator_inset_3mm",
        "manual_equator_bulge_3mm",
        "manual_equator_wide_soft",
    ]


def _branch_for(package: Mapping[str, Any]) -> str:
    regime = str(package.get("request_context", {}).get("operating_regime", "unknown"))
    family = str(package.get("classification", {}).get("cavity_family", "unknown"))
    if regime == "normal_conducting" or family in {"reentrant", "nose_cone"}:
        return "normal_conducting"
    return "superconducting"


def _candidate_shape_priors(
    branch: str,
    enabled_variants: Sequence[str],
    status: str,
    source_refs: list[str],
    confidence: float,
) -> list[dict[str, Any]]:
    if branch == "normal_conducting":
        candidates = [
            ("nc_nose_reference", "iris_torus_exact", "NC nose/reentrant reference using the verified nose arc branch."),
            ("nc_smooth_nose_probe", "expanded_smooth_nose", "NC smooth-nose probe within the current single-cell grammar."),
            ("nc_free_equator_probe", "free_equator_smooth", "NC-compatible exploratory smooth-equator candidate."),
        ]
    else:
        candidates = [
            ("srf_free_equator_smooth", "free_equator_smooth", "SRF smooth/free-equator candidate."),
            ("srf_expanded_smooth_nose", "expanded_smooth_nose", "SRF smooth-wall reference candidate."),
            ("srf_equator_inset_probe", "manual_equator_inset_3mm", "Small equator crown perturbation for visual review."),
        ]
    return [
        {
            "id": candidate_id,
            "variant": variant,
            "summary": summary,
            "human_review_status": status,
            "source_refs": source_refs,
            "confidence": confidence,
        }
        for candidate_id, variant, summary in candidates
        if variant in enabled_variants
    ][:3]


def _grammar_suggestion(branch: str, enabled_variants: Sequence[str], source_refs: list[str]) -> dict[str, Any]:
    if branch == "normal_conducting":
        return {
            "variant_policy": {
                "allow_variants": _supported_subset(enabled_variants, ["iris_torus_exact", "expanded_smooth_nose", "free_equator_smooth"]),
                "discourage_variants": [],
                "curve_selection": {
                    "nose": {
                        "preferred": "smooth_semicircle_then_reverse_quarter_arc",
                        "allowed": ["smooth_semicircle_then_reverse_quarter_arc", "local_nurbs_smooth_fallback"],
                    }
                },
                "rationale_refs": source_refs,
            }
        }
    return {
        "variant_policy": {
            "allow_variants": _supported_subset(
                enabled_variants,
                ["free_equator_smooth", "expanded_smooth_nose", "manual_equator_inset_3mm", "manual_equator_bulge_3mm"],
            ),
            "discourage_variants": _supported_subset(enabled_variants, ["iris_torus_exact"]),
            "curve_selection": {
                "equator": {
                    "preferred": "local_nurbs_crown",
                    "allowed": ["local_nurbs_crown", "cylinder"],
                }
            },
            "rationale_refs": source_refs,
        }
    }


def _parameter_range_suggestions(package: Mapping[str, Any], ontology: Mapping[str, Any]) -> list[dict[str, Any]]:
    aliases = ontology.get("parameter_aliases", {}) or {}
    suggestions: list[dict[str, Any]] = []
    for item in package.get("parameter_ranges", []) or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("parameter_name", ""))
        canonical = aliases.get(name, name)
        range_type = str(item.get("range_type", "soft"))
        if _is_image_only(item, package) or _single_source(item, package):
            range_type = "soft"
        suggestions.append(
            {
                "parameter_name": name,
                "canonical_parameter": canonical,
                "range": copy.deepcopy(item.get("range")),
                "unit": item.get("unit"),
                "range_type": range_type,
                "merge_status": "audit_metadata_only",
                "source_refs": copy.deepcopy(item.get("source_refs", [])),
                "human_review_status": item.get("human_review_status", "pending"),
                "confidence": item.get("confidence", 0.0),
            }
        )
    return suggestions


def _aggregate_review_status(package: Mapping[str, Any]) -> str:
    statuses = []
    for section in (
        "named_features",
        "shape_motifs",
        "curve_priors",
        "parameter_ranges",
        "optimization_objectives",
        "physical_constraints",
    ):
        statuses.extend(
            str(item.get("human_review_status", "pending"))
            for item in package.get(section, []) or []
            if isinstance(item, Mapping)
        )
    if not statuses:
        return "pending"
    if "pending" in statuses:
        return "pending"
    if "needs_more_evidence" in statuses:
        return "needs_more_evidence"
    if all(status == "rejected" for status in statuses):
        return "rejected"
    if "accepted" in statuses:
        return "accepted"
    if "accepted_as_soft_only" in statuses:
        return "accepted_as_soft_only"
    return "pending"


def _all_source_refs(package: Mapping[str, Any]) -> list[str]:
    refs = set(str(ref) for ref in package.get("classification", {}).get("evidence_refs", []) or [])
    for section in (
        "named_features",
        "shape_motifs",
        "curve_priors",
        "parameter_ranges",
        "optimization_objectives",
        "physical_constraints",
    ):
        for item in package.get(section, []) or []:
            if isinstance(item, Mapping):
                refs.update(str(ref) for ref in item.get("source_refs", []) or [])
    return sorted(refs)


def _global_confidence(package: Mapping[str, Any]) -> float:
    values = []
    classification_conf = package.get("classification", {}).get("confidence")
    if isinstance(classification_conf, (int, float)) and not isinstance(classification_conf, bool):
        values.append(float(classification_conf))
    for section in (
        "named_features",
        "shape_motifs",
        "curve_priors",
        "parameter_ranges",
        "optimization_objectives",
        "physical_constraints",
    ):
        for item in package.get(section, []) or []:
            if isinstance(item, Mapping):
                value = item.get("confidence")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values.append(float(value))
    if not values:
        return 0.0
    return round(min(values), 3)


def _supported_subset(enabled_variants: Sequence[str], preferred: Sequence[str]) -> list[str]:
    return [variant for variant in preferred if variant in enabled_variants]


def _first_supported(enabled_variants: Sequence[str], preferred: Sequence[str]) -> str:
    values = _supported_subset(enabled_variants, preferred)
    if not values:
        raise PriorDraftError(f"base prior does not enable any supported variants from: {', '.join(preferred)}")
    return values[0]


def _is_image_only(item: Mapping[str, Any], package: Mapping[str, Any]) -> bool:
    image_refs = {str(entry.get("id")) for entry in package.get("image_evidence", []) or [] if isinstance(entry, Mapping)}
    refs = {str(ref) for ref in item.get("source_refs", []) or []}
    return bool(refs) and refs.issubset(image_refs)


def _single_source(item: Mapping[str, Any], package: Mapping[str, Any]) -> bool:
    index = {}
    for section in ("text_evidence", "image_evidence"):
        for entry in package.get(section, []) or []:
            if isinstance(entry, Mapping) and entry.get("id"):
                index[str(entry["id"])] = str(entry.get("paper_id") or entry.get("source_id") or "")
    sources = {index.get(str(ref), "") for ref in item.get("source_refs", []) or []}
    sources.discard("")
    return len(sources) <= 1


def read_prior_yaml(path: Path) -> dict[str, Any]:
    """Read an expert prior YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PriorDraftError(f"expert prior YAML must contain a mapping: {path}")
    return data
