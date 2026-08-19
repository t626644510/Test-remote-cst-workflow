"""Typed contracts and fail-closed validation for RF boundary semantics."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence

from .ontology import (
    AXIAL_APERTURE_LANDMARK,
    BEAM_PIPE_REGION,
    EQUATOR_REGION,
    LANDMARK_ONTOLOGY_VERSION,
    NOSE_REGION,
    REGION_JUNCTION_LANDMARK,
    REGION_ONTOLOGY_VERSION,
    SYMMETRY_LANDMARK,
    landmark_ontology_mapping,
    landmark_type_ids,
    region_ontology_mapping,
    region_type_ids,
)
from .schema import (
    CANONICALIZATION_CONTRACT_ID,
    FAMILY_GRAMMAR_SCHEMA_VERSION,
    GRAPH_DIFF_SCHEMA_VERSION,
    INSTANCE_BOUNDARY_GRAPH_SCHEMA_VERSION,
    SEMANTIC_MOTIF_SCHEMA_VERSION,
)


NOSE_PAIR_MOTIF_ID = "motif.nose_pair.v0"
PARAMETER_CONTRACT = "not_applicable_semantic_topology_only"
DIFF_PARAMETER_CONTRACT = "not_applicable_no_common_geometry_parameter_vector"
TERMINAL_REVIEW_STATES = frozenset(
    {"accepted", "accepted_as_soft_only", "confirmed", "supported"}
)
REVIEW_STATES = TERMINAL_REVIEW_STATES | {"pending", "rejected"}
SIDES = frozenset({"left", "right", "center"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


class SemanticContractError(ValueError):
    """Raised when an RF boundary semantic contract fails closed."""


def canonicalization_contract() -> dict[str, Any]:
    """Return the explicit semantic canonical JSON contract."""

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


def canonical_json_bytes(value: object) -> bytes:
    """Encode finite JSON data under the semantic canonicalization contract."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticContractError(
            "semantic canonicalization requires finite JSON-compatible data"
        ) from exc


def canonical_sha256(value: object) -> str:
    """Return the canonical lowercase SHA-256 for one semantic object."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the raw lowercase SHA-256 for one source file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class EvidenceRef:
    """Hash-bound repository-relative evidence for a semantic assertion."""

    source_kind: str
    source_path: str
    source_raw_sha256: str
    locator: str
    relation: str
    subject_raw_sha256: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.source_kind, "evidence.source_kind")
        _relative_path(self.source_path, "evidence.source_path")
        _normalized_hash(self.source_raw_sha256, "evidence.source_raw_sha256")
        _non_empty(self.locator, "evidence.locator")
        _non_empty(self.relation, "evidence.relation")
        if self.subject_raw_sha256 is not None:
            _normalized_hash(
                self.subject_raw_sha256, "evidence.subject_raw_sha256"
            )

    def to_mapping(self) -> dict[str, Any]:
        """Return the portable evidence mapping."""

        result: dict[str, Any] = {
            "source_kind": self.source_kind,
            "source_path": self.source_path,
            "source_raw_sha256": self.source_raw_sha256,
            "locator": self.locator,
            "relation": self.relation,
        }
        if self.subject_raw_sha256 is not None:
            result["subject_raw_sha256"] = self.subject_raw_sha256
        return result

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRef":
        """Parse one strict evidence mapping."""

        mapping = _mapping(value, "evidence")
        _exact_keys(
            mapping,
            {
                "source_kind",
                "source_path",
                "source_raw_sha256",
                "locator",
                "relation",
            },
            {"subject_raw_sha256"},
            "evidence",
        )
        return cls(
            source_kind=_string(mapping["source_kind"], "evidence.source_kind"),
            source_path=_relative_path(
                mapping["source_path"], "evidence.source_path"
            ),
            source_raw_sha256=_normalized_hash(
                mapping["source_raw_sha256"], "evidence.source_raw_sha256"
            ),
            locator=_string(mapping["locator"], "evidence.locator"),
            relation=_string(mapping["relation"], "evidence.relation"),
            subject_raw_sha256=(
                _normalized_hash(
                    mapping["subject_raw_sha256"],
                    "evidence.subject_raw_sha256",
                )
                if mapping.get("subject_raw_sha256") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class ReviewBinding:
    """Explicit review state bound to a source item and revision."""

    status: str
    item_id: str
    revision: int | None
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        if self.status not in REVIEW_STATES:
            raise SemanticContractError(f"unsupported review status: {self.status}")
        _non_empty(self.item_id, "review.item_id")
        if self.revision is not None and (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 0
        ):
            raise SemanticContractError("review.revision must be null or a non-negative integer")

    @property
    def is_terminal(self) -> bool:
        """Return whether this review state can support a canonical R1 graph."""

        return self.status in TERMINAL_REVIEW_STATES

    def to_mapping(self) -> dict[str, Any]:
        """Return the portable review mapping."""

        return {
            "status": self.status,
            "item_id": self.item_id,
            "revision": self.revision,
            "evidence": self.evidence.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewBinding":
        """Parse one strict review mapping."""

        mapping = _mapping(value, "review")
        _exact_keys(
            mapping,
            {"status", "item_id", "revision", "evidence"},
            set(),
            "review",
        )
        revision = mapping["revision"]
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int)
        ):
            raise SemanticContractError("review.revision must be an integer or null")
        return cls(
            status=_string(mapping["status"], "review.status"),
            item_id=_string(mapping["item_id"], "review.item_id"),
            revision=revision,
            evidence=EvidenceRef.from_mapping(_mapping(mapping["evidence"], "review.evidence")),
        )


@dataclass(frozen=True)
class SemanticRegion:
    """One stable representation-independent region in an instance topology."""

    region_id: str
    region_type: str
    side: str
    role: str
    source_feature_ids: tuple[str, ...]
    motif_id: str | None
    evidence: tuple[EvidenceRef, ...]
    review: ReviewBinding

    def __post_init__(self) -> None:
        _non_empty(self.region_id, "region.region_id")
        if self.region_type not in region_type_ids():
            raise SemanticContractError(
                f"region.region_type is not in ontology v0: {self.region_type}"
            )
        if self.side not in SIDES:
            raise SemanticContractError(f"unsupported region side: {self.side}")
        _non_empty(self.role, "region.role")
        _unique_non_empty(self.source_feature_ids, "region.source_feature_ids")
        if self.motif_id is not None:
            _non_empty(self.motif_id, "region.motif_id")
        _evidence_tuple(self.evidence, "region.evidence")

    @property
    def semantic_key(self) -> str:
        """Return a family-comparable key that contains no instance parameter names."""

        return f"{self.side}:{self.region_type}"

    def to_mapping(self) -> dict[str, Any]:
        """Return the portable semantic-region mapping."""

        return {
            "region_id": self.region_id,
            "region_type": self.region_type,
            "side": self.side,
            "role": self.role,
            "source_feature_ids": list(self.source_feature_ids),
            "motif_id": self.motif_id,
            "evidence": [item.to_mapping() for item in self.evidence],
            "review": self.review.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SemanticRegion":
        """Parse one strict semantic-region mapping."""

        mapping = _mapping(value, "region")
        _exact_keys(
            mapping,
            {
                "region_id",
                "region_type",
                "side",
                "role",
                "source_feature_ids",
                "motif_id",
                "evidence",
                "review",
            },
            set(),
            "region",
        )
        motif = mapping["motif_id"]
        if motif is not None:
            motif = _string(motif, "region.motif_id")
        return cls(
            region_id=_string(mapping["region_id"], "region.region_id"),
            region_type=_string(mapping["region_type"], "region.region_type"),
            side=_string(mapping["side"], "region.side"),
            role=_string(mapping["role"], "region.role"),
            source_feature_ids=_string_tuple(
                mapping["source_feature_ids"], "region.source_feature_ids"
            ),
            motif_id=motif,
            evidence=_parse_evidence_array(mapping["evidence"], "region.evidence"),
            review=ReviewBinding.from_mapping(_mapping(mapping["review"], "region.review")),
        )


@dataclass(frozen=True)
class SemanticLandmark:
    """One stable landmark shared by regions or bound to a profile invariant."""

    landmark_id: str
    landmark_type: str
    side: str
    incident_region_ids: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    review: ReviewBinding

    def __post_init__(self) -> None:
        _non_empty(self.landmark_id, "landmark.landmark_id")
        if self.landmark_type not in landmark_type_ids():
            raise SemanticContractError(
                f"landmark type is not in ontology v0: {self.landmark_type}"
            )
        if self.side not in SIDES:
            raise SemanticContractError(f"unsupported landmark side: {self.side}")
        _unique_non_empty(self.incident_region_ids, "landmark.incident_region_ids")
        expected = 2 if self.landmark_type == REGION_JUNCTION_LANDMARK else 1
        if len(self.incident_region_ids) != expected:
            raise SemanticContractError(
                f"{self.landmark_type} requires {expected} incident region(s)"
            )
        _evidence_tuple(self.evidence, "landmark.evidence")

    def to_mapping(self) -> dict[str, Any]:
        """Return the portable landmark mapping."""

        return {
            "landmark_id": self.landmark_id,
            "landmark_type": self.landmark_type,
            "side": self.side,
            "incident_region_ids": list(self.incident_region_ids),
            "evidence": [item.to_mapping() for item in self.evidence],
            "review": self.review.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SemanticLandmark":
        """Parse one strict landmark mapping."""

        mapping = _mapping(value, "landmark")
        _exact_keys(
            mapping,
            {
                "landmark_id",
                "landmark_type",
                "side",
                "incident_region_ids",
                "evidence",
                "review",
            },
            set(),
            "landmark",
        )
        return cls(
            landmark_id=_string(mapping["landmark_id"], "landmark.landmark_id"),
            landmark_type=_string(
                mapping["landmark_type"], "landmark.landmark_type"
            ),
            side=_string(mapping["side"], "landmark.side"),
            incident_region_ids=_string_tuple(
                mapping["incident_region_ids"], "landmark.incident_region_ids"
            ),
            evidence=_parse_evidence_array(mapping["evidence"], "landmark.evidence"),
            review=ReviewBinding.from_mapping(
                _mapping(mapping["review"], "landmark.review")
            ),
        )


@dataclass(frozen=True)
class BoundaryInterface:
    """Topological join between two consecutive semantic regions."""

    interface_id: str
    left_region_id: str
    right_region_id: str
    landmark_id: str
    evidence: tuple[EvidenceRef, ...]
    interface_role: str = "semantic_topological_join"
    orientation: str = "left_to_right"

    def __post_init__(self) -> None:
        for value, path in (
            (self.interface_id, "interface.interface_id"),
            (self.left_region_id, "interface.left_region_id"),
            (self.right_region_id, "interface.right_region_id"),
            (self.landmark_id, "interface.landmark_id"),
        ):
            _non_empty(value, path)
        if self.left_region_id == self.right_region_id:
            raise SemanticContractError("interface cannot join a region to itself")
        if self.interface_role != "semantic_topological_join":
            raise SemanticContractError("unsupported interface_role")
        if self.orientation != "left_to_right":
            raise SemanticContractError("interface orientation must be left_to_right")
        _evidence_tuple(self.evidence, "interface.evidence")

    def to_mapping(self) -> dict[str, Any]:
        """Return the portable interface mapping."""

        return {
            "interface_id": self.interface_id,
            "left_region_id": self.left_region_id,
            "right_region_id": self.right_region_id,
            "landmark_id": self.landmark_id,
            "interface_role": self.interface_role,
            "orientation": self.orientation,
            "evidence": [item.to_mapping() for item in self.evidence],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BoundaryInterface":
        """Parse one strict boundary-interface mapping."""

        mapping = _mapping(value, "interface")
        _exact_keys(
            mapping,
            {
                "interface_id",
                "left_region_id",
                "right_region_id",
                "landmark_id",
                "interface_role",
                "orientation",
                "evidence",
            },
            set(),
            "interface",
        )
        return cls(
            interface_id=_string(mapping["interface_id"], "interface.interface_id"),
            left_region_id=_string(
                mapping["left_region_id"], "interface.left_region_id"
            ),
            right_region_id=_string(
                mapping["right_region_id"], "interface.right_region_id"
            ),
            landmark_id=_string(mapping["landmark_id"], "interface.landmark_id"),
            interface_role=_string(
                mapping["interface_role"], "interface.interface_role"
            ),
            orientation=_string(mapping["orientation"], "interface.orientation"),
            evidence=_parse_evidence_array(mapping["evidence"], "interface.evidence"),
        )


@dataclass(frozen=True)
class MotifInsertionRule:
    """One side-specific location where an optional motif may be inserted."""

    side: str
    between_region_types: tuple[str, str]

    def __post_init__(self) -> None:
        if self.side not in {"left", "right"}:
            raise SemanticContractError("motif insertion side must be left or right")
        if len(self.between_region_types) != 2:
            raise SemanticContractError("motif insertion requires two bounding types")
        for region_type in self.between_region_types:
            if region_type not in region_type_ids():
                raise SemanticContractError(
                    f"motif insertion references unknown region type: {region_type}"
                )

    def to_mapping(self) -> dict[str, Any]:
        """Return the insertion-rule mapping."""

        return {
            "side": self.side,
            "between_region_types": list(self.between_region_types),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MotifInsertionRule":
        """Parse one strict insertion-rule mapping."""

        mapping = _mapping(value, "insertion_rule")
        _exact_keys(
            mapping,
            {"side", "between_region_types"},
            set(),
            "insertion_rule",
        )
        values = _string_tuple(
            mapping["between_region_types"],
            "insertion_rule.between_region_types",
        )
        if len(values) != 2:
            raise SemanticContractError(
                "insertion_rule.between_region_types must contain two values"
            )
        return cls(
            side=_string(mapping["side"], "insertion_rule.side"),
            between_region_types=(values[0], values[1]),
        )


@dataclass(frozen=True)
class SemanticMotif:
    """Optional semantic topology rule that is independent of geometry parameters."""

    motif_id: str
    label: str
    region_type: str
    allowed_counts: tuple[int, ...]
    insertion_rules: tuple[MotifInsertionRule, ...]
    evidence: tuple[EvidenceRef, ...]
    occurrence_rule: str = "paired_optional"
    schema_version: str = SEMANTIC_MOTIF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_MOTIF_SCHEMA_VERSION:
            raise SemanticContractError("semantic motif schema_version must be semantic_motif.v0")
        _non_empty(self.motif_id, "motif.motif_id")
        _non_empty(self.label, "motif.label")
        if self.region_type not in region_type_ids():
            raise SemanticContractError("motif references an unknown region type")
        if self.occurrence_rule != "paired_optional":
            raise SemanticContractError("R1 motif occurrence_rule must be paired_optional")
        if (
            not self.allowed_counts
            or tuple(sorted(set(self.allowed_counts))) != self.allowed_counts
            or 0 not in self.allowed_counts
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0 or item % 2
                for item in self.allowed_counts
            )
        ):
            raise SemanticContractError(
                "paired_optional motif counts must be sorted unique non-negative even integers including zero"
            )
        if len(self.insertion_rules) != 2 or {
            rule.side for rule in self.insertion_rules
        } != {"left", "right"}:
            raise SemanticContractError("paired motif requires one left and one right insertion rule")
        if self.allowed_counts != (0, 2):
            raise SemanticContractError(
                "semantic_motif.v0 paired_optional counts must be exactly zero or two"
            )
        if any(
            self.region_type in rule.between_region_types
            for rule in self.insertion_rules
        ):
            raise SemanticContractError(
                "motif insertion bounds cannot already be the motif region type"
            )
        _evidence_tuple(self.evidence, "motif.evidence")

    def to_mapping(self) -> dict[str, Any]:
        """Return the portable semantic-motif mapping."""

        return {
            "schema_version": self.schema_version,
            "motif_id": self.motif_id,
            "label": self.label,
            "region_type": self.region_type,
            "occurrence_rule": self.occurrence_rule,
            "allowed_counts": list(self.allowed_counts),
            "insertion_rules": [item.to_mapping() for item in self.insertion_rules],
            "evidence": [item.to_mapping() for item in self.evidence],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SemanticMotif":
        """Parse one strict motif mapping."""

        mapping = _mapping(value, "motif")
        _exact_keys(
            mapping,
            {
                "schema_version",
                "motif_id",
                "label",
                "region_type",
                "occurrence_rule",
                "allowed_counts",
                "insertion_rules",
                "evidence",
            },
            set(),
            "motif",
        )
        counts = _integer_tuple(mapping["allowed_counts"], "motif.allowed_counts")
        rules = _mapping_array(mapping["insertion_rules"], "motif.insertion_rules")
        return cls(
            schema_version=_string(mapping["schema_version"], "motif.schema_version"),
            motif_id=_string(mapping["motif_id"], "motif.motif_id"),
            label=_string(mapping["label"], "motif.label"),
            region_type=_string(mapping["region_type"], "motif.region_type"),
            occurrence_rule=_string(
                mapping["occurrence_rule"], "motif.occurrence_rule"
            ),
            allowed_counts=counts,
            insertion_rules=tuple(MotifInsertionRule.from_mapping(item) for item in rules),
            evidence=_parse_evidence_array(mapping["evidence"], "motif.evidence"),
        )


@dataclass(frozen=True)
class GrammarSlot:
    """One required ordered semantic slot in a family backbone."""

    slot_id: str
    region_type: str
    side: str

    def __post_init__(self) -> None:
        _non_empty(self.slot_id, "grammar_slot.slot_id")
        if self.region_type not in region_type_ids():
            raise SemanticContractError("grammar slot references an unknown region type")
        if self.side not in SIDES:
            raise SemanticContractError("grammar slot side is unsupported")

    @property
    def semantic_key(self) -> str:
        """Return the side/type key used for graph matching."""

        return f"{self.side}:{self.region_type}"

    def to_mapping(self) -> dict[str, str]:
        """Return the grammar-slot mapping."""

        return {
            "slot_id": self.slot_id,
            "region_type": self.region_type,
            "side": self.side,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GrammarSlot":
        """Parse one strict grammar-slot mapping."""

        mapping = _mapping(value, "grammar_slot")
        _exact_keys(
            mapping,
            {"slot_id", "region_type", "side"},
            set(),
            "grammar_slot",
        )
        return cls(
            slot_id=_string(mapping["slot_id"], "grammar_slot.slot_id"),
            region_type=_string(
                mapping["region_type"], "grammar_slot.region_type"
            ),
            side=_string(mapping["side"], "grammar_slot.side"),
        )


@dataclass(frozen=True)
class FamilyGrammar:
    """One versioned family semantic grammar accepting multiple topologies."""

    grammar_id: str
    family_id: str
    backbone_slots: tuple[GrammarSlot, ...]
    motifs: tuple[SemanticMotif, ...]
    type_cardinality: tuple[tuple[str, tuple[int, ...]], ...]
    allowed_adjacencies: tuple[tuple[str, str], ...]
    evidence: tuple[EvidenceRef, ...]
    review: ReviewBinding
    exclusions: tuple[str, ...]
    schema_version: str = FAMILY_GRAMMAR_SCHEMA_VERSION
    parameter_contract: str = PARAMETER_CONTRACT

    def __post_init__(self) -> None:
        if self.schema_version != FAMILY_GRAMMAR_SCHEMA_VERSION:
            raise SemanticContractError("family grammar schema_version must be family_grammar.v0")
        _non_empty(self.grammar_id, "grammar.grammar_id")
        _non_empty(self.family_id, "grammar.family_id")
        if len(self.backbone_slots) < 3:
            raise SemanticContractError("grammar backbone requires at least three slots")
        _unique_non_empty(
            tuple(slot.slot_id for slot in self.backbone_slots),
            "grammar.backbone slot IDs",
        )
        _unique_non_empty(
            tuple(slot.semantic_key for slot in self.backbone_slots),
            "grammar.backbone semantic keys",
        )
        backbone_sides = tuple(slot.side for slot in self.backbone_slots)
        center_indexes = [
            index for index, side in enumerate(backbone_sides) if side == "center"
        ]
        if len(center_indexes) != 1:
            raise SemanticContractError(
                "R1 grammar backbone requires exactly one center slot"
            )
        center_index = center_indexes[0]
        if any(side != "left" for side in backbone_sides[:center_index]) or any(
            side != "right" for side in backbone_sides[center_index + 1 :]
        ):
            raise SemanticContractError(
                "R1 grammar backbone sides must be ordered left, center, right"
            )
        if self.backbone_slots[center_index].region_type != EQUATOR_REGION:
            raise SemanticContractError(
                "R1 grammar center slot must be EquatorRegion"
            )
        if (
            self.backbone_slots[0].region_type != BEAM_PIPE_REGION
            or self.backbone_slots[-1].region_type != BEAM_PIPE_REGION
        ):
            raise SemanticContractError(
                "R1 grammar backbone endpoints must be BeamPipeRegion"
            )
        _unique_non_empty(
            tuple(motif.motif_id for motif in self.motifs), "grammar.motif IDs"
        )
        motif_types = tuple(motif.region_type for motif in self.motifs)
        if len(motif_types) != len(set(motif_types)):
            raise SemanticContractError(
                "R1 grammar cannot assign one region type to multiple motifs"
            )
        cardinality_keys: set[str] = set()
        for region_type, counts in self.type_cardinality:
            if region_type not in region_type_ids() or region_type in cardinality_keys:
                raise SemanticContractError(
                    f"invalid or duplicate grammar cardinality type: {region_type}"
                )
            cardinality_keys.add(region_type)
            if (
                not counts
                or tuple(sorted(set(counts))) != counts
                or any(
                    isinstance(item, bool) or not isinstance(item, int) or item < 0
                    for item in counts
                )
            ):
                raise SemanticContractError(
                    f"invalid allowed cardinalities for {region_type}"
                )
        required_types = {slot.region_type for slot in self.backbone_slots} | {
            motif.region_type for motif in self.motifs
        }
        if required_types != cardinality_keys:
            raise SemanticContractError(
                "grammar cardinality types must exactly match backbone and motif types"
            )
        backbone_counts: dict[str, int] = {}
        for slot in self.backbone_slots:
            backbone_counts[slot.region_type] = (
                backbone_counts.get(slot.region_type, 0) + 1
            )
        cardinalities = dict(self.type_cardinality)
        for region_type, count in backbone_counts.items():
            if cardinalities[region_type] != (count,):
                raise SemanticContractError(
                    f"backbone cardinality for {region_type} must be exactly {count}"
                )
        for motif in self.motifs:
            if cardinalities[motif.region_type] != motif.allowed_counts:
                raise SemanticContractError(
                    f"motif/cardinality contract disagrees for {motif.region_type}"
                )
        if len(set(self.allowed_adjacencies)) != len(self.allowed_adjacencies):
            raise SemanticContractError("grammar allowed_adjacencies contains duplicates")
        for pair in self.allowed_adjacencies:
            if len(pair) != 2 or any(item not in region_type_ids() for item in pair):
                raise SemanticContractError("grammar adjacency references unknown region type")
        backbone_adjacencies = {
            (left.region_type, right.region_type)
            for left, right in zip(self.backbone_slots, self.backbone_slots[1:])
        }
        expected_adjacencies = set(backbone_adjacencies)
        for motif in self.motifs:
            for rule in motif.insertion_rules:
                matching_slots = [
                    (left, right)
                    for left, right in zip(
                        self.backbone_slots, self.backbone_slots[1:]
                    )
                    if left.side == rule.side
                    and right.side == rule.side
                    and (left.region_type, right.region_type)
                    == rule.between_region_types
                ]
                if len(matching_slots) != 1:
                    raise SemanticContractError(
                        f"motif insertion rule on {rule.side} does not identify one backbone adjacency"
                    )
                expected_adjacencies.update(
                    {
                        (rule.between_region_types[0], motif.region_type),
                        (motif.region_type, rule.between_region_types[1]),
                    }
                )
        if set(self.allowed_adjacencies) != expected_adjacencies:
            raise SemanticContractError(
                "grammar allowed_adjacencies must exactly cover backbone and optional motif paths"
            )
        _evidence_tuple(self.evidence, "grammar.evidence")
        if not self.review.is_terminal:
            raise SemanticContractError("canonical family grammar requires terminal review state")
        if not self.exclusions:
            raise SemanticContractError("grammar.exclusions must be non-empty")
        _unique_non_empty(self.exclusions, "grammar.exclusions")
        if self.parameter_contract != PARAMETER_CONTRACT:
            raise SemanticContractError("family grammar cannot define a common geometry parameter vector")

    @property
    def cardinalities(self) -> dict[str, tuple[int, ...]]:
        """Return allowed region counts by ontology type."""

        return dict(self.type_cardinality)

    def to_mapping(self) -> dict[str, Any]:
        """Return the canonical family-grammar mapping."""

        return {
            "schema_version": self.schema_version,
            "grammar_id": self.grammar_id,
            "family_id": self.family_id,
            "canonicalization_contract": canonicalization_contract(),
            "region_ontology": region_ontology_mapping(),
            "landmark_ontology": landmark_ontology_mapping(),
            "backbone_slots": [item.to_mapping() for item in self.backbone_slots],
            "motifs": [item.to_mapping() for item in self.motifs],
            "type_cardinality": {
                region_type: list(counts)
                for region_type, counts in self.type_cardinality
            },
            "allowed_adjacencies": [list(pair) for pair in self.allowed_adjacencies],
            "evidence": [item.to_mapping() for item in self.evidence],
            "review": self.review.to_mapping(),
            "parameter_contract": self.parameter_contract,
            "exclusions": list(self.exclusions),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FamilyGrammar":
        """Parse and validate one strict family-grammar mapping."""

        mapping = _mapping(value, "family_grammar")
        _exact_keys(
            mapping,
            {
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
            },
            set(),
            "family_grammar",
        )
        _canonicalization(mapping["canonicalization_contract"])
        if mapping["region_ontology"] != region_ontology_mapping():
            raise SemanticContractError("family grammar region ontology is not canonical v0")
        if mapping["landmark_ontology"] != landmark_ontology_mapping():
            raise SemanticContractError("family grammar landmark ontology is not canonical v0")
        cardinality = _mapping(mapping["type_cardinality"], "type_cardinality")
        cardinality_items = tuple(
            (
                _string(region_type, "type_cardinality key"),
                _integer_tuple(counts, f"type_cardinality.{region_type}"),
            )
            for region_type, counts in sorted(cardinality.items())
        )
        adjacency_values = _sequence(
            mapping["allowed_adjacencies"], "allowed_adjacencies"
        )
        adjacencies: list[tuple[str, str]] = []
        for index, raw_pair in enumerate(adjacency_values):
            pair = _string_tuple(raw_pair, f"allowed_adjacencies[{index}]")
            if len(pair) != 2:
                raise SemanticContractError("each allowed adjacency requires two types")
            adjacencies.append((pair[0], pair[1]))
        return cls(
            schema_version=_string(mapping["schema_version"], "schema_version"),
            grammar_id=_string(mapping["grammar_id"], "grammar_id"),
            family_id=_string(mapping["family_id"], "family_id"),
            backbone_slots=tuple(
                GrammarSlot.from_mapping(item)
                for item in _mapping_array(mapping["backbone_slots"], "backbone_slots")
            ),
            motifs=tuple(
                SemanticMotif.from_mapping(item)
                for item in _mapping_array(mapping["motifs"], "motifs")
            ),
            type_cardinality=cardinality_items,
            allowed_adjacencies=tuple(adjacencies),
            evidence=_parse_evidence_array(mapping["evidence"], "evidence"),
            review=ReviewBinding.from_mapping(_mapping(mapping["review"], "review")),
            parameter_contract=_string(
                mapping["parameter_contract"], "parameter_contract"
            ),
            exclusions=_string_tuple(mapping["exclusions"], "exclusions"),
        )


@dataclass(frozen=True)
class InstanceBoundaryGraph:
    """Actual ordered semantic topology of one RF-vacuum boundary instance."""

    graph_id: str
    family_id: str
    instance_id: str
    regions: tuple[SemanticRegion, ...]
    landmarks: tuple[SemanticLandmark, ...]
    interfaces: tuple[BoundaryInterface, ...]
    active_motif_ids: tuple[str, ...]
    nose_presence: str
    nose_evidence: tuple[EvidenceRef, ...]
    source_bindings: tuple[EvidenceRef, ...]
    exclusions: tuple[str, ...]
    schema_version: str = INSTANCE_BOUNDARY_GRAPH_SCHEMA_VERSION
    boundary_scope: str = "axisymmetric_rf_vacuum_wall_profile"
    axis: str = "z"
    orientation: str = "negative_to_positive_z"
    region_ontology_version: str = REGION_ONTOLOGY_VERSION
    landmark_ontology_version: str = LANDMARK_ONTOLOGY_VERSION
    parameter_contract: str = PARAMETER_CONTRACT

    def __post_init__(self) -> None:
        if self.schema_version != INSTANCE_BOUNDARY_GRAPH_SCHEMA_VERSION:
            raise SemanticContractError(
                "instance graph schema_version must be instance_boundary_graph.v0"
            )
        for value, path in (
            (self.graph_id, "graph.graph_id"),
            (self.family_id, "graph.family_id"),
            (self.instance_id, "graph.instance_id"),
        ):
            _non_empty(value, path)
        if self.graph_id != f"{self.instance_id}.boundary_graph.v0":
            raise SemanticContractError("graph_id must be stable and derived from instance_id")
        if self.boundary_scope != "axisymmetric_rf_vacuum_wall_profile":
            raise SemanticContractError("unsupported graph boundary_scope")
        if self.axis != "z" or self.orientation != "negative_to_positive_z":
            raise SemanticContractError("R1 graph must use oriented z-axis wall order")
        if self.region_ontology_version != REGION_ONTOLOGY_VERSION:
            raise SemanticContractError("instance graph region ontology version mismatch")
        if self.landmark_ontology_version != LANDMARK_ONTOLOGY_VERSION:
            raise SemanticContractError("instance graph landmark ontology version mismatch")
        if self.parameter_contract != PARAMETER_CONTRACT:
            raise SemanticContractError("instance graph cannot contain a geometry parameter vector")
        if len(self.regions) < 3:
            raise SemanticContractError("instance graph requires at least three regions")
        region_ids = tuple(item.region_id for item in self.regions)
        _unique_non_empty(region_ids, "graph region IDs")
        expected_prefix = f"{self.instance_id}.region."
        if any(not region_id.startswith(expected_prefix) for region_id in region_ids):
            raise SemanticContractError("every region ID must be namespaced by instance_id")
        semantic_keys = tuple(item.semantic_key for item in self.regions)
        _unique_non_empty(semantic_keys, "graph semantic side/type keys")
        if any(not item.review.is_terminal for item in self.regions):
            raise SemanticContractError("every canonical region requires terminal review state")
        sides = tuple(item.side for item in self.regions)
        first_center = next((i for i, side in enumerate(sides) if side == "center"), -1)
        if first_center < 0 or sides.count("center") != 1:
            raise SemanticContractError("instance graph requires exactly one center region")
        if any(side != "left" for side in sides[:first_center]) or any(
            side != "right" for side in sides[first_center + 1 :]
        ):
            raise SemanticContractError("region sides must be ordered left, center, right")
        center = self.regions[first_center]
        if center.region_type != EQUATOR_REGION:
            raise SemanticContractError("the center region must be EquatorRegion")
        if self.regions[0].region_type != BEAM_PIPE_REGION or self.regions[-1].region_type != BEAM_PIPE_REGION:
            raise SemanticContractError("graph endpoints must be BeamPipeRegion")
        _unique_non_empty(self.active_motif_ids, "graph.active_motif_ids")
        nose_regions = [item for item in self.regions if item.region_type == NOSE_REGION]
        if nose_regions:
            if self.nose_presence != "present":
                raise SemanticContractError("NoseRegion nodes require nose_presence=present")
            if any(item.motif_id != NOSE_PAIR_MOTIF_ID for item in nose_regions):
                raise SemanticContractError("every NoseRegion must belong to the nose-pair motif")
            if NOSE_PAIR_MOTIF_ID not in self.active_motif_ids:
                raise SemanticContractError("nose-pair motif must be active when NoseRegion exists")
        else:
            if self.nose_presence != "absent_reviewed_topology":
                raise SemanticContractError(
                    "nose-free graph requires an explicit reviewed-topology absence assertion"
                )
            if NOSE_PAIR_MOTIF_ID in self.active_motif_ids:
                raise SemanticContractError("nose-pair motif cannot be active without NoseRegion")
        _evidence_tuple(self.nose_evidence, "graph.nose_evidence")
        _evidence_tuple(self.source_bindings, "graph.source_bindings")
        if not self.exclusions:
            raise SemanticContractError("graph.exclusions must be non-empty")
        _unique_non_empty(self.exclusions, "graph.exclusions")
        self._validate_landmarks_and_interfaces(region_ids)

    def _validate_landmarks_and_interfaces(self, region_ids: tuple[str, ...]) -> None:
        landmark_ids = tuple(item.landmark_id for item in self.landmarks)
        _unique_non_empty(landmark_ids, "graph landmark IDs")
        if any(
            not item.landmark_id.startswith(f"{self.instance_id}.landmark.")
            for item in self.landmarks
        ):
            raise SemanticContractError("every landmark ID must be namespaced by instance_id")
        region_id_set = set(region_ids)
        if any(
            incident not in region_id_set
            for item in self.landmarks
            for incident in item.incident_region_ids
        ):
            raise SemanticContractError("landmark references an unknown region")
        if any(not item.review.is_terminal for item in self.landmarks):
            raise SemanticContractError("every canonical landmark requires terminal review state")
        interfaces = self.interfaces
        if len(interfaces) != len(self.regions) - 1:
            raise SemanticContractError("linear graph requires exactly n-1 interfaces")
        interface_ids = tuple(item.interface_id for item in interfaces)
        _unique_non_empty(interface_ids, "graph interface IDs")
        if any(
            not item.interface_id.startswith(f"{self.instance_id}.interface.")
            for item in interfaces
        ):
            raise SemanticContractError("every interface ID must be namespaced by instance_id")
        landmarks_by_id = {item.landmark_id: item for item in self.landmarks}
        interface_landmark_ids = tuple(item.landmark_id for item in interfaces)
        if len(interface_landmark_ids) != len(set(interface_landmark_ids)):
            raise SemanticContractError("each interface requires its own junction landmark")
        junction_landmark_ids = {
            item.landmark_id
            for item in self.landmarks
            if item.landmark_type == REGION_JUNCTION_LANDMARK
        }
        if junction_landmark_ids != set(interface_landmark_ids):
            raise SemanticContractError(
                "junction landmarks and interface landmark bindings must be one-to-one"
            )
        for index, interface in enumerate(interfaces):
            expected = (region_ids[index], region_ids[index + 1])
            actual = (interface.left_region_id, interface.right_region_id)
            if actual != expected:
                raise SemanticContractError(
                    f"interface {interface.interface_id} breaks ordered adjacency at index {index}"
                )
            landmark = landmarks_by_id.get(interface.landmark_id)
            if landmark is None or landmark.landmark_type != REGION_JUNCTION_LANDMARK:
                raise SemanticContractError("interface requires a RegionJunctionLandmark")
            if landmark.incident_region_ids != expected:
                raise SemanticContractError(
                    "interface landmark incident regions must match the ordered join"
                )
        apertures = [
            item
            for item in self.landmarks
            if item.landmark_type == AXIAL_APERTURE_LANDMARK
        ]
        if len(apertures) != 2 or {
            item.incident_region_ids[0] for item in apertures
        } != {region_ids[0], region_ids[-1]}:
            raise SemanticContractError("graph requires aperture landmarks at both endpoints")
        if {item.side for item in apertures} != {"left", "right"}:
            raise SemanticContractError("aperture landmarks require left and right sides")
        symmetry = [
            item for item in self.landmarks if item.landmark_type == SYMMETRY_LANDMARK
        ]
        center_region_id = next(item.region_id for item in self.regions if item.side == "center")
        if len(symmetry) != 1 or symmetry[0].incident_region_ids != (center_region_id,):
            raise SemanticContractError(
                "graph requires one symmetry landmark bound to the center region"
            )
        if symmetry[0].side != "center":
            raise SemanticContractError("symmetry landmark side must be center")

    @property
    def ordered_region_types(self) -> tuple[str, ...]:
        """Return the topology as an ordered region-type sequence."""

        return tuple(item.region_type for item in self.regions)

    def to_mapping(self) -> dict[str, Any]:
        """Return the canonical instance-boundary-graph mapping."""

        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "canonicalization_contract": canonicalization_contract(),
            "boundary_scope": self.boundary_scope,
            "axis": self.axis,
            "orientation": self.orientation,
            "region_ontology_version": self.region_ontology_version,
            "landmark_ontology_version": self.landmark_ontology_version,
            "regions": [item.to_mapping() for item in self.regions],
            "landmarks": [item.to_mapping() for item in self.landmarks],
            "interfaces": [item.to_mapping() for item in self.interfaces],
            "active_motif_ids": list(self.active_motif_ids),
            "nose_presence": self.nose_presence,
            "nose_evidence": [item.to_mapping() for item in self.nose_evidence],
            "source_bindings": [item.to_mapping() for item in self.source_bindings],
            "parameter_contract": self.parameter_contract,
            "exclusions": list(self.exclusions),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InstanceBoundaryGraph":
        """Parse and validate one strict instance graph mapping."""

        mapping = _mapping(value, "instance_boundary_graph")
        required = {
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
        }
        _exact_keys(mapping, required, set(), "instance_boundary_graph")
        _canonicalization(mapping["canonicalization_contract"])
        return cls(
            schema_version=_string(mapping["schema_version"], "schema_version"),
            graph_id=_string(mapping["graph_id"], "graph_id"),
            family_id=_string(mapping["family_id"], "family_id"),
            instance_id=_string(mapping["instance_id"], "instance_id"),
            boundary_scope=_string(mapping["boundary_scope"], "boundary_scope"),
            axis=_string(mapping["axis"], "axis"),
            orientation=_string(mapping["orientation"], "orientation"),
            region_ontology_version=_string(
                mapping["region_ontology_version"], "region_ontology_version"
            ),
            landmark_ontology_version=_string(
                mapping["landmark_ontology_version"], "landmark_ontology_version"
            ),
            regions=tuple(
                SemanticRegion.from_mapping(item)
                for item in _mapping_array(mapping["regions"], "regions")
            ),
            landmarks=tuple(
                SemanticLandmark.from_mapping(item)
                for item in _mapping_array(mapping["landmarks"], "landmarks")
            ),
            interfaces=tuple(
                BoundaryInterface.from_mapping(item)
                for item in _mapping_array(mapping["interfaces"], "interfaces")
            ),
            active_motif_ids=_string_tuple(
                mapping["active_motif_ids"], "active_motif_ids"
            ),
            nose_presence=_string(mapping["nose_presence"], "nose_presence"),
            nose_evidence=_parse_evidence_array(
                mapping["nose_evidence"], "nose_evidence"
            ),
            source_bindings=_parse_evidence_array(
                mapping["source_bindings"], "source_bindings"
            ),
            parameter_contract=_string(
                mapping["parameter_contract"], "parameter_contract"
            ),
            exclusions=_string_tuple(mapping["exclusions"], "exclusions"),
        )


def validate_graph_against_grammar(
    grammar: FamilyGrammar, graph: InstanceBoundaryGraph
) -> None:
    """Fail closed unless one graph is a legal instance of the family grammar."""

    if graph.family_id != grammar.family_id:
        raise SemanticContractError("graph family_id does not match grammar")
    motifs = {item.motif_id: item for item in grammar.motifs}
    unknown_active = set(graph.active_motif_ids) - set(motifs)
    if unknown_active:
        raise SemanticContractError(f"graph activates unknown motifs: {sorted(unknown_active)}")
    motif_region_ids = {item.region_type: item.motif_id for item in grammar.motifs}
    backbone_regions = [
        region
        for region in graph.regions
        if region.region_type not in motif_region_ids
    ]
    actual_backbone = tuple(region.semantic_key for region in backbone_regions)
    expected_backbone = tuple(slot.semantic_key for slot in grammar.backbone_slots)
    if actual_backbone != expected_backbone:
        raise SemanticContractError(
            "graph backbone differs from grammar; semantic topology cannot be repaired by missing parameters"
        )
    counts: dict[str, int] = {}
    for region in graph.regions:
        counts[region.region_type] = counts.get(region.region_type, 0) + 1
    for region_type, allowed in grammar.cardinalities.items():
        if counts.get(region_type, 0) not in allowed:
            raise SemanticContractError(
                f"graph cardinality for {region_type} is {counts.get(region_type, 0)}, allowed {allowed}"
            )
    for region_type in counts:
        if region_type not in grammar.cardinalities:
            raise SemanticContractError(
                f"graph contains a region type without a grammar cardinality: {region_type}"
            )
    allowed_edges = set(grammar.allowed_adjacencies)
    for left, right in zip(graph.regions, graph.regions[1:]):
        pair = (left.region_type, right.region_type)
        if pair not in allowed_edges:
            raise SemanticContractError(f"illegal semantic adjacency: {pair}")
    for motif in grammar.motifs:
        occurrences = [
            (index, region)
            for index, region in enumerate(graph.regions)
            if region.region_type == motif.region_type
        ]
        if len(occurrences) not in motif.allowed_counts:
            raise SemanticContractError(
                f"motif {motif.motif_id} occurrence count is invalid"
            )
        if occurrences and motif.motif_id not in graph.active_motif_ids:
            raise SemanticContractError(
                f"motif {motif.motif_id} has regions but is not active"
            )
        if not occurrences and motif.motif_id in graph.active_motif_ids:
            raise SemanticContractError(
                f"motif {motif.motif_id} is active without regions"
            )
        rules = {rule.side: rule for rule in motif.insertion_rules}
        seen_sides: set[str] = set()
        for index, region in occurrences:
            if index == 0 or index == len(graph.regions) - 1:
                raise SemanticContractError("motif region cannot be a graph endpoint")
            rule = rules.get(region.side)
            if rule is None:
                raise SemanticContractError("motif occurrence has no side-specific insertion rule")
            neighbors = (
                graph.regions[index - 1].region_type,
                graph.regions[index + 1].region_type,
            )
            if neighbors != rule.between_region_types:
                raise SemanticContractError(
                    f"motif {motif.motif_id} is inserted at the wrong adjacency on {region.side}"
                )
            if region.side in seen_sides:
                raise SemanticContractError("paired motif repeats one side")
            seen_sides.add(region.side)
        if occurrences and seen_sides != {"left", "right"}:
            raise SemanticContractError("paired motif must occur once on each side")


@dataclass(frozen=True)
class InstanceGraphDiff:
    """Deterministic semantic/topology comparison of two instance graphs."""

    left_graph_id: str
    right_graph_id: str
    left_graph_sha256: str
    right_graph_sha256: str
    common_regions: tuple[Mapping[str, Any], ...]
    left_only_regions: tuple[Mapping[str, Any], ...]
    right_only_regions: tuple[Mapping[str, Any], ...]
    adjacency_changes: tuple[Mapping[str, Any], ...]
    motif_changes: tuple[Mapping[str, Any], ...]
    schema_version: str = GRAPH_DIFF_SCHEMA_VERSION
    classification: str = "semantic_topology_difference"
    parameter_comparison: str = DIFF_PARAMETER_CONTRACT

    def __post_init__(self) -> None:
        if self.schema_version != GRAPH_DIFF_SCHEMA_VERSION:
            raise SemanticContractError("graph diff schema_version is unsupported")
        _non_empty(self.left_graph_id, "diff.left_graph_id")
        _non_empty(self.right_graph_id, "diff.right_graph_id")
        if self.left_graph_id == self.right_graph_id:
            raise SemanticContractError("graph diff requires two distinct graphs")
        _normalized_hash(self.left_graph_sha256, "diff.left_graph_sha256")
        _normalized_hash(self.right_graph_sha256, "diff.right_graph_sha256")
        if self.classification != "semantic_topology_difference":
            raise SemanticContractError("R1 graph diff classification must be semantic_topology_difference")
        if self.parameter_comparison != DIFF_PARAMETER_CONTRACT:
            raise SemanticContractError("graph diff cannot compare a common geometry parameter vector")
        for path, values in (
            ("common_regions", self.common_regions),
            ("left_only_regions", self.left_only_regions),
            ("right_only_regions", self.right_only_regions),
            ("adjacency_changes", self.adjacency_changes),
            ("motif_changes", self.motif_changes),
        ):
            canonical_json_bytes(list(values))
            if any(not isinstance(item, Mapping) for item in values):
                raise SemanticContractError(f"diff.{path} must contain objects")

    def to_mapping(self) -> dict[str, Any]:
        """Return the canonical graph-diff mapping."""

        return {
            "schema_version": self.schema_version,
            "canonicalization_contract": canonicalization_contract(),
            "left_graph_id": self.left_graph_id,
            "right_graph_id": self.right_graph_id,
            "left_graph_sha256": self.left_graph_sha256,
            "right_graph_sha256": self.right_graph_sha256,
            "classification": self.classification,
            "common_regions": [dict(item) for item in self.common_regions],
            "left_only_regions": [dict(item) for item in self.left_only_regions],
            "right_only_regions": [dict(item) for item in self.right_only_regions],
            "adjacency_changes": [dict(item) for item in self.adjacency_changes],
            "motif_changes": [dict(item) for item in self.motif_changes],
            "parameter_comparison": self.parameter_comparison,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InstanceGraphDiff":
        """Parse and validate one strict graph-diff mapping."""

        mapping = _mapping(value, "graph_diff")
        required = {
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
        }
        _exact_keys(mapping, required, set(), "graph_diff")
        _canonicalization(mapping["canonicalization_contract"])
        return cls(
            schema_version=_string(mapping["schema_version"], "schema_version"),
            left_graph_id=_string(mapping["left_graph_id"], "left_graph_id"),
            right_graph_id=_string(mapping["right_graph_id"], "right_graph_id"),
            left_graph_sha256=_normalized_hash(
                mapping["left_graph_sha256"], "left_graph_sha256"
            ),
            right_graph_sha256=_normalized_hash(
                mapping["right_graph_sha256"], "right_graph_sha256"
            ),
            classification=_string(mapping["classification"], "classification"),
            common_regions=tuple(
                _mapping_array(mapping["common_regions"], "common_regions")
            ),
            left_only_regions=tuple(
                _mapping_array(mapping["left_only_regions"], "left_only_regions")
            ),
            right_only_regions=tuple(
                _mapping_array(mapping["right_only_regions"], "right_only_regions")
            ),
            adjacency_changes=tuple(
                _mapping_array(mapping["adjacency_changes"], "adjacency_changes")
            ),
            motif_changes=tuple(
                _mapping_array(mapping["motif_changes"], "motif_changes")
            ),
            parameter_comparison=_string(
                mapping["parameter_comparison"], "parameter_comparison"
            ),
        )


def diff_instance_graphs(
    left: InstanceBoundaryGraph, right: InstanceBoundaryGraph
) -> InstanceGraphDiff:
    """Compare graphs by semantic identity and topology, never by parameter name."""

    if left.family_id != right.family_id:
        raise SemanticContractError("cannot diff instance graphs from different families")
    left_by_key = {item.semantic_key: item for item in left.regions}
    right_by_key = {item.semantic_key: item for item in right.regions}
    common_keys = sorted(set(left_by_key) & set(right_by_key))
    left_only_keys = sorted(set(left_by_key) - set(right_by_key))
    right_only_keys = sorted(set(right_by_key) - set(left_by_key))
    common = tuple(
        {
            "semantic_key": key,
            "region_type": left_by_key[key].region_type,
            "side": left_by_key[key].side,
            "left_region_id": left_by_key[key].region_id,
            "right_region_id": right_by_key[key].region_id,
        }
        for key in common_keys
    )

    def _summary(region: SemanticRegion) -> dict[str, str | None]:
        return {
            "semantic_key": region.semantic_key,
            "region_id": region.region_id,
            "region_type": region.region_type,
            "side": region.side,
            "motif_id": region.motif_id,
        }

    left_only = tuple(_summary(left_by_key[key]) for key in left_only_keys)
    right_only = tuple(_summary(right_by_key[key]) for key in right_only_keys)

    def _edges(graph: InstanceBoundaryGraph) -> set[tuple[str, str]]:
        return {
            (first.semantic_key, second.semantic_key)
            for first, second in zip(graph.regions, graph.regions[1:])
        }

    left_edges = _edges(left)
    right_edges = _edges(right)
    adjacency = tuple(
        {
            "edge": list(edge),
            "left_present": edge in left_edges,
            "right_present": edge in right_edges,
        }
        for edge in sorted(left_edges ^ right_edges)
    )
    motif_ids = sorted(set(left.active_motif_ids) | set(right.active_motif_ids))
    motif_changes = tuple(
        {
            "motif_id": motif_id,
            "left_present": motif_id in left.active_motif_ids,
            "right_present": motif_id in right.active_motif_ids,
            "change": (
                "unchanged"
                if (motif_id in left.active_motif_ids)
                == (motif_id in right.active_motif_ids)
                else "optional_topology_presence_changed"
            ),
        }
        for motif_id in motif_ids
    )
    if not left_only and not right_only and not adjacency and not any(
        item["change"] != "unchanged" for item in motif_changes
    ):
        raise SemanticContractError("graphs have no semantic/topology difference")
    return InstanceGraphDiff(
        left_graph_id=left.graph_id,
        right_graph_id=right.graph_id,
        left_graph_sha256=canonical_sha256(left.to_mapping()),
        right_graph_sha256=canonical_sha256(right.to_mapping()),
        common_regions=common,
        left_only_regions=left_only,
        right_only_regions=right_only,
        adjacency_changes=adjacency,
        motif_changes=motif_changes,
    )


def load_family_grammar(path: Path) -> FamilyGrammar:
    """Load a UTF-8 JSON family grammar and validate it."""

    return FamilyGrammar.from_mapping(_read_json_mapping(path))


def load_instance_boundary_graph(path: Path) -> InstanceBoundaryGraph:
    """Load a UTF-8 JSON instance boundary graph and validate it."""

    return InstanceBoundaryGraph.from_mapping(_read_json_mapping(path))


def load_instance_graph_diff(path: Path) -> InstanceGraphDiff:
    """Load a UTF-8 JSON instance graph diff and validate it."""

    return InstanceGraphDiff.from_mapping(_read_json_mapping(path))


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticContractError(f"cannot read semantic JSON source: {path}") from exc
    if not isinstance(value, dict):
        raise SemanticContractError(f"semantic JSON source must contain an object: {path}")
    return value


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticContractError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise SemanticContractError(f"{path} contains a non-string key")
    return value


def _sequence(value: object, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SemanticContractError(f"{path} must be an array")
    return value


def _mapping_array(value: object, path: str) -> list[Mapping[str, Any]]:
    items = _sequence(value, path)
    return [_mapping(item, f"{path}[{index}]") for index, item in enumerate(items)]


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticContractError(f"{path} must be a non-empty string")
    return value


def _non_empty(value: object, path: str) -> str:
    return _string(value, path)


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(value, path))
    )


def _integer_tuple(value: object, path: str) -> tuple[int, ...]:
    result: list[int] = []
    for index, item in enumerate(_sequence(value, path)):
        if isinstance(item, bool) or not isinstance(item, int):
            raise SemanticContractError(f"{path}[{index}] must be an integer")
        result.append(item)
    return tuple(result)


def _unique_non_empty(values: Iterable[str], path: str) -> None:
    items = tuple(values)
    for index, item in enumerate(items):
        _non_empty(item, f"{path}[{index}]")
    if len(items) != len(set(items)):
        raise SemanticContractError(f"{path} must be unique")


def _normalized_hash(value: object, path: str) -> str:
    text = _string(value, path)
    if not _HASH_RE.fullmatch(text):
        raise SemanticContractError(
            f"{path} must be a lowercase hexadecimal SHA-256 digest"
        )
    return text


def _relative_path(value: object, path: str) -> str:
    text = _string(value, path)
    normalized = text.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        text != normalized
        or candidate.is_absolute()
        or ".." in candidate.parts
        or _WINDOWS_ABSOLUTE_RE.match(text)
    ):
        raise SemanticContractError(f"{path} must be a canonical repository-relative path")
    return candidate.as_posix()


def _evidence_tuple(values: tuple[EvidenceRef, ...], path: str) -> None:
    if not values or any(not isinstance(item, EvidenceRef) for item in values):
        raise SemanticContractError(f"{path} must contain at least one EvidenceRef")
    canonical = tuple(canonical_sha256(item.to_mapping()) for item in values)
    if len(canonical) != len(set(canonical)):
        raise SemanticContractError(f"{path} contains duplicate evidence")


def _parse_evidence_array(value: object, path: str) -> tuple[EvidenceRef, ...]:
    return tuple(
        EvidenceRef.from_mapping(item) for item in _mapping_array(value, path)
    )


def _exact_keys(
    mapping: Mapping[str, Any],
    required: set[str],
    optional: set[str],
    path: str,
) -> None:
    missing = sorted(required - set(mapping))
    extra = sorted(set(mapping) - required - optional)
    if missing:
        raise SemanticContractError(f"{path} is missing required fields: {missing}")
    if extra:
        raise SemanticContractError(f"{path} contains unsupported fields: {extra}")


def _canonicalization(value: object) -> None:
    mapping = _mapping(value, "canonicalization_contract")
    if dict(mapping) != canonicalization_contract():
        raise SemanticContractError("semantic canonicalization_contract is not canonical v0")


__all__ = [
    "BoundaryInterface",
    "DIFF_PARAMETER_CONTRACT",
    "EvidenceRef",
    "FamilyGrammar",
    "GrammarSlot",
    "InstanceBoundaryGraph",
    "InstanceGraphDiff",
    "MotifInsertionRule",
    "NOSE_PAIR_MOTIF_ID",
    "PARAMETER_CONTRACT",
    "ReviewBinding",
    "SemanticContractError",
    "SemanticLandmark",
    "SemanticMotif",
    "SemanticRegion",
    "TERMINAL_REVIEW_STATES",
    "canonical_json_bytes",
    "canonical_sha256",
    "canonicalization_contract",
    "diff_instance_graphs",
    "file_sha256",
    "load_family_grammar",
    "load_instance_boundary_graph",
    "load_instance_graph_diff",
    "validate_graph_against_grammar",
]
