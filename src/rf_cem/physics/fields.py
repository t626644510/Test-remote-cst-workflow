"""External-artifact field bundle contract for R5."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .cases import PHYSICS_CASE_SCHEMA_VERSION, RESULT_PROVENANCE_SCHEMA_VERSION
from .common import (
    PhysicsContractError,
    boolean,
    enum,
    exact_keys,
    mapping,
    sequence,
    string,
    unit,
)
from .identity import bind_identity, identity_ref
from .modes import MODE_IDENTITY_SCHEMA_VERSION
from .references import ContractRef, ExternalArtifactRef, GeometryBinding


FIELD_BUNDLE_SCHEMA_VERSION = "field_bundle.v0"
FIELD_STATUSES = frozenset({"not_established", "established"})


@dataclass(frozen=True)
class FieldComponent:
    """Metadata for one externally stored E/B field component."""

    component_id: str
    physical_quantity: str
    unit: str
    result_locator: str
    complex_valued: bool

    def __post_init__(self) -> None:
        string(self.component_id, "field_component.component_id")
        string(self.physical_quantity, "field_component.physical_quantity")
        actual_unit = unit(self.unit, "field_component.unit")
        if actual_unit not in {"MV/m", "mT"}:
            raise PhysicsContractError("field component unit must be MV/m or mT")
        string(self.result_locator, "field_component.result_locator")
        boolean(self.complex_valued, "field_component.complex_valued")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "physical_quantity": self.physical_quantity,
            "unit": self.unit,
            "result_locator": self.result_locator,
            "complex_valued": self.complex_valued,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FieldComponent":
        value = mapping(value, "field_component")
        exact_keys(
            value,
            {
                "component_id",
                "physical_quantity",
                "unit",
                "result_locator",
                "complex_valued",
            },
            "field_component",
        )
        return cls(
            component_id=string(value["component_id"], "field_component.component_id"),
            physical_quantity=string(
                value["physical_quantity"], "field_component.physical_quantity"
            ),
            unit=unit(value["unit"], "field_component.unit"),
            result_locator=string(
                value["result_locator"], "field_component.result_locator"
            ),
            complex_valued=boolean(
                value["complex_valued"], "field_component.complex_valued"
            ),
        )


@dataclass(frozen=True)
class FieldBundle:
    """Mode-linked field metadata plus external manifest/hash references only."""

    geometry: GeometryBinding
    physics_case_ref: ContractRef
    mode_identity_ref: ContractRef
    provenance_ref: ContractRef
    field_status: str
    coordinate_system: str
    normalization: str
    components: tuple[FieldComponent, ...]
    artifacts: tuple[ExternalArtifactRef, ...]
    extraction_method: str
    field_bundle_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        expected_refs = (
            (self.physics_case_ref, "physics_case", PHYSICS_CASE_SCHEMA_VERSION),
            (self.mode_identity_ref, "mode_identity", MODE_IDENTITY_SCHEMA_VERSION),
            (
                self.provenance_ref,
                "result_provenance",
                RESULT_PROVENANCE_SCHEMA_VERSION,
            ),
        )
        for reference, kind, schema in expected_refs:
            if reference.contract_kind != kind or reference.schema_version != schema:
                raise PhysicsContractError(f"field bundle requires {schema}")
        for reference, label in (
            (self.physics_case_ref, "physics case"),
            (self.mode_identity_ref, "mode identity"),
            (self.provenance_ref, "result provenance"),
        ):
            if not reference.object_id.startswith(self.geometry.instance_id + "."):
                raise PhysicsContractError(
                    f"field bundle {label} does not bind its geometry"
                )
        enum(self.field_status, FIELD_STATUSES, "field_bundle.field_status")
        string(self.coordinate_system, "field_bundle.coordinate_system")
        string(self.normalization, "field_bundle.normalization")
        string(self.extraction_method, "field_bundle.extraction_method")
        component_ids = [item.component_id for item in self.components]
        artifact_roles = [item.role for item in self.artifacts]
        if len(component_ids) != len(set(component_ids)):
            raise PhysicsContractError("field component IDs must be unique")
        if len(artifact_roles) != len(set(artifact_roles)):
            raise PhysicsContractError("field artifact roles must be unique")
        if self.field_status == "established":
            if not self.components:
                raise PhysicsContractError("established field bundle requires components")
            if "field_manifest" not in artifact_roles or not any(
                role.startswith("field_data") for role in artifact_roles
            ):
                raise PhysicsContractError(
                    "established field bundle requires external manifest and field data"
                )
            if self.extraction_method == "not_established":
                raise PhysicsContractError(
                    "established field bundle requires extraction method"
                )
            if (
                self.coordinate_system == "not_established"
                or self.normalization == "not_established"
                or any(item.result_locator == "not_established" for item in self.components)
                or any(item.size_bytes <= 0 for item in self.artifacts)
            ):
                raise PhysicsContractError(
                    "established field bundle requires materialized coordinates, "
                    "normalization, locators, and non-empty external artifacts"
                )
        elif self.components or self.artifacts:
            raise PhysicsContractError(
                "not-established field bundle cannot contain partial field payload"
            )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="field_bundle_id",
            id_prefix=f"{self.geometry.instance_id}.field_bundle",
            label="field bundle",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": FIELD_BUNDLE_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "physics_case_ref": self.physics_case_ref.to_mapping(),
            "mode_identity_ref": self.mode_identity_ref.to_mapping(),
            "provenance_ref": self.provenance_ref.to_mapping(),
            "field_status": self.field_status,
            "coordinate_system": self.coordinate_system,
            "normalization": self.normalization,
            "components": [item.to_mapping() for item in self.components],
            "artifacts": [item.to_mapping() for item in self.artifacts],
            "extraction_method": self.extraction_method,
            "inline_field_payload": False,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "field_bundle_id": self.field_bundle_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="field_bundle",
            schema_version=FIELD_BUNDLE_SCHEMA_VERSION,
            object_id=self.field_bundle_id,
            content_sha256=self.content_sha256,
        )

    def validate_external_artifacts(self, repo_root: Path) -> tuple[Path, ...]:
        return tuple(item.validate_file(repo_root) for item in self.artifacts)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FieldBundle":
        value = mapping(value, "field_bundle")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "physics_case_ref",
                "mode_identity_ref",
                "provenance_ref",
                "field_status",
                "coordinate_system",
                "normalization",
                "components",
                "artifacts",
                "extraction_method",
                "inline_field_payload",
                "field_bundle_id",
                "content_sha256",
            },
            "field_bundle",
        )
        if value["schema_version"] != FIELD_BUNDLE_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported field bundle schema")
        if value["inline_field_payload"] is not False:
            raise PhysicsContractError("field bundle must keep data in external artifacts")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            physics_case_ref=ContractRef.from_mapping(
                mapping(value["physics_case_ref"], "physics_case_ref")
            ),
            mode_identity_ref=ContractRef.from_mapping(
                mapping(value["mode_identity_ref"], "mode_identity_ref")
            ),
            provenance_ref=ContractRef.from_mapping(
                mapping(value["provenance_ref"], "provenance_ref")
            ),
            field_status=enum(
                value["field_status"], FIELD_STATUSES, "field_bundle.field_status"
            ),
            coordinate_system=string(
                value["coordinate_system"], "field_bundle.coordinate_system"
            ),
            normalization=string(value["normalization"], "field_bundle.normalization"),
            components=tuple(
                FieldComponent.from_mapping(mapping(item, "field_component"))
                for item in sequence(value["components"], "field_bundle.components")
            ),
            artifacts=tuple(
                ExternalArtifactRef.from_mapping(mapping(item, "artifact"))
                for item in sequence(value["artifacts"], "field_bundle.artifacts")
            ),
            extraction_method=string(
                value["extraction_method"], "field_bundle.extraction_method"
            ),
            field_bundle_id=string(
                value["field_bundle_id"], "field_bundle.field_bundle_id"
            ),
            content_sha256=string(value["content_sha256"], "field_bundle.content_sha256"),
        )


__all__ = [
    "FIELD_BUNDLE_SCHEMA_VERSION",
    "FIELD_STATUSES",
    "FieldBundle",
    "FieldComponent",
]
