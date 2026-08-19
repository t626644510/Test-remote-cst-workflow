"""Fail-closed adapters from the two reviewed R1 source instances.

The adapters deliberately stop at semantic topology.  They read provenance
records and reviewed labels, but do not import a geometry kernel, compile a
boundary representation, or translate a shared geometry parameter vector.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..family_profile.core import FAMILY_ID, validate_profile_mapping
from .contracts import (
    BoundaryInterface,
    EvidenceRef,
    FamilyGrammar,
    GrammarSlot,
    InstanceBoundaryGraph,
    InstanceGraphDiff,
    MotifInsertionRule,
    NOSE_PAIR_MOTIF_ID,
    ReviewBinding,
    SemanticContractError,
    SemanticLandmark,
    SemanticMotif,
    SemanticRegion,
    canonical_sha256,
    diff_instance_graphs,
    file_sha256,
    validate_graph_against_grammar,
)
from .ontology import (
    AXIAL_APERTURE_LANDMARK,
    BEAM_PIPE_REGION,
    EQUATOR_REGION,
    GAP_SHAPING_REGION,
    IRIS_REGION,
    NOSE_REGION,
    OUTER_WALL_REGION,
    REGION_JUNCTION_LANDMARK,
    SYMMETRY_LANDMARK,
)


SLS2_INSTANCE_ID = "sls2.r149.6593e02e"
RF500_INSTANCE_ID = "rf500.2c27faee.b1r3"
R1_GRAMMAR_ID = f"{FAMILY_ID}.family_grammar.v0"

_SLS2_PROJECTION_ID = "sls2.cavity_1.paper_approximation"
_SLS2_GEOMETRY_DECISION_ID = (
    "sls2::geometry::geometry_projection::sls2.cavity_1.paper_approximation"
)
_SLS2_SEGMENTS = (
    "seg_beam_pipe_left",
    "seg_ellipse_left_lower",
    "seg_ellipse_left_upper",
    "seg_ellipse_right_upper",
    "seg_ellipse_right_lower",
    "seg_beam_pipe_right",
)
_SLS2_REQUIRED_CANDIDATES = {
    "beam_aperture_candidate_01": "BeamAperture",
    "beam_exit_candidate_01": "BeamExit",
    "beam_pipe_left_candidate_01": "BeamPipeLeft",
    "beam_pipe_right_candidate_01": "BeamPipeRight",
    "conducting_wall_candidate_01": "ConductingWall",
    "equator_region_candidate_01": "EquatorRegion",
    "iris_candidate_01": "Iris",
    "iris_candidate_02": "Iris",
    "rfvacuum_volume_candidate_01": "RFVacuumVolume",
}
_RF500_SEGMENTS = (
    "seg_beam_pipe_left",
    "seg_nose_left_smooth_nurbs",
    "seg_blend_left",
    "seg_equator_free_crown",
    "seg_blend_right",
    "seg_nose_right_smooth_nurbs",
    "seg_beam_pipe_right",
)
_GRAPH_EXCLUSIONS = (
    "geometry_parameter_vector",
    "region_geometry_ownership",
    "compiled_boundary_representation",
    "live_cst_execution",
    "rf_physical_acceptance",
)


@dataclass(frozen=True)
class R1SourceSet:
    """Repository-bound source paths required for the R1 real cases."""

    repo_root: Path
    family_profile: Path
    sls2_generation: Path
    sls2_semantics: Path
    sls2_review: Path


@dataclass(frozen=True)
class R1Contracts:
    """Validated family grammar, real instance graphs, and their diff."""

    grammar: FamilyGrammar
    graphs: tuple[InstanceBoundaryGraph, ...]
    graph_diff: InstanceGraphDiff
    source_bindings: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if tuple(graph.instance_id for graph in self.graphs) != (
            SLS2_INSTANCE_ID,
            RF500_INSTANCE_ID,
        ):
            raise SemanticContractError("R1 contracts require the canonical two-instance order")
        for graph in self.graphs:
            validate_graph_against_grammar(self.grammar, graph)
        expected = diff_instance_graphs(self.graphs[0], self.graphs[1]).to_mapping()
        if self.graph_diff.to_mapping() != expected:
            raise SemanticContractError("R1 graph diff is not derived from the supplied graphs")
        if not self.source_bindings:
            raise SemanticContractError("R1 contracts require source bindings")

    @property
    def graphs_by_id(self) -> dict[str, InstanceBoundaryGraph]:
        """Return instance graphs keyed by stable instance ID."""

        return {graph.instance_id: graph for graph in self.graphs}


@dataclass(frozen=True)
class _LoadedSource:
    path: Path
    relative_path: str
    raw_sha256: str
    value: Mapping[str, Any]

    def evidence(
        self,
        *,
        source_kind: str,
        locator: str,
        relation: str,
        subject_raw_sha256: str | None = None,
    ) -> EvidenceRef:
        return EvidenceRef(
            source_kind=source_kind,
            source_path=self.relative_path,
            source_raw_sha256=self.raw_sha256,
            locator=locator,
            relation=relation,
            subject_raw_sha256=subject_raw_sha256,
        )


@dataclass(frozen=True)
class _RegionSpec:
    slot: str
    region_type: str
    side: str
    role: str
    source_feature_ids: tuple[str, ...]
    motif_id: str | None
    evidence: tuple[EvidenceRef, ...]
    review: ReviewBinding


def build_r1_contracts(sources: R1SourceSet) -> R1Contracts:
    """Build and cross-validate the two evidence-bound R1 semantic graphs."""

    repo_root = sources.repo_root.resolve(strict=True)
    profile_source = _load_source(repo_root, sources.family_profile)
    generation_source = _load_source(repo_root, sources.sls2_generation)
    semantics_source = _load_source(repo_root, sources.sls2_semantics)
    review_source = _load_source(repo_root, sources.sls2_review)

    try:
        validate_profile_mapping(profile_source.value)
    except (TypeError, ValueError) as exc:
        raise SemanticContractError(f"family profile validation failed: {exc}") from exc
    if profile_source.value.get("family_assertion_status") != "supported":
        raise SemanticContractError(
            "canonical R1 grammar requires a supported family assertion"
        )
    _validate_sls2_semantics(semantics_source.value)

    instances = _instances_by_id(profile_source.value)
    sls2_instance = instances.get(SLS2_INSTANCE_ID)
    rf500_instance = instances.get(RF500_INSTANCE_ID)
    if sls2_instance is None or rf500_instance is None:
        raise SemanticContractError(
            "family profile must contain sls2.r149.6593e02e and rf500.2c27faee.b1r3"
        )
    if set(instances) != {SLS2_INSTANCE_ID, RF500_INSTANCE_ID}:
        raise SemanticContractError("R1 source profile must contain exactly the two frozen instances")

    _check_bound_artifact(sls2_instance, "generation.core.json", generation_source)
    _check_bound_artifact(
        sls2_instance, "literature_semantics.v0.json", semantics_source
    )
    _check_bound_artifact(sls2_instance, "review_session.v1.json", review_source)

    grammar = _build_family_grammar(profile_source, generation_source, review_source)
    sls2_graph = _build_sls2_graph(
        sls2_instance,
        generation_source,
        semantics_source,
        review_source,
    )
    rf500_graph = _build_rf500_graph(rf500_instance, profile_source)
    for graph in (sls2_graph, rf500_graph):
        validate_graph_against_grammar(grammar, graph)
    graph_diff = diff_instance_graphs(sls2_graph, rf500_graph)
    return R1Contracts(
        grammar=grammar,
        graphs=(sls2_graph, rf500_graph),
        graph_diff=graph_diff,
        source_bindings=(
            profile_source.evidence(
                source_kind="family_profile",
                locator="#/",
                relation="r1_family_source",
            ),
            generation_source.evidence(
                source_kind="sls2_generation_record",
                locator="#/",
                relation="r1_instance_source",
            ),
            semantics_source.evidence(
                source_kind="sls2_literature_semantics",
                locator="#/",
                relation="r1_context_source",
            ),
            review_source.evidence(
                source_kind="sls2_review_session",
                locator="#/",
                relation="r1_review_source",
            ),
        ),
    )


def _build_family_grammar(
    profile: _LoadedSource,
    generation: _LoadedSource,
    review: _LoadedSource,
) -> FamilyGrammar:
    family_evidence = profile.evidence(
        source_kind="family_profile",
        locator="#/family_id",
        relation="defines_family_membership",
    )
    nose_evidence = profile.evidence(
        source_kind="family_profile",
        locator=(
            f"#/instances[instance_id={RF500_INSTANCE_ID}]/parameter_payload/"
            "native_payload/feature_bindings[feature_type=NoseCone]"
        ),
        relation="supports_optional_nose_motif",
        subject_raw_sha256=_rf500_subject_hash(_instances_by_id(profile.value)[RF500_INSTANCE_ID]),
    )
    absence_evidence = review.evidence(
        source_kind="sls2_review_session",
        locator=(
            f"#/helper2_reviews/{_SLS2_PROJECTION_ID}/review/candidates"
        ),
        relation="supports_zero_occurrence_of_optional_nose_motif",
        subject_raw_sha256=generation.raw_sha256,
    )
    motif = SemanticMotif(
        motif_id=NOSE_PAIR_MOTIF_ID,
        label="Paired optional nose regions",
        region_type=NOSE_REGION,
        allowed_counts=(0, 2),
        insertion_rules=(
            MotifInsertionRule(
                side="left",
                between_region_types=(IRIS_REGION, GAP_SHAPING_REGION),
            ),
            MotifInsertionRule(
                side="right",
                between_region_types=(GAP_SHAPING_REGION, IRIS_REGION),
            ),
        ),
        evidence=(nose_evidence, absence_evidence),
    )
    slots = (
        GrammarSlot("beam_pipe_left", BEAM_PIPE_REGION, "left"),
        GrammarSlot("iris_left", IRIS_REGION, "left"),
        GrammarSlot("gap_shaping_left", GAP_SHAPING_REGION, "left"),
        GrammarSlot("outer_wall_left", OUTER_WALL_REGION, "left"),
        GrammarSlot("equator", EQUATOR_REGION, "center"),
        GrammarSlot("outer_wall_right", OUTER_WALL_REGION, "right"),
        GrammarSlot("gap_shaping_right", GAP_SHAPING_REGION, "right"),
        GrammarSlot("iris_right", IRIS_REGION, "right"),
        GrammarSlot("beam_pipe_right", BEAM_PIPE_REGION, "right"),
    )
    return FamilyGrammar(
        grammar_id=R1_GRAMMAR_ID,
        family_id=FAMILY_ID,
        backbone_slots=slots,
        motifs=(motif,),
        type_cardinality=tuple(
            sorted(
                {
                    BEAM_PIPE_REGION: (2,),
                    IRIS_REGION: (2,),
                    GAP_SHAPING_REGION: (2,),
                    NOSE_REGION: (0, 2),
                    OUTER_WALL_REGION: (2,),
                    EQUATOR_REGION: (1,),
                }.items()
            )
        ),
        allowed_adjacencies=(
            (BEAM_PIPE_REGION, IRIS_REGION),
            (IRIS_REGION, GAP_SHAPING_REGION),
            (IRIS_REGION, NOSE_REGION),
            (NOSE_REGION, GAP_SHAPING_REGION),
            (GAP_SHAPING_REGION, OUTER_WALL_REGION),
            (OUTER_WALL_REGION, EQUATOR_REGION),
            (EQUATOR_REGION, OUTER_WALL_REGION),
            (OUTER_WALL_REGION, GAP_SHAPING_REGION),
            (GAP_SHAPING_REGION, IRIS_REGION),
            (GAP_SHAPING_REGION, NOSE_REGION),
            (NOSE_REGION, IRIS_REGION),
            (IRIS_REGION, BEAM_PIPE_REGION),
        ),
        evidence=(family_evidence, nose_evidence, absence_evidence),
        review=ReviewBinding(
            status="supported",
            item_id=f"{FAMILY_ID}::family_assertion_status",
            revision=None,
            evidence=profile.evidence(
                source_kind="family_profile",
                locator="#/family_assertion_status",
                relation="reviews_family_grammar_scope",
            ),
        ),
        exclusions=(
            "family_induction",
            "geometry_compilation",
            "common_geometry_parameter_vector",
            "live_cst_execution",
        ),
    )


def _build_sls2_graph(
    instance: Mapping[str, Any],
    generation: _LoadedSource,
    semantics: _LoadedSource,
    review: _LoadedSource,
) -> InstanceBoundaryGraph:
    profile = _mapping(generation.value.get("profile"), "generation.profile")
    segments = _mapping_array(profile.get("segments"), "generation.profile.segments")
    segment_ids = tuple(_string(item.get("id"), "generation segment id") for item in segments)
    if segment_ids != _SLS2_SEGMENTS:
        raise SemanticContractError("SLS-2 profile segment order differs from the frozen six-segment source")
    symmetry = _mapping(profile.get("symmetry"), "generation.profile.symmetry")
    if symmetry.get("left_right_mirrored") is not True or symmetry.get("plane") != "z=0":
        raise SemanticContractError("SLS-2 profile lacks the reviewed z=0 mirror symmetry")
    candidate_id = generation.value.get("candidate_id")
    if candidate_id != _SLS2_PROJECTION_ID:
        raise SemanticContractError("SLS-2 generation candidate ID is not the frozen projection")
    for segment in segments:
        refs = _string_array(segment.get("feature_refs"), "SLS-2 segment feature_refs")
        if any("nose" in value.casefold() for value in (str(segment.get("id")), *refs)):
            raise SemanticContractError("SLS-2 source profile unexpectedly contains nose semantics")

    helper_review, helper_revision = _validated_sls2_review(review.value)
    candidates = _mapping(helper_review.get("candidates"), "SLS-2 helper candidates")
    bindings = _mapping(helper_review.get("bindings"), "SLS-2 helper bindings")
    geometry_decision = _mapping(
        _mapping(review.value.get("review_decisions"), "review_decisions").get(
            _SLS2_GEOMETRY_DECISION_ID
        ),
        "SLS-2 geometry decision",
    )

    generation_evidence = generation.evidence(
        source_kind="sls2_generation_record",
        locator="#/profile/segments",
        relation="defines_ordered_source_profile",
    )
    semantics_evidence = semantics.evidence(
        source_kind="sls2_literature_semantics",
        locator="#/classification",
        relation="supports_semantic_scope",
    )

    def segment_evidence(segment_id: str, relation: str) -> EvidenceRef:
        return generation.evidence(
            source_kind="sls2_generation_record",
            locator=f"#/profile/segments[id={segment_id}]",
            relation=relation,
        )

    def candidate_review(feature_id: str) -> ReviewBinding:
        candidate = _mapping(candidates.get(feature_id), f"candidate {feature_id}")
        status = _string(candidate.get("status"), f"candidate {feature_id}.status")
        return ReviewBinding(
            status=status,
            item_id=f"{_SLS2_PROJECTION_ID}::helper2::{feature_id}",
            revision=helper_revision,
            evidence=review.evidence(
                source_kind="sls2_review_session",
                locator=(
                    f"#/helper2_reviews/{_SLS2_PROJECTION_ID}/review/"
                    f"candidates/{feature_id}"
                ),
                relation="records_terminal_region_review",
                subject_raw_sha256=generation.raw_sha256,
            ),
        )

    def candidate_evidence(feature_id: str) -> EvidenceRef:
        accepted = [
            binding_id
            for binding_id, raw in bindings.items()
            if isinstance(raw, Mapping)
            and raw.get("feature_id") == feature_id
            and raw.get("status") == "accepted"
            and raw.get("deleted") is False
        ]
        if not accepted:
            raise SemanticContractError(f"SLS-2 helper candidate {feature_id} lacks an accepted binding")
        return review.evidence(
            source_kind="sls2_review_session",
            locator=(
                f"#/helper2_reviews/{_SLS2_PROJECTION_ID}/review/"
                f"bindings/{accepted[0]}"
            ),
            relation="binds_semantic_region_to_reviewed_geometry",
            subject_raw_sha256=generation.raw_sha256,
        )

    region_specs = (
        _RegionSpec(
            "beam_pipe_left", BEAM_PIPE_REGION, "left", "left beam pipe",
            ("seg_beam_pipe_left", "beam_pipe_left_candidate_01"), None,
            (segment_evidence("seg_beam_pipe_left", "supports_region"), candidate_evidence("beam_pipe_left_candidate_01")),
            candidate_review("beam_pipe_left_candidate_01"),
        ),
        _RegionSpec(
            "iris_left", IRIS_REGION, "left", "left aperture transition",
            ("seg_ellipse_left_lower", "iris_candidate_02"), None,
            (segment_evidence("seg_ellipse_left_lower", "supports_region"), candidate_evidence("iris_candidate_02")),
            candidate_review("iris_candidate_02"),
        ),
        _RegionSpec(
            "gap_shaping_left", GAP_SHAPING_REGION, "left", "left gap-shaping wall",
            ("seg_ellipse_left_lower", "conducting_wall_candidate_01"), None,
            (segment_evidence("seg_ellipse_left_lower", "supports_region"), candidate_evidence("conducting_wall_candidate_01")),
            candidate_review("conducting_wall_candidate_01"),
        ),
        _RegionSpec(
            "outer_wall_left", OUTER_WALL_REGION, "left", "left outer wall",
            ("seg_ellipse_left_upper", "conducting_wall_candidate_01"), None,
            (segment_evidence("seg_ellipse_left_upper", "supports_region"), candidate_evidence("conducting_wall_candidate_01")),
            candidate_review("conducting_wall_candidate_01"),
        ),
        _RegionSpec(
            "equator", EQUATOR_REGION, "center", "equator crown",
            ("seg_ellipse_left_upper", "seg_ellipse_right_upper", "equator_region_candidate_01"), None,
            (segment_evidence("seg_ellipse_left_upper", "supports_region"), segment_evidence("seg_ellipse_right_upper", "supports_region"), candidate_evidence("equator_region_candidate_01")),
            candidate_review("equator_region_candidate_01"),
        ),
        _RegionSpec(
            "outer_wall_right", OUTER_WALL_REGION, "right", "right outer wall",
            ("seg_ellipse_right_upper", "conducting_wall_candidate_01"), None,
            (segment_evidence("seg_ellipse_right_upper", "supports_region"), candidate_evidence("conducting_wall_candidate_01")),
            candidate_review("conducting_wall_candidate_01"),
        ),
        _RegionSpec(
            "gap_shaping_right", GAP_SHAPING_REGION, "right", "right gap-shaping wall",
            ("seg_ellipse_right_lower", "conducting_wall_candidate_01"), None,
            (segment_evidence("seg_ellipse_right_lower", "supports_region"), candidate_evidence("conducting_wall_candidate_01")),
            candidate_review("conducting_wall_candidate_01"),
        ),
        _RegionSpec(
            "iris_right", IRIS_REGION, "right", "right aperture transition",
            ("seg_ellipse_right_lower", "iris_candidate_01"), None,
            (segment_evidence("seg_ellipse_right_lower", "supports_region"), candidate_evidence("iris_candidate_01")),
            candidate_review("iris_candidate_01"),
        ),
        _RegionSpec(
            "beam_pipe_right", BEAM_PIPE_REGION, "right", "right beam pipe",
            ("seg_beam_pipe_right", "beam_pipe_right_candidate_01"), None,
            (segment_evidence("seg_beam_pipe_right", "supports_region"), candidate_evidence("beam_pipe_right_candidate_01")),
            candidate_review("beam_pipe_right_candidate_01"),
        ),
    )
    absence_evidence = (
        generation.evidence(
            source_kind="sls2_generation_record",
            locator="#/profile/segments[*]/feature_refs",
            relation="reviewed_profile_contains_no_nose_feature",
        ),
        review.evidence(
            source_kind="sls2_review_session",
            locator=f"#/helper2_reviews/{_SLS2_PROJECTION_ID}/review/candidates",
            relation="confirmed_candidate_set_contains_no_nose_type",
            subject_raw_sha256=generation.raw_sha256,
        ),
    )
    geometry_review = ReviewBinding(
        status=_string(geometry_decision.get("status"), "geometry decision status"),
        item_id=_SLS2_GEOMETRY_DECISION_ID,
        revision=_integer(geometry_decision.get("revision"), "geometry decision revision"),
        evidence=review.evidence(
            source_kind="sls2_review_session",
            locator=f"#/review_decisions/{_SLS2_GEOMETRY_DECISION_ID}",
            relation="accepts_source_geometry_projection",
            subject_raw_sha256=generation.raw_sha256,
        ),
    )
    if not geometry_review.is_terminal:
        raise SemanticContractError("SLS-2 geometry projection review is not terminal")
    return _make_graph(
        instance_id=SLS2_INSTANCE_ID,
        region_specs=region_specs,
        nose_presence="absent_reviewed_topology",
        active_motif_ids=(),
        nose_evidence=absence_evidence,
        source_bindings=(generation_evidence, semantics_evidence, geometry_review.evidence),
    )


def _build_rf500_graph(
    instance: Mapping[str, Any], profile: _LoadedSource
) -> InstanceBoundaryGraph:
    parameter_payload = _mapping(instance.get("parameter_payload"), "RF500 parameter_payload")
    native = _mapping(parameter_payload.get("native_payload"), "RF500 native_payload")
    expected_native_hash = _hash_text(
        parameter_payload.get("portable_projection_canonical_sha256"),
        "RF500 portable_projection_canonical_sha256",
    )
    if canonical_sha256(native) != expected_native_hash:
        raise SemanticContractError("RF500 embedded portable payload canonical hash mismatch")
    source_payload_hash = _hash_text(
        parameter_payload.get("source_payload_canonical_sha256"),
        "RF500 source_payload_canonical_sha256",
    )
    native_payload_hash = _hash_text(
        parameter_payload.get("native_payload_canonical_sha256"),
        "RF500 native_payload_canonical_sha256",
    )
    if source_payload_hash != native_payload_hash:
        raise SemanticContractError("RF500 native/source payload canonical bindings disagree")
    subject_hash = _rf500_subject_hash(instance)
    if _hash_text(
        parameter_payload.get("source_artifact_raw_sha256"),
        "RF500 source_artifact_raw_sha256",
    ) != subject_hash:
        raise SemanticContractError("RF500 native payload is not bound to its source artifact")

    native_profile = _mapping(native.get("profile"), "RF500 native profile")
    segments = _mapping_array(native_profile.get("segments"), "RF500 profile segments")
    segment_ids = tuple(_string(item.get("id"), "RF500 segment id") for item in segments)
    if segment_ids != _RF500_SEGMENTS:
        raise SemanticContractError("RF500 source-native profile segment order is not the reviewed seven-segment variant")
    expected_refs = (
        {"BeamPipeLeft"},
        {"NoseCone", "TransitionBlend"},
        {"TransitionBlend", "EquatorRegion"},
        {"EquatorRegion"},
        {"TransitionBlend", "EquatorRegion"},
        {"TransitionBlend", "NoseCone"},
        {"BeamPipeRight"},
    )
    for index, (segment, required) in enumerate(zip(segments, expected_refs)):
        refs = set(_string_array(segment.get("feature_refs"), f"RF500 segment {index} feature_refs"))
        if not required <= refs:
            raise SemanticContractError(
                f"RF500 segment {segment_ids[index]} omits reviewed feature refs {sorted(required - refs)}"
            )

    bindings = _mapping_array(native.get("feature_bindings"), "RF500 feature_bindings")
    by_type: dict[str, list[Mapping[str, Any]]] = {}
    for binding in bindings:
        feature_type = _string(binding.get("feature_type"), "RF500 feature_type")
        by_type.setdefault(feature_type, []).append(binding)
    for feature_type in (
        "BeamAperture",
        "BeamExit",
        "BeamPipeLeft",
        "BeamPipeRight",
        "ConductingWall",
        "EquatorRegion",
        "NoseCone",
        "TransitionBlend",
    ):
        if feature_type not in by_type:
            raise SemanticContractError(f"RF500 lacks reviewed {feature_type} binding")
    nose_binding = by_type["NoseCone"]
    if len(nose_binding) != 1:
        raise SemanticContractError("RF500 requires one reviewed binding for the paired nose source segments")
    nose_binding_item = nose_binding[0]
    if (
        nose_binding_item.get("feature_id") != "iris_candidate_01"
        or not isinstance(nose_binding_item.get("confidence"), (int, float))
        or isinstance(nose_binding_item.get("confidence"), bool)
        or float(nose_binding_item["confidence"]) < 0.85
        or not str(nose_binding_item.get("provenance", "")).startswith(
            "reviewed_feature_labels.yaml::"
        )
        or not {
            "seg_nose_left_inner_semicircle",
            "seg_nose_right_inner_semicircle",
        } <= set(_string_array(nose_binding_item.get("segment_ids"), "RF500 nose binding segment_ids"))
    ):
        raise SemanticContractError("RF500 NoseCone binding is not the reviewed human-label source")
    validation_layers = _mapping(
        instance.get("validation_layers"), "RF500 validation_layers"
    )
    human_review = _mapping(
        validation_layers.get("human_review"), "RF500 human_review"
    )
    if human_review.get("status") != "pass":
        raise SemanticContractError(
            "RF500 canonical semantic graph requires passed human-review evidence"
        )

    def profile_evidence(locator: str, relation: str) -> EvidenceRef:
        return profile.evidence(
            source_kind="family_profile_embedded_rf500_source",
            locator=(
                f"#/instances[instance_id={RF500_INSTANCE_ID}]/parameter_payload/"
                f"native_payload/{locator}"
            ),
            relation=relation,
            subject_raw_sha256=subject_hash,
        )

    def segment_evidence(segment_id: str, relation: str = "supports_region") -> EvidenceRef:
        return profile_evidence(f"profile/segments[id={segment_id}]", relation)

    def binding(feature_type: str) -> Mapping[str, Any]:
        values = by_type[feature_type]
        if feature_type not in {"BeamAperture", "BeamExit"} and len(values) != 1:
            raise SemanticContractError(f"RF500 {feature_type} binding must be unambiguous")
        return values[0]

    def binding_id(feature_type: str) -> str:
        return _string(binding(feature_type).get("feature_id"), f"RF500 {feature_type} feature_id")

    def reviewed_binding_evidence(feature_type: str) -> EvidenceRef:
        feature_id = binding_id(feature_type)
        item = binding(feature_type)
        provenance = _string(item.get("provenance"), f"RF500 {feature_type} provenance")
        if not provenance.startswith("reviewed_feature_labels.yaml::"):
            raise SemanticContractError(f"RF500 {feature_type} is not human-review bound")
        return profile_evidence(
            f"feature_bindings[feature_id={feature_id}]",
            "records_human_reviewed_semantic_binding",
        )

    def review_binding(feature_type: str) -> ReviewBinding:
        feature_id = binding_id(feature_type)
        return ReviewBinding(
            status="confirmed",
            item_id=f"{RF500_INSTANCE_ID}::reviewed_feature::{feature_id}",
            revision=None,
            evidence=reviewed_binding_evidence(feature_type),
        )

    region_specs = (
        _RegionSpec("beam_pipe_left", BEAM_PIPE_REGION, "left", "left beam pipe", ("seg_beam_pipe_left", binding_id("BeamPipeLeft")), None, (segment_evidence("seg_beam_pipe_left"), reviewed_binding_evidence("BeamPipeLeft")), review_binding("BeamPipeLeft")),
        _RegionSpec("iris_left", IRIS_REGION, "left", "left beam aperture", ("seg_beam_pipe_left", binding_id("BeamAperture")), None, (segment_evidence("seg_beam_pipe_left"), reviewed_binding_evidence("BeamAperture")), review_binding("BeamAperture")),
        _RegionSpec("nose_left", NOSE_REGION, "left", "left nose", ("seg_nose_left_smooth_nurbs", binding_id("NoseCone")), NOSE_PAIR_MOTIF_ID, (segment_evidence("seg_nose_left_smooth_nurbs", "supports_evidence_bound_nose_region"), reviewed_binding_evidence("NoseCone")), review_binding("NoseCone")),
        _RegionSpec("gap_shaping_left", GAP_SHAPING_REGION, "left", "left transition blend", ("seg_blend_left", binding_id("TransitionBlend")), None, (segment_evidence("seg_blend_left"), reviewed_binding_evidence("TransitionBlend")), review_binding("TransitionBlend")),
        _RegionSpec("outer_wall_left", OUTER_WALL_REGION, "left", "left outer wall", ("seg_blend_left", binding_id("ConductingWall")), None, (segment_evidence("seg_blend_left"), reviewed_binding_evidence("ConductingWall")), review_binding("ConductingWall")),
        _RegionSpec("equator", EQUATOR_REGION, "center", "equator crown", ("seg_equator_free_crown", binding_id("EquatorRegion")), None, (segment_evidence("seg_equator_free_crown"), reviewed_binding_evidence("EquatorRegion")), review_binding("EquatorRegion")),
        _RegionSpec("outer_wall_right", OUTER_WALL_REGION, "right", "right outer wall", ("seg_blend_right", binding_id("ConductingWall")), None, (segment_evidence("seg_blend_right"), reviewed_binding_evidence("ConductingWall")), review_binding("ConductingWall")),
        _RegionSpec("gap_shaping_right", GAP_SHAPING_REGION, "right", "right transition blend", ("seg_blend_right", binding_id("TransitionBlend")), None, (segment_evidence("seg_blend_right"), reviewed_binding_evidence("TransitionBlend")), review_binding("TransitionBlend")),
        _RegionSpec("nose_right", NOSE_REGION, "right", "right nose", ("seg_nose_right_smooth_nurbs", binding_id("NoseCone")), NOSE_PAIR_MOTIF_ID, (segment_evidence("seg_nose_right_smooth_nurbs", "supports_evidence_bound_nose_region"), reviewed_binding_evidence("NoseCone")), review_binding("NoseCone")),
        _RegionSpec("iris_right", IRIS_REGION, "right", "right beam exit", ("seg_beam_pipe_right", binding_id("BeamExit")), None, (segment_evidence("seg_beam_pipe_right"), reviewed_binding_evidence("BeamExit")), review_binding("BeamExit")),
        _RegionSpec("beam_pipe_right", BEAM_PIPE_REGION, "right", "right beam pipe", ("seg_beam_pipe_right", binding_id("BeamPipeRight")), None, (segment_evidence("seg_beam_pipe_right"), reviewed_binding_evidence("BeamPipeRight")), review_binding("BeamPipeRight")),
    )
    nose_evidence = (
        profile_evidence(
            "profile/segments[id=seg_nose_left_smooth_nurbs]",
            "supports_left_nose_presence",
        ),
        profile_evidence(
            "profile/segments[id=seg_nose_right_smooth_nurbs]",
            "supports_right_nose_presence",
        ),
        reviewed_binding_evidence("NoseCone"),
    )
    return _make_graph(
        instance_id=RF500_INSTANCE_ID,
        region_specs=region_specs,
        nose_presence="present",
        active_motif_ids=(NOSE_PAIR_MOTIF_ID,),
        nose_evidence=nose_evidence,
        source_bindings=(
            profile.evidence(
                source_kind="family_profile",
                locator=f"#/instances[instance_id={RF500_INSTANCE_ID}]",
                relation="binds_rf500_family_instance",
                subject_raw_sha256=subject_hash,
            ),
        ),
    )


def _make_graph(
    *,
    instance_id: str,
    region_specs: Sequence[_RegionSpec],
    nose_presence: str,
    active_motif_ids: tuple[str, ...],
    nose_evidence: tuple[EvidenceRef, ...],
    source_bindings: tuple[EvidenceRef, ...],
) -> InstanceBoundaryGraph:
    regions = tuple(
        SemanticRegion(
            region_id=f"{instance_id}.region.{spec.slot}",
            region_type=spec.region_type,
            side=spec.side,
            role=spec.role,
            source_feature_ids=spec.source_feature_ids,
            motif_id=spec.motif_id,
            evidence=spec.evidence,
            review=spec.review,
        )
        for spec in region_specs
    )
    center_index = next(index for index, region in enumerate(regions) if region.side == "center")
    landmarks: list[SemanticLandmark] = [
        SemanticLandmark(
            landmark_id=f"{instance_id}.landmark.aperture_left",
            landmark_type=AXIAL_APERTURE_LANDMARK,
            side="left",
            incident_region_ids=(regions[0].region_id,),
            evidence=regions[0].evidence,
            review=regions[0].review,
        )
    ]
    interfaces: list[BoundaryInterface] = []
    for index, (left, right) in enumerate(zip(regions, regions[1:])):
        landmark_id = f"{instance_id}.landmark.junction.{index:02d}"
        side = "left" if index < center_index else "right"
        evidence = _deduplicated_evidence((*left.evidence, *right.evidence))
        landmarks.append(
            SemanticLandmark(
                landmark_id=landmark_id,
                landmark_type=REGION_JUNCTION_LANDMARK,
                side=side,
                incident_region_ids=(left.region_id, right.region_id),
                evidence=evidence,
                review=left.review if left.side != "center" else right.review,
            )
        )
        interfaces.append(
            BoundaryInterface(
                interface_id=f"{instance_id}.interface.{index:02d}",
                left_region_id=left.region_id,
                right_region_id=right.region_id,
                landmark_id=landmark_id,
                evidence=evidence,
            )
        )
    center = regions[center_index]
    landmarks.extend(
        (
            SemanticLandmark(
                landmark_id=f"{instance_id}.landmark.symmetry",
                landmark_type=SYMMETRY_LANDMARK,
                side="center",
                incident_region_ids=(center.region_id,),
                evidence=center.evidence,
                review=center.review,
            ),
            SemanticLandmark(
                landmark_id=f"{instance_id}.landmark.aperture_right",
                landmark_type=AXIAL_APERTURE_LANDMARK,
                side="right",
                incident_region_ids=(regions[-1].region_id,),
                evidence=regions[-1].evidence,
                review=regions[-1].review,
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
        active_motif_ids=active_motif_ids,
        nose_presence=nose_presence,
        nose_evidence=nose_evidence,
        source_bindings=source_bindings,
        exclusions=_GRAPH_EXCLUSIONS,
    )


def _validated_sls2_review(review: Mapping[str, Any]) -> tuple[Mapping[str, Any], int]:
    if review.get("schema_version") != "review_session.v1":
        raise SemanticContractError("SLS-2 review session schema is not review_session.v1")
    if _integer(review.get("revision"), "SLS-2 review revision") < 149:
        raise SemanticContractError("SLS-2 review session is older than frozen revision 149")
    helper_entry = _mapping(
        _mapping(review.get("helper2_reviews"), "helper2_reviews").get(
            _SLS2_PROJECTION_ID
        ),
        "SLS-2 helper2 review",
    )
    helper_revision = _integer(helper_entry.get("revision"), "SLS-2 helper revision")
    if helper_revision != 147:
        raise SemanticContractError("SLS-2 Helper2 review must be frozen revision 147")
    helper_review = _mapping(helper_entry.get("review"), "SLS-2 helper review payload")
    if helper_review.get("schema_version") != "helper2_review_session.v1":
        raise SemanticContractError("SLS-2 Helper2 review schema is unsupported")
    candidates = _mapping(helper_review.get("candidates"), "SLS-2 helper candidates")
    if set(candidates) != set(_SLS2_REQUIRED_CANDIDATES):
        raise SemanticContractError("SLS-2 reviewed candidate set differs from the frozen nine candidates")
    for feature_id, expected_type in _SLS2_REQUIRED_CANDIDATES.items():
        candidate = _mapping(candidates.get(feature_id), f"candidate {feature_id}")
        if candidate.get("type") != expected_type or candidate.get("status") != "confirmed":
            raise SemanticContractError(f"SLS-2 candidate {feature_id} is not confirmed as {expected_type}")
    if any(
        "nose" in str(value).casefold()
        for feature_id, candidate in candidates.items()
        for value in (feature_id, _mapping(candidate, "candidate").get("type", ""))
    ):
        raise SemanticContractError("SLS-2 reviewed topology unexpectedly contains a nose candidate")
    geometry = _mapping(helper_review.get("geometry"), "SLS-2 reviewed geometry")
    if not geometry or any(
        not isinstance(item, Mapping) or item.get("status") != "accepted"
        for item in geometry.values()
    ):
        raise SemanticContractError("SLS-2 Helper2 geometry is not fully accepted")
    decision = _mapping(
        _mapping(review.get("review_decisions"), "review_decisions").get(
            _SLS2_GEOMETRY_DECISION_ID
        ),
        "SLS-2 geometry projection decision",
    )
    if decision.get("status") != "accepted" or decision.get("revision") != 72:
        raise SemanticContractError("SLS-2 geometry projection must be accepted at revision 72")
    return helper_review, helper_revision


def _validate_sls2_semantics(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != "literature_semantics.v0":
        raise SemanticContractError("SLS-2 semantics schema is not literature_semantics.v0")
    context = _mapping(value.get("request_context"), "SLS-2 request_context")
    if (
        context.get("geometry_scope") != "axisymmetric_single_cell_rf_vacuum"
        or context.get("operating_regime") != "normal_conducting"
    ):
        raise SemanticContractError("SLS-2 semantic scope does not match the R1 family")
    classification = _mapping(value.get("classification"), "SLS-2 classification")
    if classification.get("cell_count") != "single":
        raise SemanticContractError("SLS-2 semantic classification is not single-cell")
    sources = value.get("evidence_sources")
    if not isinstance(sources, list) or not sources:
        raise SemanticContractError("SLS-2 semantics require literature evidence sources")


def _instances_by_id(profile: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    instances = _mapping_array(profile.get("instances"), "family profile instances")
    result: dict[str, Mapping[str, Any]] = {}
    for instance in instances:
        instance_id = _string(instance.get("instance_id"), "family instance_id")
        if instance_id in result:
            raise SemanticContractError(f"duplicate family instance: {instance_id}")
        if instance.get("family_id") != FAMILY_ID:
            raise SemanticContractError(f"instance {instance_id} has the wrong family_id")
        result[instance_id] = instance
    return result


def _check_bound_artifact(
    instance: Mapping[str, Any], relative_name: str, source: _LoadedSource
) -> None:
    binding = _mapping(instance.get("source_binding"), "instance source_binding")
    if binding.get("manifest_id") != SLS2_INSTANCE_ID:
        raise SemanticContractError("SLS-2 source binding manifest ID is not frozen")
    artifacts = _mapping_array(binding.get("artifacts"), "source binding artifacts")
    matches = [
        item
        for item in artifacts
        if str(item.get("bundle_relative_path", "")).replace("\\", "/")
        == relative_name
    ]
    if len(matches) != 1:
        raise SemanticContractError(f"SLS-2 source binding omits {relative_name}")
    expected = _hash_text(matches[0].get("raw_sha256"), f"{relative_name} raw_sha256")
    if expected != source.raw_sha256:
        raise SemanticContractError(f"SLS-2 source hash mismatch for {relative_name}")


def _rf500_subject_hash(instance: Mapping[str, Any]) -> str:
    binding = _mapping(instance.get("source_binding"), "RF500 source_binding")
    if binding.get("manifest_id") != RF500_INSTANCE_ID:
        raise SemanticContractError("RF500 source binding manifest ID is not frozen")
    artifacts = _mapping_array(binding.get("artifacts"), "RF500 source artifacts")
    matches = [
        item
        for item in artifacts
        if str(item.get("bundle_relative_path", "")).replace("\\", "/")
        == "source/parametric_geometry.v0.json"
    ]
    if len(matches) != 1:
        raise SemanticContractError("RF500 source binding omits parametric_geometry.v0.json")
    return _hash_text(matches[0].get("raw_sha256"), "RF500 parametric source raw_sha256")


def _load_source(repo_root: Path, path: Path) -> _LoadedSource:
    candidate = path if path.is_absolute() else repo_root / path
    resolved = candidate.resolve(strict=True)
    try:
        relative = resolved.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise SemanticContractError(f"R1 source is outside repository root: {resolved}") from exc
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticContractError(f"cannot read R1 JSON source {relative}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise SemanticContractError(f"R1 JSON source must contain an object: {relative}")
    return _LoadedSource(
        path=resolved,
        relative_path=relative,
        raw_sha256=file_sha256(resolved),
        value=value,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SemanticContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise SemanticContractError(f"non-finite JSON constant is forbidden: {value}")


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticContractError(f"{path} must be an object")
    return value


def _mapping_array(value: object, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise SemanticContractError(f"{path} must be an array of objects")
    return list(value)


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SemanticContractError(f"{path} must be a non-empty string")
    return value


def _string_array(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SemanticContractError(f"{path} must be an array")
    result = tuple(_string(item, f"{path} item") for item in value)
    if len(result) != len(set(result)):
        raise SemanticContractError(f"{path} must contain unique strings")
    return result


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SemanticContractError(f"{path} must be a non-negative integer")
    return value


def _hash_text(value: object, path: str) -> str:
    text = _string(value, path).lower().removeprefix("sha256:")
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SemanticContractError(f"{path} must be a SHA-256 digest")
    return text


def _deduplicated_evidence(values: Sequence[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    result: list[EvidenceRef] = []
    seen: set[str] = set()
    for item in values:
        digest = canonical_sha256(item.to_mapping())
        if digest not in seen:
            seen.add(digest)
            result.append(item)
    return tuple(result)
