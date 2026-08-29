"""Deterministic, immutable proof bundle for RF-CEM R3."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from ..adapters import RF500_INSTANCE_ID, SLS2_INSTANCE_ID
from ..contracts import (
    FamilyGrammar,
    InstanceBoundaryGraph,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    load_family_grammar,
    load_instance_boundary_graph,
    validate_graph_against_grammar,
    validate_reviewed_graph_intrinsic,
)
from .alignment import (
    align_reviewed_graphs,
    graph_contract_ref,
    propose_family_extensions,
    select_optional_motif_proposal,
)
from .blind import (
    LEReC704BlindSources,
    build_lerec704_blind_graph,
    validate_blind_instance,
)
from .contracts import (
    BlindValidation,
    FamilyExtensionProposalContract,
    FamilyExtensionProposalV1,
    GrammarPatch,
    GrammarPatchApplication,
    GraphAlignment,
    GraphContractRef,
    InductionContractError,
    ProposalReview,
    load_blind_validation,
    load_family_extension_proposal,
    load_grammar_patch,
    load_graph_alignment,
    load_patch_application,
    load_proposal_review,
)
from .engine import FamilyInductionEngine
from .review import ablate_optional_motif, make_proposal_review, review_proposal


R3_BUNDLE_SCHEMA_VERSION = "r3_family_induction_bundle.v0"
R3_MANIFEST_SCHEMA_VERSION = "r3_family_induction_source_binding_manifest.v0"
R3_BUNDLE_PREFIX = "r3_family_induction"
R3_ABLATION_BUNDLE_SCHEMA_VERSION = "r3_family_induction_ablation_bundle.v1"
R3_ABLATION_MANIFEST_SCHEMA_VERSION = (
    "r3_family_induction_ablation_source_binding_manifest.v1"
)
R3_ABLATION_BUNDLE_PREFIX = "r3_family_induction_ablation"

ALIGNMENT_FILE = "graph_alignment.v0.json"
PROPOSAL_FILE = "family_extension_proposal.v0.json"
PROPOSAL_FILE_V1 = "family_extension_proposal.v1.json"
SEED_GRAMMAR_FILE = "family_grammar.seed_ablation.v0.json"
REVIEW_FILE = "family_extension_review.v0.json"
PATCH_FILE = "family_grammar_patch.v0.json"
PATCHED_GRAMMAR_FILE = "family_grammar.r3.v0.json"
PATCH_APPLICATION_FILE = "family_grammar_patch_application.v0.json"
BLIND_GRAPH_FILE = "blind/lerec704.instance_boundary_graph.v0.json"
BLIND_VALIDATION_FILE = "family_induction_blind_validation.v0.json"
MANIFEST_FILE = "source_binding_manifest.v0.json"
MANIFEST_FILE_V1 = "source_binding_manifest.v1.json"


@dataclass(frozen=True)
class R3SourceSet:
    """Explicit reviewed inputs for the real R3 proof."""

    repo_root: Path
    family_grammar: Path
    training_graphs: tuple[Path, ...]
    lerec704_ipac2015_pdf: Path
    lerec704_design_and_test_2018_pdf: Path
    representation_core: Path = Path("src/rf_cem/representation/core.py")


@dataclass(frozen=True)
class R3Bundle:
    """Loaded in-memory identities for one R3 proof bundle."""

    path: Path
    bundle_id: str
    input_sha256: str
    alignment: GraphAlignment
    proposal: FamilyExtensionProposalContract
    review: ProposalReview
    patch: GrammarPatch
    patched_grammar: FamilyGrammar
    patch_application: GrammarPatchApplication
    blind_graph: InstanceBoundaryGraph
    blind_validation: BlindValidation
    manifest: Mapping[str, Any]
    seed_grammar: FamilyGrammar | None = None
    manifest_file: str = MANIFEST_FILE
    proposal_file: str = PROPOSAL_FILE


def write_r3_bundle(
    sources: R3SourceSet,
    output_root: Path,
    *,
    review_decision: str,
    reviewer_id: str,
    review_rationale: str,
    review_revision: int = 0,
) -> R3Bundle:
    """Induce first, then explicitly review/patch, then run held-out validation."""

    if review_decision != "accepted":
        raise InductionContractError(
            "the canonical R3 closeout bundle requires an explicit accepted review"
        )
    root = sources.repo_root.resolve()
    if not root.is_dir():
        raise InductionContractError("repository root is missing")
    grammar_path = _inside(root, sources.family_grammar, "family grammar")
    graph_paths = tuple(
        _inside(root, path, "training instance graph")
        for path in sources.training_graphs
    )
    if len(graph_paths) != 2 or len(set(graph_paths)) != 2:
        raise InductionContractError("R3 induction requires exactly two unique training graphs")
    design_pdf = _inside(root, sources.lerec704_ipac2015_pdf, "LEReC design PDF")
    test_pdf = _inside(
        root,
        sources.lerec704_design_and_test_2018_pdf,
        "LEReC design-and-test PDF",
    )
    representation_core = _inside(
        root,
        sources.representation_core,
        "representation core",
    )
    grammar = load_family_grammar(grammar_path)
    graphs = tuple(load_instance_boundary_graph(path) for path in graph_paths)
    if {graph.instance_id for graph in graphs} != {
        SLS2_INSTANCE_ID,
        RF500_INSTANCE_ID,
    }:
        raise InductionContractError("R3 training graphs must be canonical SLS-2 and RF500")
    for graph in graphs:
        validate_graph_against_grammar(grammar, graph)
    refs = tuple(
        graph_contract_ref(root, path, graph)
        for path, graph in zip(graph_paths, graphs)
    )

    # The held-out source is deliberately not passed into either call.
    alignment = align_reviewed_graphs(graphs, refs)
    proposals = propose_family_extensions(alignment, graphs)
    proposal = select_optional_motif_proposal(proposals, region_type="NoseRegion")

    source_identity = {
        "schema_version": R3_BUNDLE_SCHEMA_VERSION,
        "base_grammar_id": grammar.grammar_id,
        "base_grammar_sha256": canonical_sha256(grammar.to_mapping()),
        "training_graph_refs": [item.to_mapping() for item in alignment.graph_refs],
        "alignment_id": alignment.alignment_id,
        "proposal_id": proposal.proposal_id,
        "blind_sources": [
            {
                "path": design_pdf.relative_to(root).as_posix(),
                "raw_sha256": file_sha256(design_pdf),
            },
            {
                "path": test_pdf.relative_to(root).as_posix(),
                "raw_sha256": file_sha256(test_pdf),
            },
        ],
        "representation_core": {
            "path": representation_core.relative_to(root).as_posix(),
            "raw_sha256": file_sha256(representation_core),
        },
        "explicit_review": {
            "decision": review_decision,
            "reviewer_id": reviewer_id,
            "rationale": review_rationale,
            "revision": review_revision,
        },
    }
    input_sha256 = canonical_sha256(source_identity)
    bundle_id = f"{R3_BUNDLE_PREFIX}.{input_sha256[:16]}"
    output = output_root if output_root.is_absolute() else root / output_root
    resolved_output = output.resolve()
    try:
        resolved_output.relative_to(root)
    except ValueError as exc:
        raise InductionContractError("R3 proof output must remain inside repository") from exc
    resolved_output.mkdir(parents=True, exist_ok=True)
    target = resolved_output / bundle_id
    if target.exists():
        raise FileExistsError(f"R3 proof bundle already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=resolved_output))
    try:
        _write_json(temporary / ALIGNMENT_FILE, alignment.to_mapping())
        _write_json(temporary / PROPOSAL_FILE, proposal.to_mapping())
        review = make_proposal_review(
            proposal,
            decision=review_decision,
            reviewer_id=reviewer_id,
            rationale=review_rationale,
            revision=review_revision,
        )
        _write_json(temporary / REVIEW_FILE, review.to_mapping())
        outcome = review_proposal(
            grammar,
            proposal,
            review,
            existing_graphs=graphs,
        )
        if outcome.patch is None or not outcome.application.applied:
            raise InductionContractError("accepted R3 review did not produce a patch")
        patch = outcome.patch
        patched_grammar = outcome.grammar
        _write_json(temporary / PATCH_FILE, patch.to_mapping())
        _write_json(temporary / PATCHED_GRAMMAR_FILE, patched_grammar.to_mapping())
        _write_json(
            temporary / PATCH_APPLICATION_FILE,
            outcome.application.to_mapping(),
        )

        blind_graph = build_lerec704_blind_graph(
            LEReC704BlindSources(
                repo_root=root,
                ipac2015_design_pdf=design_pdf,
                design_and_test_2018_pdf=test_pdf,
            ),
            family_id=grammar.family_id,
        )
        blind_path = temporary / BLIND_GRAPH_FILE
        _write_json(blind_path, blind_graph.to_mapping())
        blind_ref = GraphContractRef(
            instance_id=blind_graph.instance_id,
            graph_id=blind_graph.graph_id,
            source_path=(
                f"analysis_outputs/rf_cem_family_induction/{bundle_id}/"
                f"{BLIND_GRAPH_FILE}"
            ),
            source_raw_sha256=file_sha256(blind_path),
            contract_sha256=canonical_sha256(blind_graph.to_mapping()),
        )
        blind_validation = validate_blind_instance(
            patched_grammar,
            proposal,
            blind_graph,
            blind_ref,
        )
        _write_json(
            temporary / BLIND_VALIDATION_FILE,
            blind_validation.to_mapping(),
        )
        manifest = _manifest(
            root=root,
            bundle_root=temporary,
            bundle_id=bundle_id,
            input_sha256=input_sha256,
            grammar_path=grammar_path,
            graph_paths=graph_paths,
            design_pdf=design_pdf,
            test_pdf=test_pdf,
            representation_core=representation_core,
            alignment=alignment,
            proposal=proposal,
            review=review,
            patch=patch,
            patched_grammar=patched_grammar,
            application=outcome.application,
            blind_graph=blind_graph,
            blind_validation=blind_validation,
        )
        _write_json(temporary / MANIFEST_FILE, manifest)
        _validate_materialized_bundle(temporary, manifest)
        if target.exists():
            raise FileExistsError(f"R3 proof bundle already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists() and temporary.parent == resolved_output:
            shutil.rmtree(temporary)
        raise
    return R3Bundle(
        path=target,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        alignment=alignment,
        proposal=proposal,
        review=review,
        patch=patch,
        patched_grammar=patched_grammar,
        patch_application=outcome.application,
        blind_graph=blind_graph,
        blind_validation=blind_validation,
        manifest=manifest,
    )


def write_r3_ablation_bundle(
    sources: R3SourceSet,
    output_root: Path,
    *,
    review_decision: str,
    reviewer_id: str,
    review_rationale: str,
    review_revision: int = 0,
) -> R3Bundle:
    """Prove nose discovery from an intrinsic-valid, nose-ablated seed grammar."""

    if review_decision != "accepted":
        raise InductionContractError(
            "the canonical TD3 ablation bundle requires an accepted review"
        )
    root = sources.repo_root.resolve()
    if not root.is_dir():
        raise InductionContractError("repository root is missing")
    grammar_path = _inside(root, sources.family_grammar, "family grammar")
    graph_paths = tuple(
        _inside(root, path, "training instance graph")
        for path in sources.training_graphs
    )
    if len(graph_paths) != 2 or len(set(graph_paths)) != 2:
        raise InductionContractError(
            "TD3 ablation requires exactly two unique training graphs"
        )
    design_pdf = _inside(root, sources.lerec704_ipac2015_pdf, "LEReC design PDF")
    test_pdf = _inside(
        root,
        sources.lerec704_design_and_test_2018_pdf,
        "LEReC design-and-test PDF",
    )
    representation_core = _inside(
        root,
        sources.representation_core,
        "representation core",
    )
    canonical_grammar = load_family_grammar(grammar_path)
    seed_grammar = ablate_optional_motif(
        canonical_grammar,
        motif_id="motif.nose_pair.v0",
    )
    graphs = tuple(load_instance_boundary_graph(path) for path in graph_paths)
    graphs_by_id = {graph.instance_id: graph for graph in graphs}
    if set(graphs_by_id) != {SLS2_INSTANCE_ID, RF500_INSTANCE_ID}:
        raise InductionContractError(
            "TD3 ablation graphs must be canonical SLS-2 and RF500"
        )
    for graph in graphs:
        validate_reviewed_graph_intrinsic(graph)
        validate_graph_against_grammar(canonical_grammar, graph)
    validate_graph_against_grammar(seed_grammar, graphs_by_id[SLS2_INSTANCE_ID])
    try:
        validate_graph_against_grammar(seed_grammar, graphs_by_id[RF500_INSTANCE_ID])
    except ValueError:
        pass
    else:
        raise InductionContractError(
            "nose-ablated seed grammar unexpectedly admits RF500 before patch"
        )
    refs = tuple(
        graph_contract_ref(root, path, graph)
        for path, graph in zip(graph_paths, graphs)
    )
    alignment = align_reviewed_graphs(graphs, refs)
    proposal = select_optional_motif_proposal(
        FamilyInductionEngine().propose(alignment, graphs),
        region_type="NoseRegion",
    )
    if not isinstance(proposal, FamilyExtensionProposalV1) or (
        proposal.support.detector_id != "paired_optional_motif"
    ):
        raise InductionContractError(
            "TD3 ablation did not select the paired optional detector"
        )

    source_identity = {
        "schema_version": R3_ABLATION_BUNDLE_SCHEMA_VERSION,
        "canonical_grammar_id": canonical_grammar.grammar_id,
        "canonical_grammar_sha256": canonical_sha256(
            canonical_grammar.to_mapping()
        ),
        "seed_grammar_id": seed_grammar.grammar_id,
        "seed_grammar_sha256": canonical_sha256(seed_grammar.to_mapping()),
        "training_graph_refs": [item.to_mapping() for item in alignment.graph_refs],
        "alignment_id": alignment.alignment_id,
        "proposal_id": proposal.proposal_id,
        "selected_detector": proposal.support.to_mapping(),
        "blind_sources": [
            {
                "path": design_pdf.relative_to(root).as_posix(),
                "raw_sha256": file_sha256(design_pdf),
            },
            {
                "path": test_pdf.relative_to(root).as_posix(),
                "raw_sha256": file_sha256(test_pdf),
            },
        ],
        "representation_core": {
            "path": representation_core.relative_to(root).as_posix(),
            "raw_sha256": file_sha256(representation_core),
        },
        "explicit_review": {
            "decision": review_decision,
            "reviewer_id": reviewer_id,
            "rationale": review_rationale,
            "revision": review_revision,
        },
    }
    input_sha256 = canonical_sha256(source_identity)
    bundle_id = f"{R3_ABLATION_BUNDLE_PREFIX}.{input_sha256[:16]}"
    output = output_root if output_root.is_absolute() else root / output_root
    resolved_output = output.resolve()
    try:
        resolved_output.relative_to(root)
    except ValueError as exc:
        raise InductionContractError(
            "TD3 ablation proof output must remain inside repository"
        ) from exc
    resolved_output.mkdir(parents=True, exist_ok=True)
    target = resolved_output / bundle_id
    if target.exists():
        raise FileExistsError(f"TD3 ablation proof already exists: {target}")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=resolved_output)
    )
    try:
        _write_json(temporary / ALIGNMENT_FILE, alignment.to_mapping())
        _write_json(temporary / SEED_GRAMMAR_FILE, seed_grammar.to_mapping())
        _write_json(temporary / PROPOSAL_FILE_V1, proposal.to_mapping())
        review = make_proposal_review(
            proposal,
            decision=review_decision,
            reviewer_id=reviewer_id,
            rationale=review_rationale,
            revision=review_revision,
        )
        _write_json(temporary / REVIEW_FILE, review.to_mapping())
        outcome = review_proposal(
            seed_grammar,
            proposal,
            review,
            existing_graphs=graphs,
        )
        if (
            outcome.patch is None
            or not outcome.application.applied
            or "add_optional_motif" not in outcome.patch.operations
        ):
            raise InductionContractError(
                "accepted ablation review did not add the optional motif"
            )
        patch = outcome.patch
        patched_grammar = outcome.grammar
        for graph in graphs:
            validate_graph_against_grammar(patched_grammar, graph)
        _write_json(temporary / PATCH_FILE, patch.to_mapping())
        _write_json(temporary / PATCHED_GRAMMAR_FILE, patched_grammar.to_mapping())
        _write_json(
            temporary / PATCH_APPLICATION_FILE,
            outcome.application.to_mapping(),
        )

        blind_graph = build_lerec704_blind_graph(
            LEReC704BlindSources(
                repo_root=root,
                ipac2015_design_pdf=design_pdf,
                design_and_test_2018_pdf=test_pdf,
            ),
            family_id=canonical_grammar.family_id,
        )
        blind_path = temporary / BLIND_GRAPH_FILE
        _write_json(blind_path, blind_graph.to_mapping())
        blind_ref = GraphContractRef(
            instance_id=blind_graph.instance_id,
            graph_id=blind_graph.graph_id,
            source_path=(
                "analysis_outputs/rf_cem_family_induction_ablation/"
                f"{bundle_id}/{BLIND_GRAPH_FILE}"
            ),
            source_raw_sha256=file_sha256(blind_path),
            contract_sha256=canonical_sha256(blind_graph.to_mapping()),
        )
        blind_validation = validate_blind_instance(
            patched_grammar,
            proposal,
            blind_graph,
            blind_ref,
        )
        _write_json(
            temporary / BLIND_VALIDATION_FILE,
            blind_validation.to_mapping(),
        )
        manifest = _ablation_manifest(
            root=root,
            bundle_root=temporary,
            bundle_id=bundle_id,
            input_sha256=input_sha256,
            grammar_path=grammar_path,
            graph_paths=graph_paths,
            design_pdf=design_pdf,
            test_pdf=test_pdf,
            representation_core=representation_core,
            canonical_grammar=canonical_grammar,
            seed_grammar=seed_grammar,
            alignment=alignment,
            proposal=proposal,
            review=review,
            patch=patch,
            patched_grammar=patched_grammar,
            application=outcome.application,
            blind_graph=blind_graph,
            blind_validation=blind_validation,
        )
        _write_json(temporary / MANIFEST_FILE_V1, manifest)
        _validate_materialized_ablation_bundle(temporary, manifest)
        if target.exists():
            raise FileExistsError(f"TD3 ablation proof already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists() and temporary.parent == resolved_output:
            shutil.rmtree(temporary)
        raise
    return R3Bundle(
        path=target,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        alignment=alignment,
        proposal=proposal,
        review=review,
        patch=patch,
        patched_grammar=patched_grammar,
        patch_application=outcome.application,
        blind_graph=blind_graph,
        blind_validation=blind_validation,
        manifest=manifest,
        seed_grammar=seed_grammar,
        manifest_file=MANIFEST_FILE_V1,
        proposal_file=PROPOSAL_FILE_V1,
    )


def load_r3_bundle(path: Path) -> R3Bundle:
    """Strictly reload and cross-check one already materialized R3 bundle."""

    root = path.resolve()
    if not root.is_dir():
        raise InductionContractError(f"R3 bundle is missing: {root}")
    if (root / MANIFEST_FILE_V1).is_file():
        return load_r3_ablation_bundle(root)
    manifest = _read_mapping(root / MANIFEST_FILE)
    if manifest.get("schema_version") != R3_MANIFEST_SCHEMA_VERSION:
        raise InductionContractError("unsupported R3 bundle manifest schema")
    _validate_materialized_bundle(root, manifest)
    alignment = load_graph_alignment(root / ALIGNMENT_FILE)
    proposal = load_family_extension_proposal(root / PROPOSAL_FILE)
    review = load_proposal_review(root / REVIEW_FILE)
    patch = load_grammar_patch(root / PATCH_FILE)
    patched_grammar = load_family_grammar(root / PATCHED_GRAMMAR_FILE)
    application = load_patch_application(root / PATCH_APPLICATION_FILE)
    blind_graph = load_instance_boundary_graph(root / BLIND_GRAPH_FILE)
    blind_validation = load_blind_validation(root / BLIND_VALIDATION_FILE)
    if proposal.alignment_id != alignment.alignment_id or (
        proposal.alignment_content_sha256 != alignment.content_sha256
    ):
        raise InductionContractError("R3 proposal/alignment identity mismatch")
    if review.proposal_id != proposal.proposal_id or patch.review_id != review.review_id:
        raise InductionContractError("R3 review/patch identity mismatch")
    if application.patch_id != patch.patch_id or (
        application.after_grammar_sha256
        != canonical_sha256(patched_grammar.to_mapping())
    ):
        raise InductionContractError("R3 patch application identity mismatch")
    if blind_validation.blind_graph_ref.contract_sha256 != canonical_sha256(
        blind_graph.to_mapping()
    ):
        raise InductionContractError("R3 blind graph contract hash mismatch")
    if blind_validation.grammar_sha256 != canonical_sha256(
        patched_grammar.to_mapping()
    ):
        raise InductionContractError("R3 blind validation grammar hash mismatch")
    bundle_id = str(manifest.get("bundle_id", ""))
    input_sha256 = str(manifest.get("input_sha256", ""))
    if root.name != bundle_id or bundle_id != f"{R3_BUNDLE_PREFIX}.{input_sha256[:16]}":
        raise InductionContractError("R3 bundle path/identity mismatch")
    return R3Bundle(
        path=root,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        alignment=alignment,
        proposal=proposal,
        review=review,
        patch=patch,
        patched_grammar=patched_grammar,
        patch_application=application,
        blind_graph=blind_graph,
        blind_validation=blind_validation,
        manifest=manifest,
    )


def load_r3_ablation_bundle(path: Path) -> R3Bundle:
    """Strictly reload one v1 content-addressed TD3 ablation proof."""

    root = path.resolve()
    if not root.is_dir():
        raise InductionContractError(f"TD3 ablation bundle is missing: {root}")
    manifest = _read_mapping(root / MANIFEST_FILE_V1)
    if manifest.get("schema_version") != R3_ABLATION_MANIFEST_SCHEMA_VERSION:
        raise InductionContractError("unsupported TD3 ablation manifest schema")
    _validate_materialized_ablation_bundle(root, manifest)
    alignment = load_graph_alignment(root / ALIGNMENT_FILE)
    seed_grammar = load_family_grammar(root / SEED_GRAMMAR_FILE)
    proposal = load_family_extension_proposal(root / PROPOSAL_FILE_V1)
    if not isinstance(proposal, FamilyExtensionProposalV1):
        raise InductionContractError("TD3 ablation proposal is not v1")
    review = load_proposal_review(root / REVIEW_FILE)
    patch = load_grammar_patch(root / PATCH_FILE)
    patched_grammar = load_family_grammar(root / PATCHED_GRAMMAR_FILE)
    application = load_patch_application(root / PATCH_APPLICATION_FILE)
    blind_graph = load_instance_boundary_graph(root / BLIND_GRAPH_FILE)
    blind_validation = load_blind_validation(root / BLIND_VALIDATION_FILE)
    if proposal.alignment_id != alignment.alignment_id or (
        proposal.alignment_content_sha256 != alignment.content_sha256
    ):
        raise InductionContractError("TD3 proposal/alignment identity mismatch")
    if review.proposal_id != proposal.proposal_id or patch.review_id != review.review_id:
        raise InductionContractError("TD3 review/patch identity mismatch")
    if (
        patch.base_grammar_id != seed_grammar.grammar_id
        or patch.base_grammar_sha256 != canonical_sha256(seed_grammar.to_mapping())
        or application.patch_id != patch.patch_id
        or application.after_grammar_sha256
        != canonical_sha256(patched_grammar.to_mapping())
    ):
        raise InductionContractError("TD3 seed/patch application identity mismatch")
    if blind_validation.blind_graph_ref.contract_sha256 != canonical_sha256(
        blind_graph.to_mapping()
    ) or blind_validation.grammar_sha256 != canonical_sha256(
        patched_grammar.to_mapping()
    ):
        raise InductionContractError("TD3 blind validation identity mismatch")
    bundle_id = str(manifest.get("bundle_id", ""))
    input_sha256 = str(manifest.get("input_sha256", ""))
    if root.name != bundle_id or bundle_id != (
        f"{R3_ABLATION_BUNDLE_PREFIX}.{input_sha256[:16]}"
    ):
        raise InductionContractError("TD3 ablation bundle path/identity mismatch")
    return R3Bundle(
        path=root,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        alignment=alignment,
        proposal=proposal,
        review=review,
        patch=patch,
        patched_grammar=patched_grammar,
        patch_application=application,
        blind_graph=blind_graph,
        blind_validation=blind_validation,
        manifest=manifest,
        seed_grammar=seed_grammar,
        manifest_file=MANIFEST_FILE_V1,
        proposal_file=PROPOSAL_FILE_V1,
    )


def _manifest(
    *,
    root: Path,
    bundle_root: Path,
    bundle_id: str,
    input_sha256: str,
    grammar_path: Path,
    graph_paths: tuple[Path, ...],
    design_pdf: Path,
    test_pdf: Path,
    representation_core: Path,
    alignment: GraphAlignment,
    proposal: FamilyExtensionProposal,
    review: ProposalReview,
    patch: GrammarPatch,
    patched_grammar: FamilyGrammar,
    application: GrammarPatchApplication,
    blind_graph: InstanceBoundaryGraph,
    blind_validation: BlindValidation,
) -> dict[str, Any]:
    source_paths = (
        grammar_path,
        *graph_paths,
        design_pdf,
        test_pdf,
        representation_core,
    )
    sources = [
        {
            "path": item.relative_to(root).as_posix(),
            "raw_sha256": file_sha256(item),
            "size_bytes": item.stat().st_size,
        }
        for item in sorted(source_paths, key=lambda value: value.as_posix())
    ]
    artifacts = []
    for item in sorted(path for path in bundle_root.rglob("*") if path.is_file()):
        relative = item.relative_to(bundle_root).as_posix()
        if relative == MANIFEST_FILE:
            continue
        mapping = _read_mapping(item)
        artifacts.append(
            {
                "path": relative,
                "raw_sha256": file_sha256(item),
                "size_bytes": item.stat().st_size,
                "schema_version": mapping.get("schema_version"),
            }
        )
    return {
        "schema_version": R3_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "input_sha256": input_sha256,
        "status": "pass",
        "validation_mode": "reviewed_semantic_graphs_no_cst",
        "training_instance_ids": list(alignment.source_instance_ids),
        "blind_instance_id": blind_graph.instance_id,
        "alignment_id": alignment.alignment_id,
        "proposal_id": proposal.proposal_id,
        "review_id": review.review_id,
        "review_decision": review.decision,
        "patch_id": patch.patch_id,
        "patched_grammar_id": patched_grammar.grammar_id,
        "patched_grammar_sha256": canonical_sha256(patched_grammar.to_mapping()),
        "patch_application_id": application.application_id,
        "blind_validation_id": blind_validation.validation_id,
        "blind_classification": blind_validation.classification,
        "sources": sources,
        "artifacts": artifacts,
        "checks": [
            "alignment_reads_reviewed_semantic_side_and_type_only",
            "sls2_and_rf500_common_backbone_extracted",
            "nose_pair_proposed_as_optional_motif",
            "proposal_contains_evidence_locators_adjacency_confidence_algorithm_and_review_status",
            "pending_proposal_does_not_mutate_grammar",
            "accepted_manual_review_authorizes_explicit_hash_bound_patch",
            "all_training_instances_revalidate_after_patch",
            "held_out_real_lerec704_classified_after_induction",
            "blind_instance_not_used_for_induction",
            "representation_core_not_imported_or_modified",
            "live_cst_not_run",
        ],
        "exclusions": [
            "raw_pixels_or_step_unsupervised_semantic_discovery",
            "automatic_proposal_acceptance",
            "geometry_compilation",
            "observation_or_rf_result_contract",
            "live_cst_execution",
            "rf_physical_acceptance",
            "optimization_search",
        ],
    }


def _ablation_manifest(
    *,
    root: Path,
    bundle_root: Path,
    bundle_id: str,
    input_sha256: str,
    grammar_path: Path,
    graph_paths: tuple[Path, ...],
    design_pdf: Path,
    test_pdf: Path,
    representation_core: Path,
    canonical_grammar: FamilyGrammar,
    seed_grammar: FamilyGrammar,
    alignment: GraphAlignment,
    proposal: FamilyExtensionProposalV1,
    review: ProposalReview,
    patch: GrammarPatch,
    patched_grammar: FamilyGrammar,
    application: GrammarPatchApplication,
    blind_graph: InstanceBoundaryGraph,
    blind_validation: BlindValidation,
) -> dict[str, Any]:
    source_paths = (
        grammar_path,
        *graph_paths,
        design_pdf,
        test_pdf,
        representation_core,
    )
    sources = [
        {
            "path": item.relative_to(root).as_posix(),
            "raw_sha256": file_sha256(item),
            "size_bytes": item.stat().st_size,
        }
        for item in sorted(source_paths, key=lambda value: value.as_posix())
    ]
    artifacts = []
    for item in sorted(path for path in bundle_root.rglob("*") if path.is_file()):
        relative = item.relative_to(bundle_root).as_posix()
        if relative == MANIFEST_FILE_V1:
            continue
        mapping = _read_mapping(item)
        artifacts.append(
            {
                "path": relative,
                "raw_sha256": file_sha256(item),
                "size_bytes": item.stat().st_size,
                "schema_version": mapping.get("schema_version"),
            }
        )
    return {
        "schema_version": R3_ABLATION_MANIFEST_SCHEMA_VERSION,
        "bundle_schema_version": R3_ABLATION_BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "input_sha256": input_sha256,
        "status": "pass",
        "validation_mode": (
            "intrinsic_reviewed_graph_then_family_admission_no_cst"
        ),
        "canonical_grammar_id": canonical_grammar.grammar_id,
        "canonical_grammar_sha256": canonical_sha256(
            canonical_grammar.to_mapping()
        ),
        "seed_grammar_id": seed_grammar.grammar_id,
        "seed_grammar_sha256": canonical_sha256(seed_grammar.to_mapping()),
        "seed_ablation": {
            "removed_motif_id": "motif.nose_pair.v0",
            "removed_region_type": "NoseRegion",
            "motif_removed": True,
            "cardinality_removed": True,
            "insertion_adjacencies_removed": True,
        },
        "pre_patch_admission": {
            SLS2_INSTANCE_ID: True,
            RF500_INSTANCE_ID: False,
        },
        "training_instance_ids": list(alignment.source_instance_ids),
        "blind_instance_id": blind_graph.instance_id,
        "alignment_id": alignment.alignment_id,
        "proposal_id": proposal.proposal_id,
        "proposal_schema_version": proposal.schema_version,
        "selected_detector": proposal.support.to_mapping(),
        "proposal_score": proposal.proposal_score,
        "score_semantics": proposal.score_semantics,
        "review_id": review.review_id,
        "review_decision": review.decision,
        "patch_id": patch.patch_id,
        "patch_operation": "add_optional_motif",
        "patched_grammar_id": patched_grammar.grammar_id,
        "patched_grammar_sha256": canonical_sha256(patched_grammar.to_mapping()),
        "patch_application_id": application.application_id,
        "final_admission": {
            instance_id: True for instance_id in application.validated_instance_ids
        },
        "blind_validation_id": blind_validation.validation_id,
        "blind_classification": blind_validation.classification,
        "synthetic_single_optional_detector_fixture_status": (
            "implemented_no_cst_test_fixture"
        ),
        "sources": sources,
        "artifacts": artifacts,
        "checks": [
            "reviewed_graphs_intrinsic_valid_before_family_admission",
            "seed_grammar_nose_motif_cardinality_and_adjacencies_removed",
            "seed_grammar_admits_sls2_and_rejects_rf500_before_patch",
            "alignment_reads_reviewed_semantic_side_and_type_only",
            "sls2_and_rf500_common_backbone_extracted",
            "paired_optional_detector_selected",
            "nose_pair_proposed_as_optional_motif",
            "structured_support_is_heuristic_not_probability",
            "pending_proposal_does_not_mutate_grammar",
            "accepted_manual_review_authorizes_add_optional_motif",
            "all_training_instances_revalidate_after_patch",
            "synthetic_single_optional_detector_fixture_implemented",
            "held_out_real_lerec704_classified_after_induction",
            "blind_instance_not_used_for_induction",
            "representation_core_not_imported_or_modified",
            "live_cst_not_run",
        ],
        "exclusions": [
            "raw_pixels_or_step_unsupervised_semantic_discovery",
            "automatic_proposal_acceptance",
            "native_parameter_name_inference",
            "geometry_compilation",
            "observation_or_rf_result_contract",
            "live_cst_execution",
            "rf_physical_acceptance",
            "optimization_search",
        ],
    }


def _validate_materialized_ablation_bundle(
    root: Path,
    manifest: Mapping[str, Any],
) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise InductionContractError("TD3 ablation manifest requires artifacts")
    expected_paths = {
        ALIGNMENT_FILE,
        SEED_GRAMMAR_FILE,
        PROPOSAL_FILE_V1,
        REVIEW_FILE,
        PATCH_FILE,
        PATCHED_GRAMMAR_FILE,
        PATCH_APPLICATION_FILE,
        BLIND_GRAPH_FILE,
        BLIND_VALIDATION_FILE,
    }
    actual_paths: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            raise InductionContractError(
                "TD3 ablation artifact entry must be an object"
            )
        relative = raw.get("path")
        expected_hash = raw.get("raw_sha256")
        expected_size = raw.get("size_bytes")
        if not isinstance(relative, str) or not relative:
            raise InductionContractError("TD3 ablation artifact path is invalid")
        artifact_path = (root / relative).resolve()
        try:
            artifact_path.relative_to(root.resolve())
        except ValueError as exc:
            raise InductionContractError(
                "TD3 ablation artifact escapes bundle"
            ) from exc
        if not artifact_path.is_file():
            raise InductionContractError(
                f"TD3 ablation artifact is missing: {relative}"
            )
        if file_sha256(artifact_path) != expected_hash:
            raise InductionContractError(
                f"TD3 ablation artifact hash mismatch: {relative}"
            )
        if artifact_path.stat().st_size != expected_size:
            raise InductionContractError(
                f"TD3 ablation artifact size mismatch: {relative}"
            )
        actual_paths.add(relative)
    if actual_paths != expected_paths:
        raise InductionContractError("TD3 ablation artifact set mismatch")


def _validate_materialized_bundle(
    root: Path,
    manifest: Mapping[str, Any],
) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise InductionContractError("R3 manifest requires artifacts")
    expected_paths = {
        ALIGNMENT_FILE,
        PROPOSAL_FILE,
        REVIEW_FILE,
        PATCH_FILE,
        PATCHED_GRAMMAR_FILE,
        PATCH_APPLICATION_FILE,
        BLIND_GRAPH_FILE,
        BLIND_VALIDATION_FILE,
    }
    actual_paths: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            raise InductionContractError("R3 manifest artifact entry must be an object")
        relative = raw.get("path")
        expected_hash = raw.get("raw_sha256")
        expected_size = raw.get("size_bytes")
        if not isinstance(relative, str) or not relative:
            raise InductionContractError("R3 manifest artifact path is invalid")
        artifact_path = (root / relative).resolve()
        try:
            artifact_path.relative_to(root.resolve())
        except ValueError as exc:
            raise InductionContractError("R3 artifact escapes bundle") from exc
        if not artifact_path.is_file():
            raise InductionContractError(f"R3 artifact is missing: {relative}")
        if file_sha256(artifact_path) != expected_hash:
            raise InductionContractError(f"R3 artifact hash mismatch: {relative}")
        if artifact_path.stat().st_size != expected_size:
            raise InductionContractError(f"R3 artifact size mismatch: {relative}")
        actual_paths.add(relative)
    if actual_paths != expected_paths:
        raise InductionContractError("R3 manifest artifact set mismatch")


def _write_json(path: Path, mapping: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"R3 artifact already exists: {path}")
    path.write_bytes(canonical_json_bytes(mapping) + b"\n")


def _read_mapping(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InductionContractError(f"cannot read R3 JSON artifact: {path}") from exc
    if not isinstance(value, Mapping):
        raise InductionContractError(f"R3 JSON artifact must be an object: {path}")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _inside(root: Path, value: Path, label: str) -> Path:
    path = value if value.is_absolute() else root / value
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise InductionContractError(f"{label} must be inside repository") from exc
    if not resolved.is_file():
        raise InductionContractError(f"{label} is missing: {resolved}")
    return resolved


__all__ = [
    "ALIGNMENT_FILE",
    "BLIND_GRAPH_FILE",
    "BLIND_VALIDATION_FILE",
    "MANIFEST_FILE",
    "MANIFEST_FILE_V1",
    "PATCHED_GRAMMAR_FILE",
    "PATCH_APPLICATION_FILE",
    "PATCH_FILE",
    "PROPOSAL_FILE",
    "PROPOSAL_FILE_V1",
    "SEED_GRAMMAR_FILE",
    "R3Bundle",
    "R3SourceSet",
    "R3_BUNDLE_PREFIX",
    "R3_BUNDLE_SCHEMA_VERSION",
    "R3_MANIFEST_SCHEMA_VERSION",
    "R3_ABLATION_BUNDLE_PREFIX",
    "R3_ABLATION_BUNDLE_SCHEMA_VERSION",
    "R3_ABLATION_MANIFEST_SCHEMA_VERSION",
    "REVIEW_FILE",
    "load_r3_bundle",
    "load_r3_ablation_bundle",
    "write_r3_ablation_bundle",
    "write_r3_bundle",
]
