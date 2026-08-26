"""Source adapters and deterministic rebuild orchestration for Workbench W0-W4."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from rf_cem.compiler import CompileRecord, ContractSourceRef, load_compile_record
from rf_cem.family_profile import (
    canonical_sha256 as family_profile_sha256,
    validate_profile_mapping,
)
from rf_cem.literature_semantics.validator import assert_valid_semantic_package
from rf_cem.observation import R4Bundle, load_r4_bundle
from rf_cem.parametric_geometry.expert_prior import (
    DEFAULT_PRIOR_PATH,
    load_expert_prior,
)
from rf_cem.semantic.contracts import (
    FamilyGrammar,
    InstanceBoundaryGraph,
    InstanceGraphDiff,
    SemanticContractError,
    canonical_sha256 as semantic_sha256,
    diff_instance_graphs,
    load_family_grammar,
    load_instance_boundary_graph,
    load_instance_graph_diff,
    validate_graph_against_grammar,
    validate_reviewed_graph_intrinsic,
)
from rf_cem.semantic.induction import (
    ALIGNMENT_FILE,
    BLIND_GRAPH_FILE,
    BLIND_VALIDATION_FILE,
    MANIFEST_FILE as R3_MANIFEST_FILE,
    MANIFEST_FILE_V1 as R3_MANIFEST_FILE_V1,
    PATCHED_GRAMMAR_FILE,
    PATCH_APPLICATION_FILE,
    PATCH_FILE,
    PROPOSAL_FILE,
    PROPOSAL_FILE_V1,
    REVIEW_FILE,
    R3Bundle,
    SEED_GRAMMAR_FILE,
    load_r3_bundle,
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


SLS2_INSTANCE_ID = "sls2.r149.6593e02e"
RF500_INSTANCE_ID = "rf500.2c27faee.b1r3"
REQUIRED_W0_INSTANCES = {SLS2_INSTANCE_ID, RF500_INSTANCE_ID}

# The original canonical R3 proof pinned the then-current representation module
# as a build sentinel.  That source file is intentionally expected to evolve as
# versioned representation contracts are added.  Keep this one reviewed legacy
# identity readable without treating the historical code hash as a live W0-W4
# source; the immutable v0 manifest still preserves the exact old identity.
_LEGACY_R3_REPRESENTATION_SENTINELS = {
    (
        "r3_family_induction.2f6c02557798e606",
        "02745cdbe657584eb0f892085bf8d6d1f8ba7ed4d41c71fd66404a94f5dfdceb",
        39690,
    )
}


class WorkbenchIndexError(WorkbenchRegistryError):
    """Raised when a canonical W0 source cannot be indexed faithfully."""


@dataclass(frozen=True)
class WorkbenchSourceSet:
    """Explicit source set used for one reproducible W0-W4 registry rebuild."""

    repo_root: Path
    family_profile: Path
    family_profile_validation: Path | None = None
    architecture_document: Path | None = None
    literature_packages: tuple[Path, ...] = ()
    review_sessions: tuple[Path, ...] = ()
    family_grammar: Path | None = None
    instance_boundary_graphs: tuple[Path, ...] = ()
    instance_graph_diff: Path | None = None
    compile_records: tuple[Path, ...] = ()
    family_induction_bundle: Path | None = None
    observation_contract_bundle: Path | None = None


_REPRESENTATION_CATALOG = (
    {
        "id": "r2.LineRepresentation",
        "label": "LineRepresentation",
        "status": "implemented_r2_generic",
        "implementation": "rf_cem.representation.LineRepresentation",
        "scope": "family-independent boundary primitive",
    },
    {
        "id": "r2.CircularArcRepresentation",
        "label": "CircularArcRepresentation",
        "status": "implemented_r2_generic",
        "implementation": "rf_cem.representation.CircularArcRepresentation",
        "scope": "family-independent boundary primitive",
    },
    {
        "id": "r2.EllipseArcRepresentation",
        "label": "EllipseArcRepresentation",
        "status": "implemented_r2_generic",
        "implementation": "rf_cem.representation.EllipseArcRepresentation",
        "scope": "family-independent boundary primitive",
    },
    {
        "id": "r2.SplineApproxRepresentation",
        "label": "SplineApproxRepresentation",
        "status": "implemented_r2_generic",
        "implementation": "rf_cem.representation.SplineApproxRepresentation",
        "scope": "family-independent spline approximation boundary primitive",
        "fidelity": "Approximate",
        "backend": "CadQuery/OCCT splineApprox",
        "tolerance": "0.001 mm (1 micrometre)",
        "optimization_ready": True,
        "exact_nurbs": False,
    },
    {
        "id": "compat.SplineNurbsRepresentation",
        "label": "SplineNurbsRepresentation (v0 compatibility)",
        "status": "deprecated_compatibility_loader",
        "implementation": "rf_cem.representation.SplineNurbsRepresentation",
        "scope": "historical boundary_representation.v0 payloads only",
        "fidelity": "Approximate",
        "exact_nurbs": False,
    },
    {
        "id": "future.ExactNurbsRepresentation",
        "label": "ExactNurbsRepresentation",
        "status": "planned_not_implemented",
        "implementation": "none",
        "scope": "future exact poles/knots/weights/multiplicity/parameter-domain contract",
    },
    {
        "id": "r2.CompositeRegionRepresentation",
        "label": "CompositeRegionRepresentation",
        "status": "implemented_r2_generic",
        "implementation": "rf_cem.representation.CompositeRegionRepresentation",
        "scope": "ordered 1..N primitive representations owned by one opaque region",
    },
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
    {
        "id": "rf_cem_profile_compiler.v0",
        "label": "Generic topology/representation profile compiler",
        "status": "implemented_r2_no_cst",
        "implementation": "rf_cem.compiler.ProfileCompiler.compile",
    },
    {
        "id": "rf_cem_family_induction.v0",
        "label": "Reviewed semantic-graph family induction",
        "status": "implemented_r3_no_cst",
        "implementation": "rf_cem.semantic.induction",
    },
    {
        "id": "rf_cem.semantic_arc_observer.v0",
        "label": "Representation-independent semantic arc observer",
        "status": "implemented_r4_no_cst",
        "implementation": "rf_cem.observation.observe_compiled_geometry",
    },
    {
        "id": "rf_cem.axisymmetric_shape_descriptors.v0",
        "label": "Versioned axisymmetric engineering descriptors",
        "status": "implemented_r4_no_cst",
        "implementation": "rf_cem.observation.extract_scalar_descriptors",
    },
    {
        "id": "rf_cem.engineering_constraint_evaluator.v0",
        "label": "Unit-aware non-mutating constraint evaluator",
        "status": "implemented_r4_no_cst",
        "implementation": "rf_cem.observation.evaluate_constraint",
    },
)

_ROADMAP_PHASES = (
    (
        "R0B",
        "Architecture Re-baseline + Workbench W0",
        "hard_gate_passed_merged",
    ),
    ("R1", "RF Boundary Semantic Core", "hard_gate_passed_merged"),
    (
        "R2",
        "Boundary Representation Core + Compiler v1 (v0 compatible)",
        "hard_gate_passed_merged",
    ),
    (
        "R3",
        "Family Induction / Extension v1 (v0 compatible)",
        "hard_gate_passed_merged",
    ),
    (
        "R4",
        "Observation & Engineering Constraint Contract",
        "hard_gate_passed_merged",
    ),
    ("R5", "RF Result / Mode / Field Contract", "paused_or_deferred_by_user"),
)

_R1_GATES = (
    ("two_valid_graphs", "Both real instance boundary graphs validate", "passed", "family_grammar.v0 validation"),
    ("nose_absent_sls2", "SLS-2 has no nose node with reviewed-topology absence evidence", "passed", "sls2.r149.6593e02e boundary graph"),
    ("nose_present_rf500", "RF500 has an evidence-bound paired nose motif", "passed", "rf500.2c27faee.b1r3 boundary graph"),
    ("semantic_graph_diff", "Graph diff reports semantic/topology change rather than missing parameters", "passed", "instance_boundary_graph_diff.v0"),
    ("one_family_grammar", "One family grammar accepts both topologies", "passed", "family_grammar.v0"),
    ("invalid_topology_fail_closed", "Invalid adjacency, cardinality, and interfaces fail closed", "passed", "tests/test_rf_cem_semantic_core.py"),
    ("region_identity_evidence_review", "Every region has stable identity, evidence, and terminal review", "passed", "instance graph contract validation"),
    ("w1_views", "W1 exposes grammar, graphs, nose state, motif, and graph diff", "implemented", "fixed /semantic-graphs route"),
    ("no_common_parameter_vector", "No common geometry parameter vector is introduced", "passed", "semantic topology parameter contract"),
    ("no_cst_regression", "Targeted and full no-CST regression suites pass", "passed", "19 targeted passed; 745 passed and 11 skipped in the full default suite"),
    ("phase_closeout", "One R1 closeout commit/push and canonical merge", "passed", "PR #6 merge commit 5ae1ba07b841d6adf6e180ec1eedfd073657987b"),
)

_R2_GATES = (
    ("generic_representation_contract", "Line, circular arc, ellipse arc, SplineApprox, and composite contracts are generic", "passed", "SplineApproxRepresentation / boundary_representation.v1 with v0 compatibility"),
    ("one_compiler_entry", "One ProfileCompiler entry compiles both canonical topologies", "passed", "compile_record.v1 pair in r2_boundary_compiler.2980548dcdd5a85e"),
    ("region_patch_ownership", "Every semantic region owns 1..N patches and every patch has exactly one region owner", "passed", "RegionGeometry and GeometryPatch fail-closed contracts"),
    ("landmark_and_continuity", "Landmark bindings and required C0/G1/G2 diagnostics are explicit", "passed", "boundary_continuity_policy.v0 + compile_record.v1 continuity checks"),
    ("brep_step_valid", "Both profiles close into valid no-CST BRep/STEP outputs", "passed", "isolated CadQuery worker validation"),
    ("baseline_comparison", "Accepted source-native/baseline comparisons pass declared tolerances", "passed", "r2_boundary_compiler.2980548dcdd5a85e baseline comparison"),
    ("source_native_provenance", "Stage C source-native payload and artifact bindings survive compilation", "passed", "hash-bound compile inputs"),
    ("deterministic_bundle", "Fresh R2 proof builds are byte-identical", "passed", "r2_boundary_compiler.2980548dcdd5a85e reproducibility test"),
    ("w2_views", "W2 exposes compile, ownership, landmark, continuity, baseline, warning, and artifact traces", "implemented", "fixed /compile-records route"),
    ("no_cst_regression", "Targeted and full branch-local no-CST suites pass", "passed", "PR #10 TD1/TD2 compiler and Workbench no-CST closeout"),
    ("no_live_cst", "R2 has no live-CST or physical-acceptance claim", "passed", "live_cst_status=not_run"),
    ("phase_closeout", "One R2 closeout commit/push and canonical merge", "passed", "PR #7 merge commit e81ad20942258380cccb93d17cfdf0ca7e2d0e21"),
)

_R3_GATES = (
    ("semantic_only_alignment", "Alignment reads reviewed semantic side/type tokens, never common parameter names", "passed", "graph_alignment.v0"),
    ("common_backbone", "SLS-2 and RF500 yield one explicit common semantic backbone", "passed", "common_backbone slots"),
    ("optional_nose_proposal", "The paired nose contrast yields an evidence-bound optional motif proposal", "passed", "family_extension_proposal.v1 structured support in r3_family_induction_ablation.59db0a7b5f8e158c"),
    ("alternative_topology_proposal", "Paired, single, and fallback detectors yield explicit explainable proposals", "passed", "FamilyInductionEngine detector strategy and fixtures"),
    ("no_automatic_mutation", "A pending proposal cannot mutate the family grammar", "passed", "proposal/review separation"),
    ("explicit_review_patch", "Only an accepted manual review authorizes a hash-bound grammar patch", "passed", "accepted review + add_optional_motif patch"),
    ("withheld_review_nonmutation", "Rejected and needs-evidence reviews preserve the exact original grammar", "passed", "parameterized nonmutation test"),
    ("existing_instances_revalidate", "Both induction instances revalidate after the explicit patch", "passed", "family_grammar_patch_application.v0"),
    ("held_out_real_instance", "Real LEReC 704 MHz is classified only after induction as a held-out instance", "passed", "family_induction_blind_validation.v0"),
    ("representation_unchanged", "R3 neither imports nor modifies the R2 representation contract", "passed", "representation-core hash sentinel"),
    ("deterministic_bundle", "Fresh R3 proof builds are byte-identical and tampering fails closed", "passed", "r3_family_induction_ablation.59db0a7b5f8e158c validation"),
    ("w3_views", "W3 exposes alignment, backbone, proposal, review, grammar diff, and blind validation", "implemented", "fixed /family-induction route"),
    ("no_cst_regression", "Targeted and full branch-local no-CST suites pass", "passed", "PR #10 TD3 ablation and structured-support no-CST closeout"),
    ("no_live_cst", "R3 remains a reviewed-semantic no-CST proof", "passed", "R3 source-binding manifest"),
    ("phase_closeout", "One R3 closeout commit/push and canonical merge", "passed", "PR #8 merge commit 585d549c7a5dac0304852a0150f0c4114fd5b6e9"),
)

_R4_GATES = (
    ("two_real_observations", "Both real instances produce observations from compiled geometry", "passed", "r4_observation_contract.dc4d7d12fb9a8c84"),
    ("native_parameter_independence", "Observations do not read instance-native parameter names", "passed", "semantic arc observer contract"),
    ("three_layer_separation", "Exact geometry, semantic shape, and scalar layers remain separate", "passed", "identity-bound R4 contracts"),
    ("descriptor_registry", "Descriptors have definitions, units, versions, tolerances, and provenance", "passed", "scalar_descriptor_registry.v0"),
    ("invalid_values_fail_closed", "Unknown units, non-finite values, and invalid landmarks fail closed", "passed", "R4 contract tests"),
    ("cross_representation_equivalence", "Equivalent geometry with changed representation/patching has equivalent descriptors", "passed", "cross-representation no-CST test"),
    ("engineering_constraints", "Length, radius, aperture, curvature, nose, and regional constraints evaluate", "passed", "engineering_constraint.v0 + constraint_evaluation.v0"),
    ("constraint_kinds", "Hard, soft, advisory, and diagnostic constraint kinds are supported", "passed", "constraint evaluator contract"),
    ("no_geometry_mutation", "Observation and constraint evaluation do not mutate geometry", "passed", "source hash sentinel + immutable contracts"),
    ("w4_views", "W4 exposes descriptors, constraints, violations, locations, and sources", "implemented", "fixed /observations route"),
    ("no_cst_regression", "Targeted, cross-representation, and full no-CST suites pass", "passed", "PR #9 closeout and current TD regression proof"),
    ("no_rf_metrics", "R4 defines no RF metrics and runs no CST", "passed", "R4 manifest exclusions"),
    ("phase_closeout", "One R4 closeout commit/push and canonical merge", "passed", "PR #9 merge commit 8c6bd0be38e8b2bbf5d72c1254413ee6b552defe"),
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
    ("architecture.semantic", "Representation-independent semantic layer", "implemented_r1", "family grammar + instance boundary graphs"),
    ("architecture.representation", "Family-independent representation layer", "implemented_r2", "versioned primitive/composite contracts"),
    ("architecture.compiler", "Generic boundary compiler", "implemented_r2_no_cst", "one entry for SLS-2 and RF500"),
    ("architecture.family_induction", "Reviewed graph alignment, proposal, and patch", "implemented_r3_no_cst", "explicit manual review + held-out LEReC validation"),
    ("architecture.observation", "Representation-independent observation", "implemented_r4_no_cst", "exact/shape/scalar contracts + constraints"),
    ("workbench.w0", "Derived local project catalog", "implemented_r0b", "SQLite + loopback read-only server"),
    ("workbench.w1", "Semantic graph and grammar review", "implemented_r1", "SQLite + /semantic-graphs"),
    ("workbench.w2", "Compiled geometry ownership and trace review", "implemented_r2", "SQLite + /compile-records"),
    ("workbench.w3", "Family induction and blind-validation review", "implemented_r3", "SQLite + /family-induction"),
    ("workbench.w4", "Observation and engineering-constraint review", "implemented_r4", "SQLite + /observations"),
    ("technical_debt.td1_continuity", "TD1 Explicit Continuity Contract", "implemented_no_cst", "boundary_continuity_policy.v0 + compile_record.v1"),
    ("technical_debt.td2_spline_approx", "TD2 Spline Approximation Contract", "implemented_no_cst", "SplineApproxRepresentation / boundary_representation.v1"),
    ("technical_debt.td3_grammar_ablation", "TD3 Grammar Ablation and Structured Support", "implemented_no_cst", "family_extension_proposal.v1 + add_optional_motif"),
    ("workbench.desktop.v0", "Workbench Desktop v0", "implemented_no_cst", "fixed-action thin Windows launcher"),
    ("physics.rf_result_contract", "Mode-identified RF result/field contract", "paused_or_deferred_by_user", "R5 live paused; translator generalization deferred"),
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
        "tests.semantic_core_r1",
        "R1 grammar, topology, evidence, diff, and artifact contracts",
        "available_no_cst",
        "tests/test_rf_cem_semantic_core.py",
    ),
    (
        "tests.boundary_compiler_r2",
        "R2/TD1/TD2 representation v1, continuity, proof-bundle, and W2 contracts",
        "available_no_cst",
        "tests/test_rf_cem_boundary_compiler.py",
    ),
    (
        "tests.family_induction_r3",
        "R3/TD3 ablation, structured support, review, patch, blind-validation, and W3 contracts",
        "available_no_cst",
        "tests/test_rf_cem_family_induction.py",
    ),
    (
        "tests.observation_contract_r4",
        "R4 observation, descriptors, constraints, proof bundle, and W4 contracts",
        "available_no_cst",
        "tests/test_rf_cem_observation_contract.py",
    ),
    (
        "tests.workbench_desktop",
        "Portable full-profile Workbench and Desktop launcher contracts",
        "available_no_cst",
        "tests/test_rf_cem_workbench_desktop.py",
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


def rebuild_workbench(
    database: Path,
    source_set: WorkbenchSourceSet,
    *,
    registry_metadata: Mapping[str, str] | None = None,
) -> BuildSummary:
    """Validate explicit sources and atomically rebuild the W0-W4 read model."""
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

    w1_requested = any(
        (
            source_set.family_grammar is not None,
            bool(source_set.instance_boundary_graphs),
            source_set.instance_graph_diff is not None,
        )
    )
    w2_requested = bool(source_set.compile_records)
    w3_requested = source_set.family_induction_bundle is not None
    w4_requested = source_set.observation_contract_bundle is not None
    if w2_requested and len(source_set.compile_records) != 2:
        raise WorkbenchIndexError(
            "W2 indexing requires exactly two compatible compile record inputs"
        )
    if w2_requested and not w1_requested:
        raise WorkbenchIndexError(
            "W2 indexing requires the complete W1 grammar, graph, and diff proof set"
        )
    if w3_requested and not w2_requested:
        raise WorkbenchIndexError(
            "W3 indexing requires the complete W2 compile and W1 semantic proof sets"
        )
    if w4_requested and not w3_requested:
        raise WorkbenchIndexError(
            "W4 indexing requires the complete W3, W2, and W1 proof sets"
        )

    grammar: FamilyGrammar | None = None
    grammar_source: SourceRecord | None = None
    graph_sources: list[tuple[SourceRecord, InstanceBoundaryGraph]] = []
    if w1_requested:
        if (
            source_set.family_grammar is None
            or len(source_set.instance_boundary_graphs) != 2
            or source_set.instance_graph_diff is None
        ):
            raise WorkbenchIndexError(
                "W1 indexing requires one family grammar, exactly two instance graphs, and one graph diff"
            )
        grammar_source = _register_source(
            source_set.family_grammar, "family_grammar.v0", root
        )
        source_rows.append(grammar_source)
        grammar = load_family_grammar(source_set.family_grammar)
        for graph_path in sorted(source_set.instance_boundary_graphs, key=str):
            graph_source = _register_source(
                graph_path, "instance_boundary_graph.v0", root
            )
            source_rows.append(graph_source)
            graph_sources.append(
                (graph_source, load_instance_boundary_graph(graph_path))
            )
        diff_source = _register_source(
            source_set.instance_graph_diff,
            "instance_boundary_graph_diff.v0",
            root,
        )
        source_rows.append(diff_source)
        _index_r1_semantics(
            family_id=str(profile["family_id"]),
            grammar=grammar,
            grammar_source_id=grammar_source.source_id,
            graph_sources=tuple(graph_sources),
            graph_diff=load_instance_graph_diff(source_set.instance_graph_diff),
            diff_source_id=diff_source.source_id,
            add_entity=add_entity,
            add_relation=add_relation,
        )

    compile_records: list[CompileRecord] = []
    compile_record_sources: list[SourceRecord] = []
    if w2_requested:
        if grammar is None or grammar_source is None:
            raise WorkbenchIndexError("W2 indexing requires loaded W1 contracts")
        resolved_record_paths = [
            path.resolve() for path in source_set.compile_records
        ]
        if len(set(resolved_record_paths)) != len(resolved_record_paths):
            raise WorkbenchIndexError("W2 compile record paths must be unique")
        indexed_compile_inputs: list[
            tuple[SourceRecord, CompileRecord, Mapping[str, SourceRecord]]
        ] = []
        for record_path in sorted(resolved_record_paths, key=str):
            record_source = _register_source(
                record_path, "compile_record.v0_or_v1", root
            )
            source_rows.append(record_source)
            try:
                record = load_compile_record(record_path)
            except ValueError as exc:
                raise WorkbenchIndexError(
                    f"invalid W2 compile record: {record_source.display_path}: {exc}"
                ) from exc
            bundle_root = _compile_bundle_root(record_path, root)
            artifact_sources: dict[str, SourceRecord] = {}
            for artifact in record.output_artifacts:
                if artifact.role in artifact_sources:
                    raise WorkbenchIndexError(
                        f"duplicate output artifact role in {record.compile_id}: {artifact.role}"
                    )
                artifact_path = (bundle_root / artifact.path).resolve()
                try:
                    artifact_path.relative_to(bundle_root)
                except ValueError as exc:
                    raise WorkbenchIndexError(
                        f"W2 output artifact escapes its compile bundle: {artifact.path}"
                    ) from exc
                artifact_source = _register_source(
                    artifact_path,
                    "compile_output_artifact",
                    root,
                    expected_raw_sha256=artifact.raw_sha256,
                )
                if artifact_source.size_bytes != artifact.size_bytes:
                    raise WorkbenchIndexError(
                        f"output artifact size mismatch for {artifact_source.display_path}"
                    )
                source_rows.append(artifact_source)
                artifact_sources[artifact.role] = artifact_source
            compile_records.append(record)
            compile_record_sources.append(record_source)
            indexed_compile_inputs.append(
                (record_source, record, artifact_sources)
            )
        _index_r2_compiles(
            family_id=str(profile["family_id"]),
            profile=profile,
            profile_source=profile_source,
            grammar=grammar,
            grammar_source=grammar_source,
            graph_sources=tuple(graph_sources),
            compile_inputs=tuple(indexed_compile_inputs),
            add_entity=add_entity,
            add_relation=add_relation,
        )

    r3_bundle: R3Bundle | None = None
    if w3_requested:
        if grammar is None or grammar_source is None:
            raise WorkbenchIndexError("W3 indexing requires loaded W1 contracts")
        assert source_set.family_induction_bundle is not None
        (
            r3_bundle,
            r3_manifest_source,
            r3_artifact_sources,
            r3_declared_sources,
        ) = _load_r3_bundle_sources(
            source_set.family_induction_bundle,
            root=root,
            grammar_source=grammar_source,
            graph_sources=tuple(graph_sources),
        )
        source_rows.extend(r3_declared_sources)
        source_rows.append(r3_manifest_source)
        source_rows.extend(r3_artifact_sources.values())
        _index_r3_induction(
            family_id=str(profile["family_id"]),
            grammar=grammar,
            grammar_source=grammar_source,
            graph_sources=tuple(graph_sources),
            bundle=r3_bundle,
            manifest_source=r3_manifest_source,
            artifact_sources=r3_artifact_sources,
            add_entity=add_entity,
            add_relation=add_relation,
        )

    r4_bundle: R4Bundle | None = None
    if w4_requested:
        assert source_set.observation_contract_bundle is not None
        (
            r4_bundle,
            r4_manifest_source,
            r4_artifact_sources,
            r4_declared_sources,
        ) = _load_r4_bundle_sources(
            source_set.observation_contract_bundle,
            root=root,
        )
        source_rows.extend(r4_declared_sources)
        source_rows.append(r4_manifest_source)
        source_rows.extend(r4_artifact_sources.values())
        _index_r4_observations(
            r4_bundle,
            manifest_source=r4_manifest_source,
            artifact_sources=r4_artifact_sources,
            compile_records=tuple(compile_records),
            compile_record_sources=tuple(compile_record_sources),
            graph_sources=tuple(graph_sources),
            add_entity=add_entity,
            add_relation=add_relation,
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
            **dict(registry_metadata or {}),
            "required_w0_instances": canonical_json(sorted(REQUIRED_W0_INSTANCES)),
            "roadmap_phase": (
                "R4"
                if w4_requested
                else (
                    "R3"
                    if w3_requested
                    else (
                        "R2"
                        if w2_requested
                        else ("R1" if w1_requested else "R0B")
                    )
                )
            ),
            "w1_semantic_graphs": "indexed" if w1_requested else "not_supplied",
            "w2_compile_records": "indexed" if w2_requested else "not_supplied",
            "w3_family_induction": "indexed" if w3_requested else "not_supplied",
            "w4_observation_contract": "indexed" if w4_requested else "not_supplied",
            "r2_compile_ids": canonical_json(
                sorted(record.compile_id for record in compile_records)
            ),
            "r3_bundle_id": r3_bundle.bundle_id if r3_bundle is not None else "",
            "r3_alignment_id": (
                r3_bundle.alignment.alignment_id if r3_bundle is not None else ""
            ),
            "r3_proposal_id": (
                r3_bundle.proposal.proposal_id if r3_bundle is not None else ""
            ),
            "r3_blind_validation_id": (
                r3_bundle.blind_validation.validation_id
                if r3_bundle is not None
                else ""
            ),
            "r4_bundle_id": r4_bundle.bundle_id if r4_bundle is not None else "",
            "r4_descriptor_registry_id": (
                r4_bundle.descriptor_registry.registry_id
                if r4_bundle is not None
                else ""
            ),
            "r4_observation_bundle_ids": canonical_json(
                sorted(
                    item.observation_bundle.observation_bundle_id
                    for item in r4_bundle.instances
                )
                if r4_bundle is not None
                else []
            ),
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
    for gate_id, label, status, evidence in _R1_GATES:
        add_entity(
            EntityRecord(
                "roadmap_gate",
                f"R1.{gate_id}",
                label,
                status,
                roadmap_source_id,
                {"phase": "R1", "evidence": evidence},
            )
        )
    for gate_id, label, status, evidence in _R2_GATES:
        add_entity(
            EntityRecord(
                "roadmap_gate",
                f"R2.{gate_id}",
                label,
                status,
                roadmap_source_id,
                {"phase": "R2", "evidence": evidence},
            )
        )
    for gate_id, label, status, evidence in _R3_GATES:
        add_entity(
            EntityRecord(
                "roadmap_gate",
                f"R3.{gate_id}",
                label,
                status,
                roadmap_source_id,
                {"phase": "R3", "evidence": evidence},
            )
        )
    for gate_id, label, status, evidence in _R4_GATES:
        add_entity(
            EntityRecord(
                "roadmap_gate",
                f"R4.{gate_id}",
                label,
                status,
                roadmap_source_id,
                {"phase": "R4", "evidence": evidence},
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


def _index_r1_semantics(
    *,
    family_id: str,
    grammar: FamilyGrammar,
    grammar_source_id: str,
    graph_sources: tuple[tuple[SourceRecord, InstanceBoundaryGraph], ...],
    graph_diff: InstanceGraphDiff,
    diff_source_id: str,
    add_entity: Any,
    add_relation: Any,
) -> None:
    """Index a complete, mutually validated W1 semantic proof set."""

    if grammar.family_id != family_id:
        raise WorkbenchIndexError("W1 grammar family_id differs from family profile")
    graphs: dict[str, InstanceBoundaryGraph] = {}
    graph_source_ids: dict[str, str] = {}
    for source, graph in graph_sources:
        if graph.instance_id in graphs:
            raise WorkbenchIndexError(
                f"duplicate W1 graph instance: {graph.instance_id}"
            )
        graphs[graph.instance_id] = graph
        graph_source_ids[graph.instance_id] = source.source_id
    if set(graphs) != REQUIRED_W0_INSTANCES:
        raise WorkbenchIndexError(
            "W1 graphs must be the canonical SLS-2 and RF500 instances"
        )
    for graph in graphs.values():
        try:
            validate_graph_against_grammar(grammar, graph)
        except SemanticContractError as exc:
            raise WorkbenchIndexError(
                f"W1 graph {graph.graph_id} does not satisfy the grammar: {exc}"
            ) from exc
    expected_diff = diff_instance_graphs(
        graphs["sls2.r149.6593e02e"], graphs["rf500.2c27faee.b1r3"]
    )
    if graph_diff.to_mapping() != expected_diff.to_mapping():
        raise WorkbenchIndexError(
            "W1 graph diff is not the canonical SLS-2-to-RF500 semantic diff"
        )

    grammar_mapping = grammar.to_mapping()
    add_entity(
        EntityRecord(
            "family_grammar",
            grammar.grammar_id,
            "NC axisymmetric single-cell RF-vacuum family grammar",
            "validated_accepts_both_instances",
            grammar_source_id,
            grammar_mapping,
        )
    )
    add_relation(
        RelationRecord(
            "family_has_grammar",
            "family",
            family_id,
            "family_grammar",
            grammar.grammar_id,
        )
    )
    for ontology_kind, ontology in (
        ("semantic_region_ontology", grammar_mapping["region_ontology"]),
        ("semantic_landmark_ontology", grammar_mapping["landmark_ontology"]),
    ):
        ontology_id = str(ontology["schema_version"])
        add_entity(
            EntityRecord(
                ontology_kind,
                ontology_id,
                ontology_id,
                "canonical_v0",
                grammar_source_id,
                dict(ontology),
            )
        )
        add_relation(
            RelationRecord(
                "grammar_uses_ontology",
                "family_grammar",
                grammar.grammar_id,
                ontology_kind,
                ontology_id,
            )
        )
    for motif in grammar.motifs:
        add_entity(
            EntityRecord(
                "semantic_motif",
                motif.motif_id,
                motif.label,
                "paired_optional_topology",
                grammar_source_id,
                motif.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "grammar_has_motif",
                "family_grammar",
                grammar.grammar_id,
                "semantic_motif",
                motif.motif_id,
            )
        )

    for instance_id in sorted(graphs):
        graph = graphs[instance_id]
        graph_source_id = graph_source_ids[instance_id]
        graph_payload = {
            "schema_version": graph.schema_version,
            "graph_id": graph.graph_id,
            "family_id": graph.family_id,
            "instance_id": graph.instance_id,
            "graph_sha256": semantic_sha256(graph.to_mapping()),
            "nose_presence": graph.nose_presence,
            "active_motif_ids": list(graph.active_motif_ids),
            "region_count": len(graph.regions),
            "ordered_region_ids": [region.region_id for region in graph.regions],
            "ordered_region_types": list(graph.ordered_region_types),
            "parameter_contract": graph.parameter_contract,
            "exclusions": list(graph.exclusions),
        }
        status = (
            "validated_nose_present"
            if graph.nose_presence == "present"
            else "validated_nose_absent_reviewed_topology"
        )
        add_entity(
            EntityRecord(
                "instance_graph",
                graph.graph_id,
                f"{instance_id} semantic boundary graph",
                status,
                graph_source_id,
                graph_payload,
            )
        )
        add_relation(
            RelationRecord(
                "instance_has_semantic_graph",
                "instance",
                instance_id,
                "instance_graph",
                graph.graph_id,
            )
        )
        add_relation(
            RelationRecord(
                "grammar_accepts_graph",
                "family_grammar",
                grammar.grammar_id,
                "instance_graph",
                graph.graph_id,
            )
        )
        for motif_id in graph.active_motif_ids:
            add_relation(
                RelationRecord(
                    "graph_activates_motif",
                    "instance_graph",
                    graph.graph_id,
                    "semantic_motif",
                    motif_id,
                )
            )
        for region in graph.regions:
            add_entity(
                EntityRecord(
                    "semantic_region",
                    region.region_id,
                    f"{region.side} / {region.region_type}",
                    region.review.status,
                    graph_source_id,
                    region.to_mapping(),
                )
            )
            add_relation(
                RelationRecord(
                    "graph_has_region",
                    "instance_graph",
                    graph.graph_id,
                    "semantic_region",
                    region.region_id,
                )
            )
        for landmark in graph.landmarks:
            add_entity(
                EntityRecord(
                    "semantic_landmark",
                    landmark.landmark_id,
                    f"{landmark.side} / {landmark.landmark_type}",
                    landmark.review.status,
                    graph_source_id,
                    landmark.to_mapping(),
                )
            )
            add_relation(
                RelationRecord(
                    "graph_has_landmark",
                    "instance_graph",
                    graph.graph_id,
                    "semantic_landmark",
                    landmark.landmark_id,
                )
            )
            for region_id in landmark.incident_region_ids:
                add_relation(
                    RelationRecord(
                        "landmark_incident_to_region",
                        "semantic_landmark",
                        landmark.landmark_id,
                        "semantic_region",
                        region_id,
                    )
                )
        for interface in graph.interfaces:
            add_entity(
                EntityRecord(
                    "boundary_interface",
                    interface.interface_id,
                    (
                        f"{interface.left_region_id.rsplit('.', 1)[-1]} → "
                        f"{interface.right_region_id.rsplit('.', 1)[-1]}"
                    ),
                    "validated",
                    graph_source_id,
                    interface.to_mapping(),
                )
            )
            add_relation(
                RelationRecord(
                    "graph_has_interface",
                    "instance_graph",
                    graph.graph_id,
                    "boundary_interface",
                    interface.interface_id,
                )
            )
            add_relation(
                RelationRecord(
                    "interface_uses_landmark",
                    "boundary_interface",
                    interface.interface_id,
                    "semantic_landmark",
                    interface.landmark_id,
                )
            )

    diff_id = f"{graph_diff.left_graph_id}__vs__{graph_diff.right_graph_id}"
    add_entity(
        EntityRecord(
            "graph_diff",
            diff_id,
            "SLS-2 ↔ RF500 semantic topology diff",
            graph_diff.classification,
            diff_source_id,
            graph_diff.to_mapping(),
        )
    )
    add_relation(
        RelationRecord(
            "diff_compares_left_graph",
            "graph_diff",
            diff_id,
            "instance_graph",
            graph_diff.left_graph_id,
        )
    )
    add_relation(
        RelationRecord(
            "diff_compares_right_graph",
            "graph_diff",
            diff_id,
            "instance_graph",
            graph_diff.right_graph_id,
        )
    )
    add_entity(
        EntityRecord(
            "validation",
            "w1.semantic-hard-gate",
            "W1 semantic hard-gate proof",
            "pass",
            diff_source_id,
            {
                "grammar_id": grammar.grammar_id,
                "graph_ids": [
                    graphs[instance_id].graph_id
                    for instance_id in sorted(graphs)
                ],
                "graph_diff_id": diff_id,
                "nose_presence": {
                    instance_id: graphs[instance_id].nose_presence
                    for instance_id in sorted(graphs)
                },
                "parameter_comparison": graph_diff.parameter_comparison,
            },
        )
    )


def _index_r2_compiles(
    *,
    family_id: str,
    profile: Mapping[str, Any],
    profile_source: SourceRecord,
    grammar: FamilyGrammar,
    grammar_source: SourceRecord,
    graph_sources: tuple[tuple[SourceRecord, InstanceBoundaryGraph], ...],
    compile_inputs: tuple[
        tuple[SourceRecord, CompileRecord, Mapping[str, SourceRecord]], ...
    ],
    add_entity: Any,
    add_relation: Any,
) -> None:
    """Index two mutually bound, hash-verified R2 no-CST compile records."""

    graphs = {graph.instance_id: graph for _, graph in graph_sources}
    graph_source_by_instance = {
        graph.instance_id: source for source, graph in graph_sources
    }
    records = {record.instance_id: record for _, record, _ in compile_inputs}
    if len(records) != len(compile_inputs):
        raise WorkbenchIndexError("W2 compile records must have unique instance IDs")
    if set(records) != REQUIRED_W0_INSTANCES:
        raise WorkbenchIndexError(
            "W2 compile records must be the canonical SLS-2 and RF500 instances"
        )
    if set(graphs) != REQUIRED_W0_INSTANCES:
        raise WorkbenchIndexError("W2 requires both canonical W1 instance graphs")

    profile_canonical_sha = family_profile_sha256(profile)
    grammar_canonical_sha = semantic_sha256(grammar.to_mapping())
    representation_contexts: dict[str, set[str]] = {}
    representation_instances: dict[str, set[str]] = {}
    total_regions = 0
    total_patches = 0
    total_continuity_checks = 0

    for record_source, record, artifact_sources in sorted(
        compile_inputs, key=lambda item: item[1].instance_id
    ):
        graph = graphs[record.instance_id]
        graph_source = graph_source_by_instance[record.instance_id]
        if record.family_id != family_id or graph.family_id != family_id:
            raise WorkbenchIndexError(
                f"W2 family mismatch for compile record {record.compile_id}"
            )
        if record.status != "pass":
            raise WorkbenchIndexError(
                f"W2 only indexes passing hard-gate compile records: {record.compile_id}"
            )
        if record.live_cst_status != "not_run":
            raise WorkbenchIndexError("W2 compile records must remain no-CST")
        if record.physical_acceptance_status != "not_established":
            raise WorkbenchIndexError(
                "W2 compile records cannot claim RF physical acceptance"
            )
        _assert_contract_ref(
            record.family_grammar_ref,
            expected_kind="family_grammar",
            expected_schema=grammar.schema_version,
            expected_object_id=grammar.grammar_id,
            expected_canonical_sha256=grammar_canonical_sha,
            expected_source=grammar_source,
            label="family grammar",
        )
        _assert_contract_ref(
            record.instance_graph_ref,
            expected_kind="instance_boundary_graph",
            expected_schema=graph.schema_version,
            expected_object_id=graph.instance_id,
            expected_canonical_sha256=semantic_sha256(graph.to_mapping()),
            expected_source=graph_source,
            label=f"{record.instance_id} instance graph",
        )
        _assert_contract_ref(
            record.source_native_provenance.family_profile,
            expected_kind="family_profile",
            expected_schema=str(profile["schema_version"]),
            expected_object_id=family_id,
            expected_canonical_sha256=profile_canonical_sha,
            expected_source=profile_source,
            label="family profile",
        )

        expected_region_ids = tuple(region.region_id for region in graph.regions)
        actual_region_ids = tuple(
            geometry.owner_region_id for geometry in record.region_geometries
        )
        if actual_region_ids != expected_region_ids:
            raise WorkbenchIndexError(
                f"W2 region ownership/order differs from graph {graph.graph_id}"
            )
        graph_landmark_ids = {item.landmark_id for item in graph.landmarks}
        bound_landmark_ids = {
            item.landmark_id for item in record.landmark_bindings
        }
        if not graph_landmark_ids.issubset(bound_landmark_ids):
            missing = sorted(graph_landmark_ids - bound_landmark_ids)
            raise WorkbenchIndexError(
                f"W2 compile record omits semantic landmarks: {missing}"
            )
        patch_landmark_ids = {
            landmark_id
            for geometry in record.region_geometries
            for patch in geometry.patches
            for landmark_id in (patch.start_landmark_id, patch.end_landmark_id)
        }
        if not patch_landmark_ids.issubset(bound_landmark_ids):
            raise WorkbenchIndexError(
                f"W2 patches reference unresolved landmarks in {record.compile_id}"
            )
        artifact_roles = {item.role for item in record.output_artifacts}
        if artifact_roles != set(artifact_sources):
            raise WorkbenchIndexError(
                f"W2 artifact/source inventory mismatch in {record.compile_id}"
            )

        record_payload = record.to_mapping()
        add_entity(
            EntityRecord(
                "compile_record",
                record.compile_id,
                f"{record.instance_id} R2 boundary compile",
                "pass_no_cst_geometry",
                record_source.source_id,
                record_payload,
            )
        )
        add_relation(
            RelationRecord(
                "instance_has_compile_record",
                "instance",
                record.instance_id,
                "compile_record",
                record.compile_id,
            )
        )
        add_relation(
            RelationRecord(
                "compile_uses_family_grammar",
                "compile_record",
                record.compile_id,
                "family_grammar",
                grammar.grammar_id,
            )
        )
        add_relation(
            RelationRecord(
                "compile_uses_instance_graph",
                "compile_record",
                record.compile_id,
                "instance_graph",
                graph.graph_id,
            )
        )
        add_relation(
            RelationRecord(
                "compile_preserves_family_profile",
                "compile_record",
                record.compile_id,
                "family",
                family_id,
            )
        )

        for geometry in record.region_geometries:
            total_regions += 1
            geometry_payload = {
                **geometry.to_mapping(),
                "compile_id": record.compile_id,
                "instance_id": record.instance_id,
            }
            add_entity(
                EntityRecord(
                    "region_geometry",
                    geometry.region_geometry_id,
                    f"Region {geometry.region_order}: {geometry.owner_region_id}",
                    "compiled_owned",
                    record_source.source_id,
                    geometry_payload,
                )
            )
            add_relation(
                RelationRecord(
                    "compile_has_region_geometry",
                    "compile_record",
                    record.compile_id,
                    "region_geometry",
                    geometry.region_geometry_id,
                )
            )
            add_relation(
                RelationRecord(
                    "region_geometry_compiles_semantic_region",
                    "region_geometry",
                    geometry.region_geometry_id,
                    "semantic_region",
                    geometry.owner_region_id,
                )
            )
            composite = geometry.representation
            composite_payload = {
                **composite.to_mapping(),
                "compile_id": record.compile_id,
                "instance_id": record.instance_id,
                "owner_region_id": geometry.owner_region_id,
                "representation_scope": "region_composite",
            }
            add_entity(
                EntityRecord(
                    "representation",
                    composite.representation_id,
                    f"Composite for {geometry.owner_region_id}",
                    "compiled_r2",
                    record_source.source_id,
                    composite_payload,
                )
            )
            add_relation(
                RelationRecord(
                    "region_geometry_uses_representation",
                    "region_geometry",
                    geometry.region_geometry_id,
                    "representation",
                    composite.representation_id,
                )
            )
            for patch in geometry.patches:
                total_patches += 1
                representation = patch.representation
                representation_type = representation.representation_type
                representation_contexts.setdefault(
                    representation_type, set()
                ).add(geometry.owner_region_id)
                representation_instances.setdefault(
                    representation_type, set()
                ).add(record.instance_id)
                primitive_payload = {
                    **representation.to_mapping(),
                    "compile_id": record.compile_id,
                    "instance_id": record.instance_id,
                    "owner_region_id": geometry.owner_region_id,
                    "patch_id": patch.patch_id,
                    "representation_scope": "geometry_patch",
                }
                add_entity(
                    EntityRecord(
                        "representation",
                        representation.representation_id,
                        f"{representation_type} for {patch.patch_id}",
                        "compiled_r2",
                        record_source.source_id,
                        primitive_payload,
                    )
                )
                patch_payload = {
                    **patch.to_mapping(),
                    "compile_id": record.compile_id,
                    "instance_id": record.instance_id,
                }
                add_entity(
                    EntityRecord(
                        "geometry_patch",
                        patch.patch_id,
                        f"Patch {patch.global_order}: {patch.patch_id}",
                        "owned_oriented",
                        record_source.source_id,
                        patch_payload,
                    )
                )
                for relation in (
                    RelationRecord(
                        "region_geometry_has_patch",
                        "region_geometry",
                        geometry.region_geometry_id,
                        "geometry_patch",
                        patch.patch_id,
                    ),
                    RelationRecord(
                        "composite_representation_has_patch",
                        "representation",
                        composite.representation_id,
                        "geometry_patch",
                        patch.patch_id,
                    ),
                    RelationRecord(
                        "patch_uses_representation",
                        "geometry_patch",
                        patch.patch_id,
                        "representation",
                        representation.representation_id,
                    ),
                    RelationRecord(
                        "patch_owned_by_semantic_region",
                        "geometry_patch",
                        patch.patch_id,
                        "semantic_region",
                        geometry.owner_region_id,
                    ),
                ):
                    add_relation(relation)

        binding_entity_ids = {
            binding.landmark_id: f"{record.compile_id}:{binding.landmark_id}"
            for binding in record.landmark_bindings
        }
        for binding in record.landmark_bindings:
            binding_id = binding_entity_ids[binding.landmark_id]
            binding_payload = {
                **binding.to_mapping(),
                "compile_id": record.compile_id,
                "instance_id": record.instance_id,
            }
            add_entity(
                EntityRecord(
                    "landmark_geometry_binding",
                    binding_id,
                    f"{binding.binding_role}: {binding.landmark_id}",
                    "resolved",
                    record_source.source_id,
                    binding_payload,
                )
            )
            add_relation(
                RelationRecord(
                    "compile_has_landmark_binding",
                    "compile_record",
                    record.compile_id,
                    "landmark_geometry_binding",
                    binding_id,
                )
            )
            if binding.landmark_id in graph_landmark_ids:
                add_relation(
                    RelationRecord(
                        "landmark_binding_resolves_semantic_landmark",
                        "landmark_geometry_binding",
                        binding_id,
                        "semantic_landmark",
                        binding.landmark_id,
                    )
                )
            for patch_id in binding.incident_patch_ids:
                add_relation(
                    RelationRecord(
                        "landmark_binding_incident_to_patch",
                        "landmark_geometry_binding",
                        binding_id,
                        "geometry_patch",
                        patch_id,
                    )
                )

        for geometry in record.region_geometries:
            for patch in geometry.patches:
                add_relation(
                    RelationRecord(
                        "patch_starts_at_landmark_binding",
                        "geometry_patch",
                        patch.patch_id,
                        "landmark_geometry_binding",
                        binding_entity_ids[patch.start_landmark_id],
                    )
                )
                add_relation(
                    RelationRecord(
                        "patch_ends_at_landmark_binding",
                        "geometry_patch",
                        patch.patch_id,
                        "landmark_geometry_binding",
                        binding_entity_ids[patch.end_landmark_id],
                    )
                )

        if record.continuity_policy is not None:
            policy = record.continuity_policy
            add_entity(
                EntityRecord(
                    "boundary_continuity_policy",
                    policy.policy_id,
                    f"{record.instance_id} continuity policy",
                    "explicit_g1_default",
                    record_source.source_id,
                    {
                        **policy.to_mapping(),
                        "compile_id": record.compile_id,
                        "instance_id": record.instance_id,
                    },
                )
            )
            add_relation(
                RelationRecord(
                    "compile_uses_continuity_policy",
                    "compile_record",
                    record.compile_id,
                    "boundary_continuity_policy",
                    policy.policy_id,
                )
            )

        for endpoint in record.endpoint_constraints:
            endpoint_entity_id = f"{record.compile_id}:{endpoint.constraint_id}"
            add_entity(
                EntityRecord(
                    "profile_endpoint_constraint",
                    endpoint_entity_id,
                    f"{endpoint.endpoint_role}: {endpoint.landmark_id}",
                    "classified_one_sided",
                    record_source.source_id,
                    {
                        **endpoint.to_mapping(),
                        "compile_id": record.compile_id,
                        "instance_id": record.instance_id,
                    },
                )
            )
            for relation in (
                RelationRecord(
                    "compile_has_endpoint_constraint",
                    "compile_record",
                    record.compile_id,
                    "profile_endpoint_constraint",
                    endpoint_entity_id,
                ),
                RelationRecord(
                    "endpoint_constraint_at_landmark",
                    "profile_endpoint_constraint",
                    endpoint_entity_id,
                    "landmark_geometry_binding",
                    binding_entity_ids[endpoint.landmark_id],
                ),
                RelationRecord(
                    "endpoint_constraint_incident_to_patch",
                    "profile_endpoint_constraint",
                    endpoint_entity_id,
                    "geometry_patch",
                    endpoint.incident_patch_id,
                ),
            ):
                add_relation(relation)

        for check in record.continuity_checks:
            total_continuity_checks += 1
            check_entity_id = f"{record.compile_id}:{check.check_id}"
            check_payload = {
                **check.to_mapping(),
                "compile_id": record.compile_id,
                "instance_id": record.instance_id,
            }
            add_entity(
                EntityRecord(
                    "continuity_check",
                    check_entity_id,
                    f"{check.required_level} at {check.landmark_id}",
                    "required_pass" if check.required_pass else "required_fail",
                    record_source.source_id,
                    check_payload,
                )
            )
            for relation in (
                RelationRecord(
                    "compile_has_continuity_check",
                    "compile_record",
                    record.compile_id,
                    "continuity_check",
                    check_entity_id,
                ),
                RelationRecord(
                    "continuity_check_left_patch",
                    "continuity_check",
                    check_entity_id,
                    "geometry_patch",
                    check.left_patch_id,
                ),
                RelationRecord(
                    "continuity_check_right_patch",
                    "continuity_check",
                    check_entity_id,
                    "geometry_patch",
                    check.right_patch_id,
                ),
                RelationRecord(
                    "continuity_check_at_landmark",
                    "continuity_check",
                    check_entity_id,
                    "landmark_geometry_binding",
                    binding_entity_ids[check.landmark_id],
                ),
            ):
                add_relation(relation)
            if record.continuity_policy is not None:
                add_relation(
                    RelationRecord(
                        "continuity_check_uses_policy",
                        "continuity_check",
                        check_entity_id,
                        "boundary_continuity_policy",
                        record.continuity_policy.policy_id,
                    )
                )
            if check.interface_id is not None:
                add_relation(
                    RelationRecord(
                        "continuity_check_resolves_interface",
                        "continuity_check",
                        check_entity_id,
                        "boundary_interface",
                        check.interface_id,
                    )
                )

        geometry_validation_id = f"{record.compile_id}:geometry-validation"
        add_entity(
            EntityRecord(
                "geometry_validation",
                geometry_validation_id,
                f"{record.instance_id} BRep/STEP validation",
                "pass",
                record_source.source_id,
                {
                    **dict(record.geometry_validation),
                    "compile_id": record.compile_id,
                    "instance_id": record.instance_id,
                },
            )
        )
        add_relation(
            RelationRecord(
                "compile_has_geometry_validation",
                "compile_record",
                record.compile_id,
                "geometry_validation",
                geometry_validation_id,
            )
        )

        baseline_id = f"{record.compile_id}:baseline-comparison"
        add_entity(
            EntityRecord(
                "baseline_comparison",
                baseline_id,
                f"{record.instance_id} accepted baseline comparison",
                "pass",
                record_source.source_id,
                {
                    "compile_id": record.compile_id,
                    "instance_id": record.instance_id,
                    "contract": record.baseline.to_mapping(),
                    "comparison": dict(record.baseline_comparison),
                    "warnings": list(record.warnings),
                },
            )
        )
        add_relation(
            RelationRecord(
                "compile_has_baseline_comparison",
                "compile_record",
                record.compile_id,
                "baseline_comparison",
                baseline_id,
            )
        )

        for artifact in record.output_artifacts:
            artifact_source = artifact_sources[artifact.role]
            artifact_id = f"{record.compile_id}:{artifact.role}"
            add_entity(
                EntityRecord(
                    "geometry_artifact",
                    artifact_id,
                    f"{record.instance_id} / {artifact.role}",
                    "hash_verified",
                    artifact_source.source_id,
                    {
                        **artifact.to_mapping(),
                        "compile_id": record.compile_id,
                        "instance_id": record.instance_id,
                        "repository_relative_path": artifact_source.display_path,
                    },
                )
            )
            add_relation(
                RelationRecord(
                    "compile_produces_geometry_artifact",
                    "compile_record",
                    record.compile_id,
                    "geometry_artifact",
                    artifact_id,
                )
            )

    reused_types = sorted(
        representation_type
        for representation_type, contexts in representation_contexts.items()
        if len(contexts) > 1
    )
    cross_instance_types = sorted(
        representation_type
        for representation_type, instances in representation_instances.items()
        if len(instances) > 1
    )
    if not reused_types or not cross_instance_types:
        raise WorkbenchIndexError(
            "R2 requires a mathematical representation type reused across semantic contexts and instances"
        )
    add_entity(
        EntityRecord(
            "validation",
            "w2.boundary-compiler-hard-gate",
            "W2 boundary compiler hard-gate proof",
            "pass",
            grammar_source.source_id,
            {
                "compile_ids": sorted(record.compile_id for record in records.values()),
                "instance_ids": sorted(records),
                "region_count": total_regions,
                "patch_count": total_patches,
                "continuity_check_count": total_continuity_checks,
                "reused_representation_types": reused_types,
                "cross_instance_representation_types": cross_instance_types,
                "live_cst_status": "not_run",
                "physical_acceptance_status": "not_established",
            },
        )
    )


_R3_ARTIFACT_SOURCE_KINDS = {
    ALIGNMENT_FILE: "graph_alignment.v0",
    PROPOSAL_FILE: "family_extension_proposal.v0",
    PROPOSAL_FILE_V1: "family_extension_proposal.v1",
    SEED_GRAMMAR_FILE: "family_grammar.seed_ablation.v0",
    REVIEW_FILE: "family_extension_review.v0",
    PATCH_FILE: "family_grammar_patch.v0",
    PATCHED_GRAMMAR_FILE: "family_grammar.r3.v0",
    PATCH_APPLICATION_FILE: "family_grammar_patch_application.v0",
    BLIND_GRAPH_FILE: "instance_boundary_graph.v0.blind",
    BLIND_VALIDATION_FILE: "family_induction_blind_validation.v0",
}

_R3_V0_ARTIFACTS = {
    ALIGNMENT_FILE,
    PROPOSAL_FILE,
    REVIEW_FILE,
    PATCH_FILE,
    PATCHED_GRAMMAR_FILE,
    PATCH_APPLICATION_FILE,
    BLIND_GRAPH_FILE,
    BLIND_VALIDATION_FILE,
}
_R3_V1_ARTIFACTS = {
    ALIGNMENT_FILE,
    SEED_GRAMMAR_FILE,
    PROPOSAL_FILE_V1,
    REVIEW_FILE,
    PATCH_FILE,
    PATCHED_GRAMMAR_FILE,
    PATCH_APPLICATION_FILE,
    BLIND_GRAPH_FILE,
    BLIND_VALIDATION_FILE,
}


def _load_r3_bundle_sources(
    bundle_path: Path,
    *,
    root: Path,
    grammar_source: SourceRecord,
    graph_sources: tuple[tuple[SourceRecord, InstanceBoundaryGraph], ...],
) -> tuple[R3Bundle, SourceRecord, dict[str, SourceRecord], list[SourceRecord]]:
    """Load an immutable R3 bundle and register every independently auditable file."""

    candidate = bundle_path if bundle_path.is_absolute() else root / bundle_path
    bundle_root = candidate.resolve()
    try:
        bundle_root.relative_to(root)
    except ValueError as exc:
        raise WorkbenchIndexError(
            "W3 family-induction bundle must be inside the declared repository root"
        ) from exc
    try:
        bundle = load_r3_bundle(bundle_root)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise WorkbenchIndexError(f"invalid W3 family-induction bundle: {exc}") from exc

    manifest_path = bundle_root / bundle.manifest_file
    manifest_source = _register_source(
        manifest_path,
        (
            "r3_family_induction_ablation_source_binding_manifest.v1"
            if bundle.manifest_file == R3_MANIFEST_FILE_V1
            else "r3_family_induction_source_binding_manifest.v0"
        ),
        root,
    )
    raw_artifacts = bundle.manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise WorkbenchIndexError("W3 manifest artifacts must be a list")
    artifact_entries: dict[str, Mapping[str, Any]] = {}
    for value in raw_artifacts:
        if not isinstance(value, Mapping):
            raise WorkbenchIndexError("W3 manifest artifact entry must be an object")
        relative = str(value.get("path") or "")
        if relative in artifact_entries:
            raise WorkbenchIndexError(f"duplicate W3 artifact path: {relative}")
        artifact_entries[relative] = value
    expected_artifacts = (
        _R3_V1_ARTIFACTS if bundle.seed_grammar is not None else _R3_V0_ARTIFACTS
    )
    if set(artifact_entries) != expected_artifacts:
        raise WorkbenchIndexError("W3 manifest artifact inventory is incomplete")

    artifact_sources: dict[str, SourceRecord] = {}
    for relative in sorted(artifact_entries):
        value = artifact_entries[relative]
        expected_size = value.get("size_bytes")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise WorkbenchIndexError(f"W3 artifact size is invalid: {relative}")
        record = _register_source(
            bundle_root / relative,
            _R3_ARTIFACT_SOURCE_KINDS[relative],
            root,
            expected_raw_sha256=str(value.get("raw_sha256") or ""),
        )
        if record.size_bytes != expected_size:
            raise WorkbenchIndexError(f"W3 artifact size mismatch: {relative}")
        artifact_sources[relative] = record

    known_sources = {
        grammar_source.display_path: grammar_source,
        **{
            source.display_path: source
            for source, _ in graph_sources
        },
    }
    raw_declared_sources = bundle.manifest.get("sources")
    if not isinstance(raw_declared_sources, list):
        raise WorkbenchIndexError("W3 manifest sources must be a list")
    declared_paths: set[str] = set()
    new_declared_sources: list[SourceRecord] = []
    for value in raw_declared_sources:
        if not isinstance(value, Mapping):
            raise WorkbenchIndexError("W3 manifest source entry must be an object")
        relative = str(value.get("path") or "")
        if not relative or relative in declared_paths:
            raise WorkbenchIndexError("W3 manifest source paths must be non-empty and unique")
        declared_paths.add(relative)
        expected_hash = str(value.get("raw_sha256") or "")
        expected_size = value.get("size_bytes")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise WorkbenchIndexError(f"W3 declared source size is invalid: {relative}")
        known = known_sources.get(relative)
        if known is not None:
            if known.raw_sha256 != expected_hash or known.size_bytes != expected_size:
                raise WorkbenchIndexError(
                    f"W3 declared W1 source identity mismatch: {relative}"
                )
            continue
        source_kind = (
            "r3_representation_contract_sentinel"
            if relative == "src/rf_cem/representation/core.py"
            else "r3_blind_primary_source"
        )
        current_path = root / relative
        legacy_sentinel_identity = (
            bundle.bundle_id,
            expected_hash,
            expected_size,
        )
        if (
            relative == "src/rf_cem/representation/core.py"
            and legacy_sentinel_identity
            in _LEGACY_R3_REPRESENTATION_SENTINELS
            and current_path.is_file()
            and file_sha256(current_path) != expected_hash
        ):
            # Compatibility read: the manifest is the historical identity.
            # Do not register the current, different module under the old hash.
            continue
        record = _register_source(
            current_path,
            source_kind,
            root,
            expected_raw_sha256=expected_hash,
        )
        if record.size_bytes != expected_size:
            raise WorkbenchIndexError(f"W3 declared source size mismatch: {relative}")
        new_declared_sources.append(record)

    expected_w1_paths = set(known_sources)
    if not expected_w1_paths.issubset(declared_paths):
        raise WorkbenchIndexError("W3 manifest omits a W1 induction contract source")
    if "src/rf_cem/representation/core.py" not in declared_paths:
        raise WorkbenchIndexError("W3 manifest omits the R2 representation sentinel")
    pdf_paths = {path for path in declared_paths if path.lower().endswith(".pdf")}
    if len(pdf_paths) != 2:
        raise WorkbenchIndexError("W3 manifest requires both LEReC primary PDF sources")
    if len(declared_paths) != 6:
        raise WorkbenchIndexError("W3 manifest must bind exactly six canonical inputs")
    return (
        bundle,
        manifest_source,
        artifact_sources,
        new_declared_sources,
    )


def _index_r3_induction(
    *,
    family_id: str,
    grammar: FamilyGrammar,
    grammar_source: SourceRecord,
    graph_sources: tuple[tuple[SourceRecord, InstanceBoundaryGraph], ...],
    bundle: R3Bundle,
    manifest_source: SourceRecord,
    artifact_sources: Mapping[str, SourceRecord],
    add_entity: Any,
    add_relation: Any,
) -> None:
    """Recheck and index the complete reviewed R3 induction hard-gate chain."""

    alignment = bundle.alignment
    proposal = bundle.proposal
    review = bundle.review
    patch = bundle.patch
    updated = bundle.patched_grammar
    application = bundle.patch_application
    blind_graph = bundle.blind_graph
    blind_validation = bundle.blind_validation
    base_grammar = bundle.seed_grammar or grammar
    graphs = {graph.instance_id: graph for _, graph in graph_sources}
    graph_source_by_instance = {
        graph.instance_id: source for source, graph in graph_sources
    }
    if set(graphs) != REQUIRED_W0_INSTANCES:
        raise WorkbenchIndexError("W3 requires the canonical SLS-2 and RF500 graphs")
    for graph in graphs.values():
        try:
            validate_reviewed_graph_intrinsic(graph)
        except SemanticContractError as exc:
            raise WorkbenchIndexError(
                f"W3 reviewed graph is not intrinsic-valid: {graph.instance_id}: {exc}"
            ) from exc
    if bundle.seed_grammar is not None:
        seed = bundle.seed_grammar
        if (
            seed.family_id != grammar.family_id
            or any(item.region_type == "NoseRegion" for item in seed.motifs)
            or "NoseRegion" in seed.cardinalities
            or any("NoseRegion" in pair for pair in seed.allowed_adjacencies)
        ):
            raise WorkbenchIndexError(
                "W3 seed grammar did not fully ablate the nose motif contract"
            )
        try:
            validate_graph_against_grammar(seed, graphs[SLS2_INSTANCE_ID])
        except SemanticContractError as exc:
            raise WorkbenchIndexError(
                f"W3 seed grammar does not admit SLS-2: {exc}"
            ) from exc
        try:
            validate_graph_against_grammar(seed, graphs[RF500_INSTANCE_ID])
        except SemanticContractError:
            pass
        else:
            raise WorkbenchIndexError(
                "W3 seed grammar unexpectedly admits RF500 before patch"
            )
    if alignment.family_id != family_id or set(alignment.source_instance_ids) != set(
        REQUIRED_W0_INSTANCES
    ):
        raise WorkbenchIndexError("W3 alignment training set/family mismatch")
    if alignment.parameter_names_read is not False or (
        alignment.input_contract != "reviewed_instance_boundary_graphs_only"
    ):
        raise WorkbenchIndexError("W3 alignment depends on an unsupported input contract")
    refs = {item.instance_id: item for item in alignment.graph_refs}
    for instance_id in sorted(REQUIRED_W0_INSTANCES):
        graph = graphs[instance_id]
        source = graph_source_by_instance[instance_id]
        reference = refs.get(instance_id)
        if reference is None or (
            reference.graph_id,
            reference.source_path,
            reference.source_raw_sha256,
            reference.contract_sha256,
        ) != (
            graph.graph_id,
            source.display_path,
            source.raw_sha256,
            semantic_sha256(graph.to_mapping()),
        ):
            raise WorkbenchIndexError(
                f"W3 alignment graph/source binding mismatch: {instance_id}"
            )

    expected_backbone = tuple(
        f"{slot.side}:{slot.region_type}" for slot in base_grammar.backbone_slots
    )
    actual_backbone = tuple(slot.semantic_key for slot in alignment.common_backbone)
    if actual_backbone != expected_backbone:
        raise WorkbenchIndexError("W3 common backbone differs from the W1 grammar")
    if proposal.alignment_id != alignment.alignment_id or (
        proposal.alignment_content_sha256 != alignment.content_sha256
    ):
        raise WorkbenchIndexError("W3 proposal/alignment identity mismatch")
    if proposal.proposal_kind != "optional_motif" or (
        proposal.region_type,
        proposal.occurrence_rule,
        proposal.allowed_counts,
    ) != ("NoseRegion", "paired_optional", (0, 2)):
        raise WorkbenchIndexError("W3 canonical proposal is not the paired optional nose motif")
    if proposal.common_backbone_keys != actual_backbone:
        raise WorkbenchIndexError("W3 proposal/common-backbone binding mismatch")
    if set(proposal.present_instance_ids) | set(proposal.absent_instance_ids) != set(
        REQUIRED_W0_INSTANCES
    ):
        raise WorkbenchIndexError("W3 proposal does not partition both training instances")
    if review.decision != "accepted" or review.manual_confirmation is not True:
        raise WorkbenchIndexError("W3 closeout requires an accepted manual proposal review")
    if review.proposal_id != proposal.proposal_id or (
        review.proposal_content_sha256 != proposal.content_sha256
    ):
        raise WorkbenchIndexError("W3 proposal/review identity mismatch")

    base_sha = semantic_sha256(base_grammar.to_mapping())
    updated_sha = semantic_sha256(updated.to_mapping())
    if (
        patch.base_grammar_id != base_grammar.grammar_id
        or patch.base_grammar_sha256 != base_sha
        or application.before_grammar_id != base_grammar.grammar_id
        or application.before_grammar_sha256 != base_sha
    ):
        raise WorkbenchIndexError("W3 patch does not target the indexed seed grammar")
    if (
        patch.target_grammar_id != updated.grammar_id
        or patch.target_grammar_sha256 != updated_sha
        or application.after_grammar_id != updated.grammar_id
        or application.after_grammar_sha256 != updated_sha
    ):
        raise WorkbenchIndexError("W3 patch target/patched grammar identity mismatch")
    if (
        patch.proposal_id != proposal.proposal_id
        or patch.proposal_content_sha256 != proposal.content_sha256
        or patch.review_id != review.review_id
        or patch.review_content_sha256 != review.content_sha256
    ):
        raise WorkbenchIndexError("W3 patch proposal/review binding mismatch")
    if not application.applied or application.review_decision != "accepted" or (
        application.patch_id != patch.patch_id
    ):
        raise WorkbenchIndexError("W3 accepted patch was not explicitly applied")
    if (
        application.proposal_id != proposal.proposal_id
        or application.review_id != review.review_id
        or application.patch_content_sha256 != patch.content_sha256
    ):
        raise WorkbenchIndexError("W3 patch application contract binding mismatch")
    if not application.all_instances_valid or set(
        application.validated_instance_ids
    ) != set(REQUIRED_W0_INSTANCES):
        raise WorkbenchIndexError("W3 patch did not revalidate both training instances")
    try:
        for graph in graphs.values():
            validate_graph_against_grammar(updated, graph)
        validate_graph_against_grammar(updated, blind_graph)
    except (SemanticContractError, ValueError) as exc:
        raise WorkbenchIndexError(f"W3 patched grammar validation failed: {exc}") from exc

    if updated.family_id != family_id or blind_graph.family_id != family_id:
        raise WorkbenchIndexError("W3 patched grammar/blind graph family mismatch")
    patched_motif = next(
        (
            motif
            for motif in updated.motifs
            if motif.motif_id == patch.proposed_motif.motif_id
        ),
        None,
    )
    proposal_insertions = tuple(
        sorted(
            (
                item.side,
                item.before_region_type,
                item.after_region_type,
            )
            for item in proposal.insertion_adjacencies
        )
    )
    patch_insertions = tuple(
        sorted(
            (item.side, *item.between_region_types)
            for item in patch.proposed_motif.insertion_rules
        )
    )
    patch_motif_shape = patch.proposed_motif.to_mapping()
    patch_motif_shape.pop("evidence")
    patched_motif_shape = patched_motif.to_mapping() if patched_motif is not None else {}
    patched_motif_shape.pop("evidence", None)
    if (
        proposal.motif_id != patch.proposed_motif.motif_id
        or proposal.region_type != patch.proposed_motif.region_type
        or proposal.allowed_counts != patch.proposed_motif.allowed_counts
        or proposal_insertions != patch_insertions
        or patched_motif is None
        or patched_motif_shape != patch_motif_shape
    ):
        raise WorkbenchIndexError("W3 proposal/patch/patched-motif binding mismatch")
    if blind_graph.instance_id in REQUIRED_W0_INSTANCES or (
        blind_validation.blind_instance_id != blind_graph.instance_id
    ):
        raise WorkbenchIndexError("W3 blind instance is not held out")
    if set(blind_validation.training_instance_ids) != set(REQUIRED_W0_INSTANCES) or (
        blind_validation.blind_instance_used_for_induction is not False
    ):
        raise WorkbenchIndexError("W3 blind instance leaked into induction")
    blind_graph_source = artifact_sources[BLIND_GRAPH_FILE]
    if (
        blind_validation.blind_graph_ref.contract_sha256
        != semantic_sha256(blind_graph.to_mapping())
        or blind_validation.blind_graph_ref.source_raw_sha256
        != blind_graph_source.raw_sha256
    ):
        raise WorkbenchIndexError("W3 blind graph/source binding mismatch")
    if (
        blind_validation.proposal_id != proposal.proposal_id
        or blind_validation.proposal_content_sha256 != proposal.content_sha256
        or blind_validation.grammar_id != updated.grammar_id
        or blind_validation.grammar_sha256 != updated_sha
    ):
        raise WorkbenchIndexError("W3 blind validation contract binding mismatch")
    if blind_validation.representation_contract != "not_imported_or_modified":
        raise WorkbenchIndexError("W3 altered or imported the R2 representation contract")

    manifest = bundle.manifest
    required_checks = {
        "alignment_reads_reviewed_semantic_side_and_type_only",
        "sls2_and_rf500_common_backbone_extracted",
        "nose_pair_proposed_as_optional_motif",
        "pending_proposal_does_not_mutate_grammar",
        "all_training_instances_revalidate_after_patch",
        "held_out_real_lerec704_classified_after_induction",
        "blind_instance_not_used_for_induction",
        "representation_core_not_imported_or_modified",
        "live_cst_not_run",
    }
    if bundle.seed_grammar is None:
        required_checks.add(
            "accepted_manual_review_authorizes_explicit_hash_bound_patch"
        )
        expected_validation_mode = "reviewed_semantic_graphs_no_cst"
    else:
        required_checks.update(
            {
                "reviewed_graphs_intrinsic_valid_before_family_admission",
                "seed_grammar_nose_motif_cardinality_and_adjacencies_removed",
                "seed_grammar_admits_sls2_and_rejects_rf500_before_patch",
                "paired_optional_detector_selected",
                "structured_support_is_heuristic_not_probability",
                "accepted_manual_review_authorizes_add_optional_motif",
                "synthetic_single_optional_detector_fixture_implemented",
            }
        )
        expected_validation_mode = (
            "intrinsic_reviewed_graph_then_family_admission_no_cst"
        )
    manifest_checks = manifest.get("checks")
    if (
        manifest.get("status") != "pass"
        or not isinstance(manifest_checks, list)
        or not all(isinstance(value, str) for value in manifest_checks)
        or not required_checks.issubset(set(manifest_checks))
    ):
        raise WorkbenchIndexError("W3 source-binding manifest hard-gate checks are incomplete")
    if manifest.get("validation_mode") != expected_validation_mode:
        raise WorkbenchIndexError("W3 manifest validation mode is unsupported")
    expected_manifest_identities = {
        "bundle_id": bundle.bundle_id,
        "input_sha256": bundle.input_sha256,
        "training_instance_ids": list(alignment.source_instance_ids),
        "blind_instance_id": blind_graph.instance_id,
        "alignment_id": alignment.alignment_id,
        "proposal_id": proposal.proposal_id,
        "review_id": review.review_id,
        "review_decision": review.decision,
        "patch_id": patch.patch_id,
        "patched_grammar_id": updated.grammar_id,
        "patched_grammar_sha256": updated_sha,
        "patch_application_id": application.application_id,
        "blind_validation_id": blind_validation.validation_id,
        "blind_classification": blind_validation.classification,
    }
    for key, expected in expected_manifest_identities.items():
        if manifest.get(key) != expected:
            raise WorkbenchIndexError(f"W3 manifest contract identity mismatch: {key}")
    if bundle.seed_grammar is not None:
        seed = bundle.seed_grammar
        v1_identities = {
            "canonical_grammar_id": grammar.grammar_id,
            "canonical_grammar_sha256": semantic_sha256(grammar.to_mapping()),
            "seed_grammar_id": seed.grammar_id,
            "seed_grammar_sha256": semantic_sha256(seed.to_mapping()),
            "proposal_schema_version": "family_extension_proposal.v1",
            "patch_operation": "add_optional_motif",
            "score_semantics": "heuristic_support_not_probability",
        }
        for key, expected in v1_identities.items():
            if manifest.get(key) != expected:
                raise WorkbenchIndexError(
                    f"W3 ablation manifest identity mismatch: {key}"
                )
        selected_detector = manifest.get("selected_detector")
        if not isinstance(selected_detector, Mapping) or (
            selected_detector.get("detector_id") != "paired_optional_motif"
            or selected_detector.get("population_size") != 2
            or selected_detector.get("symmetry_assumption_used") is not True
        ):
            raise WorkbenchIndexError(
                "W3 ablation manifest detector/support contract is invalid"
            )

    add_entity(
        EntityRecord(
            "family_induction_bundle",
            bundle.bundle_id,
            "R3 reviewed family-induction proof bundle",
            "pass_no_cst",
            manifest_source.source_id,
            dict(manifest),
        )
    )
    add_relation(
        RelationRecord(
            "family_has_induction_bundle",
            "family",
            family_id,
            "family_induction_bundle",
            bundle.bundle_id,
        )
    )
    if bundle.seed_grammar is not None:
        seed_payload = {
            **bundle.seed_grammar.to_mapping(),
            "ablation": manifest.get("seed_ablation"),
            "pre_patch_admission": manifest.get("pre_patch_admission"),
        }
        add_entity(
            EntityRecord(
                "seed_grammar_ablation",
                bundle.seed_grammar.grammar_id,
                "TD3 seed grammar before nose-motif patch",
                "rf500_not_admitted_before_patch",
                artifact_sources[SEED_GRAMMAR_FILE].source_id,
                seed_payload,
            )
        )
        add_entity(
            EntityRecord(
                "induction_detector_fixture",
                "single_optional_motif.synthetic.v1",
                "Synthetic single optional motif detector fixture",
                str(
                    manifest.get(
                        "synthetic_single_optional_detector_fixture_status"
                    )
                ),
                manifest_source.source_id,
                {
                    "detector_id": "single_optional_motif",
                    "detector_version": "single_optional_motif.v1",
                    "symmetry_assumption_used": False,
                    "fixture_kind": "synthetic_reviewed_graphs_no_cst",
                    "status": manifest.get(
                        "synthetic_single_optional_detector_fixture_status"
                    ),
                },
            )
        )
        for relation in (
            RelationRecord(
                "bundle_has_seed_grammar_ablation",
                "family_induction_bundle",
                bundle.bundle_id,
                "seed_grammar_ablation",
                bundle.seed_grammar.grammar_id,
            ),
            RelationRecord(
                "bundle_declares_detector_fixture",
                "family_induction_bundle",
                bundle.bundle_id,
                "induction_detector_fixture",
                "single_optional_motif.synthetic.v1",
            ),
        ):
            add_relation(relation)
    _index_r3_induction_tail(
        family_id=family_id,
        grammar=base_grammar,
        bundle=bundle,
        alignment=alignment,
        proposal=proposal,
        review=review,
        patch=patch,
        updated=updated,
        application=application,
        blind_graph=blind_graph,
        blind_graph_source=blind_graph_source,
        blind_validation=blind_validation,
        artifact_sources=artifact_sources,
        manifest_source=manifest_source,
        add_entity=add_entity,
        add_relation=add_relation,
    )


def _load_r4_bundle_sources(
    bundle_path: Path,
    *,
    root: Path,
) -> tuple[R4Bundle, SourceRecord, dict[str, SourceRecord], list[SourceRecord]]:
    """Strictly load R4 and register every declared input/output source."""

    resolved = bundle_path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkbenchIndexError(
            "W4 observation bundle must be inside the declared repository root"
        ) from exc
    try:
        bundle = load_r4_bundle(resolved, repo_root=root)
    except ValueError as exc:
        raise WorkbenchIndexError(f"invalid W4 observation bundle: {exc}") from exc
    manifest_path = resolved / "source_binding_manifest.v0.json"
    manifest_source = _register_source(
        manifest_path,
        "r4_observation_source_binding_manifest.v0",
        root,
    )
    declared_sources: list[SourceRecord] = []
    source_values = bundle.manifest.get("sources")
    if not isinstance(source_values, list):
        raise WorkbenchIndexError("W4 manifest sources must be an array")
    for value in source_values:
        source = _mapping(value, "W4 declared source")
        relative = str(source.get("path") or "")
        expected = str(source.get("raw_sha256") or "")
        if not relative or not expected:
            raise WorkbenchIndexError("W4 source identity is incomplete")
        declared_sources.append(
            _register_source(
                root / relative,
                "r4_declared_source",
                root,
                expected_raw_sha256=expected,
            )
        )
    artifact_sources: dict[str, SourceRecord] = {}
    artifact_values = bundle.manifest.get("artifacts")
    if not isinstance(artifact_values, list):
        raise WorkbenchIndexError("W4 manifest artifacts must be an array")
    for value in artifact_values:
        artifact = _mapping(value, "W4 artifact")
        relative = str(artifact.get("path") or "")
        expected = str(artifact.get("raw_sha256") or "")
        if not relative or relative in artifact_sources or not expected:
            raise WorkbenchIndexError("W4 artifact identity is invalid or duplicated")
        artifact_sources[relative] = _register_source(
            resolved / relative,
            "r4_observation_artifact",
            root,
            expected_raw_sha256=expected,
        )
    return bundle, manifest_source, artifact_sources, declared_sources


def _index_r4_observations(
    bundle: R4Bundle,
    *,
    manifest_source: SourceRecord,
    artifact_sources: Mapping[str, SourceRecord],
    compile_records: tuple[CompileRecord, ...],
    compile_record_sources: tuple[SourceRecord, ...],
    graph_sources: tuple[tuple[SourceRecord, InstanceBoundaryGraph], ...],
    add_entity: Any,
    add_relation: Any,
) -> None:
    """Index the exact/shape/scalar layers and non-mutating constraints for W4."""

    compile_by_instance = {item.instance_id: item for item in compile_records}
    compile_source_by_instance = {
        record.instance_id: source
        for source, record in zip(compile_record_sources, compile_records)
    }
    graph_by_instance = {graph.instance_id: (source, graph) for source, graph in graph_sources}
    bundle_instances = {
        item.exact_geometry.instance_id: item for item in bundle.instances
    }
    if (
        set(bundle_instances) != set(compile_by_instance)
        or set(bundle_instances) != set(compile_source_by_instance)
        or set(bundle_instances) != set(graph_by_instance)
    ):
        raise WorkbenchIndexError("W4 instance set differs from indexed W1/W2 proofs")
    manifest_sources = {
        str(item.get("path") or ""): str(item.get("raw_sha256") or "")
        for item in bundle.manifest.get("sources", [])
        if isinstance(item, Mapping)
    }
    for source, _ in graph_sources:
        if manifest_sources.get(source.display_path) != source.raw_sha256:
            raise WorkbenchIndexError("W4 graph source differs from indexed W1 graph")
    for instance_id, source in compile_source_by_instance.items():
        if manifest_sources.get(source.display_path) != source.raw_sha256:
            raise WorkbenchIndexError(
                f"W4 compile source differs from indexed W2 record: {instance_id}"
            )

    registry = bundle.descriptor_registry
    registry_path = str(_mapping(bundle.manifest["descriptor_registry"], "W4 registry")["path"])
    registry_source = artifact_sources[registry_path]
    add_entity(
        EntityRecord(
            "descriptor_registry",
            registry.registry_id,
            "R4 scalar descriptor registry",
            "active_r4_no_cst",
            registry_source.source_id,
            registry.to_mapping(),
        )
    )
    definition_entity_ids: dict[str, str] = {}
    for definition in registry.definitions:
        definition_id = f"{registry.registry_id}:{definition.descriptor_id}"
        definition_entity_ids[definition.descriptor_id] = definition_id
        add_entity(
            EntityRecord(
                "descriptor_definition",
                definition_id,
                definition.label,
                "versioned_unit_bound",
                registry_source.source_id,
                definition.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "registry_defines_descriptor",
                "descriptor_registry",
                registry.registry_id,
                "descriptor_definition",
                definition_id,
            )
        )

    constraint_paths = {
        str(item["constraint_id"]): str(item["path"])
        for item in bundle.manifest.get("constraints", [])
        if isinstance(item, Mapping)
    }
    for constraint in bundle.constraints:
        constraint_source = artifact_sources[constraint_paths[constraint.constraint_id]]
        add_entity(
            EntityRecord(
                "engineering_constraint",
                constraint.constraint_id,
                constraint.label,
                constraint.constraint_kind,
                constraint_source.source_id,
                constraint.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "constraint_uses_descriptor_definition",
                "engineering_constraint",
                constraint.constraint_id,
                "descriptor_definition",
                definition_entity_ids[constraint.descriptor_id],
            )
        )

    instance_summaries = {
        str(item["instance_id"]): item
        for item in bundle.manifest.get("instances", [])
        if isinstance(item, Mapping)
    }
    total_values = 0
    total_findings = 0
    total_violations = 0
    kinds_seen: set[str] = set()
    for instance_id, instance in sorted(bundle_instances.items()):
        exact = instance.exact_geometry
        shape = instance.shape_observation
        observation_bundle = instance.observation_bundle
        record = compile_by_instance[instance_id]
        graph = graph_by_instance[instance_id][1]
        if exact.compile_id != record.compile_id or exact.compile_content_sha256 != record.content_sha256:
            raise WorkbenchIndexError("W4 exact geometry differs from indexed W2 compile")
        if {item.region_id for item in shape.regions} != {
            item.region_id for item in graph.regions
        }:
            raise WorkbenchIndexError("W4 region observations differ from indexed W1 graph")
        if {item.landmark_id for item in shape.landmarks} != {
            item.landmark_id for item in graph.landmarks
        }:
            raise WorkbenchIndexError("W4 landmark observations differ from indexed W1 graph")
        instance_root = f"instances/{instance_id}"
        exact_source = artifact_sources[
            f"{instance_root}/exact_geometry_reference.v0.json"
        ]
        shape_source = artifact_sources[
            f"{instance_root}/semantic_shape_observation.v0.json"
        ]
        bundle_source = artifact_sources[
            f"{instance_root}/observation_bundle.v0.json"
        ]
        add_entity(
            EntityRecord(
                "exact_geometry_reference",
                exact.exact_geometry_id,
                f"{instance_id} exact compiled geometry",
                "hash_bound_exact",
                exact_source.source_id,
                exact.to_mapping(),
            )
        )
        for relation in (
            RelationRecord(
                "instance_has_exact_geometry",
                "instance",
                instance_id,
                "exact_geometry_reference",
                exact.exact_geometry_id,
            ),
            RelationRecord(
                "exact_geometry_references_compile",
                "exact_geometry_reference",
                exact.exact_geometry_id,
                "compile_record",
                exact.compile_id,
            ),
        ):
            add_relation(relation)
        for artifact in exact.geometry_artifacts:
            add_relation(
                RelationRecord(
                    "exact_geometry_references_artifact",
                    "exact_geometry_reference",
                    exact.exact_geometry_id,
                    "geometry_artifact",
                    f"{exact.compile_id}:{artifact.role}",
                )
            )

        add_entity(
            EntityRecord(
                "semantic_shape_observation",
                shape.shape_observation_id,
                f"{instance_id} semantic shape observation",
                "pass_no_cst",
                shape_source.source_id,
                shape.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "shape_observes_exact_geometry",
                "semantic_shape_observation",
                shape.shape_observation_id,
                "exact_geometry_reference",
                exact.exact_geometry_id,
            )
        )
        for region in shape.regions:
            region_observation_id = f"{shape.shape_observation_id}:{region.region_id}"
            add_entity(
                EntityRecord(
                    "region_shape_observation",
                    region_observation_id,
                    f"{region.region_type} / {region.side}",
                    "normalized_arc_observed",
                    shape_source.source_id,
                    region.to_mapping(),
                )
            )
            add_relation(
                RelationRecord(
                    "shape_has_region_observation",
                    "semantic_shape_observation",
                    shape.shape_observation_id,
                    "region_shape_observation",
                    region_observation_id,
                )
            )
            add_relation(
                RelationRecord(
                    "region_observation_observes_semantic_region",
                    "region_shape_observation",
                    region_observation_id,
                    "semantic_region",
                    region.region_id,
                )
            )
        for landmark in shape.landmarks:
            landmark_observation_id = (
                f"{shape.shape_observation_id}:{landmark.landmark_id}"
            )
            add_entity(
                EntityRecord(
                    "landmark_shape_observation",
                    landmark_observation_id,
                    f"{landmark.landmark_type} / {landmark.side}",
                    "resolved_compiled_coordinate",
                    shape_source.source_id,
                    landmark.to_mapping(),
                )
            )
            add_relation(
                RelationRecord(
                    "shape_has_landmark_observation",
                    "semantic_shape_observation",
                    shape.shape_observation_id,
                    "landmark_shape_observation",
                    landmark_observation_id,
                )
            )
            add_relation(
                RelationRecord(
                    "landmark_observation_resolves_semantic_landmark",
                    "landmark_shape_observation",
                    landmark_observation_id,
                    "semantic_landmark",
                    landmark.landmark_id,
                )
            )

        add_entity(
            EntityRecord(
                "observation_bundle",
                observation_bundle.observation_bundle_id,
                f"{instance_id} R4 observation bundle",
                "pass_no_cst",
                bundle_source.source_id,
                observation_bundle.to_mapping(),
            )
        )
        for relation in (
            RelationRecord(
                "instance_has_observation_bundle",
                "instance",
                instance_id,
                "observation_bundle",
                observation_bundle.observation_bundle_id,
            ),
            RelationRecord(
                "observation_bundle_references_exact_geometry",
                "observation_bundle",
                observation_bundle.observation_bundle_id,
                "exact_geometry_reference",
                exact.exact_geometry_id,
            ),
            RelationRecord(
                "observation_bundle_references_shape",
                "observation_bundle",
                observation_bundle.observation_bundle_id,
                "semantic_shape_observation",
                shape.shape_observation_id,
            ),
            RelationRecord(
                "observation_bundle_uses_registry",
                "observation_bundle",
                observation_bundle.observation_bundle_id,
                "descriptor_registry",
                registry.registry_id,
            ),
        ):
            add_relation(relation)
        value_entity_ids: dict[str, str] = {}
        for value in observation_bundle.descriptor_values:
            total_values += 1
            value_entity_ids[value.value_id] = value.value_id
            definition = registry.by_id[value.descriptor_id]
            add_entity(
                EntityRecord(
                    "scalar_descriptor",
                    value.value_id,
                    f"{definition.label} / {value.scope_id}",
                    value.status,
                    bundle_source.source_id,
                    value.to_mapping(),
                )
            )
            add_relation(
                RelationRecord(
                    "observation_bundle_has_descriptor",
                    "observation_bundle",
                    observation_bundle.observation_bundle_id,
                    "scalar_descriptor",
                    value.value_id,
                )
            )
            add_relation(
                RelationRecord(
                    "descriptor_uses_definition",
                    "scalar_descriptor",
                    value.value_id,
                    "descriptor_definition",
                    definition_entity_ids[value.descriptor_id],
                )
            )
            target_kind = "instance" if value.scope_kind == "global" else "semantic_region"
            add_relation(
                RelationRecord(
                    "descriptor_observes_scope",
                    "scalar_descriptor",
                    value.value_id,
                    target_kind,
                    value.scope_id,
                )
            )

        summary = _mapping(instance_summaries[instance_id], "W4 instance summary")
        evaluation_paths = summary.get("evaluation_paths")
        if not isinstance(evaluation_paths, list):
            raise WorkbenchIndexError("W4 evaluation path summary is invalid")
        evaluation_path_by_id = {
            Path(str(relative)).stem: str(relative) for relative in evaluation_paths
        }
        for evaluation in instance.evaluations:
            kinds_seen.add(evaluation.constraint_kind)
            relative = evaluation_path_by_id.get(evaluation.evaluation_id)
            if relative is None:
                raise WorkbenchIndexError("W4 evaluation artifact path is missing")
            evaluation_source = artifact_sources[relative]
            add_entity(
                EntityRecord(
                    "constraint_evaluation",
                    evaluation.evaluation_id,
                    f"{instance_id} / {evaluation.constraint_kind}",
                    evaluation.result,
                    evaluation_source.source_id,
                    evaluation.to_mapping(),
                )
            )
            for relation in (
                RelationRecord(
                    "evaluation_applies_constraint",
                    "constraint_evaluation",
                    evaluation.evaluation_id,
                    "engineering_constraint",
                    evaluation.constraint_ref.object_id,
                ),
                RelationRecord(
                    "evaluation_reads_observation_bundle",
                    "constraint_evaluation",
                    evaluation.evaluation_id,
                    "observation_bundle",
                    observation_bundle.observation_bundle_id,
                ),
            ):
                add_relation(relation)
            for index, finding in enumerate(evaluation.findings):
                total_findings += 1
                if not finding.passed:
                    total_violations += 1
                finding_id = f"{evaluation.evaluation_id}:finding:{index:02d}"
                add_entity(
                    EntityRecord(
                        "constraint_finding",
                        finding_id,
                        finding.detail,
                        "pass" if finding.passed else "violation",
                        evaluation_source.source_id,
                        finding.to_mapping(),
                    )
                )
                add_relation(
                    RelationRecord(
                        "evaluation_has_finding",
                        "constraint_evaluation",
                        evaluation.evaluation_id,
                        "constraint_finding",
                        finding_id,
                    )
                )
                add_relation(
                    RelationRecord(
                        "finding_reads_descriptor",
                        "constraint_finding",
                        finding_id,
                        "scalar_descriptor",
                        value_entity_ids[finding.descriptor_value_id],
                    )
                )
                target_kind = (
                    "instance" if finding.region_type is None else "semantic_region"
                )
                add_relation(
                    RelationRecord(
                        "finding_located_at",
                        "constraint_finding",
                        finding_id,
                        target_kind,
                        finding.scope_id,
                    )
                )

    if kinds_seen != {"hard", "soft", "advisory", "diagnostic"}:
        raise WorkbenchIndexError("W4 proof does not exercise every constraint kind")
    add_entity(
        EntityRecord(
            "validation",
            "w4.observation-contract-hard-gate",
            "W4 observation and engineering-constraint hard-gate proof",
            "pass",
            manifest_source.source_id,
            {
                "bundle_id": bundle.bundle_id,
                "input_sha256": bundle.input_sha256,
                "instance_ids": sorted(bundle_instances),
                "descriptor_definition_count": len(registry.definitions),
                "descriptor_value_count": total_values,
                "constraint_count": len(bundle.constraints),
                "constraint_finding_count": total_findings,
                "violation_count": total_violations,
                "constraint_kinds": sorted(kinds_seen),
                "geometry_mutation_status": "not_performed",
                "live_cst_status": "not_run",
                "rf_metric_status": "not_defined_r4",
                "physical_acceptance_status": "not_established",
            },
        )
    )


def _index_r3_induction_tail(
    *,
    family_id: str,
    grammar: FamilyGrammar,
    bundle: R3Bundle,
    alignment: Any,
    proposal: Any,
    review: Any,
    patch: Any,
    updated: FamilyGrammar,
    application: Any,
    blind_graph: InstanceBoundaryGraph,
    blind_graph_source: SourceRecord,
    blind_validation: Any,
    artifact_sources: Mapping[str, SourceRecord],
    manifest_source: SourceRecord,
    add_entity: Any,
    add_relation: Any,
) -> None:
    """Finish indexing the original W3 chain after the W4 helpers."""

    add_entity(
        EntityRecord(
            "graph_alignment",
            alignment.alignment_id,
            "SLS-2 / RF500 reviewed graph alignment",
            "pass_semantic_only",
            artifact_sources[ALIGNMENT_FILE].source_id,
            alignment.to_mapping(),
        )
    )
    for relation in (
        RelationRecord(
            "bundle_has_alignment",
            "family_induction_bundle",
            bundle.bundle_id,
            "graph_alignment",
            alignment.alignment_id,
        ),
        RelationRecord(
            "alignment_uses_algorithm",
            "graph_alignment",
            alignment.alignment_id,
            "algorithm",
            alignment.algorithm_version,
        ),
    ):
        add_relation(relation)
    for reference in alignment.graph_refs:
        add_relation(
            RelationRecord(
                "alignment_uses_training_graph",
                "graph_alignment",
                alignment.alignment_id,
                "instance_graph",
                reference.graph_id,
            )
        )

    for slot in alignment.common_backbone:
        slot_id = f"{alignment.alignment_id}:backbone:{slot.slot_index:02d}"
        add_entity(
            EntityRecord(
                "common_backbone_slot",
                slot_id,
                f"Backbone {slot.slot_index}: {slot.semantic_key}",
                "shared_all_training_instances",
                artifact_sources[ALIGNMENT_FILE].source_id,
                slot.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "alignment_has_backbone_slot",
                "graph_alignment",
                alignment.alignment_id,
                "common_backbone_slot",
                slot_id,
            )
        )
    for index, residual in enumerate(alignment.residuals):
        residual_id = f"{alignment.alignment_id}:residual:{index:02d}"
        add_entity(
            EntityRecord(
                "alignment_residual",
                residual_id,
                f"Residual {residual.side}:{residual.region_type}",
                "proposal_evidence",
                artifact_sources[ALIGNMENT_FILE].source_id,
                residual.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "alignment_has_residual",
                "graph_alignment",
                alignment.alignment_id,
                "alignment_residual",
                residual_id,
            )
        )

    add_entity(
        EntityRecord(
            "family_extension_proposal",
            proposal.proposal_id,
            "Paired optional nose-motif proposal",
            "pending_non_mutating",
            artifact_sources[bundle.proposal_file].source_id,
            proposal.to_mapping(),
        )
    )
    add_relation(
        RelationRecord(
            "proposal_from_alignment",
            "family_extension_proposal",
            proposal.proposal_id,
            "graph_alignment",
            alignment.alignment_id,
        )
    )
    add_relation(
        RelationRecord(
            "bundle_has_proposal",
            "family_induction_bundle",
            bundle.bundle_id,
            "family_extension_proposal",
            proposal.proposal_id,
        )
    )
    for instance_id in proposal.present_instance_ids:
        add_relation(
            RelationRecord(
                "proposal_motif_present_in",
                "family_extension_proposal",
                proposal.proposal_id,
                "instance",
                instance_id,
            )
        )
    for instance_id in proposal.absent_instance_ids:
        add_relation(
            RelationRecord(
                "proposal_motif_absent_in",
                "family_extension_proposal",
                proposal.proposal_id,
                "instance",
                instance_id,
            )
        )

    add_entity(
        EntityRecord(
            "proposal_review",
            review.review_id,
            f"Manual proposal review by {review.reviewer_id}",
            review.decision,
            artifact_sources[REVIEW_FILE].source_id,
            review.to_mapping(),
        )
    )
    add_relation(
        RelationRecord(
            "proposal_has_manual_review",
            "family_extension_proposal",
            proposal.proposal_id,
            "proposal_review",
            review.review_id,
        )
    )

    add_entity(
        EntityRecord(
            "grammar_patch",
            patch.patch_id,
            "Accepted-review grammar patch",
            "authorized",
            artifact_sources[PATCH_FILE].source_id,
            patch.to_mapping(),
        )
    )
    add_entity(
        EntityRecord(
            "family_grammar",
            updated.grammar_id,
            "R3 reviewed family grammar",
            "reviewed_r3",
            artifact_sources[PATCHED_GRAMMAR_FILE].source_id,
            updated.to_mapping(),
        )
    )
    add_entity(
        EntityRecord(
            "grammar_patch_application",
            application.application_id,
            "Explicit grammar patch application",
            "pass",
            artifact_sources[PATCH_APPLICATION_FILE].source_id,
            application.to_mapping(),
        )
    )
    for relation in (
        RelationRecord(
            "review_authorizes_patch",
            "proposal_review",
            review.review_id,
            "grammar_patch",
            patch.patch_id,
        ),
        RelationRecord(
            "patch_transforms_from_grammar",
            "grammar_patch",
            patch.patch_id,
            (
                "seed_grammar_ablation"
                if bundle.seed_grammar is not None
                else "family_grammar"
            ),
            grammar.grammar_id,
        ),
        RelationRecord(
            "patch_transforms_to_grammar",
            "grammar_patch",
            patch.patch_id,
            "family_grammar",
            updated.grammar_id,
        ),
        RelationRecord(
            "patch_has_application",
            "grammar_patch",
            patch.patch_id,
            "grammar_patch_application",
            application.application_id,
        ),
        RelationRecord(
            "family_has_reviewed_r3_grammar",
            "family",
            family_id,
            "family_grammar",
            updated.grammar_id,
        ),
    ):
        add_relation(relation)
    for index, difference in enumerate(application.grammar_diff):
        difference_id = f"{application.application_id}:diff:{index:02d}"
        add_entity(
            EntityRecord(
                "grammar_diff",
                difference_id,
                f"Grammar diff: {difference.path}",
                "applied",
                artifact_sources[PATCH_APPLICATION_FILE].source_id,
                difference.to_mapping(),
            )
        )
        add_relation(
            RelationRecord(
                "application_has_grammar_diff",
                "grammar_patch_application",
                application.application_id,
                "grammar_diff",
                difference_id,
            )
        )

    add_entity(
        EntityRecord(
            "blind_instance_graph",
            blind_graph.graph_id,
            "LEReC 704 MHz held-out reviewed boundary graph",
            "held_out_real_instance",
            blind_graph_source.source_id,
            blind_graph.to_mapping(),
        )
    )
    add_entity(
        EntityRecord(
            "blind_validation",
            blind_validation.validation_id,
            "LEReC 704 MHz post-induction blind validation",
            "pass",
            artifact_sources[BLIND_VALIDATION_FILE].source_id,
            blind_validation.to_mapping(),
        )
    )
    for relation in (
        RelationRecord(
            "blind_validation_uses_graph",
            "blind_validation",
            blind_validation.validation_id,
            "blind_instance_graph",
            blind_graph.graph_id,
        ),
        RelationRecord(
            "blind_validation_uses_proposal",
            "blind_validation",
            blind_validation.validation_id,
            "family_extension_proposal",
            proposal.proposal_id,
        ),
        RelationRecord(
            "blind_validation_uses_reviewed_grammar",
            "blind_validation",
            blind_validation.validation_id,
            "family_grammar",
            updated.grammar_id,
        ),
        RelationRecord(
            "bundle_has_blind_validation",
            "family_induction_bundle",
            bundle.bundle_id,
            "blind_validation",
            blind_validation.validation_id,
        ),
    ):
        add_relation(relation)

    hard_gate_payload = {
        "bundle_id": bundle.bundle_id,
        "alignment_id": alignment.alignment_id,
        "training_instance_ids": sorted(alignment.source_instance_ids),
        "backbone_slot_count": len(alignment.common_backbone),
        "residual_count": len(alignment.residuals),
        "proposal_id": proposal.proposal_id,
        "proposal_kind": proposal.proposal_kind,
        "review_id": review.review_id,
        "review_decision": review.decision,
        "patch_id": patch.patch_id,
        "patch_applied": application.applied,
        "revalidated_instance_ids": sorted(application.validated_instance_ids),
        "blind_instance_id": blind_graph.instance_id,
        "blind_classification": blind_validation.classification,
        "blind_instance_used_for_induction": False,
        "parameter_names_read": False,
        "representation_contract": blind_validation.representation_contract,
        "live_cst_status": "not_run",
    }
    proposal_mapping = proposal.to_mapping()
    if proposal_mapping.get("schema_version") == "family_extension_proposal.v1":
        hard_gate_payload.update(
            {
                "proposal_score": proposal_mapping.get("proposal_score"),
                "score_semantics": proposal_mapping.get("score_semantics"),
                "structured_support": proposal_mapping.get("support"),
                "seed_grammar_id": (
                    bundle.seed_grammar.grammar_id
                    if bundle.seed_grammar is not None
                    else None
                ),
                "pre_patch_admission": bundle.manifest.get(
                    "pre_patch_admission"
                ),
                "final_admission": bundle.manifest.get("final_admission"),
            }
        )
    else:
        hard_gate_payload["proposal_confidence"] = proposal.confidence
    add_entity(
        EntityRecord(
            "validation",
            "w3.family-induction-hard-gate",
            "W3 family-induction hard-gate proof",
            "pass",
            manifest_source.source_id,
            hard_gate_payload,
        )
    )
    add_relation(
        RelationRecord(
            "bundle_has_hard_gate_validation",
            "family_induction_bundle",
            bundle.bundle_id,
            "validation",
            "w3.family-induction-hard-gate",
        )
    )


def _assert_contract_ref(
    reference: ContractSourceRef,
    *,
    expected_kind: str,
    expected_schema: str,
    expected_object_id: str,
    expected_canonical_sha256: str,
    expected_source: SourceRecord,
    label: str,
) -> None:
    actual = (
        reference.contract_kind,
        reference.schema_version,
        reference.object_id,
        reference.canonical_sha256,
        reference.source.source_kind,
        reference.source.source_path,
        reference.source.source_raw_sha256,
        reference.source.locator,
        reference.source.relation,
    )
    expected = (
        expected_kind,
        expected_schema,
        expected_object_id,
        expected_canonical_sha256,
        expected_kind,
        expected_source.display_path,
        expected_source.raw_sha256,
        "#/",
        "compile_input_contract",
    )
    if actual != expected:
        raise WorkbenchIndexError(f"W2 {label} contract/source binding mismatch")


def _compile_bundle_root(record_path: Path, repo_root: Path) -> Path:
    resolved = record_path.resolve()
    if resolved.parent.name != "records":
        raise WorkbenchIndexError(
            "W2 compile records must be supplied from an immutable bundle records/ directory"
        )
    bundle_root = resolved.parent.parent.resolve()
    try:
        bundle_root.relative_to(repo_root)
    except ValueError as exc:
        raise WorkbenchIndexError(
            "W2 compile bundle must be inside the declared repository root"
        ) from exc
    return bundle_root


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


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkbenchIndexError(f"{label} must be an object")
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
