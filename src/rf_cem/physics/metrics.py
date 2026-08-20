"""Unit-bound RF metric definitions and extracted scalar observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .cases import (
    PHYSICS_CASE_SCHEMA_VERSION,
    RESULT_PROVENANCE_SCHEMA_VERSION,
)
from .common import (
    PhysicsContractError,
    enum,
    exact_keys,
    mapping,
    optional_number,
    string,
    string_tuple,
    unit,
)
from .identity import bind_identity, identity_ref
from .modes import MODE_IDENTITY_SCHEMA_VERSION
from .references import ContractRef, GeometryBinding


METRIC_CONTRACT_SCHEMA_VERSION = "metric_contract.v0"
METRIC_OBSERVATION_SCHEMA_VERSION = "metric_observation.v0"

REQUIRED_METRIC_KEYS = (
    "eigenfrequency",
    "r_over_q",
    "q_perturbation",
    "stored_energy",
    "epk",
    "bpk",
    "epk_over_eacc",
    "bpk_over_eacc",
    "surface_loss",
)

METRIC_UNITS = {
    "eigenfrequency": "MHz",
    "r_over_q": "ohm",
    "q_perturbation": "1",
    "stored_energy": "J",
    "epk": "MV/m",
    "bpk": "mT",
    "epk_over_eacc": "1",
    "bpk_over_eacc": "mT/(MV/m)",
    "surface_loss": "W",
}

EXTRACTION_SUPPORT_STATUSES = frozenset(
    {"not_established", "repository_verified_locator", "live_validated"}
)
METRIC_VALIDATION_STATUSES = frozenset(
    {"not_established", "extracted", "replayed", "rejected"}
)


@dataclass(frozen=True)
class MetricContract:
    """Physical semantic, unit, locator, normalization, and mode requirement."""

    metric_key: str
    display_name: str
    native_quantity_name: str
    physical_quantity: str
    unit: str
    result_locator_template: str
    extraction_method: str
    normalization: str
    mode_requirement: str
    extraction_support: str
    semantic_safeguards: tuple[str, ...]
    metric_contract_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if self.metric_key not in REQUIRED_METRIC_KEYS:
            raise PhysicsContractError(f"unsupported R5 metric: {self.metric_key}")
        string(self.display_name, "metric_contract.display_name")
        string(self.native_quantity_name, "metric_contract.native_quantity_name")
        string(self.physical_quantity, "metric_contract.physical_quantity")
        actual_unit = unit(self.unit, "metric_contract.unit")
        if actual_unit != METRIC_UNITS[self.metric_key]:
            raise PhysicsContractError("metric contract unit does not match metric semantic")
        string(self.result_locator_template, "metric_contract.result_locator_template")
        string(self.extraction_method, "metric_contract.extraction_method")
        string(self.normalization, "metric_contract.normalization")
        string(self.mode_requirement, "metric_contract.mode_requirement")
        if self.normalization == "not_established" or self.mode_requirement == "not_established":
            raise PhysicsContractError(
                "metric normalization and mode requirements must remain explicit"
            )
        enum(
            self.extraction_support,
            EXTRACTION_SUPPORT_STATUSES,
            "metric_contract.extraction_support",
        )
        string_tuple(self.semantic_safeguards, "metric_contract.semantic_safeguards")
        if self.extraction_support == "not_established":
            if self.result_locator_template != "not_established":
                raise PhysicsContractError(
                    "unsupported metric must keep its locator not_established"
                )
            if self.extraction_method != "not_established":
                raise PhysicsContractError(
                    "unsupported metric must keep its extraction method not_established"
                )
        if self.metric_key == "q_perturbation":
            if self.native_quantity_name != "Q-Factor (Perturbation)":
                raise PhysicsContractError(
                    "Q perturbation must preserve the native CST quantity name"
                )
            safeguards = " ".join(self.semantic_safeguards).lower()
            if "q0" not in safeguards or "not" not in safeguards:
                raise PhysicsContractError(
                    "Q perturbation contract must explicitly prohibit a Q0 claim"
                )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="metric_contract_id",
            id_prefix=f"rf_metric.{self.metric_key}",
            label="metric contract",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": METRIC_CONTRACT_SCHEMA_VERSION,
            "metric_key": self.metric_key,
            "display_name": self.display_name,
            "native_quantity_name": self.native_quantity_name,
            "physical_quantity": self.physical_quantity,
            "unit": self.unit,
            "result_locator_template": self.result_locator_template,
            "extraction_method": self.extraction_method,
            "normalization": self.normalization,
            "mode_requirement": self.mode_requirement,
            "extraction_support": self.extraction_support,
            "semantic_safeguards": list(self.semantic_safeguards),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "metric_contract_id": self.metric_contract_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="metric_contract",
            schema_version=METRIC_CONTRACT_SCHEMA_VERSION,
            object_id=self.metric_contract_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MetricContract":
        value = mapping(value, "metric_contract")
        exact_keys(
            value,
            {
                "schema_version",
                "metric_key",
                "display_name",
                "native_quantity_name",
                "physical_quantity",
                "unit",
                "result_locator_template",
                "extraction_method",
                "normalization",
                "mode_requirement",
                "extraction_support",
                "semantic_safeguards",
                "metric_contract_id",
                "content_sha256",
            },
            "metric_contract",
        )
        if value["schema_version"] != METRIC_CONTRACT_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported metric contract schema")
        return cls(
            metric_key=string(value["metric_key"], "metric_contract.metric_key"),
            display_name=string(value["display_name"], "metric_contract.display_name"),
            native_quantity_name=string(
                value["native_quantity_name"], "metric_contract.native_quantity_name"
            ),
            physical_quantity=string(
                value["physical_quantity"], "metric_contract.physical_quantity"
            ),
            unit=unit(value["unit"], "metric_contract.unit"),
            result_locator_template=string(
                value["result_locator_template"],
                "metric_contract.result_locator_template",
            ),
            extraction_method=string(
                value["extraction_method"], "metric_contract.extraction_method"
            ),
            normalization=string(
                value["normalization"], "metric_contract.normalization"
            ),
            mode_requirement=string(
                value["mode_requirement"], "metric_contract.mode_requirement"
            ),
            extraction_support=enum(
                value["extraction_support"],
                EXTRACTION_SUPPORT_STATUSES,
                "metric_contract.extraction_support",
            ),
            semantic_safeguards=string_tuple(
                value["semantic_safeguards"], "metric_contract.semantic_safeguards"
            ),
            metric_contract_id=string(
                value["metric_contract_id"], "metric_contract.metric_contract_id"
            ),
            content_sha256=string(
                value["content_sha256"], "metric_contract.content_sha256"
            ),
        )


@dataclass(frozen=True)
class MetricObservation:
    """One scalar result with the full geometry/case/mode/provenance chain."""

    geometry: GeometryBinding
    physics_case_ref: ContractRef
    mode_identity_ref: ContractRef
    metric_contract_ref: ContractRef
    provenance_ref: ContractRef
    result_locator: str
    unit: str
    extraction_method: str
    normalization: str
    value: float | None
    validation_status: str
    validation_messages: tuple[str, ...]
    metric_observation_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        expected_refs = (
            (self.physics_case_ref, "physics_case", PHYSICS_CASE_SCHEMA_VERSION),
            (self.mode_identity_ref, "mode_identity", MODE_IDENTITY_SCHEMA_VERSION),
            (self.metric_contract_ref, "metric_contract", METRIC_CONTRACT_SCHEMA_VERSION),
            (
                self.provenance_ref,
                "result_provenance",
                RESULT_PROVENANCE_SCHEMA_VERSION,
            ),
        )
        for reference, kind, schema in expected_refs:
            if reference.contract_kind != kind or reference.schema_version != schema:
                raise PhysicsContractError(
                    f"metric observation requires {schema} {kind} reference"
                )
        for reference, label in (
            (self.physics_case_ref, "physics case"),
            (self.mode_identity_ref, "mode identity"),
            (self.provenance_ref, "result provenance"),
        ):
            if not reference.object_id.startswith(self.geometry.instance_id + "."):
                raise PhysicsContractError(
                    f"metric observation {label} does not bind its geometry"
                )
        string(self.result_locator, "metric_observation.result_locator")
        unit(self.unit, "metric_observation.unit")
        string(self.extraction_method, "metric_observation.extraction_method")
        string(self.normalization, "metric_observation.normalization")
        value = optional_number(self.value, "metric_observation.value")
        enum(
            self.validation_status,
            METRIC_VALIDATION_STATUSES,
            "metric_observation.validation_status",
        )
        string_tuple(
            self.validation_messages, "metric_observation.validation_messages"
        )
        if self.validation_status in {"extracted", "replayed"}:
            if value is None:
                raise PhysicsContractError("established metric observation requires a value")
            if self.result_locator == "not_established":
                raise PhysicsContractError("established metric observation requires locator")
            if self.extraction_method == "not_established":
                raise PhysicsContractError(
                    "established metric observation requires extraction method"
                )
        elif self.validation_status == "not_established" and value is not None:
            raise PhysicsContractError(
                "not-established metric observation cannot contain a value"
            )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="metric_observation_id",
            id_prefix=f"{self.geometry.instance_id}.metric_observation",
            label="metric observation",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": METRIC_OBSERVATION_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "physics_case_ref": self.physics_case_ref.to_mapping(),
            "mode_identity_ref": self.mode_identity_ref.to_mapping(),
            "metric_contract_ref": self.metric_contract_ref.to_mapping(),
            "provenance_ref": self.provenance_ref.to_mapping(),
            "result_locator": self.result_locator,
            "unit": self.unit,
            "extraction_method": self.extraction_method,
            "normalization": self.normalization,
            "value": self.value,
            "validation_status": self.validation_status,
            "validation_messages": list(self.validation_messages),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "metric_observation_id": self.metric_observation_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="metric_observation",
            schema_version=METRIC_OBSERVATION_SCHEMA_VERSION,
            object_id=self.metric_observation_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MetricObservation":
        value = mapping(value, "metric_observation")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "physics_case_ref",
                "mode_identity_ref",
                "metric_contract_ref",
                "provenance_ref",
                "result_locator",
                "unit",
                "extraction_method",
                "normalization",
                "value",
                "validation_status",
                "validation_messages",
                "metric_observation_id",
                "content_sha256",
            },
            "metric_observation",
        )
        if value["schema_version"] != METRIC_OBSERVATION_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported metric observation schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            physics_case_ref=ContractRef.from_mapping(
                mapping(value["physics_case_ref"], "physics_case_ref")
            ),
            mode_identity_ref=ContractRef.from_mapping(
                mapping(value["mode_identity_ref"], "mode_identity_ref")
            ),
            metric_contract_ref=ContractRef.from_mapping(
                mapping(value["metric_contract_ref"], "metric_contract_ref")
            ),
            provenance_ref=ContractRef.from_mapping(
                mapping(value["provenance_ref"], "provenance_ref")
            ),
            result_locator=string(
                value["result_locator"], "metric_observation.result_locator"
            ),
            unit=unit(value["unit"], "metric_observation.unit"),
            extraction_method=string(
                value["extraction_method"], "metric_observation.extraction_method"
            ),
            normalization=string(
                value["normalization"], "metric_observation.normalization"
            ),
            value=optional_number(value["value"], "metric_observation.value"),
            validation_status=enum(
                value["validation_status"],
                METRIC_VALIDATION_STATUSES,
                "metric_observation.validation_status",
            ),
            validation_messages=string_tuple(
                value["validation_messages"],
                "metric_observation.validation_messages",
            ),
            metric_observation_id=string(
                value["metric_observation_id"],
                "metric_observation.metric_observation_id",
            ),
            content_sha256=string(
                value["content_sha256"], "metric_observation.content_sha256"
            ),
        )


def build_initial_metric_contracts() -> tuple[MetricContract, ...]:
    """Return the nine R5 v0 definitions without asserting live observations."""

    scalar_method = "cst_optimization.core.results.ResultReader.get_scalar"
    definitions = (
        MetricContract(
            "eigenfrequency",
            "Eigenfrequency",
            "Frequency",
            "eigenmode frequency",
            "MHz",
            r"Tables\0D Results\Frequency (Mode {mode_index})",
            scalar_method,
            "native eigenfrequency; independent of field-amplitude normalization",
            "one established mode_identity.v0 with matching fingerprint",
            "repository_verified_locator",
            ("No live value is established by locator verification alone.",),
        ),
        MetricContract(
            "r_over_q",
            "R/Q",
            "R over Q",
            "native CST eigenmode shunt impedance over quality factor",
            "ohm",
            r"Tables\0D Results\R over Q (Mode {mode_index})",
            scalar_method,
            "native CST 3D Eigenmode Result template definition; cross-tool formula not independently established",
            "same established mode_identity.v0 and native CST normalization",
            "repository_verified_locator",
            ("Do not compare across normalization definitions without explicit evidence.",),
        ),
        MetricContract(
            "q_perturbation",
            "Q perturbation",
            "Q-Factor (Perturbation)",
            "native CST perturbation quality factor",
            "1",
            r"Tables\0D Results\Q-Factor (Perturbation) (Mode {mode_index})",
            scalar_method,
            "native CST perturbation template using the case material assignment",
            "same established mode_identity.v0, material, and perturbation template",
            "repository_verified_locator",
            ("This is not established as Q0 and must never be relabeled Q0.",),
        ),
        MetricContract(
            "stored_energy",
            "Stored energy",
            "Stored energy",
            "time-average stored electromagnetic energy",
            "J",
            "not_established",
            "not_established",
            "requires an explicit native field-amplitude normalization",
            "same established mode_identity.v0 and field normalization",
            "not_established",
            ("No verified CST result locator exists in the current repository.",),
        ),
        MetricContract(
            "epk",
            "Epk",
            "Peak electric field",
            "peak electric-field magnitude on the declared evaluation domain",
            "MV/m",
            "not_established",
            "not_established",
            "requires explicit field normalization and evaluation domain",
            "same established mode_identity.v0 and electric-field bundle",
            "not_established",
            ("Peak domain and field export path remain unverified.",),
        ),
        MetricContract(
            "bpk",
            "Bpk",
            "Peak magnetic flux density",
            "peak magnetic flux density, not magnetic field strength H",
            "mT",
            "not_established",
            "not_established",
            "requires explicit field normalization and evaluation domain",
            "same established mode_identity.v0 and magnetic-field bundle",
            "not_established",
            ("Bpk means flux density B; it must not be substituted with Hpk.",),
        ),
        MetricContract(
            "epk_over_eacc",
            "Epk/Eacc",
            "Peak electric field over accelerating gradient",
            "peak electric field divided by accelerating gradient",
            "1",
            "not_established",
            "not_established",
            "requires documented accelerating-voltage path and effective length",
            "same established mode_identity.v0, Epk domain, voltage path, and effective length",
            "not_established",
            ("Eacc is not established until path and effective length are explicit.",),
        ),
        MetricContract(
            "bpk_over_eacc",
            "Bpk/Eacc",
            "Peak magnetic flux density over accelerating gradient",
            "peak magnetic flux density divided by accelerating gradient",
            "mT/(MV/m)",
            "not_established",
            "not_established",
            "requires documented accelerating-voltage path and effective length",
            "same established mode_identity.v0, Bpk domain, voltage path, and effective length",
            "not_established",
            ("Eacc is not established until path and effective length are explicit.",),
        ),
        MetricContract(
            "surface_loss",
            "Surface loss",
            "Surface loss",
            "integrated RF surface power loss over the declared conductor boundary",
            "W",
            "not_established",
            "not_established",
            "requires explicit field normalization, conductor material, and integration boundary",
            "same established mode_identity.v0, material, normalization, and loss domain",
            "not_established",
            ("No verified CST loss-integration result locator exists in the repository.",),
        ),
    )
    if tuple(item.metric_key for item in definitions) != REQUIRED_METRIC_KEYS:
        raise AssertionError("initial RF metric definition order drifted")
    return definitions


__all__ = [
    "EXTRACTION_SUPPORT_STATUSES",
    "METRIC_CONTRACT_SCHEMA_VERSION",
    "METRIC_OBSERVATION_SCHEMA_VERSION",
    "METRIC_UNITS",
    "METRIC_VALIDATION_STATUSES",
    "REQUIRED_METRIC_KEYS",
    "MetricContract",
    "MetricObservation",
    "build_initial_metric_contracts",
]
