import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.build_500mhz_parametric_geometry import main as parametric_main
from rf_cem.design_package import BaselinePaths
from rf_cem.parametric_geometry.expert_prior import ExpertPriorError, load_expert_prior, validate_expert_prior
from rf_cem.parametric_geometry.analysis.feature_projector import build_feature_bindings, derive_key_parameters
from rf_cem.parametric_geometry.analysis.profile_primitives import extract_profile_primitives
from rf_cem.parametric_geometry.ingest.axis_estimator import verify_axis
from rf_cem.parametric_geometry.ingest.step_loader import load_geometry_manifest
from rf_cem.parametric_geometry.ingest.vacuum_selector import select_target_body


pytestmark = pytest.mark.no_cst

BASELINE = Path("Appendix/500MHz_baseline")


def _paths() -> BaselinePaths:
    if not BASELINE.exists():
        pytest.skip("Appendix/500MHz_baseline fixture is not available")
    if importlib.util.find_spec("cadquery") is None or importlib.util.find_spec("OCP") is None:
        pytest.skip("CadQuery/OCP is not installed")
    if importlib.util.find_spec("plotly") is None:
        pytest.skip("Plotly is not installed")
    paths = BaselinePaths.from_appendix(BASELINE)
    paths.validate()
    return paths


def _labels(paths: BaselinePaths) -> dict:
    return yaml.safe_load(paths.reviewed_feature_labels.read_text(encoding="utf-8")) or {}


def test_parametric_step_ingest_500mhz_and_manual_body_selection():
    paths = _paths()
    manifest = load_geometry_manifest(paths.geometry_manifest)

    assert manifest["model_summary"]["solid_count"] == 1
    assert manifest["model_summary"]["face_count"] == 22
    selection = select_target_body(manifest, 0)
    assert selection.body_ref == "solid:S0001"
    assert selection.confidence == 1.0
    with pytest.raises(ValueError, match="out of range"):
        select_target_body(manifest, 1)


def test_axis_and_feature_projection_use_reviewed_labels():
    paths = _paths()
    manifest = load_geometry_manifest(paths.geometry_manifest)
    labels = _labels(paths)
    prior, prior_metadata = load_expert_prior(appendix=paths.appendix)

    axis = verify_axis(manifest, "z")
    bindings = build_feature_bindings(labels, prior)
    parameters = derive_key_parameters(manifest, labels, prior)

    assert prior["schema_version"] == "expert_prior.v0"
    assert any(source["kind"] == "case" for source in prior_metadata["sources"])
    assert axis.accepted is True
    assert axis.detected_axis == "z"
    binding_types = {binding.feature_type for binding in bindings}
    assert {
        "RFVacuumVolume",
        "BeamPipeLeft",
        "BeamPipeRight",
        "BeamAperture",
        "BeamExit",
        "NoseCone",
        "EquatorRegion",
        "TransitionBlend",
    }.issubset(binding_types)
    assert parameters["beam_pipe_radius_left"]["value"] == pytest.approx(44.0)
    assert parameters["beam_pipe_length_left"]["value"] == pytest.approx(110.0)
    assert parameters["equator_radius"]["value"] == pytest.approx(232.1930001)
    assert parameters["nose_radius_left"]["value"] > 0
    assert parameters["blend_radius_left"]["value"] > 0
    primitives = extract_profile_primitives(manifest, labels)
    nose_arcs = [item for item in primitives["primitives"] if item["feature_type"] == "NoseCone" and item["kind"] == "arc"]
    blend_arcs = [item for item in primitives["primitives"] if item["feature_type"] == "TransitionBlend" and item["kind"] == "arc"]
    assert {round(item["major_radius"], 6) for item in nose_arcs} == {54.0, 74.0}
    assert {round(item["minor_radius"], 6) for item in nose_arcs} == {10.0}
    assert any(item["major_radius"] == pytest.approx(157.14235271385) for item in blend_arcs)
    assert any(item["minor_radius"] == pytest.approx(75.05064728615) for item in blend_arcs)


def test_expert_prior_validation_and_cli_override(tmp_path):
    paths = _paths()
    override = tmp_path / "override_prior.v0.yaml"
    override.write_text(
        """
schema_version: expert_prior.v0
model_family: axisymmetric_single_cell_rf_vacuum
feature_mappings:
  BeamPipeLeft:
    human_description: CLI override for left beam pipe mapping.
    parameter_ids:
      - custom_left_beam_parameter
    segment_ids:
      - seg_beam_pipe_left
custom_unknown_field:
  preserved: true
""",
        encoding="utf-8",
    )

    prior, metadata = load_expert_prior(appendix=paths.appendix, explicit_prior=override)

    assert any(source["kind"] == "explicit" for source in metadata["sources"])
    assert prior["custom_unknown_field"]["preserved"] is True
    assert prior["feature_mappings"]["BeamPipeLeft"]["parameter_ids"] == ["custom_left_beam_parameter"]
    broken = dict(prior)
    broken["feature_mappings"] = {"BeamPipeLeft": {"rule_id": "broken"}}
    with pytest.raises(ExpertPriorError, match="parameter_ids"):
        validate_expert_prior(broken)


def test_cli_writes_parametric_geometry_design_package(tmp_path):
    paths = _paths()
    output_dir = tmp_path / "parametric_geometry_500mhz"

    rc = parametric_main(
        [
            "--appendix",
            str(paths.appendix),
            "--output-dir",
            str(output_dir),
            "--target-body-index",
            "0",
            "--axis",
            "z",
        ]
    )

    assert rc == 0
    expected = [
        output_dir / "geometry" / "baseline_vacuum.step",
        output_dir / "geometry" / "generated_vacuum.step",
        output_dir / "geometry" / "profile_preview.svg",
        output_dir / "geometry" / "section_debug.json",
        output_dir / "metadata" / "parametric_geometry.v0.json",
        output_dir / "metadata" / "reverse_fit_report.json",
        output_dir / "metadata" / "geometry_validation.json",
        output_dir / "metadata" / "source_evidence.json",
        output_dir / "metadata" / "udsg.v0.json",
        output_dir / "metadata" / "resolved_expert_prior.v0.yaml",
        output_dir / "metadata" / "resolved_expert_prior.v0.json",
        output_dir / "translator" / "cst_payload.json",
        output_dir / "translator" / "mapping_table_patch.json",
        output_dir / "audit" / "parametric_geometry_audit.html",
        output_dir / "audit" / "variant_comparison.html",
        output_dir / "variant_index.json",
        output_dir / "variants" / "iris_torus_exact" / "geometry" / "generated_vacuum.step",
        output_dir / "variants" / "expanded_smooth_nose" / "geometry" / "generated_vacuum.step",
        output_dir / "variants" / "free_equator_smooth" / "geometry" / "generated_vacuum.step",
        output_dir / "variants" / "manual_equator_inset_3mm" / "geometry" / "generated_vacuum.step",
        output_dir / "variants" / "manual_equator_bulge_3mm" / "geometry" / "generated_vacuum.step",
        output_dir / "variants" / "manual_equator_wide_soft" / "geometry" / "generated_vacuum.step",
    ]
    for path in expected:
        assert path.exists(), path

    parametric = json.loads((output_dir / "metadata" / "parametric_geometry.v0.json").read_text(encoding="utf-8"))
    resolved_prior = yaml.safe_load((output_dir / "metadata" / "resolved_expert_prior.v0.yaml").read_text(encoding="utf-8"))
    validation = json.loads((output_dir / "metadata" / "geometry_validation.json").read_text(encoding="utf-8"))
    section_debug = json.loads((output_dir / "geometry" / "section_debug.json").read_text(encoding="utf-8"))
    payload = json.loads((output_dir / "translator" / "cst_payload.json").read_text(encoding="utf-8"))
    audit_html = (output_dir / "audit" / "parametric_geometry_audit.html").read_text(encoding="utf-8")
    actions = json.loads(
        (output_dir / "translator" / "rf_cem_artifacts" / "generated" / "cst_actions.json").read_text(encoding="utf-8")
    )
    variant_index = json.loads((output_dir / "variant_index.json").read_text(encoding="utf-8"))
    exact_parametric = json.loads(
        (output_dir / "variants" / "iris_torus_exact" / "metadata" / "parametric_geometry.v0.json").read_text(encoding="utf-8")
    )
    smooth_parametric = json.loads(
        (output_dir / "variants" / "expanded_smooth_nose" / "metadata" / "parametric_geometry.v0.json").read_text(encoding="utf-8")
    )
    free_equator_parametric = json.loads(
        (output_dir / "variants" / "free_equator_smooth" / "metadata" / "parametric_geometry.v0.json").read_text(encoding="utf-8")
    )
    inset_parametric = json.loads(
        (output_dir / "variants" / "manual_equator_inset_3mm" / "metadata" / "parametric_geometry.v0.json").read_text(encoding="utf-8")
    )
    bulge_parametric = json.loads(
        (output_dir / "variants" / "manual_equator_bulge_3mm" / "metadata" / "parametric_geometry.v0.json").read_text(encoding="utf-8")
    )

    assert parametric["schema_version"] == "parametric_geometry.v0"
    assert parametric["model_type"] == "axisymmetric_rf_vacuum_single_cell"
    assert parametric["axis"]["name"] == "z"
    assert parametric["target_body"]["body_ref"] == "solid:S0001"
    assert parametric["source"]["resolved_expert_prior"].endswith("resolved_expert_prior.v0.yaml")
    assert resolved_prior["resolved_prior"]["schema_version"] == "expert_prior.v0"
    assert resolved_prior["metadata"]["precedence"] == ["explicit", "case", "built_in"]
    assert parametric["variant"]["name"] == "free_equator_smooth"
    assert "nose_radius_left" in parametric["named_parameters"]
    assert "blend_radius_right" in parametric["named_parameters"]
    assert {item["name"] for item in variant_index["variants"]} == {
        "iris_torus_exact",
        "expanded_smooth_nose",
        "free_equator_smooth",
        "manual_equator_inset_3mm",
        "manual_equator_bulge_3mm",
        "manual_equator_wide_soft",
    }
    assert variant_index["selected_variant"] == "free_equator_smooth"
    assert any(segment["kind"] == "arc" and "NoseCone" in segment["feature_refs"] for segment in exact_parametric["profile"]["segments"])
    assert any(segment["kind"] == "arc" and "TransitionBlend" in segment["feature_refs"] for segment in exact_parametric["profile"]["segments"])
    assert any(segment["kind"] == "nurbs" and "NoseCone" in segment["feature_refs"] for segment in smooth_parametric["profile"]["segments"])
    assert any(segment["id"] == "seg_equator_free_crown" and segment["kind"] == "nurbs" for segment in free_equator_parametric["profile"]["segments"])
    assert any(key.startswith("arc_radius__seg_blend_left") for key in exact_parametric["derived_parameters"])
    assert any(key.startswith("nurbs_cp0_z__seg_nose_left_smooth_nurbs") for key in smooth_parametric["derived_parameters"])
    assert any(key.startswith("nurbs_cp0_z__seg_equator_free_crown") for key in free_equator_parametric["derived_parameters"])
    assert free_equator_parametric["derived_parameters"]["shared_equator_crown_delta_r_mm"]["value"] == pytest.approx(0.0)
    assert inset_parametric["derived_parameters"]["shared_equator_crown_delta_r_mm"]["value"] == pytest.approx(-3.0)
    assert bulge_parametric["derived_parameters"]["shared_equator_crown_delta_r_mm"]["value"] == pytest.approx(3.0)
    assert "shared_blend_arc_radius_mm" in free_equator_parametric["derived_parameters"]
    assert len(parametric["profile"]["segments"]) >= 7
    assert sum(len(segment.get("sampled_points", [])) for segment in parametric["profile"]["segments"]) > 40
    assert section_debug["sections"][0]["points"]
    assert validation["pass"] is True
    assert validation["generated"]["brep_valid"] is True
    assert validation["comparison"]["bbox_pass"] is True
    assert validation["comparison"]["volume_relative_error"] < 0.01
    assert validation["source_kernel_curve_generation_mode"] in {"cadquery_curve_segments", "dense_polyline_fallback"}
    assert validation["warnings"]
    assert payload["geometry"]["step_path"].endswith("generated_vacuum.step")
    assert "RF-CEM Parametric Geometry Audit" in audit_html
    assert "generated_vacuum.step" in audit_html
    assert "beam_pipe_radius_left" in audit_html
    assert "feature.beam_pipe" in audit_html
    assert "Feature Consumption Flow" in audit_html
    assert "Semantic Risk Register" in audit_html
    assert "Derived Curve Parameters" in audit_html
    assert "smoothness_priority=prefer_g1_with_evidence_anchors" in audit_html
    assert "nurbs" in audit_html
    assert "forward_compatibility" in audit_html
    import_action = next(action for action in actions if action["action_id"] == "import_step")
    assert "generated_vacuum.step" in import_action["vba"]


def test_cli_expert_prior_override_is_visible_in_audit(tmp_path):
    paths = _paths()
    output_dir = tmp_path / "parametric_geometry_override"
    override = tmp_path / "override_prior.v0.yaml"
    override.write_text(
        """
schema_version: expert_prior.v0
model_family: axisymmetric_single_cell_rf_vacuum
feature_mappings:
  BeamPipeLeft:
    human_description: CLI override left beam pipe text for audit.
    consumes: override cylindrical radius rule
case_specific_note: preserved for audit
""",
        encoding="utf-8",
    )

    rc = parametric_main(
        [
            "--appendix",
            str(paths.appendix),
            "--output-dir",
            str(output_dir),
            "--target-body-index",
            "0",
            "--axis",
            "z",
            "--expert-prior",
            str(override),
        ]
    )

    assert rc == 0
    audit_html = (output_dir / "audit" / "parametric_geometry_audit.html").read_text(encoding="utf-8")
    resolved = yaml.safe_load((output_dir / "metadata" / "resolved_expert_prior.v0.yaml").read_text(encoding="utf-8"))

    assert "CLI override left beam pipe text for audit" in audit_html
    assert "override cylindrical radius rule" in audit_html
    assert resolved["resolved_prior"]["case_specific_note"] == "preserved for audit"
