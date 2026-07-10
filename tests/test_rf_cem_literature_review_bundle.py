import base64
import hashlib
import json
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.review_bundle import (
    ReviewBundleError,
    ReviewBundleLoader,
)


pytestmark = pytest.mark.no_cst

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_review_payload_has_three_layers_images_and_small_session_seed(tmp_path: Path):
    manifest = _write_bundle(tmp_path)
    projection = {
        "id": "sls2-cavity-1",
        "parameters_mm": {"L": 680.0, "l": 188.671, "r": 50.0},
        "human_review_status": "pending",
    }

    loader = ReviewBundleLoader(tmp_path)
    payload = loader.build_payload(
        manifest, paper_id="sls2", geometry_projection=projection
    )
    seed = loader.session_seed(payload)

    assert payload["schema_version"] == "literature_review_payload.v1"
    assert {item["layer"] for item in payload["review_items"]} == {
        "evidence",
        "semantics",
        "geometry",
    }
    assert payload["papers"][0]["evidence_layers"]["gallery"][0]["data_uri"].startswith(
        "data:image/png;base64,"
    )
    assert payload["safety"]["live_cst"] is False
    assert payload["safety"]["production_prior_mutated"] is False
    classification = next(
        item for item in payload["review_items"] if item["section"] == "classification"
    )
    assert classification["label"] == "classification: elliptical / single / beta_1"
    assert classification["semantic_path"] == "classification"
    assert seed["review_scope"]["payload_sha256"] == payload["payload_sha256"]
    assert "data_uri" not in json.dumps(seed)


def test_review_bundle_rejects_escape_and_reports_bad_image(tmp_path: Path):
    manifest = _write_bundle(tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    unsafe = json.loads(json.dumps(manifest))
    unsafe["papers"][0]["paper_summary"] = "../outside.json"

    with pytest.raises(ReviewBundleError, match="escapes bundle root"):
        ReviewBundleLoader(tmp_path).build_payload(unsafe, paper_id="sls2")

    (tmp_path / "paper" / "figure.png").write_bytes(b"not a png")
    payload = ReviewBundleLoader(tmp_path).build_payload(manifest, paper_id="sls2")
    image = payload["papers"][0]["evidence_layers"]["gallery"][0]
    assert image["integrity_status"] == "error"
    assert image["data_uri"] == ""


def test_review_bundle_requires_exact_paper_id(tmp_path: Path):
    manifest = _write_bundle(tmp_path)

    with pytest.raises(ReviewBundleError, match="exactly one"):
        ReviewBundleLoader(tmp_path).build_payload(manifest, paper_id="missing")


def test_review_bundle_keeps_all_corpus_papers_with_isolated_ids(tmp_path: Path):
    manifest = _write_bundle(tmp_path)
    comparison = dict(manifest["papers"][0])
    comparison["id"] = "tesla"
    comparison["title"] = "TESLA comparison"
    manifest["papers"].insert(0, comparison)

    payload = ReviewBundleLoader(tmp_path).build_payload(
        manifest, paper_id="sls2", geometry_projection={"id": "candidate-1"}
    )

    assert [paper["id"] for paper in payload["papers"]] == ["tesla", "sls2"]
    ids = [item["id"] for item in payload["review_items"]]
    assert len(ids) == len(set(ids))
    assert any(item_id.startswith("tesla::semantics::") for item_id in ids)
    assert any(item_id.startswith("sls2::geometry::") for item_id in ids)


def _write_bundle(root: Path) -> dict:
    paper = root / "paper"
    paper.mkdir()
    semantics = _semantics()
    summary = {"title": "SLS-2", "summary": "test"}
    source = {"schema_version": "rf_cem.arxiv_source_manifest.v1"}
    draft = {
        "schema_version": "expert_prior.draft.v0",
        "review": {
            "patch_items": [
                {
                    "id": "patch-1",
                    "target_path": "grammar.variant_policy.enabled",
                    "value": ["nc_elliptical"],
                    "human_review_status": "pending",
                }
            ]
        },
    }
    (paper / "semantics.json").write_text(
        json.dumps(semantics, ensure_ascii=False), encoding="utf-8"
    )
    (paper / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (paper / "source.json").write_text(json.dumps(source), encoding="utf-8")
    (paper / "draft.yaml").write_text(
        yaml.safe_dump(draft, sort_keys=False), encoding="utf-8"
    )
    (paper / "figure.png").write_bytes(PNG)
    return {
        "schema_version": "literature_corpus_audit.v0",
        "title": "Review",
        "papers": [
            {
                "id": "sls2",
                "source_manifest": "paper/source.json",
                "paper_summary": "paper/summary.json",
                "literature_semantics": "paper/semantics.json",
                "draft_prior": "paper/draft.yaml",
                "evidence_images": [
                    {
                        "path": "paper/figure.png",
                        "sha256": hashlib.sha256(PNG).hexdigest(),
                        "figure_id": "Figure 3",
                    }
                ],
            }
        ],
    }


def _semantics() -> dict:
    return {
        "schema_version": "literature_semantics.v0",
        "request_context": {
            "design_intent": "500 MHz normal-conducting single cavity",
            "frequency_target_mhz": 499.654,
            "operating_regime": "normal_conducting",
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
            "exclude": ["live_cst"],
        },
        "evidence_sources": [],
        "text_evidence": [{"id": "text-1", "short_excerpt": "symmetric cavity"}],
        "image_evidence": [{"id": "image-1", "figure_id": "Figure 3"}],
        "classification": {
            "cavity_family": "elliptical",
            "cell_count": "single",
            "beta_class": "beta_1",
            "confidence": 0.9,
            "evidence_refs": ["text-1"],
            "human_review_status": "pending",
        },
        "named_features": [
            {
                "feature_name": "equator",
                "presence": "present",
                "source_refs": ["text-1"],
                "confidence": 0.9,
                "scope": "paper",
                "applicability": {"operating_regime": "normal_conducting"},
                "human_review_status": "pending",
            }
        ],
        "shape_motifs": [],
        "curve_priors": [],
        "parameter_ranges": [],
        "optimization_objectives": [],
        "physical_constraints": [],
    }
