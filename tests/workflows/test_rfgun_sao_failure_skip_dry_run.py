"""No-CST tests for FS3 failure skip dry-run diagnostics.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
Dry-run never skips evaluator or retry.
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
    resolve_failure_skip_config,
)
from cst_optimization.evaluation.failure_skip_dry_run import (
    FailureSkipDryRunDecision,
    evaluate_failure_skip_dry_run_for_key,
    evaluate_failure_skip_dry_run_for_keys,
    FakeEvaluationResult,
    run_failure_skip_dry_run_fake_evaluation,
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
        "objective_values": None,
        "objective_names": ["m1"],
        "error_taxonomy": dict(taxonomy) if taxonomy else None,
        "source": None,
        "run_id": "r1",
        "created_at": "2026-06-04 00:00:00",
    }


# ===================================================================
# Dry-run config / mode
# ===================================================================


class TestDryRunConfig:
    def test_disabled_config_produces_disabled_decision(self, tmp_path):
        cfg = FailureSkipCandidateConfig(enabled=False)
        decision = evaluate_failure_skip_dry_run_for_key(
            str(tmp_path / "nonexistent.db"), "some_key", cfg,
        )
        assert not decision.enabled
        assert decision.mode == "disabled"
        assert not decision.would_skip

    def test_mode_disabled_does_not_read_db(self, tmp_path):
        cfg = FailureSkipCandidateConfig(enabled=True, mode="disabled")
        decision = evaluate_failure_skip_dry_run_for_key(
            str(tmp_path / "nonexistent.db"), "some_key", cfg,
        )
        assert not decision.enabled
        assert decision.mode == "disabled"

    def test_mode_dry_run_checks_db(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        decision = evaluate_failure_skip_dry_run_for_key(db_path, pk, cfg)
        assert decision.enabled
        assert decision.mode == "dry_run"
        assert decision.candidate_found
        assert decision.would_skip

    def test_mode_enforce_downgraded_not_skip(self, tmp_path):
        """Enforce mode is downgraded to dry-run in FS3; no actual skip."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=1)
        decision = evaluate_failure_skip_dry_run_for_key(db_path, pk, cfg)
        assert decision.enabled
        # Enforce is downgraded 鈥?would_skip should be false
        assert not decision.would_skip
        assert "enforce mode not implemented" in str(decision.diagnostics.get("reason", ""))


# ===================================================================
# Dry-run decision semantics
# ===================================================================


class TestDryRunDecision:
    def test_candidate_hit_does_not_skip_evaluator(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        decision = evaluate_failure_skip_dry_run_for_key(db_path, pk, cfg)
        assert decision.would_skip
        # But evaluator/retry must still run
        assert decision.evaluator_must_run
        assert decision.retry_must_run
        assert decision.budget_consumed_normally

    def test_candidate_miss_does_not_skip_evaluator(self, tmp_path):
        """No candidate found; evaluator still runs."""
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        decision = evaluate_failure_skip_dry_run_for_key(
            db_path, "nonexistent_key", cfg,
        )
        assert not decision.would_skip
        assert not decision.candidate_found
        assert decision.evaluator_must_run
        assert decision.retry_must_run

    def test_blocked_environment_evidence_not_skip(self, tmp_path):
        """XR process-kill blocked -> would_skip false; evaluator runs."""
        row = {
            "id": 1,
            "schema_version": current_schema_version(),
            "parameter_key": "some_key",
            "param_names": ["p0"],
            "param_values": json.dumps([1.0]),
            "status": "solver_failed",
            "raw_metrics": {"m1": 1.0},
            "objective_names": ["m1"],
            "error_taxonomy": {"original_error": "tree path not found"},
            "source": None,
            "run_id": "r1",
            "created_at": "2026-06-04 00:00:00",
        }
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        decision = evaluate_failure_skip_dry_run_for_key(db_path, "some_key", cfg)
        assert not decision.would_skip
        assert not decision.candidate_found
        assert decision.evaluator_must_run

    def test_insufficient_evidence_no_skip(self, tmp_path):
        """Below min_failures -> would_skip false."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=2)
        decision = evaluate_failure_skip_dry_run_for_key(db_path, pk, cfg)
        assert not decision.would_skip
        assert decision.candidate_found  # candidate exists but blocked
        assert decision.evaluator_must_run

    def test_exact_key_filter(self, tmp_path):
        """Only exact keys are considered."""
        pid_target = ParameterIdentity(param_names=["p0"], values=[1.0])
        pid_other = ParameterIdentity(param_names=["p0"], values=[2.0])
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([2.0], 2),
        ]
        rows[0]["parameter_key"] = pid_target.parameter_key()
        rows[1]["parameter_key"] = pid_other.parameter_key()
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        # Check other key 鈥?should find candidate
        decision_other = evaluate_failure_skip_dry_run_for_key(
            db_path, pid_other.parameter_key(), cfg,
        )
        assert decision_other.would_skip

        # Check unknown key 鈥?no candidate
        decision_unknown = evaluate_failure_skip_dry_run_for_key(
            db_path, "unknown_key", cfg,
        )
        assert not decision_unknown.would_skip


# ===================================================================
# Multi-key evaluation
# ===================================================================


class TestMultiKey:
    def test_empty_keys(self, tmp_path):
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run")
        summary = evaluate_failure_skip_dry_run_for_keys(
            str(tmp_path / "test.db"), [], cfg,
        )
        assert summary.checked_points == 0

    def test_multiple_keys_summary(self, tmp_path):
        pid1 = ParameterIdentity(param_names=["p0"], values=[1.0])
        pid2 = ParameterIdentity(param_names=["p0"], values=[2.0])
        pk1, pk2 = pid1.parameter_key(), pid2.parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([2.0], 2),
        ]
        rows[0]["parameter_key"] = pk1
        rows[1]["parameter_key"] = pk2
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        summary = evaluate_failure_skip_dry_run_for_keys(
            db_path, [pk1, pk2], cfg,
        )
        assert summary.checked_points == 2
        assert summary.would_skip_count == 2

    def test_mixed_keys_summary(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        summary = evaluate_failure_skip_dry_run_for_keys(
            db_path, [pk, "unknown_key"], cfg,
        )
        assert summary.checked_points == 2
        assert summary.would_skip_count == 1
        assert summary.no_candidate_count == 1


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_subprocess(self):
        import cst_optimization.evaluation.failure_skip_dry_run as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "import subprocess" not in text
        assert "from subprocess" not in text

    def test_no_os_system(self):
        import cst_optimization.evaluation.failure_skip_dry_run as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "os.system" not in text

    def test_no_taskkill(self):
        import cst_optimization.evaluation.failure_skip_dry_run as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "taskkill" not in text
        assert "Stop-Process" not in text

    def test_no_cst_import(self):
        import cst_optimization.evaluation.failure_skip_dry_run as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst."]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"


# ===================================================================
# Fake-runtime harness call-count tests (FS3.1)
# ===================================================================


class TestFakeRuntimeHarness:
    """Fake evaluator is always called exactly once, regardless of would_skip."""

    def test_candidate_hit_calls_evaluator_once(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_dry_run_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert result.would_skip
        assert result.evaluator_called
        assert call_count[0] == 1, "evaluator must be called exactly once"
        assert result.objective_value == 42.0

    def test_candidate_hit_with_retry_wrapper(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        eval_count = [0]
        retry_count = [0]

        def fake_ev(pk):
            eval_count[0] += 1
            return 42.0

        def fake_retry(ev_func, **kw):
            retry_count[0] += 1
            return ev_func(kw.get("parameter_key", ""))

        result = run_failure_skip_dry_run_fake_evaluation(
            db_path, pk, cfg, fake_ev, retry_wrapper=fake_retry,
        )
        assert result.would_skip
        assert result.evaluator_called
        assert result.retry_called
        assert eval_count[0] == 1, "evaluator must be called exactly once"
        assert retry_count[0] == 1, "retry wrapper must be called exactly once"
        assert result.objective_value == 42.0

    def test_candidate_miss_calls_evaluator_once(self, tmp_path):
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 0.0

        result = run_failure_skip_dry_run_fake_evaluation(
            db_path, "nonexistent_key", cfg, fake_ev,
        )
        assert not result.would_skip
        assert not result.candidate_found
        assert result.evaluator_called
        assert call_count[0] == 1

    def test_xr_blocked_calls_evaluator_once(self, tmp_path):
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
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 0.0

        result = run_failure_skip_dry_run_fake_evaluation(
            db_path, "some_key", cfg, fake_ev,
        )
        assert not result.would_skip
        assert result.evaluator_called
        assert call_count[0] == 1

    def test_enforce_mode_calls_evaluator_once(self, tmp_path):
        """Enforce mode in FS3.1 still calls evaluator; no skip."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="enforce", min_failures=1)

        call_count = [0]
        def fake_ev(pk):
            call_count[0] += 1
            return 42.0

        result = run_failure_skip_dry_run_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert result.evaluator_called
        assert call_count[0] == 1, "enforce mode must not skip evaluator in FS3.1"

    def test_no_db_write_by_harness(self, tmp_path):
        """Harness does not write any DB rows."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        def fake_ev(pk):
            return 42.0

        # Count rows before
        import sqlite3
        conn = sqlite3.connect(db_path)
        before = conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn.close()

        result = run_failure_skip_dry_run_fake_evaluation(db_path, pk, cfg, fake_ev)

        # Count rows after
        conn2 = sqlite3.connect(db_path)
        after = conn2.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn2.close()

        assert before == after, "harness must not write DB rows"
        assert result.evaluator_called

    def test_harness_includes_dry_run_diagnostics(self, tmp_path):
        """Harness result includes would_skip and diagnostics."""
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)

        def fake_ev(pk):
            return 42.0

        result = run_failure_skip_dry_run_fake_evaluation(db_path, pk, cfg, fake_ev)
        assert result.parameter_key == pk
        assert result.would_skip
        assert result.candidate_found
        assert result.candidate_decision is not None
        assert result.evidence_count >= 1



