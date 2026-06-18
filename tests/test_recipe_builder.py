from pathlib import Path

import pytest

from cst_history_extractor.command_classifier import classify_history_items
from cst_history_extractor.macro_parser import parse_history_text
from cst_history_extractor.recipe_builder import (
    build_recipe_manifest,
    summarize_geometry_history,
)


pytestmark = pytest.mark.no_cst


def _classified_example():
    text = Path("examples/example_history.bas").read_text(encoding="utf-8")
    return classify_history_items(parse_history_text(text))


def test_recipe_manifest_extracts_reviewable_settings():
    commands = _classified_example()

    manifest = build_recipe_manifest(
        "example_history",
        "examples/example_history.bas",
        commands,
    )

    assert manifest["schema_version"] == "0.1"
    assert manifest["project"]["units"]["values"]["Length"] == "mm"
    assert manifest["project"]["units"]["values"]["Frequency"] == "GHz"
    assert manifest["project"]["parameters"]["values"]["cavity_radius"] == "42.0"
    assert manifest["materials"][0]["name"] == "OFHC_Copper"
    assert manifest["solver"]["type"] == "eigenmode"
    assert manifest["ports"][0]["type"] == "waveguide_port"
    assert manifest["ports"][0]["number"] == "1"
    assert manifest["boundaries"]["global"] is not None
    assert manifest["mesh"]["global"] is not None
    assert len(manifest["monitors"]) == 1
    assert len(manifest["postprocessing"]) == 1
    assert len(manifest["result_exports"]) == 1
    assert manifest["solver"]["source_history_indices"]


def test_geometry_summary_compresses_geometry_history():
    commands = _classified_example()

    summary = summarize_geometry_history(commands)

    assert summary["geometry_command_count"] == 2
    assert summary["imported_geometry"] == ["baseline_cavity.step"]
    assert summary["final_components"] == ["vacuum"]
    assert summary["final_solids"] == ["rf_vacuum"]
    assert summary["ignored_geometry_commands"]
