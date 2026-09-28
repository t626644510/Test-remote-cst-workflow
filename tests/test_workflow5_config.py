"""Portable configuration and fail-closed validation without a CST import."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from workflows.rfgun_hom_target.config import (
    ConfigurationError, PARAMETER_NAMES, load_config,
)

pytestmark = pytest.mark.no_cst


@pytest.fixture
def document():
    return {"workflow_5": {"paths": {"template_path": "template.cst"}, "physics": {"z_range_mm": [-100, 100]}}}


def save(tmp_path, document):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_offline_defaults_paths_and_units(tmp_path, document, monkeypatch):
    monkeypatch.delenv("CST_PYTHON_LIB", raising=False)
    cfg = load_config(save(tmp_path, document))
    assert cfg.paths.template_path == tmp_path / "template.cst"
    assert cfg.paths.cst_library_path == ""
    assert tuple(p.name for p in cfg.parameters) == PARAMETER_NAMES
    assert cfg.parameters[-1].upper == 25
    assert cfg.physics.threshold_ohm_per_m == 100000
    assert cfg.physics.z_range_mm == (-100., 100.)
    assert cfg.search.max_solves == 40
    assert cfg.search.initial_points == 12
    assert cfg.solver.max_mode_count == 24
    assert cfg.solver.upper_frequency_mhz == 1070
    json.dumps(cfg.as_dict(), allow_nan=False)


@pytest.mark.parametrize("section", ["workflow_5", "paths", "physics", "geometry", "solver", "search", "results"])
def test_unknown_keys_rejected_every_section(tmp_path, document, section):
    node = document["workflow_5"] if section == "workflow_5" else document["workflow_5"].setdefault(section, {})
    node["typo"] = 1
    with pytest.raises(ConfigurationError, match="Unknown"):
        load_config(save(tmp_path, document))


@pytest.mark.parametrize("section,key,value", [
    ("physics", "z_range_mm", None), ("physics", "z_range_mm", [1, 1]),
    ("physics", "z_samples", 100), ("physics", "z_samples", 101.0),
    ("physics", "offsets_mm", [2, 2, 6]), ("physics", "offsets_mm", [2, 0]),
    ("physics", "offsets_mm", [2, 4]),
    ("physics", "threshold_ohm_per_m", float("nan")), ("physics", "beta", 1.01),
    ("physics", "beta", 0.9),
    ("physics", "field_convention", "rms"), ("physics", "gradient_tolerance", 1),
    ("solver", "target_frequency_mhz", 1031), ("solver", "mesh", "coarse"),
    ("solver", "upper_frequency_mhz", 1060), ("solver", "upper_frequency_mhz", 1050),
    ("solver", "mode_count", 25), ("solver", "coverage_retries", -1),
    ("search", "max_solves", True), ("search", "initial_points", 0),
    ("search", "min_radius", .3), ("search", "candidate_draws", 10),
    ("search", "max_candidate_attempts", 39),
    ("results", "frequency", "Mode {bogus}"), ("results", "q_loaded", "fixed mode 1"),
    ("results", "frequency", "Mode {mode:02d}"),
    ("results", "frequency_unit", "mhz"),
    ("geometry", "flange_radius_mm", 5),
])
def test_invalid_values_fail_closed(tmp_path, document, section, key, value):
    document["workflow_5"].setdefault(section, {})[key] = value
    with pytest.raises(ConfigurationError):
        load_config(save(tmp_path, document))


def test_live_requires_explicit_existing_paths(tmp_path, document, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setenv("CST_PYTHON_LIB", str(library))
    path = save(tmp_path, document)
    with pytest.raises(ConfigurationError, match="Template"):
        load_config(path, live=True)
    (tmp_path / "template.cst").write_bytes(b"test placeholder, never opened")
    with pytest.raises(ConfigurationError, match="companion"):
        load_config(path, live=True)
    (tmp_path / "template").mkdir()
    cfg = load_config(path, live=True)
    assert cfg.paths.cst_library_path == str(library)
    document["workflow_5"]["paths"]["cst_library_path"] = "override"
    with pytest.raises(ConfigurationError, match="CST Python"):
        load_config(save(tmp_path, document), live=True)


def test_single_solve_budget_can_stop_during_initial_design(tmp_path, document):
    document["workflow_5"]["search"] = {"max_solves": 1}
    cfg = load_config(save(tmp_path, document))
    assert cfg.search.max_solves == 1
    assert cfg.search.initial_points == 12


@pytest.mark.parametrize("output", [".", "template", "template/runs", "template.cst"])
def test_output_cannot_overlap_template_or_companion(tmp_path, document, output):
    document["workflow_5"]["paths"]["output_dir"] = output
    with pytest.raises(ConfigurationError, match="source template"):
        load_config(save(tmp_path, document))


def test_cst_parameter_mapping_and_canonical_order(tmp_path, document):
    initial = load_config(save(tmp_path, document)).as_dict()["parameters"]
    initial.reverse()
    initial[0]["cst_name"] = "custom_radius"
    document["workflow_5"]["parameters"] = initial
    cfg = load_config(save(tmp_path, document))
    assert tuple(p.name for p in cfg.parameters) == PARAMETER_NAMES
    assert cfg.parameters[-1].cst_name == "custom_radius"
    initial[1]["cst_name"] = "custom_radius"
    with pytest.raises(ConfigurationError, match="unique"):
        load_config(save(tmp_path, document))


@pytest.mark.parametrize("mutation", [
    {"unit": "m"}, {"lower": 30, "upper": 10}, {"name": "unknown"},
    {"cst_name": "bad\"name"}, {"typo": 1},
])
def test_invalid_parameter_schema(tmp_path, document, mutation):
    parameters = load_config(save(tmp_path, document)).as_dict()["parameters"]
    parameters[-1].update(mutation)
    document["workflow_5"]["parameters"] = parameters
    with pytest.raises(ConfigurationError):
        load_config(save(tmp_path, document))


def test_material_override_validates_units_and_unknown_keys(tmp_path, document):
    layers = {"Copper": {"conductivity": "5.8e7", "mu": 1}, "Ideal": {"conductivity": "PEC"}}
    document["workflow_5"]["physics"]["conductivity_layers"] = layers
    cfg = load_config(save(tmp_path, document))
    assert cfg.physics.conductivity_layers["Copper"]["conductivity"] == 5.8e7
    layers["Copper"]["conductivty"] = 1
    with pytest.raises(ConfigurationError, match="Unknown"):
        load_config(save(tmp_path, document))


def test_example_requires_explicit_integration_interval(tmp_path):
    source = Path(__file__).parents[1] / "workflows/rfgun_hom_target/config.example.yaml"
    with pytest.raises(ConfigurationError, match="z_range_mm"):
        load_config(source)
    example = yaml.safe_load(source.read_text(encoding="utf-8"))
    example["workflow_5"]["physics"]["z_range_mm"] = [-100, 100]
    assert load_config(save(tmp_path, example)).physics.z_samples == 1883


def test_explicit_fixed_window_allows_exact_objective_upper_edge(tmp_path, document):
    document["workflow_5"]["solver"] = dict(coverage_policy="fixed_window",
        upper_frequency_mhz=1060, mode_count=6, max_mode_count=6, coverage_retries=0)
    cfg = load_config(save(tmp_path, document))
    assert cfg.solver.coverage_policy == "fixed_window"
    assert cfg.solver.upper_frequency_mhz == cfg.physics.frequency_max_mhz
    assert cfg.as_dict()["solver"]["coverage_policy"] == "fixed_window"


@pytest.mark.parametrize("change", [dict(coverage_retries=1), dict(max_mode_count=12),
    dict(upper_frequency_mhz=1059), dict(coverage_policy="typo"), dict(coverage_policy=True)])
def test_fixed_window_rejects_inconsistent_or_unknown_policy(tmp_path, document, change):
    document["workflow_5"]["solver"] = dict(coverage_policy="fixed_window",
        upper_frequency_mhz=1060, mode_count=6, max_mode_count=6, coverage_retries=0)
    document["workflow_5"]["solver"].update(change)
    with pytest.raises(ConfigurationError):
        load_config(save(tmp_path, document))
