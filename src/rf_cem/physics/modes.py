"""Mode fingerprint and mode identity contracts that reject bare indices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .cases import PHYSICS_CASE_SCHEMA_VERSION
from .common import (
    PhysicsContractError,
    enum,
    exact_keys,
    mapping,
    optional_number,
    optional_positive_integer,
    sequence,
    string,
    string_tuple,
)
from .identity import bind_identity, identity_ref
from .references import ContractRef, ExternalArtifactRef, GeometryBinding


MODE_FINGERPRINT_SCHEMA_VERSION = "mode_fingerprint.v0"
MODE_IDENTITY_SCHEMA_VERSION = "mode_identity.v0"

FINGERPRINT_STATUSES = frozenset({"not_established", "established"})
MODE_DETERMINATION_STATUSES = frozenset(
    {"not_established", "auto_matched", "manually_confirmed"}
)


@dataclass(frozen=True)
class ModeFingerprint:
    """Frequency/scalar plus field or symmetry evidence for one mode."""

    geometry: GeometryBinding
    physics_case_ref: ContractRef
    fingerprint_status: str
    frequency_mhz: float | None
    r_over_q_ohm: float | None
    symmetry_signature: tuple[str, ...]
    field_signature_artifacts: tuple[ExternalArtifactRef, ...]
    fingerprint_method: str
    fingerprint_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.physics_case_ref.contract_kind != "physics_case"
            or self.physics_case_ref.schema_version != PHYSICS_CASE_SCHEMA_VERSION
        ):
            raise PhysicsContractError("mode fingerprint requires physics_case.v0")
        if not self.physics_case_ref.object_id.startswith(self.geometry.instance_id + "."):
            raise PhysicsContractError("mode fingerprint case does not bind its geometry")
        enum(
            self.fingerprint_status,
            FINGERPRINT_STATUSES,
            "mode_fingerprint.fingerprint_status",
        )
        frequency = optional_number(self.frequency_mhz, "mode_fingerprint.frequency_mhz")
        r_over_q = optional_number(self.r_over_q_ohm, "mode_fingerprint.r_over_q_ohm")
        if frequency is not None and frequency <= 0.0:
            raise PhysicsContractError("mode fingerprint frequency must be positive")
        if r_over_q is not None and r_over_q < 0.0:
            raise PhysicsContractError("mode fingerprint R/Q must be non-negative")
        string_tuple(self.symmetry_signature, "mode_fingerprint.symmetry_signature")
        string(self.fingerprint_method, "mode_fingerprint.fingerprint_method")
        roles = [item.role for item in self.field_signature_artifacts]
        if len(roles) != len(set(roles)):
            raise PhysicsContractError("mode fingerprint artifact roles must be unique")
        if self.fingerprint_status == "established":
            if frequency is None or r_over_q is None:
                raise PhysicsContractError(
                    "established mode fingerprint requires frequency and R/Q"
                )
            if not self.symmetry_signature and not self.field_signature_artifacts:
                raise PhysicsContractError(
                    "established mode fingerprint requires symmetry or field evidence"
                )
            if self.fingerprint_method == "not_established":
                raise PhysicsContractError(
                    "established mode fingerprint requires a determination method"
                )
        elif any(
            (
                frequency is not None,
                r_over_q is not None,
                bool(self.symmetry_signature),
                bool(self.field_signature_artifacts),
            )
        ):
            raise PhysicsContractError(
                "not-established mode fingerprint cannot contain partial identity evidence"
            )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="fingerprint_id",
            id_prefix=f"{self.geometry.instance_id}.mode_fingerprint",
            label="mode fingerprint",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": MODE_FINGERPRINT_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "physics_case_ref": self.physics_case_ref.to_mapping(),
            "fingerprint_status": self.fingerprint_status,
            "frequency_mhz": self.frequency_mhz,
            "r_over_q_ohm": self.r_over_q_ohm,
            "symmetry_signature": list(self.symmetry_signature),
            "field_signature_artifacts": [
                item.to_mapping() for item in self.field_signature_artifacts
            ],
            "fingerprint_method": self.fingerprint_method,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "fingerprint_id": self.fingerprint_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="mode_fingerprint",
            schema_version=MODE_FINGERPRINT_SCHEMA_VERSION,
            object_id=self.fingerprint_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ModeFingerprint":
        value = mapping(value, "mode_fingerprint")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "physics_case_ref",
                "fingerprint_status",
                "frequency_mhz",
                "r_over_q_ohm",
                "symmetry_signature",
                "field_signature_artifacts",
                "fingerprint_method",
                "fingerprint_id",
                "content_sha256",
            },
            "mode_fingerprint",
        )
        if value["schema_version"] != MODE_FINGERPRINT_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported mode fingerprint schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            physics_case_ref=ContractRef.from_mapping(
                mapping(value["physics_case_ref"], "physics_case_ref")
            ),
            fingerprint_status=enum(
                value["fingerprint_status"],
                FINGERPRINT_STATUSES,
                "mode_fingerprint.fingerprint_status",
            ),
            frequency_mhz=optional_number(
                value["frequency_mhz"], "mode_fingerprint.frequency_mhz"
            ),
            r_over_q_ohm=optional_number(
                value["r_over_q_ohm"], "mode_fingerprint.r_over_q_ohm"
            ),
            symmetry_signature=string_tuple(
                value["symmetry_signature"], "mode_fingerprint.symmetry_signature"
            ),
            field_signature_artifacts=tuple(
                ExternalArtifactRef.from_mapping(mapping(item, "artifact"))
                for item in sequence(
                    value["field_signature_artifacts"],
                    "mode_fingerprint.field_signature_artifacts",
                )
            ),
            fingerprint_method=string(
                value["fingerprint_method"], "mode_fingerprint.fingerprint_method"
            ),
            fingerprint_id=string(value["fingerprint_id"], "mode_fingerprint.fingerprint_id"),
            content_sha256=string(value["content_sha256"], "mode_fingerprint.content_sha256"),
        )


@dataclass(frozen=True)
class ModeIdentity:
    """Stable mode role linked to a nontrivial fingerprint and result locator."""

    geometry: GeometryBinding
    physics_case_ref: ContractRef
    fingerprint_ref: ContractRef
    mode_family: str
    mode_role: str
    solver_result_locator: str
    solver_mode_index: int | None
    determination_status: str
    determination_method: str
    mode_identity_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.physics_case_ref.contract_kind != "physics_case"
            or self.physics_case_ref.schema_version != PHYSICS_CASE_SCHEMA_VERSION
        ):
            raise PhysicsContractError("mode identity requires physics_case.v0")
        if (
            self.fingerprint_ref.contract_kind != "mode_fingerprint"
            or self.fingerprint_ref.schema_version != MODE_FINGERPRINT_SCHEMA_VERSION
        ):
            raise PhysicsContractError("mode identity requires mode_fingerprint.v0")
        if not self.physics_case_ref.object_id.startswith(self.geometry.instance_id + "."):
            raise PhysicsContractError("mode identity case does not bind its geometry")
        if not self.fingerprint_ref.object_id.startswith(self.geometry.instance_id + "."):
            raise PhysicsContractError(
                "mode identity fingerprint does not bind its geometry"
            )
        string(self.mode_family, "mode_identity.mode_family")
        string(self.mode_role, "mode_identity.mode_role")
        locator = string(self.solver_result_locator, "mode_identity.solver_result_locator")
        optional_positive_integer(self.solver_mode_index, "mode_identity.solver_mode_index")
        enum(
            self.determination_status,
            MODE_DETERMINATION_STATUSES,
            "mode_identity.determination_status",
        )
        string(self.determination_method, "mode_identity.determination_method")
        if self.determination_status == "not_established" and self.solver_mode_index is not None:
            raise PhysicsContractError(
                "a bare solver mode index cannot establish or partially populate mode identity"
            )
        if self.determination_status != "not_established" and locator == "not_established":
            raise PhysicsContractError("established mode identity requires result locator")
        if (
            self.determination_status != "not_established"
            and self.determination_method == "not_established"
        ):
            raise PhysicsContractError(
                "established mode identity requires a determination method"
            )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="mode_identity_id",
            id_prefix=f"{self.geometry.instance_id}.mode_identity",
            label="mode identity",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": MODE_IDENTITY_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "physics_case_ref": self.physics_case_ref.to_mapping(),
            "fingerprint_ref": self.fingerprint_ref.to_mapping(),
            "mode_family": self.mode_family,
            "mode_role": self.mode_role,
            "solver_result_locator": self.solver_result_locator,
            "solver_mode_index": self.solver_mode_index,
            "determination_status": self.determination_status,
            "determination_method": self.determination_method,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "mode_identity_id": self.mode_identity_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="mode_identity",
            schema_version=MODE_IDENTITY_SCHEMA_VERSION,
            object_id=self.mode_identity_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ModeIdentity":
        value = mapping(value, "mode_identity")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "physics_case_ref",
                "fingerprint_ref",
                "mode_family",
                "mode_role",
                "solver_result_locator",
                "solver_mode_index",
                "determination_status",
                "determination_method",
                "mode_identity_id",
                "content_sha256",
            },
            "mode_identity",
        )
        if value["schema_version"] != MODE_IDENTITY_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported mode identity schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            physics_case_ref=ContractRef.from_mapping(
                mapping(value["physics_case_ref"], "physics_case_ref")
            ),
            fingerprint_ref=ContractRef.from_mapping(
                mapping(value["fingerprint_ref"], "fingerprint_ref")
            ),
            mode_family=string(value["mode_family"], "mode_identity.mode_family"),
            mode_role=string(value["mode_role"], "mode_identity.mode_role"),
            solver_result_locator=string(
                value["solver_result_locator"], "mode_identity.solver_result_locator"
            ),
            solver_mode_index=optional_positive_integer(
                value["solver_mode_index"], "mode_identity.solver_mode_index"
            ),
            determination_status=enum(
                value["determination_status"],
                MODE_DETERMINATION_STATUSES,
                "mode_identity.determination_status",
            ),
            determination_method=string(
                value["determination_method"], "mode_identity.determination_method"
            ),
            mode_identity_id=string(
                value["mode_identity_id"], "mode_identity.mode_identity_id"
            ),
            content_sha256=string(value["content_sha256"], "mode_identity.content_sha256"),
        )


__all__ = [
    "FINGERPRINT_STATUSES",
    "MODE_DETERMINATION_STATUSES",
    "MODE_FINGERPRINT_SCHEMA_VERSION",
    "MODE_IDENTITY_SCHEMA_VERSION",
    "ModeFingerprint",
    "ModeIdentity",
]
