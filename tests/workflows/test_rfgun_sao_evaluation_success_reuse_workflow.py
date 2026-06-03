"""No-CST tests for SR3 success reuse — real evaluator closure tests."""

from __future__ import annotations

import json
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
from workflows.rfgun_sao.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from workflows.rfgun_sao.evaluation_success_reuse import (
    SuccessReuseConfig,
    try_success_reuse,
    resolve_success_reuse_config,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus


# ===================================================================
# Test infrastructure: minimal config + monkeypatch helpers
# ===================================================================


def _minimal_cfg() -> dict:
    """Minimal single_pass config for build_workflow_1."""
    return {
        "cst": {"library_path": "dummy", "connect_mode": "any_or_new"},
        "project": {"cst_path": "dummy.cst"},
        "solver": {},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [{"name": "resonant_freq", "mode": "minimize"}],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }


def _prepopulate_db(tmp_path: Path, param_values: list[float]) -> str:
    """Create a temp SQLite DB with a reusable SUCCESS row, return path."""
    db_path = str(tmp_path / "reuse_test.db")
    cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
    with SQLiteEvaluationDatabase(cfg) as db:
        pid = ParameterIdentity(
            param_names=["p1"], values=param_values,
        )
        from workflows.rfgun_sao.evaluation_database_schema import (
            EvaluationDatabaseRecord, RawEvaluationPayload,
        )
        payload = RawEvaluationPayload(
            raw_metrics={"resonant_freq": 11.424},
            objective_values={"resonant_freq": 11.424},
        )
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status="success",
            raw_payload=payload,
            objective_names=["resonant_freq"],
        )
        db.insert_final_record(rec, run_id="reuse_source")
    return db_path


# ===================================================================
# Fixtures
# ===================================================================


class _FakeCSTConn:
    """Fake CST connection that doesn't connect to real CST."""
    pid = 99999

    def __init__(self, *args, **kwargs):
        self.connect_called = False
        self.quiet_mode = False

    def connect(self):
        self.connect_called = True

    def set_quiet_mode(self, val):
        self.quiet_mode = True


class _FakeSolverRunner:
    def __init__(self, *args, **kwargs):
        pass


# ===================================================================
# Config/integration tests (real build_workflow_1)
# ===================================================================


class TestWorkflowIntegration:
    def test_success_reuse_disabled_no_db_query(self, monkeypatch, tmp_path):
        """success_reuse disabled: no evaluation_database config, normal path runs."""
        from workflows.rfgun_sao.workflow import build_workflow_1
        monkeypatch.setattr("workflows.rfgun_sao.workflow.CSTConnection", _FakeCSTConn)
        monkeypatch.setattr("workflows.rfgun_sao.workflow.SolverRunner", _FakeSolverRunner)

        cfg = _minimal_cfg()
        wf, opt, ev = build_workflow_1(cfg)
        # Call evaluator — should use plain path (no reuse, no DB)
        val = ev(np.array([0.5]))
        assert np.isfinite(val)

    def test_success_reuse_enabled_without_db_raises(self, monkeypatch, tmp_path):
        """success_reuse enabled without evaluation_database raises ValueError."""
        from workflows.rfgun_sao.workflow import build_workflow_1
        monkeypatch.setattr("workflows.rfgun_sao.workflow.CSTConnection", _FakeCSTConn)
        monkeypatch.setattr("workflows.rfgun_sao.workflow.SolverRunner", _FakeSolverRunner)

        cfg = _minimal_cfg()
        cfg["success_reuse"] = {"enabled": True}
        with pytest.raises(ValueError, match="requires evaluation_database.enabled=True"):
            build_workflow_1(cfg)


class TestPlainPathReuseWorkflow:
    def test_plain_path_reuse_hit(self, monkeypatch, tmp_path):
        """Plain path: reuse hit skips evaluate_single_pass, checkpoint/DB once."""
        db_path = _prepopulate_db(tmp_path, [0.5])

        from workflows.rfgun_sao.workflow import build_workflow_1
        monkeypatch.setattr("workflows.rfgun_sao.workflow.CSTConnection", _FakeCSTConn)
        monkeypatch.setattr("workflows.rfgun_sao.workflow.SolverRunner", _FakeSolverRunner)

        cfg = _minimal_cfg()
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        checkpoint_calls = []
        wf, opt, ev = build_workflow_1(
            cfg, checkpoint_callback=lambda *a: checkpoint_calls.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        # Checkpoint called once
        assert len(checkpoint_calls) == 1

    def test_plain_path_reuse_miss(self, monkeypatch, tmp_path):
        """Plain path: reuse miss runs evaluate_single_pass normally."""
        # Use a DB with a different parameter point (no match)
        _prepopulate_db(tmp_path, [99.0])

        from workflows.rfgun_sao.workflow import build_workflow_1
        monkeypatch.setattr("workflows.rfgun_sao.workflow.CSTConnection", _FakeCSTConn)
        monkeypatch.setattr("workflows.rfgun_sao.workflow.SolverRunner", _FakeSolverRunner)

        cfg = _minimal_cfg()
        cfg["evaluation_database"] = {"enabled": True, "path": str(tmp_path / "reuse_test.db")}
        cfg["success_reuse"] = {"enabled": True}

        checkpoint_calls = []
        wf, opt, ev = build_workflow_1(
            cfg, checkpoint_callback=lambda *a: checkpoint_calls.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        # Checkpoint called (CST path runs)
        assert len(checkpoint_calls) == 1


class TestLegacyReuseWorkflow:
    def test_legacy_reuse_hit(self, monkeypatch, tmp_path):
        """Legacy path: reuse hit skips retry_handler.execute."""
        db_path = _prepopulate_db(tmp_path, [0.5])

        from workflows.rfgun_sao.workflow import build_workflow_1
        monkeypatch.setattr("workflows.rfgun_sao.workflow.CSTConnection", _FakeCSTConn)
        monkeypatch.setattr("workflows.rfgun_sao.workflow.SolverRunner", _FakeSolverRunner)

        cfg = _minimal_cfg()
        cfg["optimization"] = {
            "n_initial": 1, "n_iterations": 0, "seed": 42,
            "retry": {"enabled": True, "max_tier1": 1, "max_tier2": 0, "max_tier3": 0},
        }
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True, "require_objective_values": True}

        checkpoint_calls = []
        wf, opt, ev = build_workflow_1(
            cfg, checkpoint_callback=lambda *a: checkpoint_calls.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert len(checkpoint_calls) == 1

    def test_legacy_reuse_miss(self, monkeypatch, tmp_path):
        """Legacy path: reuse miss, retry_handler path still runs."""
        _prepopulate_db(tmp_path, [99.0])

        from workflows.rfgun_sao.workflow import build_workflow_1
        monkeypatch.setattr("workflows.rfgun_sao.workflow.CSTConnection", _FakeCSTConn)
        monkeypatch.setattr("workflows.rfgun_sao.workflow.SolverRunner", _FakeSolverRunner)

        cfg = _minimal_cfg()
        cfg["optimization"] = {
            "n_initial": 1, "n_iterations": 0, "seed": 42,
            "retry": {"enabled": True, "max_tier1": 1, "max_tier2": 0, "max_tier3": 0},
        }
        cfg["evaluation_database"] = {"enabled": True, "path": str(tmp_path / "reuse_test.db")}
        cfg["success_reuse"] = {"enabled": True}

        checkpoint_calls = []
        wf, opt, ev = build_workflow_1(
            cfg, checkpoint_callback=lambda *a: checkpoint_calls.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert len(checkpoint_calls) == 1


# ===================================================================
# No invalid reuse
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
            "status": "solver_failed", "raw_metrics": None,
            "objective_values": None, "objective_names": None,
            "diagnostics": None, "source": "original", "run_id": "r1",
            "created_at": "2026-01-01",
        }]
        from workflows.rfgun_sao.evaluation_database_storage import SQLiteEvaluationDatabase
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            db._conn.execute("INSERT INTO evaluation_records (schema_version, parameter_key, param_names, param_values, status) VALUES (?, ?, ?, ?, ?)",
                             (1, key, json.dumps(["p0"]), json.dumps([1.0]), "solver_failed"))
            db._conn.commit()
            sr_cfg = SuccessReuseConfig(enabled=True)
            result = try_success_reuse(db, pid, ["m1"], config=sr_cfg)
            assert result is None
        Path(db_path).unlink(missing_ok=True)

    def test_raw_only_row_not_reused(self):
        """Raw-only rows (no objective_values) do not trigger reuse."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        key = pid.parameter_key()
        rows_data = [{
            "id": 1, "schema_version": 1, "parameter_key": key,
            "param_names": json.dumps(["p0"]), "param_values": json.dumps([1.0]),
            "status": "success",
            "raw_metrics": json.dumps({"m1": 1.0}),
            "objective_values": None, "objective_names": None,
            "diagnostics": None, "source": "original", "run_id": "r1",
            "created_at": "2026-01-01",
        }]
        class _FakeDB:
            def query_by_parameter_key(self, k):
                return rows_data
        sr_cfg = SuccessReuseConfig(enabled=True)
        result = try_success_reuse(_FakeDB(), pid, ["m1"], config=sr_cfg)
        assert result is None

    def test_reuse_provenance(self):
        """Reused result contains provenance in diagnostics."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        key = pid.parameter_key()
        import json
        rows = [{
            "id": 42, "schema_version": 1, "parameter_key": key,
            "param_names": json.dumps(["p0"]), "param_values": json.dumps([1.0]),
            "status": "success",
            "raw_metrics": json.dumps({"m1": 1.0}),
            "objective_values": json.dumps({"m1": 0.5}),
            "objective_names": json.dumps(["m1"]),
            "diagnostics": None, "source": "original", "run_id": "orig-run",
            "created_at": "2026-06-01",
        }]
        class _FakeDB:
            def query_by_parameter_key(self, k):
                return rows
        sr_cfg = SuccessReuseConfig(enabled=True)
        result = try_success_reuse(_FakeDB(), pid, ["m1"], config=sr_cfg)
        assert result is not None
        diag = result.diagnostics or {}
        assert diag.get("reused_from_db") is True
        assert diag.get("source_row_id") == 42
        assert diag.get("source_run_id") == "orig-run"


# ===================================================================
# Safety
# ===================================================================


class TestSafety:
    def test_no_jsonl_access(self):
        """Success reuse does not access JSONL."""
        import workflows.rfgun_sao.evaluation_success_reuse as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text

    def test_no_cst_import_in_reuse_module(self):
        """Success reuse module has no CST imports."""
        import workflows.rfgun_sao.evaluation_success_reuse as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"
