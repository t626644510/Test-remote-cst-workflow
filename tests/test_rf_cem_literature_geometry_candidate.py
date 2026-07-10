import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.geometry_candidate import (
    LiteratureGeometryCandidateError,
    Sls2GeometryParameters,
    build_sls2_geometry_candidate,
    build_sls2_preview,
    build_sls2_preview_variant,
    build_sls2_profile,
    candidate_content_sha256,
    candidate_snapshot_sha256,
    generate_sls2_step,
    immutable_candidate_sha256,
    validate_geometry_candidate,
)
from rf_cem.parametric_geometry.core.backend_cadquery import CadQueryGeometryBackend


pytestmark = pytest.mark.no_cst


PUBLISHED_PARAMETERS = {
    "L": 680.0,
    "l": 188.671,
    "r": 50.0,
    "R": 249.901,
    "a": 125.232,
    "b": 70.2322,
}


def test_candidate_binds_coherent_tuple_evidence_and_semantic_hash():
    package = _semantic_package()
    candidate = _candidate(package)

    validate_geometry_candidate(candidate, package)

    assert candidate["schema_version"] == "literature_geometry_candidate.v0"
    assert candidate["generator"]["id"] == "symmetric_elliptical_four_quarter_arcs.v0"
    assert candidate["parameter_tuple"]["values"] == PUBLISHED_PARAMETERS
    assert candidate["parameter_tuple"]["derived"]["h"] == pytest.approx(151.329)
    assert candidate["parameter_tuple"]["source_refs"] == ["sls2_p8_spline", "sls2_p9_material_table"]
    assert candidate["parameter_tuple"]["source_roles"] == {
        "paper_figure_3_symmetric_parameterization": "sls2_p8_spline",
        "published_candidate_row": "sls2_p9_material_table",
    }
    assert "Figure 3" in candidate["approximation"]["paper_definition"]
    assert "reconstruction hypothesis" in candidate["approximation"]["reconstruction_hypothesis"]
    assert candidate["execution_policy"] == {
        "mode": "preview_only",
        "production_merge_allowed": False,
        "live_cst_allowed": False,
    }
    assert candidate["integrity"]["immutable_candidate_sha256"] == immutable_candidate_sha256(candidate)
    assert candidate["integrity"]["candidate_content_sha256"] == candidate_content_sha256(candidate)


def test_review_status_and_chinese_note_are_mutable_but_snapshot_is_bound():
    package = _semantic_package()
    candidate = _candidate(package)
    immutable_hash = immutable_candidate_sha256(candidate)
    original_snapshot = candidate_snapshot_sha256(candidate)

    candidate["review"]["human_review_status"] = "accepted_as_soft_only"
    candidate["review"]["review_note"] = "尺寸组可用于几何预览，不代表射频性能复现。"
    candidate["review"]["reviewer"] = "human"

    validate_geometry_candidate(candidate, package)
    assert immutable_candidate_sha256(candidate) == immutable_hash
    assert candidate_snapshot_sha256(candidate) != original_snapshot


def test_parameter_or_generator_tampering_breaks_candidate_integrity():
    package = _semantic_package()
    candidate = _candidate(package)
    candidate["approximation"]["exact_conic_in_step"] = True

    with pytest.raises(LiteratureGeometryCandidateError, match="candidate_content_sha256"):
        validate_geometry_candidate(candidate, package)


def test_stale_semantic_package_breaks_candidate_binding():
    package = _semantic_package()
    candidate = _candidate(package)
    changed_package = copy.deepcopy(package)
    changed_package["evidence_sources"][0]["title"] = "changed"

    with pytest.raises(LiteratureGeometryCandidateError, match="semantic_package_sha256"):
        validate_geometry_candidate(candidate, changed_package)


def test_candidate_rejects_unknown_evidence_and_semantic_path():
    package = _semantic_package()
    with pytest.raises(LiteratureGeometryCandidateError, match="unknown evidence_refs"):
        build_sls2_geometry_candidate(
            package,
            candidate_id="sls2.candidate_1",
            parameters=PUBLISHED_PARAMETERS,
            evidence_refs=["missing"],
            semantic_paths=["classification"],
        )
    with pytest.raises(LiteratureGeometryCandidateError, match="unknown semantic path"):
        build_sls2_geometry_candidate(
            package,
            candidate_id="sls2.candidate_1",
            parameters=PUBLISHED_PARAMETERS,
            evidence_refs=["sls2_p8_spline", "sls2_p9_material_table"],
            semantic_paths=["parameter_ranges[99]"],
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"L": 377.342}, "L must be greater than 2\\*l"),
        ({"r": 0.0}, "r must be greater than zero"),
        ({"a": 151.329}, "0 < a < h"),
        ({"b": 0.0}, "0 < b < R-r"),
        ({"b": 199.901}, "0 < b < R-r"),
    ],
)
def test_parameter_guards_block_invalid_geometry(override, message):
    values = {**PUBLISHED_PARAMETERS, **override}
    with pytest.raises(LiteratureGeometryCandidateError, match=message):
        Sls2GeometryParameters.from_mapping(values)


def test_profile_has_four_mirrored_quarter_ellipse_approximations():
    profile = build_sls2_profile(PUBLISHED_PARAMETERS, samples_per_quarter=25)
    segments = profile["segments"]
    nurbs = [segment for segment in segments if segment["kind"] == "nurbs"]

    assert len(segments) == 6
    assert len(nurbs) == 4
    assert all(len(segment["curve"]["sampled_points"]) == 25 for segment in nurbs)
    assert profile["points"][0] == {"z_mm": -340.0, "r_mm": 50.0}
    assert profile["points"][-1] == {"z_mm": 340.0, "r_mm": 50.0}
    assert segments[1]["end"]["z"] == pytest.approx(-125.232)
    assert segments[1]["end"]["r"] == pytest.approx(179.6688)
    assert segments[2]["end"]["z"] == pytest.approx(0.0, abs=1e-12)
    assert segments[2]["end"]["r"] == pytest.approx(249.901)
    points = [(point["z_mm"], point["r_mm"]) for point in profile["points"]]
    assert len(points) == 99
    for left, right in zip(points, reversed(points)):
        assert left[0] == pytest.approx(-right[0], abs=1e-10)
        assert left[1] == pytest.approx(right[1], abs=1e-10)


def test_pure_preview_exposes_profile_parameters_guards_features_and_udsg():
    package = _semantic_package()
    preview = build_sls2_preview(_candidate(package), package)

    assert preview["schema_version"] == "literature_geometry_preview.v0"
    assert preview["guards"]["L_gt_2l"] is True
    assert preview["guards"]["a_between_0_and_h"] is True
    assert preview["profile"]["points"][49]["z_mm"] == pytest.approx(0.0, abs=1e-12)
    assert {feature["id"] for feature in preview["features"]} == {
        "feature.beam_pipe_left",
        "feature.ellipse_wall_left",
        "feature.equator",
        "feature.ellipse_wall_right",
        "feature.beam_pipe_right",
    }
    assert preview["udsg"]["edges"][-1]["relation"] == "revolves_about_z"


def test_generate_api_records_step_mesh_brep_and_both_candidate_hashes(tmp_path):
    package = _semantic_package()
    candidate = _candidate(package)
    output_step = tmp_path / "sls2_candidate_1.step"
    output_report = tmp_path / "generation.json"
    backend = _FakeBackend()

    report = generate_sls2_step(
        candidate,
        package,
        output_step=output_step,
        output_report=output_report,
        backend=backend,
    )

    assert backend.calls[0]["profile_segments"][1]["curve"]["sampled_points"]
    assert report["validation"]["pass"] is True
    assert report["validation"]["generated"]["brep_valid"] is True
    assert report["preview"]["baseline"] is None
    assert report["preview"]["previous"] is None
    assert report["preview"]["current"]["mesh"]["triangles"]
    assert report["integrity"]["immutable_candidate_sha256"] == immutable_candidate_sha256(candidate)
    assert report["integrity"]["candidate_snapshot_sha256"] == candidate_snapshot_sha256(candidate)
    assert json.loads(output_report.read_text(encoding="utf-8"))["schema_version"] == "literature_geometry_generation.v0"


def test_rejected_candidate_cannot_generate(tmp_path):
    package = _semantic_package()
    candidate = _candidate(package)
    candidate["review"]["human_review_status"] = "rejected"

    with pytest.raises(LiteratureGeometryCandidateError, match="rejected"):
        generate_sls2_step(candidate, package, output_step=tmp_path / "rejected.step", backend=_FakeBackend())


def test_human_preview_variant_keeps_paper_baseline_without_claiming_edited_values(tmp_path):
    package = _semantic_package()
    parent = _candidate(package)
    edited_values = {**PUBLISHED_PARAMETERS, "R": 252.0, "a": 123.0}
    variant = build_sls2_preview_variant(
        parent,
        package,
        candidate_id="sls2.candidate_1.iteration_1",
        parameters=edited_values,
        review_note="人工调整 R 与 a，用于外形比较。",
    )

    validate_geometry_candidate(variant, package, parent_candidate=parent)
    assert variant["parameter_tuple"]["origin"] == "human_preview_edit"
    assert variant["parameter_tuple"]["source_refs"] == []
    assert "source_roles" not in variant["parameter_tuple"]
    assert "sls2_p9_material_table" not in json.dumps(variant["parameter_tuple"])
    assert variant["parameter_tuple"]["value_provenance"]["published_value_claim"] is False
    assert variant["lineage"]["parent_immutable_candidate_sha256"] == parent["integrity"]["immutable_candidate_sha256"]
    assert variant["paper_baseline"]["parameter_tuple"]["values"] == PUBLISHED_PARAMETERS
    assert variant["paper_baseline"]["parameter_tuple"]["source_roles"]["published_candidate_row"] == (
        "sls2_p9_material_table"
    )
    assert variant["integrity"]["candidate_content_sha256"] == candidate_content_sha256(variant)

    preview = build_sls2_preview(variant, package, parent_candidate=parent)
    assert preview["features"][0]["evidence_relation"] == "paper_baseline_context_only"
    assert preview["udsg"]["edges"][0]["relation"] == "supports_published_baseline"
    report = generate_sls2_step(
        variant,
        package,
        output_step=tmp_path / "iteration_1.step",
        backend=_FakeBackend(),
        parent_candidate=parent,
    )
    assert report["validation"]["pass"] is True
    assert report["preview"]["baseline"]["provenance"] == "published_candidate"
    assert report["preview"]["previous"]["candidate_id"] == parent["candidate_id"]
    assert report["paper_baseline"]["parameter_tuple"]["values"] == PUBLISHED_PARAMETERS


def test_second_human_iteration_preserves_root_paper_tuple_and_binds_immediate_parent():
    package = _semantic_package()
    published = _candidate(package)
    first = build_sls2_preview_variant(
        published,
        package,
        candidate_id="sls2.candidate_1.iteration_1",
        parameters={**PUBLISHED_PARAMETERS, "R": 252.0},
    )
    second = build_sls2_preview_variant(
        first,
        package,
        candidate_id="sls2.candidate_1.iteration_2",
        parameters={**PUBLISHED_PARAMETERS, "R": 252.0, "b": 72.0},
    )

    validate_geometry_candidate(second, package, parent_candidate=first)
    assert second["lineage"]["parent_candidate_id"] == first["candidate_id"]
    assert second["lineage"]["parent_candidate_content_sha256"] == first["integrity"]["candidate_content_sha256"]
    assert second["paper_baseline"] == first["paper_baseline"]
    assert second["paper_baseline"]["candidate_id"] == published["candidate_id"]


def test_real_cadquery_worker_generates_valid_no_seed_step(tmp_path):
    if importlib.util.find_spec("cadquery") is None or importlib.util.find_spec("OCP") is None:
        pytest.skip("CadQuery/OCP is not installed")
    package = _semantic_package()
    candidate = _candidate(package)

    report = generate_sls2_step(candidate, package, output_step=tmp_path / "sls2_candidate_1.step")

    assert report["validation"]["pass"] is True, report["validation"]
    assert report["kernel_report"]["body_selection"]["mode"] == "generated_without_seed"
    assert report["kernel_report"]["baseline"] is None
    assert report["kernel_report"]["curve_generation"]["mode"] == "cadquery_curve_segments"
    assert len(report["kernel_report"]["curve_generation"]["approximations"]) == 4
    assert all(item["max_degree"] == 5 for item in report["kernel_report"]["curve_generation"]["approximations"])
    assert Path(report["geometry"]["step_path"]).stat().st_size > 0


def test_existing_seed_recover_api_still_forwards_the_seed_step(tmp_path):
    backend = _RecordingCadQueryBackend()
    seed = tmp_path / "seed.step"
    output = tmp_path / "generated.step"

    report = backend.recover(
        step_file=seed,
        output_step=output,
        axis="z",
        body_index=2,
        profile_points=[(-1.0, 2.0), (1.0, 2.0)],
        profile_segments=[],
        deflection_mm=0.25,
    )

    assert report["step_file"] == seed
    assert report["output_step"] == output
    assert report["body_index"] == 2


def _candidate(package):
    return build_sls2_geometry_candidate(
        package,
        candidate_id="sls2.candidate_1",
        parameters=PUBLISHED_PARAMETERS,
        evidence_refs=["sls2_p8_spline", "sls2_p9_material_table"],
        semantic_paths=["classification", "text_evidence[0]", "text_evidence[1]"],
    )


def _semantic_package():
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
                "evidence_summary": "The symmetric study fixes L, l and r and defines R, a and b as design variables.",
            },
            {
                "id": "sls2_p9_material_table",
                "paper_id": "paper_sls2",
                "page": 9,
                "evidence_summary": "One published candidate reports the coherent R, a and b row.",
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


class _FakeBackend:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        Path(kwargs["output_step"]).write_text("ISO-10303-21;", encoding="ascii")
        axial_values = [point[0] for point in kwargs["profile_points"]]
        radial_extent = max(point[1] for point in kwargs["profile_points"])
        return {
            "schema_version": "cadquery_recovery_kernel.v0",
            "body_selection": {"mode": "generated_without_seed", "body_index": None, "solid_count": 0},
            "baseline": None,
            "generated": {
                "bbox_mm": {
                    "xmin": -radial_extent,
                    "xmax": radial_extent,
                    "ymin": -radial_extent,
                    "ymax": radial_extent,
                    "zmin": min(axial_values),
                    "zmax": max(axial_values),
                },
                "volume_mm3": 1.0,
                "surface_area_mm2": 1.0,
                "brep_valid": True,
            },
            "generated_mesh": {
                "vertices": [[0.0, 0.0, -340.0], [1.0, 0.0, 0.0], [0.0, 0.0, 340.0]],
                "triangles": [[0, 1, 2]],
            },
            "curve_generation": {
                "mode": "cadquery_curve_segments",
                "fallbacks": [],
                "approximations": [
                    {"segment_id": f"ellipse_{index}", "input_source": "sampled_points"}
                    for index in range(4)
                ],
            },
            "output_step": str(kwargs["output_step"]),
        }


class _RecordingCadQueryBackend(CadQueryGeometryBackend):
    def _run_worker(self, **kwargs):
        return kwargs
