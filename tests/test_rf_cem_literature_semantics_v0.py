import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.audit import build_audit_html
from rf_cem.literature_semantics.prior_mapper import build_draft_prior, merge_draft_prior, read_prior_yaml
from rf_cem.literature_semantics.types import PriorDraftError
from rf_cem.literature_semantics.validator import validate_semantic_package
from rf_cem.parametric_geometry.expert_prior import DEFAULT_PRIOR_PATH


pytestmark = pytest.mark.no_cst


def test_missing_provenance_review_confidence_fails_validation():
    package = _semantic_package()
    package["shape_motifs"][0].pop("confidence")

    issues = validate_semantic_package(package)

    assert any(issue.severity == "error" and "confidence" in issue.path for issue in issues)


def test_valid_srf_package_builds_deterministic_draft_prior():
    package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    draft_a = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)
    draft_b = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)

    assert draft_a == draft_b
    assert draft_a["schema_version"] == "expert_prior.draft.v0"
    variants = {item["variant"] for item in draft_a["candidate_shape_priors"]}
    assert "free_equator_smooth" in variants
    assert "iris_torus_exact" in draft_a["grammar"]["variant_policy"]["discourage_variants"]
    assert all(item["source_refs"] for item in draft_a["review"]["patch_items"])


def test_pending_draft_cannot_merge_when_review_is_required():
    package = _semantic_package(status="pending")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)

    with pytest.raises(PriorDraftError, match="unreviewed"):
        merge_draft_prior(base_prior, draft, semantic_package=package, require_reviewed=True)


def test_reviewed_srf_draft_merges_only_supported_prior_fields():
    package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)
    _review_all_patches(draft)

    merged = merge_draft_prior(base_prior, draft, semantic_package=package, require_reviewed=True)

    assert merged["grammar"]["variant_policy"]["default_selected_variant"] == "free_equator_smooth"
    assert merged["grammar"]["variant_policy"]["curve_selection"]["equator"]["free_equator_smooth"] == "local_nurbs_crown"
    assert "literature_semantics" in merged
    records = merged["literature_semantics"]["records"]
    assert records[0]["source_evidence"]["required_for_all_nonbaseline_fields"] is True


def test_reviewed_nc_package_suggests_controlled_nose_reentrant_candidate():
    package = _semantic_package(regime="normal_conducting", family="nose_cone", motif_name="reentrant_nose", status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)
    _review_all_patches(draft)
    merged = merge_draft_prior(base_prior, draft, semantic_package=package, require_reviewed=True)

    variants = {item["variant"] for item in draft["candidate_shape_priors"]}
    assert "iris_torus_exact" in variants
    assert merged["grammar"]["variant_policy"]["default_selected_variant"] == "iris_torus_exact"
    assert merged["grammar"]["variant_policy"]["curve_selection"]["nose"]["iris_torus_exact"] == (
        "smooth_semicircle_then_reverse_quarter_arc"
    )
    assert "HOM" not in str(merged["grammar"]["variant_policy"])


def test_image_only_hard_numeric_range_is_rejected():
    package = _semantic_package(status="accepted")
    package["parameter_ranges"][0]["source_refs"] = ["img1"]
    package["parameter_ranges"][0]["range_type"] = "hard"

    issues = validate_semantic_package(package)

    assert any(issue.severity == "error" and "image-only numeric ranges" in issue.message for issue in issues)


def test_single_source_numeric_range_is_downgraded_to_soft_metadata():
    package = _semantic_package(status="accepted")
    package["parameter_ranges"][0]["range_type"] = "hard"
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    issues = validate_semantic_package(package)
    draft = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)

    assert any(issue.severity == "warning" and "single-source" in issue.message for issue in issues)
    assert draft["derived_parameter_candidates"][0]["range_type"] == "soft"
    assert draft["derived_parameter_candidates"][0]["merge_status"] == "audit_metadata_only"


def test_unsupported_hom_coupler_content_is_audit_warning_only():
    package = _semantic_package(status="accepted")
    package["optimization_objectives"].append(
        {
            "objective_name": "HOM damping with coupler",
            "source_refs": ["txt1"],
            "confidence": 0.4,
            "scope": "out-of-scope evidence",
            "applicability": {"geometry_scope": "axisymmetric_single_cell_rf_vacuum"},
            "human_review_status": "accepted_as_soft_only",
        }
    )
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    issues = validate_semantic_package(package)
    draft = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)

    assert any("HOM" in issue.message or "coupler" in issue.message for issue in issues)
    executable_targets = [item["target_path"] for item in draft["review"]["patch_items"]]
    assert not any("HOM" in target or "coupler" in target for target in executable_targets)


def test_audit_html_contains_required_sections_and_review_status():
    package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior_ref=DEFAULT_PRIOR_PATH, base_prior=base_prior)

    html = build_audit_html(package, draft)

    assert "Corpus summary" in html
    assert "Evidence cards" in html
    assert "Prior diff" in html
    assert "Candidate gallery" in html
    assert "Review controls" in html
    assert "accepted" in html


def test_mixed_srf_nose_package_is_audit_only():
    package = _semantic_package(regime="superconducting", family="nose_cone", status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    issues = validate_semantic_package(package)
    draft = build_draft_prior(package, base_prior=base_prior)

    assert any("audit-only" in issue.message for issue in issues)
    assert draft["grammar"]["executable_eligible"] is False
    assert [item["target_path"] for item in draft["review"]["patch_items"]] == ["literature_semantics"]


def test_normal_conducting_elliptical_maps_to_current_smooth_equator_branch():
    package = _semantic_package(regime="normal_conducting", family="elliptical", status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    draft = build_draft_prior(package, base_prior=base_prior)

    assert draft["grammar"]["branch_id"] == "nc_elliptical"
    assert draft["review"]["patch_items"][0]["value"] == "free_equator_smooth"


def test_curve_region_conflict_is_audit_only():
    package = _semantic_package(regime="normal_conducting", family="elliptical")
    package["curve_priors"][0]["curve_region"] = "nose"
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    issues = validate_semantic_package(package)
    draft = build_draft_prior(package, base_prior=base_prior)

    assert any("audit-only" in issue.message for issue in issues)
    assert draft["grammar"]["executable_eligible"] is False
    assert [item["target_path"] for item in draft["review"]["patch_items"]] == [
        "literature_semantics"
    ]


def test_multicell_literature_is_audit_only_for_single_cell_grammar():
    package = _semantic_package(cell_count="multi", status="accepted")
    for section in (
        "named_features",
        "shape_motifs",
        "curve_priors",
        "parameter_ranges",
        "optimization_objectives",
        "physical_constraints",
    ):
        for item in package[section]:
            item["applicability"]["cell_count"] = "multi"
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    draft = build_draft_prior(package, base_prior=base_prior)

    assert draft["grammar"]["executable_eligible"] is False
    assert len(draft["review"]["patch_items"]) == 1


def test_semantic_acceptance_does_not_auto_accept_generated_patches():
    package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)

    draft = build_draft_prior(package, base_prior=base_prior)

    assert {item["human_review_status"] for item in draft["review"]["patch_items"]} == {"pending"}
    assert all(item["review_basis"] for item in draft["review"]["patch_items"])


def test_review_status_only_edit_preserves_integrity_and_allows_merge():
    package = _semantic_package(status="pending")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior=base_prior)

    _review_all_patches(draft)
    merged = merge_draft_prior(base_prior, draft, semantic_package=package)

    assert merged["grammar"]["variant_policy"]["default_selected_variant"] == "free_equator_smooth"


def test_patch_value_tampering_breaks_integrity():
    package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior=base_prior)
    _review_all_patches(draft)
    draft["review"]["patch_items"][1]["value"] = ["not_a_real_variant"]

    with pytest.raises(PriorDraftError, match="immutable_draft_sha256"):
        merge_draft_prior(base_prior, draft, semantic_package=package)


def test_review_basis_status_tampering_breaks_integrity():
    package = _semantic_package(status="pending")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior=base_prior)
    _review_all_patches(draft)
    draft["review"]["patch_items"][0]["review_basis"][0][
        "human_review_status"
    ] = "accepted"

    with pytest.raises(PriorDraftError, match="immutable_draft_sha256"):
        merge_draft_prior(base_prior, draft, semantic_package=package)


def test_stale_base_or_semantic_package_hash_blocks_merge():
    package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior=base_prior)
    _review_all_patches(draft)

    changed_base = dict(base_prior)
    changed_base["human_notes"] = ["changed after draft"]
    with pytest.raises(PriorDraftError, match="base_prior_sha256"):
        merge_draft_prior(changed_base, draft, semantic_package=package)

    changed_package = dict(package)
    changed_package["request_context"] = {**package["request_context"], "frequency_target_mhz": 501.0}
    with pytest.raises(PriorDraftError, match="semantic_package_sha256"):
        merge_draft_prior(base_prior, draft, semantic_package=changed_package)


def test_sequential_literature_merges_preserve_both_provenance_records():
    first_package = _semantic_package(status="accepted")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    first_draft = build_draft_prior(first_package, base_prior=base_prior)
    _review_all_patches(first_draft)
    first_merged = merge_draft_prior(
        base_prior,
        first_draft,
        semantic_package=first_package,
    )

    second_package = copy.deepcopy(first_package)
    second_package["evidence_sources"][0]["title"] = "Independent second source"
    second_draft = build_draft_prior(second_package, base_prior=first_merged)
    _review_all_patches(second_draft)
    second_merged = merge_draft_prior(
        first_merged,
        second_draft,
        semantic_package=second_package,
    )

    records = second_merged["literature_semantics"]["records"]
    assert len(records) == 2
    assert len({record["semantic_package_sha256"] for record in records}) == 2


def test_audit_uses_actual_schema_review_words():
    package = _semantic_package(status="pending")
    base_prior = read_prior_yaml(DEFAULT_PRIOR_PATH)
    draft = build_draft_prior(package, base_prior=base_prior)

    html = build_audit_html(package, draft)

    assert "accepted_as_soft_only" in html
    assert "rejected" in html
    assert "<code>accept</code>" not in html


def _review_all_patches(draft: dict, status: str = "accepted") -> None:
    for item in draft["review"]["patch_items"]:
        item["human_review_status"] = status


def _semantic_package(
    *,
    regime: str = "superconducting",
    family: str = "elliptical",
    motif_name: str = "smooth_equator",
    status: str = "pending",
    cell_count: str = "single",
) -> dict:
    return {
        "schema_version": "literature_semantics.v0",
        "request_context": {
            "design_intent": f"500 MHz {regime} single-cell cavity",
            "frequency_target_mhz": 500.0,
            "operating_regime": regime,
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
            "exclude": ["HOM", "coupler", "thermal", "structural", "multipacting"],
        },
        "evidence_sources": [
            {
                "id": "paper1",
                "source_type": "paper",
                "title": "500 MHz cavity design note",
                "year": 2024,
                "venue": "JACoW",
                "license": "uploaded_for_review",
            }
        ],
        "text_evidence": [
            {
                "id": "txt1",
                "paper_id": "paper1",
                "page": 1,
                "section": "design",
                "short_excerpt": "The cavity uses Req and Rir as design variables.",
                "excerpt_hash": "sha256:text1",
            }
        ],
        "image_evidence": [
            {
                "id": "img1",
                "paper_id": "paper1",
                "page": 2,
                "figure_id": "fig1",
                "caption": "Cross-section showing iris and equator.",
                "bbox": [0, 0, 100, 100],
                "crop_ref": "figures/fig1.png",
            }
        ],
        "classification": {
            "cavity_family": family,
            "cell_count": cell_count,
            "beta_class": "beta_1",
            "frequency_band_mhz": {"min": 450.0, "max": 550.0},
            "confidence": 0.82,
            "evidence_refs": ["txt1"],
        },
        "named_features": [
            {
                "feature_name": "equator",
                "aliases": ["Req", "equator radius"],
                "presence": True,
                "source_refs": ["txt1", "img1"],
                "confidence": 0.78,
                "scope": "single-cell axisymmetric RF vacuum",
                "applicability": {"operating_regime": regime, "cavity_family": family},
                "human_review_status": status,
            }
        ],
        "shape_motifs": [
            {
                "name": motif_name,
                "polarity": "preferred",
                "source_refs": ["txt1"],
                "confidence": 0.74,
                "scope": "shape prior only",
                "applicability": {"operating_regime": regime, "cavity_family": family},
                "human_review_status": status,
            }
        ],
        "curve_priors": [
            {
                "curve_region": "nose" if family in {"nose_cone", "reentrant"} else "equator",
                "allowed_curve_types": ["arc"] if family in {"nose_cone", "reentrant"} else ["ellipse", "local_spline"],
                "preferred_forms": ["arc"] if family in {"nose_cone", "reentrant"} else ["ellipse", "local_spline"],
                "forbidden_forms": [],
                "source_refs": ["txt1"],
                "confidence": 0.73,
                "scope": "existing RF-CEM curve_selection names",
                "applicability": {"operating_regime": regime, "cavity_family": family},
                "human_review_status": status,
            }
        ],
        "parameter_ranges": [
            {
                "parameter_name": "shared_equator_crown_delta_r_mm",
                "semantic_role": "smooth equator crown seed",
                "range": {"min": -3.0, "max": 3.0},
                "unit": "mm",
                "range_type": "soft",
                "source_refs": ["txt1"],
                "confidence": 0.7,
                "scope": "candidate initialization only",
                "applicability": {"operating_regime": regime, "cavity_family": family},
                "human_review_status": status,
            }
        ],
        "optimization_objectives": [
            {
                "objective_name": "maintain_frequency",
                "source_refs": ["txt1"],
                "confidence": 0.7,
                "scope": "audit metadata only",
                "applicability": {"operating_regime": regime, "cavity_family": family},
                "human_review_status": status,
            }
        ],
        "physical_constraints": [
            {
                "constraint_id": "axisymmetric_single_cell_only",
                "constraint_type": "scope",
                "statement": "Use only axisymmetric single-cell RF vacuum grammar.",
                "source_refs": ["txt1"],
                "confidence": 0.86,
                "scope": "MVP geometry scope",
                "applicability": {"geometry_scope": "axisymmetric_single_cell_rf_vacuum"},
                "human_review_status": status,
            }
        ],
    }
