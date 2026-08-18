"""Typed data containers, canonical hashing, and validation for family profiles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from .schema import (
    FAMILY_INSTANCE_SCHEMA_VERSION,
    FAMILY_PROFILE_SCHEMA_VERSION,
    load_family_profile_schema,
)


FAMILY_ID = "nc_axisymmetric_single_cell_rf_vacuum"
FAMILY_IDENTITY: dict[str, str] = {
    "operating_regime": "normal_conducting",
    "symmetry": "axisymmetric",
    "cell_count": "single",
    "geometry_scope": "rf_vacuum",
}
CANONICALIZATION_CONTRACT_ID = "rf_cem_family_canonical_json.v0"
VALIDATION_LAYERS = (
    "payload_schema_validation",
    "parameter_validation",
    "geometry_generation",
    "geometry_validation",
    "human_review",
    "helper2_review",
    "live_cst",
    "physical_acceptance",
)
VALIDATION_STATUSES = frozenset(
    {
        "pass",
        "pending",
        "frozen",
        "partial",
        "not_run",
        "not_linked",
        "not_established",
    }
)
EXCLUDED_METRICS = (
    "Epk/Eacc",
    "Bpk/Eacc",
    "R/Q",
    "Q",
    "shunt impedance",
    "(R/Q)*Q",
    "power/gradient equivalence",
    "wake/impedance objectives",
)
_HASH_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


class FamilyProfileError(ValueError):
    """Raised when a family profile or source binding is invalid."""


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON-compatible data under the family canonicalization contract.

    The contract uses UTF-8, sorted keys, compact separators, and literal
    Unicode.  Python's ``allow_nan=False`` makes non-standard NaN/Infinity
    values fail closed.  This is deliberately not advertised as RFC 8785.
    """

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FamilyProfileError(
            "family canonicalization requires finite JSON-compatible data"
        ) from exc


def canonical_sha256(value: object) -> str:
    """Return a lowercase, unprefixed SHA-256 for canonical JSON data."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the raw SHA-256 of a file without rewriting or normalizing it."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_absolute_path_string(value: str) -> bool:
    return bool(_WINDOWS_ABSOLUTE_RE.match(value)) or (
        value.startswith("/") and not value.startswith("//")
    )


def _check_finite_json(value: object, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise FamilyProfileError(f"{path} contains NaN or Infinity")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise FamilyProfileError(f"{path} contains a non-string object key")
            _check_finite_json(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _check_finite_json(child, f"{path}[{index}]")


def _check_no_absolute_paths(value: object, path: str = "$") -> None:
    if isinstance(value, str) and _is_absolute_path_string(value):
        raise FamilyProfileError(f"{path} contains a machine absolute path")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _check_no_absolute_paths(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _check_no_absolute_paths(child, f"{path}[{index}]")


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FamilyProfileError(f"{path} must be an object")
    return value


def _require_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FamilyProfileError(f"{path} must be a non-empty string")
    return value


def _require_hash(value: object, path: str) -> str:
    text = _require_string(value, path)
    if not _HASH_RE.fullmatch(text):
        raise FamilyProfileError(f"{path} must be a SHA-256 hex digest")
    return text.removeprefix("sha256:").lower()


def _require_relative_reference(value: object, path: str) -> str:
    text = _require_string(value, path)
    if _is_absolute_path_string(text):
        raise FamilyProfileError(f"{path} must be relative")
    return text


def _require_exact_keys(mapping: Mapping[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - set(mapping))
    extra = sorted(set(mapping) - required)
    if missing:
        raise FamilyProfileError(f"{path} is missing required fields: {missing}")
    if extra:
        raise FamilyProfileError(f"{path} contains unsupported fields: {extra}")


def _validate_canonicalization_contract(value: object) -> None:
    contract = _require_mapping(value, "canonicalization_contract")
    _require_exact_keys(
        contract,
        {
            "contract_id",
            "encoding",
            "sort_keys",
            "separators",
            "ensure_ascii",
            "allow_nan",
            "rfc8785_claim",
            "hash_format",
        },
        "canonicalization_contract",
    )
    expected = {
        "contract_id": CANONICALIZATION_CONTRACT_ID,
        "encoding": "UTF-8",
        "sort_keys": True,
        "ensure_ascii": False,
        "allow_nan": False,
        "rfc8785_claim": False,
        "hash_format": "lowercase_hex_sha256",
    }
    for key, expected_value in expected.items():
        if contract[key] != expected_value:
            raise FamilyProfileError(
                f"canonicalization_contract.{key} must be {expected_value!r}"
            )
    if contract["separators"] != [",", ":"]:
        raise FamilyProfileError("canonicalization_contract.separators must be [',', ':']")


def _validate_source_binding(value: object, path: str) -> None:
    binding = _require_mapping(value, path)
    _require_exact_keys(
        binding,
        {"manifest_id", "manifest_schema_version", "manifest_raw_sha256", "artifacts"},
        path,
    )
    _require_string(binding["manifest_id"], f"{path}.manifest_id")
    _require_string(binding["manifest_schema_version"], f"{path}.manifest_schema_version")
    _require_hash(binding["manifest_raw_sha256"], f"{path}.manifest_raw_sha256")
    artifacts = binding["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise FamilyProfileError(f"{path}.artifacts must be a non-empty array")
    for index, artifact in enumerate(artifacts):
        item_path = f"{path}.artifacts[{index}]"
        item = _require_mapping(artifact, item_path)
        allowed = {"bundle_relative_path", "raw_sha256", "canonical_sha256", "role"}
        extra = set(item) - allowed
        if extra:
            raise FamilyProfileError(f"{item_path} contains unsupported fields: {sorted(extra)}")
        _require_relative_reference(item.get("bundle_relative_path"), f"{item_path}.bundle_relative_path")
        _require_hash(item.get("raw_sha256"), f"{item_path}.raw_sha256")
        if item.get("canonical_sha256") is not None:
            _require_hash(item["canonical_sha256"], f"{item_path}.canonical_sha256")
        if item.get("role") is not None:
            _require_string(item["role"], f"{item_path}.role")


def _validate_parameter_groups(value: object, path: str) -> None:
    groups = _require_mapping(value, path)
    if not groups:
        raise FamilyProfileError(f"{path} must contain at least one group")
    for name, raw_group in groups.items():
        group_path = f"{path}.{name}"
        _require_string(name, group_path)
        group = _require_mapping(raw_group, group_path)
        if "values" not in group or "count" not in group:
            raise FamilyProfileError(f"{group_path} requires values and count")
        values = _require_mapping(group["values"], f"{group_path}.values")
        count = group["count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise FamilyProfileError(f"{group_path}.count must be a non-negative integer")
        if count != len(values):
            raise FamilyProfileError(f"{group_path}.count does not match values")
        _check_finite_json(values, f"{group_path}.values")


def _validate_evidence(value: object, path: str) -> None:
    evidence = _require_mapping(value, path)
    _require_relative_reference(evidence.get("bundle_relative_path"), f"{path}.bundle_relative_path")
    _require_string(evidence.get("locator"), f"{path}.locator")
    hash_fields = ("source_file_sha256", "raw_sha256", "canonical_payload_sha256")
    if not any(evidence.get(field) is not None for field in hash_fields):
        raise FamilyProfileError(f"{path} must contain hash-bound evidence")
    for field in hash_fields:
        if evidence.get(field) is not None:
            _require_hash(evidence[field], f"{path}.{field}")


def _validate_family_assertions(value: object, path: str) -> None:
    assertions = _require_mapping(value, path)
    if set(assertions) != set(FAMILY_IDENTITY):
        raise FamilyProfileError(f"{path} must contain the four family identity assertions")
    for key, expected_claim in FAMILY_IDENTITY.items():
        assertion_path = f"{path}.{key}"
        assertion = _require_mapping(assertions[key], assertion_path)
        allowed = {"claim", "status", "evidence", "basis"}
        extra = set(assertion) - allowed
        if extra:
            raise FamilyProfileError(f"{assertion_path} contains unsupported fields: {sorted(extra)}")
        if assertion.get("claim") != expected_claim:
            raise FamilyProfileError(f"{assertion_path}.claim does not match family identity")
        if assertion.get("status") not in {"supported", "pending"}:
            raise FamilyProfileError(f"{assertion_path}.status is invalid")
        evidence = assertion.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise FamilyProfileError(f"{assertion_path}.evidence must be non-empty")
        for index, item in enumerate(evidence):
            _validate_evidence(item, f"{assertion_path}.evidence[{index}]")


def _validate_validation_layers(value: object, path: str) -> None:
    layers = _require_mapping(value, path)
    if set(layers) != set(VALIDATION_LAYERS):
        raise FamilyProfileError(f"{path} must preserve all validation layers separately")
    for name in VALIDATION_LAYERS:
        layer_path = f"{path}.{name}"
        layer = _require_mapping(layers[name], layer_path)
        status = layer.get("status")
        if status not in VALIDATION_STATUSES:
            raise FamilyProfileError(f"{layer_path}.status is invalid: {status!r}")
        _check_finite_json(layer, layer_path)


def _validate_instance_mapping(instance: Mapping[str, Any], path: str) -> None:
    required = {
        "schema_version",
        "instance_id",
        "family_id",
        "source_binding",
        "native_schema",
        "native_model_type",
        "native_variant",
        "native_units",
        "parameter_payload",
        "geometry_artifacts",
        "validation_layers",
        "family_assertion_evidence",
        "provenance",
        "live_cst",
        "physical_acceptance",
    }
    _require_exact_keys(instance, required, path)
    if instance["schema_version"] != FAMILY_INSTANCE_SCHEMA_VERSION:
        raise FamilyProfileError(f"{path}.schema_version is invalid")
    _require_string(instance["instance_id"], f"{path}.instance_id")
    if instance["family_id"] != FAMILY_ID:
        raise FamilyProfileError(f"{path}.family_id does not match the profile family")
    _validate_source_binding(instance["source_binding"], f"{path}.source_binding")
    for field in ("native_schema", "native_model_type", "native_variant"):
        _require_string(instance[field], f"{path}.{field}")
    native_units = _require_mapping(instance["native_units"], f"{path}.native_units")
    for key, unit in native_units.items():
        _require_string(key, f"{path}.native_units key")
        _require_string(unit, f"{path}.native_units.{key}")

    payload_path = f"{path}.parameter_payload"
    payload = _require_mapping(instance["parameter_payload"], payload_path)
    required_payload = {
        "adapter_id",
        "native_schema_version",
        "native_payload",
        "native_payload_locator",
        "native_payload_canonical_sha256",
        "source_artifact_raw_sha256",
        "parameter_groups",
        "parameter_count",
        "units",
        "scope",
        "source_refs",
    }
    optional_payload = {"source_payload_canonical_sha256", "portable_path_policy"}
    missing_payload = sorted(required_payload - set(payload))
    extra_payload = sorted(set(payload) - required_payload - optional_payload)
    if missing_payload:
        raise FamilyProfileError(
            f"{payload_path} is missing required fields: {missing_payload}"
        )
    if extra_payload:
        raise FamilyProfileError(
            f"{payload_path} contains unsupported fields: {extra_payload}"
        )
    for field in ("adapter_id", "native_schema_version", "native_payload_locator", "scope"):
        _require_string(payload[field], f"{payload_path}.{field}")
    native_payload = _require_mapping(payload["native_payload"], f"{payload_path}.native_payload")
    _check_finite_json(native_payload, f"{payload_path}.native_payload")
    _require_hash(
        payload["native_payload_canonical_sha256"],
        f"{payload_path}.native_payload_canonical_sha256",
    )
    if canonical_sha256(native_payload) != _require_hash(
        payload["native_payload_canonical_sha256"],
        f"{payload_path}.native_payload_canonical_sha256",
    ):
        raise FamilyProfileError(f"{payload_path}.native_payload canonical hash mismatch")
    if payload.get("source_payload_canonical_sha256") is not None:
        _require_hash(payload["source_payload_canonical_sha256"], f"{payload_path}.source_payload_canonical_sha256")
    _require_hash(payload["source_artifact_raw_sha256"], f"{payload_path}.source_artifact_raw_sha256")
    _validate_parameter_groups(payload["parameter_groups"], f"{payload_path}.parameter_groups")
    parameter_count = _require_mapping(payload["parameter_count"], f"{payload_path}.parameter_count")
    for key, count in parameter_count.items():
        _require_string(key, f"{payload_path}.parameter_count key")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise FamilyProfileError(f"{payload_path}.parameter_count.{key} must be non-negative integer")
    units = _require_mapping(payload["units"], f"{payload_path}.units")
    for key, unit in units.items():
        _require_string(key, f"{payload_path}.units key")
        _require_string(unit, f"{payload_path}.units.{key}")
    source_refs = payload["source_refs"]
    if not isinstance(source_refs, list) or not source_refs:
        raise FamilyProfileError(f"{payload_path}.source_refs must be non-empty")
    for index, ref in enumerate(source_refs):
        _check_no_absolute_paths(ref, f"{payload_path}.source_refs[{index}]")
        if isinstance(ref, Mapping):
            if ref.get("bundle_relative_path") is not None:
                _require_relative_reference(ref["bundle_relative_path"], f"{payload_path}.source_refs[{index}].bundle_relative_path")
            for field in ("raw_sha256", "source_file_sha256", "canonical_sha256", "canonical_payload_sha256"):
                if ref.get(field) is not None:
                    _require_hash(ref[field], f"{payload_path}.source_refs[{index}].{field}")
        else:
            _require_string(ref, f"{payload_path}.source_refs[{index}]")
    if payload.get("portable_path_policy") is not None:
        _require_string(payload["portable_path_policy"], f"{payload_path}.portable_path_policy")

    geometry_artifacts = instance["geometry_artifacts"]
    if not isinstance(geometry_artifacts, list) or not geometry_artifacts:
        raise FamilyProfileError(f"{path}.geometry_artifacts must be non-empty")
    for index, artifact in enumerate(geometry_artifacts):
        artifact_path = f"{path}.geometry_artifacts[{index}]"
        item = _require_mapping(artifact, artifact_path)
        _require_string(item.get("role"), f"{artifact_path}.role")
        _require_relative_reference(item.get("bundle_relative_path"), f"{artifact_path}.bundle_relative_path")
        _require_hash(item.get("raw_sha256"), f"{artifact_path}.raw_sha256")
        if item.get("canonical_sha256") is not None:
            _require_hash(item["canonical_sha256"], f"{artifact_path}.canonical_sha256")
    _validate_validation_layers(instance["validation_layers"], f"{path}.validation_layers")
    _validate_family_assertions(instance["family_assertion_evidence"], f"{path}.family_assertion_evidence")
    _require_mapping(instance["provenance"], f"{path}.provenance")
    live = _require_mapping(instance["live_cst"], f"{path}.live_cst")
    if live.get("status") not in {"not_run", "not_linked"}:
        raise FamilyProfileError(f"{path}.live_cst may not claim a live result in family profile v0")
    physical = _require_mapping(instance["physical_acceptance"], f"{path}.physical_acceptance")
    if physical.get("status") != "not_established":
        raise FamilyProfileError(f"{path}.physical_acceptance must remain not_established")


def validate_profile_mapping(profile: Mapping[str, Any]) -> None:
    """Validate a profile against the generic contract and semantic guardrails."""

    _check_finite_json(profile)
    _check_no_absolute_paths(profile)
    required = {
        "schema_version",
        "family_id",
        "family_identity",
        "canonicalization_contract",
        "instances",
        "family_assertion_status",
        "metric_contract_status",
        "scope",
        "exclusions",
    }
    _require_exact_keys(profile, required, "profile")
    if profile["schema_version"] != FAMILY_PROFILE_SCHEMA_VERSION:
        raise FamilyProfileError("profile.schema_version is invalid")
    if profile["family_id"] != FAMILY_ID:
        raise FamilyProfileError("profile.family_id is invalid")
    if profile["family_identity"] != FAMILY_IDENTITY:
        raise FamilyProfileError("profile.family_identity is invalid")
    _validate_canonicalization_contract(profile["canonicalization_contract"])
    if profile["family_assertion_status"] not in {"supported", "pending"}:
        raise FamilyProfileError("profile.family_assertion_status is invalid")
    if profile["metric_contract_status"] != "excluded_pending_definition":
        raise FamilyProfileError("profile.metric_contract_status must remain excluded_pending_definition")
    _require_mapping(profile["scope"], "profile.scope")
    exclusions = profile["exclusions"]
    if not isinstance(exclusions, list) or not all(isinstance(item, str) and item for item in exclusions):
        raise FamilyProfileError("profile.exclusions must be a list of non-empty strings")
    if not set(EXCLUDED_METRICS).issubset(set(exclusions)):
        raise FamilyProfileError("profile.exclusions must include the v0 metric exclusions")
    scope = profile["scope"]
    executable = scope.get("executable_family_objectives", [])
    if executable != []:
        raise FamilyProfileError("family executable objectives must remain empty in v0")
    instances = profile["instances"]
    if not isinstance(instances, list) or not instances:
        raise FamilyProfileError("profile.instances must contain at least one instance")
    ids: set[str] = set()
    for index, raw_instance in enumerate(instances):
        instance = _require_mapping(raw_instance, f"profile.instances[{index}]")
        instance_id = _require_string(instance.get("instance_id"), f"profile.instances[{index}].instance_id")
        if instance_id in ids:
            raise FamilyProfileError(f"duplicate instance_id: {instance_id}")
        ids.add(instance_id)
        _validate_instance_mapping(instance, f"profile.instances[{index}]")


class NativePayloadAdapter(Protocol):
    """Minimal protocol consumed by the round-trip verifier."""

    adapter_id: str

    def restore_native_payload(self, instance: "FamilyInstance") -> dict[str, Any]:
        """Restore the canonical native payload stored in an instance."""


@dataclass(frozen=True)
class FamilyInstance:
    """One native geometry payload projected into the family contract."""

    schema_version: str
    instance_id: str
    family_id: str
    source_binding: dict[str, Any]
    native_schema: str
    native_model_type: str
    native_variant: str
    native_units: dict[str, str]
    parameter_payload: dict[str, Any]
    geometry_artifacts: list[dict[str, Any]]
    validation_layers: dict[str, dict[str, Any]]
    family_assertion_evidence: dict[str, dict[str, Any]]
    provenance: dict[str, Any]
    live_cst: dict[str, Any]
    physical_acceptance: dict[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        """Return a JSON-compatible defensive mapping for this instance."""

        return {
            "schema_version": self.schema_version,
            "instance_id": self.instance_id,
            "family_id": self.family_id,
            "source_binding": deepcopy(self.source_binding),
            "native_schema": self.native_schema,
            "native_model_type": self.native_model_type,
            "native_variant": self.native_variant,
            "native_units": deepcopy(self.native_units),
            "parameter_payload": deepcopy(self.parameter_payload),
            "geometry_artifacts": deepcopy(self.geometry_artifacts),
            "validation_layers": deepcopy(self.validation_layers),
            "family_assertion_evidence": deepcopy(self.family_assertion_evidence),
            "provenance": deepcopy(self.provenance),
            "live_cst": deepcopy(self.live_cst),
            "physical_acceptance": deepcopy(self.physical_acceptance),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FamilyInstance":
        """Validate and construct an instance from a profile mapping."""

        validate_profile_mapping(
            {
                "schema_version": FAMILY_PROFILE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "family_identity": deepcopy(FAMILY_IDENTITY),
                "canonicalization_contract": canonicalization_contract_mapping(),
                "instances": [value],
                "family_assertion_status": "supported",
                "metric_contract_status": "excluded_pending_definition",
                "scope": {"executable_family_objectives": []},
                "exclusions": list(EXCLUDED_METRICS),
            }
        )
        raw = dict(value)
        return cls(
            schema_version=raw["schema_version"],
            instance_id=raw["instance_id"],
            family_id=raw["family_id"],
            source_binding=deepcopy(raw["source_binding"]),
            native_schema=raw["native_schema"],
            native_model_type=raw["native_model_type"],
            native_variant=raw["native_variant"],
            native_units=deepcopy(raw["native_units"]),
            parameter_payload=deepcopy(raw["parameter_payload"]),
            geometry_artifacts=deepcopy(raw["geometry_artifacts"]),
            validation_layers=deepcopy(raw["validation_layers"]),
            family_assertion_evidence=deepcopy(raw["family_assertion_evidence"]),
            provenance=deepcopy(raw["provenance"]),
            live_cst=deepcopy(raw["live_cst"]),
            physical_acceptance=deepcopy(raw["physical_acceptance"]),
        )

    def validate(self) -> None:
        """Validate this instance without requiring a source bundle."""

        validate_profile_mapping(
            {
                "schema_version": FAMILY_PROFILE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "family_identity": deepcopy(FAMILY_IDENTITY),
                "canonicalization_contract": canonicalization_contract_mapping(),
                "instances": [self.to_mapping()],
                "family_assertion_status": "supported",
                "metric_contract_status": "excluded_pending_definition",
                "scope": {"executable_family_objectives": []},
                "exclusions": list(EXCLUDED_METRICS),
            }
        )

    def restore_native_payload(self) -> dict[str, Any]:
        """Return the stored native payload without renaming or flattening it."""

        return deepcopy(self.parameter_payload["native_payload"])


@dataclass(frozen=True)
class FamilyProfile:
    """A deterministic family profile containing one or more instances."""

    schema_version: str
    family_id: str
    family_identity: dict[str, str]
    canonicalization_contract: dict[str, Any]
    instances: tuple[FamilyInstance, ...]
    family_assertion_status: str
    metric_contract_status: str
    scope: dict[str, Any]
    exclusions: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        """Return the deterministic profile core without timestamps or paths."""

        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "family_identity": deepcopy(self.family_identity),
            "canonicalization_contract": deepcopy(self.canonicalization_contract),
            "instances": [instance.to_mapping() for instance in self.instances],
            "family_assertion_status": self.family_assertion_status,
            "metric_contract_status": self.metric_contract_status,
            "scope": deepcopy(self.scope),
            "exclusions": list(self.exclusions),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FamilyProfile":
        """Validate and construct a profile from a JSON-compatible mapping."""

        validate_profile_mapping(value)
        return cls(
            schema_version=value["schema_version"],
            family_id=value["family_id"],
            family_identity=deepcopy(value["family_identity"]),
            canonicalization_contract=deepcopy(value["canonicalization_contract"]),
            instances=tuple(FamilyInstance.from_mapping(item) for item in value["instances"]),
            family_assertion_status=value["family_assertion_status"],
            metric_contract_status=value["metric_contract_status"],
            scope=deepcopy(value["scope"]),
            exclusions=tuple(value["exclusions"]),
        )

    def validate(self) -> None:
        """Validate this profile against the generic schema guardrails."""

        validate_profile_mapping(self.to_mapping())


def canonicalization_contract_mapping() -> dict[str, Any]:
    """Return the explicit canonical JSON contract embedded in a profile."""

    return {
        "contract_id": CANONICALIZATION_CONTRACT_ID,
        "encoding": "UTF-8",
        "sort_keys": True,
        "separators": [",", ":"],
        "ensure_ascii": False,
        "allow_nan": False,
        "rfc8785_claim": False,
        "hash_format": "lowercase_hex_sha256",
    }


def make_family_profile(instances: list[FamilyInstance] | tuple[FamilyInstance, ...]) -> FamilyProfile:
    """Build and validate a generic profile from one or more instances."""

    profile = FamilyProfile(
        schema_version=FAMILY_PROFILE_SCHEMA_VERSION,
        family_id=FAMILY_ID,
        family_identity=deepcopy(FAMILY_IDENTITY),
        canonicalization_contract=canonicalization_contract_mapping(),
        instances=tuple(instances),
        family_assertion_status="supported",
        metric_contract_status="excluded_pending_definition",
        scope={
            "operating_regime": "normal_conducting",
            "symmetry": "axisymmetric",
            "cell_count": "single",
            "geometry_scope": "rf_vacuum",
            "executable_family_objectives": [],
            "validation_mode": "no_cst_source_audit",
        },
        exclusions=EXCLUDED_METRICS,
    )
    profile.validate()
    return profile


def load_profile(path: Path) -> FamilyProfile:
    """Load and validate one family profile JSON file."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FamilyProfileError(f"cannot read family profile: {path}") from exc
    if not isinstance(value, Mapping):
        raise FamilyProfileError("family profile root must be an object")
    return FamilyProfile.from_mapping(value)


def write_profile(path: Path, profile: FamilyProfile) -> tuple[str, str]:
    """Write a deterministic profile and return ``(raw_sha256, canonical_sha256)``."""

    profile.validate()
    raw = json.dumps(
        profile.to_mapping(), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest(), canonical_sha256(profile.to_mapping())


def verify_round_trip(adapter: NativePayloadAdapter, instance: FamilyInstance) -> dict[str, Any]:
    """Verify lossless canonical round-trip for an adapter-built instance."""

    expected = _require_hash(
        instance.parameter_payload["native_payload_canonical_sha256"],
        "instance.parameter_payload.native_payload_canonical_sha256",
    )
    restored = adapter.restore_native_payload(instance)
    restored_hash = canonical_sha256(restored)
    if restored_hash != expected:
        raise FamilyProfileError(
            f"adapter round-trip hash mismatch for {instance.instance_id}: "
            f"expected {expected}, got {restored_hash}"
        )
    return {
        "instance_id": instance.instance_id,
        "adapter_id": instance.parameter_payload["adapter_id"],
        "input_native_payload_canonical_sha256": expected,
        "restored_native_payload_canonical_sha256": restored_hash,
        "passed": True,
        "parameter_count": deepcopy(instance.parameter_payload["parameter_count"]),
    }


__all__ = [
    "CANONICALIZATION_CONTRACT_ID",
    "EXCLUDED_METRICS",
    "FAMILY_ID",
    "FAMILY_IDENTITY",
    "FAMILY_INSTANCE_SCHEMA_VERSION",
    "FAMILY_PROFILE_SCHEMA_VERSION",
    "FamilyInstance",
    "FamilyProfile",
    "FamilyProfileError",
    "NativePayloadAdapter",
    "VALIDATION_LAYERS",
    "canonical_json_bytes",
    "canonical_sha256",
    "canonicalization_contract_mapping",
    "file_sha256",
    "load_family_profile_schema",
    "load_profile",
    "make_family_profile",
    "validate_profile_mapping",
    "verify_round_trip",
    "write_profile",
]
