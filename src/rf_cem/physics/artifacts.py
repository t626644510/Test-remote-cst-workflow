"""Deterministic no-CST R5 readiness proof and strict replay loader."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from rf_cem.compiler import CompileRecord, load_compile_record
from rf_cem.observation import R4Bundle, load_r4_bundle
from rf_cem.semantic.adapters import RF500_INSTANCE_ID, SLS2_INSTANCE_ID
from rf_cem.semantic.contracts import (
    InstanceBoundaryGraph,
    canonical_json_bytes,
    canonical_sha256,
    canonicalization_contract,
    file_sha256,
    load_instance_boundary_graph,
)

from .cases import PhysicsCase, PhysicsLinkStatus, ResultProvenance
from .common import (
    PhysicsContractError,
    exact_keys,
    mapping,
    normalized_hash,
    read_json_mapping,
    resolve_inside,
    sequence,
    string,
)
from .comparability import ComparabilityAssessment, assess_comparability
from .convergence import MeshConvergence
from .fields import FieldBundle
from .metrics import (
    REQUIRED_METRIC_KEYS,
    MetricContract,
    MetricObservation,
    build_initial_metric_contracts,
)
from .modes import ModeFingerprint, ModeIdentity
from .references import (
    BoundaryAssignment,
    ContractRef,
    GeometryBinding,
    MaterialAssignment,
    MeshDefinition,
    SolverDefinition,
)


R5_BUNDLE_SCHEMA_VERSION = "r5_rf_result_readiness_bundle.v0"
R5_MANIFEST_SCHEMA_VERSION = "r5_rf_result_source_binding_manifest.v0"
R5_BUNDLE_PREFIX = "r5_rf_result_readiness"
MANIFEST_FILE = "source_binding_manifest.v0.json"
READINESS_VALIDATION_MODE = "no_cst_readiness_only"
READINESS_STATUS = "readiness_contracts_established_live_evidence_pending"
READINESS_REQUIRED_CONTRACTS = (
    "physics_case.v0",
    "mode_identity.v0",
    "mode_fingerprint.v0",
    "metric_contract.v0",
    "metric_observation.v0",
    "field_bundle.v0",
    "mesh_convergence.v0",
    "result_provenance.v0",
)
READINESS_CHECKS = (
    "all planned RF500 objects bind R1 graph, R2 compile record, and R4 exact geometry",
    "Q-Factor (Perturbation) remains Q perturbation and is not claimed as Q0",
    "normalization and mode requirements are explicit for all nine metrics",
    "field contract permits only external hash-bound artifacts",
    "planned mesh levels remain not comparable until results and mode fingerprints exist",
    "SLS-2 remains explicitly not_linked",
)
READINESS_EXCLUSIONS = (
    "no CST process was started",
    "no RF value was copied from historical prose",
    "no physical acceptance is established",
    "no multiphysics, HOM, wake, port, coupler, or optimization campaign",
)
PLANNED_MESH_LEVELS = ("coarse", "nominal", "fine")


@dataclass(frozen=True)
class R5ReadinessSourceSet:
    """Explicit R4 and maintained-source inputs for an R5 readiness proof."""

    repo_root: Path
    r4_bundle: Path
    architecture_document: Path = Path("docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md")
    interface_document: Path = Path("docs/CST_AUTOMATION_INTERFACES.md")
    goal_document: Path = Path(".agent/goals/RF-CEM_Codex_Goal_R0B-R5.md")


@dataclass(frozen=True)
class R5CaseArtifacts:
    """All case-scoped planned or captured R5 objects."""

    physics_case: PhysicsCase
    provenance: ResultProvenance
    mode_fingerprint: ModeFingerprint
    mode_identity: ModeIdentity
    metric_observations: tuple[MetricObservation, ...]
    field_bundle: FieldBundle


@dataclass(frozen=True)
class R5Bundle:
    """Strictly loaded R5 readiness bundle with cross-links checked."""

    path: Path
    bundle_id: str
    input_sha256: str
    links: tuple[PhysicsLinkStatus, ...]
    metric_contracts: tuple[MetricContract, ...]
    cases: tuple[R5CaseArtifacts, ...]
    convergence: tuple[MeshConvergence, ...]
    comparability: tuple[ComparabilityAssessment, ...]
    manifest: Mapping[str, Any]


def write_r5_readiness_bundle(
    sources: R5ReadinessSourceSet,
    output_root: Path,
) -> R5Bundle:
    """Write an immutable planned/not-established proof without invoking CST."""

    root = sources.repo_root.resolve()
    if not root.is_dir():
        raise PhysicsContractError("repository root is missing")
    r4_path = _inside(root, sources.r4_bundle, "R4 bundle")
    roadmap = _inside(root, sources.architecture_document, "architecture document")
    interface_doc = _inside(root, sources.interface_document, "CST interface document")
    goal_doc = _inside(root, sources.goal_document, "R0B-R5 goal document")
    r4 = load_r4_bundle(r4_path, repo_root=root)
    records, graphs, record_paths, graph_paths = _load_r4_identity_chain(root, r4)
    geometry_by_instance = _geometry_bindings(r4, records, graphs)
    rf_geometry = geometry_by_instance[RF500_INSTANCE_ID]
    sls2_geometry = geometry_by_instance[SLS2_INSTANCE_ID]

    metrics = build_initial_metric_contracts()
    cases = tuple(
        _build_planned_case(rf_geometry, level, ordinal, metrics)
        for ordinal, level in enumerate(PLANNED_MESH_LEVELS, start=1)
    )
    links = (
        PhysicsLinkStatus(
            geometry=rf_geometry,
            link_status="planned_not_run",
            physics_case_refs=tuple(item.physics_case.identity_ref() for item in cases),
            reason=(
                "Three bounded mesh levels are planned; CST execution requires explicit "
                "user authorization and has not occurred."
            ),
        ),
        PhysicsLinkStatus(
            geometry=sls2_geometry,
            link_status="not_linked",
            physics_case_refs=(),
            reason="No materialized live-CST SLS-2 RF evidence exists in this repository.",
        ),
    )
    eigenfrequency = next(item for item in metrics if item.metric_key == "eigenfrequency")
    convergence = (
        MeshConvergence(
            geometry=rf_geometry,
            metric_contract_ref=eigenfrequency.identity_ref(),
            convergence_status="not_established",
            relative_tolerance=1.0e-4,
            samples=(),
            relative_changes=(),
            assessment=(
                "Planned coarse/nominal/fine levels have no solver observations; "
                "convergence is not established."
            ),
        ),
    )
    comparisons = _planned_comparisons(cases, eigenfrequency)

    implementation_root = Path(__file__).resolve().parent
    implementation_sources = tuple(sorted(implementation_root.glob("*.py"), key=str))
    live_locator_source = root / "src/rf_cem/live_500mhz_postprocessing_diagnostic.py"
    input_sources = tuple(
        sorted(
            {
                r4_path / MANIFEST_FILE,
                roadmap,
                interface_doc,
                goal_doc,
                live_locator_source,
                *record_paths,
                *graph_paths,
                *implementation_sources,
            },
            key=str,
        )
    )
    source_identities = tuple(_source_identity(root, path) for path in input_sources)
    preimage = {
        "schema_version": R5_BUNDLE_SCHEMA_VERSION,
        "canonicalization_contract": canonicalization_contract(),
        "sources": list(source_identities),
        "r4_bundle_id": r4.bundle_id,
        "r4_input_sha256": r4.input_sha256,
        "geometry_bindings": [
            geometry_by_instance[key].to_mapping() for key in sorted(geometry_by_instance)
        ],
        "metric_contract_sha256": [item.content_sha256 for item in metrics],
        "planned_case_sha256": [item.physics_case.content_sha256 for item in cases],
        "validation_mode": READINESS_VALIDATION_MODE,
    }
    input_sha256 = canonical_sha256(preimage)
    bundle_id = f"{R5_BUNDLE_PREFIX}.{input_sha256[:16]}"
    output = output_root if output_root.is_absolute() else root / output_root
    resolved_output = output.resolve()
    try:
        resolved_output.relative_to(root)
    except ValueError as exc:
        raise PhysicsContractError("R5 output must remain inside repository") from exc
    resolved_output.mkdir(parents=True, exist_ok=True)
    target = resolved_output / bundle_id
    if target.exists():
        raise FileExistsError(f"R5 readiness bundle already exists: {target}")
    before = {path: file_sha256(path) for path in input_sources}
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=resolved_output))
    try:
        artifacts: list[dict[str, Any]] = []
        for metric in metrics:
            _write_contract(
                temporary,
                f"metric_contracts/{metric.metric_key}.metric_contract.v0.json",
                metric.to_mapping(),
                artifacts,
            )
        for link in links:
            _write_contract(
                temporary,
                f"links/{link.geometry.instance_id}.physics_link_status.v0.json",
                link.to_mapping(),
                artifacts,
            )
        for case in cases:
            case_root = f"cases/{case.physics_case.physics_case_id}"
            _write_contract(
                temporary,
                f"{case_root}/physics_case.v0.json",
                case.physics_case.to_mapping(),
                artifacts,
            )
            _write_contract(
                temporary,
                f"{case_root}/result_provenance.v0.json",
                case.provenance.to_mapping(),
                artifacts,
            )
            _write_contract(
                temporary,
                f"{case_root}/mode_fingerprint.v0.json",
                case.mode_fingerprint.to_mapping(),
                artifacts,
            )
            _write_contract(
                temporary,
                f"{case_root}/mode_identity.v0.json",
                case.mode_identity.to_mapping(),
                artifacts,
            )
            _write_contract(
                temporary,
                f"{case_root}/field_bundle.v0.json",
                case.field_bundle.to_mapping(),
                artifacts,
            )
            for metric, observation in zip(metrics, case.metric_observations):
                _write_contract(
                    temporary,
                    f"{case_root}/metrics/{metric.metric_key}.metric_observation.v0.json",
                    observation.to_mapping(),
                    artifacts,
                )
        for item in convergence:
            _write_contract(
                temporary,
                f"convergence/{item.convergence_id}.json",
                item.to_mapping(),
                artifacts,
            )
        for item in comparisons:
            _write_contract(
                temporary,
                f"comparability/{item.assessment_id}.json",
                item.to_mapping(),
                artifacts,
            )
        manifest = _manifest_mapping(
            bundle_id=bundle_id,
            input_sha256=input_sha256,
            sources=source_identities,
            artifacts=tuple(sorted(artifacts, key=lambda item: str(item["path"]))),
            r4=r4,
            links=links,
            metrics=metrics,
            cases=cases,
            convergence=convergence,
            comparisons=comparisons,
        )
        _write_json(temporary / MANIFEST_FILE, manifest)
        if {path: file_sha256(path) for path in input_sources} != before:
            raise PhysicsContractError("R5 readiness build mutated or raced an input source")
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return load_r5_bundle(target, repo_root=root)


def load_r5_bundle(path: Path, *, repo_root: Path | None = None) -> R5Bundle:
    """Strictly validate and replay one R5 readiness proof directory."""

    bundle_path = path.resolve()
    root = (repo_root or _discover_repo_root(bundle_path)).resolve()
    try:
        bundle_path.relative_to(root)
    except ValueError as exc:
        raise PhysicsContractError("R5 bundle must remain inside repository") from exc
    manifest = read_json_mapping(bundle_path / MANIFEST_FILE, "R5 manifest")
    _validate_manifest_header(bundle_path, manifest)
    _validate_sources(root, manifest)
    _validate_r4_binding(root, manifest)
    artifact_mappings = _validate_artifacts(bundle_path, manifest)

    links: list[PhysicsLinkStatus] = []
    metrics: list[MetricContract] = []
    cases: list[PhysicsCase] = []
    provenances: list[ResultProvenance] = []
    fingerprints: list[ModeFingerprint] = []
    modes: list[ModeIdentity] = []
    observations: list[MetricObservation] = []
    fields: list[FieldBundle] = []
    convergence: list[MeshConvergence] = []
    comparisons: list[ComparabilityAssessment] = []
    dispatch = {
        "physics_link_status.v0": (PhysicsLinkStatus, links),
        "metric_contract.v0": (MetricContract, metrics),
        "physics_case.v0": (PhysicsCase, cases),
        "result_provenance.v0": (ResultProvenance, provenances),
        "mode_fingerprint.v0": (ModeFingerprint, fingerprints),
        "mode_identity.v0": (ModeIdentity, modes),
        "metric_observation.v0": (MetricObservation, observations),
        "field_bundle.v0": (FieldBundle, fields),
        "mesh_convergence.v0": (MeshConvergence, convergence),
        "result_comparability.v0": (ComparabilityAssessment, comparisons),
    }
    for artifact in artifact_mappings:
        schema = string(artifact["schema_version"], "artifact.schema_version")
        if schema not in dispatch:
            raise PhysicsContractError(f"unsupported R5 artifact schema: {schema}")
        cls, destination = dispatch[schema]
        payload = read_json_mapping(
            resolve_inside(bundle_path, str(artifact["path"]), "artifact.path"),
            schema,
        )
        destination.append(cls.from_mapping(payload))

    case_artifacts = _assemble_cases(
        cases, provenances, fingerprints, modes, observations, fields, metrics
    )
    bundle = R5Bundle(
        path=bundle_path,
        bundle_id=string(manifest["bundle_id"], "manifest.bundle_id"),
        input_sha256=normalized_hash(manifest["input_sha256"], "manifest.input_sha256"),
        links=tuple(sorted(links, key=lambda item: item.geometry.instance_id)),
        metric_contracts=tuple(sorted(metrics, key=lambda item: REQUIRED_METRIC_KEYS.index(item.metric_key))),
        cases=tuple(
            sorted(
                case_artifacts,
                key=lambda item: int(
                    item.physics_case.mesh.control_parameters.get("ordinal", 0)
                ),
            )
        ),
        convergence=tuple(convergence),
        comparability=tuple(sorted(comparisons, key=lambda item: item.assessment_id)),
        manifest=manifest,
    )
    _validate_bundle_cross_links(bundle, root)
    _validate_input_identity(bundle)
    return bundle


def _build_planned_case(
    geometry: GeometryBinding,
    level: str,
    ordinal: int,
    metrics: tuple[MetricContract, ...],
) -> R5CaseArtifacts:
    solver = SolverDefinition(
        product="CST Studio Suite",
        version="2026",
        build=None,
        solver_name="Solver_HF_TET_E",
        interface="repository-verified cst.interface wrappers via cst_optimization",
        settings_status="repository_verified",
    )
    case = PhysicsCase(
        geometry=geometry,
        solver=solver,
        solver_recipe="RF500 tetrahedral eigenmode diagnostic recipe; exact live recipe capture pending",
        materials=(
            MaterialAssignment(
                role="conducting_background",
                selection="cavity background",
                material_name="Copper (annealed)",
                conductivity_s_per_m=5.8e7,
                settings_status="repository_verified",
            ),
            MaterialAssignment(
                role="rf_vacuum",
                selection="RFVacuumVolume",
                material_name="Vacuum",
                conductivity_s_per_m=None,
                settings_status="repository_verified",
            ),
        ),
        boundaries=(
            BoundaryAssignment(
                selection="global cavity boundary template",
                condition="not_materialized_in_current_clone",
                settings_status="not_established",
            ),
        ),
        mesh=MeshDefinition(
            mesh_id=f"rf500.tetrahedral.planned_{ordinal:02d}_{level}",
            level=level,
            strategy="tetrahedral_eigenmode_planned_refinement",
            control_parameters={
                "ordinal": ordinal,
                "refinement_role": level,
                "numeric_controls": "not_established_until_bounded_live_plan",
            },
            settings_status="planned",
        ),
        requested_mode_count=1,
        case_status="planned_not_run",
        authorization_status="not_requested",
        limitations=(
            "No CST execution was authorized or performed.",
            "Exact boundary values, CST build, and numeric mesh controls are not established.",
            "This object is readiness evidence, not an RF result or physical acceptance.",
        ),
    )
    provenance = ResultProvenance(
        geometry=geometry,
        physics_case_ref=case.identity_ref(),
        solver=solver,
        run_status="not_run",
        authorization_status="not_requested",
        execution_id=f"planned:{case.physics_case_id}",
        started_at=None,
        completed_at=None,
        extraction_software="rf_cem.physics readiness contract only",
        source_artifacts=(),
        log_artifacts=(),
        replay_command="not_available_until_authorized_live_capture",
        limitations=("No replayable CST project/result artifact exists for this planned case.",),
    )
    fingerprint = ModeFingerprint(
        geometry=geometry,
        physics_case_ref=case.identity_ref(),
        fingerprint_status="not_established",
        frequency_mhz=None,
        r_over_q_ohm=None,
        symmetry_signature=(),
        field_signature_artifacts=(),
        fingerprint_method="not_established; bare mode index is insufficient",
    )
    mode = ModeIdentity(
        geometry=geometry,
        physics_case_ref=case.identity_ref(),
        fingerprint_ref=fingerprint.identity_ref(),
        mode_family="accelerating_monopole_candidate",
        mode_role="fundamental_accelerating_mode_candidate",
        solver_result_locator="not_established",
        solver_mode_index=None,
        determination_status="not_established",
        determination_method="requires frequency + R/Q + field/symmetry fingerprint",
    )
    metric_observations = tuple(
        MetricObservation(
            geometry=geometry,
            physics_case_ref=case.identity_ref(),
            mode_identity_ref=mode.identity_ref(),
            metric_contract_ref=metric.identity_ref(),
            provenance_ref=provenance.identity_ref(),
            result_locator=(
                metric.result_locator_template.format(mode_index=1)
                if metric.extraction_support != "not_established"
                else "not_established"
            ),
            unit=metric.unit,
            extraction_method=metric.extraction_method,
            normalization=metric.normalization,
            value=None,
            validation_status="not_established",
            validation_messages=(
                "No authorized live-CST result is materialized for this case.",
                "A verified locator does not establish a scalar value or mode identity.",
            ),
        )
        for metric in metrics
    )
    field = FieldBundle(
        geometry=geometry,
        physics_case_ref=case.identity_ref(),
        mode_identity_ref=mode.identity_ref(),
        provenance_ref=provenance.identity_ref(),
        field_status="not_established",
        coordinate_system="not_established",
        normalization="not_established",
        components=(),
        artifacts=(),
        extraction_method="not_established",
    )
    return R5CaseArtifacts(case, provenance, fingerprint, mode, metric_observations, field)


def _planned_comparisons(
    cases: tuple[R5CaseArtifacts, ...],
    eigenfrequency: MetricContract,
) -> tuple[ComparabilityAssessment, ...]:
    comparisons: list[ComparabilityAssessment] = []
    for left, right in zip(cases, cases[1:]):
        left_obs = next(
            item
            for item in left.metric_observations
            if item.metric_contract_ref == eigenfrequency.identity_ref()
        )
        right_obs = next(
            item
            for item in right.metric_observations
            if item.metric_contract_ref == eigenfrequency.identity_ref()
        )
        comparisons.append(
            assess_comparability(
                left_observation=left_obs,
                right_observation=right_obs,
                left_case=left.physics_case,
                right_case=right.physics_case,
                left_mode=left.mode_identity,
                right_mode=right.mode_identity,
                left_fingerprint=left.mode_fingerprint,
                right_fingerprint=right.mode_fingerprint,
                left_metric=eigenfrequency,
                right_metric=eigenfrequency,
                comparison_purpose="mesh_convergence",
            )
        )
    return tuple(comparisons)


def _load_r4_identity_chain(
    root: Path, r4: R4Bundle
) -> tuple[
    tuple[CompileRecord, ...],
    tuple[InstanceBoundaryGraph, ...],
    tuple[Path, ...],
    tuple[Path, ...],
]:
    sources = [mapping(item, "R4 source") for item in sequence(r4.manifest["sources"], "R4 sources")]
    record_paths = tuple(
        sorted(
            (
                resolve_inside(root, str(item["path"]), "R4 compile source")
                for item in sources
                if str(item["path"]).endswith(".compile_record.v0.json")
            ),
            key=str,
        )
    )
    graph_paths = tuple(
        sorted(
            (
                resolve_inside(root, str(item["path"]), "R4 graph source")
                for item in sources
                if str(item["path"]).endswith(".instance_boundary_graph.v0.json")
            ),
            key=str,
        )
    )
    if len(record_paths) != 2 or len(graph_paths) != 2:
        raise PhysicsContractError("R5 requires both R4-bound compile records and graphs")
    return (
        tuple(load_compile_record(path) for path in record_paths),
        tuple(load_instance_boundary_graph(path) for path in graph_paths),
        record_paths,
        graph_paths,
    )


def _geometry_bindings(
    r4: R4Bundle,
    records: tuple[CompileRecord, ...],
    graphs: tuple[InstanceBoundaryGraph, ...],
) -> dict[str, GeometryBinding]:
    record_by_instance = {item.instance_id: item for item in records}
    graph_by_instance = {item.instance_id: item for item in graphs}
    exact_by_instance = {item.exact_geometry.instance_id: item.exact_geometry for item in r4.instances}
    required = {RF500_INSTANCE_ID, SLS2_INSTANCE_ID}
    if set(record_by_instance) != required or set(graph_by_instance) != required or set(exact_by_instance) != required:
        raise PhysicsContractError("R5 geometry chain must cover canonical RF500 and SLS-2")
    result: dict[str, GeometryBinding] = {}
    for instance_id in sorted(required):
        record = record_by_instance[instance_id]
        graph = graph_by_instance[instance_id]
        exact = exact_by_instance[instance_id]
        if exact.compile_id != record.compile_id or exact.compile_content_sha256 != record.content_sha256:
            raise PhysicsContractError("R4 exact geometry does not match R2 compile record")
        result[instance_id] = GeometryBinding(
            family_id=record.family_id,
            instance_id=instance_id,
            instance_graph_ref=ContractRef(
                "instance_boundary_graph",
                "instance_boundary_graph.v0",
                graph.graph_id,
                canonical_sha256(graph.to_mapping()),
            ),
            compile_record_ref=ContractRef(
                "compile_record",
                "compile_record.v0",
                record.compile_id,
                record.content_sha256,
            ),
            exact_geometry_ref=ContractRef(
                "exact_geometry_reference",
                "exact_geometry_reference.v0",
                exact.exact_geometry_id,
                exact.content_sha256,
            ),
        )
    return result


def _assemble_cases(
    cases: list[PhysicsCase],
    provenances: list[ResultProvenance],
    fingerprints: list[ModeFingerprint],
    modes: list[ModeIdentity],
    observations: list[MetricObservation],
    fields: list[FieldBundle],
    metrics: list[MetricContract],
) -> tuple[R5CaseArtifacts, ...]:
    metric_refs = {item.identity_ref() for item in metrics}
    if len(metric_refs) != len(metrics):
        raise PhysicsContractError("R5 metric contracts must have unique identities")
    case_refs = [item.identity_ref() for item in cases]
    if len(case_refs) != len(set(case_refs)):
        raise PhysicsContractError("R5 physics cases must have unique identities")
    expected_case_refs = set(case_refs)
    case_scoped_collections = (
        ("result provenance", provenances),
        ("mode fingerprint", fingerprints),
        ("mode identity", modes),
        ("field bundle", fields),
    )
    for label, values in case_scoped_collections:
        references = [item.physics_case_ref for item in values]
        if len(values) != len(cases) or set(references) != expected_case_refs:
            raise PhysicsContractError(
                f"R5 {label} inventory has duplicate, missing, or orphan case bindings"
            )
    if len(observations) != len(cases) * len(metrics) or any(
        item.physics_case_ref not in expected_case_refs for item in observations
    ):
        raise PhysicsContractError(
            "R5 metric observation inventory has duplicate, missing, or orphan case bindings"
        )
    result: list[R5CaseArtifacts] = []
    for case in cases:
        reference = case.identity_ref()
        provenance = _one(
            [item for item in provenances if item.physics_case_ref == reference],
            "result provenance",
        )
        fingerprint = _one(
            [item for item in fingerprints if item.physics_case_ref == reference],
            "mode fingerprint",
        )
        mode = _one([item for item in modes if item.physics_case_ref == reference], "mode identity")
        field = _one([item for item in fields if item.physics_case_ref == reference], "field bundle")
        scoped = tuple(
            sorted(
                (item for item in observations if item.physics_case_ref == reference),
                key=lambda item: item.metric_contract_ref.object_id,
            )
        )
        if len(scoped) != len(metrics) or {
            item.metric_contract_ref for item in scoped
        } != metric_refs:
            raise PhysicsContractError("each R5 case requires all nine metric observations")
        result.append(R5CaseArtifacts(case, provenance, fingerprint, mode, scoped, field))
    return tuple(result)


def _validate_bundle_cross_links(bundle: R5Bundle, root: Path) -> None:
    if bundle.manifest.get("validation_mode") != READINESS_VALIDATION_MODE:
        raise PhysicsContractError("R5 readiness manifest validation mode is invalid")
    if bundle.manifest.get("status") != READINESS_STATUS:
        raise PhysicsContractError("R5 readiness manifest status is invalid")
    if bundle.manifest.get("live_cst_status") != "not_run":
        raise PhysicsContractError("readiness bundle cannot claim live-CST execution")
    if bundle.manifest.get("live_cst_authorization") != "not_requested":
        raise PhysicsContractError(
            "readiness bundle cannot claim live-CST authorization"
        )
    if bundle.manifest.get("physical_acceptance_status") != "not_established":
        raise PhysicsContractError(
            "readiness bundle cannot claim physical acceptance"
        )
    required_contracts = tuple(
        string(item, "manifest.required_contracts[]")
        for item in sequence(
            bundle.manifest["required_contracts"], "manifest.required_contracts"
        )
    )
    if required_contracts != READINESS_REQUIRED_CONTRACTS:
        raise PhysicsContractError("R5 required-contract inventory is invalid")
    checks = tuple(
        string(item, "manifest.checks[]")
        for item in sequence(bundle.manifest["checks"], "manifest.checks")
    )
    if checks != READINESS_CHECKS:
        raise PhysicsContractError("R5 readiness checks are incomplete or changed")
    exclusions = tuple(
        string(item, "manifest.exclusions[]")
        for item in sequence(bundle.manifest["exclusions"], "manifest.exclusions")
    )
    if exclusions != READINESS_EXCLUSIONS:
        raise PhysicsContractError("R5 readiness exclusions are incomplete or changed")
    if tuple(item.metric_key for item in bundle.metric_contracts) != REQUIRED_METRIC_KEYS:
        raise PhysicsContractError("R5 readiness bundle must define exactly nine initial metrics")
    if len(bundle.links) != 2 or len(
        {item.geometry.instance_id for item in bundle.links}
    ) != 2:
        raise PhysicsContractError("R5 readiness requires exactly two unique instance links")
    link_status = {item.geometry.instance_id: item.link_status for item in bundle.links}
    if link_status != {
        RF500_INSTANCE_ID: "planned_not_run",
        SLS2_INSTANCE_ID: "not_linked",
    }:
        raise PhysicsContractError("R5 readiness instance-link statuses are invalid")
    if len(bundle.cases) != 3:
        raise PhysicsContractError("R5 readiness requires three planned RF500 mesh levels")
    mesh_levels = tuple(item.physics_case.mesh.level for item in bundle.cases)
    mesh_ids = tuple(item.physics_case.mesh.mesh_id for item in bundle.cases)
    ordinals = tuple(
        item.physics_case.mesh.control_parameters.get("ordinal") for item in bundle.cases
    )
    if (
        mesh_levels != PLANNED_MESH_LEVELS
        or len(set(mesh_ids)) != len(mesh_ids)
        or ordinals != (1, 2, 3)
    ):
        raise PhysicsContractError(
            "R5 readiness mesh cases must be unique ordered coarse/nominal/fine levels"
        )
    case_refs = {item.physics_case.identity_ref() for item in bundle.cases}
    if len(case_refs) != len(bundle.cases):
        raise PhysicsContractError("R5 readiness physics-case identities are duplicated")
    metric_by_ref = {item.identity_ref(): item for item in bundle.metric_contracts}
    all_observation_refs = {
        observation.identity_ref()
        for item in bundle.cases
        for observation in item.metric_observations
    }
    rf_link = next(item for item in bundle.links if item.geometry.instance_id == RF500_INSTANCE_ID)
    if set(rf_link.physics_case_refs) != case_refs:
        raise PhysicsContractError("RF500 physics link does not cover planned cases")
    for item in bundle.cases:
        case = item.physics_case
        if case.geometry.instance_id != RF500_INSTANCE_ID or case.case_status != "planned_not_run":
            raise PhysicsContractError("readiness bundle contains a non-planned RF500 case")
        if case.authorization_status != "not_requested":
            raise PhysicsContractError("readiness physics case cannot claim authorization")
        if item.provenance.run_status != "not_run":
            raise PhysicsContractError("readiness provenance must remain not_run")
        if item.provenance.authorization_status != "not_requested":
            raise PhysicsContractError("readiness provenance cannot claim authorization")
        if item.provenance.physics_case_ref != case.identity_ref():
            raise PhysicsContractError("provenance/case cross-link mismatch")
        if item.provenance.geometry != case.geometry or item.provenance.solver != case.solver:
            raise PhysicsContractError("provenance setup differs from its physics case")
        if item.mode_fingerprint.fingerprint_status != "not_established":
            raise PhysicsContractError("readiness mode fingerprint must remain not_established")
        if (
            item.mode_fingerprint.geometry != case.geometry
            or item.mode_fingerprint.physics_case_ref != case.identity_ref()
        ):
            raise PhysicsContractError("mode fingerprint differs from its physics case")
        if item.mode_identity.determination_status != "not_established":
            raise PhysicsContractError("readiness mode identity must remain not_established")
        if (
            item.mode_identity.geometry != case.geometry
            or item.mode_identity.physics_case_ref != case.identity_ref()
        ):
            raise PhysicsContractError("mode identity differs from its physics case")
        if item.mode_identity.fingerprint_ref != item.mode_fingerprint.identity_ref():
            raise PhysicsContractError("mode identity/fingerprint cross-link mismatch")
        if item.field_bundle.field_status != "not_established":
            raise PhysicsContractError("readiness field bundle must remain not_established")
        if (
            item.field_bundle.geometry != case.geometry
            or item.field_bundle.physics_case_ref != case.identity_ref()
            or item.field_bundle.provenance_ref != item.provenance.identity_ref()
        ):
            raise PhysicsContractError("field bundle setup cross-link mismatch")
        if item.field_bundle.mode_identity_ref != item.mode_identity.identity_ref():
            raise PhysicsContractError("field/mode cross-link mismatch")
        for observation in item.metric_observations:
            if observation.validation_status != "not_established" or observation.value is not None:
                raise PhysicsContractError("readiness metric cannot contain an RF value")
            if observation.mode_identity_ref != item.mode_identity.identity_ref():
                raise PhysicsContractError("metric/mode cross-link mismatch")
            if observation.provenance_ref != item.provenance.identity_ref():
                raise PhysicsContractError("metric/provenance cross-link mismatch")
            if observation.geometry != case.geometry or observation.physics_case_ref != case.identity_ref():
                raise PhysicsContractError("metric/case geometry cross-link mismatch")
            metric = metric_by_ref[observation.metric_contract_ref]
            if (
                observation.unit != metric.unit
                or observation.extraction_method != metric.extraction_method
                or observation.normalization != metric.normalization
            ):
                raise PhysicsContractError(
                    "metric observation unit/method/normalization differs from its contract"
                )
            if (
                observation.validation_status in {"extracted", "replayed"}
                and metric.extraction_support == "not_established"
            ):
                raise PhysicsContractError(
                    "unsupported metric contract cannot produce an established observation"
                )
        for artifact in (*item.provenance.source_artifacts, *item.provenance.log_artifacts):
            artifact.validate_file(root)
        for artifact in item.mode_fingerprint.field_signature_artifacts:
            artifact.validate_file(root)
        item.field_bundle.validate_external_artifacts(root)
    if len(bundle.convergence) != 1 or bundle.convergence[0].convergence_status != "not_established":
        raise PhysicsContractError("readiness mesh convergence must be explicitly not established")
    for convergence in bundle.convergence:
        if convergence.geometry != bundle.cases[0].physics_case.geometry:
            raise PhysicsContractError("mesh convergence geometry binding mismatch")
        metric = metric_by_ref.get(convergence.metric_contract_ref)
        if metric is None or metric.metric_key != "eigenfrequency":
            raise PhysicsContractError("mesh convergence metric contract is missing")
    if len(bundle.comparability) != 2 or any(
        item.decision != "not_comparable" for item in bundle.comparability
    ):
        raise PhysicsContractError("readiness comparisons must default to not_comparable")
    for assessment in bundle.comparability:
        if (
            assessment.left_observation_ref not in all_observation_refs
            or assessment.right_observation_ref not in all_observation_refs
        ):
            raise PhysicsContractError("comparability observation reference is missing")
    eigenfrequency = next(
        item for item in bundle.metric_contracts if item.metric_key == "eigenfrequency"
    )
    expected_comparisons = tuple(
        sorted(
            _planned_comparisons(bundle.cases, eigenfrequency),
            key=lambda item: item.assessment_id,
        )
    )
    if tuple(item.to_mapping() for item in bundle.comparability) != tuple(
        item.to_mapping() for item in expected_comparisons
    ):
        raise PhysicsContractError("R5 readiness comparability decisions do not replay")
    expected_instance_links = [
        {
            "instance_id": item.geometry.instance_id,
            "link_id": item.link_id,
            "link_status": item.link_status,
        }
        for item in bundle.links
    ]
    actual_instance_links = [
        dict(mapping(item, "manifest.instance_links[]"))
        for item in sequence(
            bundle.manifest["instance_links"], "manifest.instance_links"
        )
    ]
    if actual_instance_links != expected_instance_links:
        raise PhysicsContractError("R5 manifest instance links do not replay")
    summary = mapping(bundle.manifest["summary"], "manifest.summary")
    expected = {
        "case_count": len(bundle.cases),
        "comparability_count": len(bundle.comparability),
        "convergence_count": len(bundle.convergence),
        "field_bundle_count": len(bundle.cases),
        "metric_contract_count": len(bundle.metric_contracts),
        "metric_observation_count": sum(len(item.metric_observations) for item in bundle.cases),
        "mode_fingerprint_count": len(bundle.cases),
        "mode_identity_count": len(bundle.cases),
        "result_provenance_count": len(bundle.cases),
    }
    if dict(summary) != expected:
        raise PhysicsContractError("R5 manifest summary does not match loaded contracts")


def _validate_input_identity(bundle: R5Bundle) -> None:
    """Recompute the content-address preimage used to name the readiness bundle."""

    r4_binding = mapping(bundle.manifest["r4_binding"], "manifest.r4_binding")
    geometry_by_instance = {
        item.geometry.instance_id: item.geometry for item in bundle.links
    }
    preimage = {
        "schema_version": R5_BUNDLE_SCHEMA_VERSION,
        "canonicalization_contract": canonicalization_contract(),
        "sources": list(sequence(bundle.manifest["sources"], "manifest.sources")),
        "r4_bundle_id": r4_binding["bundle_id"],
        "r4_input_sha256": r4_binding["input_sha256"],
        "geometry_bindings": [
            geometry_by_instance[key].to_mapping() for key in sorted(geometry_by_instance)
        ],
        "metric_contract_sha256": [
            item.content_sha256 for item in bundle.metric_contracts
        ],
        "planned_case_sha256": [
            item.physics_case.content_sha256 for item in bundle.cases
        ],
        "validation_mode": READINESS_VALIDATION_MODE,
    }
    actual = canonical_sha256(preimage)
    if actual != bundle.input_sha256:
        raise PhysicsContractError("R5 input SHA-256 preimage does not replay")


def _validate_r4_binding(root: Path, manifest: Mapping[str, Any]) -> None:
    """Replay the complete R4 bundle referenced by the R5 source inventory."""

    binding = mapping(manifest["r4_binding"], "manifest.r4_binding")
    exact_keys(binding, {"bundle_id", "input_sha256"}, "manifest.r4_binding")
    bundle_id = string(binding["bundle_id"], "manifest.r4_binding.bundle_id")
    input_sha = normalized_hash(
        binding["input_sha256"], "manifest.r4_binding.input_sha256"
    )
    candidates = []
    for raw in sequence(manifest["sources"], "manifest.sources"):
        source = mapping(raw, "source")
        relative = str(source.get("path") or "")
        if relative.endswith(f"/{bundle_id}/{MANIFEST_FILE}"):
            candidates.append(resolve_inside(root, relative, "R4 manifest source").parent)
    if len(candidates) != 1:
        raise PhysicsContractError("R5 manifest must bind exactly one complete R4 bundle")
    r4 = load_r4_bundle(candidates[0], repo_root=root)
    if r4.bundle_id != bundle_id or r4.input_sha256 != input_sha:
        raise PhysicsContractError("R5/R4 bundle identity mismatch")


def _manifest_mapping(
    *,
    bundle_id: str,
    input_sha256: str,
    sources: tuple[dict[str, Any], ...],
    artifacts: tuple[dict[str, Any], ...],
    r4: R4Bundle,
    links: tuple[PhysicsLinkStatus, ...],
    metrics: tuple[MetricContract, ...],
    cases: tuple[R5CaseArtifacts, ...],
    convergence: tuple[MeshConvergence, ...],
    comparisons: tuple[ComparabilityAssessment, ...],
) -> dict[str, Any]:
    return {
        "schema_version": R5_MANIFEST_SCHEMA_VERSION,
        "canonicalization_contract": canonicalization_contract(),
        "bundle_id": bundle_id,
        "input_sha256": input_sha256,
        "repository_root_binding": ".",
        "validation_mode": READINESS_VALIDATION_MODE,
        "status": READINESS_STATUS,
        "live_cst_status": "not_run",
        "live_cst_authorization": "not_requested",
        "physical_acceptance_status": "not_established",
        "r4_binding": {"bundle_id": r4.bundle_id, "input_sha256": r4.input_sha256},
        "sources": list(sources),
        "artifacts": list(artifacts),
        "instance_links": [
            {
                "instance_id": item.geometry.instance_id,
                "link_id": item.link_id,
                "link_status": item.link_status,
            }
            for item in links
        ],
        "required_contracts": list(READINESS_REQUIRED_CONTRACTS),
        "summary": {
            "case_count": len(cases),
            "comparability_count": len(comparisons),
            "convergence_count": len(convergence),
            "field_bundle_count": len(cases),
            "metric_contract_count": len(metrics),
            "metric_observation_count": sum(len(item.metric_observations) for item in cases),
            "mode_fingerprint_count": len(cases),
            "mode_identity_count": len(cases),
            "result_provenance_count": len(cases),
        },
        "checks": list(READINESS_CHECKS),
        "exclusions": list(READINESS_EXCLUSIONS),
    }


def _validate_manifest_header(path: Path, manifest: Mapping[str, Any]) -> None:
    exact_keys(
        manifest,
        {
            "schema_version",
            "canonicalization_contract",
            "bundle_id",
            "input_sha256",
            "repository_root_binding",
            "validation_mode",
            "status",
            "live_cst_status",
            "live_cst_authorization",
            "physical_acceptance_status",
            "r4_binding",
            "sources",
            "artifacts",
            "instance_links",
            "required_contracts",
            "summary",
            "checks",
            "exclusions",
        },
        "R5 manifest",
    )
    if manifest["schema_version"] != R5_MANIFEST_SCHEMA_VERSION:
        raise PhysicsContractError("unsupported R5 manifest schema")
    if manifest["canonicalization_contract"] != canonicalization_contract():
        raise PhysicsContractError("R5 canonicalization contract drifted")
    bundle_id = string(manifest["bundle_id"], "manifest.bundle_id")
    input_sha = normalized_hash(manifest["input_sha256"], "manifest.input_sha256")
    if bundle_id != f"{R5_BUNDLE_PREFIX}.{input_sha[:16]}" or path.name != bundle_id:
        raise PhysicsContractError("R5 bundle path/ID/input hash mismatch")
    if manifest["repository_root_binding"] != ".":
        raise PhysicsContractError("R5 repository root binding must be portable")


def _validate_sources(root: Path, manifest: Mapping[str, Any]) -> None:
    seen: set[str] = set()
    for raw in sequence(manifest["sources"], "manifest.sources"):
        item = mapping(raw, "source")
        exact_keys(item, {"path", "raw_sha256", "size_bytes"}, "source")
        relative = string(item["path"], "source.path")
        if relative in seen:
            raise PhysicsContractError("duplicate R5 source path")
        seen.add(relative)
        path = resolve_inside(root, relative, "source.path")
        expected_size = _non_negative_size(item["size_bytes"], "source.size_bytes")
        if not path.is_file() or path.stat().st_size != expected_size:
            raise PhysicsContractError(f"R5 source is missing or changed: {relative}")
        if file_sha256(path) != normalized_hash(item["raw_sha256"], "source.raw_sha256"):
            raise PhysicsContractError(f"R5 source hash mismatch: {relative}")


def _validate_artifacts(
    bundle: Path, manifest: Mapping[str, Any]
) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for raw in sequence(manifest["artifacts"], "manifest.artifacts"):
        item = mapping(raw, "artifact")
        exact_keys(
            item,
            {"path", "schema_version", "raw_sha256", "size_bytes"},
            "artifact",
        )
        relative = string(item["path"], "artifact.path")
        if relative in seen:
            raise PhysicsContractError("duplicate R5 artifact path")
        seen.add(relative)
        path = resolve_inside(bundle, relative, "artifact.path")
        expected_size = _non_negative_size(
            item["size_bytes"], "artifact.size_bytes"
        )
        if not path.is_file() or path.stat().st_size != expected_size:
            raise PhysicsContractError(f"R5 artifact is missing or changed: {relative}")
        if file_sha256(path) != normalized_hash(item["raw_sha256"], "artifact.raw_sha256"):
            raise PhysicsContractError(f"R5 artifact hash mismatch: {relative}")
        result.append(item)
    if not result:
        raise PhysicsContractError("R5 manifest contains no contract artifacts")
    return tuple(result)


def _write_contract(
    root: Path,
    relative: str,
    value: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
) -> None:
    path = resolve_inside(root, relative, "contract output path")
    _write_json(path, value)
    artifacts.append(
        {
            "path": relative,
            "schema_version": value["schema_version"],
            "raw_sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
    )


def _non_negative_size(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PhysicsContractError(f"{label} must be a non-negative integer")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _source_identity(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise PhysicsContractError("R5 source must remain inside repository") from exc
    if not resolved.is_file():
        raise PhysicsContractError(f"R5 source is missing: {relative}")
    return {
        "path": relative,
        "raw_sha256": file_sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _inside(root: Path, value: Path, label: str) -> Path:
    path = value.resolve() if value.is_absolute() else (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PhysicsContractError(f"{label} must remain inside repository") from exc
    if not path.exists():
        raise PhysicsContractError(f"{label} is missing: {path}")
    return path


def _one(values: list[Any], label: str) -> Any:
    if len(values) != 1:
        raise PhysicsContractError(f"each R5 case requires exactly one {label}")
    return values[0]


def _discover_repo_root(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists() and (candidate / "src/rf_cem").is_dir():
            return candidate
    raise PhysicsContractError("cannot discover repository root for R5 bundle")


__all__ = [
    "MANIFEST_FILE",
    "R5Bundle",
    "R5CaseArtifacts",
    "R5ReadinessSourceSet",
    "R5_BUNDLE_PREFIX",
    "R5_BUNDLE_SCHEMA_VERSION",
    "R5_MANIFEST_SCHEMA_VERSION",
    "load_r5_bundle",
    "write_r5_readiness_bundle",
]
