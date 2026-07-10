import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.history_templates import CstHistoryBlock, CstHistoryTemplates
from rf_cem.parametric_geometry.optimization_adapter import (
    apply_curve_parameter_overrides,
    baseline_vector,
    build_parameter_set,
    build_parameter_specs,
    generate_candidate_package,
)
from rf_cem.translator import translate_baseline
from workflows.rf_cem_500mhz_parametric_opt.evaluator import RfCemParametricEvaluator
from workflows.rf_cem_500mhz_parametric_opt.types import EvaluationStatus


pytestmark = pytest.mark.no_cst

BASELINE = Path("Appendix/500MHz_baseline")


def _cadquery_available() -> bool:
    return importlib.util.find_spec("cadquery") is not None and importlib.util.find_spec("OCP") is not None


def test_optimization_adapter_filters_supported_numeric_derived_parameters(tmp_path):
    parametric_path = tmp_path / "parametric_geometry.v0.json"
    parametric_path.write_text(
        json.dumps(
            {
                "derived_parameters": {
                    "shared_equator_crown_delta_r_mm": {
                        "value": 0.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                    "shared_equator_crown_shoulder_z_abs_mm": {
                        "value": 30.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                    "curve_type__seg_equator_free_crown": {
                        "value": "nurbs",
                        "unit": "categorical",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                    "shared_blend_arc_radius_mm": {
                        "value": 75.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    specs = build_parameter_specs(parametric_path)
    parameter_set = build_parameter_set(specs)

    assert [spec.name for spec in specs] == [
        "shared_equator_crown_delta_r_mm",
        "shared_equator_crown_shoulder_z_abs_mm",
    ]
    assert parameter_set.names == [spec.name for spec in specs]
    assert baseline_vector(specs).tolist() == [0.0, 30.0]
    override = apply_curve_parameter_overrides(
        {
            "shared_equator_crown_delta_r_mm": -1.5,
            "shared_equator_crown_shoulder_z_abs_mm": 42.0,
        }
    )
    policy = override["grammar"]["variant_policy"]
    assert policy["enabled_variants"] == ["free_equator_smooth"]
    assert policy["curve_parameters"]["equator"]["free_equator_smooth"]["crown_radius_delta_mm"] == -1.5
    assert policy["curve_parameters"]["equator"]["free_equator_smooth"]["shoulder_z_abs_mm"] == 42.0
    with pytest.raises(ValueError, match="no v0 prior override mapping"):
        build_parameter_specs(parametric_path, parameter_names=("shared_blend_arc_radius_mm",))


def test_exploratory_12d_specs_and_prior_override_are_configurable(tmp_path):
    parametric_path = tmp_path / "parametric_geometry.v0.json"
    parametric_path.write_text(
        json.dumps(
            {
                "derived_parameters": {
                    "shared_equator_crown_delta_r_mm": {
                        "value": 0.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                        "feature_refs": ["EquatorRegion"],
                        "segment_id": "shared",
                    },
                    "nurbs_cp1_z__seg_equator_free_crown": {
                        "value": -30.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                    "nurbs_cp2_z__seg_equator_free_crown": {
                        "value": 0.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                    "nurbs_cp3_z__seg_equator_free_crown": {
                        "value": 30.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    specs = build_parameter_specs(parametric_path, parameter_preset="exploratory_12d")
    names = [spec.name for spec in specs]

    assert len(specs) == 12
    assert names[:4] == [
        "equator_crown_delta_r_mm",
        "equator_crown_z_mid_mm",
        "equator_left_shoulder_z_abs_mm",
        "equator_right_shoulder_z_abs_mm",
    ]
    assert specs[0].low == pytest.approx(-8.0)
    assert specs[2].baseline == pytest.approx(30.0)
    assert {spec.parameter_group for spec in specs} >= {"equator_global", "nose_nurbs", "blend_arc"}

    override = apply_curve_parameter_overrides(
        {
            "equator_crown_delta_r_mm": 6.0,
            "equator_left_shoulder_z_abs_mm": 22.0,
            "equator_right_shoulder_delta_r_mm": -3.0,
            "nose_left_inner_delta_r_mm": 3.0,
            "nose_right_inner_delta_z_mm": -5.0,
            "blend_left_radius_delta_mm": 9.0,
        }
    )
    curve_parameters = override["grammar"]["variant_policy"]["curve_parameters"]

    assert curve_parameters["equator"]["free_equator_smooth"]["crown_radius_delta_mm"] == pytest.approx(6.0)
    assert curve_parameters["equator"]["free_equator_smooth"]["left_shoulder_z_abs_mm"] == pytest.approx(22.0)
    assert curve_parameters["equator"]["free_equator_smooth"]["right_shoulder_delta_r_mm"] == pytest.approx(-3.0)
    assert curve_parameters["nose"]["free_equator_smooth"]["left_inner_delta_r_mm"] == pytest.approx(3.0)
    assert curve_parameters["nose"]["free_equator_smooth"]["right_inner_delta_z_mm"] == pytest.approx(-5.0)
    assert curve_parameters["blend"]["free_equator_smooth"]["left_radius_delta_mm"] == pytest.approx(9.0)


def test_translator_postprocessing_fail_closed_is_opt_in():
    templates = CstHistoryTemplates(
        source="fixture",
        recipe={"solver": {"type": "eigenmode", "settings": {}}},
        units_block="With Units\nEnd With",
        boundary_block="With Boundary\nEnd With",
        frequency_range_block='Solver.FrequencyRange "498", "530"',
        solver_blocks=("With EigenmodeSolver\nEnd With",),
        source_history_indices={"units": [1], "boundary": [2], "frequency_range": [3], "solver": [4]},
    )
    udsg = {"schema_version": "udsg.v0", "features": [], "validation": {"warnings": []}}
    step_file = Path("generated_vacuum.step")

    optional = translate_baseline(udsg, templates, step_file, require_postprocessing=False)
    required = translate_baseline(udsg, templates, step_file, require_postprocessing=True)

    assert optional.report["status"] == "ok"
    assert optional.report["blocking_errors"] == []
    assert any("postprocessing/result-template" in warning for warning in optional.report["warnings"])
    assert required.report["status"] == "blocked"
    assert "postprocessing/result-template" in required.report["blocking_errors"][0]

    result_block = CstHistoryBlock(
        action_id="results_q_factor_0005",
        caption="Q factor result export",
        category="results",
        subcategory="q_factor",
        vba="' verified Q factor block",
        source_index=5,
        confidence=0.82,
    )
    with_post = CstHistoryTemplates(
        source="fixture",
        recipe={"solver": {"type": "eigenmode", "settings": {}}},
        units_block="With Units\nEnd With",
        boundary_block="With Boundary\nEnd With",
        frequency_range_block='Solver.FrequencyRange "498", "530"',
        solver_blocks=("With EigenmodeSolver\nEnd With",),
        source_history_indices={"units": [1], "boundary": [2], "frequency_range": [3], "solver": [4], "result_exports": [5]},
        result_export_blocks=(result_block,),
    )
    artifacts = translate_baseline(udsg, with_post, step_file, require_postprocessing=True)

    assert artifacts.report["status"] == "ok"
    assert artifacts.actions[-1]["action_id"] == "results_q_factor_0005"
    assert artifacts.actions[-1]["action_type"] == "export_result"
    assert [action["action_id"] for action in artifacts.actions[:7]] == [
        "set_units",
        "set_background_material",
        "import_step",
        "assign_imported_vacuum_material",
        "set_boundary",
        "set_frequency_range",
        "set_eigenmode_solver_01",
    ]


def test_no_cst_evaluator_marks_missing_postprocessing_template(tmp_path, monkeypatch):
    parametric_path = tmp_path / "parametric_geometry.v0.json"
    parametric_path.write_text(
        json.dumps(
            {
                "derived_parameters": {
                    "shared_equator_crown_delta_r_mm": {
                        "value": 0.0,
                        "unit": "mm",
                        "optimization_candidate": True,
                        "affects_generated_step": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    specs = build_parameter_specs(parametric_path, parameter_names=("shared_equator_crown_delta_r_mm",))
    parameter_set = build_parameter_set(specs)

    def fake_generate_candidate_package(**kwargs):
        candidate_dir = kwargs["output_dir"]
        validation_path = candidate_dir / "metadata" / "geometry_validation.json"
        report_path = candidate_dir / "translator" / "rf_cem_artifacts" / "generated" / "translator_report.json"
        validation_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        validation_path.write_text(json.dumps({"pass": True, "blocking_errors": []}), encoding="utf-8")
        report_path.write_text(
            json.dumps({"postprocessing_summary": {"verified": False}}),
            encoding="utf-8",
        )
        return {
            "generated_step": str(candidate_dir / "geometry" / "generated_vacuum.step"),
            "geometry_validation": str(validation_path),
            "cst_payload": str(candidate_dir / "translator" / "cst_payload.json"),
        }

    monkeypatch.setattr(
        "workflows.rf_cem_500mhz_parametric_opt.evaluator.generate_candidate_package",
        fake_generate_candidate_package,
    )
    evaluator = RfCemParametricEvaluator(
        appendix=Path("Appendix/500MHz_baseline"),
        output_dir=tmp_path / "candidates",
        parameter_set=parameter_set,
    )

    record = evaluator.evaluate_no_cst(baseline_vector(specs), index=1)

    assert record.status == EvaluationStatus.POSTPROCESS_TEMPLATE_MISSING
    assert record.metadata["no_cst_geometry_pass"] is True
    assert record.metadata["postprocess_status"] == "template_missing"


def test_generate_single_variant_candidate_package_from_curve_overrides(tmp_path):
    if not BASELINE.exists():
        pytest.skip("Appendix/500MHz_baseline fixture is not available")
    if not _cadquery_available():
        pytest.skip("CadQuery/OCP is not installed")

    output_dir = tmp_path / "candidate_000"
    result = generate_candidate_package(
        appendix=BASELINE,
        output_dir=output_dir,
        parameter_values={
            "shared_equator_crown_delta_r_mm": -1.5,
            "shared_equator_crown_shoulder_z_abs_mm": 42.0,
        },
    )

    parametric_path = output_dir / "metadata" / "parametric_geometry.v0.json"
    validation_path = output_dir / "metadata" / "geometry_validation.json"
    payload_path = output_dir / "translator" / "cst_payload.json"
    variant_index_path = output_dir / "variant_index.json"
    generated_step = output_dir / "geometry" / "generated_vacuum.step"

    assert result["variant"] == "free_equator_smooth"
    for path in (parametric_path, validation_path, payload_path, variant_index_path, generated_step):
        assert path.exists(), path
    parametric = json.loads(parametric_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    variant_index = json.loads(variant_index_path.read_text(encoding="utf-8"))

    assert parametric["variant"]["name"] == "free_equator_smooth"
    assert parametric["derived_parameters"]["shared_equator_crown_delta_r_mm"]["value"] == pytest.approx(-1.5)
    assert parametric["derived_parameters"]["shared_equator_crown_shoulder_z_abs_mm"]["value"] == pytest.approx(42.0)
    assert validation["pass"] is True
    assert "volume relative error exceeds threshold" in validation["warnings"]
    assert validation["blocking_errors"] == []
    assert validation["generated"]["brep_valid"] is True
    assert payload["geometry"]["step_path"].endswith("generated_vacuum.step")
    assert variant_index["selected_variant"] == "free_equator_smooth"
    assert [item["name"] for item in variant_index["variants"]] == ["free_equator_smooth"]
