"""No-CST tests for DB-backed success reuse lookup helper (SR2)."""

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

from workflows.rfgun_sao.evaluation_database_schema import (
    EvaluationDatabaseStatus,
    ParameterIdentity,
    current_schema_version,
)
from workflows.rfgun_sao.evaluation_success_reuse import (
    SuccessReuseConfig,
    find_eligible_success_record,
    reconstruct_evaluation_result,
    resolve_success_reuse_config,
)
from workflows.rfgun_sao.types import EvaluationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pid(values: list[float], precision: int | None = None) -> ParameterIdentity:
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
        precision=precision,
    )


def _make_row(
    status: str = "success",
    param_names: list[str] | None = None,
    schema_version: int | None = None,
    raw_metrics: dict | None = None,
    objective_values: dict | None = None,
    objective_names: list[str] | None = None,
    diagnostics: dict | None = None,
    row_id: int = 1,
    run_id: str = "run1",
    created_at: str = "2026-01-01 00:00:00",
) -> dict:
    """Build a fake DB row dict similar to what query_by_parameter_key returns."""
    if param_names is None:
        param_names = ["p0"]
    if schema_version is None:
        schema_version = current_schema_version()
    if objective_names is None and objective_values is not None:
        objective_names = list(objective_values.keys())
    row: dict = {
        "id": row_id,
        "schema_version": schema_version,
        "parameter_key": _pid([float(v) for v in [0] * len(param_names)]).parameter_key(),
        "param_names": json.dumps(param_names),
        "param_values": json.dumps([0.0] * len(param_names)),
        "param_precision": None,
        "status": status,
        "raw_metrics": json.dumps(raw_metrics) if raw_metrics else None,
        "objective_values": json.dumps(objective_values) if objective_values else None,
        "objective_names": json.dumps(objective_names) if objective_names else None,
        "gate_results": None,
        "diagnostics": json.dumps(diagnostics) if diagnostics else None,
        "artifact_refs": None,
        "source": "test",
        "provenance": None,
        "retry_count": 0,
        "error_taxonomy": None,
        "run_id": run_id,
        "created_at": created_at,
    }
    return row


class FakeDB:
    """Duck-typed SQLiteEvaluationDatabase for no-CST tests."""
    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def query_by_parameter_key(self, key: str) -> list[dict]:
        return [r for r in self._rows if r.get("parameter_key") == key]


# ===================================================================
# Config
# ===================================================================


class TestResolveConfig:
    def test_none_returns_disabled(self) -> None:
        cfg = resolve_success_reuse_config(None, db_enabled=False)
        assert cfg.enabled is False

    def test_missing_section_returns_disabled(self) -> None:
        cfg = resolve_success_reuse_config({}, db_enabled=False)
        assert cfg.enabled is False

    def test_explicit_disabled_returns_disabled(self) -> None:
        cfg = resolve_success_reuse_config(
            {"success_reuse": {"enabled": False}}, db_enabled=False,
        )
        assert cfg.enabled is False

    def test_enabled_without_db_raises(self) -> None:
        with pytest.raises(ValueError, match="requires evaluation_database.enabled=True"):
            resolve_success_reuse_config(
                {"success_reuse": {"enabled": True}}, db_enabled=False,
            )

    def test_enabled_with_db_ok(self) -> None:
        cfg = resolve_success_reuse_config(
            {"success_reuse": {"enabled": True}}, db_enabled=True,
        )
        assert cfg.enabled is True

    def test_default_values(self) -> None:
        cfg = resolve_success_reuse_config(
            {"success_reuse": {"enabled": True}}, db_enabled=True,
        )
        assert cfg.require_objective_values is True
        assert cfg.allow_raw_recompute is False
        assert cfg.max_age_days is None
        assert cfg.log_decisions is True


# ===================================================================
# find_eligible_success_record
# ===================================================================


class TestLookupDisabled:
    def test_disabled_returns_none(self) -> None:
        db = FakeDB()
        pid = _pid([1.0])
        cfg = SuccessReuseConfig(enabled=False)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_disabled_no_db_query(self) -> None:
        """When disabled, the DB is never queried."""
        class DBAssertNoQuery:
            def query_by_parameter_key(self, key):
                raise AssertionError("should not be called")
        cfg = SuccessReuseConfig(enabled=False)
        result = find_eligible_success_record(DBAssertNoQuery(), _pid([1.0]), ["m1"], cfg)
        assert result is None


class TestLookupEligibility:
    def test_exact_match_returns_row(self) -> None:
        pid = _pid([1.0])
        row = _make_row(param_names=["p0"], objective_values={"m1": 0.5}, objective_names=["m1"])
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is not None
        assert result["id"] == 1

    def test_different_key_returns_none(self) -> None:
        pid = _pid([1.0])
        other_pid = _pid([99.0])
        row = _make_row(param_names=["p0"], objective_values={"m1": 0.5}, objective_names=["m1"])
        row["parameter_key"] = other_pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_solver_failed_ignored(self) -> None:
        pid = _pid([1.0])
        row = _make_row(status="solver_failed", param_names=["p0"])
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_gate_rejected_ignored(self) -> None:
        pid = _pid([1.0])
        row = _make_row(status="gate_rejected", param_names=["p0"])
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_unknown_failed_ignored(self) -> None:
        pid = _pid([1.0])
        row = _make_row(status="unknown_failed", param_names=["p0"])
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_schema_mismatch_ignored(self) -> None:
        pid = _pid([1.0])
        row = _make_row(
            param_names=["p0"], schema_version=99,
            objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_missing_identity_returns_none(self) -> None:
        db = FakeDB()
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, None, ["m1"], cfg)
        assert result is None

    def test_missing_objective_values_rejected_default(self) -> None:
        """require_objective_values=True: row without objective_values rejected."""
        pid = _pid([1.0])
        row = _make_row(
            param_names=["p0"], status="success",
            raw_metrics={"m1": 1.0}, objective_values=None,
        )
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True, require_objective_values=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_raw_only_rejected_in_sr2(self) -> None:
        """SR2: raw-only rows are rejected (no safe recompute helper)."""
        pid = _pid([1.0])
        row = _make_row(
            param_names=["p0"], status="success",
            raw_metrics={"m1": 1.0}, objective_values=None,
            objective_names=["m1"],
        )
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True, require_objective_values=False)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_param_names_mismatch_ignored(self) -> None:
        pid = _pid([1.0, 2.0])  # 2 params
        row = _make_row(
            param_names=["p0"],  # 1 param — mismatch
            objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_objective_names_mismatch_ignored(self) -> None:
        pid = _pid([1.0])
        row = _make_row(
            param_names=["p0"], status="success",
            objective_values={"m1": 0.5}, objective_names=["m1", "m2"],
        )
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None

    def test_diagnostic_only_ignored(self) -> None:
        pid = _pid([1.0])
        row = _make_row(status="diagnostic_only", param_names=["p0"])
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is None


class TestLookupTieBreaking:
    def test_multiple_success_chooses_newest(self) -> None:
        pid = _pid([1.0])
        key = pid.parameter_key()
        older = _make_row(
            row_id=1, run_id="old", created_at="2025-01-01 00:00:00",
            param_names=["p0"], objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        newer = _make_row(
            row_id=2, run_id="new", created_at="2026-01-01 00:00:00",
            param_names=["p0"], objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        older["parameter_key"] = key
        newer["parameter_key"] = key
        db = FakeDB([older, newer])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is not None
        assert result["run_id"] == "new"

    def test_same_created_at_chooses_highest_id(self) -> None:
        pid = _pid([1.0])
        key = pid.parameter_key()
        r1 = _make_row(
            row_id=1, created_at="2026-01-01 00:00:00",
            param_names=["p0"], objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        r2 = _make_row(
            row_id=2, created_at="2026-01-01 00:00:00",
            param_names=["p0"], objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        r1["parameter_key"] = key
        r2["parameter_key"] = key
        db = FakeDB([r1, r2])
        cfg = SuccessReuseConfig(enabled=True)
        result = find_eligible_success_record(db, pid, ["m1"], cfg)
        assert result is not None
        assert result["id"] == 2


# ===================================================================
# reconstruct_evaluation_result
# ===================================================================


class TestReconstruction:
    def test_basic_reconstruction(self) -> None:
        row = _make_row(
            param_names=["p0"], status="success",
            raw_metrics={"m1": 1.0, "m2": 2.0},
            objective_values={"m1": 0.5, "m2": 1.0},
            objective_names=["m1", "m2"],
            diagnostics={"source": "original", "__retry_penalty__": {"m1": 0.3, "m2": 0.8}},
            row_id=42, run_id="test-run", created_at="2026-06-01 12:00:00",
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1", "m2"], config=cfg)
        assert result is not None
        assert result.status == EvaluationStatus.SUCCESS
        assert result.error == ""
        assert result.raw_metrics == {"m1": 1.0, "m2": 2.0}
        assert result.objective_values == {"m1": 0.5, "m2": 1.0}
        assert result.diagnostics is not None
        assert result.diagnostics.get("reused_from_db") is True
        assert result.diagnostics.get("source_row_id") == 42
        assert result.diagnostics.get("source_run_id") == "test-run"

    def test_penalty_from_diagnostics(self) -> None:
        row = _make_row(
            param_names=["p0"], status="success",
            objective_values={"m1": 0.5}, objective_names=["m1"],
            diagnostics={"__retry_penalty__": {"m1": 0.3}},
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result is not None
        assert result.penalty_values == {"m1": 0.3}

    def test_fallback_penalty_with_raw_recompute(self) -> None:
        """Row without __retry_penalty__ uses objective_values when allow_raw_recompute=True."""
        row = _make_row(
            param_names=["p0"], status="success",
            objective_values={"m1": 0.5}, objective_names=["m1"],
        )
        cfg = SuccessReuseConfig(enabled=True, allow_raw_recompute=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result is not None
        assert "m1" in (result.penalty_values or {})

    def test_no_failure_reconstruction(self) -> None:
        """EvaluationResult from reuse is always SUCCESS."""
        row = _make_row(
            status="success", param_names=["p0"],
            objective_values={"m1": 0.5}, objective_names=["m1"],
            diagnostics={"__retry_penalty__": {"m1": 0.3}},
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result.status == EvaluationStatus.SUCCESS

    def test_inject_reuse_provenance(self) -> None:
        row = _make_row(
            row_id=7, run_id="abc", created_at="2026-06-01 12:00:00",
            param_names=["p0"], status="success",
            objective_values={"m1": 0.5}, objective_names=["m1"],
            diagnostics={"__retry_penalty__": {"m1": 0.3}},
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result.diagnostics.get("reused_from_db") is True
        assert result.diagnostics.get("source_row_id") == 7
        assert result.diagnostics.get("source_run_id") == "abc"
        assert result.diagnostics.get("source_created_at") == "2026-06-01 12:00:00"

    def test_f0_from_raw_metrics(self) -> None:
        row = _make_row(
            param_names=["p0"], status="success",
            objective_values={"resonant_freq": 11.424}, objective_names=["resonant_freq"],
            raw_metrics={"resonant_freq": 11.424},
            diagnostics={"__retry_penalty__": {"resonant_freq": 0.3}},
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["resonant_freq"], config=cfg)
        assert result.f0_ghz == 11.424


# ===================================================================
# max_age_days
# ===================================================================


class TestMaxAgeDays:
    def test_max_age_days_rejected_at_config(self) -> None:
        """max_age_days is not supported in SR2; raises ValueError."""
        with pytest.raises(ValueError, match="max_age_days is not supported"):
            resolve_success_reuse_config(
                {"success_reuse": {"enabled": True, "max_age_days": 30}},
                db_enabled=True,
            )

    def test_max_age_days_raises_from_lookup(self) -> None:
        """Lookup raises ValueError when max_age_days is set."""
        pid = _pid([1.0])
        row = _make_row(
            param_names=["p0"], objective_values={"m1": 0.5},
            objective_names=["m1"],
        )
        row["parameter_key"] = pid.parameter_key()
        db = FakeDB([row])
        cfg = SuccessReuseConfig(enabled=True, max_age_days=30)
        with pytest.raises(ValueError, match="max_age_days"):
            find_eligible_success_record(db, pid, ["m1"], cfg)


# ===================================================================
# Reconstruction safety
# ===================================================================


class TestReconstructionSafety:
    def test_no_objective_values_returns_none(self) -> None:
        """reconstruct_evaluation_result returns None without objective_values."""
        row = _make_row(
            param_names=["p0"], status="success",
            raw_metrics={"m1": 1.0}, objective_values=None,
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result is None, "should return None when objective_values missing"

    def test_empty_objective_values_returns_none(self) -> None:
        """Empty objective_values dict returns None."""
        row = _make_row(
            param_names=["p0"], status="success",
            objective_values={}, objective_names=[],
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result is None

    def test_row_with_persisted_penalty_reconstructs(self) -> None:
        """Row with __retry_penalty__ reconstructs successfully."""
        row = _make_row(
            param_names=["p0"], status="success",
            objective_values={"m1": 0.5}, objective_names=["m1"],
            diagnostics={"__retry_penalty__": {"m1": 0.3}},
        )
        cfg = SuccessReuseConfig(enabled=True)
        result = reconstruct_evaluation_result(row, ["m1"], config=cfg)
        assert result is not None
        assert result.status == EvaluationStatus.SUCCESS
        assert result.penalty_values == {"m1": 0.3}


# ===================================================================
# Safety
# ===================================================================


class TestSafety:
    def test_no_cst_import(self) -> None:
        import workflows.rfgun_sao.evaluation_success_reuse as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = [
            "cst.interface", "cst.results", "import cst", "from cst",
            "cst_optimization",
        ]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"

    def test_no_jsonl_reference(self) -> None:
        import workflows.rfgun_sao.evaluation_success_reuse as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text
        assert "jsonl" not in text.lower() or "json" not in text
