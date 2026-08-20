"""Explicit review and grammar-patch workflow for R3 proposals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from ..contracts import (
    NOSE_PAIR_MOTIF_ID,
    EvidenceRef,
    FamilyGrammar,
    InstanceBoundaryGraph,
    MotifInsertionRule,
    ReviewBinding,
    SemanticMotif,
    canonical_json_bytes,
    canonical_sha256,
    validate_graph_against_grammar,
)
from .contracts import (
    FamilyExtensionProposal,
    GrammarDiffEntry,
    GrammarPatch,
    GrammarPatchApplication,
    InductionContractError,
    ProposalReview,
)


@dataclass(frozen=True)
class ReviewOutcome:
    """Pure result of an explicit proposal review decision."""

    grammar: FamilyGrammar
    review: ProposalReview
    patch: GrammarPatch | None
    application: GrammarPatchApplication


def make_proposal_review(
    proposal: FamilyExtensionProposal,
    *,
    decision: str,
    reviewer_id: str,
    rationale: str,
    revision: int = 0,
    evidence: Sequence[EvidenceRef] | None = None,
) -> ProposalReview:
    """Create a separate manual review record without touching a grammar."""

    return ProposalReview(
        proposal_id=proposal.proposal_id,
        proposal_content_sha256=proposal.content_sha256,
        decision=decision,
        reviewer_id=reviewer_id,
        rationale=rationale,
        revision=revision,
        evidence=tuple(evidence or proposal.evidence),
    )


def review_proposal(
    grammar: FamilyGrammar,
    proposal: FamilyExtensionProposal,
    review: ProposalReview,
    *,
    existing_graphs: Sequence[InstanceBoundaryGraph],
) -> ReviewOutcome:
    """Apply only an accepted proposal; all other decisions preserve bytes."""

    _validate_review_binding(proposal, review)
    before_sha = canonical_sha256(grammar.to_mapping())
    if review.decision != "accepted":
        validated_ids, all_valid = _validation_summary(grammar, existing_graphs)
        application = GrammarPatchApplication(
            proposal_id=proposal.proposal_id,
            review_id=review.review_id,
            review_decision=review.decision,
            applied=False,
            patch_id=None,
            patch_content_sha256=None,
            before_grammar_id=grammar.grammar_id,
            before_grammar_sha256=before_sha,
            after_grammar_id=grammar.grammar_id,
            after_grammar_sha256=before_sha,
            grammar_diff=(),
            validated_instance_ids=validated_ids,
            all_instances_valid=all_valid,
        )
        return ReviewOutcome(
            grammar=grammar,
            review=review,
            patch=None,
            application=application,
        )

    patch = build_grammar_patch(grammar, proposal, review)
    updated, application = apply_grammar_patch(
        grammar,
        proposal,
        review,
        patch,
        existing_graphs=existing_graphs,
    )
    return ReviewOutcome(
        grammar=updated,
        review=review,
        patch=patch,
        application=application,
    )


def build_grammar_patch(
    grammar: FamilyGrammar,
    proposal: FamilyExtensionProposal,
    review: ProposalReview,
) -> GrammarPatch:
    """Authorize one deterministic patch only after an accepted manual review."""

    _validate_review_binding(proposal, review)
    if review.decision != "accepted":
        raise InductionContractError("only an accepted proposal can create a grammar patch")
    motif = _proposal_motif(proposal)
    existing = {item.motif_id: item for item in grammar.motifs}.get(motif.motif_id)
    operation = "add_optional_motif" if existing is None else "confirm_optional_motif"
    if existing is not None and not _same_motif_shape(existing, motif):
        raise InductionContractError("proposal conflicts with the existing motif contract")
    target = _patched_grammar(grammar, proposal, review, motif)
    operations = (
        "set_grammar_id",
        operation,
        "append_induction_evidence",
        "replace_review_binding",
        "remove_family_induction_exclusion",
    )
    return GrammarPatch(
        base_grammar_id=grammar.grammar_id,
        base_grammar_sha256=canonical_sha256(grammar.to_mapping()),
        target_grammar_id=target.grammar_id,
        target_grammar_sha256=canonical_sha256(target.to_mapping()),
        proposal_id=proposal.proposal_id,
        proposal_content_sha256=proposal.content_sha256,
        review_id=review.review_id,
        review_content_sha256=review.content_sha256,
        operations=operations,
        proposed_motif=motif,
        audit_evidence=_dedupe_evidence((*proposal.evidence, *review.evidence)),
    )


def apply_grammar_patch(
    grammar: FamilyGrammar,
    proposal: FamilyExtensionProposal,
    review: ProposalReview,
    patch: GrammarPatch,
    *,
    existing_graphs: Sequence[InstanceBoundaryGraph],
) -> tuple[FamilyGrammar, GrammarPatchApplication]:
    """Apply one hash-bound patch and revalidate every existing instance."""

    _validate_review_binding(proposal, review)
    if review.decision != "accepted":
        raise InductionContractError("grammar patch application requires accepted review")
    before_sha = canonical_sha256(grammar.to_mapping())
    if patch.base_grammar_id != grammar.grammar_id or patch.base_grammar_sha256 != before_sha:
        raise InductionContractError("grammar patch base identity mismatch")
    if patch.proposal_id != proposal.proposal_id or (
        patch.proposal_content_sha256 != proposal.content_sha256
    ):
        raise InductionContractError("grammar patch proposal identity mismatch")
    if patch.review_id != review.review_id or (
        patch.review_content_sha256 != review.content_sha256
    ):
        raise InductionContractError("grammar patch review identity mismatch")
    motif = _proposal_motif(proposal)
    if not _same_motif_shape(patch.proposed_motif, motif):
        raise InductionContractError("grammar patch motif differs from proposal")
    updated = _patched_grammar(grammar, proposal, review, patch.proposed_motif)
    after_sha = canonical_sha256(updated.to_mapping())
    if patch.target_grammar_id != updated.grammar_id or (
        patch.target_grammar_sha256 != after_sha
    ):
        raise InductionContractError("grammar patch target identity mismatch")
    _validate_existing_graphs(updated, existing_graphs)
    application = GrammarPatchApplication(
        proposal_id=proposal.proposal_id,
        review_id=review.review_id,
        review_decision=review.decision,
        applied=True,
        patch_id=patch.patch_id,
        patch_content_sha256=patch.content_sha256,
        before_grammar_id=grammar.grammar_id,
        before_grammar_sha256=before_sha,
        after_grammar_id=updated.grammar_id,
        after_grammar_sha256=after_sha,
        grammar_diff=_grammar_diff(grammar, updated),
        validated_instance_ids=tuple(
            sorted(graph.instance_id for graph in existing_graphs)
        ),
        all_instances_valid=True,
    )
    return updated, application


def _patched_grammar(
    grammar: FamilyGrammar,
    proposal: FamilyExtensionProposal,
    review: ProposalReview,
    proposed_motif: SemanticMotif,
) -> FamilyGrammar:
    existing_by_id = {item.motif_id: item for item in grammar.motifs}
    existing = existing_by_id.get(proposed_motif.motif_id)
    if existing is None:
        existing_by_id[proposed_motif.motif_id] = proposed_motif
    else:
        if not _same_motif_shape(existing, proposed_motif):
            raise InductionContractError("accepted proposal conflicts with grammar motif")
        existing_by_id[proposed_motif.motif_id] = replace(
            existing,
            evidence=_dedupe_evidence((*existing.evidence, *proposed_motif.evidence)),
        )
    motifs = tuple(existing_by_id[key] for key in sorted(existing_by_id))
    cardinality_counts: dict[str, int] = {}
    for slot in grammar.backbone_slots:
        cardinality_counts[slot.region_type] = cardinality_counts.get(slot.region_type, 0) + 1
    cardinalities: dict[str, tuple[int, ...]] = {
        region_type: (count,) for region_type, count in cardinality_counts.items()
    }
    for motif in motifs:
        cardinalities[motif.region_type] = motif.allowed_counts
    adjacencies = {
        (left.region_type, right.region_type)
        for left, right in zip(grammar.backbone_slots, grammar.backbone_slots[1:])
    }
    for motif in motifs:
        for rule in motif.insertion_rules:
            before, after = rule.between_region_types
            adjacencies.add((before, motif.region_type))
            adjacencies.add((motif.region_type, after))
    exclusions = set(grammar.exclusions)
    exclusions.discard("family_induction")
    exclusions.update(
        {
            "automatic_proposal_acceptance",
            "raw_pixels_or_step_unsupervised_semantic_discovery",
        }
    )
    return FamilyGrammar(
        grammar_id=f"{grammar.family_id}.family_grammar.r3.v0",
        family_id=grammar.family_id,
        backbone_slots=grammar.backbone_slots,
        motifs=motifs,
        type_cardinality=tuple(
            (region_type, cardinalities[region_type])
            for region_type in sorted(cardinalities)
        ),
        allowed_adjacencies=tuple(sorted(adjacencies)),
        evidence=_dedupe_evidence((*grammar.evidence, *proposal.evidence, *review.evidence)),
        review=ReviewBinding(
            status="accepted",
            item_id=proposal.proposal_id,
            revision=review.revision,
            evidence=review.evidence[0],
        ),
        exclusions=tuple(sorted(exclusions)),
    )


def _proposal_motif(proposal: FamilyExtensionProposal) -> SemanticMotif:
    if proposal.proposal_kind != "optional_motif":
        raise InductionContractError("only an optional-motif proposal can patch this grammar")
    if proposal.motif_id is None or proposal.region_type is None:
        raise InductionContractError("optional motif proposal is incomplete")
    return SemanticMotif(
        motif_id=proposal.motif_id,
        label=(
            "Paired optional nose regions"
            if proposal.motif_id == NOSE_PAIR_MOTIF_ID
            else f"Induced paired optional {proposal.region_type}"
        ),
        region_type=proposal.region_type,
        allowed_counts=proposal.allowed_counts,
        insertion_rules=tuple(
            MotifInsertionRule(
                side=item.side,
                between_region_types=(
                    item.before_region_type,
                    item.after_region_type,
                ),
            )
            for item in proposal.insertion_adjacencies
        ),
        evidence=proposal.evidence,
    )


def _same_motif_shape(left: SemanticMotif, right: SemanticMotif) -> bool:
    left_mapping = left.to_mapping()
    right_mapping = right.to_mapping()
    left_mapping.pop("evidence")
    right_mapping.pop("evidence")
    return canonical_json_bytes(left_mapping) == canonical_json_bytes(right_mapping)


def _validate_review_binding(
    proposal: FamilyExtensionProposal,
    review: ProposalReview,
) -> None:
    if review.proposal_id != proposal.proposal_id or (
        review.proposal_content_sha256 != proposal.content_sha256
    ):
        raise InductionContractError("proposal review identity mismatch")
    if proposal.review_status != "pending" or proposal.grammar_mutation_status != "not_applied":
        raise InductionContractError("review input proposal was already mutated")


def _validate_existing_graphs(
    grammar: FamilyGrammar,
    graphs: Sequence[InstanceBoundaryGraph],
) -> None:
    if not graphs:
        raise InductionContractError("grammar review requires existing instance graphs")
    instance_ids = [graph.instance_id for graph in graphs]
    if len(instance_ids) != len(set(instance_ids)):
        raise InductionContractError("existing instance graphs must be unique")
    for graph in graphs:
        validate_graph_against_grammar(grammar, graph)


def _validation_summary(
    grammar: FamilyGrammar,
    graphs: Sequence[InstanceBoundaryGraph],
) -> tuple[tuple[str, ...], bool]:
    instance_ids = [graph.instance_id for graph in graphs]
    if len(instance_ids) != len(set(instance_ids)):
        raise InductionContractError("existing instance graphs must be unique")
    valid: list[str] = []
    for graph in graphs:
        try:
            validate_graph_against_grammar(grammar, graph)
        except ValueError:
            continue
        valid.append(graph.instance_id)
    return tuple(sorted(valid)), len(valid) == len(graphs)


def _grammar_diff(
    before: FamilyGrammar,
    after: FamilyGrammar,
) -> tuple[GrammarDiffEntry, ...]:
    before_mapping = before.to_mapping()
    after_mapping = after.to_mapping()
    paths = (
        "grammar_id",
        "motifs",
        "type_cardinality",
        "allowed_adjacencies",
        "evidence",
        "review",
        "exclusions",
    )
    values = []
    for key in paths:
        if canonical_json_bytes(before_mapping[key]) == canonical_json_bytes(
            after_mapping[key]
        ):
            continue
        values.append(
            GrammarDiffEntry(
                path=f"#/{key}",
                before=before_mapping[key],
                after=after_mapping[key],
            )
        )
    return tuple(values)


def _dedupe_evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    by_key: dict[bytes, EvidenceRef] = {}
    for item in values:
        by_key.setdefault(canonical_json_bytes(item.to_mapping()), item)
    return tuple(by_key[key] for key in sorted(by_key))


__all__ = [
    "ReviewOutcome",
    "apply_grammar_patch",
    "build_grammar_patch",
    "make_proposal_review",
    "review_proposal",
]
