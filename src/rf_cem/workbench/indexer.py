"""Source adapters and deterministic rebuild orchestration for Workbench W0."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from rf_cem.family_profile import validate_profile_mapping
from rf_cem.literature_semantics.validator import assert_valid_semantic_package
from rf_cem.parametric_geometry.expert_prior import (
    DEFAULT_PRIOR_PATH,
    load_expert_prior,
)

from .registry import (
    BuildSummary,
    EntityRecord,
    RelationRecord,
    SourceRecord,
    WorkbenchRegistryError,
    canonical_json,
    file_sha256,
    write_registry,
)


REQUIRED_W0_INSTANCES = {"sls2.r149.6593e02e", "rf500.2c27faee.b1r3"}


class WorkbenchIndexError(WorkbenchRegistryError):
    """Raised when a canonical W0 source cannot be indexed faithfully."""


@dataclass(frozen=True)
class WorkbenchSourceSet:
    """Explicit source set used for one reproducible W0 registry rebuild."""

    repo_root: Path
    family_profile: Path
    family_profile_validation: Path | None = None
    architecture_document: Path | None = None
    literature_packages: tuple[Path, ...] = ()
    review_sessions: tuple[Path, ...] = ()


_REPRESENTATION_CATALOG = (
    {
        "id": "legacy.line",
        "label": "Line",
        "status": "implemented_legacy",
        "implementation": "rf_cem.parametric_geometry.grammar.cavity_grammar_v0._line",
        "scope": "RF500 profile segments",
    },
    {
        "id": "legacy.circular_arc",
        "label": "Circular arc",
        "status": "implemented_legacy",
        "implementation": "rf_cem.parametric_geometry.grammar.cavity_grammar_v0._arc_from_angles",
        "scope": "RF500 nose/blend evidence arcs",
    },
    {
        "id": "legacy.nurbs_spline",
        "label": "NURBS / spline approximation",
        "status": "implemented_legacy",
        "implementation": "rf_cem.parametric_geometry.grammar.cavity_grammar_v0._nurbs",
        "scope": "RF500 smooth nose/equator and SLS-2 splineApprox export",
    },
    {
        "id": "legacy.analytic_ellipse_samples",
        "label": "Analytic ellipse-arc samples",
        "status": "implemented_source_with_approximate_kernel_export",
        "implementation": "rf_cem.literature_semantics.geometry_candidate._sample_quarter_ellipse",
        "scope": "SLS-2 four-quarter-ellipse source model",
    },
    {
        "id": "r2.composite_region_representation",
        "label": "Composite region representation",
        "status": "planned_r2",
        "implementation": None,
        "scope": "not implemented in R0B",
    },
)

_ALGORITHM_CATALOG = (
    {
        "id": "family_profile.source_native_roundtrip.v0",
        "label": "Family-profile source-native round trip",
        "status": "established_no_cst",
        "implementation": "rf_cem.family_profile",
    },
    {
        "id": "rf500.cavity_grammar.v0",
        "label": "RF500 cavity grammar v0",
        "status": "implemented_legacy",
        "implementation": "rf_cem.parametric_geometry.grammar.cavity_grammar_v0",
    },
    {
        "id": "rf500.segment_fit_ladder.v0",
        "label": "RF500 segment fitting ladder",
        "status": "implemented_legacy",
        "implementation": "rf_cem.parametric_geometry.grammar.segment_fit",
    },
    {
        "id": "rf500.continuity_check.v0",
        "label": "RF500 profile continuity check",
        "status": "implemented_legacy",
        "implementation": "rf_cem.parametric_geometry.grammar.continuity.check_profile_continuity",
    },
    {
        "id": "sls2.four_quarter_ellipses.v0",
        "label": "SLS-2 symmetric four-quarter-ellipse generator",
        "status": "established_no_cst",
        "implementation": "rf_cem.literature_semantics.geometry_candidate",
    },
    {
        "id": "workbench.legacy_compile_adapter.v0",
        "label": "Legacy compile-record adapter",
        "status": "implemented_w0_placeholder",
        "implementation": "rf_cem.workbench.indexer",
    },
)

_ROADMAP_PHASES = (
    (
        "R0B",
        "Architecture Re-baseline + Workbench W0",
        "hard_gate_passed_pending_canonical_merge",
    ),
    ("R1", "RF Boundary Semantic Core", "planned"),
    ("R2", "Boundary Representation Core + Compiler v0", "planned"),
    ("R3", "Family Induction / Extension v0", "planned"),
    ("R4", "Observation & Engineering Constraint Contract", "planned"),
    ("R5", "RF Result / Mode / Field Contract", "planned_requires_live_cst_authorization"),
)

_R0B_GATES = (
    ("stage_c_canonical_owner", "Stage C integrated into canonical owner", "passed", "PR #4 merge commit 3867a9a8eae502359556a83bcad15b3a519e64de"),
    ("semantic_dependency_boundary", "semantic is independent of representation, geometry kernels, and CST", "implemented", "architecture dependency tests"),
    ("representation_dependency_boundary", "representation is independent of semantic families and CST", "implemented", "architecture dependency tests"),
    ("compiler_dependency_boundary", "compiler is the semantic/representation composition boundary", "implemented", "package boundary and dependency tests"),
    ("observation_read_only_boundary", "observation does not generate geometry", "implemented", "package boundary and dependency tests"),
    ("deterministic_rebuild", "SQLite registry is deletable and deterministically rebuildable", "implemented", "registry snapshot rebuild test"),
    ("w0_views", "W0 exposes catalog, validation, coverage, compile placeholders, and roadmap", "implemented", "fixed-route server tests"),
    ("two_real_instances", "SLS-2 and RF500 are indexed without source confusion", "evaluated_at_rebuild", "family_profile.v0 adapter"),
    ("source_hash_status", "source changes are reported stale or missing", "implemented", "source re-hash test"),
    ("server_safety", "loopback read-only server exposes no shell, CST, or file browser", "implemented", "Host/Origin/token and fixed-route tests"),
    (
        "no_cst_regression",
        "targeted and full no-CST suites pass",
        "passed",
        "52 targeted passed; 738 passed and 11 skipped in full no-CST suite",
    ),
    (
        "documentation_closeout",
        "canonical Markdown and source inventory are complete",
        "passed",
        "canonical roadmap/goal paths and maintained-document inventory verified",
    ),
)

_CAPABILITY_CATALOG = (
    ("source.family_profile.v0", "Source-lossless family profile", "established", "Stage C"),
    ("source.literature_semantics.v0", "Literature semantics and evidence", "established", "literature review workflow"),
    ("source.helper2_review", "Helper2 geometry/Feature/UDSG review", "established_partial", "frozen SLS-2 overlay"),
    ("architecture.semantic", "Representation-independent semantic layer", "boundary_established_r0b", "R1 implementation planned"),
    ("architecture.representation", "Family-independent representation layer", "boundary_established_r0b", "R2 implementation planned"),
    ("architecture.compiler", "Generic boundary compiler", "boundary_only_r0b", "R2 implementation planned"),
    ("architecture.observation", "Representation-independent observation", "boundary_only_r0b", "R4 implementation planned"),
    ("workbench.w0", "Derived local project catalog", "implemented_r0b", "SQLite + loopback read-only server"),
    ("physics.rf_result_contract", "Mode-identified RF result/field contract", "planned_r5", "live CST requires explicit authorization"),
)

_VALIDATION_CATALOG = (
    (
        "tests.family_profile",
        "Stage C family-profile contracts",
        "available_no_cst",
        "tests/test_rf_cem_family_profile.py",
    ),
    (
        "tests.architecture_boundaries",
        "R0B architecture dependency guards",
        "available_no_cst",
        "tests/test_rf_cem_architecture_boundaries.py",
    ),
    (
        "tests.workbench_w0",
        "Workbench W0 rebuild/server contracts",
        "available_no_cst",
        "tests/test_rf_cem_workbench.py",
    ),
    (
        "tests.literature_review",
        "Literature semantics and review GUI contracts",
        "available_no_cst",
        "tests/test_rf_cem_literature_*.py",
    ),
    (
        "tests.geometry",
        "RF-CEM geometry and optimisation contracts",
        "available_no_cst",
        "tests/test_rf_cem_parametric_*.py",
    ),
)


def rebuild_workbench(database: Path, source_set: WorkbenchSourceSet) -> BuildSummary:
    """Validate explicit sources and atomically rebuild the W0 read model."""
    root = source_set.repo_root.resolve()
    if not root.is_dir():
        raise WorkbenchIndexError(f"repository root is missing: {root}")

    source_rows: list[SourceRecord] = []
    entity_rows: list[EntityRecord] = []
    relation_rows: list[RelationRecord] = []
    entity_keys: set[tuple[str, str]] = set()
    relation_keys: set[tuple[str, str, str, str, str]] = set()

    def add_entity(row: EntityRecord) -> None:
        key = (row.entity_kind, row.entity_id)
        if key in entity_keys:
            raise WorkbenchIndexError(f"duplicate indexed entity: {key}")
        entity_keys.add(key)
        entity_rows.append(row)

    def add_relation(row: RelationRecord) -> None:
        key = (
            row.relation_kind,
            row.from_kind,
            row.from_id,
            row.to_kind,
            row.to_id,
        )
        if key in relation_keys:
            raise WorkbenchIndexError(f"duplicate indexed relation: {key}")
        relation_keys.add(key)
        relation_rows.append(row)

    catalog_source = _register_source(Path(__file__), "workbench_catalog", root)
    source_rows.append(catalog_source)
    roadmap_source_id = catalog_source.source_id
    if source_set.architecture_document is not None:
        architecture_source = _register_source(
            source_set.architecture_document, "architecture_document", root
        )
        source_rows.append(architecture_source)
        roadmap_source_id = architecture_source.source_id

    _index_catalog(add_entity, catalog_source.source_id, roadmap_source_id)

    prior_source = _register_source(DEFAULT_PRIOR_PATH, "expert_prior.v0", root)
    source_rows.append(prior_source)
    prior, prior_metadata = load_expert_prior()
    _index_expert_prior(prior, prior_metadata, prior_source.source_id, add_entity)

    profile_source = _register_source(
        source_set.family_profile, "family_profile.v0", root
    )
    source_rows.append(profile_source)
    profile = _read_json_mapping(source_set.family_profile)
    validate_profile_mapping(profile)
    indexed_instances = _index_family_profile(
        profile,
        source_id=profile_source.source_id,
        add_entity=add_entity,
        add_relation=add_relation,
    )

    if source_set.family_profile_validation is not None:
        validation_source = _register_source(
            source_set.family_profile_validation,
            "family_profile_validation.v0",
            root,
        )
        source_rows.append(validation_source)
        validation = _read_json_mapping(source_set.family_profile_validation)
        validation_id = f"family-profile-report:{validation_source.raw_sha256[:16]}"
        add_entity(
            EntityRecord(
                "validation",
                validation_id,
                "Family profile validation report",
                _mapping_status(validation),
                validation_source.source_id,
                validation,
            )
        )
        add_relation(
            RelationRecord(
                "family_has_validation",
                "family",
                str(profile["family_id"]),
                "validation",
                validation_id,
            )
        )

    for package_path in sorted(source_set.literature_packages, key=str):
        semantic_source = _register_source(
            package_path, "literature_semantics.v0", root
        )
        source_rows.append(semantic_source)
        _index_literature_package(
            _read_json_mapping(package_path),
            semantic_source.source_id,
            add_entity,
        )

    for session_path in sorted(source_set.review_sessions, key=str):
        review_source = _register_source(session_path, "review_session.v1", root)
        source_rows.append(review_source)
        _index_review_session(
            _read_json_mapping(session_path),
            review_source.source_id,
            add_entity,
        )

    missing_instances = sorted(REQUIRED_W0_INSTANCES - indexed_instances)
    if missing_instances:
        raise WorkbenchIndexError(
            "W0 family profile is missing required real instances: "
            + ", ".join(missing_instances)
        )
    add_entity(
        EntityRecord(
            "validation",
            "w0.required-real-instances",
            "W0 required real instances",
            "pass",
            profile_source.source_id,
            {"required_instance_ids": sorted(REQUIRED_W0_INSTANCES)},
        )
    )

    source_ids = [row.source_id for row in source_rows]
    if len(source_ids) != len(set(source_ids)):
        raise WorkbenchIndexError("the same source path/kind was indexed more than once")
    return write_registry(
        database,
        sources=source_rows,
        entities=entity_rows,
        relations=relation_rows,
        metadata={
            "required_w0_instances": canonical_json(sorted(REQUIRED_W0_INSTANCES)),
            "roadmap_phase": "R0B",
        },
    )


def _index_catalog(
    add_entity: Any,
    catalog_source_id: str,
    roadmap_source_id: str,
) -> None:
    for item in _REPRESENTATION_CATALOG:
        add_entity(
            EntityRecord(
                "representation",
                str(item["id"]),
                str(item["label"]),
                str(item["status"]),
                catalog_source_id,
                dict(item),
            )
        )
    for item in _ALGORITHM_CATALOG:
        add_entity(
            EntityRecord(
                "algorithm",
                str(item["id"]),
                str(item["label"]),
                str(item["status"]),
                catalog_source_id,
                dict(item),
            )
        )
    for phase, label, status in _ROADMAP_PHASES:
        add_entity(
            EntityRecord(
                "roadmap_phase",
                phase,
                label,
                status,
                roadmap_source_id,
                {"phase": phase},
            )
        )
    for gate_id, label, status, evidence in _R0B_GATES:
        add_entity(
            EntityRecord(
                "roadmap_gate",
                f"R0B.{gate_id}",
                label,
                status,
                roadmap_source_id,
                {"phase": "R0B", "evidence": evidence},
            )
        )
    for capability_id, label, status, evidence in _CAPABILITY_CATALOG:
        add_entity(
            EntityRecord(
                "capability",
                capability_id,
                label,
                status,
                catalog_source_id,
                {"evidence": evidence},
            )
        )
    for validation_id, label, status, implementation in _VALIDATION_CATALOG:
        add_entity(
            EntityRecord(
                "validation",
                validation_id,
                label,
                status,
                catalog_source_id,
                {"test_path": implementation, "evidence_class": "test_contract"},
            )
        )


def _index_expert_prior(
    prior: Mapping[str, Any],
    prior_metadata: Mapping[str, Any],
    source_id: str,
    add_entity: Any,
) -> None:
    grammar = prior.get("grammar", {})
    variant_policy = (
        grammar.get("variant_policy", {}) if isinstance(grammar, Mapping) else {}
    )
    enabled = (
        variant_policy.get("enabled_variants", [])
        if isinstance(variant_policy, Mapping)
        else []
    )
    selected = (
        str(variant_policy.get("default_selected_variant") or "")
        if isinstance(variant_policy, Mapping)
        else ""
    )
    if not isinstance(enabled, list) or not enabled:
        raise WorkbenchIndexError("expert prior grammar.variant_policy.enabled_variants is empty")
    for variant in enabled:
        variant_name = str(variant)
        add_entity(
            EntityRecord(
                "algorithm",
                f"rf500.grammar_variant.{variant_name}",
                f"Grammar variant: {variant_name}",
                "enabled_selected" if variant_name == selected else "enabled",
                source_id,
                {
                    "algorithm_class": "legacy_grammar_variant",
                    "variant_name": variant_name,
                    "selected_by_default": variant_name == selected,
                    "curve_selection": variant_policy.get("curve_selection", {})
                    if isinstance(variant_policy, Mapping)
                    else {},
                },
            )
        )
    for policy_name in ("fit_policy", "validation", "interface_policy"):
        policy = prior.get(policy_name, {})
        if not isinstance(policy, Mapping):
            raise WorkbenchIndexError(f"expert prior {policy_name} must be an object")
        add_entity(
            EntityRecord(
                "algorithm",
                f"rf500.control_policy.{policy_name}",
                f"RF500 control policy: {policy_name}",
                "implemented_legacy",
                source_id,
                {
                    "algorithm_class": "control_policy",
                    "policy": dict(policy),
                    "source_precedence": prior_metadata.get("precedence", []),
                },
            )
        )


def _index_family_profile(
    profile: Mapping[str, Any],
    *,
    source_id: str,
    add_entity: Any,
    add_relation: Any,
) -> set[str]:
    family_id = str(profile["family_id"])
    add_entity(
        EntityRecord(
            "family",
            family_id,
            family_id,
            str(profile.get("family_assertion_status") or "indexed"),
            source_id,
            {
                "schema_version": profile.get("schema_version"),
                "family_identity": profile.get("family_identity", {}),
                "metric_contract_status": profile.get("metric_contract_status"),
                "scope": profile.get("scope", {}),
            },
        )
    )
    for key, value in sorted(dict(profile.get("family_identity", {})).items()):
        semantic_id = f"family-identity:{key}:{value}"
        add_entity(
            EntityRecord(
                "semantic",
                semantic_id,
                f"{key}: {value}",
                "supported",
                source_id,
                {"semantic_class": "family_identity", "key": key, "value": value},
            )
        )

    instance_ids: set[str] = set()
    for raw_instance in profile.get("instances", []):
        if not isinstance(raw_instance, Mapping):
            raise WorkbenchIndexError("family profile contains a non-object instance")
        instance = dict(raw_instance)
        instance_id = str(instance["instance_id"])
        instance_ids.add(instance_id)
        add_entity(
            EntityRecord(
                "instance",
                instance_id,
                instance_id,
                _instance_status(instance),
                source_id,
                {
                    "family_id": family_id,
                    "native_schema": instance.get("native_schema"),
                    "native_model_type": instance.get("native_model_type"),
                    "native_variant": instance.get("native_variant"),
                    "native_units": instance.get("native_units", {}),
                    "source_binding": instance.get("source_binding", {}),
                    "live_cst": instance.get("live_cst", {}),
                    "physical_acceptance": instance.get("physical_acceptance", {}),
                },
            )
        )
        add_relation(
            RelationRecord(
                "family_has_instance", "family", family_id, "instance", instance_id
            )
        )
        for layer, layer_value in sorted(
            dict(instance.get("validation_layers", {})).items()
        ):
            if not isinstance(layer_value, Mapping):
                raise WorkbenchIndexError(
                    f"instance validation layer is not an object: {instance_id}.{layer}"
                )
            validation_id = f"{instance_id}:{layer}"
            add_entity(
                EntityRecord(
                    "validation",
                    validation_id,
                    f"{instance_id} / {layer}",
                    str(layer_value.get("status") or "unknown"),
                    source_id,
                    dict(layer_value),
                )
            )
            add_relation(
                RelationRecord(
                    "instance_has_validation",
                    "instance",
                    instance_id,
                    "validation",
                    validation_id,
                )
            )
        compile_id = f"legacy:{instance_id}"
        add_entity(
            EntityRecord(
                "compile_record",
                compile_id,
                f"Legacy geometry source for {instance_id}",
                "legacy_adapter_placeholder",
                source_id,
                {
                    "schema_version": "compile_record.placeholder.r0b",
                    "instance_id": instance_id,
                    "geometry_artifacts": instance.get("geometry_artifacts", []),
                    "limitation": (
                        "This is a W0 legacy source view, not compile_record.v0 and "
                        "not evidence of generic compiler execution."
                    ),
                },
            )
        )
        add_relation(
            RelationRecord(
                "instance_has_compile_record",
                "instance",
                instance_id,
                "compile_record",
                compile_id,
            )
        )
    return instance_ids


def _index_literature_package(
    package: Mapping[str, Any],
    source_id: str,
    add_entity: Any,
) -> None:
    assert_valid_semantic_package(package)
    context = package.get("request_context", {})
    evidence_sources = package.get("evidence_sources", [])
    source_paper_id = ""
    if isinstance(evidence_sources, list) and evidence_sources:
        first_source = evidence_sources[0]
        if isinstance(first_source, Mapping):
            source_paper_id = str(first_source.get("id") or "")
    paper_id = str(
        context.get("paper_id")
        or context.get("design_id")
        or source_paper_id
        or source_id.rsplit(":", 1)[-1]
    )
    classification = package.get("classification", {})
    add_entity(
        EntityRecord(
            "semantic",
            f"literature:{paper_id}:classification",
            f"{paper_id} classification",
            str(classification.get("human_review_status") or "source_claim"),
            source_id,
            {"section": "classification", "value": classification},
        )
    )
    for section in (
        "named_features",
        "shape_motifs",
        "curve_priors",
        "parameter_ranges",
        "optimization_objectives",
        "physical_constraints",
    ):
        values = package.get(section, []) or []
        if not isinstance(values, list):
            raise WorkbenchIndexError(f"literature section must be a list: {section}")
        for index, item in enumerate(values, start=1):
            if not isinstance(item, Mapping):
                raise WorkbenchIndexError(
                    f"literature item must be an object: {section}[{index - 1}]"
                )
            native_id = str(item.get("id") or f"item-{index}")
            label = _semantic_label(item, native_id)
            add_entity(
                EntityRecord(
                    "semantic",
                    f"literature:{paper_id}:{section}:{native_id}",
                    label,
                    str(item.get("human_review_status") or "pending"),
                    source_id,
                    {"paper_id": paper_id, "section": section, "item": dict(item)},
                )
            )


def _index_review_session(
    session: Mapping[str, Any],
    source_id: str,
    add_entity: Any,
) -> None:
    if session.get("schema_version") != "review_session.v1":
        raise WorkbenchIndexError("review session schema_version must be review_session.v1")
    scope = session.get("review_scope", {})
    paper_id = str(scope.get("paper_id") or "unknown-paper")
    decisions = session.get("review_decisions", {})
    if not isinstance(decisions, Mapping):
        raise WorkbenchIndexError("review_decisions must be an object")
    for item_id, decision in sorted(decisions.items()):
        if not isinstance(decision, Mapping):
            raise WorkbenchIndexError(f"review decision is not an object: {item_id}")
        add_entity(
            EntityRecord(
                "review",
                f"{paper_id}:{item_id}",
                str(item_id),
                str(decision.get("status") or "pending"),
                source_id,
                {
                    "paper_id": paper_id,
                    "revision": decision.get("revision"),
                    "review_note": decision.get("review_note", ""),
                },
            )
        )
    helper2 = session.get("helper2_reviews", {})
    if not isinstance(helper2, Mapping):
        raise WorkbenchIndexError("helper2_reviews must be an object")
    for projection_id, envelope in sorted(helper2.items()):
        if not isinstance(envelope, Mapping) or not isinstance(
            envelope.get("review"), Mapping
        ):
            raise WorkbenchIndexError(
                f"Helper2 review envelope is invalid: {projection_id}"
            )
        review = dict(envelope["review"])
        candidates = review.get("candidates", {})
        if not isinstance(candidates, Mapping):
            raise WorkbenchIndexError("Helper2 candidates must be an object")
        for candidate_id, candidate in sorted(candidates.items()):
            if not isinstance(candidate, Mapping):
                raise WorkbenchIndexError(
                    f"Helper2 candidate is not an object: {candidate_id}"
                )
            add_entity(
                EntityRecord(
                    "semantic",
                    f"helper2:{projection_id}:{candidate_id}",
                    str(candidate.get("type") or candidate_id),
                    str(candidate.get("status") or "requires_review"),
                    source_id,
                    {
                        "semantic_class": "helper2_feature_candidate",
                        "paper_id": paper_id,
                        "projection_id": projection_id,
                        "candidate": dict(candidate),
                    },
                )
            )
        geometry = review.get("geometry", {})
        bindings = review.get("bindings", {})
        add_entity(
            EntityRecord(
                "validation",
                f"helper2:{projection_id}",
                f"Helper2 review / {projection_id}",
                "partial_review_overlay",
                source_id,
                {
                    "paper_id": paper_id,
                    "projection_id": projection_id,
                    "geometry_review_count": len(geometry)
                    if isinstance(geometry, Mapping)
                    else 0,
                    "candidate_review_count": len(candidates),
                    "binding_review_count": len(bindings)
                    if isinstance(bindings, Mapping)
                    else 0,
                    "revision": envelope.get("revision"),
                },
            )
        )


def _register_source(
    path: Path,
    source_kind: str,
    root: Path,
    expected_raw_sha256: str | None = None,
) -> SourceRecord:
    resolved = path.resolve()
    if not resolved.is_file():
        raise WorkbenchIndexError(f"Workbench source is missing: {path}")
    try:
        display_path = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise WorkbenchIndexError(
            f"Workbench source must be inside the declared repository root: {path}"
        ) from exc
    raw_sha = file_sha256(resolved)
    expected = (
        str(expected_raw_sha256).lower().removeprefix("sha256:")
        if expected_raw_sha256 is not None
        else None
    )
    if expected is not None and expected != raw_sha:
        raise WorkbenchIndexError(
            f"source raw SHA-256 mismatch for {display_path}: expected {expected}, got {raw_sha}"
        )
    source_id = f"{source_kind}:{hashlib.sha256(display_path.encode('utf-8')).hexdigest()[:16]}"
    return SourceRecord(
        source_id=source_id,
        source_kind=source_kind,
        display_path=display_path,
        raw_sha256=raw_sha,
        size_bytes=resolved.stat().st_size,
        expected_raw_sha256=expected,
        payload={"path_policy": "repository_relative"},
    )


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkbenchIndexError(f"cannot read UTF-8 JSON source: {path}") from exc
    if not isinstance(value, dict):
        raise WorkbenchIndexError(f"Workbench JSON source must contain an object: {path}")
    return value


def _instance_status(instance: Mapping[str, Any]) -> str:
    physical = instance.get("physical_acceptance", {})
    live = instance.get("live_cst", {})
    if isinstance(physical, Mapping) and physical.get("status") not in {
        None,
        "not_established",
    }:
        return "physical_evidence_present"
    if isinstance(live, Mapping) and live.get("status") not in {
        None,
        "not_run",
        "not_linked",
    }:
        return "live_cst_linked"
    return "established_no_cst_source_instance"


def _mapping_status(value: Mapping[str, Any]) -> str:
    for key in ("status", "overall_status", "validation_status"):
        if value.get(key) is not None:
            return str(value[key])
    if value.get("roundtrip_all_passed") is True:
        return "pass"
    if value.get("roundtrip_all_passed") is False:
        return "incomplete"
    return "indexed"


def _semantic_label(item: Mapping[str, Any], fallback: str) -> str:
    for key in (
        "name",
        "subject",
        "feature_type",
        "motif_type",
        "parameter",
        "objective",
        "constraint",
        "id",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


__all__ = [
    "REQUIRED_W0_INSTANCES",
    "WorkbenchIndexError",
    "WorkbenchSourceSet",
    "rebuild_workbench",
]
