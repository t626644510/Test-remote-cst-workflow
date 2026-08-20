"""No-CST R3 graph-induction, review, patch, and blind-validation gates."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile

import pytest

from rf_cem.semantic import (
    BoundaryInterface,
    EvidenceRef,
    FamilyGrammar,
    GrammarSlot,
    InstanceBoundaryGraph,
    MotifInsertionRule,
    ReviewBinding,
    SemanticLandmark,
    SemanticMotif,
    SemanticRegion,
    validate_graph_against_grammar,
)
from rf_cem.semantic.contracts import (
    NOSE_PAIR_MOTIF_ID,
    canonical_json_bytes,
    canonical_sha256,
)
from rf_cem.semantic.induction import (
    BlindValidation,
    FamilyExtensionProposal,
    GraphAlignment,
    GraphContractRef,
    InductionContractError,
    MANIFEST_FILE,
    ProposalReview,
    PROPOSAL_FILE,
    R3SourceSet,
    align_reviewed_graphs,
    load_r3_bundle,
    make_proposal_review,
    propose_family_extensions,
    review_proposal,
    select_optional_motif_proposal,
    validate_blind_instance,
    write_r3_bundle,
)
from rf_cem.workbench import (
    RegistryReader,
    WorkbenchIndexError,
    WorkbenchServer,
    WorkbenchSourceSet,
    rebuild_workbench,
)


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
FAMILY_ID = "fixture.nc_axisymmetric_single_cell"
BACKBONE = (
    ("beam_pipe_left", "BeamPipeRegion", "left"),
    ("iris_left", "IrisRegion", "left"),
    ("gap_shaping_left", "GapShapingRegion", "left"),
    ("outer_wall_left", "OuterWallRegion", "left"),
    ("equator", "EquatorRegion", "center"),
    ("outer_wall_right", "OuterWallRegion", "right"),
    ("gap_shaping_right", "GapShapingRegion", "right"),
    ("iris_right", "IrisRegion", "right"),
    ("beam_pipe_right", "BeamPipeRegion", "right"),
)


def test_alignment_uses_semantic_tokens_and_proposes_optional_nose() -> None:
    absent = _graph("fixture.absent", nose_sides=(), feature_prefix="alpha_parameter")
    present = _graph(
        "fixture.present",
        nose_sides=("left", "right"),
        feature_prefix="unrelated_native_name",
    )
    alignment, proposal = _induce(absent, present)
    assert GraphAlignment.from_mapping(alignment.to_mapping()) == alignment
    assert FamilyExtensionProposal.from_mapping(proposal.to_mapping()) == proposal
    assert alignment.parameter_names_read is False
    assert alignment.source_instance_ids == ("fixture.absent", "fixture.present")
    assert [item.semantic_key for item in alignment.common_backbone] == [
        f"{side}:{region_type}" for _, region_type, side in BACKBONE
    ]
    assert [(item.side, item.region_type) for item in alignment.residuals] == [
        ("left", "NoseRegion"),
        ("right", "NoseRegion"),
    ]
    assert proposal.proposal_kind == "optional_motif"
    assert proposal.motif_id == NOSE_PAIR_MOTIF_ID
    assert proposal.present_instance_ids == ("fixture.present",)
    assert proposal.absent_instance_ids == ("fixture.absent",)
    assert proposal.allowed_counts == (0, 2)
    assert {item.side for item in proposal.insertion_adjacencies} == {"left", "right"}
    assert proposal.review_status == "pending"
    assert proposal.grammar_mutation_status == "not_applied"
    assert proposal.confidence == pytest.approx(0.95)


def test_alignment_is_invariant_to_roles_and_source_feature_names() -> None:
    first = _graph("fixture.a", nose_sides=(), feature_prefix="L_cell_mm")
    second = _graph(
        "fixture.b",
        nose_sides=("left", "right"),
        feature_prefix="radius_equator_native",
    )
    alignment, proposal = _induce(first, second)
    changed_graphs = tuple(_rename_nonsemantic_fields(graph) for graph in (first, second))
    changed_alignment, changed_proposal = _induce(*changed_graphs)
    assert [item.semantic_key for item in changed_alignment.common_backbone] == [
        item.semantic_key for item in alignment.common_backbone
    ]
    assert [
        (item.side, item.region_type, item.left_anchor_key, item.right_anchor_key)
        for item in changed_alignment.residuals
    ] == [
        (item.side, item.region_type, item.left_anchor_key, item.right_anchor_key)
        for item in alignment.residuals
    ]
    assert changed_proposal.insertion_adjacencies == proposal.insertion_adjacencies
    assert changed_proposal.allowed_counts == proposal.allowed_counts
    encoded = canonical_json_bytes(changed_alignment.to_mapping())
    assert b"replacement_parameter" not in encoded
    assert b"changed role" not in encoded


@pytest.mark.parametrize("decision", ["rejected", "needs_evidence"])
def test_rejected_or_needs_evidence_review_preserves_grammar(decision: str) -> None:
    absent = _graph("fixture.absent", nose_sides=(), feature_prefix="a")
    present = _graph(
        "fixture.present", nose_sides=("left", "right"), feature_prefix="b"
    )
    _, proposal = _induce(absent, present)
    grammar = _grammar(include_nose=True)
    before = canonical_json_bytes(grammar.to_mapping())
    review = make_proposal_review(
        proposal,
        decision=decision,
        reviewer_id="fixture.reviewer",
        rationale="Exercise the explicit non-acceptance path.",
    )
    outcome = review_proposal(
        grammar,
        proposal,
        review,
        existing_graphs=(absent, present),
    )
    assert outcome.grammar is grammar
    assert canonical_json_bytes(outcome.grammar.to_mapping()) == before
    assert outcome.patch is None
    assert outcome.application.applied is False
    assert outcome.application.before_grammar_sha256 == (
        outcome.application.after_grammar_sha256
    )
    assert outcome.application.grammar_diff == ()


def test_accepted_review_adds_motif_by_explicit_patch_and_revalidates() -> None:
    absent = _graph("fixture.absent", nose_sides=(), feature_prefix="a")
    present = _graph(
        "fixture.present", nose_sides=("left", "right"), feature_prefix="b"
    )
    _, proposal = _induce(absent, present)
    grammar = _grammar(include_nose=False)
    validate_graph_against_grammar(grammar, absent)
    with pytest.raises(ValueError):
        validate_graph_against_grammar(grammar, present)
    before_hash = canonical_sha256(grammar.to_mapping())
    review = make_proposal_review(
        proposal,
        decision="accepted",
        reviewer_id="fixture.human-reviewer",
        rationale="Reviewed graph evidence supports a paired optional nose motif.",
    )
    outcome = review_proposal(
        grammar,
        proposal,
        review,
        existing_graphs=(absent, present),
    )
    assert outcome.patch is not None
    assert "add_optional_motif" in outcome.patch.operations
    assert outcome.application.applied is True
    assert outcome.application.all_instances_valid is True
    assert set(outcome.application.validated_instance_ids) == {
        absent.instance_id,
        present.instance_id,
    }
    assert canonical_sha256(outcome.grammar.to_mapping()) != before_hash
    assert "family_induction" not in outcome.grammar.exclusions
    assert "automatic_proposal_acceptance" in outcome.grammar.exclusions
    validate_graph_against_grammar(outcome.grammar, absent)
    validate_graph_against_grammar(outcome.grammar, present)


def test_accepted_review_confirms_existing_motif_with_auditable_diff() -> None:
    absent = _graph("fixture.absent", nose_sides=(), feature_prefix="a")
    present = _graph(
        "fixture.present", nose_sides=("left", "right"), feature_prefix="b"
    )
    _, proposal = _induce(absent, present)
    grammar = _grammar(include_nose=True)
    review = make_proposal_review(
        proposal,
        decision="accepted",
        reviewer_id="fixture.human-reviewer",
        rationale="Confirm the existing manually encoded motif using induction evidence.",
    )
    outcome = review_proposal(
        grammar,
        proposal,
        review,
        existing_graphs=(absent, present),
    )
    assert outcome.patch is not None
    assert "confirm_optional_motif" in outcome.patch.operations
    assert outcome.grammar.grammar_id.endswith("family_grammar.r3.v0")
    assert {item.path for item in outcome.application.grammar_diff}.issuperset(
        {"#/grammar_id", "#/evidence", "#/review", "#/exclusions"}
    )


def test_unpaired_residual_becomes_alternative_topology_proposal() -> None:
    absent = _graph("fixture.absent", nose_sides=(), feature_prefix="a")
    asymmetric = _graph(
        "fixture.asymmetric", nose_sides=("left",), feature_prefix="b"
    )
    refs = (_graph_ref(absent), _graph_ref(asymmetric))
    alignment = align_reviewed_graphs((absent, asymmetric), refs)
    proposals = propose_family_extensions(alignment, (absent, asymmetric))
    assert len(proposals) == 1
    assert proposals[0].proposal_kind == "alternative_topology"
    assert proposals[0].alternative_reason is not None
    assert proposals[0].grammar_mutation_status == "not_applied"


def test_blind_fixture_is_classified_after_training_and_never_imports_representation() -> None:
    absent = _graph("fixture.train.absent", nose_sides=(), feature_prefix="train_a")
    present = _graph(
        "fixture.train.present",
        nose_sides=("left", "right"),
        feature_prefix="train_b",
    )
    _, proposal = _induce(absent, present)
    review = make_proposal_review(
        proposal,
        decision="accepted",
        reviewer_id="fixture.reviewer",
        rationale="Accept the training-only proposal before blind classification.",
    )
    outcome = review_proposal(
        _grammar(include_nose=False),
        proposal,
        review,
        existing_graphs=(absent, present),
    )
    blind = _graph(
        "fixture.blind.realish",
        nose_sides=("left", "right"),
        feature_prefix="held_out_unseen_native_labels",
    )
    validation = validate_blind_instance(
        outcome.grammar,
        proposal,
        blind,
        _graph_ref(blind),
    )
    assert BlindValidation.from_mapping(validation.to_mapping()) == validation
    assert validation.classification == "known_optional_motif_present"
    assert validation.blind_instance_used_for_induction is False
    assert validation.representation_contract == "not_imported_or_modified"
    assert blind.instance_id not in validation.training_instance_ids


def test_contracts_fail_closed_on_identity_or_nonfinite_tamper() -> None:
    absent = _graph("fixture.absent", nose_sides=(), feature_prefix="a")
    present = _graph(
        "fixture.present", nose_sides=("left", "right"), feature_prefix="b"
    )
    alignment, proposal = _induce(absent, present)
    tampered = alignment.to_mapping()
    tampered["parameter_names_read"] = True
    with pytest.raises(InductionContractError):
        GraphAlignment.from_mapping(tampered)
    proposal_mapping = proposal.to_mapping()
    proposal_mapping["confidence"] = float("nan")
    with pytest.raises(InductionContractError):
        FamilyExtensionProposal.from_mapping(proposal_mapping)
    review = make_proposal_review(
        proposal,
        decision="accepted",
        reviewer_id="fixture.reviewer",
        rationale="Identity tamper test.",
    )
    review_mapping = review.to_mapping()
    review_mapping["proposal_content_sha256"] = "0" * 64
    with pytest.raises(InductionContractError):
        ProposalReview.from_mapping(review_mapping)


def test_real_r3_bundle_is_reproducible_and_loadable() -> None:
    sources = _real_source_set()
    if sources is None:
        pytest.skip("ignored R1 graphs and LEReC primary PDFs are not materialized")
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="r3-a-", dir=scratch) as first_dir:
            with tempfile.TemporaryDirectory(prefix="r3-b-", dir=scratch) as second_dir:
                first = write_r3_bundle(
                    sources,
                    Path(first_dir),
                    review_decision="accepted",
                    reviewer_id="test.explicit-reviewer",
                    review_rationale="Deterministic reviewed acceptance for the real R3 proof.",
                )
                second = write_r3_bundle(
                    sources,
                    Path(second_dir),
                    review_decision="accepted",
                    reviewer_id="test.explicit-reviewer",
                    review_rationale="Deterministic reviewed acceptance for the real R3 proof.",
                )
                assert first.bundle_id == second.bundle_id
                assert first.input_sha256 == second.input_sha256
                assert _bundle_files(first.path) == _bundle_files(second.path)
                loaded = load_r3_bundle(first.path)
                assert loaded.proposal.proposal_id == first.proposal.proposal_id
                assert loaded.patch_application.all_instances_valid is True
                assert loaded.blind_validation.classification == (
                    "known_optional_motif_present"
                )
                workbench_sources = _real_w3_workbench_source_set(
                    sources,
                    first.path,
                )
                if workbench_sources is not None:
                    database = Path(first_dir) / "workbench-w3.sqlite"
                    first_summary = rebuild_workbench(database, workbench_sources)
                    first_snapshot = RegistryReader(database).snapshot()
                    second_summary = rebuild_workbench(database, workbench_sources)
                    assert first_summary.input_set_sha256 == (
                        second_summary.input_set_sha256
                    )
                    assert first_snapshot == RegistryReader(database).snapshot()
                    reader = RegistryReader(database)
                    counts = reader.entity_counts()
                    assert counts["graph_alignment"] == 1
                    assert counts["common_backbone_slot"] == 9
                    assert counts["alignment_residual"] == 2
                    assert counts["family_extension_proposal"] == 1
                    assert counts["proposal_review"] == 1
                    assert counts["grammar_patch"] == 1
                    assert counts["blind_instance_graph"] == 1
                    assert counts["blind_validation"] == 1
                    assert counts["grammar_diff"] >= 4
                    assert reader.metadata()["indexer_version"] == "r4.w4.v0"
                    assert reader.metadata()["roadmap_phase"] == "R3"
                    entities = {
                        (item["entity_kind"], item["entity_id"]): item
                        for item in reader.snapshot()["entities"]
                    }
                    assert entities[
                        ("validation", "w3.family-induction-hard-gate")
                    ]["status"] == "pass"
                    assert {item["status"] for item in reader.audit_sources(ROOT)} == {
                        "fresh"
                    }
                    with WorkbenchServer(
                        database,
                        source_root=ROOT,
                        token="r3-workbench-test-token",
                    ) as server:
                        connection = HTTPConnection(server.host, server.port, timeout=5)
                        connection.request(
                            "GET",
                            "/family-induction?token=r3-workbench-test-token",
                        )
                        response = connection.getresponse()
                        body = response.read().decode("utf-8")
                        connection.close()
                    assert response.status == 200
                    for text in (
                        "Family Induction / W3",
                        "Common semantic backbone",
                        "Pending proposal does not mutate grammar",
                        "Accepted manual review",
                        "Grammar before / after diff",
                        "Held-out real instance: LEReC 704 MHz",
                        "known_optional_motif_present",
                        "Representation contract: <b>not_imported_or_modified</b>",
                        "No live CST",
                        "Parameter names read: <b>False</b>",
                    ):
                        assert text in body

                    second_manifest = second.path / MANIFEST_FILE
                    original_manifest = second_manifest.read_bytes()
                    manifest_mapping = json.loads(original_manifest)
                    manifest_mapping["alignment_id"] = "tampered.alignment"
                    second_manifest.write_bytes(
                        canonical_json_bytes(manifest_mapping) + b"\n"
                    )
                    with pytest.raises(
                        WorkbenchIndexError,
                        match="manifest contract identity mismatch: alignment_id",
                    ):
                        rebuild_workbench(
                            Path(second_dir) / "tampered-manifest-w3.sqlite",
                            replace(
                                workbench_sources,
                                family_induction_bundle=second.path,
                            ),
                        )
                    second_manifest.write_bytes(original_manifest)

                    (second.path / PROPOSAL_FILE).write_bytes(b"tampered\n")
                    with pytest.raises(WorkbenchIndexError, match="invalid W3"):
                        rebuild_workbench(
                            Path(second_dir) / "tampered-w3.sqlite",
                            replace(
                                workbench_sources,
                                family_induction_bundle=second.path,
                            ),
                        )
    finally:
        try:
            scratch.rmdir()
        except OSError:
            pass


def _induce(
    first: InstanceBoundaryGraph,
    second: InstanceBoundaryGraph,
) -> tuple[GraphAlignment, FamilyExtensionProposal]:
    refs = (_graph_ref(first), _graph_ref(second))
    alignment = align_reviewed_graphs((first, second), refs)
    proposal = select_optional_motif_proposal(
        propose_family_extensions(alignment, (first, second)),
        region_type="NoseRegion",
    )
    return alignment, proposal


def _graph_ref(graph: InstanceBoundaryGraph) -> GraphContractRef:
    return GraphContractRef(
        instance_id=graph.instance_id,
        graph_id=graph.graph_id,
        source_path=f"fixtures/{graph.instance_id}.instance_boundary_graph.v0.json",
        source_raw_sha256=_sha(f"raw:{graph.instance_id}"),
        contract_sha256=canonical_sha256(graph.to_mapping()),
    )


def _graph(
    instance_id: str,
    *,
    nose_sides: tuple[str, ...],
    feature_prefix: str,
) -> InstanceBoundaryGraph:
    evidence = _evidence(instance_id)
    specs = list(BACKBONE)
    if "left" in nose_sides:
        specs.insert(2, ("nose_left", "NoseRegion", "left"))
    if "right" in nose_sides:
        right_iris_index = next(
            index for index, item in enumerate(specs) if item[0] == "iris_right"
        )
        specs.insert(right_iris_index, ("nose_right", "NoseRegion", "right"))
    regions = tuple(
        SemanticRegion(
            region_id=f"{instance_id}.region.{name}",
            region_type=region_type,
            side=side,
            role=f"{feature_prefix} role {index}",
            source_feature_ids=(f"{feature_prefix}.{index}",),
            motif_id=NOSE_PAIR_MOTIF_ID if region_type == "NoseRegion" else None,
            evidence=(evidence,),
            review=_review(f"{instance_id}::region::{name}", evidence),
        )
        for index, (name, region_type, side) in enumerate(specs)
    )
    landmarks: list[SemanticLandmark] = [
        SemanticLandmark(
            landmark_id=f"{instance_id}.landmark.aperture_left",
            landmark_type="AxialApertureLandmark",
            side="left",
            incident_region_ids=(regions[0].region_id,),
            evidence=(evidence,),
            review=_review(f"{instance_id}::aperture_left", evidence),
        )
    ]
    interfaces: list[BoundaryInterface] = []
    for index, (left, right) in enumerate(zip(regions, regions[1:])):
        landmark_id = f"{instance_id}.landmark.junction.{index:02d}"
        side = "left" if right.side == "center" else (
            "right" if left.side == "center" else left.side
        )
        landmarks.append(
            SemanticLandmark(
                landmark_id=landmark_id,
                landmark_type="RegionJunctionLandmark",
                side=side,
                incident_region_ids=(left.region_id, right.region_id),
                evidence=(evidence,),
                review=_review(f"{instance_id}::junction::{index}", evidence),
            )
        )
        interfaces.append(
            BoundaryInterface(
                interface_id=f"{instance_id}.interface.{index:02d}",
                left_region_id=left.region_id,
                right_region_id=right.region_id,
                landmark_id=landmark_id,
                evidence=(evidence,),
            )
        )
    center = next(region for region in regions if region.side == "center")
    landmarks.extend(
        (
            SemanticLandmark(
                landmark_id=f"{instance_id}.landmark.symmetry",
                landmark_type="SymmetryLandmark",
                side="center",
                incident_region_ids=(center.region_id,),
                evidence=(evidence,),
                review=_review(f"{instance_id}::symmetry", evidence),
            ),
            SemanticLandmark(
                landmark_id=f"{instance_id}.landmark.aperture_right",
                landmark_type="AxialApertureLandmark",
                side="right",
                incident_region_ids=(regions[-1].region_id,),
                evidence=(evidence,),
                review=_review(f"{instance_id}::aperture_right", evidence),
            ),
        )
    )
    return InstanceBoundaryGraph(
        graph_id=f"{instance_id}.boundary_graph.v0",
        family_id=FAMILY_ID,
        instance_id=instance_id,
        regions=regions,
        landmarks=tuple(landmarks),
        interfaces=tuple(interfaces),
        active_motif_ids=(NOSE_PAIR_MOTIF_ID,) if nose_sides else (),
        nose_presence="present" if nose_sides else "absent_reviewed_topology",
        nose_evidence=(evidence,),
        source_bindings=(evidence,),
        exclusions=("geometry_parameter_vector", "live_cst_execution"),
    )


def _grammar(*, include_nose: bool) -> FamilyGrammar:
    evidence = _evidence("grammar")
    slots = tuple(
        GrammarSlot(slot_id=name, region_type=region_type, side=side)
        for name, region_type, side in BACKBONE
    )
    motifs = ()
    if include_nose:
        motifs = (
            SemanticMotif(
                motif_id=NOSE_PAIR_MOTIF_ID,
                label="Paired optional nose regions",
                region_type="NoseRegion",
                allowed_counts=(0, 2),
                insertion_rules=(
                    MotifInsertionRule(
                        side="left",
                        between_region_types=("IrisRegion", "GapShapingRegion"),
                    ),
                    MotifInsertionRule(
                        side="right",
                        between_region_types=("GapShapingRegion", "IrisRegion"),
                    ),
                ),
                evidence=(evidence,),
            ),
        )
    counts: dict[str, int] = {}
    for slot in slots:
        counts[slot.region_type] = counts.get(slot.region_type, 0) + 1
    cardinalities = {key: (value,) for key, value in counts.items()}
    if include_nose:
        cardinalities["NoseRegion"] = (0, 2)
    adjacencies = {
        (left.region_type, right.region_type)
        for left, right in zip(slots, slots[1:])
    }
    if include_nose:
        adjacencies.update(
            {
                ("IrisRegion", "NoseRegion"),
                ("NoseRegion", "GapShapingRegion"),
                ("GapShapingRegion", "NoseRegion"),
                ("NoseRegion", "IrisRegion"),
            }
        )
    return FamilyGrammar(
        grammar_id=f"{FAMILY_ID}.family_grammar.pre_r3.v0",
        family_id=FAMILY_ID,
        backbone_slots=slots,
        motifs=motifs,
        type_cardinality=tuple(
            (key, cardinalities[key]) for key in sorted(cardinalities)
        ),
        allowed_adjacencies=tuple(sorted(adjacencies)),
        evidence=(evidence,),
        review=ReviewBinding(
            status="supported",
            item_id=f"{FAMILY_ID}::grammar",
            revision=0,
            evidence=evidence,
        ),
        exclusions=("family_induction", "live_cst_execution"),
    )


def _rename_nonsemantic_fields(graph: InstanceBoundaryGraph) -> InstanceBoundaryGraph:
    regions = tuple(
        replace(
            region,
            role=f"changed role {index}",
            source_feature_ids=(f"replacement_parameter_{index}",),
        )
        for index, region in enumerate(graph.regions)
    )
    return replace(graph, regions=regions)


def _evidence(name: str) -> EvidenceRef:
    return EvidenceRef(
        source_kind="fixture_reviewed_graph",
        source_path=f"fixtures/{name}.json",
        source_raw_sha256=_sha(name),
        locator="#/reviewed_topology",
        relation="supports_reviewed_semantic_topology",
    )


def _review(item_id: str, evidence: EvidenceRef) -> ReviewBinding:
    return ReviewBinding(
        status="confirmed",
        item_id=item_id,
        revision=0,
        evidence=evidence,
    )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bundle_files(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def _real_source_set() -> R3SourceSet | None:
    semantic_root = (
        ROOT
        / "analysis_outputs/rf_cem_semantic_core"
        / "r1_semantic_core.28e8d6fa9efa221f"
    )
    source_root = (
        ROOT
        / "analysis_outputs/rf_cem_family_induction/sources/lerec704"
    )
    sources = R3SourceSet(
        repo_root=ROOT,
        family_grammar=semantic_root / "family_grammar.v0.json",
        training_graphs=(
            semantic_root
            / "instances/sls2.r149.6593e02e.instance_boundary_graph.v0.json",
            semantic_root
            / "instances/rf500.2c27faee.b1r3.instance_boundary_graph.v0.json",
        ),
        lerec704_ipac2015_pdf=source_root / "source.pdf",
        lerec704_design_and_test_2018_pdf=(
            source_root / "design_and_test_2018.pdf"
        ),
    )
    paths = (
        sources.family_grammar,
        *sources.training_graphs,
        sources.lerec704_ipac2015_pdf,
        sources.lerec704_design_and_test_2018_pdf,
    )
    return sources if all(path.is_file() for path in paths) else None


def _real_w3_workbench_source_set(
    r3_sources: R3SourceSet,
    induction_bundle: Path,
) -> WorkbenchSourceSet | None:
    family_profile = (
        ROOT
        / "analysis_outputs/rf_cem_family_profiles"
        / "nc_axisymmetric_single_cell_rf_vacuum.00414d4f"
        / "family_profile.v0.json"
    )
    r2_records_root = (
        ROOT
        / "analysis_outputs/rf_cem_boundary_compiler"
        / "r2_boundary_compiler.aa66a3e90125437b"
        / "records"
    )
    compile_records = (
        r2_records_root / "sls2.r149.6593e02e.compile_record.v0.json",
        r2_records_root / "rf500.2c27faee.b1r3.compile_record.v0.json",
    )
    graph_diff = r3_sources.family_grammar.parent / "instance_graph_diff.v0.json"
    required = (family_profile, graph_diff, *compile_records)
    if not all(path.is_file() for path in required):
        return None
    return WorkbenchSourceSet(
        repo_root=ROOT,
        family_profile=family_profile,
        family_grammar=r3_sources.family_grammar,
        instance_boundary_graphs=r3_sources.training_graphs,
        instance_graph_diff=graph_diff,
        compile_records=compile_records,
        family_induction_bundle=induction_bundle,
    )
