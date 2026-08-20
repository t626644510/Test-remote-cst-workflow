"""Identity, geometry, solver, material, boundary, mesh, and artifact records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from rf_cem.semantic.contracts import canonical_sha256, file_sha256

from .common import (
    PhysicsContractError,
    enum,
    exact_keys,
    finite_json,
    mapping,
    non_negative,
    normalized_hash,
    optional_number,
    optional_string,
    positive_integer,
    relative_path,
    resolve_inside,
    sequence,
    string,
)


SETTING_STATUSES = frozenset(
    {"established", "repository_verified", "planned", "not_established"}
)


@dataclass(frozen=True)
class ContractRef:
    """Hash-bound identity of one separate canonical contract object."""

    contract_kind: str
    schema_version: str
    object_id: str
    content_sha256: str

    def __post_init__(self) -> None:
        string(self.contract_kind, "contract_ref.contract_kind")
        string(self.schema_version, "contract_ref.schema_version")
        string(self.object_id, "contract_ref.object_id")
        normalized_hash(self.content_sha256, "contract_ref.content_sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "contract_kind": self.contract_kind,
            "schema_version": self.schema_version,
            "object_id": self.object_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContractRef":
        value = mapping(value, "contract_ref")
        exact_keys(
            value,
            {"contract_kind", "schema_version", "object_id", "content_sha256"},
            "contract_ref",
        )
        return cls(
            contract_kind=string(value["contract_kind"], "contract_ref.contract_kind"),
            schema_version=string(value["schema_version"], "contract_ref.schema_version"),
            object_id=string(value["object_id"], "contract_ref.object_id"),
            content_sha256=normalized_hash(
                value["content_sha256"], "contract_ref.content_sha256"
            ),
        )


@dataclass(frozen=True)
class ExternalArtifactRef:
    """Hash and size reference to payload kept outside scalar JSON contracts."""

    role: str
    repository_relative_path: str
    media_type: str
    raw_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        string(self.role, "artifact.role")
        relative_path(self.repository_relative_path, "artifact.repository_relative_path")
        string(self.media_type, "artifact.media_type")
        normalized_hash(self.raw_sha256, "artifact.raw_sha256")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool):
            raise PhysicsContractError("artifact.size_bytes must be an integer")
        if self.size_bytes < 0:
            raise PhysicsContractError("artifact.size_bytes must be non-negative")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "repository_relative_path": self.repository_relative_path,
            "media_type": self.media_type,
            "raw_sha256": self.raw_sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalArtifactRef":
        value = mapping(value, "artifact")
        exact_keys(
            value,
            {
                "role",
                "repository_relative_path",
                "media_type",
                "raw_sha256",
                "size_bytes",
            },
            "artifact",
        )
        size = value["size_bytes"]
        if not isinstance(size, int) or isinstance(size, bool):
            raise PhysicsContractError("artifact.size_bytes must be an integer")
        return cls(
            role=string(value["role"], "artifact.role"),
            repository_relative_path=relative_path(
                value["repository_relative_path"],
                "artifact.repository_relative_path",
            ),
            media_type=string(value["media_type"], "artifact.media_type"),
            raw_sha256=normalized_hash(value["raw_sha256"], "artifact.raw_sha256"),
            size_bytes=size,
        )

    @classmethod
    def from_file(
        cls,
        *,
        repo_root: Path,
        path: Path,
        role: str,
        media_type: str,
    ) -> "ExternalArtifactRef":
        root = repo_root.resolve()
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise PhysicsContractError("external artifact must remain inside repository") from exc
        if not resolved.is_file():
            raise PhysicsContractError(f"external artifact is missing: {relative}")
        return cls(
            role=role,
            repository_relative_path=relative,
            media_type=media_type,
            raw_sha256=file_sha256(resolved),
            size_bytes=resolved.stat().st_size,
        )

    def validate_file(self, repo_root: Path) -> Path:
        path = resolve_inside(
            repo_root, self.repository_relative_path, "artifact.repository_relative_path"
        )
        if not path.is_file():
            raise PhysicsContractError(
                f"external artifact is missing: {self.repository_relative_path}"
            )
        if path.stat().st_size != self.size_bytes:
            raise PhysicsContractError(
                f"external artifact size mismatch: {self.repository_relative_path}"
            )
        if file_sha256(path) != self.raw_sha256:
            raise PhysicsContractError(
                f"external artifact hash mismatch: {self.repository_relative_path}"
            )
        return path


@dataclass(frozen=True)
class GeometryBinding:
    """Complete R1/R2/R4 identity chain required by every RF result."""

    family_id: str
    instance_id: str
    instance_graph_ref: ContractRef
    compile_record_ref: ContractRef
    exact_geometry_ref: ContractRef

    def __post_init__(self) -> None:
        string(self.family_id, "geometry.family_id")
        string(self.instance_id, "geometry.instance_id")
        expected = (
            (self.instance_graph_ref, "instance_boundary_graph", "instance_boundary_graph.v0"),
            (self.compile_record_ref, "compile_record", "compile_record.v0"),
            (
                self.exact_geometry_ref,
                "exact_geometry_reference",
                "exact_geometry_reference.v0",
            ),
        )
        for reference, kind, schema in expected:
            if reference.contract_kind != kind or reference.schema_version != schema:
                raise PhysicsContractError(
                    f"geometry {kind} reference has the wrong kind or schema"
                )
        if not self.instance_graph_ref.object_id.startswith(self.instance_id + "."):
            raise PhysicsContractError("instance graph reference does not bind the instance")
        if not self.compile_record_ref.object_id.startswith(self.instance_id + "."):
            raise PhysicsContractError("compile record reference does not bind the instance")
        if not self.exact_geometry_ref.object_id.startswith(self.instance_id + "."):
            raise PhysicsContractError("exact geometry reference does not bind the instance")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "instance_graph_ref": self.instance_graph_ref.to_mapping(),
            "compile_record_ref": self.compile_record_ref.to_mapping(),
            "exact_geometry_ref": self.exact_geometry_ref.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GeometryBinding":
        value = mapping(value, "geometry")
        exact_keys(
            value,
            {
                "family_id",
                "instance_id",
                "instance_graph_ref",
                "compile_record_ref",
                "exact_geometry_ref",
            },
            "geometry",
        )
        return cls(
            family_id=string(value["family_id"], "geometry.family_id"),
            instance_id=string(value["instance_id"], "geometry.instance_id"),
            instance_graph_ref=ContractRef.from_mapping(
                mapping(value["instance_graph_ref"], "geometry.instance_graph_ref")
            ),
            compile_record_ref=ContractRef.from_mapping(
                mapping(value["compile_record_ref"], "geometry.compile_record_ref")
            ),
            exact_geometry_ref=ContractRef.from_mapping(
                mapping(value["exact_geometry_ref"], "geometry.exact_geometry_ref")
            ),
        )


@dataclass(frozen=True)
class SolverDefinition:
    """Solver and API identity; build can remain explicit but unestablished."""

    product: str
    version: str
    build: str | None
    solver_name: str
    interface: str
    settings_status: str

    def __post_init__(self) -> None:
        string(self.product, "solver.product")
        string(self.version, "solver.version")
        optional_string(self.build, "solver.build")
        string(self.solver_name, "solver.solver_name")
        string(self.interface, "solver.interface")
        enum(self.settings_status, SETTING_STATUSES, "solver.settings_status")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "version": self.version,
            "build": self.build,
            "solver_name": self.solver_name,
            "interface": self.interface,
            "settings_status": self.settings_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SolverDefinition":
        value = mapping(value, "solver")
        exact_keys(
            value,
            {"product", "version", "build", "solver_name", "interface", "settings_status"},
            "solver",
        )
        return cls(
            product=string(value["product"], "solver.product"),
            version=string(value["version"], "solver.version"),
            build=optional_string(value["build"], "solver.build"),
            solver_name=string(value["solver_name"], "solver.solver_name"),
            interface=string(value["interface"], "solver.interface"),
            settings_status=enum(
                value["settings_status"], SETTING_STATUSES, "solver.settings_status"
            ),
        )


@dataclass(frozen=True)
class MaterialAssignment:
    """One explicit material assignment and optional conductivity."""

    role: str
    selection: str
    material_name: str
    conductivity_s_per_m: float | None
    settings_status: str

    def __post_init__(self) -> None:
        string(self.role, "material.role")
        string(self.selection, "material.selection")
        string(self.material_name, "material.material_name")
        conductivity = optional_number(
            self.conductivity_s_per_m, "material.conductivity_s_per_m"
        )
        if conductivity is not None and conductivity <= 0.0:
            raise PhysicsContractError("material conductivity must be positive")
        enum(self.settings_status, SETTING_STATUSES, "material.settings_status")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "selection": self.selection,
            "material_name": self.material_name,
            "conductivity_s_per_m": self.conductivity_s_per_m,
            "settings_status": self.settings_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MaterialAssignment":
        value = mapping(value, "material")
        exact_keys(
            value,
            {
                "role",
                "selection",
                "material_name",
                "conductivity_s_per_m",
                "settings_status",
            },
            "material",
        )
        return cls(
            role=string(value["role"], "material.role"),
            selection=string(value["selection"], "material.selection"),
            material_name=string(value["material_name"], "material.material_name"),
            conductivity_s_per_m=optional_number(
                value["conductivity_s_per_m"], "material.conductivity_s_per_m"
            ),
            settings_status=enum(
                value["settings_status"], SETTING_STATUSES, "material.settings_status"
            ),
        )


@dataclass(frozen=True)
class BoundaryAssignment:
    """One named electromagnetic boundary assignment."""

    selection: str
    condition: str
    settings_status: str

    def __post_init__(self) -> None:
        string(self.selection, "boundary.selection")
        string(self.condition, "boundary.condition")
        enum(self.settings_status, SETTING_STATUSES, "boundary.settings_status")

    def to_mapping(self) -> dict[str, str]:
        return {
            "selection": self.selection,
            "condition": self.condition,
            "settings_status": self.settings_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BoundaryAssignment":
        value = mapping(value, "boundary")
        exact_keys(value, {"selection", "condition", "settings_status"}, "boundary")
        return cls(
            selection=string(value["selection"], "boundary.selection"),
            condition=string(value["condition"], "boundary.condition"),
            settings_status=enum(
                value["settings_status"], SETTING_STATUSES, "boundary.settings_status"
            ),
        )


@dataclass(frozen=True)
class MeshDefinition:
    """Named mesh level with finite explicit controls and establishment state."""

    mesh_id: str
    level: str
    strategy: str
    control_parameters: Mapping[str, Any]
    settings_status: str

    def __post_init__(self) -> None:
        string(self.mesh_id, "mesh.mesh_id")
        string(self.level, "mesh.level")
        string(self.strategy, "mesh.strategy")
        finite_json(dict(self.control_parameters), "mesh.control_parameters")
        enum(self.settings_status, SETTING_STATUSES, "mesh.settings_status")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "mesh_id": self.mesh_id,
            "level": self.level,
            "strategy": self.strategy,
            "control_parameters": dict(self.control_parameters),
            "settings_status": self.settings_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MeshDefinition":
        value = mapping(value, "mesh")
        exact_keys(
            value,
            {"mesh_id", "level", "strategy", "control_parameters", "settings_status"},
            "mesh",
        )
        controls = dict(mapping(value["control_parameters"], "mesh.control_parameters"))
        finite_json(controls, "mesh.control_parameters")
        return cls(
            mesh_id=string(value["mesh_id"], "mesh.mesh_id"),
            level=string(value["level"], "mesh.level"),
            strategy=string(value["strategy"], "mesh.strategy"),
            control_parameters=controls,
            settings_status=enum(
                value["settings_status"], SETTING_STATUSES, "mesh.settings_status"
            ),
        )


def content_fingerprint(value: object) -> str:
    """Return the canonical content digest used by comparison policies."""

    return canonical_sha256(value)


__all__ = [
    "BoundaryAssignment",
    "ContractRef",
    "ExternalArtifactRef",
    "GeometryBinding",
    "MaterialAssignment",
    "MeshDefinition",
    "SETTING_STATUSES",
    "SolverDefinition",
    "content_fingerprint",
]
