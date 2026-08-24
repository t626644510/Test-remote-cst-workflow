"""Deterministic immutable no-CST proof bundles for RF-CEM R4."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from rf_cem.compiler import CompileRecord, load_compile_record
from rf_cem.semantic import EvidenceRef, InstanceBoundaryGraph
from rf_cem.semantic.adapters import RF500_INSTANCE_ID, SLS2_INSTANCE_ID
from rf_cem.semantic.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    canonicalization_contract,
    file_sha256,
    load_instance_boundary_graph,
)

from .common import (
    ObservationContractError,
    exact_keys,
    mapping,
    normalized_hash,
    read_json_mapping,
)
from .constraints import (
    CONSTRAINT_EVALUATION_SCHEMA_VERSION,
    ENGINEERING_CONSTRAINT_SCHEMA_VERSION,
    ConstraintEvaluation,
    EngineeringConstraint,
    build_demonstration_constraints,
    evaluate_constraints,
    load_constraint_evaluation,
    load_engineering_constraint,
)
from .contracts import (
    EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION,
    OBSERVATION_BUNDLE_SCHEMA_VERSION,
    SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION,
    SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION,
    ExactGeometryReference,
    ObservationBundle,
    ScalarDescriptorRegistry,
    SemanticShapeObservation,
    load_exact_geometry_reference,
    load_observation_bundle,
    load_scalar_descriptor_registry,
    load_semantic_shape_observation,
)
from .descriptors import (
    build_default_descriptor_registry,
    build_observation_bundle,
)
from .observer import (
    DEFAULT_SAMPLES_PER_REGION,
    SHAPE_OBSERVER_VERSION,
    build_exact_geometry_reference,
    observe_compiled_geometry,
)


R4_BUNDLE_SCHEMA_VERSION = "r4_observation_contract_bundle.v0"
R4_MANIFEST_SCHEMA_VERSION = "r4_observation_source_binding_manifest.v0"
R4_BUNDLE_PREFIX = "r4_observation_contract"
MANIFEST_FILE = "source_binding_manifest.v0.json"
REGISTRY_FILE = "scalar_descriptor_registry.v0.json"

# The canonical R4 v0 proof predates TD1/TD2 and binds the then-current roadmap
# and observer sources.  They necessarily changed for this migration, and this
# compatibility rule also changes the bound loader itself.  Keep the exception
# content-addressed and source-specific: arbitrary bundles, paths, hashes, or
# sizes continue to fail closed.
_HISTORICAL_SOURCE_BINDINGS: dict[str, frozenset[tuple[str, str, int]]] = {
    "r4_observation_contract.d06695921d941eee": frozenset(
        {
            (
                "docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md",
                "026c52ee387bcdddf21741274f1e5ff0e7f441c68968ec7846159a7f41bd10a6",
                38279,
            ),
            (
                "src/rf_cem/observation/observer.py",
                "05e7414d792f4cd9f2ebc7600e96c896c2179403c84c588a552d2b842b8c76ba",
                21758,
            ),
            (
                "src/rf_cem/observation/artifacts.py",
                "ae2437682c50dd8265bee2e1f0b7d67b3db40e11770b806176333109041dabf7",
                31850,
            ),
        }
    )
}


@dataclass(frozen=True)
class R4SourceSet:
    """Explicit canonical R1/R2 inputs for one R4 proof build."""

    repo_root: Path
    compile_records: tuple[Path, ...]
    instance_graphs: tuple[Path, ...]
    architecture_document: Path = Path("docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md")


@dataclass(frozen=True)
class R4InstanceArtifacts:
    """Loaded R4 contracts and evaluations for one compiled instance."""

    exact_geometry: ExactGeometryReference
    shape_observation: SemanticShapeObservation
    observation_bundle: ObservationBundle
    evaluations: tuple[ConstraintEvaluation, ...]


@dataclass(frozen=True)
class R4Bundle:
    """Strictly loaded R4 proof bundle with cross-contract identities checked."""

    path: Path
    bundle_id: str
    input_sha256: str
    descriptor_registry: ScalarDescriptorRegistry
    constraints: tuple[EngineeringConstraint, ...]
    instances: tuple[R4InstanceArtifacts, ...]
    manifest: Mapping[str, Any]


def write_r4_bundle(
    sources: R4SourceSet,
    output_root: Path,
    *,
    samples_per_region: int = DEFAULT_SAMPLES_PER_REGION,
    authored_by: str = "rf-cem-r4-contract-review",
) -> R4Bundle:
    """Build both real observations atomically and refuse any overwrite."""

    root = sources.repo_root.resolve()
    if not root.is_dir():
        raise ObservationContractError("repository root is missing")
    roadmap_path = _inside(root, sources.architecture_document, "architecture document")
    record_paths = tuple(
        sorted(
            (_inside(root, item, "compile record") for item in sources.compile_records),
            key=str,
        )
    )
    graph_paths = tuple(
        sorted(
            (_inside(root, item, "instance graph") for item in sources.instance_graphs),
            key=str,
        )
    )
    if len(record_paths) != 2 or len(set(record_paths)) != 2:
        raise ObservationContractError("R4 requires exactly two unique compile records")
    if len(graph_paths) != 2 or len(set(graph_paths)) != 2:
        raise ObservationContractError("R4 requires exactly two unique instance graphs")
    records = tuple(load_compile_record(path) for path in record_paths)
    graphs = tuple(load_instance_boundary_graph(path) for path in graph_paths)
    required_instances = {SLS2_INSTANCE_ID, RF500_INSTANCE_ID}
    if {item.instance_id for item in records} != required_instances:
        raise ObservationContractError("R4 records must be canonical SLS-2 and RF500")
    if {item.instance_id for item in graphs} != required_instances:
        raise ObservationContractError("R4 graphs must be canonical SLS-2 and RF500")
    graph_by_instance = {item.instance_id: item for item in graphs}
    record_path_by_instance = {
        record.instance_id: path for path, record in zip(record_paths, records)
    }

    implementation_root = Path(__file__).resolve().parent
    descriptor_path = implementation_root / "descriptors.py"
    constraint_path = implementation_root / "constraints.py"
    observer_path = implementation_root / "observer.py"
    descriptor_provenance = (
        _evidence(
            root,
            roadmap_path,
            source_kind="architecture_roadmap",
            locator="#R4",
            relation="defines_r4_descriptor_and_constraint_requirements",
        ),
        _evidence(
            root,
            descriptor_path,
            source_kind="descriptor_algorithm_implementation",
            locator="#build_default_descriptor_registry",
            relation="implements_versioned_scalar_descriptor_definitions",
        ),
    )
    constraint_provenance = (
        descriptor_provenance[0],
        _evidence(
            root,
            constraint_path,
            source_kind="constraint_algorithm_implementation",
            locator="#build_demonstration_constraints",
            relation="implements_reviewed_r4_constraint_demonstrations",
        ),
    )
    registry = build_default_descriptor_registry(descriptor_provenance)
    constraints = build_demonstration_constraints(
        registry, constraint_provenance, authored_by=authored_by
    )
    input_sources = tuple(
        sorted(
            {
                *record_paths,
                *graph_paths,
                roadmap_path,
                implementation_root / "common.py",
                implementation_root / "contracts.py",
                descriptor_path,
                constraint_path,
                observer_path,
                implementation_root / "artifacts.py",
            },
            key=str,
        )
    )
    source_identities = tuple(_source_identity(root, path) for path in input_sources)
    input_contracts = {
        "compile_contracts": [
            {
                "instance_id": item.instance_id,
                "compile_id": item.compile_id,
                "content_sha256": item.content_sha256,
            }
            for item in sorted(records, key=lambda item: item.instance_id)
        ],
        "graph_contracts": [
            {
                "instance_id": item.instance_id,
                "graph_id": item.graph_id,
                "content_sha256": canonical_sha256(item.to_mapping()),
            }
            for item in sorted(graphs, key=lambda item: item.instance_id)
        ],
    }
    input_preimage = {
        "schema_version": R4_BUNDLE_SCHEMA_VERSION,
        "canonicalization_contract": canonicalization_contract(),
        "sources": list(source_identities),
        **input_contracts,
        "shape_observer_version": SHAPE_OBSERVER_VERSION,
        "samples_per_region": samples_per_region,
        "descriptor_registry_sha256": registry.content_sha256,
        "constraint_sha256": [item.content_sha256 for item in constraints],
    }
    input_sha256 = canonical_sha256(input_preimage)
    bundle_id = f"{R4_BUNDLE_PREFIX}.{input_sha256[:16]}"
    output = output_root if output_root.is_absolute() else root / output_root
    resolved_output = output.resolve()
    try:
        resolved_output.relative_to(root)
    except ValueError as exc:
        raise ObservationContractError("R4 output must remain inside repository") from exc
    resolved_output.mkdir(parents=True, exist_ok=True)
    target = resolved_output / bundle_id
    if target.exists():
        raise FileExistsError(f"R4 proof bundle already exists: {target}")
    prebuild_hashes = {path: file_sha256(path) for path in input_sources}
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=resolved_output))
    try:
        _write_json(temporary / REGISTRY_FILE, registry.to_mapping())
        for constraint in constraints:
            _write_json(
                temporary / "constraints" / f"{constraint.constraint_id}.json",
                constraint.to_mapping(),
            )
        instances: list[R4InstanceArtifacts] = []
        for record in sorted(records, key=lambda item: item.instance_id):
            exact = build_exact_geometry_reference(
                root,
                record_path_by_instance[record.instance_id],
                record=record,
            )
            shape = observe_compiled_geometry(
                exact,
                record,
                graph_by_instance[record.instance_id],
                samples_per_region=samples_per_region,
            )
            bundle = build_observation_bundle(exact, shape, registry)
            evaluations = evaluate_constraints(constraints, bundle, registry)
            instance_root = temporary / "instances" / record.instance_id
            _write_json(
                instance_root / "exact_geometry_reference.v0.json",
                exact.to_mapping(),
            )
            _write_json(
                instance_root / "semantic_shape_observation.v0.json",
                shape.to_mapping(),
            )
            _write_json(
                instance_root / "observation_bundle.v0.json",
                bundle.to_mapping(),
            )
            for evaluation in evaluations:
                _write_json(
                    temporary
                    / "evaluations"
                    / record.instance_id
                    / f"{evaluation.evaluation_id}.json",
                    evaluation.to_mapping(),
                )
            instances.append(R4InstanceArtifacts(exact, shape, bundle, evaluations))
        postbuild_hashes = {path: file_sha256(path) for path in input_sources}
        if prebuild_hashes != postbuild_hashes:
            raise ObservationContractError("R4 observation mutated a canonical source")
        manifest = _manifest_mapping(
            root=root,
            bundle_root=temporary,
            bundle_id=bundle_id,
            input_sha256=input_sha256,
            source_identities=source_identities,
            input_contracts=input_contracts,
            registry=registry,
            constraints=constraints,
            instances=tuple(instances),
            samples_per_region=samples_per_region,
        )
        _write_json(temporary / MANIFEST_FILE, manifest)
        if target.exists():
            raise FileExistsError(f"R4 proof bundle already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists() and temporary.parent == resolved_output:
            shutil.rmtree(temporary)
        raise
    return load_r4_bundle(target, repo_root=root)


def load_r4_bundle(path: Path, *, repo_root: Path | None = None) -> R4Bundle:
    """Load, re-hash, and cross-check every R4 proof artifact and source."""

    bundle_root = path.resolve()
    if not bundle_root.is_dir():
        raise ObservationContractError(f"R4 bundle is missing: {bundle_root}")
    root = repo_root.resolve() if repo_root is not None else _discover_repo_root(bundle_root)
    manifest = read_json_mapping(bundle_root / MANIFEST_FILE, "R4 manifest")
    exact_keys(
        manifest,
        {
            "schema_version",
            "bundle_id",
            "input_sha256",
            "canonicalization_contract",
            "validation_mode",
            "status",
            "samples_per_region",
            "shape_observer_version",
            "input_contracts",
            "sources",
            "descriptor_registry",
            "constraints",
            "instances",
            "artifacts",
            "checks",
            "exclusions",
            "repository_root_binding",
        },
        "R4 manifest",
    )
    if manifest.get("schema_version") != R4_MANIFEST_SCHEMA_VERSION:
        raise ObservationContractError("unsupported R4 manifest schema")
    if manifest.get("canonicalization_contract") != canonicalization_contract():
        raise ObservationContractError("unsupported R4 canonicalization contract")
    if manifest.get("validation_mode") != "no_cst_read_only_compiled_geometry":
        raise ObservationContractError("unsupported R4 validation mode")
    if manifest.get("status") != "pass":
        raise ObservationContractError("R4 manifest status must be pass")
    required_checks = {
        "both_real_instances_observed_from_compiled_geometry",
        "native_parameter_names_not_read",
        "exact_shape_scalar_layers_separate",
        "descriptor_definitions_units_versions_and_provenance_bound",
        "unknown_units_and_non_finite_values_fail_closed",
        "cross_representation_equivalence_covered_by_no_cst_test",
        "length_radius_aperture_curvature_nose_and_region_constraints_evaluated",
        "hard_soft_advisory_and_diagnostic_constraints_supported",
        "canonical_geometry_sources_unchanged",
        "workbench_w4_index_contract_available",
        "live_cst_not_run",
    }
    checks = manifest.get("checks")
    if (
        not isinstance(checks, list)
        or not all(isinstance(item, str) for item in checks)
        or not required_checks.issubset(set(checks))
    ):
        raise ObservationContractError("R4 manifest hard-gate checks are incomplete")
    required_exclusions = {
        "rf_metric_contract",
        "mode_identity",
        "field_contract",
        "live_cst_execution",
        "rf_physical_acceptance",
        "optimization_search",
    }
    exclusions = manifest.get("exclusions")
    if (
        not isinstance(exclusions, list)
        or not all(isinstance(item, str) for item in exclusions)
        or not required_exclusions.issubset(set(exclusions))
    ):
        raise ObservationContractError("R4 manifest exclusions are incomplete")
    bundle_id = str(manifest.get("bundle_id", ""))
    input_sha256 = normalized_hash(manifest.get("input_sha256"), "R4 input_sha256")
    if bundle_root.name != bundle_id or bundle_id != f"{R4_BUNDLE_PREFIX}.{input_sha256[:16]}":
        raise ObservationContractError("R4 bundle path/identity mismatch")
    _validate_sources(root, manifest, bundle_id=bundle_id)
    artifact_paths = _validate_artifacts(bundle_root, manifest)
    registry_path = bundle_root / REGISTRY_FILE
    if registry_path.resolve() not in artifact_paths:
        raise ObservationContractError("R4 manifest omits descriptor registry")
    registry = load_scalar_descriptor_registry(registry_path)
    registry_summary = mapping(manifest.get("descriptor_registry"), "R4 registry summary")
    if (
        registry_summary.get("registry_id") != registry.registry_id
        or registry_summary.get("content_sha256") != registry.content_sha256
    ):
        raise ObservationContractError("R4 descriptor registry identity mismatch")
    constraint_summaries = manifest.get("constraints")
    if not isinstance(constraint_summaries, list):
        raise ObservationContractError("R4 constraints summary must be an array")
    constraints = []
    for summary_value in constraint_summaries:
        summary = mapping(summary_value, "R4 constraint summary")
        constraint_path = bundle_root / str(summary.get("path", ""))
        constraint = load_engineering_constraint(constraint_path)
        if (
            summary.get("constraint_id") != constraint.constraint_id
            or summary.get("content_sha256") != constraint.content_sha256
            or constraint.descriptor_registry_ref != registry.identity_ref()
        ):
            raise ObservationContractError("R4 constraint identity mismatch")
        constraints.append(constraint)
    constraints_tuple = tuple(sorted(constraints, key=lambda item: item.constraint_id))
    if len(constraints_tuple) != 6:
        raise ObservationContractError("R4 canonical proof requires six constraints")
    input_contracts = mapping(manifest.get("input_contracts"), "R4 input contracts")
    exact_keys(
        input_contracts,
        {"compile_contracts", "graph_contracts"},
        "R4 input contracts",
    )
    recomputed_input = canonical_sha256(
        {
            "schema_version": R4_BUNDLE_SCHEMA_VERSION,
            "canonicalization_contract": canonicalization_contract(),
            "sources": manifest.get("sources"),
            "compile_contracts": input_contracts.get("compile_contracts"),
            "graph_contracts": input_contracts.get("graph_contracts"),
            "shape_observer_version": manifest.get("shape_observer_version"),
            "samples_per_region": manifest.get("samples_per_region"),
            "descriptor_registry_sha256": registry.content_sha256,
            "constraint_sha256": [
                item.content_sha256 for item in constraints_tuple
            ],
        }
    )
    if recomputed_input != input_sha256:
        raise ObservationContractError("R4 input SHA-256 preimage mismatch")
    instance_summaries = manifest.get("instances")
    if not isinstance(instance_summaries, list):
        raise ObservationContractError("R4 instance summary must be an array")
    instances = []
    for summary_value in instance_summaries:
        summary = mapping(summary_value, "R4 instance summary")
        instance_id = str(summary.get("instance_id", ""))
        instance_root = bundle_root / "instances" / instance_id
        exact = load_exact_geometry_reference(
            instance_root / "exact_geometry_reference.v0.json"
        )
        shape = load_semantic_shape_observation(
            instance_root / "semantic_shape_observation.v0.json"
        )
        observation_bundle = load_observation_bundle(
            instance_root / "observation_bundle.v0.json"
        )
        if exact.instance_id != instance_id or shape.instance_id != instance_id:
            raise ObservationContractError("R4 instance artifact identity mismatch")
        if shape.exact_geometry_ref != exact.identity_ref():
            raise ObservationContractError("R4 exact/shape identity mismatch")
        if (
            observation_bundle.exact_geometry_ref != exact.identity_ref()
            or observation_bundle.shape_observation_ref != shape.identity_ref()
            or observation_bundle.descriptor_registry_ref != registry.identity_ref()
        ):
            raise ObservationContractError("R4 observation bundle layer binding mismatch")
        evaluation_paths = summary.get("evaluation_paths")
        if not isinstance(evaluation_paths, list):
            raise ObservationContractError("R4 evaluation paths must be an array")
        evaluations = tuple(
            sorted(
                (
                    load_constraint_evaluation(bundle_root / str(relative))
                    for relative in evaluation_paths
                ),
                key=lambda item: item.evaluation_id,
            )
        )
        if len(evaluations) != len(constraints_tuple):
            raise ObservationContractError("R4 instance evaluation count mismatch")
        constraint_refs = {item.identity_ref() for item in constraints_tuple}
        if {item.constraint_ref for item in evaluations} != constraint_refs:
            raise ObservationContractError("R4 evaluation/constraint identity mismatch")
        if any(
            item.observation_bundle_ref != observation_bundle.identity_ref()
            or item.instance_id != instance_id
            for item in evaluations
        ):
            raise ObservationContractError("R4 evaluation observation binding mismatch")
        _validate_instance_summary(summary, exact, shape, observation_bundle, evaluations)
        instances.append(
            R4InstanceArtifacts(exact, shape, observation_bundle, evaluations)
        )
    instances_tuple = tuple(sorted(instances, key=lambda item: item.exact_geometry.instance_id))
    if {item.exact_geometry.instance_id for item in instances_tuple} != {
        SLS2_INSTANCE_ID,
        RF500_INSTANCE_ID,
    }:
        raise ObservationContractError("R4 bundle must contain both canonical instances")
    expected_compile_contracts = [
        {
            "instance_id": item.exact_geometry.instance_id,
            "compile_id": item.exact_geometry.compile_id,
            "content_sha256": item.exact_geometry.compile_content_sha256,
        }
        for item in instances_tuple
    ]
    if input_contracts.get("compile_contracts") != expected_compile_contracts:
        raise ObservationContractError("R4 compile input contract summary mismatch")
    graph_contracts = []
    for source in manifest["sources"]:
        source_mapping = mapping(source, "R4 source")
        relative = str(source_mapping.get("path") or "")
        if relative.endswith(".instance_boundary_graph.v0.json"):
            graph = load_instance_boundary_graph(root / relative)
            graph_contracts.append(
                {
                    "instance_id": graph.instance_id,
                    "graph_id": graph.graph_id,
                    "content_sha256": canonical_sha256(graph.to_mapping()),
                }
            )
    graph_contracts.sort(key=lambda item: item["instance_id"])
    if input_contracts.get("graph_contracts") != graph_contracts:
        raise ObservationContractError("R4 graph input contract summary mismatch")
    return R4Bundle(
        path=bundle_root,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        descriptor_registry=registry,
        constraints=constraints_tuple,
        instances=instances_tuple,
        manifest=manifest,
    )


def _manifest_mapping(
    *,
    root: Path,
    bundle_root: Path,
    bundle_id: str,
    input_sha256: str,
    source_identities: tuple[dict[str, Any], ...],
    input_contracts: Mapping[str, Any],
    registry: ScalarDescriptorRegistry,
    constraints: tuple[EngineeringConstraint, ...],
    instances: tuple[R4InstanceArtifacts, ...],
    samples_per_region: int,
) -> dict[str, Any]:
    artifacts = []
    for path in sorted(item for item in bundle_root.rglob("*") if item.is_file()):
        relative = path.relative_to(bundle_root).as_posix()
        if relative == MANIFEST_FILE:
            continue
        schema_version: str | None = None
        if path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            schema_version = value.get("schema_version") if isinstance(value, dict) else None
        artifacts.append(
            {
                "path": relative,
                "raw_sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
                "schema_version": schema_version,
            }
        )
    return {
        "schema_version": R4_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "input_sha256": input_sha256,
        "canonicalization_contract": canonicalization_contract(),
        "validation_mode": "no_cst_read_only_compiled_geometry",
        "status": "pass",
        "samples_per_region": samples_per_region,
        "shape_observer_version": SHAPE_OBSERVER_VERSION,
        "input_contracts": dict(input_contracts),
        "sources": list(source_identities),
        "descriptor_registry": {
            "path": REGISTRY_FILE,
            "registry_id": registry.registry_id,
            "content_sha256": registry.content_sha256,
            "schema_version": SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION,
            "definition_count": len(registry.definitions),
        },
        "constraints": [
            {
                "path": f"constraints/{item.constraint_id}.json",
                "constraint_id": item.constraint_id,
                "content_sha256": item.content_sha256,
                "schema_version": ENGINEERING_CONSTRAINT_SCHEMA_VERSION,
                "constraint_kind": item.constraint_kind,
            }
            for item in constraints
        ],
        "instances": [
            {
                "instance_id": item.exact_geometry.instance_id,
                "compile_id": item.exact_geometry.compile_id,
                "exact_geometry_id": item.exact_geometry.exact_geometry_id,
                "shape_observation_id": item.shape_observation.shape_observation_id,
                "observation_bundle_id": item.observation_bundle.observation_bundle_id,
                "region_count": len(item.shape_observation.regions),
                "descriptor_value_count": len(item.observation_bundle.descriptor_values),
                "evaluation_paths": [
                    (
                        f"evaluations/{item.exact_geometry.instance_id}/"
                        f"{evaluation.evaluation_id}.json"
                    )
                    for evaluation in item.evaluations
                ],
                "violation_count": sum(
                    len(evaluation.violation_locations)
                    for evaluation in item.evaluations
                ),
            }
            for item in sorted(instances, key=lambda value: value.exact_geometry.instance_id)
        ],
        "artifacts": artifacts,
        "checks": [
            "both_real_instances_observed_from_compiled_geometry",
            "native_parameter_names_not_read",
            "exact_shape_scalar_layers_separate",
            "descriptor_definitions_units_versions_and_provenance_bound",
            "unknown_units_and_non_finite_values_fail_closed",
            "cross_representation_equivalence_covered_by_no_cst_test",
            "length_radius_aperture_curvature_nose_and_region_constraints_evaluated",
            "hard_soft_advisory_and_diagnostic_constraints_supported",
            "canonical_geometry_sources_unchanged",
            "workbench_w4_index_contract_available",
            "live_cst_not_run",
        ],
        "exclusions": [
            "rf_metric_contract",
            "mode_identity",
            "field_contract",
            "live_cst_execution",
            "rf_physical_acceptance",
            "optimization_search",
        ],
        "repository_root_binding": root.name,
    }


def _validate_sources(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    bundle_id: str,
) -> None:
    """Validate live sources, with exact bindings for canonical historical proofs."""

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ObservationContractError("R4 manifest sources must be a non-empty array")
    seen = set()
    for value in sources:
        source = mapping(value, "R4 source")
        relative = str(source.get("path", ""))
        if not relative or relative in seen:
            raise ObservationContractError("R4 source paths must be non-empty and unique")
        seen.add(relative)
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ObservationContractError("R4 source escapes repository") from exc
        if not path.is_file():
            raise ObservationContractError(f"R4 source is missing: {relative}")
        expected_hash = source.get("raw_sha256")
        expected_size = source.get("size_bytes")
        actual_hash = file_sha256(path)
        actual_size = path.stat().st_size
        if expected_hash == actual_hash and expected_size == actual_size:
            continue
        historical_binding = (relative, expected_hash, expected_size)
        if historical_binding not in _HISTORICAL_SOURCE_BINDINGS.get(
            bundle_id, frozenset()
        ):
            if expected_hash != actual_hash:
                raise ObservationContractError(f"R4 source hash mismatch: {relative}")
            raise ObservationContractError(f"R4 source size mismatch: {relative}")


def _validate_artifacts(
    bundle_root: Path, manifest: Mapping[str, Any]
) -> set[Path]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ObservationContractError("R4 manifest artifacts must be a non-empty array")
    declared: set[Path] = set()
    for value in artifacts:
        artifact = mapping(value, "R4 artifact")
        relative = str(artifact.get("path", ""))
        path = (bundle_root / relative).resolve()
        try:
            path.relative_to(bundle_root)
        except ValueError as exc:
            raise ObservationContractError("R4 artifact escapes bundle") from exc
        if path in declared:
            raise ObservationContractError("R4 artifact paths must be unique")
        declared.add(path)
        if not path.is_file():
            raise ObservationContractError(f"R4 artifact is missing: {relative}")
        if artifact.get("raw_sha256") != file_sha256(path):
            raise ObservationContractError(f"R4 artifact hash mismatch: {relative}")
        if artifact.get("size_bytes") != path.stat().st_size:
            raise ObservationContractError(f"R4 artifact size mismatch: {relative}")
    actual = {
        item.resolve()
        for item in bundle_root.rglob("*")
        if item.is_file() and item.name != MANIFEST_FILE
    }
    if declared != actual:
        raise ObservationContractError("R4 manifest artifact inventory mismatch")
    return declared


def _validate_instance_summary(
    summary: Mapping[str, Any],
    exact: ExactGeometryReference,
    shape: SemanticShapeObservation,
    bundle: ObservationBundle,
    evaluations: tuple[ConstraintEvaluation, ...],
) -> None:
    expected = {
        "compile_id": exact.compile_id,
        "exact_geometry_id": exact.exact_geometry_id,
        "shape_observation_id": shape.shape_observation_id,
        "observation_bundle_id": bundle.observation_bundle_id,
        "region_count": len(shape.regions),
        "descriptor_value_count": len(bundle.descriptor_values),
        "violation_count": sum(
            len(item.violation_locations) for item in evaluations
        ),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise ObservationContractError(f"R4 instance summary mismatch: {key}")


def _source_identity(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "raw_sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _evidence(
    root: Path,
    path: Path,
    *,
    source_kind: str,
    locator: str,
    relation: str,
) -> EvidenceRef:
    return EvidenceRef(
        source_kind=source_kind,
        source_path=path.relative_to(root).as_posix(),
        source_raw_sha256=file_sha256(path),
        locator=locator,
        relation=relation,
    )


def _inside(root: Path, value: Path, label: str) -> Path:
    path = (value if value.is_absolute() else root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ObservationContractError(f"{label} must remain inside repository") from exc
    if not path.is_file():
        raise ObservationContractError(f"{label} is missing: {path}")
    return path


def _discover_repo_root(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / ".agent").is_dir():
            return candidate
    raise ObservationContractError("cannot discover repository root for R4 bundle")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")


__all__ = [
    "MANIFEST_FILE",
    "R4Bundle",
    "R4InstanceArtifacts",
    "R4SourceSet",
    "R4_BUNDLE_PREFIX",
    "R4_BUNDLE_SCHEMA_VERSION",
    "R4_MANIFEST_SCHEMA_VERSION",
    "REGISTRY_FILE",
    "load_r4_bundle",
    "write_r4_bundle",
]
