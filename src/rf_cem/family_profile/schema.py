"""JSON Schema data for the generic RF-CEM family profile contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


FAMILY_PROFILE_SCHEMA_VERSION = "family_profile.v0"
FAMILY_INSTANCE_SCHEMA_VERSION = "family_instance.v0"


_HASH_PATTERN = r"^(sha256:)?[0-9a-fA-F]{64}$"
_VALIDATION_STATUS_ENUM = [
    "pass",
    "pending",
    "frozen",
    "partial",
    "not_run",
    "not_linked",
    "not_established",
]


FAMILY_PROFILE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "rf_cem.family_profile.v0",
    "title": "RF-CEM family profile v0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "family_id",
        "family_identity",
        "canonicalization_contract",
        "instances",
        "family_assertion_status",
        "metric_contract_status",
        "scope",
        "exclusions",
    ],
    "properties": {
        "schema_version": {"const": FAMILY_PROFILE_SCHEMA_VERSION},
        "family_id": {"const": "nc_axisymmetric_single_cell_rf_vacuum"},
        "family_identity": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "operating_regime",
                "symmetry",
                "cell_count",
                "geometry_scope",
            ],
            "properties": {
                "operating_regime": {"const": "normal_conducting"},
                "symmetry": {"const": "axisymmetric"},
                "cell_count": {"const": "single"},
                "geometry_scope": {"const": "rf_vacuum"},
            },
        },
        "canonicalization_contract": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "contract_id",
                "encoding",
                "sort_keys",
                "separators",
                "ensure_ascii",
                "allow_nan",
                "rfc8785_claim",
                "hash_format",
            ],
            "properties": {
                "contract_id": {"const": "rf_cem_family_canonical_json.v0"},
                "encoding": {"const": "UTF-8"},
                "sort_keys": {"const": True},
                "separators": {
                    "type": "array",
                    "prefixItems": [{"const": ","}, {"const": ":"}],
                    "minItems": 2,
                    "maxItems": 2,
                },
                "ensure_ascii": {"const": False},
                "allow_nan": {"const": False},
                "rfc8785_claim": {"const": False},
                "hash_format": {"const": "lowercase_hex_sha256"},
            },
        },
        "instances": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/family_instance.v0"},
        },
        "family_assertion_status": {
            "enum": ["supported", "pending"],
        },
        "metric_contract_status": {
            "const": "excluded_pending_definition",
        },
        "scope": {"type": "object"},
        "exclusions": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "$defs": {
        "hash": {"type": "string", "pattern": _HASH_PATTERN},
        "evidence": {
            "type": "object",
            "additionalProperties": True,
            "required": ["bundle_relative_path", "locator"],
            "properties": {
                "bundle_relative_path": {"type": "string", "minLength": 1},
                "locator": {"type": "string", "minLength": 1},
                "source_file_sha256": {"$ref": "#/$defs/hash"},
                "raw_sha256": {"$ref": "#/$defs/hash"},
                "canonical_payload_sha256": {"$ref": "#/$defs/hash"},
            },
        },
        "validation_layer": {
            "type": "object",
            "additionalProperties": True,
            "required": ["status"],
            "properties": {
                "status": {"enum": _VALIDATION_STATUS_ENUM},
            },
        },
        "family_instance.v0": {
            "type": "object",
            "additionalProperties": False,
            "required": [
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
            ],
            "properties": {
                "schema_version": {"const": FAMILY_INSTANCE_SCHEMA_VERSION},
                "instance_id": {"type": "string", "minLength": 1},
                "family_id": {"const": "nc_axisymmetric_single_cell_rf_vacuum"},
                "source_binding": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["manifest_id", "manifest_schema_version", "manifest_raw_sha256", "artifacts"],
                    "properties": {
                        "manifest_id": {"type": "string", "minLength": 1},
                        "manifest_schema_version": {"type": "string", "minLength": 1},
                        "manifest_raw_sha256": {"$ref": "#/$defs/hash"},
                        "artifacts": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["bundle_relative_path", "raw_sha256"],
                                "properties": {
                                    "bundle_relative_path": {"type": "string", "minLength": 1},
                                    "raw_sha256": {"$ref": "#/$defs/hash"},
                                    "canonical_sha256": {"$ref": "#/$defs/hash"},
                                    "role": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "native_schema": {"type": "string", "minLength": 1},
                "native_model_type": {"type": "string", "minLength": 1},
                "native_variant": {"type": "string", "minLength": 1},
                "native_units": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "minLength": 1},
                },
                "parameter_payload": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
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
                    ],
                    "properties": {
                        "adapter_id": {"type": "string", "minLength": 1},
                        "native_schema_version": {"type": "string", "minLength": 1},
                        "native_payload": {"type": "object"},
                        "native_payload_locator": {"type": "string", "minLength": 1},
                        "native_payload_canonical_sha256": {"$ref": "#/$defs/hash"},
                        "source_payload_canonical_sha256": {"$ref": "#/$defs/hash"},
                        "source_artifact_raw_sha256": {"$ref": "#/$defs/hash"},
                        "parameter_groups": {"type": "object", "minProperties": 1},
                        "parameter_count": {"type": "object", "minProperties": 1},
                        "units": {"type": "object"},
                        "scope": {"type": "string", "minLength": 1},
                        "source_refs": {"type": "array", "minItems": 1},
                        "portable_path_policy": {"type": "string"},
                    },
                },
                "geometry_artifacts": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "required": ["role", "bundle_relative_path", "raw_sha256"],
                        "properties": {
                            "role": {"type": "string", "minLength": 1},
                            "bundle_relative_path": {"type": "string", "minLength": 1},
                            "raw_sha256": {"$ref": "#/$defs/hash"},
                            "canonical_sha256": {"$ref": "#/$defs/hash"},
                        },
                    },
                },
                "validation_layers": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "payload_schema_validation",
                        "parameter_validation",
                        "geometry_generation",
                        "geometry_validation",
                        "human_review",
                        "helper2_review",
                        "live_cst",
                        "physical_acceptance",
                    ],
                    "properties": {
                        name: {"$ref": "#/$defs/validation_layer"}
                        for name in (
                            "payload_schema_validation",
                            "parameter_validation",
                            "geometry_generation",
                            "geometry_validation",
                            "human_review",
                            "helper2_review",
                            "live_cst",
                            "physical_acceptance",
                        )
                    },
                },
                "family_assertion_evidence": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "operating_regime",
                        "symmetry",
                        "cell_count",
                        "geometry_scope",
                    ],
                    "properties": {
                        key: {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["claim", "status", "evidence"],
                            "properties": {
                                "claim": {"type": "string", "minLength": 1},
                                "status": {"enum": ["supported", "pending"]},
                                "evidence": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"$ref": "#/$defs/evidence"},
                                },
                                "basis": {"type": "string"},
                            },
                        }
                        for key in (
                            "operating_regime",
                            "symmetry",
                            "cell_count",
                            "geometry_scope",
                        )
                    },
                },
                "provenance": {"type": "object"},
                "live_cst": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["status"],
                    "properties": {"status": {"enum": ["not_run", "not_linked"]}},
                },
                "physical_acceptance": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["status"],
                    "properties": {"status": {"const": "not_established"}},
                },
            },
        },
    },
}


def load_family_profile_schema() -> dict[str, Any]:
    """Return a defensive copy of the generic family profile JSON Schema."""

    return deepcopy(FAMILY_PROFILE_SCHEMA)
