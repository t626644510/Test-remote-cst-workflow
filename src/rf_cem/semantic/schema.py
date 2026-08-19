"""JSON Schema data for the RF boundary semantic core contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .ontology import landmark_type_ids, region_type_ids


FAMILY_GRAMMAR_SCHEMA_VERSION = "family_grammar.v0"
INSTANCE_BOUNDARY_GRAPH_SCHEMA_VERSION = "instance_boundary_graph.v0"
SEMANTIC_MOTIF_SCHEMA_VERSION = "semantic_motif.v0"
GRAPH_DIFF_SCHEMA_VERSION = "instance_boundary_graph_diff.v0"
CANONICALIZATION_CONTRACT_ID = "rf_cem_semantic_canonical_json.v0"

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_SIDES = ["left", "right", "center"]
_REVIEW_STATES = [
    "accepted",
    "accepted_as_soft_only",
    "confirmed",
    "supported",
    "pending",
    "rejected",
]

_CANONICALIZATION_SCHEMA: dict[str, Any] = {
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
        "contract_id": {"const": CANONICALIZATION_CONTRACT_ID},
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
}

_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "source_kind",
        "source_path",
        "source_raw_sha256",
        "locator",
        "relation",
    ],
    "properties": {
        "source_kind": {"type": "string", "minLength": 1},
        "source_path": {"type": "string", "minLength": 1},
        "source_raw_sha256": {"type": "string", "pattern": _HASH_PATTERN},
        "subject_raw_sha256": {"type": "string", "pattern": _HASH_PATTERN},
        "locator": {"type": "string", "minLength": 1},
        "relation": {"type": "string", "minLength": 1},
    },
}

_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "item_id", "revision", "evidence"],
    "properties": {
        "status": {"enum": _REVIEW_STATES},
        "item_id": {"type": "string", "minLength": 1},
        "revision": {"type": ["integer", "null"], "minimum": 0},
        "evidence": _EVIDENCE_SCHEMA,
    },
}

_REGION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "region_id",
        "region_type",
        "side",
        "role",
        "source_feature_ids",
        "motif_id",
        "evidence",
        "review",
    ],
    "properties": {
        "region_id": {"type": "string", "minLength": 1},
        "region_type": {"enum": sorted(region_type_ids())},
        "side": {"enum": _SIDES},
        "role": {"type": "string", "minLength": 1},
        "source_feature_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "motif_id": {"type": ["string", "null"]},
        "evidence": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
        "review": _REVIEW_SCHEMA,
    },
}

_LANDMARK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "landmark_id",
        "landmark_type",
        "side",
        "incident_region_ids",
        "evidence",
        "review",
    ],
    "properties": {
        "landmark_id": {"type": "string", "minLength": 1},
        "landmark_type": {"enum": sorted(landmark_type_ids())},
        "side": {"enum": _SIDES},
        "incident_region_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "evidence": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
        "review": _REVIEW_SCHEMA,
    },
}

_INTERFACE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "interface_id",
        "left_region_id",
        "right_region_id",
        "landmark_id",
        "interface_role",
        "orientation",
        "evidence",
    ],
    "properties": {
        "interface_id": {"type": "string", "minLength": 1},
        "left_region_id": {"type": "string", "minLength": 1},
        "right_region_id": {"type": "string", "minLength": 1},
        "landmark_id": {"type": "string", "minLength": 1},
        "interface_role": {"const": "semantic_topological_join"},
        "orientation": {"const": "left_to_right"},
        "evidence": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
    },
}

_MOTIF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "motif_id",
        "label",
        "region_type",
        "occurrence_rule",
        "allowed_counts",
        "insertion_rules",
        "evidence",
    ],
    "properties": {
        "schema_version": {"const": SEMANTIC_MOTIF_SCHEMA_VERSION},
        "motif_id": {"type": "string", "minLength": 1},
        "label": {"type": "string", "minLength": 1},
        "region_type": {"enum": sorted(region_type_ids())},
        "occurrence_rule": {"const": "paired_optional"},
        "allowed_counts": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
            "prefixItems": [{"const": 0}, {"const": 2}],
        },
        "insertion_rules": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["side", "between_region_types"],
                "properties": {
                    "side": {"enum": ["left", "right"]},
                    "between_region_types": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"enum": sorted(region_type_ids())},
                    },
                },
            },
        },
        "evidence": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
    },
}


FAMILY_GRAMMAR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "rf_cem.family_grammar.v0",
    "title": "RF-CEM family grammar v0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "grammar_id",
        "family_id",
        "canonicalization_contract",
        "region_ontology",
        "landmark_ontology",
        "backbone_slots",
        "motifs",
        "type_cardinality",
        "allowed_adjacencies",
        "evidence",
        "review",
        "parameter_contract",
        "exclusions",
    ],
    "properties": {
        "schema_version": {"const": FAMILY_GRAMMAR_SCHEMA_VERSION},
        "grammar_id": {"type": "string", "minLength": 1},
        "family_id": {"type": "string", "minLength": 1},
        "canonicalization_contract": _CANONICALIZATION_SCHEMA,
        "region_ontology": {"type": "object"},
        "landmark_ontology": {"type": "object"},
        "backbone_slots": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["slot_id", "region_type", "side"],
                "properties": {
                    "slot_id": {"type": "string", "minLength": 1},
                    "region_type": {"enum": sorted(region_type_ids())},
                    "side": {"enum": _SIDES},
                },
            },
        },
        "motifs": {"type": "array", "items": _MOTIF_SCHEMA},
        "type_cardinality": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": 0},
            },
        },
        "allowed_adjacencies": {
            "type": "array",
            "items": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"enum": sorted(region_type_ids())},
            },
        },
        "evidence": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
        "review": _REVIEW_SCHEMA,
        "parameter_contract": {"const": "not_applicable_semantic_topology_only"},
        "exclusions": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
    },
}


INSTANCE_BOUNDARY_GRAPH_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "rf_cem.instance_boundary_graph.v0",
    "title": "RF-CEM instance boundary graph v0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "graph_id",
        "family_id",
        "instance_id",
        "canonicalization_contract",
        "boundary_scope",
        "axis",
        "orientation",
        "region_ontology_version",
        "landmark_ontology_version",
        "regions",
        "landmarks",
        "interfaces",
        "active_motif_ids",
        "nose_presence",
        "nose_evidence",
        "source_bindings",
        "parameter_contract",
        "exclusions",
    ],
    "properties": {
        "schema_version": {"const": INSTANCE_BOUNDARY_GRAPH_SCHEMA_VERSION},
        "graph_id": {"type": "string", "minLength": 1},
        "family_id": {"type": "string", "minLength": 1},
        "instance_id": {"type": "string", "minLength": 1},
        "canonicalization_contract": _CANONICALIZATION_SCHEMA,
        "boundary_scope": {"const": "axisymmetric_rf_vacuum_wall_profile"},
        "axis": {"const": "z"},
        "orientation": {"const": "negative_to_positive_z"},
        "region_ontology_version": {"type": "string", "minLength": 1},
        "landmark_ontology_version": {"type": "string", "minLength": 1},
        "regions": {"type": "array", "minItems": 3, "items": _REGION_SCHEMA},
        "landmarks": {"type": "array", "minItems": 3, "items": _LANDMARK_SCHEMA},
        "interfaces": {"type": "array", "minItems": 2, "items": _INTERFACE_SCHEMA},
        "active_motif_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "nose_presence": {"enum": ["present", "absent_reviewed_topology"]},
        "nose_evidence": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
        "source_bindings": {"type": "array", "minItems": 1, "items": _EVIDENCE_SCHEMA},
        "parameter_contract": {"const": "not_applicable_semantic_topology_only"},
        "exclusions": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
    },
}


GRAPH_DIFF_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "rf_cem.instance_boundary_graph_diff.v0",
    "title": "RF-CEM instance boundary graph diff v0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "canonicalization_contract",
        "left_graph_id",
        "right_graph_id",
        "left_graph_sha256",
        "right_graph_sha256",
        "classification",
        "common_regions",
        "left_only_regions",
        "right_only_regions",
        "adjacency_changes",
        "motif_changes",
        "parameter_comparison",
    ],
    "properties": {
        "schema_version": {"const": GRAPH_DIFF_SCHEMA_VERSION},
        "canonicalization_contract": _CANONICALIZATION_SCHEMA,
        "left_graph_id": {"type": "string", "minLength": 1},
        "right_graph_id": {"type": "string", "minLength": 1},
        "left_graph_sha256": {"type": "string", "pattern": _HASH_PATTERN},
        "right_graph_sha256": {"type": "string", "pattern": _HASH_PATTERN},
        "classification": {"const": "semantic_topology_difference"},
        "common_regions": {"type": "array"},
        "left_only_regions": {"type": "array"},
        "right_only_regions": {"type": "array"},
        "adjacency_changes": {"type": "array"},
        "motif_changes": {"type": "array"},
        "parameter_comparison": {
            "const": "not_applicable_no_common_geometry_parameter_vector"
        },
    },
}


def load_family_grammar_schema() -> dict[str, Any]:
    """Return a defensive copy of the family grammar JSON Schema."""

    return deepcopy(FAMILY_GRAMMAR_SCHEMA)


def load_instance_boundary_graph_schema() -> dict[str, Any]:
    """Return a defensive copy of the instance graph JSON Schema."""

    return deepcopy(INSTANCE_BOUNDARY_GRAPH_SCHEMA)


def load_graph_diff_schema() -> dict[str, Any]:
    """Return a defensive copy of the graph-diff JSON Schema."""

    return deepcopy(GRAPH_DIFF_SCHEMA)


__all__ = [
    "CANONICALIZATION_CONTRACT_ID",
    "FAMILY_GRAMMAR_SCHEMA",
    "FAMILY_GRAMMAR_SCHEMA_VERSION",
    "GRAPH_DIFF_SCHEMA",
    "GRAPH_DIFF_SCHEMA_VERSION",
    "INSTANCE_BOUNDARY_GRAPH_SCHEMA",
    "INSTANCE_BOUNDARY_GRAPH_SCHEMA_VERSION",
    "SEMANTIC_MOTIF_SCHEMA_VERSION",
    "load_family_grammar_schema",
    "load_graph_diff_schema",
    "load_instance_boundary_graph_schema",
]
