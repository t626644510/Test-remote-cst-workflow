import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.build_500mhz_baseline import main as build_500mhz_main
from rf_cem.design_package import BaselinePaths
from rf_cem.history_templates import load_cst_history_templates
from rf_cem.live_500mhz_postprocessing_diagnostic import _install_model_rpp
from rf_cem.translator import emit_copper_background_material_block, emit_step_import_block, translate_baseline
from rf_cem.udsg_builder import build_baseline_udsg


pytestmark = pytest.mark.no_cst

BASELINE = Path("Appendix/500MHz_baseline")


def _paths() -> BaselinePaths:
    if not BASELINE.exists():
        pytest.skip("Appendix/500MHz_baseline fixture is not available")
    paths = BaselinePaths.from_appendix(BASELINE)
    paths.validate()
    return paths


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_reviewed_labels_build_required_udsg_features():
    paths = _paths()
    templates = load_cst_history_templates(paths.model_history_json)

    udsg, review_diff = build_baseline_udsg(paths, history_recipe=templates.recipe)

    features = [feature for feature in udsg["features"] if feature["status"] in {"confirmed", "modified"}]
    feature_types = {feature["type"] for feature in features}
    assert {
        "RFVacuumVolume",
        "ConductingWall",
        "BeamPipeLeft",
        "BeamPipeRight",
        "BeamAperture",
        "BeamExit",
    }.issubset(feature_types)
    assert sum(1 for feature in udsg["features"] if feature["status"] == "confirmed") == 9
    assert sum(1 for feature in udsg["features"] if feature["status"] == "rejected") == 2
    assert udsg["validation"]["status"] == "ok"
    assert review_diff["schema_version"] == "review_session_diff.v0"
    assert len(review_diff["deleted_bindings"]) == 2
    assert len(review_diff["rewired_bindings"]) == 14


def test_history_template_extractor_reads_baseline_eigenmode_settings():
    paths = _paths()

    templates = load_cst_history_templates(paths.model_history_json)
    units = templates.recipe["project"]["units"]["values"]
    summary = templates.eigenmode_summary

    assert units["Length"] == "mm"
    assert units["Frequency"] == "MHz"
    assert units["Time"] == "ns"
    assert summary["solver_type"] == "eigenmode"
    assert summary["frequency_range"] == {"min": "498", "max": "530", "unit_assumption": "project frequency unit"}
    assert summary["mesh_type"] == "Tetrahedral Mesh"
    assert summary["number_of_modes"] == "1"
    assert summary["accuracy"] == "1e-12"
    assert summary["minimum_passes"] == "2"
    assert summary["maximum_passes"] == "6"


def test_step_import_emitter_supports_filename_modes():
    step_file = Path(r"C:\tmp\500MHz.stp")

    star = emit_step_import_block(step_file, filename_mode="star-basename")
    absolute = emit_step_import_block(step_file, filename_mode="absolute")

    assert '.FileName "*500MHz.stp"' in star
    assert '.FileName "C:\\tmp\\500MHz.stp"' in absolute
    assert '.ScaleToUnit "0"' in star
    assert '.Version "11.0"' in star
    assert ".Read" in star


def test_copper_background_material_block_is_emitted_from_verified_pattern():
    block = emit_copper_background_material_block()

    assert "With Background" in block
    assert ".ResetBackground" in block
    assert ".ApplyInAllDirections \"False\"" in block
    assert "With Material" in block
    assert ".Type \"Lossy metal\"" in block
    assert ".Sigma \"5.8e+007\"" in block
    assert ".ChangeBackgroundMaterial" in block


def test_postprocessing_template_registration_writes_model_rpp(tmp_path):
    template_dir = tmp_path / "template_project"
    source_3d = template_dir / "Model" / "3D"
    source_3d.mkdir(parents=True)
    (source_3d / "Model.rpp").write_text(
        "\n".join(
            [
                "11",
                "0",
                "0",
                "4",
                "Frequency (Mode 1)",
                "3D Eigenmode Result",
                "1",
                "0D",
                "2D and 3D Field Results",
                "P",
                "ED10",
                "3D Eigenmode Result^+MWS+PS+DS.rtp",
                "VBA",
                "1",
                "Frequency (Mode 1)",
                "R over Q (Mode 1)",
                "3D Eigenmode Result",
                "1",
                "0D",
                "2D and 3D Field Results",
                "P",
                "ED10",
                "3D Eigenmode Result^+MWS+PS+DS.rtp",
                "VBA",
                "1",
                "R over Q (Mode 1)",
                "Q-Factor (Perturbation) (Mode 1)",
                "3D Eigenmode Result",
                "1",
                "0D",
                "2D and 3D Field Results",
                "1",
                "ED10",
                "3D Eigenmode Result^+MWS+PS+DS.rtp",
                "VBA",
                "1",
                "Q-Factor (Perturbation) (Mode 1)",
                "Unrelated Result",
                "Other Template",
                "1",
                "0D",
                "Other Group",
                "P",
                "ED10",
                "Other.rtp",
                "VBA",
                "1",
                "Unrelated Result",
                "0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    project_dir = tmp_path / "generated_project"
    (project_dir / "Model" / "3D").mkdir(parents=True)

    report = _install_model_rpp(template_dir, project_dir)
    text = (project_dir / "Model" / "3D" / "Model.rpp").read_text(encoding="utf-8")

    assert report["status"] == "ok"
    assert report["source_policy"] == "filtered_source_model_rpp"
    assert "\n3\nFrequency (Mode 1)\n" in text
    assert "R over Q (Mode 1)" in text
    assert "Q-Factor (Perturbation) (Mode 1)" in text
    assert "Unrelated Result" not in text


def test_symmetry_and_translation_are_deterministic():
    paths = _paths()
    templates = load_cst_history_templates(paths.model_history_json)
    udsg, _ = build_baseline_udsg(paths, history_recipe=templates.recipe)

    first = translate_baseline(udsg, templates, paths.step_file)
    second = translate_baseline(udsg, templates, paths.step_file)

    assert udsg["geometry"]["symmetry"]["is_xy_symmetric"] is True
    assert _stable_hash(first.actions) == _stable_hash(second.actions)
    assert _stable_hash(first.mapping_table) == _stable_hash(second.mapping_table)
    assert first.script == second.script
    assert first.report["blocking_errors"] == []
    assert first.mapping_table["geometry_overlaps"]


def test_cli_writes_no_cst_artifacts(tmp_path):
    paths = _paths()
    output_dir = tmp_path / "rf_cem_500mhz"

    rc = build_500mhz_main([
        "--appendix",
        str(paths.appendix),
        "--output-dir",
        str(output_dir),
    ])

    assert rc == 0
    expected = [
        output_dir / "semantic" / "udsg.v0.json",
        output_dir / "generated" / "cst_actions.json",
        output_dir / "generated" / "cst_mapping_table.json",
        output_dir / "generated" / "cst_script.bas",
        output_dir / "generated" / "translator_report.json",
        output_dir / "generated" / "review_session_diff.json",
    ]
    for path in expected:
        assert path.exists(), path
    report = json.loads((output_dir / "generated" / "translator_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["blocking_errors"] == []
