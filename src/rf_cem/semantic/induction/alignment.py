"""Parameter-name-independent graph alignment and family proposals."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Iterable, Sequence

from ..contracts import (
    NOSE_PAIR_MOTIF_ID,
    EvidenceRef,
    InstanceBoundaryGraph,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    validate_reviewed_graph_intrinsic,
)
from .contracts import (
    CONFIDENCE_CONTRACT,
    AlignmentResidual,
    CommonBackboneSlot,
    FamilyExtensionProposal,
    FamilyExtensionProposalContract,
    GraphAlignment,
    GraphContractRef,
    InductionContractError,
    InsertionAdjacency,
    ProposalGraphLocator,
    RegionMatch,
)


def graph_contract_ref(
    repo_root: Path,
    source_path: Path,
    graph: InstanceBoundaryGraph,
) -> GraphContractRef:
    """Bind one loaded graph to a repository-relative source and two hashes."""

    root = repo_root.resolve()
    path = source_path if source_path.is_absolute() else root / source_path
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise InductionContractError("graph source must be inside the repository") from exc
    if not resolved.is_file():
        raise InductionContractError(f"graph source is missing: {resolved}")
    return GraphContractRef(
        instance_id=graph.instance_id,
        graph_id=graph.graph_id,
        source_path=relative,
        source_raw_sha256=file_sha256(resolved),
        contract_sha256=canonical_sha256(graph.to_mapping()),
    )


def align_reviewed_graphs(
    graphs: Sequence[InstanceBoundaryGraph],
    graph_refs: Sequence[GraphContractRef],
) -> GraphAlignment:
    """Align reviewed graphs using only ordered semantic side/type tokens.

    Geometry values, parameter payloads, source feature names and roles are not
    read by this algorithm. Input pairs are sorted by instance ID so callers do
    not influence the deterministic result through iteration order.
    """

    if len(graphs) != len(graph_refs) or len(graphs) < 2:
        raise InductionContractError("alignment requires matching graph/ref inputs")
    pairs = sorted(zip(graphs, graph_refs), key=lambda item: item[0].instance_id)
    ordered_graphs = tuple(item[0] for item in pairs)
    ordered_refs = tuple(item[1] for item in pairs)
    family_ids = {graph.family_id for graph in ordered_graphs}
    if len(family_ids) != 1:
        raise InductionContractError("alignment graphs must belong to one family")
    for graph, ref in zip(ordered_graphs, ordered_refs):
        validate_reviewed_graph_intrinsic(graph)
        if ref.instance_id != graph.instance_id or ref.graph_id != graph.graph_id:
            raise InductionContractError("alignment graph reference identity mismatch")
        if ref.contract_sha256 != canonical_sha256(graph.to_mapping()):
            raise InductionContractError("alignment graph reference contract hash mismatch")

    token_sequences = tuple(
        tuple((region.side, region.region_type) for region in graph.regions)
        for graph in ordered_graphs
    )
    common = token_sequences[0]
    for sequence in token_sequences[1:]:
        common = _longest_common_subsequence(common, sequence)
    if len(common) < 3:
        raise InductionContractError("reviewed graphs do not share a usable backbone")

    indexes_by_graph: dict[str, tuple[int, ...]] = {}
    for graph, sequence in zip(ordered_graphs, token_sequences):
        indexes_by_graph[graph.instance_id] = _locate_subsequence(sequence, common)

    slots: list[CommonBackboneSlot] = []
    for slot_index, token in enumerate(common):
        matches = tuple(
            RegionMatch(
                instance_id=graph.instance_id,
                region_id=graph.regions[indexes_by_graph[graph.instance_id][slot_index]].region_id,
                region_index=indexes_by_graph[graph.instance_id][slot_index],
            )
            for graph in ordered_graphs
        )
        slots.append(
            CommonBackboneSlot(
                slot_index=slot_index,
                semantic_key=_semantic_key(token),
                side=token[0],
                region_type=token[1],
                matches=matches,
            )
        )

    residuals: list[AlignmentResidual] = []
    common_keys = tuple(_semantic_key(token) for token in common)
    for graph in ordered_graphs:
        matched_indexes = set(indexes_by_graph[graph.instance_id])
        anchor_by_index = {
            graph_index: common_index
            for common_index, graph_index in enumerate(indexes_by_graph[graph.instance_id])
        }
        for region_index, region in enumerate(graph.regions):
            if region_index in matched_indexes:
                continue
            left_common_indexes = [
                common_index
                for graph_index, common_index in anchor_by_index.items()
                if graph_index < region_index
            ]
            right_common_indexes = [
                common_index
                for graph_index, common_index in anchor_by_index.items()
                if graph_index > region_index
            ]
            left_anchor = common_keys[max(left_common_indexes)] if left_common_indexes else None
            right_anchor = common_keys[min(right_common_indexes)] if right_common_indexes else None
            residuals.append(
                AlignmentResidual(
                    instance_id=graph.instance_id,
                    graph_id=graph.graph_id,
                    region_id=region.region_id,
                    region_index=region_index,
                    semantic_key=region.semantic_key,
                    side=region.side,
                    region_type=region.region_type,
                    left_anchor_key=left_anchor,
                    right_anchor_key=right_anchor,
                    graph_locator=f"#/regions/{region_index}",
                )
            )

    return GraphAlignment(
        family_id=ordered_graphs[0].family_id,
        graph_refs=ordered_refs,
        common_backbone=tuple(slots),
        residuals=tuple(
            sorted(
                residuals,
                key=lambda item: (item.instance_id, item.region_index, item.region_id),
            )
        ),
    )


def propose_family_extensions(
    alignment: GraphAlignment,
    graphs: Sequence[InstanceBoundaryGraph],
) -> tuple[FamilyExtensionProposal, ...]:
    """Propose optional motifs or explain unmatched alternative topology."""

    graph_by_id = {graph.instance_id: graph for graph in graphs}
    if set(graph_by_id) != set(alignment.source_instance_ids):
        raise InductionContractError("proposal graphs do not match alignment inputs")
    if any(graph.family_id != alignment.family_id for graph in graphs):
        raise InductionContractError("proposal graph family mismatch")
    by_type: dict[str, list[AlignmentResidual]] = defaultdict(list)
    for residual in alignment.residuals:
        by_type[residual.region_type].append(residual)
    proposals: list[FamilyExtensionProposal] = []
    for region_type in sorted(by_type):
        residuals = tuple(
            sorted(
                by_type[region_type],
                key=lambda item: (item.instance_id, item.region_index),
            )
        )
        present_ids = tuple(
            sorted({item.instance_id for item in residuals})
        )
        absent_ids = tuple(
            sorted(set(alignment.source_instance_ids) - set(present_ids))
        )
        optional, insertions = _paired_optional_shape(
            residuals,
            present_ids=present_ids,
            absent_ids=absent_ids,
        )
        graph_locators = _proposal_graph_locators(
            alignment,
            residuals=residuals,
            region_type=region_type,
        )
        evidence = _proposal_evidence(
            graph_by_id,
            residuals=residuals,
            region_type=region_type,
        )
        if optional:
            motif_id = (
                NOSE_PAIR_MOTIF_ID
                if region_type == "NoseRegion"
                else f"motif.{_slug(region_type)}_pair.induced.v0"
            )
            proposals.append(
                FamilyExtensionProposal(
                    family_id=alignment.family_id,
                    proposal_kind="optional_motif",
                    alignment_id=alignment.alignment_id,
                    alignment_content_sha256=alignment.content_sha256,
                    source_instance_ids=alignment.source_instance_ids,
                    common_backbone_keys=tuple(
                        item.semantic_key for item in alignment.common_backbone
                    ),
                    motif_id=motif_id,
                    region_type=region_type,
                    occurrence_rule="paired_optional",
                    allowed_counts=(0, 2),
                    insertion_adjacencies=insertions,
                    present_instance_ids=present_ids,
                    absent_instance_ids=absent_ids,
                    graph_locators=graph_locators,
                    evidence=evidence,
                    confidence=_optional_confidence(graph_by_id, residuals),
                    confidence_basis=CONFIDENCE_CONTRACT,
                    alternative_reason=None,
                    limitations=(
                        "two-instance structural evidence is not a statistical population estimate",
                        "semantic region labels are reviewed inputs, not discovered from raw pixels or STEP",
                        "proposal requires a separate explicit review before grammar mutation",
                    ),
                )
            )
        else:
            proposals.append(
                FamilyExtensionProposal(
                    family_id=alignment.family_id,
                    proposal_kind="alternative_topology",
                    alignment_id=alignment.alignment_id,
                    alignment_content_sha256=alignment.content_sha256,
                    source_instance_ids=alignment.source_instance_ids,
                    common_backbone_keys=tuple(
                        item.semantic_key for item in alignment.common_backbone
                    ),
                    motif_id=None,
                    region_type=None,
                    occurrence_rule=None,
                    allowed_counts=(),
                    insertion_adjacencies=(),
                    present_instance_ids=present_ids,
                    absent_instance_ids=absent_ids,
                    graph_locators=graph_locators,
                    evidence=evidence,
                    confidence=0.60,
                    confidence_basis=CONFIDENCE_CONTRACT,
                    alternative_reason=(
                        f"unmatched {region_type} regions do not form one mirrored paired-optional insertion"
                    ),
                    limitations=(
                        "alternative topology requires additional review and evidence",
                        "no grammar mutation is authorized by this proposal",
                    ),
                )
            )
    return tuple(proposals)


def select_optional_motif_proposal(
    proposals: Iterable[FamilyExtensionProposalContract],
    *,
    region_type: str,
) -> FamilyExtensionProposalContract:
    """Return exactly one optional proposal for a requested ontology type."""

    matches = [
        item
        for item in proposals
        if item.proposal_kind == "optional_motif" and item.region_type == region_type
    ]
    if len(matches) != 1:
        raise InductionContractError(
            f"expected one optional {region_type} proposal, found {len(matches)}"
        )
    return matches[0]


def _longest_common_subsequence(
    left: tuple[tuple[str, str], ...],
    right: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    rows = len(left) + 1
    columns = len(right) + 1
    table: list[list[tuple[tuple[str, str], ...]]] = [
        [tuple() for _ in range(columns)] for _ in range(rows)
    ]
    for left_index in range(1, rows):
        for right_index in range(1, columns):
            if left[left_index - 1] == right[right_index - 1]:
                table[left_index][right_index] = (
                    *table[left_index - 1][right_index - 1],
                    left[left_index - 1],
                )
            else:
                above = table[left_index - 1][right_index]
                before = table[left_index][right_index - 1]
                if len(above) > len(before):
                    table[left_index][right_index] = above
                elif len(before) > len(above):
                    table[left_index][right_index] = before
                else:
                    table[left_index][right_index] = min(above, before)
    return table[-1][-1]


def _locate_subsequence(
    sequence: tuple[tuple[str, str], ...],
    subsequence: tuple[tuple[str, str], ...],
) -> tuple[int, ...]:
    values: list[int] = []
    cursor = 0
    for token in subsequence:
        for index in range(cursor, len(sequence)):
            if sequence[index] == token:
                values.append(index)
                cursor = index + 1
                break
        else:
            raise InductionContractError("common sequence cannot be located in graph")
    return tuple(values)


def _paired_optional_shape(
    residuals: tuple[AlignmentResidual, ...],
    *,
    present_ids: tuple[str, ...],
    absent_ids: tuple[str, ...],
) -> tuple[bool, tuple[InsertionAdjacency, ...]]:
    if not present_ids or not absent_ids:
        return False, ()
    expected: tuple[InsertionAdjacency, ...] | None = None
    for instance_id in present_ids:
        values = tuple(item for item in residuals if item.instance_id == instance_id)
        if len(values) != 2 or {item.side for item in values} != {"left", "right"}:
            return False, ()
        insertions: list[InsertionAdjacency] = []
        for item in sorted(values, key=lambda residual: residual.side):
            if item.left_anchor_key is None or item.right_anchor_key is None:
                return False, ()
            left_side, left_type = _split_semantic_key(item.left_anchor_key)
            right_side, right_type = _split_semantic_key(item.right_anchor_key)
            if left_side != item.side or right_side != item.side:
                return False, ()
            insertions.append(
                InsertionAdjacency(
                    side=item.side,
                    before_region_type=left_type,
                    after_region_type=right_type,
                )
            )
        candidate = tuple(sorted(insertions, key=lambda item: item.side))
        if expected is None:
            expected = candidate
        elif candidate != expected:
            return False, ()
    return (expected is not None), (expected or ())


def _proposal_graph_locators(
    alignment: GraphAlignment,
    *,
    residuals: tuple[AlignmentResidual, ...],
    region_type: str,
) -> tuple[ProposalGraphLocator, ...]:
    ref_by_id = {item.instance_id: item for item in alignment.graph_refs}
    values: list[ProposalGraphLocator] = []
    for instance_id in alignment.source_instance_ids:
        ref = ref_by_id[instance_id]
        instance_residuals = [
            item for item in residuals if item.instance_id == instance_id
        ]
        if instance_residuals:
            for residual in instance_residuals:
                values.append(
                    ProposalGraphLocator(
                        instance_id=instance_id,
                        graph_id=ref.graph_id,
                        source_path=ref.source_path,
                        source_raw_sha256=ref.source_raw_sha256,
                        contract_sha256=ref.contract_sha256,
                        locator=residual.graph_locator,
                        relation=f"supports_presence_of_{region_type}",
                    )
                )
        else:
            values.append(
                ProposalGraphLocator(
                    instance_id=instance_id,
                    graph_id=ref.graph_id,
                    source_path=ref.source_path,
                    source_raw_sha256=ref.source_raw_sha256,
                    contract_sha256=ref.contract_sha256,
                    locator="#/regions",
                    relation=f"supports_zero_occurrence_of_{region_type}",
                )
            )
    return tuple(values)


def _proposal_evidence(
    graph_by_id: dict[str, InstanceBoundaryGraph],
    *,
    residuals: tuple[AlignmentResidual, ...],
    region_type: str,
) -> tuple[EvidenceRef, ...]:
    values: list[EvidenceRef] = []
    residual_ids = {item.region_id for item in residuals}
    for graph in sorted(graph_by_id.values(), key=lambda item: item.instance_id):
        for region in graph.regions:
            if region.region_id in residual_ids:
                values.extend(region.evidence)
        if region_type == "NoseRegion":
            values.extend(graph.nose_evidence)
        else:
            values.extend(graph.source_bindings)
    return _dedupe_evidence(values)


def _optional_confidence(
    graph_by_id: dict[str, InstanceBoundaryGraph],
    residuals: tuple[AlignmentResidual, ...],
) -> float:
    regions = {
        region.region_id: region
        for graph in graph_by_id.values()
        for region in graph.regions
    }
    terminal = all(regions[item.region_id].review.is_terminal for item in residuals)
    evidence_bound = all(regions[item.region_id].evidence for item in residuals)
    score = 0.75
    score += 0.10  # mirrored pair and present/absent contrast passed
    score += 0.05 if terminal else 0.0
    score += 0.05 if evidence_bound else 0.0
    return min(score, 0.95)


def _dedupe_evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    by_key: dict[bytes, EvidenceRef] = {}
    for item in values:
        by_key.setdefault(canonical_json_bytes(item.to_mapping()), item)
    return tuple(by_key[key] for key in sorted(by_key))


def _semantic_key(token: tuple[str, str]) -> str:
    return f"{token[0]}:{token[1]}"


def _split_semantic_key(value: str) -> tuple[str, str]:
    side, separator, region_type = value.partition(":")
    if not separator or not side or not region_type:
        raise InductionContractError(f"invalid semantic key: {value}")
    return side, region_type


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


__all__ = [
    "align_reviewed_graphs",
    "graph_contract_ref",
    "propose_family_extensions",
    "select_optional_motif_proposal",
]
