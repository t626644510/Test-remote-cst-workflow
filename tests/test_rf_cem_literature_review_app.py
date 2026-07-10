import copy
import json
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.geometry_candidate import (
    build_sls2_geometry_candidate,
)
from rf_cem.literature_semantics.review_app import Sls2LiteratureReviewApp


pytestmark = pytest.mark.no_cst


PARAMETERS = {
    "L": 680.0,
    "l": 188.671,
    "r": 50.0,
    "R": 249.901,
    "a": 125.232,
    "b": 70.2322,
}


def test_prepare_server_writes_bound_html_and_small_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, package, candidate = _write_bundle(tmp_path)
    session_root = tmp_path / "session"
    app = Sls2LiteratureReviewApp(
        bundle_root=tmp_path,
        corpus_manifest=manifest,
        session_root=session_root,
        candidate=candidate,
    )
    monkeypatch.setattr(app, "_materialize_candidate", _fake_materializer(tmp_path))

    launch = app.prepare_server(port=0, token="t" * 32)
    try:
        session = json.loads(
            (session_root / "review_session.v1.json").read_text(encoding="utf-8")
        )
        html = launch.html_path.read_text(encoding="utf-8")
        assert launch.review_url.startswith("http://127.0.0.1:")
        assert "Layer 1 · Evidence" in html
        assert "Layer 3 · Geometry projection" in html
        assert session["review_scope"]["paper_id"] == "sls2"
        assert len(json.dumps(session)) < 20_000
        assert launch.initial_step_path.name == "fake.step"
    finally:
        launch.server.stop()


def test_parameter_iteration_is_human_edit_with_paper_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, package, candidate = _write_bundle(tmp_path)
    app = Sls2LiteratureReviewApp(
        bundle_root=tmp_path,
        corpus_manifest=manifest,
        session_root=tmp_path / "session",
        candidate=candidate,
    )
    monkeypatch.setattr(app, "_materialize_candidate", _fake_materializer(tmp_path))
    app._baseline_model = _model("paper baseline", PARAMETERS)  # integration state
    app._latest_model = copy.deepcopy(app._baseline_model)
    edited = {**PARAMETERS, "R": 251.0}

    report = app.preview(
        {"review_decisions": {}},
        {"reason": "parameter_iteration", "parameters": edited},
    )

    assert report["parameter_tuple"]["origin"] == "human_preview_edit"
    assert report["parameter_tuple"]["source_refs"] == []
    assert report["paper_baseline"]["parameter_tuple"]["values"] == PARAMETERS
    assert report["preview"]["baseline"]["label"] == "paper baseline"
    assert report["preview"]["previous"]["label"] == "paper baseline"
    assert report["review_items"][0]["human_review_status"] == "pending"


def _fake_materializer(root: Path):
    step = root / "fake.step"
    step.write_text("ISO-10303-21;", encoding="ascii")

    def materialize(candidate, *, parent_candidate):
        values = candidate["parameter_tuple"]["values"]
        report = {
            "schema_version": "literature_geometry_generation.v0",
            "candidate_id": candidate["candidate_id"],
            "review_status": candidate["review"]["human_review_status"],
            "parameter_tuple": copy.deepcopy(candidate["parameter_tuple"]),
            "preview": {
                "baseline": None,
                "previous": None,
                "current": _model(candidate["candidate_id"], values),
            },
            "geometry": {"step_path": str(step), "unit": "mm"},
            "features": [],
            "udsg": {},
            "validation": {"pass": True, "generated": True},
            "integrity": copy.deepcopy(candidate["integrity"]),
        }
        if candidate["parameter_tuple"]["origin"] == "human_preview_edit":
            report["lineage"] = copy.deepcopy(candidate["lineage"])
            report["paper_baseline"] = copy.deepcopy(candidate["paper_baseline"])
        return report

    return materialize


def _model(label: str, values: dict) -> dict:
    return {
        "label": label,
        "candidate_id": label,
        "profile_points": [
            [-values["L"] / 2.0, values["r"]],
            [0.0, values["R"]],
            [values["L"] / 2.0, values["r"]],
        ],
        "mesh": {
            "vertices": [[0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            "triangles": [[0, 1, 2]],
        },
        "step_path": "fake.step",
    }


def _write_bundle(root: Path):
    paper = root / "paper"
    paper.mkdir()
    package = _semantic_package()
    candidate = build_sls2_geometry_candidate(
        package,
        candidate_id="sls2.test.cavity_1",
        parameters=PARAMETERS,
        evidence_refs=["sls2_p8_spline", "sls2_p9_material_table"],
        semantic_paths=["classification", "text_evidence[0]", "text_evidence[1]"],
    )
    (paper / "semantics.json").write_text(
        json.dumps(package, ensure_ascii=False), encoding="utf-8"
    )
    (paper / "summary.json").write_text(
        json.dumps({"title": "SLS-2 test", "summary": "test"}), encoding="utf-8"
    )
    (paper / "source.json").write_text(
        json.dumps({"schema_version": "rf_cem.arxiv_source_manifest.v1"}),
        encoding="utf-8",
    )
    (paper / "draft.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "expert_prior.draft.v0", "review": {"patch_items": []}},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "literature_corpus_audit.v0",
        "title": "SLS-2 review test",
        "papers": [
            {
                "id": "sls2",
                "title": "SLS-2 test",
                "source_manifest": "paper/source.json",
                "paper_summary": "paper/summary.json",
                "literature_semantics": "paper/semantics.json",
                "draft_prior": "paper/draft.yaml",
                "evidence_images": [],
            }
        ],
    }
    return manifest, package, candidate


def _semantic_package() -> dict:
    return {
        "schema_version": "literature_semantics.v0",
        "request_context": {
            "design_intent": "Preview the paper's symmetric SLS-2 geometry without CST.",
            "frequency_target_mhz": 499.654,
            "operating_regime": "normal_conducting",
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
            "exclude": ["live CST", "RF performance claim"],
        },
        "evidence_sources": [
            {
                "id": "paper_sls2",
                "source_type": "paper_pdf",
                "title": "Multi-objective shape optimization of radio frequency cavities",
            }
        ],
        "text_evidence": [
            {
                "id": "sls2_p8_spline",
                "paper_id": "paper_sls2",
                "page": 8,
                "evidence_summary": "Figure 3 fixes L, l and r and defines R, a and b.",
            },
            {
                "id": "sls2_p9_material_table",
                "paper_id": "paper_sls2",
                "page": 9,
                "evidence_summary": "One candidate reports the coherent R, a and b row.",
            },
        ],
        "classification": {
            "cavity_family": "elliptical",
            "cell_count": "single",
            "beta_class": "beta_1",
            "confidence": 0.95,
            "evidence_refs": ["sls2_p8_spline", "sls2_p9_material_table"],
            "human_review_status": "pending",
        },
    }
