"""Typed contracts for the RF-CEM R2 topology/representation compiler."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from rf_cem.representation import (
    CompositeRegionRepresentation,
    GeometryPatch,
    Point2D,
    RegionGeometry,
    RepresentationContractError,
    representation_from_mapping,
)
from rf_cem.semantic import EvidenceRef, FamilyGrammar, InstanceBoundaryGraph
from rf_cem.semantic.contracts import canonical_sha256


BOUNDARY_CONTINUITY_POLICY_SCHEMA_VERSION = "boundary_continuity_policy.v0"
LEGACY_COMPILE_RECORD_SCHEMA_VERSION = "compile_record.v0"
COMPILE_REQUEST_SCHEMA_VERSION = "compile_request.v1"
COMPILE_RECORD_SCHEMA_VERSION = "compile_record.v1"
LEGACY_COMPILER_VERSION = "rf_cem_profile_compiler.v0"
COMPILER_VERSION = "rf_cem_profile_compiler.v1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class CompileContractError(ValueError):
    """Raised when an R2 compile request or record violates its contract."""


@dataclass(frozen=True)
class ContractSourceRef:
    """Hash-bound reference to one canonical input contract."""

    contract_kind: str
    schema_version: str
    object_id: str
    canonical_sha256: str
    source: EvidenceRef

    def __post_init__(self) -> None:
        for value, path in (
            (self.contract_kind, "contract_ref.contract_kind"),
            (self.schema_version, "contract_ref.schema_version"),
            (self.object_id, "contract_ref.object_id"),
        ):
            _non_empty(value, path)
        _hash(self.canonical_sha256, "contract_ref.canonical_sha256")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "contract_kind": self.contract_kind,
            "schema_version": self.schema_version,
            "object_id": self.object_id,
            "canonical_sha256": self.canonical_sha256,
            "source": self.source.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContractSourceRef":
        mapping = _mapping(value, "contract_ref")
        _exact_keys(
            mapping,
            {"contract_kind", "schema_version", "object_id", "canonical_sha256", "source"},
            "contract_ref",
        )
        return cls(
            contract_kind=_string(mapping["contract_kind"], "contract_ref.contract_kind"),
            schema_version=_string(mapping["schema_version"], "contract_ref.schema_version"),
            object_id=_string(mapping["object_id"], "contract_ref.object_id"),
            canonical_sha256=_hash(mapping["canonical_sha256"], "contract_ref.canonical_sha256"),
            source=EvidenceRef.from_mapping(_mapping(mapping["source"], "contract_ref.source")),
        )


@dataclass(frozen=True)
class NativeArtifactRef:
    """One exact source-native geometry or validation artifact."""

    role: str
    bundle_relative_path: str
    raw_sha256: str

    def __post_init__(self) -> None:
        _non_empty(self.role, "native_artifact.role")
        _relative_path(self.bundle_relative_path, "native_artifact.bundle_relative_path")
        _hash(self.raw_sha256, "native_artifact.raw_sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "role": self.role,
            "bundle_relative_path": self.bundle_relative_path,
            "raw_sha256": self.raw_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NativeArtifactRef":
        mapping = _mapping(value, "native_artifact")
        _exact_keys(mapping, {"role", "bundle_relative_path", "raw_sha256"}, "native_artifact")
        return cls(
            role=_string(mapping["role"], "native_artifact.role"),
            bundle_relative_path=_relative_path(
                mapping["bundle_relative_path"], "native_artifact.bundle_relative_path"
            ),
            raw_sha256=_hash(mapping["raw_sha256"], "native_artifact.raw_sha256"),
        )


@dataclass(frozen=True)
class SourceNativeProvenance:
    """Stage C source-native payload binding preserved through compilation."""

    family_profile: ContractSourceRef
    adapter_id: str
    native_schema_version: str
    native_payload_locator: str
    native_payload_canonical_sha256: str
    native_artifacts: tuple[NativeArtifactRef, ...]
    source_native_roundtrip_status: str = "pass"

    def __post_init__(self) -> None:
        for value, path in (
            (self.adapter_id, "source_native.adapter_id"),
            (self.native_schema_version, "source_native.native_schema_version"),
            (self.native_payload_locator, "source_native.native_payload_locator"),
        ):
            _non_empty(value, path)
        _hash(self.native_payload_canonical_sha256, "source_native.native_payload_canonical_sha256")
        if not self.native_artifacts:
            raise CompileContractError("source-native provenance requires artifact bindings")
        if self.source_native_roundtrip_status != "pass":
            raise CompileContractError("source-native roundtrip must pass before compilation")
        roles = [item.role for item in self.native_artifacts]
        if len(roles) != len(set(roles)):
            raise CompileContractError("source-native artifact roles must be unique")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "family_profile": self.family_profile.to_mapping(),
            "adapter_id": self.adapter_id,
            "native_schema_version": self.native_schema_version,
            "native_payload_locator": self.native_payload_locator,
            "native_payload_canonical_sha256": self.native_payload_canonical_sha256,
            "native_artifacts": [item.to_mapping() for item in self.native_artifacts],
            "source_native_roundtrip_status": self.source_native_roundtrip_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SourceNativeProvenance":
        mapping = _mapping(value, "source_native")
        _exact_keys(
            mapping,
            {
                "family_profile",
                "adapter_id",
                "native_schema_version",
                "native_payload_locator",
                "native_payload_canonical_sha256",
                "native_artifacts",
                "source_native_roundtrip_status",
            },
            "source_native",
        )
        return cls(
            family_profile=ContractSourceRef.from_mapping(
                _mapping(mapping["family_profile"], "source_native.family_profile")
            ),
            adapter_id=_string(mapping["adapter_id"], "source_native.adapter_id"),
            native_schema_version=_string(
                mapping["native_schema_version"], "source_native.native_schema_version"
            ),
            native_payload_locator=_string(
                mapping["native_payload_locator"], "source_native.native_payload_locator"
            ),
            native_payload_canonical_sha256=_hash(
                mapping["native_payload_canonical_sha256"],
                "source_native.native_payload_canonical_sha256",
            ),
            native_artifacts=tuple(
                NativeArtifactRef.from_mapping(_mapping(item, "source_native.native_artifact"))
                for item in _sequence(mapping["native_artifacts"], "source_native.native_artifacts")
            ),
            source_native_roundtrip_status=_string(
                mapping["source_native_roundtrip_status"],
                "source_native.source_native_roundtrip_status",
            ),
        )


@dataclass(frozen=True)
class BaselineContract:
    """Declared no-CST comparison basis and tolerances for one instance."""

    baseline_kind: str
    accepted_step_raw_sha256: str
    accepted_step_materialized: bool
    source_profile_contract: str = "source_native_curve_equivalence.v0"
    profile_max_deviation_tolerance_mm: float = 1.0e-6
    bbox_absolute_tolerance_mm: float = 0.3
    volume_relative_tolerance: float = 0.01
    surface_area_relative_tolerance: float = 0.01

    def __post_init__(self) -> None:
        if self.baseline_kind not in {
            "frozen_step_and_source_native_profile",
            "source_native_profile_with_unmaterialized_step",
        }:
            raise CompileContractError("unsupported baseline_kind")
        _hash(self.accepted_step_raw_sha256, "baseline.accepted_step_raw_sha256")
        if not isinstance(self.accepted_step_materialized, bool):
            raise CompileContractError("baseline.accepted_step_materialized must be boolean")
        if self.accepted_step_materialized != (
            self.baseline_kind == "frozen_step_and_source_native_profile"
        ):
            raise CompileContractError("baseline kind/materialization mismatch")
        if self.source_profile_contract != "source_native_curve_equivalence.v0":
            raise CompileContractError("unsupported source profile contract")
        for value, path in (
            (self.profile_max_deviation_tolerance_mm, "baseline.profile_tolerance_mm"),
            (self.bbox_absolute_tolerance_mm, "baseline.bbox_tolerance_mm"),
            (self.volume_relative_tolerance, "baseline.volume_tolerance"),
            (self.surface_area_relative_tolerance, "baseline.area_tolerance"),
        ):
            if _number(value, path) <= 0.0:
                raise CompileContractError(f"{path} must be positive")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "baseline_kind": self.baseline_kind,
            "accepted_step_raw_sha256": self.accepted_step_raw_sha256,
            "accepted_step_materialized": self.accepted_step_materialized,
            "source_profile_contract": self.source_profile_contract,
            "profile_max_deviation_tolerance_mm": self.profile_max_deviation_tolerance_mm,
            "bbox_absolute_tolerance_mm": self.bbox_absolute_tolerance_mm,
            "volume_relative_tolerance": self.volume_relative_tolerance,
            "surface_area_relative_tolerance": self.surface_area_relative_tolerance,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BaselineContract":
        mapping = _mapping(value, "baseline")
        _exact_keys(
            mapping,
            {
                "baseline_kind",
                "accepted_step_raw_sha256",
                "accepted_step_materialized",
                "source_profile_contract",
                "profile_max_deviation_tolerance_mm",
                "bbox_absolute_tolerance_mm",
                "volume_relative_tolerance",
                "surface_area_relative_tolerance",
            },
            "baseline",
        )
        materialized = mapping["accepted_step_materialized"]
        if not isinstance(materialized, bool):
            raise CompileContractError("baseline.accepted_step_materialized must be boolean")
        return cls(
            baseline_kind=_string(mapping["baseline_kind"], "baseline.baseline_kind"),
            accepted_step_raw_sha256=_hash(
                mapping["accepted_step_raw_sha256"], "baseline.accepted_step_raw_sha256"
            ),
            accepted_step_materialized=materialized,
            source_profile_contract=_string(
                mapping["source_profile_contract"], "baseline.source_profile_contract"
            ),
            profile_max_deviation_tolerance_mm=_number(
                mapping["profile_max_deviation_tolerance_mm"],
                "baseline.profile_max_deviation_tolerance_mm",
            ),
            bbox_absolute_tolerance_mm=_number(
                mapping["bbox_absolute_tolerance_mm"], "baseline.bbox_absolute_tolerance_mm"
            ),
            volume_relative_tolerance=_number(
                mapping["volume_relative_tolerance"], "baseline.volume_relative_tolerance"
            ),
            surface_area_relative_tolerance=_number(
                mapping["surface_area_relative_tolerance"],
                "baseline.surface_area_relative_tolerance",
            ),
        )


@dataclass(frozen=True)
class ContinuityRequirement:
    """One hard geometric-continuity requirement in a policy."""

    required_level: str
    enforcement: str = "hard"

    def __post_init__(self) -> None:
        if self.required_level not in {"C0", "G1", "G2"}:
            raise CompileContractError("unsupported continuity requirement level")
        if self.enforcement != "hard":
            raise CompileContractError("boundary continuity policy v0 supports hard enforcement only")

    def to_mapping(self) -> dict[str, str]:
        return {
            "required_continuity": self.required_level,
            "enforcement": self.enforcement,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContinuityRequirement":
        mapping = _mapping(value, "continuity_requirement")
        _exact_keys(
            mapping,
            {"required_continuity", "enforcement"},
            "continuity_requirement",
        )
        return cls(
            required_level=_string(
                mapping["required_continuity"],
                "continuity_requirement.required_continuity",
            ),
            enforcement=_string(
                mapping["enforcement"], "continuity_requirement.enforcement"
            ),
        )


@dataclass(frozen=True)
class ContinuityInterfaceOverride:
    """Explicit continuity intent for one semantic boundary interface."""

    interface_id: str
    requirement: ContinuityRequirement
    intentional_corner: bool
    rationale: str

    def __post_init__(self) -> None:
        _non_empty(self.interface_id, "continuity_override.interface_id")
        _non_empty(self.rationale, "continuity_override.rationale")
        if not isinstance(self.intentional_corner, bool):
            raise CompileContractError(
                "continuity_override.intentional_corner must be boolean"
            )
        if self.requirement.required_level == "C0" and not self.intentional_corner:
            raise CompileContractError(
                "C0 interface override requires an explicit intentional corner"
            )
        if self.intentional_corner and self.requirement.required_level != "C0":
            raise CompileContractError(
                "intentional-corner override must require C0"
            )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "interface_id": self.interface_id,
            **self.requirement.to_mapping(),
            "intentional_corner": self.intentional_corner,
            "rationale": self.rationale,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContinuityInterfaceOverride":
        mapping = _mapping(value, "continuity_override")
        _exact_keys(
            mapping,
            {
                "interface_id",
                "required_continuity",
                "enforcement",
                "intentional_corner",
                "rationale",
            },
            "continuity_override",
        )
        intentional_corner = mapping["intentional_corner"]
        if not isinstance(intentional_corner, bool):
            raise CompileContractError(
                "continuity_override.intentional_corner must be boolean"
            )
        return cls(
            interface_id=_string(
                mapping["interface_id"], "continuity_override.interface_id"
            ),
            requirement=ContinuityRequirement(
                required_level=_string(
                    mapping["required_continuity"],
                    "continuity_override.required_continuity",
                ),
                enforcement=_string(
                    mapping["enforcement"], "continuity_override.enforcement"
                ),
            ),
            intentional_corner=intentional_corner,
            rationale=_string(mapping["rationale"], "continuity_override.rationale"),
        )


@dataclass(frozen=True)
class BoundaryContinuityPolicy:
    """Versioned family policy independent of concrete curve implementations."""

    policy_id: str
    family_id: str
    internal_patch_policy: ContinuityRequirement
    semantic_interface_default: ContinuityRequirement
    semantic_interface_overrides: tuple[ContinuityInterfaceOverride, ...] = ()
    supported_levels: tuple[str, ...] = ("C0", "G1", "G2")
    policy_provenance: str = (
        "docs/RF-CEM_Technical_Record_2_TD1-TD3_Workbench_Desktop.md#td1"
    )
    schema_version: str = BOUNDARY_CONTINUITY_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BOUNDARY_CONTINUITY_POLICY_SCHEMA_VERSION:
            raise CompileContractError("unsupported boundary continuity policy schema")
        _non_empty(self.policy_id, "continuity_policy.policy_id")
        _non_empty(self.family_id, "continuity_policy.family_id")
        _non_empty(self.policy_provenance, "continuity_policy.policy_provenance")
        if self.internal_patch_policy.required_level != "G1":
            raise CompileContractError("internal patch default must be G1 hard")
        if self.semantic_interface_default.required_level != "G1":
            raise CompileContractError("semantic interface default must be G1 hard")
        if self.supported_levels != ("C0", "G1", "G2"):
            raise CompileContractError("continuity policy must support C0, G1 and G2")
        override_ids = [item.interface_id for item in self.semantic_interface_overrides]
        if len(override_ids) != len(set(override_ids)):
            raise CompileContractError("continuity interface overrides must be unique")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "family_id": self.family_id,
            "internal_patch_policy": self.internal_patch_policy.to_mapping(),
            "semantic_interface_default": self.semantic_interface_default.to_mapping(),
            "semantic_interface_overrides": [
                item.to_mapping() for item in self.semantic_interface_overrides
            ],
            "supported_levels": list(self.supported_levels),
            "policy_provenance": self.policy_provenance,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BoundaryContinuityPolicy":
        mapping = _mapping(value, "continuity_policy")
        _exact_keys(
            mapping,
            {
                "schema_version",
                "policy_id",
                "family_id",
                "internal_patch_policy",
                "semantic_interface_default",
                "semantic_interface_overrides",
                "supported_levels",
                "policy_provenance",
            },
            "continuity_policy",
        )
        return cls(
            schema_version=_string(
                mapping["schema_version"], "continuity_policy.schema_version"
            ),
            policy_id=_string(mapping["policy_id"], "continuity_policy.policy_id"),
            family_id=_string(mapping["family_id"], "continuity_policy.family_id"),
            internal_patch_policy=ContinuityRequirement.from_mapping(
                _mapping(
                    mapping["internal_patch_policy"],
                    "continuity_policy.internal_patch_policy",
                )
            ),
            semantic_interface_default=ContinuityRequirement.from_mapping(
                _mapping(
                    mapping["semantic_interface_default"],
                    "continuity_policy.semantic_interface_default",
                )
            ),
            semantic_interface_overrides=tuple(
                ContinuityInterfaceOverride.from_mapping(
                    _mapping(item, "continuity_policy.semantic_interface_override")
                )
                for item in _sequence(
                    mapping["semantic_interface_overrides"],
                    "continuity_policy.semantic_interface_overrides",
                )
            ),
            supported_levels=_string_tuple(
                mapping["supported_levels"], "continuity_policy.supported_levels"
            ),
            policy_provenance=_string(
                mapping["policy_provenance"],
                "continuity_policy.policy_provenance",
            ),
        )


def default_boundary_continuity_policy(
    family_id: str,
    *,
    overrides: tuple[ContinuityInterfaceOverride, ...] = (),
    policy_id: str | None = None,
) -> BoundaryContinuityPolicy:
    """Return the explicit RF-wall G1 policy used when no override is declared."""

    _non_empty(family_id, "continuity_policy.family_id")
    return BoundaryContinuityPolicy(
        policy_id=policy_id or f"{family_id}.boundary_continuity_policy.v0",
        family_id=family_id,
        internal_patch_policy=ContinuityRequirement("G1"),
        semantic_interface_default=ContinuityRequirement("G1"),
        semantic_interface_overrides=overrides,
    )


@dataclass(frozen=True)
class RegionRepresentationBinding:
    """One semantic-region-to-mathematical-representation compile input."""

    region_id: str
    region_order: int
    representation: CompositeRegionRepresentation
    source_native_segment_refs: tuple[str, ...]
    source_parameter_intervals: tuple[tuple[float, float], ...]
    start_landmark_id: str
    end_landmark_id: str
    internal_landmark_ids: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        _non_empty(self.region_id, "region_binding.region_id")
        _non_negative_integer(self.region_order, "region_binding.region_order")
        for value, path in (
            (self.start_landmark_id, "region_binding.start_landmark_id"),
            (self.end_landmark_id, "region_binding.end_landmark_id"),
        ):
            _non_empty(value, path)
        component_count = len(self.representation.components)
        if len(self.source_native_segment_refs) != component_count:
            raise CompileContractError("source-native segment/component cardinality mismatch")
        if len(self.source_parameter_intervals) != component_count:
            raise CompileContractError("source interval/component cardinality mismatch")
        if len(self.internal_landmark_ids) != max(0, component_count - 1):
            raise CompileContractError("internal landmark/component cardinality mismatch")
        if len(set(self.internal_landmark_ids)) != len(self.internal_landmark_ids):
            raise CompileContractError("internal landmark IDs must be unique")
        for source_ref in self.source_native_segment_refs:
            _non_empty(source_ref, "region_binding.source_native_segment_ref")
        for start, end in self.source_parameter_intervals:
            if not 0.0 <= _number(start, "region_binding.interval.start") < _number(
                end, "region_binding.interval.end"
            ) <= 1.0:
                raise CompileContractError("source parameter intervals must satisfy 0 <= start < end <= 1")
        if not self.evidence:
            raise CompileContractError("region representation binding requires evidence")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_order": self.region_order,
            "representation": self.representation.to_mapping(),
            "source_native_segment_refs": list(self.source_native_segment_refs),
            "source_parameter_intervals": [list(value) for value in self.source_parameter_intervals],
            "start_landmark_id": self.start_landmark_id,
            "end_landmark_id": self.end_landmark_id,
            "internal_landmark_ids": list(self.internal_landmark_ids),
            "evidence": [item.to_mapping() for item in self.evidence],
        }


@dataclass(frozen=True)
class CompileRequest:
    """Runtime request for the sole R2 topology/representation composition entry."""

    family_grammar: FamilyGrammar
    instance_graph: InstanceBoundaryGraph
    family_grammar_ref: ContractSourceRef
    instance_graph_ref: ContractSourceRef
    source_native_provenance: SourceNativeProvenance
    baseline: BaselineContract
    region_bindings: tuple[RegionRepresentationBinding, ...]
    continuity_policy: BoundaryContinuityPolicy | None = None
    compiler_version: str = COMPILER_VERSION

    def __post_init__(self) -> None:
        if self.compiler_version != COMPILER_VERSION:
            raise CompileContractError("unsupported compiler version")
        if self.family_grammar.family_id != self.instance_graph.family_id:
            raise CompileContractError("grammar and instance graph family mismatch")
        if self.family_grammar_ref.object_id != self.family_grammar.grammar_id:
            raise CompileContractError("family grammar ref object ID mismatch")
        if self.instance_graph_ref.object_id != self.instance_graph.instance_id:
            raise CompileContractError("instance graph ref object ID mismatch")
        graph_region_ids = [item.region_id for item in self.instance_graph.regions]
        binding_ids = [item.region_id for item in self.region_bindings]
        if binding_ids != graph_region_ids:
            raise CompileContractError("region bindings must exactly follow instance graph order")
        if [item.region_order for item in self.region_bindings] != list(range(len(binding_ids))):
            raise CompileContractError("region binding order must be contiguous from zero")
        policy = self.continuity_policy
        if policy is None:
            policy = default_boundary_continuity_policy(self.instance_graph.family_id)
            object.__setattr__(self, "continuity_policy", policy)
        if policy.family_id != self.instance_graph.family_id:
            raise CompileContractError("continuity policy and instance graph family mismatch")
        interface_ids = {
            _string(getattr(item, "interface_id", None), "interface.interface_id")
            for item in self.instance_graph.interfaces
        }
        unknown_overrides = {
            item.interface_id for item in policy.semantic_interface_overrides
        } - interface_ids
        if unknown_overrides:
            raise CompileContractError(
                f"continuity policy overrides unknown interfaces: {sorted(unknown_overrides)}"
            )

    @property
    def family_id(self) -> str:
        return self.instance_graph.family_id

    @property
    def instance_id(self) -> str:
        return self.instance_graph.instance_id

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": COMPILE_REQUEST_SCHEMA_VERSION,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "compiler_version": self.compiler_version,
            "family_grammar_ref": self.family_grammar_ref.to_mapping(),
            "instance_graph_ref": self.instance_graph_ref.to_mapping(),
            "source_native_provenance": self.source_native_provenance.to_mapping(),
            "baseline": self.baseline.to_mapping(),
            "region_bindings": [item.to_mapping() for item in self.region_bindings],
            "continuity_policy": self.continuity_policy.to_mapping(),
        }


@dataclass(frozen=True)
class LandmarkGeometryBinding:
    """Resolved profile coordinate shared by patches at one landmark."""

    landmark_id: str
    point: Point2D
    incident_patch_ids: tuple[str, ...]
    binding_role: str
    maximum_incident_gap_mm: float

    def __post_init__(self) -> None:
        _non_empty(self.landmark_id, "landmark_binding.landmark_id")
        if self.binding_role not in {"profile_endpoint", "region_interface", "internal_patch_join", "symmetry"}:
            raise CompileContractError("unsupported landmark binding role")
        if not self.incident_patch_ids or len(self.incident_patch_ids) > 2:
            raise CompileContractError("landmark binding requires one or two incident patches")
        if len(set(self.incident_patch_ids)) != len(self.incident_patch_ids):
            raise CompileContractError("landmark incident patch IDs must be unique")
        if _number(self.maximum_incident_gap_mm, "landmark_binding.maximum_incident_gap_mm") < 0.0:
            raise CompileContractError("landmark maximum gap must be non-negative")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "landmark_id": self.landmark_id,
            "point": self.point.to_mapping(),
            "incident_patch_ids": list(self.incident_patch_ids),
            "binding_role": self.binding_role,
            "maximum_incident_gap_mm": self.maximum_incident_gap_mm,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LandmarkGeometryBinding":
        mapping = _mapping(value, "landmark_binding")
        _exact_keys(
            mapping,
            {"landmark_id", "point", "incident_patch_ids", "binding_role", "maximum_incident_gap_mm"},
            "landmark_binding",
        )
        return cls(
            landmark_id=_string(mapping["landmark_id"], "landmark_binding.landmark_id"),
            point=Point2D.from_mapping(_mapping(mapping["point"], "landmark_binding.point")),
            incident_patch_ids=_string_tuple(
                mapping["incident_patch_ids"], "landmark_binding.incident_patch_ids"
            ),
            binding_role=_string(mapping["binding_role"], "landmark_binding.binding_role"),
            maximum_incident_gap_mm=_number(
                mapping["maximum_incident_gap_mm"],
                "landmark_binding.maximum_incident_gap_mm",
            ),
        )


@dataclass(frozen=True)
class EndpointConstraint:
    """One classified one-sided profile endpoint, never a fake continuity join."""

    constraint_id: str
    landmark_id: str
    endpoint_role: str
    incident_patch_id: str
    position: Point2D
    tangent: tuple[float, float]
    normal: tuple[float, float]
    termination_plane: str
    classification_source: str
    two_sided_continuity_applicable: bool = False

    def __post_init__(self) -> None:
        for value, path in (
            (self.constraint_id, "endpoint_constraint.constraint_id"),
            (self.landmark_id, "endpoint_constraint.landmark_id"),
            (self.incident_patch_id, "endpoint_constraint.incident_patch_id"),
            (self.classification_source, "endpoint_constraint.classification_source"),
        ):
            _non_empty(value, path)
        if self.endpoint_role not in {"profile_start", "profile_end"}:
            raise CompileContractError("unsupported profile endpoint role")
        if self.termination_plane != "constant_z":
            raise CompileContractError("unsupported endpoint termination plane")
        for vector, path in (
            (self.tangent, "endpoint_constraint.tangent"),
            (self.normal, "endpoint_constraint.normal"),
        ):
            if len(vector) != 2:
                raise CompileContractError(f"{path} must contain two components")
            length = math.hypot(
                _number(vector[0], f"{path}[0]"),
                _number(vector[1], f"{path}[1]"),
            )
            if abs(length - 1.0) > 1.0e-9:
                raise CompileContractError(f"{path} must be a unit vector")
        if self.two_sided_continuity_applicable is not False:
            raise CompileContractError(
                "profile endpoint cannot be classified as a two-sided continuity join"
            )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "landmark_id": self.landmark_id,
            "endpoint_role": self.endpoint_role,
            "incident_patch_id": self.incident_patch_id,
            "position": self.position.to_mapping(),
            "tangent": list(self.tangent),
            "normal": list(self.normal),
            "termination_plane": self.termination_plane,
            "classification_source": self.classification_source,
            "two_sided_continuity_applicable": self.two_sided_continuity_applicable,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EndpointConstraint":
        mapping = _mapping(value, "endpoint_constraint")
        required = set(cls.__dataclass_fields__)
        _exact_keys(mapping, required, "endpoint_constraint")
        tangent = _number_pair(mapping["tangent"], "endpoint_constraint.tangent")
        normal = _number_pair(mapping["normal"], "endpoint_constraint.normal")
        applicable = mapping["two_sided_continuity_applicable"]
        if not isinstance(applicable, bool):
            raise CompileContractError(
                "endpoint_constraint.two_sided_continuity_applicable must be boolean"
            )
        return cls(
            constraint_id=_string(
                mapping["constraint_id"], "endpoint_constraint.constraint_id"
            ),
            landmark_id=_string(
                mapping["landmark_id"], "endpoint_constraint.landmark_id"
            ),
            endpoint_role=_string(
                mapping["endpoint_role"], "endpoint_constraint.endpoint_role"
            ),
            incident_patch_id=_string(
                mapping["incident_patch_id"],
                "endpoint_constraint.incident_patch_id",
            ),
            position=Point2D.from_mapping(
                _mapping(mapping["position"], "endpoint_constraint.position")
            ),
            tangent=tangent,
            normal=normal,
            termination_plane=_string(
                mapping["termination_plane"],
                "endpoint_constraint.termination_plane",
            ),
            classification_source=_string(
                mapping["classification_source"],
                "endpoint_constraint.classification_source",
            ),
            two_sided_continuity_applicable=applicable,
        )


@dataclass(frozen=True)
class ContinuityCheck:
    """C0/G1/G2 diagnostic at one deterministic oriented patch join."""

    check_id: str
    landmark_id: str
    left_patch_id: str
    right_patch_id: str
    join_scope: str
    required_level: str
    c0_gap_mm: float
    tangent_angle_deg: float
    curvature_delta_per_mm: float
    c0_tolerance_mm: float
    g1_tolerance_deg: float
    g2_tolerance_per_mm: float
    c0_pass: bool
    g1_pass: bool
    g2_pass: bool
    required_pass: bool
    requirement_source: str = "legacy_source_native_segment_rule"
    policy_ref: str = "legacy.compile_record.v0"
    intentional_corner: bool = False
    enforcement: str = "hard"
    interface_id: str | None = None

    def __post_init__(self) -> None:
        for value, path in (
            (self.check_id, "continuity.check_id"),
            (self.landmark_id, "continuity.landmark_id"),
            (self.left_patch_id, "continuity.left_patch_id"),
            (self.right_patch_id, "continuity.right_patch_id"),
        ):
            _non_empty(value, path)
        if self.join_scope not in {"cross_region", "within_region"}:
            raise CompileContractError("unsupported continuity join scope")
        if self.required_level not in {"C0", "G1", "G2"}:
            raise CompileContractError("unsupported continuity required level")
        if self.requirement_source not in {
            "legacy_source_native_segment_rule",
            "internal_patch_policy",
            "semantic_interface_default",
            "semantic_interface_override",
        }:
            raise CompileContractError("unsupported continuity requirement source")
        _non_empty(self.policy_ref, "continuity.policy_ref")
        if not isinstance(self.intentional_corner, bool):
            raise CompileContractError("continuity.intentional_corner must be boolean")
        if self.enforcement != "hard":
            raise CompileContractError("continuity enforcement must be hard")
        if self.join_scope == "within_region" and self.interface_id is not None:
            raise CompileContractError("within-region continuity cannot reference an interface")
        if self.join_scope == "cross_region":
            if self.requirement_source == "legacy_source_native_segment_rule":
                if self.interface_id is not None:
                    raise CompileContractError("legacy continuity cannot add an interface ID")
            else:
                _non_empty(self.interface_id, "continuity.interface_id")
        if self.intentional_corner:
            if self.required_level != "C0" or self.requirement_source != "semantic_interface_override":
                raise CompileContractError(
                    "intentional corner requires an explicit C0 interface override"
                )
        for value, path in (
            (self.c0_gap_mm, "continuity.c0_gap_mm"),
            (self.tangent_angle_deg, "continuity.tangent_angle_deg"),
            (self.curvature_delta_per_mm, "continuity.curvature_delta_per_mm"),
        ):
            if _number(value, path) < 0.0:
                raise CompileContractError(f"{path} must be non-negative")
        for value, path in (
            (self.c0_tolerance_mm, "continuity.c0_tolerance_mm"),
            (self.g1_tolerance_deg, "continuity.g1_tolerance_deg"),
            (self.g2_tolerance_per_mm, "continuity.g2_tolerance_per_mm"),
        ):
            if _number(value, path) <= 0.0:
                raise CompileContractError(f"{path} must be positive")
        for value, path in (
            (self.c0_pass, "continuity.c0_pass"),
            (self.g1_pass, "continuity.g1_pass"),
            (self.g2_pass, "continuity.g2_pass"),
            (self.required_pass, "continuity.required_pass"),
        ):
            if not isinstance(value, bool):
                raise CompileContractError(f"{path} must be boolean")

    def to_mapping(self, *, legacy: bool = False) -> dict[str, Any]:
        mapping = {
            "check_id": self.check_id,
            "landmark_id": self.landmark_id,
            "left_patch_id": self.left_patch_id,
            "right_patch_id": self.right_patch_id,
            "join_scope": self.join_scope,
            "required_level": self.required_level,
            "c0_gap_mm": self.c0_gap_mm,
            "tangent_angle_deg": self.tangent_angle_deg,
            "curvature_delta_per_mm": self.curvature_delta_per_mm,
            "c0_tolerance_mm": self.c0_tolerance_mm,
            "g1_tolerance_deg": self.g1_tolerance_deg,
            "g2_tolerance_per_mm": self.g2_tolerance_per_mm,
            "c0_pass": self.c0_pass,
            "g1_pass": self.g1_pass,
            "g2_pass": self.g2_pass,
            "required_pass": self.required_pass,
        }
        if not legacy:
            mapping.update(
                {
                    "requirement_source": self.requirement_source,
                    "policy_ref": self.policy_ref,
                    "intentional_corner": self.intentional_corner,
                    "enforcement": self.enforcement,
                    "interface_id": self.interface_id,
                }
            )
        return mapping

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], *, legacy: bool = False
    ) -> "ContinuityCheck":
        mapping = _mapping(value, "continuity")
        required = {
            field
            for field in cls.__dataclass_fields__
            if field
            not in {
                "requirement_source",
                "policy_ref",
                "intentional_corner",
                "enforcement",
                "interface_id",
            }
        }
        if not legacy:
            required.update(
                {
                    "requirement_source",
                    "policy_ref",
                    "intentional_corner",
                    "enforcement",
                    "interface_id",
                }
            )
        _exact_keys(mapping, required, "continuity")
        boolean_fields = {"c0_pass", "g1_pass", "g2_pass", "required_pass"}
        for field in boolean_fields:
            if not isinstance(mapping[field], bool):
                raise CompileContractError(f"continuity.{field} must be boolean")
        return cls(
            check_id=_string(mapping["check_id"], "continuity.check_id"),
            landmark_id=_string(mapping["landmark_id"], "continuity.landmark_id"),
            left_patch_id=_string(mapping["left_patch_id"], "continuity.left_patch_id"),
            right_patch_id=_string(mapping["right_patch_id"], "continuity.right_patch_id"),
            join_scope=_string(mapping["join_scope"], "continuity.join_scope"),
            required_level=_string(mapping["required_level"], "continuity.required_level"),
            c0_gap_mm=_number(mapping["c0_gap_mm"], "continuity.c0_gap_mm"),
            tangent_angle_deg=_number(
                mapping["tangent_angle_deg"], "continuity.tangent_angle_deg"
            ),
            curvature_delta_per_mm=_number(
                mapping["curvature_delta_per_mm"], "continuity.curvature_delta_per_mm"
            ),
            c0_tolerance_mm=_number(
                mapping["c0_tolerance_mm"], "continuity.c0_tolerance_mm"
            ),
            g1_tolerance_deg=_number(
                mapping["g1_tolerance_deg"], "continuity.g1_tolerance_deg"
            ),
            g2_tolerance_per_mm=_number(
                mapping["g2_tolerance_per_mm"], "continuity.g2_tolerance_per_mm"
            ),
            c0_pass=mapping["c0_pass"],
            g1_pass=mapping["g1_pass"],
            g2_pass=mapping["g2_pass"],
            required_pass=mapping["required_pass"],
            requirement_source=(
                "legacy_source_native_segment_rule"
                if legacy
                else _string(
                    mapping["requirement_source"], "continuity.requirement_source"
                )
            ),
            policy_ref=(
                "legacy.compile_record.v0"
                if legacy
                else _string(mapping["policy_ref"], "continuity.policy_ref")
            ),
            intentional_corner=(False if legacy else mapping["intentional_corner"]),
            enforcement=(
                "hard"
                if legacy
                else _string(mapping["enforcement"], "continuity.enforcement")
            ),
            interface_id=(
                None
                if legacy or mapping["interface_id"] is None
                else _string(mapping["interface_id"], "continuity.interface_id")
            ),
        )


@dataclass(frozen=True)
class OutputArtifactRef:
    """Exact bundle-relative compiler output artifact binding."""

    role: str
    path: str
    media_type: str
    raw_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _non_empty(self.role, "output_artifact.role")
        _relative_path(self.path, "output_artifact.path")
        _non_empty(self.media_type, "output_artifact.media_type")
        _hash(self.raw_sha256, "output_artifact.raw_sha256")
        _non_negative_integer(self.size_bytes, "output_artifact.size_bytes")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "media_type": self.media_type,
            "raw_sha256": self.raw_sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OutputArtifactRef":
        mapping = _mapping(value, "output_artifact")
        _exact_keys(mapping, {"role", "path", "media_type", "raw_sha256", "size_bytes"}, "output_artifact")
        return cls(
            role=_string(mapping["role"], "output_artifact.role"),
            path=_relative_path(mapping["path"], "output_artifact.path"),
            media_type=_string(mapping["media_type"], "output_artifact.media_type"),
            raw_sha256=_hash(mapping["raw_sha256"], "output_artifact.raw_sha256"),
            size_bytes=_integer(mapping["size_bytes"], "output_artifact.size_bytes"),
        )


@dataclass(frozen=True)
class CompileRecord:
    """Strict, hash-identified result of one R2 geometry compilation."""

    family_id: str
    instance_id: str
    compiler_version: str
    family_grammar_ref: ContractSourceRef
    instance_graph_ref: ContractSourceRef
    source_native_provenance: SourceNativeProvenance
    baseline: BaselineContract
    region_geometries: tuple[RegionGeometry, ...]
    landmark_bindings: tuple[LandmarkGeometryBinding, ...]
    continuity_checks: tuple[ContinuityCheck, ...]
    geometry_validation: Mapping[str, Any]
    baseline_comparison: Mapping[str, Any]
    output_artifacts: tuple[OutputArtifactRef, ...]
    warnings: tuple[str, ...]
    status: str
    live_cst_status: str = "not_run"
    physical_acceptance_status: str = "not_established"
    parent_compile_id: str | None = None
    compile_id: str = ""
    content_sha256: str = ""
    continuity_policy: BoundaryContinuityPolicy | None = None
    endpoint_constraints: tuple[EndpointConstraint, ...] = ()
    schema_version: str = COMPILE_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, path in (
            (self.family_id, "compile_record.family_id"),
            (self.instance_id, "compile_record.instance_id"),
        ):
            _non_empty(value, path)
        if self.schema_version not in {
            LEGACY_COMPILE_RECORD_SCHEMA_VERSION,
            COMPILE_RECORD_SCHEMA_VERSION,
        }:
            raise CompileContractError("unsupported compile record schema")
        expected_compiler = (
            LEGACY_COMPILER_VERSION
            if self.schema_version == LEGACY_COMPILE_RECORD_SCHEMA_VERSION
            else COMPILER_VERSION
        )
        if self.compiler_version != expected_compiler:
            raise CompileContractError("unsupported compiler version in compile record")
        if self.status not in {"pass", "failed"}:
            raise CompileContractError("compile record status must be pass or failed")
        if self.live_cst_status != "not_run":
            raise CompileContractError("R2 compile record live_cst_status must be not_run")
        if self.physical_acceptance_status != "not_established":
            raise CompileContractError(
                "R2 compile record physical_acceptance_status must be not_established"
            )
        if self.parent_compile_id is not None:
            _non_empty(self.parent_compile_id, "compile_record.parent_compile_id")
        if not self.region_geometries:
            raise CompileContractError("compile record requires RegionGeometry outputs")
        region_orders = [item.region_order for item in self.region_geometries]
        if region_orders != list(range(len(region_orders))):
            raise CompileContractError("compile record region order must be contiguous")
        owner_ids = [item.owner_region_id for item in self.region_geometries]
        if len(owner_ids) != len(set(owner_ids)):
            raise CompileContractError("compile record has duplicate region owners")
        patches = [patch for geometry in self.region_geometries for patch in geometry.patches]
        patch_ids = [patch.patch_id for patch in patches]
        if len(patch_ids) != len(set(patch_ids)):
            raise CompileContractError("compile record has duplicate patch IDs")
        if [patch.global_order for patch in patches] != list(range(len(patches))):
            raise CompileContractError("compile record global patch order must be contiguous")
        if not self.landmark_bindings:
            raise CompileContractError("compile record requires resolved landmarks")
        landmark_ids = [item.landmark_id for item in self.landmark_bindings]
        if len(landmark_ids) != len(set(landmark_ids)):
            raise CompileContractError("compile record has duplicate landmark bindings")
        for check in self.continuity_checks:
            if check.left_patch_id not in patch_ids or check.right_patch_id not in patch_ids:
                raise CompileContractError("continuity check references an unknown patch")
        if self.schema_version == LEGACY_COMPILE_RECORD_SCHEMA_VERSION:
            if self.continuity_policy is not None or self.endpoint_constraints:
                raise CompileContractError(
                    "legacy compile record cannot contain v1 policy or endpoint contracts"
                )
            if any(
                check.requirement_source != "legacy_source_native_segment_rule"
                for check in self.continuity_checks
            ):
                raise CompileContractError("legacy continuity source marker changed")
        else:
            if self.continuity_policy is None:
                raise CompileContractError("compile_record.v1 requires a continuity policy")
            if self.continuity_policy.family_id != self.family_id:
                raise CompileContractError("compile record continuity policy family mismatch")
            if len(self.endpoint_constraints) != 2 or {
                item.endpoint_role for item in self.endpoint_constraints
            } != {"profile_start", "profile_end"}:
                raise CompileContractError(
                    "compile_record.v1 requires classified start and end constraints"
                )
            endpoint_landmarks = {item.landmark_id for item in self.endpoint_constraints}
            if endpoint_landmarks & {item.landmark_id for item in self.continuity_checks}:
                raise CompileContractError(
                    "profile endpoint was emitted as a two-sided continuity check"
                )
            for endpoint in self.endpoint_constraints:
                if endpoint.incident_patch_id not in patch_ids:
                    raise CompileContractError(
                        "endpoint constraint references an unknown incident patch"
                    )
            for check in self.continuity_checks:
                if check.policy_ref != self.continuity_policy.policy_id:
                    raise CompileContractError("continuity check policy reference mismatch")
        _finite_json(self.geometry_validation, "compile_record.geometry_validation")
        _finite_json(self.baseline_comparison, "compile_record.baseline_comparison")
        if not self.output_artifacts:
            raise CompileContractError("compile record requires output artifacts")
        if any(not isinstance(item, str) or not item.strip() for item in self.warnings):
            raise CompileContractError("compile record warnings must be non-empty strings")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.instance_id}.compile.{content[:16]}"
        if self.content_sha256:
            if self.content_sha256 != content:
                raise CompileContractError("compile record content SHA-256 mismatch")
        else:
            object.__setattr__(self, "content_sha256", content)
        if self.compile_id:
            if self.compile_id != expected_id:
                raise CompileContractError("compile record ID mismatch")
        else:
            object.__setattr__(self, "compile_id", expected_id)
        if self.status == "pass":
            if any(not check.required_pass for check in self.continuity_checks):
                raise CompileContractError("passing compile record has failed required continuity")
            if self.geometry_validation.get("pass") is not True:
                raise CompileContractError("passing compile record has failed geometry validation")
            if self.baseline_comparison.get("pass") is not True:
                raise CompileContractError("passing compile record has failed baseline comparison")

    @property
    def patch_count(self) -> int:
        return sum(item.patch_count for item in self.region_geometries)

    def _content_mapping(self) -> dict[str, Any]:
        mapping = {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "compiler_version": self.compiler_version,
            "family_grammar_ref": self.family_grammar_ref.to_mapping(),
            "instance_graph_ref": self.instance_graph_ref.to_mapping(),
            "source_native_provenance": self.source_native_provenance.to_mapping(),
            "baseline": self.baseline.to_mapping(),
            "region_geometries": [item.to_mapping() for item in self.region_geometries],
            "landmark_bindings": [item.to_mapping() for item in self.landmark_bindings],
            "continuity_checks": [
                item.to_mapping(
                    legacy=self.schema_version == LEGACY_COMPILE_RECORD_SCHEMA_VERSION
                )
                for item in self.continuity_checks
            ],
            "geometry_validation": dict(self.geometry_validation),
            "baseline_comparison": dict(self.baseline_comparison),
            "output_artifacts": [item.to_mapping() for item in self.output_artifacts],
            "warnings": list(self.warnings),
            "status": self.status,
            "live_cst_status": self.live_cst_status,
            "physical_acceptance_status": self.physical_acceptance_status,
            "parent_compile_id": self.parent_compile_id,
            "region_count": len(self.region_geometries),
            "patch_count": self.patch_count,
        }
        if self.schema_version == COMPILE_RECORD_SCHEMA_VERSION:
            if self.continuity_policy is None:
                raise CompileContractError("compile_record.v1 requires a continuity policy")
            mapping.update(
                {
                    "continuity_policy": self.continuity_policy.to_mapping(),
                    "endpoint_constraints": [
                        item.to_mapping() for item in self.endpoint_constraints
                    ],
                }
            )
        return mapping

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "compile_id": self.compile_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CompileRecord":
        mapping = _mapping(value, "compile_record")
        schema_version = _string(
            mapping.get("schema_version"), "compile_record.schema_version"
        )
        if schema_version not in {
            LEGACY_COMPILE_RECORD_SCHEMA_VERSION,
            COMPILE_RECORD_SCHEMA_VERSION,
        }:
            raise CompileContractError("unsupported compile record schema")
        required = {
            "schema_version",
            "family_id",
            "instance_id",
            "compiler_version",
            "family_grammar_ref",
            "instance_graph_ref",
            "source_native_provenance",
            "baseline",
            "region_geometries",
            "landmark_bindings",
            "continuity_checks",
            "geometry_validation",
            "baseline_comparison",
            "output_artifacts",
            "warnings",
            "status",
            "live_cst_status",
            "physical_acceptance_status",
            "parent_compile_id",
            "region_count",
            "patch_count",
            "compile_id",
            "content_sha256",
        }
        if schema_version == COMPILE_RECORD_SCHEMA_VERSION:
            required.update({"continuity_policy", "endpoint_constraints"})
        _exact_keys(mapping, required, "compile_record")
        parent = mapping["parent_compile_id"]
        if parent is not None and not isinstance(parent, str):
            raise CompileContractError("parent_compile_id must be a string or null")
        result = cls(
            family_id=_string(mapping["family_id"], "compile_record.family_id"),
            instance_id=_string(mapping["instance_id"], "compile_record.instance_id"),
            compiler_version=_string(
                mapping["compiler_version"], "compile_record.compiler_version"
            ),
            family_grammar_ref=ContractSourceRef.from_mapping(
                _mapping(mapping["family_grammar_ref"], "compile_record.family_grammar_ref")
            ),
            instance_graph_ref=ContractSourceRef.from_mapping(
                _mapping(mapping["instance_graph_ref"], "compile_record.instance_graph_ref")
            ),
            source_native_provenance=SourceNativeProvenance.from_mapping(
                _mapping(
                    mapping["source_native_provenance"],
                    "compile_record.source_native_provenance",
                )
            ),
            baseline=BaselineContract.from_mapping(
                _mapping(mapping["baseline"], "compile_record.baseline")
            ),
            region_geometries=tuple(
                RegionGeometry.from_mapping(_mapping(item, "compile_record.region_geometry"))
                for item in _sequence(mapping["region_geometries"], "compile_record.region_geometries")
            ),
            landmark_bindings=tuple(
                LandmarkGeometryBinding.from_mapping(
                    _mapping(item, "compile_record.landmark_binding")
                )
                for item in _sequence(mapping["landmark_bindings"], "compile_record.landmark_bindings")
            ),
            continuity_checks=tuple(
                ContinuityCheck.from_mapping(
                    _mapping(item, "compile_record.continuity"),
                    legacy=schema_version == LEGACY_COMPILE_RECORD_SCHEMA_VERSION,
                )
                for item in _sequence(mapping["continuity_checks"], "compile_record.continuity_checks")
            ),
            geometry_validation=dict(
                _mapping(mapping["geometry_validation"], "compile_record.geometry_validation")
            ),
            baseline_comparison=dict(
                _mapping(mapping["baseline_comparison"], "compile_record.baseline_comparison")
            ),
            output_artifacts=tuple(
                OutputArtifactRef.from_mapping(_mapping(item, "compile_record.output_artifact"))
                for item in _sequence(mapping["output_artifacts"], "compile_record.output_artifacts")
            ),
            warnings=_string_tuple(mapping["warnings"], "compile_record.warnings"),
            status=_string(mapping["status"], "compile_record.status"),
            live_cst_status=_string(
                mapping["live_cst_status"], "compile_record.live_cst_status"
            ),
            physical_acceptance_status=_string(
                mapping["physical_acceptance_status"],
                "compile_record.physical_acceptance_status",
            ),
            parent_compile_id=parent,
            compile_id=_string(mapping["compile_id"], "compile_record.compile_id"),
            content_sha256=_hash(mapping["content_sha256"], "compile_record.content_sha256"),
            continuity_policy=(
                None
                if schema_version == LEGACY_COMPILE_RECORD_SCHEMA_VERSION
                else BoundaryContinuityPolicy.from_mapping(
                    _mapping(
                        mapping["continuity_policy"],
                        "compile_record.continuity_policy",
                    )
                )
            ),
            endpoint_constraints=(
                ()
                if schema_version == LEGACY_COMPILE_RECORD_SCHEMA_VERSION
                else tuple(
                    EndpointConstraint.from_mapping(
                        _mapping(item, "compile_record.endpoint_constraint")
                    )
                    for item in _sequence(
                        mapping["endpoint_constraints"],
                        "compile_record.endpoint_constraints",
                    )
                )
            ),
            schema_version=schema_version,
        )
        if mapping["region_count"] != len(result.region_geometries):
            raise CompileContractError("compile record region_count mismatch")
        if mapping["patch_count"] != result.patch_count:
            raise CompileContractError("compile record patch_count mismatch")
        return result


def load_compile_record(path: Path) -> CompileRecord:
    """Load one strict finite ``compile_record.v0`` JSON artifact."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CompileContractError(f"cannot read compile record: {path}") from exc
    return CompileRecord.from_mapping(_mapping(value, "compile_record"))


def _finite_json(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _number(value, path)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CompileContractError(f"{path} has a non-string key")
            _finite_json(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _finite_json(item, f"{path}[{index}]")
        return
    raise CompileContractError(f"{path} contains a non-JSON value")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _relative_path(value: object, path: str) -> str:
    result = _non_empty(value, path).replace("\\", "/")
    pure = PurePosixPath(result)
    if pure.is_absolute() or ".." in pure.parts or (pure.parts and ":" in pure.parts[0]):
        raise CompileContractError(f"{path} must be repository/bundle relative")
    return result


def _hash(value: object, path: str) -> str:
    result = _string(value, path)
    if not _HASH_RE.fullmatch(result):
        raise CompileContractError(f"{path} must be a lowercase SHA-256")
    return result


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompileContractError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise CompileContractError(f"{path} must be finite")
    return result


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompileContractError(f"{path} must be an integer")
    return value


def _non_negative_integer(value: object, path: str) -> None:
    if _integer(value, path) < 0:
        raise CompileContractError(f"{path} must be non-negative")


def _non_empty(value: object, path: str) -> str:
    result = _string(value, path)
    if not result.strip():
        raise CompileContractError(f"{path} must not be empty")
    return result


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise CompileContractError(f"{path} must be a string")
    return value


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{path}[]") for item in _sequence(value, path))


def _number_pair(value: object, path: str) -> tuple[float, float]:
    values = _sequence(value, path)
    if len(values) != 2:
        raise CompileContractError(f"{path} must contain two values")
    return (_number(values[0], f"{path}[0]"), _number(values[1], f"{path}[1]"))


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompileContractError(f"{path} must be an object")
    return value


def _sequence(value: object, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CompileContractError(f"{path} must be an array")
    return value


def _exact_keys(mapping: Mapping[str, Any], required: set[str], path: str) -> None:
    actual = set(mapping)
    if actual != required:
        raise CompileContractError(
            f"{path} keys mismatch; missing={sorted(required - actual)}, "
            f"unexpected={sorted(actual - required)}"
        )


__all__ = [
    "BaselineContract",
    "BOUNDARY_CONTINUITY_POLICY_SCHEMA_VERSION",
    "BoundaryContinuityPolicy",
    "COMPILE_RECORD_SCHEMA_VERSION",
    "COMPILE_REQUEST_SCHEMA_VERSION",
    "COMPILER_VERSION",
    "CompileContractError",
    "CompileRecord",
    "CompileRequest",
    "ContinuityCheck",
    "ContinuityInterfaceOverride",
    "ContinuityRequirement",
    "ContractSourceRef",
    "EndpointConstraint",
    "LandmarkGeometryBinding",
    "LEGACY_COMPILE_RECORD_SCHEMA_VERSION",
    "LEGACY_COMPILER_VERSION",
    "load_compile_record",
    "NativeArtifactRef",
    "OutputArtifactRef",
    "RegionRepresentationBinding",
    "SourceNativeProvenance",
    "default_boundary_continuity_policy",
]
