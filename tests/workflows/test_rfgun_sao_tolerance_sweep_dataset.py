"""No-CST tests for TSE2 tolerance sweep dataset.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from workflows.rfgun_tolerance.sweep_dataset import (
    ToleranceOutputSpec,
    ToleranceParameterSpec,
    ToleranceSweepDataset,
    ToleranceSweepGroup,
    build_sweep_dataset,
    build_sweep_dataset_from_record_groups,
    build_sweep_group_from_db,
    build_sweep_group_from_records,
    enabled_tolerance_parameters,
    enabled_tolerance_outputs,
    load_tolerance_output_specs,
    load_tolerance_parameter_specs,
    mm_to_um,
    normalize_tolerance_level,
    um_to_mm,
)


# ===================================================================
# Unit conversion
# ===================================================================


class TestUnitConversion:
    def test_mm_to_um(self):
        assert mm_to_um(0.003) == 3.0

    def test_um_to_mm(self):
        assert um_to_mm(30.0) == 0.03

    def test_normalize_mm(self):
        mm, um = normalize_tolerance_level(0.003, "mm")
        assert mm == 0.003
        assert um == 3.0

    def test_normalize_um(self):
        mm, um = normalize_tolerance_level(3.0, "um")
        assert mm == 0.003
        assert um == 3.0

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown tolerance unit"):
            normalize_tolerance_level(1.0, "m")


# ===================================================================
# Config inventory
# ===================================================================


def _cfg(overrides=None):
    """Build a synthetic config with tolerance section."""
    c = {
        "tolerance": {
            "parameters": [
                {"name": "offset1", "nominal": 0.0, "tolerance_abs": 0.003, "unit": "mm",
                 "enabled": True, "description": "Beam axis offset X"},
                {"name": "offset2", "nominal": 0.0, "tolerance_abs": 0.005, "unit": "mm",
                 "enabled": False, "description": "Beam axis offset Y"},
                {"name": "R_cell_3", "nominal": 10.782, "tolerance_abs": 0.003, "unit": "mm",
                 "enabled": True, "description": "Cell 3 Equator Radius"},
            ],
            "outputs": [
                {"name": "f0_ghz", "enabled": True, "description": "Resonant frequency (GHz)"},
                {"name": "e_peak", "enabled": True, "description": "Peak E-field (V/m)"},
                {"name": "Sc_max", "enabled": True, "description": "Max modified Poynting"},
                {"name": "DeltaT_K", "enabled": True, "description": "Pulsed heating (K)"},
                {"name": "s11_db", "enabled": False, "description": "S11 (dB)"},
            ],
        },
    }
    if overrides:
        c.update(overrides)
    return c


class TestConfigInventory:
    def test_parameter_specs_loaded(self):
        specs = load_tolerance_parameter_specs(_cfg())
        assert len(specs) == 3
        assert specs[0].name == "offset1"
        assert specs[1].name == "offset2"
        assert specs[2].name == "R_cell_3"

    def test_tolerance_abs_um_computed(self):
        specs = load_tolerance_parameter_specs(_cfg())
        assert specs[0].tolerance_abs_um == 3.0
        assert specs[1].tolerance_abs_um == 5.0
        assert specs[2].tolerance_abs_um == 3.0

    def test_enabled_parameters_filtered(self):
        specs = load_tolerance_parameter_specs(_cfg())
        enabled = enabled_tolerance_parameters(specs)
        assert len(enabled) == 2
        for s in enabled:
            assert s.enabled is True

    def test_output_specs_loaded(self):
        specs = load_tolerance_output_specs(_cfg())
        assert len(specs) == 5  # all 5 outputs (enabled + disabled)
        assert specs[0].name == "f0_ghz"
        assert specs[4].name == "s11_db"

    def test_enabled_outputs_filtered(self):
        specs = load_tolerance_output_specs(_cfg())
        enabled = enabled_tolerance_outputs(specs)
        assert len(enabled) == 4

    def test_output_alias_f0(self):
        specs = load_tolerance_output_specs(_cfg())
        f0 = [s for s in specs if s.name == "f0_ghz"][0]
        assert f0.tam_metric_alias == "resonant_freq"

    def test_output_alias_e_peak(self):
        specs = load_tolerance_output_specs(_cfg())
        ep = [s for s in specs if s.name == "e_peak"][0]
        assert ep.tam_metric_alias == "peak_e_field"

    def test_output_alias_Sc_max(self):
        specs = load_tolerance_output_specs(_cfg())
        sc = [s for s in specs if s.name == "Sc_max"][0]
        assert sc.tam_metric_alias == "max_modified_poynting"

    def test_output_alias_DeltaT_K(self):
        specs = load_tolerance_output_specs(_cfg())
        dt = [s for s in specs if s.name == "DeltaT_K"][0]
        assert dt.tam_metric_alias == "pulsed_heating"

    def test_p_input_mw_unchanged(self):
        cfg2 = _cfg()
        cfg2["tolerance"]["outputs"].append(
            {"name": "p_input_mw", "enabled": True, "description": "Input power (MW)"},
        )
        specs = load_tolerance_output_specs(cfg2)
        pi = [s for s in specs if s.name == "p_input_mw"][0]
        assert pi.tam_metric_alias == "p_input_mw"

    def test_missing_tolerance_section_raises(self):
        with pytest.raises(ValueError, match="missing 'tolerance' section"):
            load_tolerance_parameter_specs({})

    def test_missing_nominal_raises(self):
        cfg = _cfg()
        cfg["tolerance"]["parameters"][0].pop("nominal")
        with pytest.raises(ValueError, match="missing 'nominal'"):
            load_tolerance_parameter_specs(cfg)

    def test_missing_tolerance_abs_raises(self):
        cfg = _cfg()
        cfg["tolerance"]["parameters"][1].pop("tolerance_abs")
        with pytest.raises(ValueError, match="missing 'tolerance_abs'"):
            load_tolerance_parameter_specs(cfg)


# ===================================================================
# Sweep groups
# ===================================================================


def _record(param_values, metrics=None):
    if metrics is None:
        metrics = {"m1": 10.0}
    return {
        "status": "success", "solver_ok": True,
        "parameter_identity": {"param_names": ["a"], "values": list(param_values), "parameter_key": ""},
        "raw_metrics": dict(metrics),
    }


class TestSweepGroup:
    def test_group_from_records(self):
        records = [_record([1.0]) for _ in range(3)]
        g = build_sweep_group_from_records(records, "offset1", 3.0, "um")
        assert g.tolerance_parameter == "offset1"
        assert g.tolerance_level_um == 3.0
        assert g.tolerance_level_mm == 0.003
        assert g.dataset.accepted_row_count == 3
        assert g.source_label == "offset1_3um"

    def test_default_source_label(self):
        records = [_record([1.0])]
        g = build_sweep_group_from_records(records, "offset1", 10.0, "um")
        assert g.source_label == "offset1_10um"

    def test_records_not_mutated(self):
        records = [_record([1.0])]
        before = list(records)
        build_sweep_group_from_records(records, "offset1", 3.0, "um")
        assert records == before

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown tolerance unit"):
            build_sweep_group_from_records([], "offset1", 1.0, "m")


# ===================================================================
# Sweep dataset
# ===================================================================


class TestSweepDataset:
    def _g(self, param, level_um, rows=2):
        records = [_record([1.0]) for _ in range(rows)]
        return build_sweep_group_from_records(records, param, level_um, "um")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="requires at least one group"):
            build_sweep_dataset([])

    def test_single_group(self):
        g = self._g("offset1", 3)
        sd = build_sweep_dataset([g])
        assert sd.tolerance_parameter == "offset1"
        assert len(sd.groups) == 1
        assert sd.tolerance_levels_um == (3.0,)

    def test_groups_sorted_by_level(self):
        g1 = self._g("offset1", 30)
        g2 = self._g("offset1", 3)
        sd = build_sweep_dataset([g1, g2])
        assert list(sd.tolerance_levels_um) == [3.0, 30.0]

    def test_duplicate_level_raises(self):
        g1 = self._g("offset1", 3)
        g2 = self._g("offset1", 3)
        with pytest.raises(ValueError, match="Duplicate tolerance level"):
            build_sweep_dataset([g1, g2])

    def test_mixed_parameter_raises(self):
        g1 = self._g("offset1", 3)
        g2 = self._g("offset2", 10)
        with pytest.raises(ValueError, match="Mixed tolerance parameters"):
            build_sweep_dataset([g1, g2])

    def test_from_record_groups(self):
        specs = [
            {"tolerance_parameter": "offset1", "tolerance_level": 3, "tolerance_unit": "um",
             "records": [_record([1.0]) for _ in range(2)]},
            {"tolerance_parameter": "offset1", "tolerance_level": 10, "tolerance_unit": "um",
             "records": [_record([1.0]) for _ in range(3)]},
        ]
        sd = build_sweep_dataset_from_record_groups(specs)
        assert len(sd.groups) == 2
        assert sd.tolerance_levels_um == (3.0, 10.0)
        assert sd.groups[0].dataset.accepted_row_count == 2
        assert sd.groups[1].dataset.accepted_row_count == 3


# ===================================================================
# DB-level loader
# ===================================================================


class TestDBLoader:
    def test_group_from_temp_db(self, tmp_path):
        import json as _json
        from cst_optimization.evaluation.evaluation_database_schema import current_schema_version
        from cst_optimization.evaluation.evaluation_database_storage import (
            EvaluationDatabaseConfig, SQLiteEvaluationDatabase,
        )
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "raw_metrics, objective_values, objective_names) VALUES (?,?,?,?,?,?,?,?)",
                (current_schema_version(), "k1", _json.dumps(["a"]), _json.dumps([1.0]),
                 "success", _json.dumps({"m1": 10.0}), _json.dumps({"m1": 10.0}),
                 _json.dumps(["m1"])),
            )
            db._conn.commit()

        g = build_sweep_group_from_db(db_path, "offset1", 3.0, "um")
        assert g.tolerance_parameter == "offset1"
        assert g.dataset.accepted_row_count >= 1
        assert g.db_path == db_path

    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            build_sweep_group_from_db(str(tmp_path / "nonexistent.db"), "offset1", 3.0)


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_factory_import(self):
        import workflows.rfgun_tolerance.sweep_dataset as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "cst_optimization.factory" not in text
        assert "cst_optimization.workflows.recovery" not in text

    def test_no_jsonl_excel(self):
        import workflows.rfgun_tolerance.sweep_dataset as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text
        assert ".xlsx" not in text
        assert "openpyxl" not in text
        assert "xlrd" not in text
