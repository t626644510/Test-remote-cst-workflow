"""Held-out LEReC 704 MHz graph adapter and post-induction validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..contracts import (
    AXIAL_APERTURE_LANDMARK,
    NOSE_PAIR_MOTIF_ID,
    REGION_JUNCTION_LANDMARK,
    SYMMETRY_LANDMARK,
    BoundaryInterface,
    EvidenceRef,
    FamilyGrammar,
    InstanceBoundaryGraph,
    ReviewBinding,
    SemanticLandmark,
    SemanticRegion,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    validate_graph_against_grammar,
)
from .contracts import (
    BlindValidation,
    FamilyExtensionProposalContract,
    GraphContractRef,
    InductionContractError,
)


LEREC704_INSTANCE_ID = "lerec704.wepwi061.arxiv1804-02007"
LEREC704_DESIGN_SHA256 = "d806257972ae33208f5244ed31e1329064d120b82491bc4cb9a9e6afb544ba82"
LEREC704_TEST_SHA256 = "01b6a72aedf32783568cec6e0ab567cd6870d7f4ec7a2e98558d24b790baffab"


@dataclass(frozen=True)
class LEReC704BlindSources:
    """Two primary papers supporting the held-out real instance."""

    repo_root: Path
    ipac2015_design_pdf: Path
    design_and_test_2018_pdf: Path


def build_lerec704_blind_graph(
    sources: LEReC704BlindSources,
    *,
    family_id: str,
) -> InstanceBoundaryGraph:
    """Build the reviewed axisymmetric main-cell topology from primary papers.

    The graph deliberately excludes the non-axisymmetric FPC, tuner, pickup and
    vacuum-pump ports visible on the tested assembly. Those auxiliary features
    are outside the family wall-profile boundary scope.
    """

    root = sources.repo_root.resolve()
    design_path = _source_path(root, sources.ipac2015_design_pdf, "IPAC2015 PDF")
    test_path = _source_path(
        root,
        sources.design_and_test_2018_pdf,
        "2018 design-and-test PDF",
    )
    design_sha = file_sha256(design_path)
    test_sha = file_sha256(test_path)
    if design_sha != LEREC704_DESIGN_SHA256:
        raise InductionContractError("LEReC IPAC2015 source PDF hash mismatch")
    if test_sha != LEREC704_TEST_SHA256:
        raise InductionContractError("LEReC 2018 source PDF hash mismatch")
    design_evidence = EvidenceRef(
        source_kind="jacow_ipac2015_primary_paper",
        source_path=design_path.relative_to(root).as_posix(),
        source_raw_sha256=design_sha,
        locator="page=3;Figure=4(d);text=704_MHz_elliptical_shape_and_two_nose_cones",
        relation="supports_reviewed_axisymmetric_single_cell_nose_topology",
    )
    test_evidence = EvidenceRef(
        source_kind="arxiv_2018_design_and_test_primary_paper",
        source_path=test_path.relative_to(root).as_posix(),
        source_raw_sha256=test_sha,
        locator="pages=1,3,9;Table=1;Figure=2;section=RF_test",
        relation="supports_real_normal_conducting_single_cell_design_and_rf_test",
    )
    evidence = (design_evidence, test_evidence)
    region_specs = (
        ("beam_pipe_left", "BeamPipeRegion", "left", "left beam pipe", None),
        ("iris_left", "IrisRegion", "left", "left aperture throat", None),
        ("nose_left", "NoseRegion", "left", "left reviewed nose cone", NOSE_PAIR_MOTIF_ID),
        ("gap_shaping_left", "GapShapingRegion", "left", "left gap shaping", None),
        ("outer_wall_left", "OuterWallRegion", "left", "left toroidal outer wall", None),
        ("equator", "EquatorRegion", "center", "straight equator crown", None),
        ("outer_wall_right", "OuterWallRegion", "right", "right toroidal outer wall", None),
        ("gap_shaping_right", "GapShapingRegion", "right", "right gap shaping", None),
        ("nose_right", "NoseRegion", "right", "right reviewed nose cone", NOSE_PAIR_MOTIF_ID),
        ("iris_right", "IrisRegion", "right", "right aperture throat", None),
        ("beam_pipe_right", "BeamPipeRegion", "right", "right beam pipe", None),
    )
    regions = tuple(
        SemanticRegion(
            region_id=f"{LEREC704_INSTANCE_ID}.region.{name}",
            region_type=region_type,
            side=side,
            role=role,
            source_feature_ids=(f"wepwi061.figure4d.{name}",),
            motif_id=motif_id,
            evidence=evidence,
            review=_review(
                item_id=f"{LEREC704_INSTANCE_ID}::reviewed_region::{name}",
                evidence=design_evidence,
            ),
        )
        for name, region_type, side, role, motif_id in region_specs
    )
    landmarks: list[SemanticLandmark] = [
        SemanticLandmark(
            landmark_id=f"{LEREC704_INSTANCE_ID}.landmark.aperture_left",
            landmark_type=AXIAL_APERTURE_LANDMARK,
            side="left",
            incident_region_ids=(regions[0].region_id,),
            evidence=evidence,
            review=_review(
                item_id=f"{LEREC704_INSTANCE_ID}::landmark::aperture_left",
                evidence=design_evidence,
            ),
        )
    ]
    interfaces: list[BoundaryInterface] = []
    for index, (left, right) in enumerate(zip(regions, regions[1:])):
        landmark_id = f"{LEREC704_INSTANCE_ID}.landmark.junction.{index:02d}"
        side = _join_side(left.side, right.side)
        landmarks.append(
            SemanticLandmark(
                landmark_id=landmark_id,
                landmark_type=REGION_JUNCTION_LANDMARK,
                side=side,
                incident_region_ids=(left.region_id, right.region_id),
                evidence=evidence,
                review=_review(
                    item_id=f"{LEREC704_INSTANCE_ID}::landmark::junction::{index:02d}",
                    evidence=design_evidence,
                ),
            )
        )
        interfaces.append(
            BoundaryInterface(
                interface_id=f"{LEREC704_INSTANCE_ID}.interface.{index:02d}",
                left_region_id=left.region_id,
                right_region_id=right.region_id,
                landmark_id=landmark_id,
                evidence=evidence,
            )
        )
    landmarks.extend(
        (
            SemanticLandmark(
                landmark_id=f"{LEREC704_INSTANCE_ID}.landmark.symmetry",
                landmark_type=SYMMETRY_LANDMARK,
                side="center",
                incident_region_ids=(regions[5].region_id,),
                evidence=evidence,
                review=_review(
                    item_id=f"{LEREC704_INSTANCE_ID}::landmark::symmetry",
                    evidence=design_evidence,
                ),
            ),
            SemanticLandmark(
                landmark_id=f"{LEREC704_INSTANCE_ID}.landmark.aperture_right",
                landmark_type=AXIAL_APERTURE_LANDMARK,
                side="right",
                incident_region_ids=(regions[-1].region_id,),
                evidence=evidence,
                review=_review(
                    item_id=f"{LEREC704_INSTANCE_ID}::landmark::aperture_right",
                    evidence=design_evidence,
                ),
            ),
        )
    )
    return InstanceBoundaryGraph(
        graph_id=f"{LEREC704_INSTANCE_ID}.boundary_graph.v0",
        family_id=family_id,
        instance_id=LEREC704_INSTANCE_ID,
        regions=regions,
        landmarks=tuple(landmarks),
        interfaces=tuple(interfaces),
        active_motif_ids=(NOSE_PAIR_MOTIF_ID,),
        nose_presence="present",
        nose_evidence=evidence,
        source_bindings=evidence,
        exclusions=(
            "non_axisymmetric_fpc_tuner_pickup_and_pump_ports",
            "geometry_parameter_vector",
            "compiled_boundary_representation",
            "live_cst_execution",
            "rf_physical_acceptance",
        ),
    )


def blind_graph_ref(
    repo_root: Path,
    graph_path: Path,
    graph: InstanceBoundaryGraph,
) -> GraphContractRef:
    """Create a strict reference after the blind graph artifact is materialized."""

    root = repo_root.resolve()
    path = graph_path if graph_path.is_absolute() else root / graph_path
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise InductionContractError("blind graph artifact must be inside repository") from exc
    if not resolved.is_file():
        raise InductionContractError("blind graph artifact is missing")
    return GraphContractRef(
        instance_id=graph.instance_id,
        graph_id=graph.graph_id,
        source_path=relative,
        source_raw_sha256=file_sha256(resolved),
        contract_sha256=canonical_sha256(graph.to_mapping()),
    )


def validate_blind_instance(
    grammar: FamilyGrammar,
    proposal: FamilyExtensionProposalContract,
    blind_graph: InstanceBoundaryGraph,
    graph_ref: GraphContractRef,
) -> BlindValidation:
    """Classify a held-out graph only after induction and explicit patching."""

    training_ids = tuple(sorted(proposal.source_instance_ids))
    if blind_graph.instance_id in training_ids:
        raise InductionContractError("blind graph was present in the induction inputs")
    if proposal.proposal_kind != "optional_motif" or proposal.region_type is None:
        raise InductionContractError("blind validation requires an accepted optional motif")
    validate_graph_against_grammar(grammar, blind_graph)
    motif_types = {item.region_type for item in grammar.motifs}
    observed_backbone = tuple(
        region.semantic_key
        for region in blind_graph.regions
        if region.region_type not in motif_types
    )
    if observed_backbone != proposal.common_backbone_keys:
        raise InductionContractError("blind graph backbone differs from induced backbone")
    observed_motif = tuple(
        region.semantic_key
        for region in blind_graph.regions
        if region.region_type == proposal.region_type
    )
    if len(observed_motif) == 2:
        classification = "known_optional_motif_present"
    elif not observed_motif:
        classification = "known_optional_motif_absent"
    else:
        classification = "new_extension_proposed"
    return BlindValidation(
        family_id=blind_graph.family_id,
        training_instance_ids=training_ids,
        blind_instance_id=blind_graph.instance_id,
        blind_graph_ref=graph_ref,
        proposal_id=proposal.proposal_id,
        proposal_content_sha256=proposal.content_sha256,
        grammar_id=grammar.grammar_id,
        grammar_sha256=canonical_sha256(grammar.to_mapping()),
        classification=classification,
        observed_backbone_keys=observed_backbone,
        observed_motif_region_keys=observed_motif,
        evidence=_dedupe_evidence(
            (*blind_graph.source_bindings, *blind_graph.nose_evidence)
        ),
        grammar_valid=True,
    )


def _review(*, item_id: str, evidence: EvidenceRef) -> ReviewBinding:
    return ReviewBinding(
        status="confirmed",
        item_id=item_id,
        revision=0,
        evidence=evidence,
    )


def _join_side(left: str, right: str) -> str:
    if right == "center":
        return "left"
    if left == "center":
        return "right"
    if left != right:
        raise InductionContractError("unexpected cross-side non-center join")
    return left


def _source_path(root: Path, value: Path, label: str) -> Path:
    path = value if value.is_absolute() else root / value
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise InductionContractError(f"{label} must be inside repository") from exc
    if not resolved.is_file():
        raise InductionContractError(f"{label} is missing: {resolved}")
    return resolved


def _dedupe_evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    by_key: dict[bytes, EvidenceRef] = {}
    for item in values:
        by_key.setdefault(canonical_json_bytes(item.to_mapping()), item)
    return tuple(by_key[key] for key in sorted(by_key))


__all__ = [
    "LEREC704_DESIGN_SHA256",
    "LEREC704_INSTANCE_ID",
    "LEREC704_TEST_SHA256",
    "LEReC704BlindSources",
    "blind_graph_ref",
    "build_lerec704_blind_graph",
    "validate_blind_instance",
]
