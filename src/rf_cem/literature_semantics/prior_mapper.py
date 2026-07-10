"""Map reviewed literature semantics into auditable expert prior drafts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .types import (
    DRAFT_PRIOR_SCHEMA_VERSION,
    MERGEABLE_REVIEW_STATUSES,
    MUTABLE_REVIEW_FIELDS,
    SEMANTIC_ITEM_SECTIONS,
    PriorDraftError,
    canonical_sha256,
)
from .validator import (
    FORBIDDEN_EXECUTABLE_KEYS,
    assert_valid_semantic_package,
    executable_branch_matches,
    load_ontology,
    validate_semantic_package,
)
from rf_cem.parametric_geometry.expert_prior import ExpertPriorError, validate_expert_prior


MERGE_PRECEDENCE = [
    "reviewed_feature_labels",
    "baseline_geometry",
    "human_accepted_multi_source_text_or_hybrid_literature",
    "single_source_text_literature",
    "image_only_literature",
]

DEFAULT_VARIANT_TARGET = "grammar.variant_policy.default_selected_variant"
ENABLED_VARIANTS_TARGET = "grammar.variant_policy.enabled_variants"
CURVE_SELECTION_PREFIX = "grammar.variant_policy.curve_selection."
ADDITIVE_TARGETS = {"literature_semantics"}


def build_draft_prior(
    package: Mapping[str, Any],
    *,
    base_prior_ref: str | Path = "expert_prior.v0.yaml",
    literature_semantics_ref: str | Path = "literature_semantics.v0.json",
    base_prior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an auditable expert_prior.draft.v0 YAML payload."""
    if base_prior is None:
        raise PriorDraftError("base_prior is required to build an integrity-bound draft")
    issues = assert_valid_semantic_package(package)
    ontology = load_ontology()
    enabled_variants = _enabled_variants(base_prior)
    matches = executable_branch_matches(package, ontology)
    branch_id, branch_rule = matches[0] if len(matches) == 1 else (None, None)
    executable_paths = _executable_semantic_paths(package, branch_rule)
    source_refs = _source_refs_for_paths(package, executable_paths)
    confidence = _confidence_for_paths(package, executable_paths)
    candidate_shape_priors = _candidate_shape_priors(
        branch_id,
        branch_rule,
        enabled_variants,
        source_refs,
        confidence,
    )
    grammar_suggestion = _grammar_suggestion(branch_id, branch_rule, enabled_variants, source_refs)
    parameter_suggestions = _parameter_range_suggestions(package, ontology)
    audit_metadata = {
        "schema_version": "literature_semantics_prior_metadata.v0",
        "literature_semantics_ref": str(literature_semantics_ref),
        "semantic_package_sha256": canonical_sha256(dict(package)),
        "executable_branch": branch_id,
        "executable_eligible": branch_rule is not None,
        "request_context": copy.deepcopy(package.get("request_context", {})),
        "classification": copy.deepcopy(package.get("classification", {})),
        "candidate_shape_priors": candidate_shape_priors,
        "parameter_range_suggestions": parameter_suggestions,
        "source_evidence": {
            "required_for_all_nonbaseline_fields": True,
            "source_refs": source_refs,
        },
    }
    patch_items = _patch_items(
        package,
        branch_id,
        branch_rule,
        enabled_variants,
        executable_paths,
        audit_metadata,
    )
    draft = {
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
            "requires_patch_review": True,
            "allowed_review_statuses": sorted(MERGEABLE_REVIEW_STATUSES),
            "patch_items": patch_items,
        },
        "integrity": {
            "algorithm": "sha256",
            "semantic_package_sha256": canonical_sha256(dict(package)),
            "base_prior_sha256": canonical_sha256(dict(base_prior)),
        },
    }
    draft["integrity"]["immutable_draft_sha256"] = immutable_draft_sha256(draft)
    return draft


def merge_draft_prior(
    base_prior: Mapping[str, Any],
    draft_prior: Mapping[str, Any],
    *,
    semantic_package: Mapping[str, Any],
    require_reviewed: bool = True,
) -> dict[str, Any]:
    """Merge accepted draft prior patch items into an expert_prior.v0 mapping."""
    if draft_prior.get("schema_version") != DRAFT_PRIOR_SCHEMA_VERSION:
        raise PriorDraftError(f"unsupported draft schema_version: {draft_prior.get('schema_version')!r}")
    patch_items = draft_prior.get("review", {}).get("patch_items", [])
    if not isinstance(patch_items, list):
        raise PriorDraftError("draft prior review.patch_items must be a list")
    _verify_draft_integrity(base_prior, semantic_package, draft_prior)
    ontology = load_ontology()
    seen_ids: set[str] = set()
    seen_targets: set[str] = set()
    for item in patch_items:
        if not isinstance(item, Mapping):
            raise PriorDraftError("patch item must be a mapping")
        patch_id = str(item.get("id", ""))
        target_path = str(item.get("target_path", ""))
        if not patch_id or patch_id in seen_ids:
            raise PriorDraftError(f"patch id is missing or duplicated: {patch_id!r}")
        if not target_path or target_path in seen_targets:
            raise PriorDraftError(f"patch target is missing or duplicated: {target_path!r}")
        seen_ids.add(patch_id)
        seen_targets.add(target_path)
        _validate_patch_item(item, base_prior, ontology)
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
        status = item.get("human_review_status")
        if status not in MERGEABLE_REVIEW_STATUSES:
            continue
        if status == "accepted_as_soft_only" and _is_executable_target(str(item["target_path"])):
            soft_only.append(copy.deepcopy(dict(item)))
            continue
        target_path = str(item["target_path"])
        if target_path == "literature_semantics":
            _merge_literature_metadata(result, item.get("value"))
        else:
            _set_path(result, target_path.split("."), copy.deepcopy(item.get("value")))
    if soft_only:
        metadata = _ensure_literature_collection(result)
        metadata.setdefault("soft_only_patch_items", []).extend(soft_only)
    _validate_merged_variant_policy(result, ontology)
    try:
        validate_expert_prior(result)
    except ExpertPriorError as exc:
        raise PriorDraftError(f"merged expert prior is invalid: {exc}") from exc
    return result


def blocking_validation_errors(package: Mapping[str, Any]) -> list[str]:
    """Return formatted blocking validation errors for CLI use."""
    return [
        f"{issue.path}: {issue.message}"
        for issue in validate_semantic_package(package)
        if issue.severity == "error"
    ]


def _patch_items(
    package: Mapping[str, Any],
    branch_id: str | None,
    branch_rule: Mapping[str, Any] | None,
    enabled_variants: Sequence[str],
    executable_paths: list[str],
    audit_metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    all_paths = _all_semantic_paths(package)
    metadata_patch = _patch(
        package,
        "patch.literature_metadata",
        "literature_semantics",
        audit_metadata,
        all_paths,
        "Preserve non-executable literature provenance and soft suggestions.",
        branch_id=branch_id,
    )
    if branch_rule is None:
        return [metadata_patch]

    preferred = [str(item) for item in branch_rule.get("preferred_variants", [])]
    selected_variant = _first_supported(enabled_variants, preferred)
    allowed_variants = _supported_subset(enabled_variants, preferred)
    curve_region = str(branch_rule.get("curve_region", ""))
    curve_variant = str(branch_rule.get("curve_variant", ""))
    curve_value = str(branch_rule.get("curve_value", ""))
    curve_target = f"{CURVE_SELECTION_PREFIX}{curve_region}.{curve_variant}"
    patches = [
        _patch(
            package,
            "patch.default_variant",
            DEFAULT_VARIANT_TARGET,
            selected_variant,
            executable_paths,
            "Select a family-consistent default shape prior candidate.",
            branch_id=branch_id,
        ),
        _patch(
            package,
            "patch.enabled_variants",
            ENABLED_VARIANTS_TARGET,
            allowed_variants,
            executable_paths,
            "Limit candidate variants to current supported grammar branches.",
            branch_id=branch_id,
        ),
        _patch(
            package,
            "patch.curve_selection",
            curve_target,
            curve_value,
            executable_paths,
            "Use only existing v0 curve-selection names.",
            branch_id=branch_id,
        ),
    ]
    patches.append(metadata_patch)
    return patches


def _patch(
    package: Mapping[str, Any],
    patch_id: str,
    target_path: str,
    value: object,
    semantic_paths: list[str],
    rationale: str,
    *,
    branch_id: str | None,
) -> dict[str, Any]:
    return {
        "id": patch_id,
        "target_path": target_path,
        "value": value,
        "human_review_status": "pending",
        "source_refs": _source_refs_for_paths(package, semantic_paths),
        "confidence": _confidence_for_paths(package, semantic_paths),
        "semantic_paths": semantic_paths,
        "review_basis": _review_basis(package, semantic_paths),
        "executable_branch": branch_id,
        "rationale": rationale,
    }


def _validate_patch_item(
    item: Mapping[str, Any],
    base_prior: Mapping[str, Any],
    ontology: Mapping[str, Any],
) -> None:
    target = str(item.get("target_path", ""))
    if not target:
        raise PriorDraftError("patch item missing target_path")
    if not item.get("source_refs"):
        raise PriorDraftError(f"patch item {item.get('id', '?')} missing source_refs")
    value = item.get("value")
    enabled = set(_enabled_variants(base_prior))
    supported = set(str(entry) for entry in ontology.get("supported_variants", []))
    if target == DEFAULT_VARIANT_TARGET:
        if not isinstance(value, str) or value not in enabled or value not in supported:
            raise PriorDraftError(f"default variant is not enabled and ontology-supported: {value!r}")
        return
    if target == ENABLED_VARIANTS_TARGET:
        if not isinstance(value, list) or not value or not all(isinstance(entry, str) for entry in value):
            raise PriorDraftError("enabled variants patch must be a non-empty string list")
        if len(value) != len(set(value)):
            raise PriorDraftError("enabled variants patch contains duplicates")
        if not set(value).issubset(enabled & supported):
            raise PriorDraftError("enabled variants patch contains unknown or newly invented variants")
        return
    if target.startswith(CURVE_SELECTION_PREFIX):
        parts = target.split(".")
        if len(parts) != 5:
            raise PriorDraftError(f"curve selection target must be an exact region/variant path: {target}")
        region, variant = parts[-2:]
        base_value = (
            base_prior.get("grammar", {})
            .get("variant_policy", {})
            .get("curve_selection", {})
            .get(region, {})
            .get(variant)
        )
        if base_value is None or variant not in enabled:
            raise PriorDraftError(f"curve selection target is absent from the verified base prior: {target}")
        if value != base_value:
            raise PriorDraftError(
                f"v0 literature merge cannot replace a verified curve implementation: {target}={value!r}"
            )
        return
    if target in ADDITIVE_TARGETS:
        if not isinstance(value, Mapping):
            raise PriorDraftError("literature metadata patch must contain a mapping")
        forbidden = _forbidden_mapping_paths(value)
        if forbidden:
            raise PriorDraftError(f"literature metadata contains forbidden executable keys: {', '.join(forbidden)}")
        return
    raise PriorDraftError(f"patch target is not allowed in v0 merge: {target}")


def _is_executable_target(target: str) -> bool:
    return target in {DEFAULT_VARIANT_TARGET, ENABLED_VARIANTS_TARGET} or target.startswith(CURVE_SELECTION_PREFIX)


def _set_path(target: dict[str, Any], parts: list[str], value: object) -> None:
    current = target
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise PriorDraftError(f"cannot merge into non-mapping path: {'.'.join(parts)}")
        current = child
    current[parts[-1]] = value


def _merge_literature_metadata(target: dict[str, Any], value: object) -> None:
    if not isinstance(value, Mapping):
        raise PriorDraftError("literature metadata patch must contain a mapping")
    record = copy.deepcopy(dict(value))
    digest = str(record.get("semantic_package_sha256", ""))
    if not digest:
        raise PriorDraftError("literature metadata record is missing semantic_package_sha256")

    collection = _ensure_literature_collection(target)
    records = collection["records"]
    for current in records:
        if isinstance(current, Mapping) and current.get("semantic_package_sha256") == digest:
            if dict(current) != record:
                raise PriorDraftError(
                    "literature metadata conflicts with an existing record for the same semantic package"
                )
            return
    records.append(record)


def _ensure_literature_collection(target: dict[str, Any]) -> dict[str, Any]:
    existing = target.get("literature_semantics")
    if existing is None:
        collection: dict[str, Any] = {
            "schema_version": "literature_semantics_collection.v0",
            "records": [],
        }
        target["literature_semantics"] = collection
    elif (
        isinstance(existing, dict)
        and existing.get("schema_version") == "literature_semantics_collection.v0"
        and isinstance(existing.get("records"), list)
    ):
        collection = existing
    elif isinstance(existing, Mapping):
        legacy = copy.deepcopy(dict(existing))
        collection = {
            "schema_version": "literature_semantics_collection.v0",
            "records": [legacy],
        }
        target["literature_semantics"] = collection
    else:
        raise PriorDraftError("existing literature_semantics must be a mapping")
    return collection


def _verify_draft_integrity(
    base_prior: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
    draft_prior: Mapping[str, Any],
) -> None:
    integrity = draft_prior.get("integrity", {})
    if not isinstance(integrity, Mapping) or integrity.get("algorithm") != "sha256":
        raise PriorDraftError("draft prior is missing supported integrity metadata")
    expected = {
        "semantic_package_sha256": canonical_sha256(dict(semantic_package)),
        "base_prior_sha256": canonical_sha256(dict(base_prior)),
        "immutable_draft_sha256": immutable_draft_sha256(draft_prior),
    }
    for key, digest in expected.items():
        if integrity.get(key) != digest:
            raise PriorDraftError(f"draft integrity mismatch for {key}")


def immutable_draft_sha256(draft_prior: Mapping[str, Any]) -> str:
    """Hash the immutable draft fields while allowing patch-level review edits."""
    return canonical_sha256(_immutable_draft_projection(draft_prior))


def _immutable_draft_projection(draft_prior: Mapping[str, Any]) -> dict[str, Any]:
    projected = copy.deepcopy(dict(draft_prior))
    integrity = projected.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("immutable_draft_sha256", None)
    review = projected.get("review")
    patch_items = review.get("patch_items") if isinstance(review, dict) else None
    if isinstance(patch_items, list):
        for item in patch_items:
            if isinstance(item, dict):
                for key in MUTABLE_REVIEW_FIELDS:
                    item.pop(key, None)
    return projected


def _validate_merged_variant_policy(
    prior: Mapping[str, Any],
    ontology: Mapping[str, Any],
) -> None:
    policy = prior.get("grammar", {}).get("variant_policy", {})
    enabled = policy.get("enabled_variants", [])
    selected = policy.get("default_selected_variant")
    supported = set(str(item) for item in ontology.get("supported_variants", []))
    if not isinstance(enabled, list) or not enabled or not set(enabled).issubset(supported):
        raise PriorDraftError("merged enabled_variants are empty or outside the ontology")
    if selected not in enabled:
        raise PriorDraftError("merged default_selected_variant is not enabled")


def _forbidden_mapping_paths(value: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_EXECUTABLE_KEYS:
                found.append(child_path)
            found.extend(_forbidden_mapping_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_mapping_paths(child, f"{path}[{index}]"))
    return found


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


def _candidate_shape_priors(
    branch_id: str | None,
    branch_rule: Mapping[str, Any] | None,
    enabled_variants: Sequence[str],
    source_refs: list[str],
    confidence: float,
) -> list[dict[str, Any]]:
    if branch_id is None or branch_rule is None:
        return []
    preferred = [str(item) for item in branch_rule.get("preferred_variants", [])]
    return [
        {
            "id": f"{branch_id}.{variant}",
            "variant": variant,
            "summary": f"Audit candidate for executable branch {branch_id}; no geometry is generated at this stage.",
            "human_review_status": "pending",
            "source_refs": source_refs,
            "confidence": confidence,
        }
        for variant in preferred
        if variant in enabled_variants
    ][:3]


def _grammar_suggestion(
    branch_id: str | None,
    branch_rule: Mapping[str, Any] | None,
    enabled_variants: Sequence[str],
    source_refs: list[str],
) -> dict[str, Any]:
    if branch_id is None or branch_rule is None:
        return {
            "executable_eligible": False,
            "reason": "No current single-cell grammar branch matches this literature package.",
            "rationale_refs": source_refs,
        }
    preferred = [str(item) for item in branch_rule.get("preferred_variants", [])]
    region = str(branch_rule.get("curve_region", ""))
    value = str(branch_rule.get("curve_value", ""))
    discourage = ["iris_torus_exact"] if branch_id == "srf_elliptical" else []
    return {
        "executable_eligible": True,
        "branch_id": branch_id,
        "variant_policy": {
            "allow_variants": _supported_subset(enabled_variants, preferred),
            "discourage_variants": _supported_subset(enabled_variants, discourage),
            "curve_selection": {
                region: {
                    "preferred": value,
                    "allowed": [value],
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


def _all_semantic_paths(package: Mapping[str, Any]) -> list[str]:
    paths = ["classification"]
    for section in SEMANTIC_ITEM_SECTIONS:
        paths.extend(
            f"{section}[{index}]"
            for index, item in enumerate(package.get(section, []) or [])
            if isinstance(item, Mapping)
        )
    return paths


def _executable_semantic_paths(
    package: Mapping[str, Any],
    branch_rule: Mapping[str, Any] | None,
) -> list[str]:
    paths = ["classification"]
    for section in ("named_features", "shape_motifs"):
        paths.extend(
            f"{section}[{index}]"
            for index, item in enumerate(package.get(section, []) or [])
            if isinstance(item, Mapping)
        )
    curve_region = str((branch_rule or {}).get("curve_region", ""))
    paths.extend(
        f"curve_priors[{index}]"
        for index, item in enumerate(package.get("curve_priors", []) or [])
        if isinstance(item, Mapping) and item.get("curve_region") == curve_region
    )
    return paths


def _semantic_item_at_path(package: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    if path == "classification":
        value = package.get("classification", {})
        return value if isinstance(value, Mapping) else {}
    if not path.endswith("]") or "[" not in path:
        return {}
    section, index_text = path[:-1].split("[", 1)
    try:
        value = (package.get(section, []) or [])[int(index_text)]
    except (IndexError, TypeError, ValueError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _source_refs_for_paths(package: Mapping[str, Any], semantic_paths: Sequence[str]) -> list[str]:
    refs: set[str] = set()
    for path in semantic_paths:
        item = _semantic_item_at_path(package, path)
        key = "evidence_refs" if path == "classification" else "source_refs"
        refs.update(str(ref) for ref in item.get(key, []) or [])
    return sorted(refs)


def _confidence_for_paths(package: Mapping[str, Any], semantic_paths: Sequence[str]) -> float:
    values: list[float] = []
    for path in semantic_paths:
        value = _semantic_item_at_path(package, path).get("confidence")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return round(min(values), 3) if values else 0.0


def _review_basis(package: Mapping[str, Any], semantic_paths: Sequence[str]) -> list[dict[str, Any]]:
    basis = []
    for path in semantic_paths:
        item = _semantic_item_at_path(package, path)
        source_key = "evidence_refs" if path == "classification" else "source_refs"
        basis.append(
            {
                "semantic_path": path,
                "human_review_status": item.get("human_review_status", "pending"),
                "source_refs": [str(ref) for ref in item.get(source_key, []) or []],
                "confidence": item.get("confidence", 0.0),
            }
        )
    return basis


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
