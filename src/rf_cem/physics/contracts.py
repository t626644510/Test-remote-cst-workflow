"""Public versioned contract surface for RF-CEM R5."""

from __future__ import annotations

from pathlib import Path

from .cases import (
    AUTHORIZATION_STATUSES,
    CASE_STATUSES,
    LINK_STATUSES,
    PHYSICS_CASE_SCHEMA_VERSION,
    PHYSICS_LINK_STATUS_SCHEMA_VERSION,
    RESULT_PROVENANCE_SCHEMA_VERSION,
    RUN_STATUSES,
    PhysicsCase,
    PhysicsLinkStatus,
    ResultProvenance,
)
from .common import PhysicsContractError, read_json_mapping
from .comparability import (
    COMPARABILITY_DECISIONS,
    COMPARABILITY_SCHEMA_VERSION,
    COMPARISON_PURPOSES,
    ComparabilityAssessment,
    assess_comparability,
)
from .convergence import (
    CONVERGENCE_STATUSES,
    MESH_CONVERGENCE_SCHEMA_VERSION,
    MeshConvergence,
    MeshConvergenceSample,
    evaluate_mesh_convergence,
)
from .fields import (
    FIELD_BUNDLE_SCHEMA_VERSION,
    FIELD_STATUSES,
    FieldBundle,
    FieldComponent,
)
from .metrics import (
    EXTRACTION_SUPPORT_STATUSES,
    METRIC_CONTRACT_SCHEMA_VERSION,
    METRIC_OBSERVATION_SCHEMA_VERSION,
    METRIC_UNITS,
    METRIC_VALIDATION_STATUSES,
    REQUIRED_METRIC_KEYS,
    MetricContract,
    MetricObservation,
    build_initial_metric_contracts,
)
from .modes import (
    FINGERPRINT_STATUSES,
    MODE_DETERMINATION_STATUSES,
    MODE_FINGERPRINT_SCHEMA_VERSION,
    MODE_IDENTITY_SCHEMA_VERSION,
    ModeFingerprint,
    ModeIdentity,
)
from .references import (
    SETTING_STATUSES,
    BoundaryAssignment,
    ContractRef,
    ExternalArtifactRef,
    GeometryBinding,
    MaterialAssignment,
    MeshDefinition,
    SolverDefinition,
)


def load_physics_case(path: Path) -> PhysicsCase:
    return PhysicsCase.from_mapping(read_json_mapping(path, "physics_case"))


def load_mode_identity(path: Path) -> ModeIdentity:
    return ModeIdentity.from_mapping(read_json_mapping(path, "mode_identity"))


def load_mode_fingerprint(path: Path) -> ModeFingerprint:
    return ModeFingerprint.from_mapping(read_json_mapping(path, "mode_fingerprint"))


def load_metric_contract(path: Path) -> MetricContract:
    return MetricContract.from_mapping(read_json_mapping(path, "metric_contract"))


def load_metric_observation(path: Path) -> MetricObservation:
    return MetricObservation.from_mapping(read_json_mapping(path, "metric_observation"))


def load_field_bundle(path: Path) -> FieldBundle:
    return FieldBundle.from_mapping(read_json_mapping(path, "field_bundle"))


def load_mesh_convergence(path: Path) -> MeshConvergence:
    return MeshConvergence.from_mapping(read_json_mapping(path, "mesh_convergence"))


def load_result_provenance(path: Path) -> ResultProvenance:
    return ResultProvenance.from_mapping(read_json_mapping(path, "result_provenance"))


def load_physics_link_status(path: Path) -> PhysicsLinkStatus:
    return PhysicsLinkStatus.from_mapping(read_json_mapping(path, "physics_link_status"))


def load_comparability(path: Path) -> ComparabilityAssessment:
    return ComparabilityAssessment.from_mapping(read_json_mapping(path, "comparability"))


__all__ = [
    "AUTHORIZATION_STATUSES",
    "BoundaryAssignment",
    "CASE_STATUSES",
    "COMPARABILITY_DECISIONS",
    "COMPARABILITY_SCHEMA_VERSION",
    "COMPARISON_PURPOSES",
    "CONVERGENCE_STATUSES",
    "ComparabilityAssessment",
    "ContractRef",
    "EXTRACTION_SUPPORT_STATUSES",
    "ExternalArtifactRef",
    "FIELD_BUNDLE_SCHEMA_VERSION",
    "FIELD_STATUSES",
    "FINGERPRINT_STATUSES",
    "FieldBundle",
    "FieldComponent",
    "GeometryBinding",
    "LINK_STATUSES",
    "METRIC_CONTRACT_SCHEMA_VERSION",
    "METRIC_OBSERVATION_SCHEMA_VERSION",
    "METRIC_UNITS",
    "METRIC_VALIDATION_STATUSES",
    "MESH_CONVERGENCE_SCHEMA_VERSION",
    "MODE_DETERMINATION_STATUSES",
    "MODE_FINGERPRINT_SCHEMA_VERSION",
    "MODE_IDENTITY_SCHEMA_VERSION",
    "MaterialAssignment",
    "MeshConvergence",
    "MeshConvergenceSample",
    "MeshDefinition",
    "MetricContract",
    "MetricObservation",
    "ModeFingerprint",
    "ModeIdentity",
    "PHYSICS_CASE_SCHEMA_VERSION",
    "PHYSICS_LINK_STATUS_SCHEMA_VERSION",
    "PhysicsCase",
    "PhysicsContractError",
    "PhysicsLinkStatus",
    "REQUIRED_METRIC_KEYS",
    "RESULT_PROVENANCE_SCHEMA_VERSION",
    "RUN_STATUSES",
    "ResultProvenance",
    "SETTING_STATUSES",
    "SolverDefinition",
    "assess_comparability",
    "build_initial_metric_contracts",
    "evaluate_mesh_convergence",
    "load_comparability",
    "load_field_bundle",
    "load_mesh_convergence",
    "load_metric_contract",
    "load_metric_observation",
    "load_mode_fingerprint",
    "load_mode_identity",
    "load_physics_case",
    "load_physics_link_status",
    "load_result_provenance",
]
