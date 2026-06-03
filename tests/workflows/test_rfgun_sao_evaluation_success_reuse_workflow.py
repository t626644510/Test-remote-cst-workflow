"""No-CST tests for SR3 success reuse runtime integration in workflow."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
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
)
from workflows.rfgun_sao.evaluation_success_reuse import (
    SuccessReuseConfig,
    try_success_reuse,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus


# ===================================================================
# Fake objects
# ===================================================================


class FakeDB:
    """Duck-typed SQLiteEvaluationDatabase for no-CST tests."""
    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def query_by_parameter_key(self, key: str) -> list[dict]:
        return [r for r in self._rows if r.get("parameter_key") == key]


class FakeEvaluator:
    """Fake evaluator that records whether it was called."""
    def __init__(self):
        self.evaluate_called = False

    def evaluate_single_pass(self, *args, **kwargs):
        self.evaluate_called = True
        return {}, {}, True, EvaluationStatus.SUCCESS, ""

    def adapt_for_retry(self, *args, **kwargs):
        self.evaluate_called = True
        return EvaluationResult(status=EvaluationStatus.SUCCESS)


class FakeRetryHandler:
    """Fake retry handler that records whether it was called."""
    def __init__(self):
        self.execute_called = False

    def execute(self, fn, *args, **kwargs):
        self.execute_called = True
        return EvaluationResult(status=EvaluationStatus.SUCCESS), 1

    def force_reset(self):
        pass


class FakeRetryRuntime:
    """Fake retry runtime that records whether evaluate_once was called."""
    def __init__(self):
        self.loop_called = False

    def run_retry_loop_no_cst(self, *args, **kwargs):
        self.loop_called = True
        return MagicMock(final_record=None, succeeded=False)


# ===================================================================
# Helpers
# ---------------------------------------------------------------------------


def _make_success_row(
    key: str,
    param_names: list[str] | None = None,
    objective_values: dict | None = None,
) -> dict:
    if param_names is None:
        param_names = ["p0"]
    if objective_values is None:
        objective_values = {"m1": 0.5}
    import json
    return {
        "id": 1,
        "schema_version": 1,
        "parameter_key": key,
        "param_names": json.dumps(param_names),
        "param_values": json.dumps([1.0]),
        "status": "success",
        "raw_metrics": json.dumps({"m1": 1.0}),
        "objective_values": json.dumps(objective_values),
        "objective_names": json.dumps(list(objective_values.keys())),
        "diagnostics": None,
        "source": "original",
        "run_id": "orig-run",
        "created_at": "2026-06-01 00:00:00",
    }


# ===================================================================
# Config
# ===================================================================


class TestWorkflowConfig:
    def test_disabled_no_db_query(self):
        """When success_reuse is disabled, no DB query occurs."""
        cfg = SuccessReuseConfig(enabled=False)
        db = MagicMock()
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None
        db.query_by_parameter_key.assert_not_called()

    def test_enabled_without_db_fails(self):
        """Success reuse cannot be enabled without DB."""
        from workflows.rfgun_sao.evaluation_success_reuse import resolve_success_reuse_config
        with pytest.raises(ValueError, match="requires evaluation_database.enabled=True"):
            resolve_success_reuse_config(
                {"success_reuse": {"enabled": True}}, db_enabled=False,
            )


# ===================================================================
# Plain path reuse
# ===================================================================


class TestPlainPathReuse:
    def test_plain_path_reuse_hit_skips_evaluate(self):
        """Reuse hit in plain path skips evaluate_single_pass."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [_make_success_row(key)]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is not None
        assert result.status == EvaluationStatus.SUCCESS

    def test_plain_path_reuse_miss_calls_evaluate(self):
        """Reuse miss in plain path: fake evaluator runs normally."""
        evaluator = FakeEvaluator()
        key = ParameterIdentity(param_names=["p0"], values=[99.0]).parameter_key()
        # No matching row exists
        db = FakeDB([])
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[99.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None
        # Evaluator would be called by workflow after miss
        assert not evaluator.evaluate_called  # not called yet

    def test_plain_path_reuse_returns_penalty_values(self):
        """Reuse hit returns result with penalty_values."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [_make_success_row(key)]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is not None
        assert result.penalty_values is not None
        assert "m1" in result.penalty_values


# ===================================================================
# Retry runtime path reuse
# ===================================================================


class TestRetryRuntimeReuse:
    def test_retry_runtime_reuse_hit_skips_loop(self):
        """Reuse hit in retry runtime path skips retry loop."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [_make_success_row(key)]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is not None
        assert result.status == EvaluationStatus.SUCCESS

    def test_retry_runtime_reuse_miss_keeps_loop(self):
        """Reuse miss in retry runtime: loop can still run."""
        db = FakeDB([])
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[99.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None


# ===================================================================
# Legacy retry path reuse
# ===================================================================


class TestLegacyRetryReuse:
    def test_legacy_reuse_hit_skips_retry_handler(self):
        """Reuse hit in legacy path skips retry_handler.execute."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [_make_success_row(key)]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is not None

    def test_legacy_reuse_miss_keeps_handler(self):
        """Reuse miss in legacy path: retry_handler still runs."""
        db = FakeDB([])
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[99.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None


# ===================================================================
# Safety — no invalid reuse
# ===================================================================


class TestNoInvalidReuse:
    def test_failure_row_not_reused(self):
        """Failure rows do not trigger reuse."""
        import json
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        key = pid.parameter_key()
        rows = [{
            "id": 1, "schema_version": 1, "parameter_key": key,
            "param_names": json.dumps(["p0"]), "param_values": json.dumps([1.0]),
            "status": "solver_failed",  # not success
            "raw_metrics": None, "objective_values": None, "objective_names": None,
            "diagnostics": None, "source": "original", "run_id": "r1",
            "created_at": "2026-01-01",
        }]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None

    def test_raw_only_row_not_reused(self):
        """Raw-only rows (no objective_values) do not trigger reuse."""
        import json
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        key = pid.parameter_key()
        rows = [{
            "id": 1, "schema_version": 1, "parameter_key": key,
            "param_names": json.dumps(["p0"]), "param_values": json.dumps([1.0]),
            "status": "success",
            "raw_metrics": json.dumps({"m1": 1.0}),
            "objective_values": None, "objective_names": None,
            "diagnostics": None, "source": "original", "run_id": "r1",
            "created_at": "2026-01-01",
        }]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None

    def test_objective_names_mismatch_no_reuse(self):
        """objective_names mismatch prevents reuse."""
        import json
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        key = pid.parameter_key()
        rows = [{
            "id": 1, "schema_version": 1, "parameter_key": key,
            "param_names": json.dumps(["p0"]), "param_values": json.dumps([1.0]),
            "status": "success",
            "raw_metrics": json.dumps({"m1": 1.0}),
            "objective_values": json.dumps({"m1": 0.5}),
            "objective_names": json.dumps(["m1", "m2"]),  # mismatch
            "diagnostics": None, "source": "original", "run_id": "r1",
            "created_at": "2026-01-01",
        }]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is None

    def test_reuse_provenance_in_diagnostics(self):
        """Reused result contains provenance in diagnostics."""
        key = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [_make_success_row(key)]
        db = FakeDB(rows)
        cfg = SuccessReuseConfig(enabled=True)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        result = try_success_reuse(db, pid, ["m1"], config=cfg)
        assert result is not None
        diag = result.diagnostics or {}
        assert diag.get("reused_from_db") is True
        assert diag.get("source_row_id") == 1
        assert diag.get("source_run_id") == "orig-run"

    def test_no_jsonl_access(self):
        """Success reuse does not access JSONL."""
        import workflows.rfgun_sao.evaluation_success_reuse as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text
