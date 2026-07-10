"""Validation for uploaded RF-CEM literature semantic packages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from .types import (
    REVIEW_STATUSES,
    SEMANTIC_ITEM_SECTIONS,
    SEMANTICS_SCHEMA_VERSION,
    LiteratureSemanticsError,
    ValidationIssue,
    read_structured_file,
    semantic_package_file,
)


ONTOLOGY_PATH = Path(__file__).resolve().parent / "ontology_v0.yaml"
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "request_context",
    "evidence_sources",
    "classification",
}
FORBIDDEN_EXECUTABLE_KEYS = {
    "cst_api",
    "executable_formula",
    "formula",
    "generated_step",
    "profile_points",
    "python",
    "step_geometry",
}


def load_ontology(path: Path = ONTOLOGY_PATH) -> dict[str, Any]:
    """Load the v0 ontology whitelist."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise LiteratureSemanticsError(f"ontology must be a YAML mapping: {path}")
    return data


def load_semantic_package(path: Path) -> dict[str, Any]:
    """Load an uploaded literature semantic package from a JSON/YAML file or directory."""
    return read_structured_file(semantic_package_file(path))


def validate_semantic_package(package: Mapping[str, Any], ontology: Mapping[str, Any] | None = None) -> list[ValidationIssue]:
    """Return validation issues for a literature semantic package.

    Errors are blocking for draft-prior generation. Warnings are carried into
    audit output and can be reviewed by a human expert.
    """
    ontology = ontology or load_ontology()
    issues: list[ValidationIssue] = []
    if package.get("schema_version") != SEMANTICS_SCHEMA_VERSION:
        issues.append(_error("schema_version", f"expected {SEMANTICS_SCHEMA_VERSION!r}"))
    missing = sorted(REQUIRED_TOP_LEVEL - set(package))
    for key in missing:
        issues.append(_error(key, "missing required top-level section"))
    if issues:
        return issues

    _validate_request_context(package, ontology, issues)
    _validate_evidence(package, issues)
    _validate_classification(package, ontology, issues)
    evidence_index = _evidence_index(package)
    for section in SEMANTIC_ITEM_SECTIONS:
        values = package.get(section, [])
        if values is None:
            continue
        if not isinstance(values, list):
            issues.append(_error(section, "semantic section must be a list"))
            continue
        for idx, item in enumerate(values):
            _validate_semantic_item(section, idx, item, ontology, evidence_index, issues)
    _find_forbidden_keys(package, "", issues)
    return issues


def assert_valid_semantic_package(package: Mapping[str, Any]) -> list[ValidationIssue]:
    """Validate and raise when the package has blocking errors."""
    issues = validate_semantic_package(package)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        detail = "; ".join(f"{issue.path}: {issue.message}" for issue in errors)
        raise LiteratureSemanticsError(detail)
    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    """Return True when a validation issue list contains blocking errors."""
    return any(issue.severity == "error" for issue in issues)


def _validate_request_context(package: Mapping[str, Any], ontology: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    context = package.get("request_context")
    if not isinstance(context, Mapping):
        issues.append(_error("request_context", "must be a mapping"))
        return
    if context.get("geometry_scope") not in set(ontology.get("geometry_scopes", [])):
        issues.append(_error("request_context.geometry_scope", "unsupported geometry scope"))
    if context.get("operating_regime") not in set(ontology.get("operating_regimes", [])):
        issues.append(_error("request_context.operating_regime", "unsupported operating regime"))
    frequency = context.get("frequency_target_mhz")
    if frequency is not None and not _number(frequency):
        issues.append(_error("request_context.frequency_target_mhz", "frequency must be numeric in MHz"))
    excluded = context.get("exclude", [])
    if excluded and not isinstance(excluded, list):
        issues.append(_error("request_context.exclude", "exclude must be a list"))


def _validate_evidence(package: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    evidence_sources = package.get("evidence_sources")
    if not isinstance(evidence_sources, list) or not evidence_sources:
        issues.append(_error("evidence_sources", "must be a non-empty list"))
        return
    for idx, source in enumerate(evidence_sources):
        path = f"evidence_sources[{idx}]"
        if not isinstance(source, Mapping):
            issues.append(_error(path, "evidence source must be a mapping"))
            continue
        for key in ("id", "source_type"):
            if not source.get(key):
                issues.append(_error(f"{path}.{key}", "missing required evidence source field"))


def _validate_classification(package: Mapping[str, Any], ontology: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    classification = package.get("classification")
    if not isinstance(classification, Mapping):
        issues.append(_error("classification", "must be a mapping"))
        return
    checks = {
        "cavity_family": "cavity_families",
        "cell_count": "cell_counts",
        "beta_class": "beta_classes",
    }
    for key, ontology_key in checks.items():
        if classification.get(key) not in set(ontology.get(ontology_key, [])):
            issues.append(_error(f"classification.{key}", f"unsupported {key}"))
    confidence = classification.get("confidence")
    if not _confidence(confidence):
        issues.append(_error("classification.confidence", "confidence must be a number between 0 and 1"))
    if not _non_empty_list(classification.get("evidence_refs")):
        issues.append(_error("classification.evidence_refs", "classification must cite evidence_refs"))
    else:
        refs = set(_evidence_index(package).keys())
        for ref in classification.get("evidence_refs", []):
            if str(ref) not in refs:
                issues.append(_error("classification.evidence_refs", f"unknown evidence ref {ref!r}"))


def _validate_semantic_item(
    section: str,
    idx: int,
    item: object,
    ontology: Mapping[str, Any],
    evidence_index: Mapping[str, Mapping[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    path = f"{section}[{idx}]"
    if not isinstance(item, Mapping):
        issues.append(_error(path, "semantic item must be a mapping"))
        return
    for key in ("source_refs", "confidence", "scope", "applicability", "human_review_status"):
        if key not in item:
            issues.append(_error(f"{path}.{key}", "missing required semantic rule field"))
    if "source_refs" in item and not _non_empty_list(item.get("source_refs")):
        issues.append(_error(f"{path}.source_refs", "must be a non-empty list"))
    elif "source_refs" in item:
        for ref in item.get("source_refs", []):
            if str(ref) not in evidence_index:
                issues.append(_error(f"{path}.source_refs", f"unknown evidence ref {ref!r}"))
    if "confidence" in item and not _confidence(item.get("confidence")):
        issues.append(_error(f"{path}.confidence", "must be a number between 0 and 1"))
    status = item.get("human_review_status")
    if status is not None and status not in REVIEW_STATUSES:
        issues.append(_error(f"{path}.human_review_status", f"unsupported review status {status!r}"))
    if "applicability" in item and item.get("applicability") in (None, "", {}):
        issues.append(_error(f"{path}.applicability", "must describe where this rule applies"))
    _validate_ontology_names(section, idx, item, ontology, issues)
    _validate_numeric_evidence_policy(section, idx, item, evidence_index, issues)
    _validate_out_of_scope(section, idx, item, ontology, issues)


def _validate_ontology_names(
    section: str,
    idx: int,
    item: Mapping[str, Any],
    ontology: Mapping[str, Any],
    issues: list[ValidationIssue],
) -> None:
    path = f"{section}[{idx}]"
    if section == "curve_priors":
        region = item.get("curve_region")
        if region and region not in set(ontology.get("curve_regions", [])):
            issues.append(_warning(f"{path}.curve_region", "unsupported curve region will be audit-only"))
        for key in ("allowed_curve_types", "preferred_forms", "forbidden_forms"):
            values = item.get(key, [])
            if values and not set(values).issubset(set(ontology.get("curve_types", []))):
                issues.append(_warning(f"{path}.{key}", "unsupported curve type will be audit-only"))
    if section == "parameter_ranges":
        name = str(item.get("parameter_name", ""))
        aliases = set((ontology.get("parameter_aliases") or {}).keys()) | set((ontology.get("parameter_aliases") or {}).values())
        if name and name not in aliases:
            issues.append(_warning(f"{path}.parameter_name", "unsupported parameter will be audit-only"))
    if section == "optimization_objectives":
        name = item.get("objective_name") or item.get("name")
        if name and name not in set(ontology.get("objectives", [])):
            issues.append(_warning(f"{path}.objective_name", "unsupported objective will be audit-only"))


def _validate_numeric_evidence_policy(
    section: str,
    idx: int,
    item: Mapping[str, Any],
    evidence_index: Mapping[str, Mapping[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    if section != "parameter_ranges":
        return
    path = f"{section}[{idx}]"
    refs = [str(ref) for ref in item.get("source_refs", [])]
    evidence_modes = {_evidence_mode(ref, evidence_index) for ref in refs}
    evidence_modes.discard("")
    if evidence_modes == {"image"} and item.get("range_type") == "hard":
        issues.append(_error(f"{path}.range_type", "image-only numeric ranges cannot be hard rules"))
    if len({_paper_id(ref, evidence_index) for ref in refs if _paper_id(ref, evidence_index)}) <= 1 and item.get("range_type") == "hard":
        issues.append(_warning(f"{path}.range_type", "single-source numeric ranges are downgraded to soft"))


def _validate_out_of_scope(
    section: str,
    idx: int,
    item: Mapping[str, Any],
    ontology: Mapping[str, Any],
    issues: list[ValidationIssue],
) -> None:
    text = " ".join(str(value) for value in item.values())
    for term in ontology.get("out_of_scope_terms", []):
        if term.lower() in text.lower():
            issues.append(_warning(f"{section}[{idx}]", f"{term} is out of scope for this MVP and will be audit-only"))


def _find_forbidden_keys(value: object, path: str, issues: list[ValidationIssue]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_EXECUTABLE_KEYS:
                issues.append(_error(child_path, "natural language semantics must not contain executable geometry/CST fields"))
            _find_forbidden_keys(child, child_path, issues)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _find_forbidden_keys(child, f"{path}[{idx}]", issues)


def _evidence_index(package: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for item in package.get("evidence_sources", []) or []:
        if isinstance(item, Mapping) and item.get("id"):
            enriched = dict(item)
            enriched.setdefault("evidence_mode", "source")
            index[str(item["id"])] = enriched
    for section, mode in (("text_evidence", "text"), ("image_evidence", "image")):
        for item in package.get(section, []) or []:
            if isinstance(item, Mapping) and item.get("id"):
                enriched = dict(item)
                enriched.setdefault("evidence_mode", mode)
                index[str(item["id"])] = enriched
    return index


def _evidence_mode(ref: str, evidence_index: Mapping[str, Mapping[str, Any]]) -> str:
    item = evidence_index.get(ref, {})
    return str(item.get("evidence_mode", ""))


def _paper_id(ref: str, evidence_index: Mapping[str, Mapping[str, Any]]) -> str:
    item = evidence_index.get(ref, {})
    return str(item.get("paper_id") or item.get("source_id") or "")


def _confidence(value: object) -> bool:
    return _number(value) and 0.0 <= float(value) <= 1.0


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _non_empty_list(value: object) -> bool:
    return isinstance(value, list) and bool(value)


def _error(path: str, message: str) -> ValidationIssue:
    return ValidationIssue("error", path, message)


def _warning(path: str, message: str) -> ValidationIssue:
    return ValidationIssue("warning", path, message)
