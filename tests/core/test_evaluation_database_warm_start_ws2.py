"""No-CST tests for WS2 DB warm-start prior loader."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseStatus,
    ParameterIdentity,
    current_schema_version,
)
from cst_optimization.evaluation.evaluation_database_warm_start import (
    DbWarmStartConfig,
    DbWarmStartPrior,
    DbWarmStartLoadReport,
    load_warm_start_priors,
    resolve_db_warm_start_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(
    status: str = "success",
    schema_version: int | None = None,
    param_names: list[str] | None = None,
    param_values: list[float] | None = None,
    objective_values: dict | None = None,
    objective_names: list[str] | None = None,
    row_id: int = 1,
    run_id: str = "r1",
    created_at: str = "2026-01-01 00:00:00",
    diagnostics: dict | None = None,
) -> dict:
    """Build a fake DB row dict."""
    if schema_version is None:
        schema_version = current_schema_version()
    if param_names is None:
        param_names = ["p0"]
    if param_values is None:
        param_values = [1.0]
    pid = ParameterIdentity(param_names=param_names, values=param_values)
    if objective_names is None and objective_values is not None:
        objective_names = list(objective_values.keys())
    row: dict = {
        "id": row_id,
        "schema_version": schema_version,
        "parameter_key": pid.parameter_key(),
        "param_names": json.dumps(param_names),
        "param_values": json.dumps(param_values),
        "status": status,
        "raw_metrics": json.dumps({"m1": 1.0}) if objective_values else None,
        "objective_values": json.dumps(objective_values) if objective_values else None,
        "objective_names": json.dumps(objective_names) if objective_names else None,
        "diagnostics": json.dumps(diagnostics) if diagnostics else None,
        "source": "test",
        "run_id": run_id,
        "created_at": created_at,
    }
    return row


# ===================================================================
# Config resolution
# ===================================================================


class TestResolveConfig:
    def test_none_returns_disabled(self) -> None:
        cfg = resolve_db_warm_start_config(None, db_enabled=False)
        assert cfg.enabled is False

    def test_missing_section_returns_disabled(self) -> None:
        cfg = resolve_db_warm_start_config({}, db_enabled=False)
        assert cfg.enabled is False

    def test_evaluation_db_disabled_alone(self) -> None:
        """warm_start.enabled=True without DB enabled raises."""
        with pytest.raises(ValueError, match="requires evaluation_database.enabled=True"):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True}}},
                db_enabled=False,
            )

    def test_warm_start_without_db_raises(self) -> None:
        with pytest.raises(ValueError, match="requires evaluation_database.enabled=True"):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True}}},
                db_enabled=False,  # DB explicitly disabled
            )

    def test_db_enabled_warm_start_enabled_ok(self) -> None:
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True}}},
            db_enabled=True,
        )
        assert cfg.enabled is True
        assert cfg.max_priors == 50
        assert cfg.order_by == "best_objective"

    def test_invalid_order_by_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid order_by"):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True, "order_by": "invalid"}}},
                db_enabled=True,
            )

    def test_negative_max_priors_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True, "max_priors": -1}}},
                db_enabled=True,
            )

    def test_zero_max_priors_ok(self) -> None:
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True, "max_priors": 0}}},
            db_enabled=True,
        )
        assert cfg.enabled is True
        assert cfg.max_priors == 0

    def test_custom_max_priors(self) -> None:
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True, "max_priors": 10}}},
            db_enabled=True,
        )
        assert cfg.max_priors == 10

    def test_custom_order_by_newest(self) -> None:
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True, "order_by": "newest"}}},
            db_enabled=True,
        )
        assert cfg.order_by == "newest"

    def test_success_reuse_alone_does_not_enable(self) -> None:
        """success_reuse.enabled alone does NOT enable warm-start."""
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"success_reuse": {"enabled": True}}},
            db_enabled=True,
        )
        assert cfg.enabled is False

    def test_db_enabled_alone_does_not_enable(self) -> None:
        """evaluation_database.enabled alone does NOT enable warm-start."""
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"path": "/tmp/d.db"}},
            db_enabled=True,
        )
        assert cfg.enabled is False


# ===================================================================
# load_warm_start_priors
# ===================================================================


class TestLoadPriors:
    def test_empty_rows_returns_empty(self) -> None:
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.found_rows == 0
        assert report.accepted_priors == 0

    def test_loads_success_row(self) -> None:
        rows = [_make_row(objective_values={"m1": 0.5}, objective_names=["m1"])]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1
        assert report.rejected_rows == 0
        priors = report.diagnostics.get("priors", [])
        assert len(priors) == 1
        assert priors[0].parameter_key == rows[0]["parameter_key"]
        assert priors[0].objective_values == {"m1": 0.5}

    def test_rejects_failure_rows(self) -> None:
        rows = [_make_row(status="solver_failed")]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 0
        assert report.rejected_rows == 1
        assert "status_not_success" in report.rejection_reasons

    def test_rejects_gate_rejected(self) -> None:
        rows = [_make_row(status="gate_rejected")]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        assert "status_not_success" in report.rejection_reasons

    def test_rejects_schema_mismatch(self) -> None:
        rows = [_make_row(schema_version=99, objective_values={"m1": 0.5}, objective_names=["m1"])]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        assert "schema_incompatible" in report.rejection_reasons

    def test_rejects_missing_parameter_key(self) -> None:
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["parameter_key"] = ""
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        assert "missing_parameter_key" in report.rejection_reasons

    def test_rejects_param_names_mismatch(self) -> None:
        rows = [_make_row(param_names=["p0", "p1"], param_values=[1.0, 2.0], objective_values={"m1": 0.5}, objective_names=["m1"])]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        assert "param_names_mismatch" in report.rejection_reasons

    def test_rejects_objective_names_mismatch(self) -> None:
        rows = [_make_row(objective_values={"m1": 0.5}, objective_names=["m1", "m2"])]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        assert "objective_names_mismatch" in report.rejection_reasons

    def test_rejects_missing_objective_values(self) -> None:
        rows = [_make_row(objective_values=None, objective_names=None)]
        cfg = DbWarmStartConfig(enabled=True, require_objective_values=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        # The row lacks objective_names entirely, so it's rejected as
        # objective_names_mismatch (None != ["m1"]) before the values check.
        assert "objective_names_mismatch" in report.rejection_reasons

    def test_rejects_empty_objective_values(self) -> None:
        """Empty objective_values dict when names match is rejected."""
        rows = [_make_row(objective_values={}, objective_names=["m1"])]
        cfg = DbWarmStartConfig(enabled=True, require_objective_values=True)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows == 1
        assert "missing_objective_values" in report.rejection_reasons

    def test_duplicate_parameter_key_keeps_one(self) -> None:
        """Duplicate parameter_key: keep best (newest for same scalar)."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [
            _make_row(row_id=1, created_at="2025-01-01", objective_values={"m1": 0.5}, objective_names=["m1"]),
            _make_row(row_id=2, created_at="2026-01-01", objective_values={"m1": 0.5}, objective_names=["m1"]),
        ]
        # Both rows have same key
        rows[0]["parameter_key"] = key
        rows[1]["parameter_key"] = key
        cfg = DbWarmStartConfig(enabled=True, order_by="best_objective")
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1  # only one kept
        assert report.skipped_duplicates == 1

    def test_capping_by_max_priors(self) -> None:
        rows = [
            _make_row(row_id=i, param_values=[float(i)], objective_values={"m1": float(i)}, objective_names=["m1"])
            for i in range(1, 6)
        ]
        cfg = DbWarmStartConfig(enabled=True, max_priors=2)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 2
        assert report.capped is True

    def test_checkpoint_dedup(self) -> None:
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        key = row["parameter_key"]
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            [row], cfg,
            metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys={key},
        )
        assert report.accepted_priors == 0
        assert report.skipped_checkpoint_duplicates == 1

    def test_order_by_newest(self) -> None:
        rows = [
            _make_row(row_id=1, created_at="2025-01-01", objective_values={"m1": 0.5}, objective_names=["m1"]),
            _make_row(row_id=2, created_at="2026-01-01", objective_values={"m1": 0.8}, objective_names=["m1"]),
        ]
        # Ensure unique keys
        for i, r in enumerate(rows):
            pid = ParameterIdentity(param_names=["p0"], values=[float(i + 1)])
            r["parameter_key"] = pid.parameter_key()
            r["param_values"] = json.dumps([float(i + 1)])

        cfg = DbWarmStartConfig(enabled=True, order_by="newest")
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        priors = report.diagnostics.get("priors", [])
        assert len(priors) == 2
        # Newest first
        assert priors[0].parameter_key == rows[1]["parameter_key"]

    def test_order_by_best_objective(self) -> None:
        rows = [
            _make_row(row_id=1, objective_values={"m1": 5.0}, objective_names=["m1"]),
            _make_row(row_id=2, objective_values={"m1": 1.0}, objective_names=["m1"]),
        ]
        for i, r in enumerate(rows):
            pid = ParameterIdentity(param_names=["p0"], values=[float(i + 1)])
            r["parameter_key"] = pid.parameter_key()
            r["param_values"] = json.dumps([float(i + 1)])

        cfg = DbWarmStartConfig(enabled=True, order_by="best_objective")
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        priors = report.diagnostics.get("priors", [])
        assert len(priors) == 2
        # Best (lowest) scalar first
        assert priors[0].scalar <= priors[1].scalar


# ===================================================================
# Hardening: disabled config
# ===================================================================


class TestDisabledConfig:
    def test_disabled_returns_empty(self):
        """Disabled config returns empty report with zero priors."""
        rows = [_make_row(objective_values={"m1": 0.5}, objective_names=["m1"])]
        cfg = DbWarmStartConfig(enabled=False)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 0
        assert len(report.diagnostics.get("priors", [])) == 0


# ===================================================================
# Hardening: max_priors=0
# ===================================================================


class TestMaxPriorsZero:
    def test_resolver_accepts_zero(self):
        """Resolver accepts max_priors=0."""
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True, "max_priors": 0}}},
            db_enabled=True,
        )
        assert cfg.max_priors == 0

    def test_loader_returns_empty(self):
        """max_priors=0 returns no priors regardless of eligible rows."""
        rows = [_make_row(objective_values={"m1": 0.5}, objective_names=["m1"])]
        cfg = DbWarmStartConfig(enabled=True, max_priors=0)
        report = load_warm_start_priors(rows, cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 0
        assert report.capped is False


# ===================================================================
# Hardening: duplicate per-key policy
# ===================================================================


class TestDuplicateHardening:
    def test_worse_first_best_wins(self):
        """Duplicate key: best (lower scalar) row wins even if later."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        r1 = _make_row(row_id=1, param_values=[1.0], objective_values={"m1": 5.0}, objective_names=["m1"])
        r2 = _make_row(row_id=2, param_values=[1.0], objective_values={"m1": 1.0}, objective_names=["m1"])
        r1["parameter_key"] = key
        r2["parameter_key"] = key
        cfg = DbWarmStartConfig(enabled=True, order_by="best_objective")
        report = load_warm_start_priors([r1, r2], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1
        assert report.skipped_duplicates == 1
        priors = report.diagnostics.get("priors", [])
        assert priors[0].scalar == 1.0

    def test_same_scalar_newer_wins(self):
        """Duplicate key with same scalar: newer timestamp wins."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        r_old = _make_row(row_id=1, created_at="2025-01-01", param_values=[1.0],
                          objective_values={"m1": 0.5}, objective_names=["m1"])
        r_new = _make_row(row_id=2, created_at="2026-01-01", param_values=[1.0],
                          objective_values={"m1": 0.5}, objective_names=["m1"])
        r_old["parameter_key"] = key
        r_new["parameter_key"] = key
        cfg = DbWarmStartConfig(enabled=True, order_by="best_objective")
        report = load_warm_start_priors([r_old, r_new], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1
        priors = report.diagnostics.get("priors", [])
        assert priors[0].source_created_at == "2026-01-01"

    def test_same_timestamp_higher_id_wins(self):
        """Duplicate key with same timestamp: higher id wins."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        r1 = _make_row(row_id=1, param_values=[1.0], objective_values={"m1": 0.5}, objective_names=["m1"])
        r2 = _make_row(row_id=2, param_values=[1.0], objective_values={"m1": 0.5}, objective_names=["m1"])
        r1["parameter_key"] = key
        r2["parameter_key"] = key
        cfg = DbWarmStartConfig(enabled=True, order_by="best_objective")
        report = load_warm_start_priors([r1, r2], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1
        priors = report.diagnostics.get("priors", [])
        assert priors[0].source_row_id == 2

    def test_newest_mode_chooses_newest(self):
        """newest mode: newest timestamp wins even if scalar worse."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        r_old = _make_row(row_id=1, created_at="2025-01-01", param_values=[1.0],
                          objective_values={"m1": 0.1}, objective_names=["m1"])
        r_new = _make_row(row_id=2, created_at="2026-01-01", param_values=[1.0],
                          objective_values={"m1": 0.9}, objective_names=["m1"])
        r_old["parameter_key"] = key
        r_new["parameter_key"] = key
        cfg = DbWarmStartConfig(enabled=True, order_by="newest")
        report = load_warm_start_priors([r_old, r_new], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1
        priors = report.diagnostics.get("priors", [])
        assert priors[0].source_created_at == "2026-01-01"
        assert priors[0].scalar == 0.9


# ===================================================================
# Hardening: param identity validation
# ===================================================================


class TestParamIdentityHardening:
    def test_missing_param_values_rejected(self):
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["param_values"] = None
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "missing_param_values" in report.rejection_reasons

    def test_wrong_length_param_values_rejected(self):
        import json
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        # Manually set param_values to wrong length (doesn't match param_names)
        row["param_values"] = json.dumps([1.0, 2.0])
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "param_values_mismatch" in report.rejection_reasons

    def test_non_numeric_param_value_rejected(self):
        import json
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["param_values"] = json.dumps(["not_a_number"])
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "invalid_param_values" in report.rejection_reasons

    def test_parameter_key_mismatch_rejected(self):
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["parameter_key"] = "bogus_key_that_does_not_match"
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "parameter_key_mismatch" in report.rejection_reasons


# ===================================================================
# Hardening: objective payload validation
# ===================================================================


class TestObjectiveHardening:
    def test_objective_values_missing_keys_rejected(self):
        """Missing objective values keys: row rejected."""
        import json
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        # objective_values present but with different key
        row["objective_values"] = json.dumps({"other_key": 0.5})
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 0

    def test_non_numeric_objective_rejected(self):
        import json
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["objective_values"] = json.dumps({"m1": "not_numeric"})
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "invalid_objective_values" in report.rejection_reasons

    def test_nan_objective_rejected(self):
        import json
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["objective_values"] = json.dumps({"m1": float("nan")})
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "nonfinite_objective_values" in report.rejection_reasons

    def test_inf_objective_rejected(self):
        import json
        row = _make_row(objective_values={"m1": 0.5}, objective_names=["m1"])
        row["objective_values"] = json.dumps({"m1": float("inf")})
        cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors([row], cfg, metric_names=["m1"], param_names=["p0"])
        assert "nonfinite_objective_values" in report.rejection_reasons


# ===================================================================
# Hardening: allow_raw_recompute
# ===================================================================


class TestAllowRawRecompute:
    def test_allow_raw_true_raises(self):
        """allow_raw_recompute=True raises ValueError in WS2."""
        with pytest.raises(ValueError, match="allow_raw_recompute"):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True, "allow_raw_recompute": True}}},
                db_enabled=True,
            )


# ===================================================================
# Safety
# ===================================================================


class TestSafety:
    def test_no_cst_import(self) -> None:
        import cst_optimization.evaluation.evaluation_database_warm_start as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst."]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"

    def test_no_jsonl_reference(self) -> None:
        import cst_optimization.evaluation.evaluation_database_warm_start as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text
