"""No-CST tests for FS4 failure skip enforce helper.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
Enforce skip never calls evaluator when skip is active.
"""

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
    ParameterIdentity,
    current_schema_version,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from cst_optimization.evaluation.failure_skip_candidates import (
    FailureSkipCandidateConfig,
)
from cst_optimization.evaluation.failure_skip_enforce import (
    FakeEnforceEvaluationResult,
    FailureSkipEnforceDecision,
    FailureSkipRuntimeResult,
    evaluate_failure_skip_enforce_for_key,
    run_failure_skip_enforce_fake_evaluation,
    run_failure_skip_evaluator,
)


# ===================================================================
# Helpers
# ===================================================================


def _seed_db(tmp_path: Path, rows: list[dict]) -> str:
    """Create a temp DB with the given rows.  Returns path."""
    db_path = str(tmp_path / "fs_test.db")
    cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
    with SQLiteEvaluationDatabase(cfg) as db:
        for row in rows:
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "raw_metrics, objective_values, objective_names, source, "
                "diagnostics, error_taxonomy, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.get("schema_version", current_schema_version()),
                    row.get("parameter_key", ""),
                    json.dumps(row.get("param_names", ["p0"])),
                    json.dumps(row.get("param_values", [1.0])),
                    row.get("status", "success"),
                    json.dumps(row.get("raw_metrics")) if row.get("raw_metrics") else None,
                    json.dumps(row.get("objective_values")) if row.get("objective_values") else None,
                    json.dumps(row.get("objective_names", ["m1"])),
                    row.get("source"),
                    json.dumps(row.get("diagnostics")) if row.get("diagnostics") else None,
                    json.dumps(row.get("error_taxonomy")) if row.get("error_taxonomy") else None,
                    row.get("run_id", "r1"),
                    row.get("created_at", "2026-06-04 00:00:00"),
                ),
            )
        db._conn.commit()
    return db_path


def _solver_failed_row(
    param_values: list[float],
    row_id: int = 1,
    taxonomy: dict | None = None,
) -> dict:
    """Convenience: create a solver_failed row with deterministic taxonomy."""
    if taxonomy is None:
        taxonomy = {"original_error": "mesh error", "original_status": "solver_failed"}
    pid = ParameterIdentity(param_names=["p0"], values=param_values)
    return {
        "id": row_id,
        "schema_version": current_schema_version(),
        "parameter_key": pid.parameter_key(),
        "param_names": ["p0"],
        "param_values": list(param_values),
        "status": "solver_failed",
        "raw_metrics": {"m1": 1.0},
        "objective_names": ["m1"],
        "error_taxonomy": dict(taxonomy) if taxonomy else None,
        "source": None,
        "run_id": "r1",
        "created_at": "2026-06-04 00:00:00",
    }


# ===================================================================
# Enforce decision tests
# ===================================================================


class TestEnforceDecision:
    def test_disabled_no_enforce(self, tmp_path):
        cfg = FailureSkipCandidateConfig(enabled=False, mode="enforce")
        decision = evaluate_failure_skip_enforce_for_key(
            str(tmp_path / "nonexistent.db"), "some_key", cfg,
        )
        assert not decision.enforce_skip
        assert decision.evaluator_must_run

    def test_dry_run_no_enforce(self, tmp_path):
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        decision = evaluate_failure_skip_enforce_for_key(db_path, pk, cfg)
        assert not decision.enforce_skip
        assert decision.evaluator_must_run

    def test_enforce_no_candidate_no_skip(self, tmp_path):
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=1)
        decision = evaluate_failure_skip_enforce_for_key(
            db_path, "nonexistent_key", cfg,
        )
        assert not decision.enforce_skip
        assert not decision.candidate_found
        assert decision.evaluator_must_run

    def test_enforce_candidate_below_threshold_no_skip(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)
        decision = evaluate_failure_skip_enforce_for_key(db_path, pk, cfg)
        assert not decision.enforce_skip
        assert decision.evaluator_must_run

    def test_enforce_candidate_meets_threshold_skips(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([1.0], 2),
        ]
        rows[0]["parameter_key"] = pk
        rows[1]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)
        decision = evaluate_failure_skip_enforce_for_key(db_path, pk, cfg)
        assert decision.enforce_skip
        assert decision.candidate_found
        assert decision.candidate_decision == "enforce_eligible"
        assert decision.evidence_count == 2
        assert not decision.evaluator_must_run
        assert not decision.retry_must_run
        assert not decision.budget_consumed
        assert decision.synthetic_status == "skipped_failure_reuse"

    def test_enforce_xr_process_kill_no_skip(self, tmp_path):
        """XR process-kill evidence is hard-blocked; no enforce skip."""
        row = {
            "id": 1,
            "schema_version": current_schema_version(),
            "parameter_key": "some_key",
            "param_names": ["p0"],
            "param_values": [1.0],
            "status": "solver_failed",
            "raw_metrics": {"m1": 1.0},
            "objective_names": ["m1"],
            "error_taxonomy": {"original_error": "tree path not found"},
            "source": None,
            "run_id": "r1",
            "created_at": "2026-06-04 00:00:00",
        }
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=1)
        decision = evaluate_failure_skip_enforce_for_key(db_path, "some_key", cfg)
        assert not decision.enforce_skip
        assert decision.evaluator_must_run

    def test_enforce_unknown_exception_allowed_with_threshold(self, tmp_path):
        """Unknown exception can be enforced if explicitly configured."""
        row = {
            "id": 1,
            "schema_version": current_schema_version(),
            "parameter_key": "uk_key",
            "param_names": ["p0"],
            "param_values": [1.0],
            "status": "weird_status",
            "raw_metrics": {"m1": 1.0},
            "objective_names": ["m1"],
            "error_taxonomy": None,
            "source": None,
            "run_id": "r1",
            "created_at": "2026-06-04 00:00:00",
        }
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(
            enabled=True, mode="enforce", min_failures=1,
            allow_unknown_exception=True,
        )
        decision = evaluate_failure_skip_enforce_for_key(db_path, "uk_key", cfg)
        assert decision.enforce_skip, "unknown_exception should enforce when configured"
        assert not decision.evaluator_must_run


# ===================================================================
# Fake-runtime enforce harness call-count tests
# ===================================================================


class TestFakeEnforceHarness:
    def test_enforce_hit_does_not_call_evaluator(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([1.0], 2),
        ]
        rows[0]["parameter_key"] = pk
        rows[1]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_enforce_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert result.enforce_skip
        assert not result.evaluator_called
        assert call_count[0] == 0, "evaluator must NOT be called on enforce skip"
        assert result.objective_value is None

    def test_enforce_hit_retry_wrapper_not_called(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([1.0], 2),
        ]
        rows[0]["parameter_key"] = pk
        rows[1]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        eval_count = [0]
        retry_count = [0]
        def fake_ev(pk):
            eval_count[0] += 1
            return 42.0
        def fake_retry(ev, **kw):
            retry_count[0] += 1
            return ev(kw.get("parameter_key", ""))

        result = run_failure_skip_enforce_fake_evaluation(
            db_path, pk, cfg, fake_ev, retry_wrapper=fake_retry,
        )
        assert result.enforce_skip
        assert not result.evaluator_called
        assert not result.retry_called
        assert eval_count[0] == 0
        assert retry_count[0] == 0

    def test_enforce_miss_calls_evaluator_once(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_enforce_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert not result.enforce_skip
        assert result.evaluator_called
        assert call_count[0] == 1

    def test_enforce_miss_with_retry_wrapper(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        eval_count = [0]
        retry_count = [0]
        def fake_ev(pk):
            eval_count[0] += 1
            return 42.0
        def fake_retry(ev, **kw):
            retry_count[0] += 1
            return ev(kw.get("parameter_key", ""))

        result = run_failure_skip_enforce_fake_evaluation(
            db_path, pk, cfg, fake_ev, retry_wrapper=fake_retry,
        )
        assert not result.enforce_skip
        assert result.evaluator_called
        assert result.retry_called
        assert eval_count[0] == 1
        assert retry_count[0] == 1

    def test_disabled_calls_evaluator_once(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=False, mode="enforce")

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_enforce_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert not result.enforce_skip
        assert result.evaluator_called
        assert call_count[0] == 1

    def test_dry_run_calls_evaluator_once(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([1.0], 2),
        ]
        rows[0]["parameter_key"] = pk
        rows[1]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=2)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_enforce_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert not result.enforce_skip
        assert result.evaluator_called
        assert call_count[0] == 1

    def test_xr_blocked_calls_evaluator_once(self, tmp_path):
        row = {
            "id": 1,
            "schema_version": current_schema_version(),
            "parameter_key": "xr_key",
            "param_names": ["p0"],
            "param_values": [1.0],
            "status": "solver_failed",
            "raw_metrics": {"m1": 1.0},
            "objective_names": ["m1"],
            "error_taxonomy": {"original_error": "tree path not found"},
            "source": None,
            "run_id": "r1",
            "created_at": "2026-06-04 00:00:00",
        }
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=1)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 0.0

        result = run_failure_skip_enforce_fake_evaluation(db_path, "xr_key", cfg, fake_ev)
        assert not result.enforce_skip
        assert result.evaluator_called
        assert call_count[0] == 1


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_subprocess(self):
        import cst_optimization.evaluation.failure_skip_enforce as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "import subprocess" not in text
        assert "from subprocess" not in text

    def test_no_os_system(self):
        import cst_optimization.evaluation.failure_skip_enforce as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "os.system" not in text

    def test_no_taskkill(self):
        import cst_optimization.evaluation.failure_skip_enforce as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "taskkill" not in text
        assert "Stop-Process" not in text

    def test_no_cst_import(self):
        import cst_optimization.evaluation.failure_skip_enforce as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst."]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"


# ===================================================================
# Runtime evaluator wrapper tests (FS5)
# ===================================================================


class TestRuntimeEvaluatorWrapper:
    """run_failure_skip_evaluator() call-count and synthetic row tests."""

    def _make_pid(self, values):
        pid = ParameterIdentity(param_names=["p0"], values=values)
        return pid, pid.parameter_key()

    def _seed_enforce_candidate(self, tmp_path, key, count=2):
        """Seed *count* solver_failed rows for *key*."""
        rows = []
        for i in range(count):
            rows.append({
                "id": i + 1,
                "schema_version": current_schema_version(),
                "parameter_key": key,
                "param_names": ["p0"],
                "param_values": [1.0],
                "status": "solver_failed",
                "raw_metrics": {"m1": 1.0},
                "objective_names": ["m1"],
                "error_taxonomy": {"original_error": "mesh error", "original_status": "solver_failed"},
                "source": None,
                "run_id": "r1",
                "created_at": "2026-06-04 00:00:00",
            })
        return _seed_db(tmp_path, rows)

    def test_enforce_hit_skips_evaluator(self, tmp_path):
        """Enforce hit -> evaluator NOT called."""
        pid, pk = self._make_pid([1.0])
        db_path = self._seed_enforce_candidate(tmp_path, pk, 2)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_evaluator(db_path, pk, cfg, fake_ev,
            param_names=["p0"], param_values=[1.0],
            write_synthetic_row=True,
        )
        assert result.enforced_skip
        assert not result.evaluator_called
        assert call_count[0] == 0
        assert result.synthetic_status == "skipped_failure_reuse"

    def test_enforce_hit_writes_synthetic_row(self, tmp_path):
        """Enforce hit writes exactly one synthetic skip row."""
        pid, pk = self._make_pid([1.0])
        db_path = self._seed_enforce_candidate(tmp_path, pk, 2)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        conn = __import__("sqlite3").connect(db_path)
        before = conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn.close()

        result = run_failure_skip_evaluator(db_path, pk, cfg, lambda x: 42.0,
            param_names=["p0"], param_values=[1.0],
            write_synthetic_row=True,
        )

        conn2 = __import__("sqlite3").connect(db_path)
        after = conn2.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        row = conn2.execute("SELECT status, source FROM evaluation_records WHERE id = ?",
                          (result.synthetic_row_id,)).fetchone()
        conn2.close()

        assert after == before + 1, "must write exactly one row"
        assert row[0] == "skipped_failure_reuse"
        assert row[1] == "failure_skip_enforce"

    def test_enforce_miss_calls_evaluator(self, tmp_path):
        """Enforce miss (below threshold) -> evaluator called once."""
        pid, pk = self._make_pid([1.0])
        db_path = self._seed_enforce_candidate(tmp_path, pk, 1)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_evaluator(db_path, pk, cfg, fake_ev,
            param_names=["p0"], param_values=[1.0],
        )
        assert not result.enforced_skip
        assert result.evaluator_called
        assert call_count[0] == 1
        assert result.objective_value == 42.0

    def test_enforce_hit_no_synthetic_row_when_disabled(self, tmp_path):
        """Enforce hit with write_synthetic_row=False does not write row."""
        pid, pk = self._make_pid([1.0])
        db_path = self._seed_enforce_candidate(tmp_path, pk, 2)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=2)

        conn = __import__("sqlite3").connect(db_path)
        before = conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn.close()

        result = run_failure_skip_evaluator(db_path, pk, cfg, lambda x: 42.0,
            param_names=["p0"], param_values=[1.0],
            write_synthetic_row=False,
        )
        assert result.enforced_skip
        assert result.synthetic_row_id is None

        conn2 = __import__("sqlite3").connect(db_path)
        after = conn2.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn2.close()
        assert after == before

    def test_dry_run_calls_evaluator_once(self, tmp_path):
        """dry_run mode -> evaluator called once, no synthetic row."""
        pid, pk = self._make_pid([1.0])
        db_path = self._seed_enforce_candidate(tmp_path, pk, 2)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=2)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        conn = __import__("sqlite3").connect(db_path)
        before = conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn.close()

        result = run_failure_skip_evaluator(db_path, pk, cfg, fake_ev,
            param_names=["p0"], param_values=[1.0],
        )
        assert not result.enforced_skip
        assert result.evaluator_called
        assert call_count[0] == 1

        conn2 = __import__("sqlite3").connect(db_path)
        after = conn2.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn2.close()
        assert after == before

    def test_xr_blocked_calls_evaluator(self, tmp_path):
        """XR process-kill evidence -> no skip, evaluator called."""
        from cst_optimization.evaluation.failure_skip_candidates import XR_PROCESS_KILL
        row = {
            "id": 1,
            "schema_version": current_schema_version(),
            "parameter_key": "xr_key",
            "param_names": ["p0"],
            "param_values": [1.0],
            "status": "solver_failed",
            "raw_metrics": {"m1": 1.0},
            "objective_names": ["m1"],
            "error_taxonomy": {"original_error": "tree path not found"},
            "source": None,
            "run_id": "r1",
            "created_at": "2026-06-04 00:00:00",
        }
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=1)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 0.0

        result = run_failure_skip_evaluator(db_path, "xr_key", cfg, fake_ev,
            param_names=["p0"], param_values=[1.0],
        )
        assert not result.enforced_skip
        assert result.evaluator_called
        assert call_count[0] == 1



