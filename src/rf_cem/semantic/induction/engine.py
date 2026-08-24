"""Strategy-based R3 motif detection over reviewed semantic graphs only."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol, Sequence

from ..contracts import (
    NOSE_PAIR_MOTIF_ID,
    InstanceBoundaryGraph,
    validate_reviewed_graph_intrinsic,
)
from .alignment import (
    _paired_optional_shape,
    _proposal_evidence,
    _proposal_graph_locators,
    _slug,
)
from .contracts import (
    SCORE_SEMANTICS,
    AlignmentResidual,
    FamilyExtensionProposalV1,
    GraphAlignment,
    InductionContractError,
    InsertionAdjacency,
    ProposalSupport,
)


@dataclass(frozen=True)
class DetectorInput:
    """One residual ontology type and its complete training-graph context."""

    alignment: GraphAlignment
    graphs: tuple[InstanceBoundaryGraph, ...]
    region_type: str
    residuals: tuple[AlignmentResidual, ...]
    present_instance_ids: tuple[str, ...]
    absent_instance_ids: tuple[str, ...]


class MotifDetector(Protocol):
    """Pure detector strategy returning one proposal or declining a shape."""

    detector_id: str
    detector_version: str

    def detect(self, inputs: DetectorInput) -> FamilyExtensionProposalV1 | None:
        """Return a deterministic proposal when this detector recognizes the shape."""


@dataclass(frozen=True)
class PairedOptionalMotifDetector:
    detector_id: str = "paired_optional_motif"
    detector_version: str = "paired_optional_motif.v1"

    def detect(self, inputs: DetectorInput) -> FamilyExtensionProposalV1 | None:
        optional, insertions = _paired_optional_shape(
            inputs.residuals,
            present_ids=inputs.present_instance_ids,
            absent_ids=inputs.absent_instance_ids,
        )
        if not optional:
            return None
        motif_id = (
            NOSE_PAIR_MOTIF_ID
            if inputs.region_type == "NoseRegion"
            else f"motif.{_slug(inputs.region_type)}_pair.induced.v1"
        )
        return _proposal(
            inputs,
            detector=self,
            proposal_kind="optional_motif",
            motif_id=motif_id,
            region_type=inputs.region_type,
            occurrence_rule="paired_optional",
            allowed_counts=(0, 2),
            insertion_adjacencies=insertions,
            alternative_reason=None,
            structural_match=1.0,
            symmetry_assumption_used=True,
            limitations=(
                "structured support is deterministic proposal ranking, not probability",
                "paired symmetry is a detector assumption recorded in support",
                "semantic labels are reviewed inputs, not discovered from raw geometry",
                "proposal requires explicit review before grammar mutation",
            ),
        )


@dataclass(frozen=True)
class SingleOptionalMotifDetector:
    detector_id: str = "single_optional_motif"
    detector_version: str = "single_optional_motif.v1"

    def detect(self, inputs: DetectorInput) -> FamilyExtensionProposalV1 | None:
        optional, insertions = _single_optional_shape(
            inputs.residuals,
            present_ids=inputs.present_instance_ids,
            absent_ids=inputs.absent_instance_ids,
        )
        if not optional:
            return None
        return _proposal(
            inputs,
            detector=self,
            proposal_kind="optional_motif",
            motif_id=f"motif.{_slug(inputs.region_type)}_single.induced.v1",
            region_type=inputs.region_type,
            occurrence_rule="single_optional",
            allowed_counts=(0, 1),
            insertion_adjacencies=insertions,
            alternative_reason=None,
            structural_match=1.0,
            symmetry_assumption_used=False,
            limitations=(
                "structured support is deterministic proposal ranking, not probability",
                "single-sided detector behavior is demonstrated with synthetic reviewed fixtures",
                "proposal requires explicit review before any grammar implementation",
            ),
        )


@dataclass(frozen=True)
class AlternativeTopologyDetector:
    detector_id: str = "alternative_topology_fallback"
    detector_version: str = "alternative_topology_fallback.v1"

    def detect(self, inputs: DetectorInput) -> FamilyExtensionProposalV1:
        return _proposal(
            inputs,
            detector=self,
            proposal_kind="alternative_topology",
            motif_id=None,
            region_type=None,
            occurrence_rule=None,
            allowed_counts=(),
            insertion_adjacencies=(),
            alternative_reason=(
                f"unmatched {inputs.region_type} regions are not recognized by an optional-motif detector"
            ),
            structural_match=0.5,
            symmetry_assumption_used=False,
            limitations=(
                "alternative topology requires additional review and evidence",
                "structured support is deterministic proposal ranking, not probability",
                "no grammar mutation is authorized by this fallback proposal",
            ),
        )


@dataclass(frozen=True)
class FamilyInductionEngine:
    """Apply ordered detector strategies without reading native parameter names."""

    detectors: tuple[MotifDetector, ...] = (
        PairedOptionalMotifDetector(),
        SingleOptionalMotifDetector(),
        AlternativeTopologyDetector(),
    )

    def __post_init__(self) -> None:
        if not self.detectors:
            raise InductionContractError("family induction engine requires detectors")
        detector_ids = [item.detector_id for item in self.detectors]
        if len(detector_ids) != len(set(detector_ids)):
            raise InductionContractError("family induction detector IDs must be unique")
        if not isinstance(self.detectors[-1], AlternativeTopologyDetector):
            raise InductionContractError(
                "family induction detector chain requires an alternative-topology fallback"
            )

    def propose(
        self,
        alignment: GraphAlignment,
        graphs: Sequence[InstanceBoundaryGraph],
    ) -> tuple[FamilyExtensionProposalV1, ...]:
        ordered_graphs = tuple(sorted(graphs, key=lambda item: item.instance_id))
        graph_by_id = {graph.instance_id: graph for graph in ordered_graphs}
        if set(graph_by_id) != set(alignment.source_instance_ids):
            raise InductionContractError(
                "proposal graphs do not match alignment inputs"
            )
        for graph in ordered_graphs:
            validate_reviewed_graph_intrinsic(graph)
            if graph.family_id != alignment.family_id:
                raise InductionContractError("proposal graph family mismatch")

        by_type: dict[str, list[AlignmentResidual]] = defaultdict(list)
        for residual in alignment.residuals:
            by_type[residual.region_type].append(residual)
        proposals: list[FamilyExtensionProposalV1] = []
        for region_type in sorted(by_type):
            residuals = tuple(
                sorted(
                    by_type[region_type],
                    key=lambda item: (item.instance_id, item.region_index),
                )
            )
            present_ids = tuple(sorted({item.instance_id for item in residuals}))
            absent_ids = tuple(
                sorted(set(alignment.source_instance_ids) - set(present_ids))
            )
            inputs = DetectorInput(
                alignment=alignment,
                graphs=ordered_graphs,
                region_type=region_type,
                residuals=residuals,
                present_instance_ids=present_ids,
                absent_instance_ids=absent_ids,
            )
            for detector in self.detectors:
                proposal = detector.detect(inputs)
                if proposal is not None:
                    proposals.append(proposal)
                    break
            else:  # pragma: no cover - constructor requires a fallback
                raise InductionContractError(
                    f"no detector handled residual type {region_type}"
                )
        return tuple(proposals)


def _single_optional_shape(
    residuals: tuple[AlignmentResidual, ...],
    *,
    present_ids: tuple[str, ...],
    absent_ids: tuple[str, ...],
) -> tuple[bool, tuple[InsertionAdjacency, ...]]:
    if not present_ids or not absent_ids:
        return False, ()
    expected: InsertionAdjacency | None = None
    for instance_id in present_ids:
        values = tuple(item for item in residuals if item.instance_id == instance_id)
        if len(values) != 1:
            return False, ()
        residual = values[0]
        if residual.left_anchor_key is None or residual.right_anchor_key is None:
            return False, ()
        left_side, _, left_type = residual.left_anchor_key.partition(":")
        right_side, _, right_type = residual.right_anchor_key.partition(":")
        if left_side != residual.side or right_side != residual.side:
            return False, ()
        candidate = InsertionAdjacency(
            side=residual.side,
            before_region_type=left_type,
            after_region_type=right_type,
        )
        if expected is None:
            expected = candidate
        elif candidate != expected:
            return False, ()
    return (expected is not None), ((expected,) if expected is not None else ())


def _proposal(
    inputs: DetectorInput,
    *,
    detector: MotifDetector,
    proposal_kind: str,
    motif_id: str | None,
    region_type: str | None,
    occurrence_rule: str | None,
    allowed_counts: tuple[int, ...],
    insertion_adjacencies: tuple[InsertionAdjacency, ...],
    alternative_reason: str | None,
    structural_match: float,
    symmetry_assumption_used: bool,
    limitations: tuple[str, ...],
) -> FamilyExtensionProposalV1:
    graph_by_id = {graph.instance_id: graph for graph in inputs.graphs}
    residual_regions = [
        next(
            region
            for region in graph_by_id[item.instance_id].regions
            if region.region_id == item.region_id
        )
        for item in inputs.residuals
    ]
    evidence_completeness = sum(bool(region.evidence) for region in residual_regions) / len(
        residual_regions
    )
    review_coverage = sum(region.review.is_terminal for region in residual_regions) / len(
        residual_regions
    )
    population_size = len(inputs.alignment.source_instance_ids)
    cross_instance_support = (
        2.0
        * min(len(inputs.present_instance_ids), len(inputs.absent_instance_ids))
        / population_size
    )
    support = ProposalSupport(
        structural_match=structural_match,
        evidence_completeness=evidence_completeness,
        review_coverage=review_coverage,
        cross_instance_support=cross_instance_support,
        population_size=population_size,
        symmetry_assumption_used=symmetry_assumption_used,
        detector_id=detector.detector_id,
        detector_version=detector.detector_version,
    )
    score = round(
        0.35 * support.structural_match
        + 0.20 * support.evidence_completeness
        + 0.15 * support.review_coverage
        + 0.20 * support.cross_instance_support
        + 0.10 * min(1.0, support.population_size / 2.0),
        12,
    )
    return FamilyExtensionProposalV1(
        family_id=inputs.alignment.family_id,
        proposal_kind=proposal_kind,
        alignment_id=inputs.alignment.alignment_id,
        alignment_content_sha256=inputs.alignment.content_sha256,
        source_instance_ids=inputs.alignment.source_instance_ids,
        common_backbone_keys=tuple(
            item.semantic_key for item in inputs.alignment.common_backbone
        ),
        motif_id=motif_id,
        region_type=region_type,
        occurrence_rule=occurrence_rule,
        allowed_counts=allowed_counts,
        insertion_adjacencies=insertion_adjacencies,
        present_instance_ids=inputs.present_instance_ids,
        absent_instance_ids=inputs.absent_instance_ids,
        graph_locators=_proposal_graph_locators(
            inputs.alignment,
            residuals=inputs.residuals,
            region_type=inputs.region_type,
        ),
        evidence=_proposal_evidence(
            graph_by_id,
            residuals=inputs.residuals,
            region_type=inputs.region_type,
        ),
        support=support,
        proposal_score=score,
        score_semantics=SCORE_SEMANTICS,
        alternative_reason=alternative_reason,
        limitations=limitations,
    )


__all__ = [
    "AlternativeTopologyDetector",
    "DetectorInput",
    "FamilyInductionEngine",
    "MotifDetector",
    "PairedOptionalMotifDetector",
    "SingleOptionalMotifDetector",
]
