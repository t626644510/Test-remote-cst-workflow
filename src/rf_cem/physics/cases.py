"""Physics-case, instance-link, and replay provenance contracts for R5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .common import (
    PhysicsContractError,
    enum,
    exact_keys,
    mapping,
    optional_string,
    positive_integer,
    sequence,
    string,
    string_tuple,
)
from .identity import bind_identity, identity_ref
from .references import (
    BoundaryAssignment,
    ContractRef,
    ExternalArtifactRef,
    GeometryBinding,
    MaterialAssignment,
    MeshDefinition,
    SolverDefinition,
)


PHYSICS_CASE_SCHEMA_VERSION = "physics_case.v0"
RESULT_PROVENANCE_SCHEMA_VERSION = "result_provenance.v0"
PHYSICS_LINK_STATUS_SCHEMA_VERSION = "physics_link_status.v0"

CASE_STATUSES = frozenset({"planned_not_run", "completed", "failed"})
AUTHORIZATION_STATUSES = frozenset(
    {"not_requested", "not_authorized", "authorized"}
)
RUN_STATUSES = frozenset({"not_run", "completed", "failed"})
LINK_STATUSES = frozenset({"planned_not_run", "linked", "not_linked"})


@dataclass(frozen=True)
class PhysicsCase:
    """Complete geometry and solver setup identity for one eigenmode run."""

    geometry: GeometryBinding
    solver: SolverDefinition
    solver_recipe: str
    materials: tuple[MaterialAssignment, ...]
    boundaries: tuple[BoundaryAssignment, ...]
    mesh: MeshDefinition
    requested_mode_count: int
    case_status: str
    authorization_status: str
    limitations: tuple[str, ...]
    analysis_type: str = "eigenmode"
    physics_case_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if self.analysis_type != "eigenmode":
            raise PhysicsContractError("R5 v0 supports only eigenmode physics cases")
        string(self.solver_recipe, "physics_case.solver_recipe")
        positive_integer(self.requested_mode_count, "physics_case.requested_mode_count")
        enum(self.case_status, CASE_STATUSES, "physics_case.case_status")
        enum(
            self.authorization_status,
            AUTHORIZATION_STATUSES,
            "physics_case.authorization_status",
        )
        string_tuple(self.limitations, "physics_case.limitations")
        if not self.materials:
            raise PhysicsContractError("physics case requires material assignments")
        if not self.boundaries:
            raise PhysicsContractError("physics case requires boundary assignments")
        material_roles = [item.role for item in self.materials]
        if len(material_roles) != len(set(material_roles)):
            raise PhysicsContractError("physics case material roles must be unique")
        boundary_selections = [item.selection for item in self.boundaries]
        if len(boundary_selections) != len(set(boundary_selections)):
            raise PhysicsContractError("physics case boundary selections must be unique")
        if self.case_status == "completed":
            if self.authorization_status != "authorized":
                raise PhysicsContractError("completed physics case requires authorization")
            if self.solver.settings_status != "established" or not self.solver.build:
                raise PhysicsContractError(
                    "completed physics case requires established solver version/build"
                )
            settings = [
                *(item.settings_status for item in self.materials),
                *(item.settings_status for item in self.boundaries),
                self.mesh.settings_status,
            ]
            if any(status != "established" for status in settings):
                raise PhysicsContractError(
                    "completed physics case requires established material, boundary, and mesh settings"
                )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="physics_case_id",
            id_prefix=f"{self.geometry.instance_id}.physics_case",
            label="physics case",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": PHYSICS_CASE_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "analysis_type": self.analysis_type,
            "solver": self.solver.to_mapping(),
            "solver_recipe": self.solver_recipe,
            "materials": [item.to_mapping() for item in self.materials],
            "boundaries": [item.to_mapping() for item in self.boundaries],
            "mesh": self.mesh.to_mapping(),
            "requested_mode_count": self.requested_mode_count,
            "case_status": self.case_status,
            "authorization_status": self.authorization_status,
            "limitations": list(self.limitations),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "physics_case_id": self.physics_case_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="physics_case",
            schema_version=PHYSICS_CASE_SCHEMA_VERSION,
            object_id=self.physics_case_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PhysicsCase":
        value = mapping(value, "physics_case")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "analysis_type",
                "solver",
                "solver_recipe",
                "materials",
                "boundaries",
                "mesh",
                "requested_mode_count",
                "case_status",
                "authorization_status",
                "limitations",
                "physics_case_id",
                "content_sha256",
            },
            "physics_case",
        )
        if value["schema_version"] != PHYSICS_CASE_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported physics case schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            analysis_type=string(value["analysis_type"], "physics_case.analysis_type"),
            solver=SolverDefinition.from_mapping(mapping(value["solver"], "solver")),
            solver_recipe=string(value["solver_recipe"], "physics_case.solver_recipe"),
            materials=tuple(
                MaterialAssignment.from_mapping(mapping(item, "material"))
                for item in sequence(value["materials"], "physics_case.materials")
            ),
            boundaries=tuple(
                BoundaryAssignment.from_mapping(mapping(item, "boundary"))
                for item in sequence(value["boundaries"], "physics_case.boundaries")
            ),
            mesh=MeshDefinition.from_mapping(mapping(value["mesh"], "mesh")),
            requested_mode_count=positive_integer(
                value["requested_mode_count"], "physics_case.requested_mode_count"
            ),
            case_status=enum(value["case_status"], CASE_STATUSES, "physics_case.case_status"),
            authorization_status=enum(
                value["authorization_status"],
                AUTHORIZATION_STATUSES,
                "physics_case.authorization_status",
            ),
            limitations=string_tuple(value["limitations"], "physics_case.limitations"),
            physics_case_id=string(value["physics_case_id"], "physics_case.physics_case_id"),
            content_sha256=string(value["content_sha256"], "physics_case.content_sha256"),
        )


@dataclass(frozen=True)
class ResultProvenance:
    """Replay identity for one solver execution and extraction boundary."""

    geometry: GeometryBinding
    physics_case_ref: ContractRef
    solver: SolverDefinition
    run_status: str
    authorization_status: str
    execution_id: str
    started_at: str | None
    completed_at: str | None
    extraction_software: str
    source_artifacts: tuple[ExternalArtifactRef, ...]
    log_artifacts: tuple[ExternalArtifactRef, ...]
    replay_command: str
    limitations: tuple[str, ...]
    provenance_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.physics_case_ref.contract_kind != "physics_case"
            or self.physics_case_ref.schema_version != PHYSICS_CASE_SCHEMA_VERSION
        ):
            raise PhysicsContractError("result provenance requires physics_case.v0")
        if not self.physics_case_ref.object_id.startswith(self.geometry.instance_id + "."):
            raise PhysicsContractError("result provenance case does not bind its geometry")
        enum(self.run_status, RUN_STATUSES, "provenance.run_status")
        enum(
            self.authorization_status,
            AUTHORIZATION_STATUSES,
            "provenance.authorization_status",
        )
        string(self.execution_id, "provenance.execution_id")
        optional_string(self.started_at, "provenance.started_at")
        optional_string(self.completed_at, "provenance.completed_at")
        string(self.extraction_software, "provenance.extraction_software")
        string(self.replay_command, "provenance.replay_command")
        string_tuple(self.limitations, "provenance.limitations")
        roles = [item.role for item in (*self.source_artifacts, *self.log_artifacts)]
        if len(roles) != len(set(roles)):
            raise PhysicsContractError("provenance artifact roles must be unique")
        if self.run_status == "completed":
            if self.authorization_status != "authorized":
                raise PhysicsContractError("completed provenance requires authorization")
            if not self.started_at or not self.completed_at:
                raise PhysicsContractError("completed provenance requires execution timestamps")
            if not self.source_artifacts:
                raise PhysicsContractError("completed provenance requires replay source artifacts")
            if self.solver.settings_status != "established" or not self.solver.build:
                raise PhysicsContractError("completed provenance requires exact solver build")
        elif self.run_status == "not_run" and (self.started_at or self.completed_at):
            raise PhysicsContractError("not-run provenance cannot have execution timestamps")
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="provenance_id",
            id_prefix=f"{self.geometry.instance_id}.result_provenance",
            label="result provenance",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_PROVENANCE_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "physics_case_ref": self.physics_case_ref.to_mapping(),
            "solver": self.solver.to_mapping(),
            "run_status": self.run_status,
            "authorization_status": self.authorization_status,
            "execution_id": self.execution_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "extraction_software": self.extraction_software,
            "source_artifacts": [item.to_mapping() for item in self.source_artifacts],
            "log_artifacts": [item.to_mapping() for item in self.log_artifacts],
            "replay_command": self.replay_command,
            "limitations": list(self.limitations),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "provenance_id": self.provenance_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="result_provenance",
            schema_version=RESULT_PROVENANCE_SCHEMA_VERSION,
            object_id=self.provenance_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ResultProvenance":
        value = mapping(value, "result_provenance")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "physics_case_ref",
                "solver",
                "run_status",
                "authorization_status",
                "execution_id",
                "started_at",
                "completed_at",
                "extraction_software",
                "source_artifacts",
                "log_artifacts",
                "replay_command",
                "limitations",
                "provenance_id",
                "content_sha256",
            },
            "result_provenance",
        )
        if value["schema_version"] != RESULT_PROVENANCE_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported result provenance schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            physics_case_ref=ContractRef.from_mapping(
                mapping(value["physics_case_ref"], "physics_case_ref")
            ),
            solver=SolverDefinition.from_mapping(mapping(value["solver"], "solver")),
            run_status=enum(value["run_status"], RUN_STATUSES, "provenance.run_status"),
            authorization_status=enum(
                value["authorization_status"],
                AUTHORIZATION_STATUSES,
                "provenance.authorization_status",
            ),
            execution_id=string(value["execution_id"], "provenance.execution_id"),
            started_at=optional_string(value["started_at"], "provenance.started_at"),
            completed_at=optional_string(value["completed_at"], "provenance.completed_at"),
            extraction_software=string(
                value["extraction_software"], "provenance.extraction_software"
            ),
            source_artifacts=tuple(
                ExternalArtifactRef.from_mapping(mapping(item, "artifact"))
                for item in sequence(value["source_artifacts"], "provenance.source_artifacts")
            ),
            log_artifacts=tuple(
                ExternalArtifactRef.from_mapping(mapping(item, "artifact"))
                for item in sequence(value["log_artifacts"], "provenance.log_artifacts")
            ),
            replay_command=string(value["replay_command"], "provenance.replay_command"),
            limitations=string_tuple(value["limitations"], "provenance.limitations"),
            provenance_id=string(value["provenance_id"], "provenance.provenance_id"),
            content_sha256=string(value["content_sha256"], "provenance.content_sha256"),
        )


@dataclass(frozen=True)
class PhysicsLinkStatus:
    """Explicit per-instance physics linkage state, including SLS-2 absence."""

    geometry: GeometryBinding
    link_status: str
    physics_case_refs: tuple[ContractRef, ...]
    reason: str
    link_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        enum(self.link_status, LINK_STATUSES, "physics_link.link_status")
        string(self.reason, "physics_link.reason")
        for reference in self.physics_case_refs:
            if (
                reference.contract_kind != "physics_case"
                or reference.schema_version != PHYSICS_CASE_SCHEMA_VERSION
            ):
                raise PhysicsContractError("physics link case reference is invalid")
            if not reference.object_id.startswith(self.geometry.instance_id + "."):
                raise PhysicsContractError(
                    "physics link case reference does not bind its instance"
                )
        if len(self.physics_case_refs) != len(set(self.physics_case_refs)):
            raise PhysicsContractError("physics link case references must be unique")
        if self.link_status == "not_linked" and self.physics_case_refs:
            raise PhysicsContractError("not-linked instance cannot reference physics cases")
        if self.link_status != "not_linked" and not self.physics_case_refs:
            raise PhysicsContractError("linked/planned instance requires physics cases")
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="link_id",
            id_prefix=f"{self.geometry.instance_id}.physics_link",
            label="physics link",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": PHYSICS_LINK_STATUS_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "link_status": self.link_status,
            "physics_case_refs": [item.to_mapping() for item in self.physics_case_refs],
            "reason": self.reason,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "link_id": self.link_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="physics_link_status",
            schema_version=PHYSICS_LINK_STATUS_SCHEMA_VERSION,
            object_id=self.link_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PhysicsLinkStatus":
        value = mapping(value, "physics_link")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "link_status",
                "physics_case_refs",
                "reason",
                "link_id",
                "content_sha256",
            },
            "physics_link",
        )
        if value["schema_version"] != PHYSICS_LINK_STATUS_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported physics link schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            link_status=enum(value["link_status"], LINK_STATUSES, "physics_link.link_status"),
            physics_case_refs=tuple(
                ContractRef.from_mapping(mapping(item, "contract_ref"))
                for item in sequence(value["physics_case_refs"], "physics_link.physics_case_refs")
            ),
            reason=string(value["reason"], "physics_link.reason"),
            link_id=string(value["link_id"], "physics_link.link_id"),
            content_sha256=string(value["content_sha256"], "physics_link.content_sha256"),
        )


__all__ = [
    "AUTHORIZATION_STATUSES",
    "CASE_STATUSES",
    "LINK_STATUSES",
    "PHYSICS_CASE_SCHEMA_VERSION",
    "PHYSICS_LINK_STATUS_SCHEMA_VERSION",
    "RESULT_PROVENANCE_SCHEMA_VERSION",
    "RUN_STATUSES",
    "PhysicsCase",
    "PhysicsLinkStatus",
    "ResultProvenance",
]
