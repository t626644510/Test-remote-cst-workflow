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

from rf_cem.literature_semantics.corpus_audit import (
    CorpusAuditError,
    build_corpus_audit_html,
    write_corpus_audit_html,
)
from rf_cem.literature_semantics.prior_mapper import immutable_draft_sha256
from rf_cem.literature_semantics.types import canonical_sha256


pytestmark = pytest.mark.no_cst


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_corpus_audit_embeds_images_escapes_text_and_compares_papers(tmp_path: Path):
    first = _write_paper_bundle(
        tmp_path,
        "paper-a",
        title="<script>alert(1)</script>",
        curve_forms=["ellipse"],
    )
    second = _write_paper_bundle(
        tmp_path,
        "paper-b",
        title="Second & paper",
        curve_forms=["local_nurbs_crown"],
    )
    manifest = {
        "schema_version": "literature_corpus_audit.v0",
        "title": "RF <Corpus>",
        "generated_at": "2026-07-10T12:00:00Z",
        "papers": [first, second],
        "cross_paper_findings": [
            {"topic": "iris treatment", "finding": "Compare <both> papers", "paper_ids": ["paper-a", "paper-b"]}
        ],
        "warnings": ["Do not <merge> without review"],
    }
    manifest_path = tmp_path / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    html = build_corpus_audit_html(tmp_path, manifest_path)

    assert "RF-CEM Literature Corpus Audit" not in html  # The manifest title is authoritative.
    assert "RF &lt;Corpus&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Do not &lt;merge&gt; without review" in html
    assert "Compare &lt;both&gt; papers" in html
    assert "Corpus / integrity / validation" in html
    assert "Paper summary" in html
    assert "Key findings" in html
    assert "Limitations" in html
    assert "Semantic groups" in html
    assert "Patch provenance" in html
    assert "Evidence gallery" in html
    assert "data:image/png;base64," in html
    assert "curve_priors.equator has different claims" in html
    assert "grammar.variant_policy.curve_selection.equator" in html
    assert "Semantic package validation passed without issues." in html


def test_corpus_audit_can_render_one_strictly_isolated_paper(tmp_path: Path):
    first = _write_paper_bundle(
        tmp_path, "paper-a", title="Normal-conducting", curve_forms=["ellipse"]
    )
    second = _write_paper_bundle(
        tmp_path, "paper-b", title="Superconducting", curve_forms=["spline"]
    )

    html = build_corpus_audit_html(
        tmp_path,
        _manifest(first, second),
        paper_id="paper-a",
    )

    assert "Normal-conducting · isolated audit" in html
    assert "Superconducting" not in html
    assert "curve_priors.equator has different claims" not in html

    with pytest.raises(CorpusAuditError, match="exactly one"):
        build_corpus_audit_html(
            tmp_path,
            _manifest(first, second),
            paper_id="missing",
        )


def test_corpus_audit_rejects_traversal_for_structured_resources(tmp_path: Path):
    outside = tmp_path.parent / "outside-summary.json"
    outside.write_text("{}", encoding="utf-8")
    manifest = _manifest(
        {
            "id": "unsafe",
            "paper_summary": "../outside-summary.json",
            "literature_semantics": "missing.json",
            "draft_prior": "missing.yaml",
            "evidence_images": [],
        }
    )

    with pytest.raises(CorpusAuditError, match="path escapes bundle root"):
        build_corpus_audit_html(tmp_path, manifest)


def test_corpus_audit_rejects_traversal_for_image_resources(tmp_path: Path):
    paper = _write_paper_bundle(tmp_path, "paper", title="Safe", curve_forms=["ellipse"])
    paper["evidence_images"] = [{"path": "../outside.png"}]

    with pytest.raises(CorpusAuditError, match="path escapes bundle root"):
        build_corpus_audit_html(tmp_path, _manifest(paper))


def test_oversized_image_is_reported_but_not_embedded(tmp_path: Path):
    paper = _write_paper_bundle(tmp_path, "paper", title="Safe", curve_forms=["ellipse"])

    html = build_corpus_audit_html(tmp_path, _manifest(paper), max_image_bytes=16)

    assert "image exceeds max_image_bytes=16" in html
    assert "data:image/png;base64," not in html
    assert "Image unavailable" in html


def test_write_corpus_audit_reports_missing_and_checksum_failed_resources(tmp_path: Path):
    paper = _write_paper_bundle(tmp_path, "paper", title="Safe", curve_forms=["ellipse"])
    paper["paper_summary_sha256"] = "sha256:" + "0" * 64
    paper["draft_prior"] = "paper/missing.yaml"
    output = tmp_path / "reports" / "corpus_audit.html"

    write_corpus_audit_html(output, tmp_path, _manifest(paper))
    html = output.read_text(encoding="utf-8")

    assert "checksum mismatch" in html
    assert "resource is not a file: missing.yaml" in html
    assert html.startswith("<!doctype html>")


def test_source_pdf_and_draft_semantic_drift_are_integrity_errors(tmp_path: Path):
    paper = _write_paper_bundle(tmp_path, "paper", title="Safe", curve_forms=["ellipse"])
    (tmp_path / "paper" / "source.pdf").write_bytes(b"%PDF-1.4\nchanged")
    semantic_path = tmp_path / "paper" / "literature_semantics.v0.json"
    semantics = json.loads(semantic_path.read_text(encoding="utf-8"))
    semantics["request_context"]["frequency_target_mhz"] = 501.0
    semantic_path.write_text(json.dumps(semantics), encoding="utf-8")

    html = build_corpus_audit_html(tmp_path, _manifest(paper))

    assert "source manifest checksum mismatch" in html
    assert "draft semantic_package_sha256 does not match" in html


def _manifest(*papers: dict) -> dict:
    return {
        "schema_version": "literature_corpus_audit.v0",
        "title": "Audit",
        "generated_at": "2026-07-10T12:00:00Z",
        "papers": list(papers),
        "cross_paper_findings": [],
        "warnings": [],
    }


def _write_paper_bundle(
    root: Path,
    paper_id: str,
    *,
    title: str,
    curve_forms: list[str],
) -> dict:
    directory = root / paper_id
    directory.mkdir()
    summary = {
        "title": title,
        "citation": f"Citation for {title}",
        "selection_rationale": "Selected for a test fixture",
        "methodology": ["Axisymmetric eigenmode study"],
        "summary": f"Summary for {title}",
        "key_findings": ["RF geometry finding", {"frequency": "500 MHz"}],
        "limitations": ["Single-cell evidence only"],
    }
    semantics = _semantic_package(paper_id, curve_forms)
    draft = {
        "schema_version": "expert_prior.draft.v0",
        "review": {
            "merge_blocked": True,
            "patch_items": [
                {
                    "id": f"{paper_id}.patch.iris",
                    "target_path": "grammar.variant_policy.curve_selection.equator",
                    "value": curve_forms[0],
                    "source_refs": [f"{paper_id}.text"],
                    "confidence": 0.75,
                    "human_review_status": "pending",
                    "rationale": "Literature evidence <requires review>",
                }
            ],
        },
        "integrity": {
            "algorithm": "sha256",
            "semantic_package_sha256": canonical_sha256(semantics),
            "base_prior_sha256": "sha256:" + "b" * 64,
        },
    }
    draft["integrity"]["immutable_draft_sha256"] = immutable_draft_sha256(draft)
    source_pdf = b"%PDF-1.4\nfixture"
    source_pdf_sha256 = hashlib.sha256(source_pdf).hexdigest()
    version = 1 if paper_id == "paper-a" else 2
    source_manifest = {
        "schema_version": "rf_cem.arxiv_source_manifest.v1",
        "source": {
            "arxiv_id": f"1234.5678v{version}",
            "version": version,
            "abs_url": f"https://arxiv.org/abs/{paper_id}",
        },
        "metadata": {"title": title, "authors": ["A. Author", "B. Author"]},
        "pdf": {
            "path": "source.pdf",
            "size_bytes": len(source_pdf),
            "sha256": source_pdf_sha256,
        },
    }
    (directory / "paper_summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    (directory / "literature_semantics.v0.json").write_text(
        json.dumps(semantics, ensure_ascii=False),
        encoding="utf-8",
    )
    (directory / "expert_prior.draft.v0.yaml").write_text(
        yaml.safe_dump(draft, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (directory / "source_manifest.json").write_text(
        json.dumps(source_manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (directory / "source.pdf").write_bytes(source_pdf)
    (directory / "figure.png").write_bytes(PNG_1X1)
    return {
        "id": paper_id,
        "arxiv_id": source_manifest["source"]["arxiv_id"],
        "version": source_manifest["source"]["version"],
        "title": title,
        "authors": source_manifest["metadata"]["authors"],
        "source_url": source_manifest["source"]["abs_url"],
        "pdf_sha256": source_manifest["pdf"]["sha256"],
        "source_manifest": f"{paper_id}/source_manifest.json",
        "paper_summary": f"{paper_id}/paper_summary.json",
        "literature_semantics": f"{paper_id}/literature_semantics.v0.json",
        "draft_prior": f"{paper_id}/expert_prior.draft.v0.yaml",
        "evidence_images": [
            {
                "path": f"{paper_id}/figure.png",
                "page": 3,
                "figure_id": "Fig. 1 <cross-section>",
                "caption": "Iris & equator profile",
                "evidence_refs": [f"{paper_id}.image"],
                "sha256": hashlib.sha256(PNG_1X1).hexdigest(),
            }
        ],
    }


def _semantic_package(paper_id: str, curve_forms: list[str]) -> dict:
    text_ref = f"{paper_id}.text"
    image_ref = f"{paper_id}.image"
    common = {
        "source_refs": [text_ref],
        "confidence": 0.75,
        "scope": "axisymmetric single-cell evidence",
        "applicability": {
            "operating_regime": "superconducting",
            "cavity_family": "elliptical",
        },
        "human_review_status": "pending",
    }
    return {
        "schema_version": "literature_semantics.v0",
        "request_context": {
            "design_intent": "500 MHz superconducting single-cell cavity",
            "frequency_target_mhz": 500.0,
            "operating_regime": "superconducting",
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
            "exclude": ["HOM", "coupler", "thermal", "structural", "multipacting"],
        },
        "evidence_sources": [{"id": paper_id, "source_type": "paper", "title": paper_id}],
        "text_evidence": [
            {
                "id": text_ref,
                "paper_id": paper_id,
                "page": 2,
                "section": "geometry",
                "short_excerpt": "The iris uses a smooth curve.",
                "excerpt_hash": "sha256:text",
            }
        ],
        "image_evidence": [
            {
                "id": image_ref,
                "paper_id": paper_id,
                "page": 3,
                "figure_id": "Fig. 1",
                "caption": "Cavity cross-section",
                "bbox": [0, 0, 100, 100],
                "crop_ref": f"{paper_id}/figure.png",
            }
        ],
        "classification": {
            "cavity_family": "elliptical",
            "cell_count": "single",
            "beta_class": "beta_1",
            "frequency_band_mhz": {"min": 450.0, "max": 550.0},
            "confidence": 0.8,
            "evidence_refs": [text_ref],
        },
        "named_features": [
            {
                "feature_name": "iris",
                "aliases": ["Rir"],
                "presence": True,
                **common,
            }
        ],
        "shape_motifs": [{"name": "smooth_equator", "polarity": "preferred", **common}],
        "curve_priors": [
            {
                "curve_region": "equator",
                "allowed_curve_types": curve_forms,
                "preferred_forms": curve_forms,
                "forbidden_forms": [],
                **common,
            }
        ],
        "parameter_ranges": [],
        "optimization_objectives": [],
        "physical_constraints": [],
    }
