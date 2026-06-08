"""No-CST tests for SR3 success reuse 鈥?call-count skip proof tests."""

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

from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseStatus,
    ParameterIdentity,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from cst_optimization.evaluation.evaluation_success_reuse import (
    SuccessReuseConfig,
    try_success_reuse,
    resolve_success_reuse_config,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus


# ===================================================================
# Call-count tracking fakes
# ===================================================================


class TrackerCSTConn:
    """Fake CST connection 鈥?tracks calls, no real CST."""
    pid = 99999
    def __init__(self, *args, **kwargs):
        self.connect_called = False
        self.quiet_mode = False
    def connect(self):
        self.connect_called = True
    def set_quiet_mode(self, val):
        self.quiet_mode = True
    def close(self, force=False):
        pass


class TrackerEval:
    """Fake Workflow1Evaluator 鈥?tracks evaluate_single_pass and adapt_for_retry."""
    def __init__(self):
        self.evaluate_single_pass_calls = 0
        self.adapt_for_retry_calls = 0

    def evaluate_single_pass(self, *args, **kwargs):
        self.evaluate_single_pass_calls += 1
        return (
            {"resonant_freq": 11.424},
            {"resonant_freq": 0.3},
            True,
            EvaluationStatus.SUCCESS,
            "",
        )

    def adapt_for_retry(self, params, iteration):
        self.adapt_for_retry_calls += 1
        return EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            raw_metrics={"resonant_freq": 11.424},
            objective_values={"resonant_freq": 11.424},
            penalty_values={"resonant_freq": 0.3},
        )

    def on_reconnect(self, new_conn):
        pass

    def last_diagnostics(self):
        return {}


class TrackerRetryHandler:
    """Fake EvaluationRetryHandler 鈥?tracks execute and force_reset."""
    def __init__(self):
        self.execute_calls = 0
        self.force_reset_calls = 0
        self._all_connections = []

    def execute(self, fn, params, iteration):
        self.execute_calls += 1
        return EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            raw_metrics={"resonant_freq": 11.424},
            objective_values={"resonant_freq": 11.424},
            penalty_values={"resonant_freq": 0.3},
        ), 1

    def force_reset(self):
        self.force_reset_calls += 1

    def close_all(self, force=False):
        pass


# ===================================================================
# Test infrastructure
# ===================================================================


class TrackerSolverRunner:
    def __init__(self, *args, **kwargs):
        pass


def _minimal_cfg() -> dict:
    """Minimal single_pass config."""
    return {
        "cst": {"library_path": "dummy", "connect_mode": "any_or_new"},
        "project": {"cst_path": "dummy.cst"},
        "solver": {},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [{"name": "resonant_freq", "mode": "minimize"}],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }


def _prepopulate_db(tmp_path: Path, param_values: list[float]) -> str:
    """Create temp SQLite DB with one reusable SUCCESS row. Return path."""
    db_path = str(tmp_path / "reuse_test.db")
    cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
    with SQLiteEvaluationDatabase(cfg) as db:
        pid = ParameterIdentity(
            param_names=["p1"], values=param_values,
        )
        from cst_optimization.evaluation.evaluation_database_schema import (
            EvaluationDatabaseRecord, RawEvaluationPayload,
        )
        payload = RawEvaluationPayload(
            raw_metrics={"resonant_freq": 11.424},
            objective_values={"resonant_freq": 11.424},
            diagnostics={"__retry_penalty__": {"resonant_freq": 0.3}},
        )
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status="success",
            raw_payload=payload,
            objective_names=["resonant_freq"],
        )
        db.insert_final_record(rec, run_id="reuse_source")
    return db_path


def _db_row_count(db_path: str) -> int:
    """Count evaluation_records rows in a SQLite DB."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
    conn.close()
    return count


def _db_latest_source(db_path: str) -> str:
    """Get the source of the newest row."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT source FROM evaluation_records ORDER BY id DESC LIMIT 1",
    ).fetchone()
    conn.close()
    return row[0] if row else ""


def _monkeypatch_build(wf_mod, monkeypatch, tracker_eval):
    """Monkeypatch workflow module components for no-CST tests."""
    monkeypatch.setattr(wf_mod, "CSTConnection", TrackerCSTConn)
    monkeypatch.setattr(wf_mod, "SolverRunner", TrackerSolverRunner)
    monkeypatch.setattr(wf_mod, "Workflow1Evaluator", lambda *a, **kw: tracker_eval)


# ===================================================================
# Tests
# ===================================================================


class TestPlainPathSkip:
    def test_plain_hit_skips_evaluate(self, monkeypatch, tmp_path):
        """Plain: reuse hit -> evaluate_single_pass not called, checkpoint once."""
        db_path = _prepopulate_db(tmp_path, [0.5])
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg = _minimal_cfg()
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        ckpt = []
        wf, opt, ev = wf_mod.build_workflow_1(
            cfg, checkpoint_callback=lambda *a: ckpt.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert tracker_eval.evaluate_single_pass_calls == 0, "CST not skipped!"
        assert len(ckpt) == 1
        assert _db_row_count(db_path) == 2  # source + reuse
        assert _db_latest_source(db_path) == "db_success_reuse"

    def test_plain_miss_calls_evaluate(self, monkeypatch, tmp_path):
        """Plain: reuse miss -> evaluate_single_pass called once."""
        db_path = _prepopulate_db(tmp_path, [99.0])  # mismatched key
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg = _minimal_cfg()
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        ckpt = []
        wf, opt, ev = wf_mod.build_workflow_1(
            cfg, checkpoint_callback=lambda *a: ckpt.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert tracker_eval.evaluate_single_pass_calls == 1
        assert len(ckpt) == 1


class TestLegacyPathSkip:
    def test_legacy_hit_skips_handler(self, monkeypatch, tmp_path):
        """Legacy: reuse hit -> retry_handler.execute not called."""
        db_path = _prepopulate_db(tmp_path, [0.5])
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg = _minimal_cfg()
        cfg["optimization"] = {
            "n_initial": 1, "n_iterations": 0, "seed": 42,
            "retry": {"enabled": True, "max_tier1": 1, "max_tier2": 0, "max_tier3": 0},
        }
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        # Monkeypatch EvaluationRetryHandler too
        handler = TrackerRetryHandler()
        monkeypatch.setattr(wf_mod, "EvaluationRetryHandler", lambda *a, **kw: handler)

        ckpt = []
        wf, opt, ev = wf_mod.build_workflow_1(
            cfg, checkpoint_callback=lambda *a: ckpt.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert handler.execute_calls == 0, "retry_handler not skipped!"
        assert tracker_eval.adapt_for_retry_calls == 0
        assert len(ckpt) == 1
        assert _db_latest_source(db_path) == "db_success_reuse"

    def test_legacy_miss_calls_handler(self, monkeypatch, tmp_path):
        """Legacy: reuse miss -> retry_handler.execute called once."""
        db_path = _prepopulate_db(tmp_path, [99.0])
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg = _minimal_cfg()
        cfg["optimization"] = {
            "n_initial": 1, "n_iterations": 0, "seed": 42,
            "retry": {"enabled": True, "max_tier1": 1, "max_tier2": 0, "max_tier3": 0},
        }
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        handler = TrackerRetryHandler()
        monkeypatch.setattr(wf_mod, "EvaluationRetryHandler", lambda *a, **kw: handler)

        ckpt = []
        wf, opt, ev = wf_mod.build_workflow_1(
            cfg, checkpoint_callback=lambda *a: ckpt.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert handler.execute_calls >= 1


class TestRetryRuntimePathSkip:
    def test_retry_runtime_hit_skips_cst(self, monkeypatch, tmp_path):
        """Retry runtime: reuse hit -> no evaluate_single_pass called."""
        db_path = _prepopulate_db(tmp_path, [0.5])
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg = _minimal_cfg()
        cfg["optimization"] = {
            "n_initial": 1, "n_iterations": 0, "seed": 42,
            "retry": {"enabled": False},
        }
        cfg["retry_runtime"] = {"enabled": True, "max_tier": 1}
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        ckpt = []
        wf, opt, ev = wf_mod.build_workflow_1(
            cfg, checkpoint_callback=lambda *a: ckpt.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert tracker_eval.evaluate_single_pass_calls == 0, "CST eval not skipped!"
        assert len(ckpt) == 1
        assert _db_latest_source(db_path) == "db_success_reuse"

    def test_retry_runtime_miss_calls_eval(self, monkeypatch, tmp_path):
        """Retry runtime: reuse miss -> evaluate_single_pass called."""
        db_path = _prepopulate_db(tmp_path, [99.0])
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg = _minimal_cfg()
        cfg["optimization"] = {
            "n_initial": 1, "n_iterations": 0, "seed": 42,
            "retry": {"enabled": False},
        }
        cfg["retry_runtime"] = {"enabled": True, "max_tier": 1}
        cfg["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg["success_reuse"] = {"enabled": True}

        ckpt = []
        wf, opt, ev = wf_mod.build_workflow_1(
            cfg, checkpoint_callback=lambda *a: ckpt.append(a),
        )
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert tracker_eval.evaluate_single_pass_calls >= 1


class TestNegativeReuse:
    @pytest.mark.parametrize("status", [
        "solver_failed", "gate_rejected", "unknown_failed",
    ])
    def test_non_success_rows_not_reused(self, monkeypatch, tmp_path, status):
        """Non-success status rows do not trigger reuse; normal path runs."""
        import sqlite3, json
        db_path = str(tmp_path / "negative.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p1"], values=[0.5])
            # Insert via raw SQL to avoid validate_evaluation_record rejecting status
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), json.dumps(["p1"]),
                 json.dumps([0.5]), status),
            )
            db._conn.commit()
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg2 = _minimal_cfg()
        cfg2["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg2["success_reuse"] = {"enabled": True}

        wf, opt, ev = wf_mod.build_workflow_1(cfg2)
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        # Normal path must have run
        assert tracker_eval.evaluate_single_pass_calls >= 1

    def test_raw_only_not_reused(self, monkeypatch, tmp_path):
        """Raw-only row (no objective_values) does not trigger reuse."""
        import sqlite3, json
        db_path = str(tmp_path / "raw_only.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p1"], values=[0.5])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, raw_metrics) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), json.dumps(["p1"]),
                 json.dumps([0.5]), "success", json.dumps({"m1": 1.0})),
            )
            db._conn.commit()
        tracker_eval = TrackerEval()
        from workflows.rfgun_sao import workflow as wf_mod
        _monkeypatch_build(wf_mod, monkeypatch, tracker_eval)

        cfg2 = _minimal_cfg()
        cfg2["evaluation_database"] = {"enabled": True, "path": db_path}
        cfg2["success_reuse"] = {"enabled": True}

        wf, opt, ev = wf_mod.build_workflow_1(cfg2)
        val = ev(np.array([0.5]))
        assert np.isfinite(val)
        assert tracker_eval.evaluate_single_pass_calls >= 1

