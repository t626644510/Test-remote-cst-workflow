"""Strict portable contracts for RF-CEM family induction and review."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence, Union

from ..contracts import (
    EvidenceRef,
    SemanticMotif,
    canonical_json_bytes,
    canonical_sha256,
)


ALIGNMENT_SCHEMA_VERSION = "graph_alignment.v0"
PROPOSAL_SCHEMA_VERSION = "family_extension_proposal.v0"
PROPOSAL_SCHEMA_VERSION_V1 = "family_extension_proposal.v1"
PROPOSAL_REVIEW_SCHEMA_VERSION = "family_extension_review.v0"
GRAMMAR_PATCH_SCHEMA_VERSION = "family_grammar_patch.v0"
PATCH_APPLICATION_SCHEMA_VERSION = "family_grammar_patch_application.v0"
BLIND_VALIDATION_SCHEMA_VERSION = "family_induction_blind_validation.v0"
INDUCTION_ALGORITHM_VERSION = "rf_cem_family_induction.v0"
INDUCTION_ALGORITHM_VERSION_V1 = "rf_cem_family_induction.v1"
INDUCTION_INPUT_CONTRACT = "reviewed_instance_boundary_graphs_only"
CONFIDENCE_CONTRACT = "deterministic_evidence_completeness_not_probability"
SCORE_SEMANTICS = "heuristic_support_not_probability"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


class InductionContractError(ValueError):
    """Raised when an R3 contract fails closed."""


@dataclass(frozen=True)
class GraphContractRef:
    """Hash-bound source reference for one reviewed instance graph."""

    instance_id: str
    graph_id: str
    source_path: str
    source_raw_sha256: str
    contract_sha256: str

    def __post_init__(self) -> None:
        _non_empty(self.instance_id, "graph_ref.instance_id")
        _non_empty(self.graph_id, "graph_ref.graph_id")
        _relative_path(self.source_path, "graph_ref.source_path")
        _hash(self.source_raw_sha256, "graph_ref.source_raw_sha256")
        _hash(self.contract_sha256, "graph_ref.contract_sha256")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "graph_id": self.graph_id,
            "source_path": self.source_path,
            "source_raw_sha256": self.source_raw_sha256,
            "contract_sha256": self.contract_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GraphContractRef":
        mapping = _mapping(value, "graph_ref")
        _exact_keys(
            mapping,
            {
                "instance_id",
                "graph_id",
                "source_path",
                "source_raw_sha256",
                "contract_sha256",
            },
            "graph_ref",
        )
        return cls(
            instance_id=_string(mapping["instance_id"], "graph_ref.instance_id"),
            graph_id=_string(mapping["graph_id"], "graph_ref.graph_id"),
            source_path=_relative_path(mapping["source_path"], "graph_ref.source_path"),
            source_raw_sha256=_hash(
                mapping["source_raw_sha256"], "graph_ref.source_raw_sha256"
            ),
            contract_sha256=_hash(
                mapping["contract_sha256"], "graph_ref.contract_sha256"
            ),
        )


@dataclass(frozen=True)
class RegionMatch:
    """One graph-specific region occupying a common aligned slot."""

    instance_id: str
    region_id: str
    region_index: int

    def __post_init__(self) -> None:
        _non_empty(self.instance_id, "region_match.instance_id")
        _non_empty(self.region_id, "region_match.region_id")
        _non_negative_integer(self.region_index, "region_match.region_index")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "region_id": self.region_id,
            "region_index": self.region_index,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RegionMatch":
        mapping = _mapping(value, "region_match")
        _exact_keys(mapping, {"instance_id", "region_id", "region_index"}, "region_match")
        return cls(
            instance_id=_string(mapping["instance_id"], "region_match.instance_id"),
            region_id=_string(mapping["region_id"], "region_match.region_id"),
            region_index=_integer(mapping["region_index"], "region_match.region_index"),
        )


@dataclass(frozen=True)
class CommonBackboneSlot:
    """One semantic side/type token shared by every induction graph."""

    slot_index: int
    semantic_key: str
    side: str
    region_type: str
    matches: tuple[RegionMatch, ...]

    def __post_init__(self) -> None:
        _non_negative_integer(self.slot_index, "backbone_slot.slot_index")
        _non_empty(self.semantic_key, "backbone_slot.semantic_key")
        if self.semantic_key != f"{self.side}:{self.region_type}":
            raise InductionContractError("backbone semantic key must be side:type")
        if self.side not in {"left", "center", "right"}:
            raise InductionContractError("backbone slot side is unsupported")
        _non_empty(self.region_type, "backbone_slot.region_type")
        if len(self.matches) < 2:
            raise InductionContractError("common backbone slot requires at least two matches")
        instance_ids = [item.instance_id for item in self.matches]
        if len(instance_ids) != len(set(instance_ids)):
            raise InductionContractError("backbone slot has duplicate instance matches")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "semantic_key": self.semantic_key,
            "side": self.side,
            "region_type": self.region_type,
            "matches": [item.to_mapping() for item in self.matches],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CommonBackboneSlot":
        mapping = _mapping(value, "backbone_slot")
        _exact_keys(
            mapping,
            {"slot_index", "semantic_key", "side", "region_type", "matches"},
            "backbone_slot",
        )
        return cls(
            slot_index=_integer(mapping["slot_index"], "backbone_slot.slot_index"),
            semantic_key=_string(mapping["semantic_key"], "backbone_slot.semantic_key"),
            side=_string(mapping["side"], "backbone_slot.side"),
            region_type=_string(mapping["region_type"], "backbone_slot.region_type"),
            matches=tuple(
                RegionMatch.from_mapping(item)
                for item in _mapping_array(mapping["matches"], "backbone_slot.matches")
            ),
        )


@dataclass(frozen=True)
class AlignmentResidual:
    """One graph region not present in the common backbone."""

    instance_id: str
    graph_id: str
    region_id: str
    region_index: int
    semantic_key: str
    side: str
    region_type: str
    left_anchor_key: str | None
    right_anchor_key: str | None
    graph_locator: str

    def __post_init__(self) -> None:
        for value, path in (
            (self.instance_id, "residual.instance_id"),
            (self.graph_id, "residual.graph_id"),
            (self.region_id, "residual.region_id"),
            (self.semantic_key, "residual.semantic_key"),
            (self.region_type, "residual.region_type"),
            (self.graph_locator, "residual.graph_locator"),
        ):
            _non_empty(value, path)
        _non_negative_integer(self.region_index, "residual.region_index")
        if self.side not in {"left", "center", "right"}:
            raise InductionContractError("residual side is unsupported")
        if self.semantic_key != f"{self.side}:{self.region_type}":
            raise InductionContractError("residual semantic key must be side:type")
        for anchor, path in (
            (self.left_anchor_key, "residual.left_anchor_key"),
            (self.right_anchor_key, "residual.right_anchor_key"),
        ):
            if anchor is not None:
                _non_empty(anchor, path)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "graph_id": self.graph_id,
            "region_id": self.region_id,
            "region_index": self.region_index,
            "semantic_key": self.semantic_key,
            "side": self.side,
            "region_type": self.region_type,
            "left_anchor_key": self.left_anchor_key,
            "right_anchor_key": self.right_anchor_key,
            "graph_locator": self.graph_locator,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AlignmentResidual":
        mapping = _mapping(value, "residual")
        required = {
            "instance_id",
            "graph_id",
            "region_id",
            "region_index",
            "semantic_key",
            "side",
            "region_type",
            "left_anchor_key",
            "right_anchor_key",
            "graph_locator",
        }
        _exact_keys(mapping, required, "residual")
        return cls(
            instance_id=_string(mapping["instance_id"], "residual.instance_id"),
            graph_id=_string(mapping["graph_id"], "residual.graph_id"),
            region_id=_string(mapping["region_id"], "residual.region_id"),
            region_index=_integer(mapping["region_index"], "residual.region_index"),
            semantic_key=_string(mapping["semantic_key"], "residual.semantic_key"),
            side=_string(mapping["side"], "residual.side"),
            region_type=_string(mapping["region_type"], "residual.region_type"),
            left_anchor_key=_optional_string(
                mapping["left_anchor_key"], "residual.left_anchor_key"
            ),
            right_anchor_key=_optional_string(
                mapping["right_anchor_key"], "residual.right_anchor_key"
            ),
            graph_locator=_string(mapping["graph_locator"], "residual.graph_locator"),
        )


@dataclass(frozen=True)
class GraphAlignment:
    """Deterministic alignment of reviewed semantic graphs only."""

    family_id: str
    graph_refs: tuple[GraphContractRef, ...]
    common_backbone: tuple[CommonBackboneSlot, ...]
    residuals: tuple[AlignmentResidual, ...]
    algorithm_version: str = INDUCTION_ALGORITHM_VERSION
    input_contract: str = INDUCTION_INPUT_CONTRACT
    parameter_names_read: bool = False
    alignment_id: str = ""
    content_sha256: str = ""
    schema_version: str = ALIGNMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ALIGNMENT_SCHEMA_VERSION:
            raise InductionContractError("unsupported graph alignment schema")
        if self.algorithm_version != INDUCTION_ALGORITHM_VERSION:
            raise InductionContractError("unsupported induction algorithm version")
        if self.input_contract != INDUCTION_INPUT_CONTRACT:
            raise InductionContractError("alignment input contract is unsupported")
        if self.parameter_names_read is not False:
            raise InductionContractError("R3 alignment must not read parameter names")
        _non_empty(self.family_id, "alignment.family_id")
        if len(self.graph_refs) < 2:
            raise InductionContractError("alignment requires at least two reviewed graphs")
        instance_ids = [item.instance_id for item in self.graph_refs]
        if len(instance_ids) != len(set(instance_ids)):
            raise InductionContractError("alignment graph instance IDs must be unique")
        if not self.common_backbone:
            raise InductionContractError("alignment requires a non-empty common backbone")
        if [item.slot_index for item in self.common_backbone] != list(
            range(len(self.common_backbone))
        ):
            raise InductionContractError("common backbone slot order must be contiguous")
        expected_instances = set(instance_ids)
        for slot in self.common_backbone:
            if {item.instance_id for item in slot.matches} != expected_instances:
                raise InductionContractError("every backbone slot must match every input graph")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.family_id}.alignment.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "alignment_id", self.alignment_id, expected_id)

    @property
    def source_instance_ids(self) -> tuple[str, ...]:
        return tuple(item.instance_id for item in self.graph_refs)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "algorithm_version": self.algorithm_version,
            "input_contract": self.input_contract,
            "parameter_names_read": self.parameter_names_read,
            "graph_refs": [item.to_mapping() for item in self.graph_refs],
            "common_backbone": [item.to_mapping() for item in self.common_backbone],
            "residuals": [item.to_mapping() for item in self.residuals],
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "alignment_id": self.alignment_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GraphAlignment":
        mapping = _mapping(value, "alignment")
        required = {
            "schema_version",
            "family_id",
            "algorithm_version",
            "input_contract",
            "parameter_names_read",
            "graph_refs",
            "common_backbone",
            "residuals",
            "alignment_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "alignment")
        return cls(
            schema_version=_string(mapping["schema_version"], "alignment.schema_version"),
            family_id=_string(mapping["family_id"], "alignment.family_id"),
            algorithm_version=_string(
                mapping["algorithm_version"], "alignment.algorithm_version"
            ),
            input_contract=_string(mapping["input_contract"], "alignment.input_contract"),
            parameter_names_read=_boolean(
                mapping["parameter_names_read"], "alignment.parameter_names_read"
            ),
            graph_refs=tuple(
                GraphContractRef.from_mapping(item)
                for item in _mapping_array(mapping["graph_refs"], "alignment.graph_refs")
            ),
            common_backbone=tuple(
                CommonBackboneSlot.from_mapping(item)
                for item in _mapping_array(
                    mapping["common_backbone"], "alignment.common_backbone"
                )
            ),
            residuals=tuple(
                AlignmentResidual.from_mapping(item)
                for item in _mapping_array(mapping["residuals"], "alignment.residuals")
            ),
            alignment_id=_string(mapping["alignment_id"], "alignment.alignment_id"),
            content_sha256=_hash(
                mapping["content_sha256"], "alignment.content_sha256"
            ),
        )


@dataclass(frozen=True)
class ProposalGraphLocator:
    """A source graph locator supporting one proposal assertion."""

    instance_id: str
    graph_id: str
    source_path: str
    source_raw_sha256: str
    contract_sha256: str
    locator: str
    relation: str

    def __post_init__(self) -> None:
        for value, path in (
            (self.instance_id, "proposal_locator.instance_id"),
            (self.graph_id, "proposal_locator.graph_id"),
            (self.locator, "proposal_locator.locator"),
            (self.relation, "proposal_locator.relation"),
        ):
            _non_empty(value, path)
        _relative_path(self.source_path, "proposal_locator.source_path")
        _hash(self.source_raw_sha256, "proposal_locator.source_raw_sha256")
        _hash(self.contract_sha256, "proposal_locator.contract_sha256")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "graph_id": self.graph_id,
            "source_path": self.source_path,
            "source_raw_sha256": self.source_raw_sha256,
            "contract_sha256": self.contract_sha256,
            "locator": self.locator,
            "relation": self.relation,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProposalGraphLocator":
        mapping = _mapping(value, "proposal_locator")
        required = {
            "instance_id",
            "graph_id",
            "source_path",
            "source_raw_sha256",
            "contract_sha256",
            "locator",
            "relation",
        }
        _exact_keys(mapping, required, "proposal_locator")
        return cls(
            instance_id=_string(mapping["instance_id"], "proposal_locator.instance_id"),
            graph_id=_string(mapping["graph_id"], "proposal_locator.graph_id"),
            source_path=_relative_path(
                mapping["source_path"], "proposal_locator.source_path"
            ),
            source_raw_sha256=_hash(
                mapping["source_raw_sha256"], "proposal_locator.source_raw_sha256"
            ),
            contract_sha256=_hash(
                mapping["contract_sha256"], "proposal_locator.contract_sha256"
            ),
            locator=_string(mapping["locator"], "proposal_locator.locator"),
            relation=_string(mapping["relation"], "proposal_locator.relation"),
        )


@dataclass(frozen=True)
class InsertionAdjacency:
    """One side-specific location inferred for an optional region."""

    side: str
    before_region_type: str
    after_region_type: str

    def __post_init__(self) -> None:
        if self.side not in {"left", "right"}:
            raise InductionContractError("insertion adjacency side must be left or right")
        _non_empty(self.before_region_type, "insertion.before_region_type")
        _non_empty(self.after_region_type, "insertion.after_region_type")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "before_region_type": self.before_region_type,
            "after_region_type": self.after_region_type,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InsertionAdjacency":
        mapping = _mapping(value, "insertion")
        _exact_keys(
            mapping,
            {"side", "before_region_type", "after_region_type"},
            "insertion",
        )
        return cls(
            side=_string(mapping["side"], "insertion.side"),
            before_region_type=_string(
                mapping["before_region_type"], "insertion.before_region_type"
            ),
            after_region_type=_string(
                mapping["after_region_type"], "insertion.after_region_type"
            ),
        )


@dataclass(frozen=True)
class ProposalSupport:
    """Structured, deterministic support for a v1 induction proposal."""

    structural_match: float
    evidence_completeness: float
    review_coverage: float
    cross_instance_support: float
    population_size: int
    symmetry_assumption_used: bool
    detector_id: str
    detector_version: str

    def __post_init__(self) -> None:
        for value, path in (
            (self.structural_match, "support.structural_match"),
            (self.evidence_completeness, "support.evidence_completeness"),
            (self.review_coverage, "support.review_coverage"),
            (self.cross_instance_support, "support.cross_instance_support"),
        ):
            score = _number(value, path)
            if not 0.0 <= score <= 1.0:
                raise InductionContractError(f"{path} must be in [0, 1]")
        if _integer(self.population_size, "support.population_size") < 2:
            raise InductionContractError("support population_size must be at least two")
        if not isinstance(self.symmetry_assumption_used, bool):
            raise InductionContractError(
                "support.symmetry_assumption_used must be boolean"
            )
        _non_empty(self.detector_id, "support.detector_id")
        _non_empty(self.detector_version, "support.detector_version")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "structural_match": float(self.structural_match),
            "evidence_completeness": float(self.evidence_completeness),
            "review_coverage": float(self.review_coverage),
            "cross_instance_support": float(self.cross_instance_support),
            "population_size": self.population_size,
            "symmetry_assumption_used": self.symmetry_assumption_used,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProposalSupport":
        mapping = _mapping(value, "proposal.support")
        _exact_keys(
            mapping,
            {
                "structural_match",
                "evidence_completeness",
                "review_coverage",
                "cross_instance_support",
                "population_size",
                "symmetry_assumption_used",
                "detector_id",
                "detector_version",
            },
            "proposal.support",
        )
        return cls(
            structural_match=_number(
                mapping["structural_match"], "support.structural_match"
            ),
            evidence_completeness=_number(
                mapping["evidence_completeness"],
                "support.evidence_completeness",
            ),
            review_coverage=_number(
                mapping["review_coverage"], "support.review_coverage"
            ),
            cross_instance_support=_number(
                mapping["cross_instance_support"],
                "support.cross_instance_support",
            ),
            population_size=_integer(
                mapping["population_size"], "support.population_size"
            ),
            symmetry_assumption_used=_boolean(
                mapping["symmetry_assumption_used"],
                "support.symmetry_assumption_used",
            ),
            detector_id=_string(mapping["detector_id"], "support.detector_id"),
            detector_version=_string(
                mapping["detector_version"], "support.detector_version"
            ),
        )


@dataclass(frozen=True)
class FamilyExtensionProposal:
    """Evidence-gated family structure proposal; never a grammar mutation."""

    family_id: str
    proposal_kind: str
    alignment_id: str
    alignment_content_sha256: str
    source_instance_ids: tuple[str, ...]
    common_backbone_keys: tuple[str, ...]
    motif_id: str | None
    region_type: str | None
    occurrence_rule: str | None
    allowed_counts: tuple[int, ...]
    insertion_adjacencies: tuple[InsertionAdjacency, ...]
    present_instance_ids: tuple[str, ...]
    absent_instance_ids: tuple[str, ...]
    graph_locators: tuple[ProposalGraphLocator, ...]
    evidence: tuple[EvidenceRef, ...]
    confidence: float
    confidence_basis: str
    alternative_reason: str | None
    limitations: tuple[str, ...]
    algorithm_version: str = INDUCTION_ALGORITHM_VERSION
    review_status: str = "pending"
    grammar_mutation_status: str = "not_applied"
    proposal_id: str = ""
    content_sha256: str = ""
    schema_version: str = PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROPOSAL_SCHEMA_VERSION:
            raise InductionContractError("unsupported family extension proposal schema")
        if self.algorithm_version != INDUCTION_ALGORITHM_VERSION:
            raise InductionContractError("proposal algorithm version mismatch")
        if self.review_status != "pending" or self.grammar_mutation_status != "not_applied":
            raise InductionContractError("new proposals must remain pending and non-mutating")
        if self.proposal_kind not in {"optional_motif", "alternative_topology"}:
            raise InductionContractError("unsupported family extension proposal kind")
        _non_empty(self.family_id, "proposal.family_id")
        _non_empty(self.alignment_id, "proposal.alignment_id")
        _hash(self.alignment_content_sha256, "proposal.alignment_content_sha256")
        _unique_non_empty(self.source_instance_ids, "proposal.source_instance_ids")
        _unique_non_empty(self.common_backbone_keys, "proposal.common_backbone_keys")
        if not self.graph_locators or not self.evidence:
            raise InductionContractError("proposal requires graph locators and evidence")
        confidence = _number(self.confidence, "proposal.confidence")
        if confidence < 0.0 or confidence > 1.0:
            raise InductionContractError("proposal confidence must be in [0, 1]")
        if self.confidence_basis != CONFIDENCE_CONTRACT:
            raise InductionContractError("proposal confidence basis is unsupported")
        _unique_non_empty(self.limitations, "proposal.limitations")
        if self.proposal_kind == "optional_motif":
            for value, path in (
                (self.motif_id, "proposal.motif_id"),
                (self.region_type, "proposal.region_type"),
                (self.occurrence_rule, "proposal.occurrence_rule"),
            ):
                if value is None:
                    raise InductionContractError(f"{path} is required")
                _non_empty(value, path)
            if self.occurrence_rule != "paired_optional" or self.allowed_counts != (0, 2):
                raise InductionContractError("R3 optional motif must be paired with counts 0 or 2")
            if len(self.insertion_adjacencies) != 2 or {
                item.side for item in self.insertion_adjacencies
            } != {"left", "right"}:
                raise InductionContractError("paired optional proposal requires left/right insertions")
            if not self.present_instance_ids or not self.absent_instance_ids:
                raise InductionContractError("optional proposal requires present/absent contrast")
            if set(self.present_instance_ids) | set(self.absent_instance_ids) != set(
                self.source_instance_ids
            ):
                raise InductionContractError("proposal presence partition is incomplete")
            if set(self.present_instance_ids) & set(self.absent_instance_ids):
                raise InductionContractError("proposal presence partition overlaps")
            if self.alternative_reason is not None:
                raise InductionContractError("optional motif proposal cannot have alternative_reason")
        else:
            if any(
                value is not None
                for value in (self.motif_id, self.region_type, self.occurrence_rule)
            ):
                raise InductionContractError("alternative topology cannot assert a motif")
            if self.allowed_counts or self.insertion_adjacencies:
                raise InductionContractError("alternative topology cannot define motif cardinality")
            if self.alternative_reason is None:
                raise InductionContractError("alternative topology requires a reason")
            _non_empty(self.alternative_reason, "proposal.alternative_reason")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.family_id}.proposal.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "proposal_id", self.proposal_id, expected_id)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "proposal_kind": self.proposal_kind,
            "alignment_id": self.alignment_id,
            "alignment_content_sha256": self.alignment_content_sha256,
            "source_instance_ids": list(self.source_instance_ids),
            "common_backbone_keys": list(self.common_backbone_keys),
            "motif_id": self.motif_id,
            "region_type": self.region_type,
            "occurrence_rule": self.occurrence_rule,
            "allowed_counts": list(self.allowed_counts),
            "insertion_adjacencies": [
                item.to_mapping() for item in self.insertion_adjacencies
            ],
            "present_instance_ids": list(self.present_instance_ids),
            "absent_instance_ids": list(self.absent_instance_ids),
            "graph_locators": [item.to_mapping() for item in self.graph_locators],
            "evidence": [item.to_mapping() for item in self.evidence],
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "alternative_reason": self.alternative_reason,
            "limitations": list(self.limitations),
            "algorithm_version": self.algorithm_version,
            "review_status": self.review_status,
            "grammar_mutation_status": self.grammar_mutation_status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "proposal_id": self.proposal_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FamilyExtensionProposal":
        mapping = _mapping(value, "proposal")
        required = {
            "schema_version",
            "family_id",
            "proposal_kind",
            "alignment_id",
            "alignment_content_sha256",
            "source_instance_ids",
            "common_backbone_keys",
            "motif_id",
            "region_type",
            "occurrence_rule",
            "allowed_counts",
            "insertion_adjacencies",
            "present_instance_ids",
            "absent_instance_ids",
            "graph_locators",
            "evidence",
            "confidence",
            "confidence_basis",
            "alternative_reason",
            "limitations",
            "algorithm_version",
            "review_status",
            "grammar_mutation_status",
            "proposal_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "proposal")
        return cls(
            schema_version=_string(mapping["schema_version"], "proposal.schema_version"),
            family_id=_string(mapping["family_id"], "proposal.family_id"),
            proposal_kind=_string(mapping["proposal_kind"], "proposal.proposal_kind"),
            alignment_id=_string(mapping["alignment_id"], "proposal.alignment_id"),
            alignment_content_sha256=_hash(
                mapping["alignment_content_sha256"],
                "proposal.alignment_content_sha256",
            ),
            source_instance_ids=_string_tuple(
                mapping["source_instance_ids"], "proposal.source_instance_ids"
            ),
            common_backbone_keys=_string_tuple(
                mapping["common_backbone_keys"], "proposal.common_backbone_keys"
            ),
            motif_id=_optional_string(mapping["motif_id"], "proposal.motif_id"),
            region_type=_optional_string(
                mapping["region_type"], "proposal.region_type"
            ),
            occurrence_rule=_optional_string(
                mapping["occurrence_rule"], "proposal.occurrence_rule"
            ),
            allowed_counts=_integer_tuple(
                mapping["allowed_counts"], "proposal.allowed_counts"
            ),
            insertion_adjacencies=tuple(
                InsertionAdjacency.from_mapping(item)
                for item in _mapping_array(
                    mapping["insertion_adjacencies"],
                    "proposal.insertion_adjacencies",
                )
            ),
            present_instance_ids=_string_tuple(
                mapping["present_instance_ids"], "proposal.present_instance_ids"
            ),
            absent_instance_ids=_string_tuple(
                mapping["absent_instance_ids"], "proposal.absent_instance_ids"
            ),
            graph_locators=tuple(
                ProposalGraphLocator.from_mapping(item)
                for item in _mapping_array(
                    mapping["graph_locators"], "proposal.graph_locators"
                )
            ),
            evidence=tuple(
                EvidenceRef.from_mapping(item)
                for item in _mapping_array(mapping["evidence"], "proposal.evidence")
            ),
            confidence=_number(mapping["confidence"], "proposal.confidence"),
            confidence_basis=_string(
                mapping["confidence_basis"], "proposal.confidence_basis"
            ),
            alternative_reason=_optional_string(
                mapping["alternative_reason"], "proposal.alternative_reason"
            ),
            limitations=_string_tuple(mapping["limitations"], "proposal.limitations"),
            algorithm_version=_string(
                mapping["algorithm_version"], "proposal.algorithm_version"
            ),
            review_status=_string(mapping["review_status"], "proposal.review_status"),
            grammar_mutation_status=_string(
                mapping["grammar_mutation_status"],
                "proposal.grammar_mutation_status",
            ),
            proposal_id=_string(mapping["proposal_id"], "proposal.proposal_id"),
            content_sha256=_hash(mapping["content_sha256"], "proposal.content_sha256"),
        )


@dataclass(frozen=True)
class FamilyExtensionProposalV1:
    """Detector-selected proposal with structured non-probability support."""

    family_id: str
    proposal_kind: str
    alignment_id: str
    alignment_content_sha256: str
    source_instance_ids: tuple[str, ...]
    common_backbone_keys: tuple[str, ...]
    motif_id: str | None
    region_type: str | None
    occurrence_rule: str | None
    allowed_counts: tuple[int, ...]
    insertion_adjacencies: tuple[InsertionAdjacency, ...]
    present_instance_ids: tuple[str, ...]
    absent_instance_ids: tuple[str, ...]
    graph_locators: tuple[ProposalGraphLocator, ...]
    evidence: tuple[EvidenceRef, ...]
    support: ProposalSupport
    proposal_score: float
    score_semantics: str
    alternative_reason: str | None
    limitations: tuple[str, ...]
    algorithm_version: str = INDUCTION_ALGORITHM_VERSION_V1
    review_status: str = "pending"
    grammar_mutation_status: str = "not_applied"
    proposal_id: str = ""
    content_sha256: str = ""
    schema_version: str = PROPOSAL_SCHEMA_VERSION_V1

    def __post_init__(self) -> None:
        if self.schema_version != PROPOSAL_SCHEMA_VERSION_V1:
            raise InductionContractError("unsupported v1 family extension proposal schema")
        if self.algorithm_version != INDUCTION_ALGORITHM_VERSION_V1:
            raise InductionContractError("v1 proposal algorithm version mismatch")
        if self.review_status != "pending" or self.grammar_mutation_status != "not_applied":
            raise InductionContractError("new proposals must remain pending and non-mutating")
        if self.proposal_kind not in {"optional_motif", "alternative_topology"}:
            raise InductionContractError("unsupported family extension proposal kind")
        _non_empty(self.family_id, "proposal.family_id")
        _non_empty(self.alignment_id, "proposal.alignment_id")
        _hash(self.alignment_content_sha256, "proposal.alignment_content_sha256")
        _unique_non_empty(self.source_instance_ids, "proposal.source_instance_ids")
        _unique_non_empty(self.common_backbone_keys, "proposal.common_backbone_keys")
        if not self.graph_locators or not self.evidence:
            raise InductionContractError("proposal requires graph locators and evidence")
        if self.support.population_size != len(self.source_instance_ids):
            raise InductionContractError(
                "proposal support population_size must match source instances"
            )
        score = _number(self.proposal_score, "proposal.proposal_score")
        if not 0.0 <= score <= 1.0:
            raise InductionContractError("proposal_score must be in [0, 1]")
        if self.score_semantics != SCORE_SEMANTICS:
            raise InductionContractError("proposal score semantics is unsupported")
        _unique_non_empty(self.limitations, "proposal.limitations")
        if self.proposal_kind == "optional_motif":
            for value, path in (
                (self.motif_id, "proposal.motif_id"),
                (self.region_type, "proposal.region_type"),
                (self.occurrence_rule, "proposal.occurrence_rule"),
            ):
                if value is None:
                    raise InductionContractError(f"{path} is required")
                _non_empty(value, path)
            expected_shape = {
                "paired_optional": ((0, 2), 2, {"left", "right"}),
                "single_optional": ((0, 1), 1, None),
            }.get(self.occurrence_rule)
            if expected_shape is None:
                raise InductionContractError("unsupported v1 optional occurrence rule")
            expected_counts, expected_insertions, expected_sides = expected_shape
            if self.allowed_counts != expected_counts or len(
                self.insertion_adjacencies
            ) != expected_insertions:
                raise InductionContractError("v1 optional motif shape is inconsistent")
            sides = {item.side for item in self.insertion_adjacencies}
            if expected_sides is not None and sides != expected_sides:
                raise InductionContractError(
                    "paired optional proposal requires left/right insertions"
                )
            if not self.present_instance_ids or not self.absent_instance_ids:
                raise InductionContractError(
                    "optional proposal requires present/absent contrast"
                )
            if set(self.present_instance_ids) | set(self.absent_instance_ids) != set(
                self.source_instance_ids
            ) or set(self.present_instance_ids) & set(self.absent_instance_ids):
                raise InductionContractError(
                    "proposal presence partition must be complete and disjoint"
                )
            if self.alternative_reason is not None:
                raise InductionContractError(
                    "optional motif proposal cannot have alternative_reason"
                )
        else:
            if any(
                value is not None
                for value in (self.motif_id, self.region_type, self.occurrence_rule)
            ):
                raise InductionContractError("alternative topology cannot assert a motif")
            if self.allowed_counts or self.insertion_adjacencies:
                raise InductionContractError(
                    "alternative topology cannot define motif cardinality"
                )
            if self.alternative_reason is None:
                raise InductionContractError("alternative topology requires a reason")
            _non_empty(self.alternative_reason, "proposal.alternative_reason")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.family_id}.proposal.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "proposal_id", self.proposal_id, expected_id)

    @property
    def confidence(self) -> float:
        """Deprecated API view; this is a ranking score, never probability."""

        return self.proposal_score

    @property
    def confidence_basis(self) -> str:
        """Deprecated API view of the explicit non-probability semantics."""

        return self.score_semantics

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "proposal_kind": self.proposal_kind,
            "alignment_id": self.alignment_id,
            "alignment_content_sha256": self.alignment_content_sha256,
            "source_instance_ids": list(self.source_instance_ids),
            "common_backbone_keys": list(self.common_backbone_keys),
            "motif_id": self.motif_id,
            "region_type": self.region_type,
            "occurrence_rule": self.occurrence_rule,
            "allowed_counts": list(self.allowed_counts),
            "insertion_adjacencies": [
                item.to_mapping() for item in self.insertion_adjacencies
            ],
            "present_instance_ids": list(self.present_instance_ids),
            "absent_instance_ids": list(self.absent_instance_ids),
            "graph_locators": [item.to_mapping() for item in self.graph_locators],
            "evidence": [item.to_mapping() for item in self.evidence],
            "support": self.support.to_mapping(),
            "proposal_score": float(self.proposal_score),
            "score_semantics": self.score_semantics,
            "alternative_reason": self.alternative_reason,
            "limitations": list(self.limitations),
            "algorithm_version": self.algorithm_version,
            "review_status": self.review_status,
            "grammar_mutation_status": self.grammar_mutation_status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "proposal_id": self.proposal_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FamilyExtensionProposalV1":
        mapping = _mapping(value, "proposal")
        required = {
            "schema_version",
            "family_id",
            "proposal_kind",
            "alignment_id",
            "alignment_content_sha256",
            "source_instance_ids",
            "common_backbone_keys",
            "motif_id",
            "region_type",
            "occurrence_rule",
            "allowed_counts",
            "insertion_adjacencies",
            "present_instance_ids",
            "absent_instance_ids",
            "graph_locators",
            "evidence",
            "support",
            "proposal_score",
            "score_semantics",
            "alternative_reason",
            "limitations",
            "algorithm_version",
            "review_status",
            "grammar_mutation_status",
            "proposal_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "proposal")
        return cls(
            schema_version=_string(mapping["schema_version"], "proposal.schema_version"),
            family_id=_string(mapping["family_id"], "proposal.family_id"),
            proposal_kind=_string(mapping["proposal_kind"], "proposal.proposal_kind"),
            alignment_id=_string(mapping["alignment_id"], "proposal.alignment_id"),
            alignment_content_sha256=_hash(
                mapping["alignment_content_sha256"],
                "proposal.alignment_content_sha256",
            ),
            source_instance_ids=_string_tuple(
                mapping["source_instance_ids"], "proposal.source_instance_ids"
            ),
            common_backbone_keys=_string_tuple(
                mapping["common_backbone_keys"], "proposal.common_backbone_keys"
            ),
            motif_id=_optional_string(mapping["motif_id"], "proposal.motif_id"),
            region_type=_optional_string(
                mapping["region_type"], "proposal.region_type"
            ),
            occurrence_rule=_optional_string(
                mapping["occurrence_rule"], "proposal.occurrence_rule"
            ),
            allowed_counts=_integer_tuple(
                mapping["allowed_counts"], "proposal.allowed_counts"
            ),
            insertion_adjacencies=tuple(
                InsertionAdjacency.from_mapping(item)
                for item in _mapping_array(
                    mapping["insertion_adjacencies"],
                    "proposal.insertion_adjacencies",
                )
            ),
            present_instance_ids=_string_tuple(
                mapping["present_instance_ids"], "proposal.present_instance_ids"
            ),
            absent_instance_ids=_string_tuple(
                mapping["absent_instance_ids"], "proposal.absent_instance_ids"
            ),
            graph_locators=tuple(
                ProposalGraphLocator.from_mapping(item)
                for item in _mapping_array(
                    mapping["graph_locators"], "proposal.graph_locators"
                )
            ),
            evidence=tuple(
                EvidenceRef.from_mapping(item)
                for item in _mapping_array(mapping["evidence"], "proposal.evidence")
            ),
            support=ProposalSupport.from_mapping(
                _mapping(mapping["support"], "proposal.support")
            ),
            proposal_score=_number(
                mapping["proposal_score"], "proposal.proposal_score"
            ),
            score_semantics=_string(
                mapping["score_semantics"], "proposal.score_semantics"
            ),
            alternative_reason=_optional_string(
                mapping["alternative_reason"], "proposal.alternative_reason"
            ),
            limitations=_string_tuple(mapping["limitations"], "proposal.limitations"),
            algorithm_version=_string(
                mapping["algorithm_version"], "proposal.algorithm_version"
            ),
            review_status=_string(mapping["review_status"], "proposal.review_status"),
            grammar_mutation_status=_string(
                mapping["grammar_mutation_status"],
                "proposal.grammar_mutation_status",
            ),
            proposal_id=_string(mapping["proposal_id"], "proposal.proposal_id"),
            content_sha256=_hash(mapping["content_sha256"], "proposal.content_sha256"),
        )


FamilyExtensionProposalContract = Union[
    FamilyExtensionProposal,
    FamilyExtensionProposalV1,
]


@dataclass(frozen=True)
class ProposalReview:
    """Explicit manual decision that remains separate from a proposal."""

    proposal_id: str
    proposal_content_sha256: str
    decision: str
    reviewer_id: str
    rationale: str
    revision: int
    evidence: tuple[EvidenceRef, ...]
    manual_confirmation: bool = True
    review_id: str = ""
    content_sha256: str = ""
    schema_version: str = PROPOSAL_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROPOSAL_REVIEW_SCHEMA_VERSION:
            raise InductionContractError("unsupported proposal review schema")
        if self.decision not in {"accepted", "rejected", "needs_evidence"}:
            raise InductionContractError("unsupported proposal review decision")
        if self.manual_confirmation is not True:
            raise InductionContractError("proposal review must be an explicit manual confirmation")
        for value, path in (
            (self.proposal_id, "proposal_review.proposal_id"),
            (self.reviewer_id, "proposal_review.reviewer_id"),
            (self.rationale, "proposal_review.rationale"),
        ):
            _non_empty(value, path)
        _hash(
            self.proposal_content_sha256,
            "proposal_review.proposal_content_sha256",
        )
        _non_negative_integer(self.revision, "proposal_review.revision")
        if not self.evidence:
            raise InductionContractError("proposal review requires evidence")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.proposal_id}.review.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "review_id", self.review_id, expected_id)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "proposal_content_sha256": self.proposal_content_sha256,
            "decision": self.decision,
            "reviewer_id": self.reviewer_id,
            "rationale": self.rationale,
            "revision": self.revision,
            "evidence": [item.to_mapping() for item in self.evidence],
            "manual_confirmation": self.manual_confirmation,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "review_id": self.review_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProposalReview":
        mapping = _mapping(value, "proposal_review")
        required = {
            "schema_version",
            "proposal_id",
            "proposal_content_sha256",
            "decision",
            "reviewer_id",
            "rationale",
            "revision",
            "evidence",
            "manual_confirmation",
            "review_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "proposal_review")
        return cls(
            schema_version=_string(
                mapping["schema_version"], "proposal_review.schema_version"
            ),
            proposal_id=_string(mapping["proposal_id"], "proposal_review.proposal_id"),
            proposal_content_sha256=_hash(
                mapping["proposal_content_sha256"],
                "proposal_review.proposal_content_sha256",
            ),
            decision=_string(mapping["decision"], "proposal_review.decision"),
            reviewer_id=_string(mapping["reviewer_id"], "proposal_review.reviewer_id"),
            rationale=_string(mapping["rationale"], "proposal_review.rationale"),
            revision=_integer(mapping["revision"], "proposal_review.revision"),
            evidence=tuple(
                EvidenceRef.from_mapping(item)
                for item in _mapping_array(mapping["evidence"], "proposal_review.evidence")
            ),
            manual_confirmation=_boolean(
                mapping["manual_confirmation"],
                "proposal_review.manual_confirmation",
            ),
            review_id=_string(mapping["review_id"], "proposal_review.review_id"),
            content_sha256=_hash(
                mapping["content_sha256"], "proposal_review.content_sha256"
            ),
        )


@dataclass(frozen=True)
class GrammarPatch:
    """Explicit authorized transformation from one grammar hash to another."""

    base_grammar_id: str
    base_grammar_sha256: str
    target_grammar_id: str
    target_grammar_sha256: str
    proposal_id: str
    proposal_content_sha256: str
    review_id: str
    review_content_sha256: str
    operations: tuple[str, ...]
    proposed_motif: SemanticMotif
    audit_evidence: tuple[EvidenceRef, ...]
    authorization: str = "accepted_manual_review"
    patch_id: str = ""
    content_sha256: str = ""
    schema_version: str = GRAMMAR_PATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GRAMMAR_PATCH_SCHEMA_VERSION:
            raise InductionContractError("unsupported grammar patch schema")
        if self.authorization != "accepted_manual_review":
            raise InductionContractError("grammar patch lacks accepted manual review")
        for value, path in (
            (self.base_grammar_id, "grammar_patch.base_grammar_id"),
            (self.target_grammar_id, "grammar_patch.target_grammar_id"),
            (self.proposal_id, "grammar_patch.proposal_id"),
            (self.review_id, "grammar_patch.review_id"),
        ):
            _non_empty(value, path)
        for value, path in (
            (self.base_grammar_sha256, "grammar_patch.base_grammar_sha256"),
            (self.target_grammar_sha256, "grammar_patch.target_grammar_sha256"),
            (self.proposal_content_sha256, "grammar_patch.proposal_content_sha256"),
            (self.review_content_sha256, "grammar_patch.review_content_sha256"),
        ):
            _hash(value, path)
        _unique_non_empty(self.operations, "grammar_patch.operations")
        required = {
            "set_grammar_id",
            "append_induction_evidence",
            "replace_review_binding",
            "remove_family_induction_exclusion",
        }
        if not required.issubset(self.operations):
            raise InductionContractError("grammar patch is missing mandatory audit operations")
        if not ({"add_optional_motif", "confirm_optional_motif"} & set(self.operations)):
            raise InductionContractError("grammar patch must add or confirm an optional motif")
        if not self.audit_evidence:
            raise InductionContractError("grammar patch requires audit evidence")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.base_grammar_id}.patch.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "patch_id", self.patch_id, expected_id)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_grammar_id": self.base_grammar_id,
            "base_grammar_sha256": self.base_grammar_sha256,
            "target_grammar_id": self.target_grammar_id,
            "target_grammar_sha256": self.target_grammar_sha256,
            "proposal_id": self.proposal_id,
            "proposal_content_sha256": self.proposal_content_sha256,
            "review_id": self.review_id,
            "review_content_sha256": self.review_content_sha256,
            "operations": list(self.operations),
            "proposed_motif": self.proposed_motif.to_mapping(),
            "audit_evidence": [item.to_mapping() for item in self.audit_evidence],
            "authorization": self.authorization,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "patch_id": self.patch_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GrammarPatch":
        mapping = _mapping(value, "grammar_patch")
        required = {
            "schema_version",
            "base_grammar_id",
            "base_grammar_sha256",
            "target_grammar_id",
            "target_grammar_sha256",
            "proposal_id",
            "proposal_content_sha256",
            "review_id",
            "review_content_sha256",
            "operations",
            "proposed_motif",
            "audit_evidence",
            "authorization",
            "patch_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "grammar_patch")
        return cls(
            schema_version=_string(mapping["schema_version"], "grammar_patch.schema_version"),
            base_grammar_id=_string(
                mapping["base_grammar_id"], "grammar_patch.base_grammar_id"
            ),
            base_grammar_sha256=_hash(
                mapping["base_grammar_sha256"], "grammar_patch.base_grammar_sha256"
            ),
            target_grammar_id=_string(
                mapping["target_grammar_id"], "grammar_patch.target_grammar_id"
            ),
            target_grammar_sha256=_hash(
                mapping["target_grammar_sha256"], "grammar_patch.target_grammar_sha256"
            ),
            proposal_id=_string(mapping["proposal_id"], "grammar_patch.proposal_id"),
            proposal_content_sha256=_hash(
                mapping["proposal_content_sha256"],
                "grammar_patch.proposal_content_sha256",
            ),
            review_id=_string(mapping["review_id"], "grammar_patch.review_id"),
            review_content_sha256=_hash(
                mapping["review_content_sha256"],
                "grammar_patch.review_content_sha256",
            ),
            operations=_string_tuple(mapping["operations"], "grammar_patch.operations"),
            proposed_motif=SemanticMotif.from_mapping(
                _mapping(mapping["proposed_motif"], "grammar_patch.proposed_motif")
            ),
            audit_evidence=tuple(
                EvidenceRef.from_mapping(item)
                for item in _mapping_array(
                    mapping["audit_evidence"], "grammar_patch.audit_evidence"
                )
            ),
            authorization=_string(
                mapping["authorization"], "grammar_patch.authorization"
            ),
            patch_id=_string(mapping["patch_id"], "grammar_patch.patch_id"),
            content_sha256=_hash(
                mapping["content_sha256"], "grammar_patch.content_sha256"
            ),
        )


@dataclass(frozen=True)
class GrammarDiffEntry:
    """One human-visible grammar before/after difference."""

    path: str
    before: Any
    after: Any

    def __post_init__(self) -> None:
        _non_empty(self.path, "grammar_diff.path")
        _finite_json(self.before, "grammar_diff.before")
        _finite_json(self.after, "grammar_diff.after")
        if canonical_json_bytes(self.before) == canonical_json_bytes(self.after):
            raise InductionContractError("grammar diff entry must describe a change")

    def to_mapping(self) -> dict[str, Any]:
        return {"path": self.path, "before": self.before, "after": self.after}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GrammarDiffEntry":
        mapping = _mapping(value, "grammar_diff")
        _exact_keys(mapping, {"path", "before", "after"}, "grammar_diff")
        return cls(
            path=_string(mapping["path"], "grammar_diff.path"),
            before=mapping["before"],
            after=mapping["after"],
        )


@dataclass(frozen=True)
class GrammarPatchApplication:
    """Auditable result of applying or withholding one reviewed proposal."""

    proposal_id: str
    review_id: str
    review_decision: str
    applied: bool
    patch_id: str | None
    patch_content_sha256: str | None
    before_grammar_id: str
    before_grammar_sha256: str
    after_grammar_id: str
    after_grammar_sha256: str
    grammar_diff: tuple[GrammarDiffEntry, ...]
    validated_instance_ids: tuple[str, ...]
    all_instances_valid: bool
    original_grammar_unchanged_before_review: bool = True
    status: str = "pass"
    application_id: str = ""
    content_sha256: str = ""
    schema_version: str = PATCH_APPLICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PATCH_APPLICATION_SCHEMA_VERSION:
            raise InductionContractError("unsupported patch application schema")
        if self.review_decision not in {"accepted", "rejected", "needs_evidence"}:
            raise InductionContractError("unsupported patch application review decision")
        if self.status != "pass":
            raise InductionContractError("persisted patch application must pass")
        if self.original_grammar_unchanged_before_review is not True:
            raise InductionContractError("proposal must not mutate grammar before review")
        for value, path in (
            (self.proposal_id, "patch_application.proposal_id"),
            (self.review_id, "patch_application.review_id"),
            (self.before_grammar_id, "patch_application.before_grammar_id"),
            (self.after_grammar_id, "patch_application.after_grammar_id"),
        ):
            _non_empty(value, path)
        _hash(self.before_grammar_sha256, "patch_application.before_grammar_sha256")
        _hash(self.after_grammar_sha256, "patch_application.after_grammar_sha256")
        if self.applied:
            if self.review_decision != "accepted":
                raise InductionContractError("only an accepted review may apply a patch")
            if self.patch_id is None or self.patch_content_sha256 is None:
                raise InductionContractError("applied patch requires patch identity")
            _non_empty(self.patch_id, "patch_application.patch_id")
            _hash(
                self.patch_content_sha256,
                "patch_application.patch_content_sha256",
            )
            if not self.grammar_diff or not self.validated_instance_ids:
                raise InductionContractError("applied patch requires diff and revalidation")
            if self.all_instances_valid is not True:
                raise InductionContractError("applied patch must revalidate every existing instance")
            if self.before_grammar_sha256 == self.after_grammar_sha256:
                raise InductionContractError("applied patch must update grammar content")
        else:
            if self.review_decision == "accepted":
                raise InductionContractError("accepted review cannot remain unapplied")
            if self.patch_id is not None or self.patch_content_sha256 is not None:
                raise InductionContractError("withheld review cannot create a patch")
            if self.before_grammar_id != self.after_grammar_id or (
                self.before_grammar_sha256 != self.after_grammar_sha256
            ):
                raise InductionContractError("withheld review must leave grammar unchanged")
            if self.grammar_diff:
                raise InductionContractError("withheld review cannot have a grammar diff")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.proposal_id}.application.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "application_id", self.application_id, expected_id)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "review_id": self.review_id,
            "review_decision": self.review_decision,
            "applied": self.applied,
            "patch_id": self.patch_id,
            "patch_content_sha256": self.patch_content_sha256,
            "before_grammar_id": self.before_grammar_id,
            "before_grammar_sha256": self.before_grammar_sha256,
            "after_grammar_id": self.after_grammar_id,
            "after_grammar_sha256": self.after_grammar_sha256,
            "grammar_diff": [item.to_mapping() for item in self.grammar_diff],
            "validated_instance_ids": list(self.validated_instance_ids),
            "all_instances_valid": self.all_instances_valid,
            "original_grammar_unchanged_before_review": (
                self.original_grammar_unchanged_before_review
            ),
            "status": self.status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "application_id": self.application_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GrammarPatchApplication":
        mapping = _mapping(value, "patch_application")
        required = {
            "schema_version",
            "proposal_id",
            "review_id",
            "review_decision",
            "applied",
            "patch_id",
            "patch_content_sha256",
            "before_grammar_id",
            "before_grammar_sha256",
            "after_grammar_id",
            "after_grammar_sha256",
            "grammar_diff",
            "validated_instance_ids",
            "all_instances_valid",
            "original_grammar_unchanged_before_review",
            "status",
            "application_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "patch_application")
        return cls(
            schema_version=_string(
                mapping["schema_version"], "patch_application.schema_version"
            ),
            proposal_id=_string(
                mapping["proposal_id"], "patch_application.proposal_id"
            ),
            review_id=_string(mapping["review_id"], "patch_application.review_id"),
            review_decision=_string(
                mapping["review_decision"], "patch_application.review_decision"
            ),
            applied=_boolean(mapping["applied"], "patch_application.applied"),
            patch_id=_optional_string(mapping["patch_id"], "patch_application.patch_id"),
            patch_content_sha256=_optional_hash(
                mapping["patch_content_sha256"],
                "patch_application.patch_content_sha256",
            ),
            before_grammar_id=_string(
                mapping["before_grammar_id"], "patch_application.before_grammar_id"
            ),
            before_grammar_sha256=_hash(
                mapping["before_grammar_sha256"],
                "patch_application.before_grammar_sha256",
            ),
            after_grammar_id=_string(
                mapping["after_grammar_id"], "patch_application.after_grammar_id"
            ),
            after_grammar_sha256=_hash(
                mapping["after_grammar_sha256"],
                "patch_application.after_grammar_sha256",
            ),
            grammar_diff=tuple(
                GrammarDiffEntry.from_mapping(item)
                for item in _mapping_array(
                    mapping["grammar_diff"], "patch_application.grammar_diff"
                )
            ),
            validated_instance_ids=_string_tuple(
                mapping["validated_instance_ids"],
                "patch_application.validated_instance_ids",
            ),
            all_instances_valid=_boolean(
                mapping["all_instances_valid"],
                "patch_application.all_instances_valid",
            ),
            original_grammar_unchanged_before_review=_boolean(
                mapping["original_grammar_unchanged_before_review"],
                "patch_application.original_grammar_unchanged_before_review",
            ),
            status=_string(mapping["status"], "patch_application.status"),
            application_id=_string(
                mapping["application_id"], "patch_application.application_id"
            ),
            content_sha256=_hash(
                mapping["content_sha256"], "patch_application.content_sha256"
            ),
        )


@dataclass(frozen=True)
class BlindValidation:
    """Post-induction classification of a held-out reviewed real instance."""

    family_id: str
    training_instance_ids: tuple[str, ...]
    blind_instance_id: str
    blind_graph_ref: GraphContractRef
    proposal_id: str
    proposal_content_sha256: str
    grammar_id: str
    grammar_sha256: str
    classification: str
    observed_backbone_keys: tuple[str, ...]
    observed_motif_region_keys: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    grammar_valid: bool
    blind_instance_used_for_induction: bool = False
    representation_contract: str = "not_imported_or_modified"
    status: str = "pass"
    validation_id: str = ""
    content_sha256: str = ""
    schema_version: str = BLIND_VALIDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BLIND_VALIDATION_SCHEMA_VERSION:
            raise InductionContractError("unsupported blind validation schema")
        if self.classification not in {
            "known_optional_motif_present",
            "known_optional_motif_absent",
            "new_extension_proposed",
        }:
            raise InductionContractError("unsupported blind classification")
        if self.blind_instance_used_for_induction is not False:
            raise InductionContractError("blind instance cannot be used for induction")
        if self.representation_contract != "not_imported_or_modified":
            raise InductionContractError("R3 blind validation cannot depend on representation")
        if self.status != "pass" or self.grammar_valid is not True:
            raise InductionContractError("persisted R3 blind validation must pass")
        _non_empty(self.family_id, "blind_validation.family_id")
        _unique_non_empty(
            self.training_instance_ids, "blind_validation.training_instance_ids"
        )
        if self.blind_instance_id in self.training_instance_ids:
            raise InductionContractError("blind instance appears in induction training set")
        if self.blind_graph_ref.instance_id != self.blind_instance_id:
            raise InductionContractError("blind graph reference instance mismatch")
        for value, path in (
            (self.blind_instance_id, "blind_validation.blind_instance_id"),
            (self.proposal_id, "blind_validation.proposal_id"),
            (self.grammar_id, "blind_validation.grammar_id"),
        ):
            _non_empty(value, path)
        _hash(
            self.proposal_content_sha256,
            "blind_validation.proposal_content_sha256",
        )
        _hash(self.grammar_sha256, "blind_validation.grammar_sha256")
        _unique_non_empty(
            self.observed_backbone_keys,
            "blind_validation.observed_backbone_keys",
        )
        if not self.evidence:
            raise InductionContractError("blind validation requires evidence")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.blind_instance_id}.blind_validation.{content[:16]}"
        _set_or_check_identity(self, "content_sha256", self.content_sha256, content)
        _set_or_check_identity(self, "validation_id", self.validation_id, expected_id)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "training_instance_ids": list(self.training_instance_ids),
            "blind_instance_id": self.blind_instance_id,
            "blind_graph_ref": self.blind_graph_ref.to_mapping(),
            "proposal_id": self.proposal_id,
            "proposal_content_sha256": self.proposal_content_sha256,
            "grammar_id": self.grammar_id,
            "grammar_sha256": self.grammar_sha256,
            "classification": self.classification,
            "observed_backbone_keys": list(self.observed_backbone_keys),
            "observed_motif_region_keys": list(self.observed_motif_region_keys),
            "evidence": [item.to_mapping() for item in self.evidence],
            "grammar_valid": self.grammar_valid,
            "blind_instance_used_for_induction": self.blind_instance_used_for_induction,
            "representation_contract": self.representation_contract,
            "status": self.status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "validation_id": self.validation_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BlindValidation":
        mapping = _mapping(value, "blind_validation")
        required = {
            "schema_version",
            "family_id",
            "training_instance_ids",
            "blind_instance_id",
            "blind_graph_ref",
            "proposal_id",
            "proposal_content_sha256",
            "grammar_id",
            "grammar_sha256",
            "classification",
            "observed_backbone_keys",
            "observed_motif_region_keys",
            "evidence",
            "grammar_valid",
            "blind_instance_used_for_induction",
            "representation_contract",
            "status",
            "validation_id",
            "content_sha256",
        }
        _exact_keys(mapping, required, "blind_validation")
        return cls(
            schema_version=_string(
                mapping["schema_version"], "blind_validation.schema_version"
            ),
            family_id=_string(mapping["family_id"], "blind_validation.family_id"),
            training_instance_ids=_string_tuple(
                mapping["training_instance_ids"],
                "blind_validation.training_instance_ids",
            ),
            blind_instance_id=_string(
                mapping["blind_instance_id"], "blind_validation.blind_instance_id"
            ),
            blind_graph_ref=GraphContractRef.from_mapping(
                _mapping(mapping["blind_graph_ref"], "blind_validation.blind_graph_ref")
            ),
            proposal_id=_string(mapping["proposal_id"], "blind_validation.proposal_id"),
            proposal_content_sha256=_hash(
                mapping["proposal_content_sha256"],
                "blind_validation.proposal_content_sha256",
            ),
            grammar_id=_string(mapping["grammar_id"], "blind_validation.grammar_id"),
            grammar_sha256=_hash(
                mapping["grammar_sha256"], "blind_validation.grammar_sha256"
            ),
            classification=_string(
                mapping["classification"], "blind_validation.classification"
            ),
            observed_backbone_keys=_string_tuple(
                mapping["observed_backbone_keys"],
                "blind_validation.observed_backbone_keys",
            ),
            observed_motif_region_keys=_string_tuple(
                mapping["observed_motif_region_keys"],
                "blind_validation.observed_motif_region_keys",
            ),
            evidence=tuple(
                EvidenceRef.from_mapping(item)
                for item in _mapping_array(mapping["evidence"], "blind_validation.evidence")
            ),
            grammar_valid=_boolean(
                mapping["grammar_valid"], "blind_validation.grammar_valid"
            ),
            blind_instance_used_for_induction=_boolean(
                mapping["blind_instance_used_for_induction"],
                "blind_validation.blind_instance_used_for_induction",
            ),
            representation_contract=_string(
                mapping["representation_contract"],
                "blind_validation.representation_contract",
            ),
            status=_string(mapping["status"], "blind_validation.status"),
            validation_id=_string(
                mapping["validation_id"], "blind_validation.validation_id"
            ),
            content_sha256=_hash(
                mapping["content_sha256"], "blind_validation.content_sha256"
            ),
        )


def load_graph_alignment(path: Path) -> GraphAlignment:
    return GraphAlignment.from_mapping(_read_mapping(path, "graph alignment"))


def load_family_extension_proposal(path: Path) -> FamilyExtensionProposalContract:
    mapping = _read_mapping(path, "family extension proposal")
    if mapping.get("schema_version") == PROPOSAL_SCHEMA_VERSION:
        return FamilyExtensionProposal.from_mapping(mapping)
    if mapping.get("schema_version") == PROPOSAL_SCHEMA_VERSION_V1:
        return FamilyExtensionProposalV1.from_mapping(mapping)
    raise InductionContractError("unsupported family extension proposal schema")


def load_proposal_review(path: Path) -> ProposalReview:
    return ProposalReview.from_mapping(_read_mapping(path, "proposal review"))


def load_grammar_patch(path: Path) -> GrammarPatch:
    return GrammarPatch.from_mapping(_read_mapping(path, "grammar patch"))


def load_patch_application(path: Path) -> GrammarPatchApplication:
    return GrammarPatchApplication.from_mapping(
        _read_mapping(path, "grammar patch application")
    )


def load_blind_validation(path: Path) -> BlindValidation:
    return BlindValidation.from_mapping(_read_mapping(path, "blind validation"))


def _read_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InductionContractError(f"cannot read {label}: {path}") from exc
    return _mapping(value, label)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _set_or_check_identity(instance: Any, field: str, actual: str, expected: str) -> None:
    if actual:
        if actual != expected:
            raise InductionContractError(f"{field} mismatch")
    else:
        object.__setattr__(instance, field, expected)


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InductionContractError(f"{path} must be an object")
    return value


def _mapping_array(value: object, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise InductionContractError(f"{path} must be an array")
    return [_mapping(item, f"{path}[]") for item in value]


def _exact_keys(mapping: Mapping[str, Any], required: set[str], path: str) -> None:
    actual = set(mapping)
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        raise InductionContractError(f"{path} keys mismatch; missing={missing}, extra={extra}")


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InductionContractError(f"{path} must be a non-empty string")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InductionContractError(f"{path} must be an array")
    return tuple(_string(item, f"{path}[]") for item in value)


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InductionContractError(f"{path} must be an integer")
    return value


def _integer_tuple(value: object, path: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise InductionContractError(f"{path} must be an array")
    return tuple(_integer(item, f"{path}[]") for item in value)


def _non_negative_integer(value: object, path: str) -> int:
    result = _integer(value, path)
    if result < 0:
        raise InductionContractError(f"{path} must be non-negative")
    return result


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InductionContractError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise InductionContractError(f"{path} must be finite")
    return result


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise InductionContractError(f"{path} must be boolean")
    return value


def _hash(value: object, path: str) -> str:
    result = _string(value, path)
    if _HASH_RE.fullmatch(result) is None:
        raise InductionContractError(f"{path} must be lowercase SHA-256")
    return result


def _optional_hash(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _hash(value, path)


def _relative_path(value: object, path: str) -> str:
    result = _string(value, path).replace("\\", "/")
    pure = PurePosixPath(result)
    if pure.is_absolute() or _WINDOWS_ABSOLUTE_RE.match(result) or ".." in pure.parts:
        raise InductionContractError(f"{path} must be repository-relative")
    return pure.as_posix()


def _non_empty(value: object, path: str) -> None:
    _string(value, path)


def _unique_non_empty(values: Sequence[str], path: str) -> None:
    if not values:
        raise InductionContractError(f"{path} must be non-empty")
    for item in values:
        _non_empty(item, f"{path}[]")
    if len(values) != len(set(values)):
        raise InductionContractError(f"{path} values must be unique")


def _finite_json(value: object, path: str) -> None:
    try:
        canonical_json_bytes(value)
    except ValueError as exc:
        raise InductionContractError(f"{path} must be finite JSON") from exc


__all__ = [
    "ALIGNMENT_SCHEMA_VERSION",
    "BLIND_VALIDATION_SCHEMA_VERSION",
    "CONFIDENCE_CONTRACT",
    "GRAMMAR_PATCH_SCHEMA_VERSION",
    "INDUCTION_ALGORITHM_VERSION",
    "INDUCTION_ALGORITHM_VERSION_V1",
    "INDUCTION_INPUT_CONTRACT",
    "PATCH_APPLICATION_SCHEMA_VERSION",
    "PROPOSAL_REVIEW_SCHEMA_VERSION",
    "PROPOSAL_SCHEMA_VERSION",
    "PROPOSAL_SCHEMA_VERSION_V1",
    "SCORE_SEMANTICS",
    "AlignmentResidual",
    "BlindValidation",
    "CommonBackboneSlot",
    "FamilyExtensionProposal",
    "FamilyExtensionProposalContract",
    "FamilyExtensionProposalV1",
    "GrammarDiffEntry",
    "GrammarPatch",
    "GrammarPatchApplication",
    "GraphAlignment",
    "GraphContractRef",
    "InductionContractError",
    "InsertionAdjacency",
    "ProposalGraphLocator",
    "ProposalReview",
    "ProposalSupport",
    "RegionMatch",
    "load_blind_validation",
    "load_family_extension_proposal",
    "load_grammar_patch",
    "load_graph_alignment",
    "load_patch_application",
    "load_proposal_review",
]
