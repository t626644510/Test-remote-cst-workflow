"""No-CST tests for FS2 failure skip candidate loader.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
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

from workflows.rfgun_sao.evaluation_database_schema import (
    ParameterIdentity,
    current_schema_version,
)
from workflows.rfgun_sao.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from workflows.rfgun_sao.failure_skip_candidates import (
    CALIBRATION_FAILED,
    GATE_REJECTED,
    SCHEMA_INCOMPATIBLE,
    SOLVER_FAILED,
    SOLVER_FAILED_WITHOUT_TAXONOMY,
    SUCCESS,
    SUCCESS_REUSE,
    TRANSIENT_ENVIRONMENT_FAULT,
    UNKNOWN_EXCEPTION,
    WARM_START_PRIOR,
    XR_PROCESS_KILL,
    FailureSkipCandidateConfig,
    classify_failure_skip_evidence,
    find_failure_skip_candidate_for_key,
    is_candidate_evidence_classification,
    is_environment_fault_classification,
    load_failure_skip_candidates,
    resolve_failure_skip_config,
)


# ===================================================================
# Helpers
# ===================================================================


def _make_row(
    status: str = "success",
    schema_version: int | None = None,
    param_names: list[str] | None = None,
    param_values: list[float] | None = None,
    objective_names: list[str] | None = None,
    row_id: int = 1,
    run_id: str = "r1",
    created_at: str = "2026-06-04 00:00:00",
    source: str | None = None,
    diagnostics: dict | None = None,
    error_taxonomy: dict | None = None,
    objective_values: dict | None = None,
    raw_metrics: dict | None = None,
) -> dict:
    """Build a fake DB row dict with JSON fields already decoded."""
    if schema_version is None:
        schema_version = current_schema_version()
    if param_names is None:
        param_names = ["p0"]
    if param_values is None:
        param_values = [1.0]
    pid = ParameterIdentity(param_names=param_names, values=param_values)
    row: dict = {
        "id": row_id,
        "schema_version": schema_version,
        "parameter_key": pid.parameter_key(),
        "param_names": list(param_names),
        "param_values": list(param_values),
        "status": status,
        "raw_metrics": {"m1": 1.0} if raw_metrics is None and objective_values is None else (dict(raw_metrics) if raw_metrics else None),
        "objective_values": dict(objective_values) if objective_values else None,
        "objective_names": list(objective_names) if objective_names else ["m1"],
        "diagnostics": dict(diagnostics) if diagnostics else None,
        "error_taxonomy": dict(error_taxonomy) if error_taxonomy else None,
        "source": source,
        "run_id": run_id,
        "created_at": created_at,
    }
    return row


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
    return _make_row(
        status="solver_failed", param_values=param_values,
        row_id=row_id, error_taxonomy=taxonomy,
    )


# ===================================================================
# Config
# ===================================================================


class TestConfig:
    def test_default_disabled(self):
        cfg = resolve_failure_skip_config({})
        assert cfg.enabled is False
        assert cfg.mode == "disabled"

    def test_disabled_returns_no_candidates(self):
        cfg = FailureSkipCandidateConfig(enabled=False)
        assert cfg.enabled is False

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError, match="Invalid failure_skip.mode"):
            resolve_failure_skip_config(
                {"evaluation_database": {"failure_skip": {"enabled": True, "mode": "invalid"}}},
            )

    def test_dry_run_mode_accepted(self):
        cfg = resolve_failure_skip_config(
            {"evaluation_database": {"failure_skip": {"enabled": True, "mode": "dry_run"}}},
        )
        assert cfg.enabled
        assert cfg.mode == "dry_run"

    def test_enforce_mode_accepted(self):
        cfg = resolve_failure_skip_config(
            {"evaluation_database": {"failure_skip": {"enabled": True, "mode": "enforce"}}},
        )
        assert cfg.enabled
        assert cfg.mode == "enforce"


# ===================================================================
# Evidence classification
# ===================================================================


class TestEvidenceClassification:
    def test_success_excluded(self):
        row = _make_row(status="success")
        assert classify_failure_skip_evidence(row) == SUCCESS

    def test_success_reuse_excluded(self):
        row = _make_row(status="success", source="db_success_reuse")
        assert classify_failure_skip_evidence(row) == SUCCESS_REUSE

    def test_warm_start_prior_excluded(self):
        row = _make_row(status="success", diagnostics={"is_warm_start_prior": True})
        assert classify_failure_skip_evidence(row) == WARM_START_PRIOR

    def test_gate_rejected_classified(self):
        row = _make_row(status="gate_rejected")
        assert classify_failure_skip_evidence(row) == GATE_REJECTED
        assert is_candidate_evidence_classification(GATE_REJECTED, FailureSkipCandidateConfig())

    def test_calibration_failed_classified(self):
        row = _make_row(status="calibration_failed")
        cl = classify_failure_skip_evidence(row)
        assert cl == CALIBRATION_FAILED
        assert is_candidate_evidence_classification(cl, FailureSkipCandidateConfig())

    def test_solver_failed_with_known_taxonomy(self):
        """solver_failed with recognized error -> SOLVER_FAILED."""
        row = _make_row(
            status="solver_failed",
            error_taxonomy={"original_error": "mesh error", "original_status": "solver_failed"},
        )
        assert classify_failure_skip_evidence(row) == SOLVER_FAILED

    def test_solver_failed_process_kill_environment(self):
        """solver_failed with process-kill markers -> XR_PROCESS_KILL."""
        row = _make_row(
            status="solver_failed",
            error_taxonomy={"original_error": "tree path not found: 'Tables\\0D Results\\MaxE_Z0'"},
        )
        assert classify_failure_skip_evidence(row) == XR_PROCESS_KILL
        assert is_environment_fault_classification(XR_PROCESS_KILL)

    def test_solver_failed_connection_lost_environment(self):
        """solver_failed with connection-lost -> XR_PROCESS_KILL."""
        row = _make_row(
            status="solver_failed",
            error_taxonomy={"original_error": "The connection was lost to the Design Environment."},
        )
        assert classify_failure_skip_evidence(row) == XR_PROCESS_KILL

    def test_solver_failed_without_taxonomy_ambiguous(self):
        """solver_failed with no taxonomy -> SOLVER_FAILED_WITHOUT_TAXONOMY."""
        row = _make_row(status="solver_failed")
        assert classify_failure_skip_evidence(row) == SOLVER_FAILED_WITHOUT_TAXONOMY

    def test_transient_failed_environment_fault(self):
        row = _make_row(status="transient_failed")
        assert classify_failure_skip_evidence(row) == TRANSIENT_ENVIRONMENT_FAULT
        assert is_environment_fault_classification(TRANSIENT_ENVIRONMENT_FAULT)

    def test_schema_incompatible_blocked(self):
        row = _make_row(status="solver_failed", schema_version=99)
        assert classify_failure_skip_evidence(row) == SCHEMA_INCOMPATIBLE

    def test_unknown_status_unknown_exception(self):
        row = _make_row(status="some_unknown_status")
        assert classify_failure_skip_evidence(row) == UNKNOWN_EXCEPTION


# ===================================================================
# DB loader
# ===================================================================


class TestDBLoader:
    def test_missing_db_path_returns_empty(self, tmp_path):
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run")
        result = load_failure_skip_candidates(
            str(tmp_path / "nonexistent.db"), cfg,
        )
        assert result.found_rows == 0
        assert len(result.candidates) == 0

    def test_disabled_config_returns_empty(self, tmp_path):
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=False)
        result = load_failure_skip_candidates(db_path, cfg)
        assert not result.enabled
        assert len(result.candidates) == 0

    def test_success_rows_excluded(self, tmp_path):
        rows = [_make_row(status="success", row_id=1)]
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run")
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.found_rows == 1
        assert len(result.candidates) == 0

    def test_solver_failed_becomes_candidate(self, tmp_path):
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.found_rows == 1
        assert result.candidate_rows >= 1
        assert result.candidates[0].recommended_skip

    def test_min_failures_below_threshold_blocks(self, tmp_path):
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=2)
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.candidate_rows >= 1
        assert not result.candidates[0].recommended_skip
        assert any("insufficient_evidence" in r for r in result.candidates[0].blocked_reasons)

    def test_two_failures_same_key_recommends(self, tmp_path):
        pk = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([1.0], 2),
        ]
        rows[0]["parameter_key"] = pk
        rows[1]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=2)
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.candidate_rows >= 1
        assert result.candidates[0].evidence_count == 2
        assert result.candidates[0].recommended_skip

    def test_different_keys_do_not_combine(self, tmp_path):
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([2.0], 2),
        ]
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=2)
        result = load_failure_skip_candidates(db_path, cfg)
        for c in result.candidates:
            assert not c.recommended_skip

    def test_same_param_values_not_deduped_by_db_id(self, tmp_path):
        """Two identical rows get unique DB IDs; both counted."""
        pk = ParameterIdentity(param_names=["p0"], values=[1.0]).parameter_key()
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([1.0], 1),
        ]
        rows[0]["parameter_key"] = pk
        rows[1]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.candidates[0].evidence_count == 2

    def test_parameter_keys_filter(self, tmp_path):
        rows = [
            _solver_failed_row([1.0], 1),
            _solver_failed_row([2.0], 2),
        ]
        pid1 = ParameterIdentity(param_names=["p0"], values=[1.0])
        rows[0]["parameter_key"] = pid1.parameter_key()
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(
            db_path, cfg, parameter_keys=[pid1.parameter_key()],
        )
        assert result.candidate_rows == 1
        assert result.candidates[0].parameter_key == pid1.parameter_key()

    def test_max_candidates_cap(self, tmp_path):
        rows = [_solver_failed_row([float(i)], i) for i in range(1, 11)]
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(
            enabled=True, mode="dry_run", min_failures=1, max_candidates=3,
        )
        result = load_failure_skip_candidates(db_path, cfg)
        assert len(result.candidates) == 3
        assert result.max_candidates_applied

    def test_environment_fault_blocked_by_default(self, tmp_path):
        row = _make_row(
            status="solver_failed",
            error_taxonomy={"original_error": "tree path not found"},
        )
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.candidate_rows == 0
        assert result.blocked_by_reason.get("environment_fault", 0) >= 1

    def test_environment_fault_allowed_when_configured(self, tmp_path):
        row = _make_row(
            status="solver_failed",
            error_taxonomy={"original_error": "tree path not found"},
        )
        db_path = _seed_db(tmp_path, [row])
        cfg = FailureSkipCandidateConfig(
            enabled=True, mode="dry_run", min_failures=1,
            allow_environment_faults=True,
        )
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.candidate_rows >= 1

    def test_classification_counts_reported(self, tmp_path):
        rows = [
            _solver_failed_row([1.0], 1),
            _make_row(status="gate_rejected", row_id=2),
        ]
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        assert SOLVER_FAILED in result.by_classification
        assert GATE_REJECTED in result.by_classification


# ===================================================================
# Single-key lookup
# ===================================================================


class TestSingleKeyLookup:
    def test_single_key_found(self, tmp_path):
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        pk = pid.parameter_key()
        rows = [_solver_failed_row([1.0], 1)]
        rows[0]["parameter_key"] = pk
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        candidate = find_failure_skip_candidate_for_key(db_path, pk, cfg)
        assert candidate is not None
        assert candidate.parameter_key == pk

    def test_single_key_not_found(self, tmp_path):
        rows = [_solver_failed_row([1.0], 1)]
        db_path = _seed_db(tmp_path, rows)
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        candidate = find_failure_skip_candidate_for_key(db_path, "nonexistent_key", cfg)
        assert candidate is None

    def test_disabled_returns_none(self, tmp_path):
        db_path = _seed_db(tmp_path, [_solver_failed_row([1.0], 1)])
        cfg = FailureSkipCandidateConfig(enabled=False)
        candidate = find_failure_skip_candidate_for_key(db_path, "some_key", cfg)
        assert candidate is None


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_subprocess(self):
        import workflows.rfgun_sao.failure_skip_candidates as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "import subprocess" not in text
        assert "from subprocess" not in text

    def test_no_os_system(self):
        import workflows.rfgun_sao.failure_skip_candidates as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "os.system" not in text

    def test_no_taskkill(self):
        import workflows.rfgun_sao.failure_skip_candidates as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "taskkill" not in text
        assert "Stop-Process" not in text

    def test_no_cst_import(self):
        import workflows.rfgun_sao.failure_skip_candidates as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"
