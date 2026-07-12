from __future__ import annotations

import re
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.interactive_reviewer import (
    build_interactive_review_html,
    write_interactive_review_html,
)


pytestmark = pytest.mark.no_cst


@pytest.fixture(autouse=True)
def _small_embedded_plotly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep renderer tests small while exercising the offline embed path."""
    monkeypatch.setattr(
        "plotly.offline.get_plotlyjs",
        lambda: "window.Plotly={react:function(){return Promise.resolve();}};",
    )


def test_interactive_reviewer_has_three_layers_review_controls_and_geometry_views() -> None:
    html = build_interactive_review_html(_payload(), "local-secret")

    assert html.startswith("<!doctype html>")
    assert "Layer 1 · Evidence" in html
    assert "Layer 2 · Semantic candidates" in html
    assert "Layer 3 · Geometry projection" in html
    assert 'data-subview="geometry"' in html
    assert 'data-subview="features"' in html
    assert 'data-subview="udsg"' in html
    assert "OK / 接受" in html
    assert "Soft OK / 仅软建议" in html
    assert "Reject / 拒绝" in html
    assert "Needs evidence / 补证据" in html
    assert "中文备注 / review_note" in html
    assert "全局中文备注" in html
    assert "Add structured semantic / 新增结构化语义" in html
    assert "Review summary" in html


def test_interactive_reviewer_uses_strict_same_origin_api_contract() -> None:
    html = build_interactive_review_html(_payload(), "local-secret")

    for endpoint in (
        "/api/session",
        "/api/review-events",
        "/api/manual-items",
        "/api/preview",
        "/api/helper2-review",
        "/api/paper-source",
    ):
        assert endpoint in html
    assert '"X-Review-Token":TOKEN' in html
    assert "expected_revision" in html
    assert "accepted_as_soft_only" in html
    assert "needs_more_evidence" in html
    assert "human_review_status:" not in html
    assert "?token=" not in html
    assert "credentials:\"same-origin\"" in html
    assert "connect-src 'self'" in html
    assert "frame-src blob:" in html
    assert "style-src 'unsafe-inline'" in html
    assert "style-src 'nonce-" not in html


def test_interactive_reviewer_embeds_no_remote_assets_and_escapes_script_data() -> None:
    payload = _payload()
    payload["title"] = 'Unsafe </title><script id="title-attack">alert(1)</script>'
    payload["semantic_candidates"][0]["claim"] = "</script><img src=x onerror=alert(2)>"

    html = build_interactive_review_html(payload, "token</script><script>alert(3)</script>")

    assert '<script id="title-attack">' not in html
    assert "<img src=x onerror=alert(2)>" not in html
    assert "token</script>" not in html
    assert "\\u003c/script\\u003e" in html
    assert "&lt;/title&gt;&lt;script" in html
    assert not re.search(r"<(?:script|img)[^>]+src=[\"']https?://", html, re.IGNORECASE)
    assert "cdn.plot.ly" not in html
    assert "default-src 'none'" in html
    assert "object-src 'none'" in html


def test_interactive_reviewer_exposes_six_mm_parameters_and_preview_payload() -> None:
    html = build_interactive_review_html(_payload(), "local-secret")

    assert "SLS-2 parameter iteration / 参数迭代" in html
    assert 'const PARAMETER_KEYS=["L","l","r","R","a","b"]' in html
    assert 'name="${esc(key)}" type="number"' in html
    assert 'reason="parameter_iteration"' not in html  # passed as an argument, never interpolated into a URL
    assert 'generatePreview("parameter_iteration"' in html
    assert "parameters:parameterValues" in html
    assert "baseline" in html
    assert "previous" in html
    assert "current" in html
    assert "profile_points" in html
    assert "feature_candidates" in html
    assert "Geometry refs" in html
    assert "Confidence / status" in html
    assert "Helper2 面审核" in html
    assert "PDF 原文同页" in html
    assert "literature_semantic_candidate_view.v1" in html
    assert "配置应用建议 / Draft patches" in html
    assert "Generated geometry hypothesis" not in html
    assert "UDSG preview" not in html


def test_interactive_reviewer_accepts_adapter_review_items_and_nested_evidence() -> None:
    payload = _payload()
    payload["papers"] = [
        {
            "source_manifest": {"id": "paper-from-manifest", "title": "Manifest title"},
            "evidence": {
                "text": [{"id": "text-1", "text": "geometry claim"}],
                "images": [{"id": "image-1", "caption": "Figure evidence"}],
                "gallery": [],
            },
        }
    ]
    payload["review_items"] = [
        {"item_id": "paper::classification", "layer": "semantics", "kind": "classification", "content": {"family": "elliptical"}},
        {"item_id": "paper::patch", "layer": "semantics", "kind": "draft_prior_patch", "content": {"target_path": "metadata.x"}},
        {"item_id": "paper::evidence", "layer": "evidence", "title": "Evidence decision", "content": {"page": 4}},
        {"item_id": "paper::geometry", "layer": "geometry", "title": "Geometry decision", "content": {"model_type": "axisymmetric"}},
    ]

    html = build_interactive_review_html(payload, "local-secret")

    for item_id in ("paper::classification", "paper::patch", "paper::evidence", "paper::geometry"):
        assert item_id in html
    assert "paper-from-manifest" in html
    assert "geometry claim" in html
    assert "Figure evidence" in html
    assert "draft_prior_patch" in html


def test_write_interactive_review_html_is_utf8_and_replaces_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "review.html"
    output.parent.mkdir(parents=True)
    output.write_text("stale", encoding="utf-8")

    write_interactive_review_html(output, _payload(), "local-secret")

    written = output.read_text(encoding="utf-8")
    assert written.startswith("<!doctype html>")
    assert "中文备注" in written
    assert "stale" not in written
    assert not (output.parent / ".review.html.tmp").exists()


@pytest.mark.parametrize("token", ["", "   ", None])
def test_interactive_reviewer_requires_non_empty_token(token: object) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_interactive_review_html(_payload(), token)  # type: ignore[arg-type]


def test_interactive_reviewer_requires_mapping_payload() -> None:
    with pytest.raises(TypeError, match="mapping"):
        build_interactive_review_html([], "local-secret")  # type: ignore[arg-type]


def _payload() -> dict:
    triangle = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 0, 1]], "triangles": [[0, 1, 2]]}
    return {
        "title": "RF-CEM 文献语义审计",
        "papers": [
            {
                "id": "sls2",
                "title": "SLS-2 candidate #1",
                "evidence": [{"id": "figure-3", "page": 6, "caption": "对称轴对称椭圆轮廓"}],
            }
        ],
        "semantic_candidates": [
            {
                "id": "sls2-ellipse",
                "paper_id": "sls2",
                "section": "shape_motifs",
                "name": "symmetric elliptical cavity",
                "human_review_status": "pending",
                "evidence_refs": ["figure-3"],
            }
        ],
        "geometry_projection": {
            "parameter_tuple": {
                "unit": "mm",
                "values": {"L": 680.0, "l": 188.671, "r": 50.0, "R": 249.901, "a": 125.232, "b": 70.2322},
            },
            "preview": {
                "baseline": None,
                "previous": {"label": "previous", "mesh": triangle, "profile_points": [[0, 50], [1, 60]]},
                "current": {"label": "current", "mesh": triangle, "profile_points": [[0, 50], [1, 62]]},
            },
            "geometry": {"model_type": "axisymmetric_single_cell", "axis": "z"},
            "features": [{"id": "equator", "type": "EquatorRegion", "segment_refs": ["seg-3"]}],
            "udsg": {"schema_version": "literature_geometry_udsg.preview.v0", "nodes": []},
            "validation": {"pass": True, "generated": True},
        },
    }
