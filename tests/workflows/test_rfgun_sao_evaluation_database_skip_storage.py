"""No-CST tests for SE2 synthetic skip row storage.

All tests use temp SQLite DBs.  No subprocess, no taskkill, no OS calls.
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
    EvaluationDatabaseStatus,
    current_schema_version,
)
from workflows.rfgun_sao.evaluation_database_skip_records import (
    SKIPPED_FAILURE_REUSE,
    SKIPPED_PROBABLY_INFEASIBLE,
    EvaluationSkipRecordPayload,
    get_schema_capabilities,
    is_reusable_success_status,
    is_skip_status,
)
from workflows.rfgun_sao.evaluation_database_skip_storage import (
    build_skip_payload_from_enforce_decision,
    write_failure_skip_synthetic_row,
)
from workflows.rfgun_sao.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from workflows.rfgun_sao.failure_skip_candidates import (
    FailureSkipCandidateConfig,
    load_failure_skip_candidates,
)
from workflows.rfgun_sao.failure_skip_enforce import (
    FailureSkipEnforceDecision,
)


# ===================================================================
# Helpers
# ===================================================================


def _create_db(tmp_path: Path) -> str:
    """Create an empty evaluation DB and return its path."""
    db_path = str(tmp_path / "se2_test.db")
    cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
    with SQLiteEvaluationDatabase(cfg):
        pass
    return db_path


def _insert_success_row(db_path: str, param_values: list[float]) -> None:
    """Insert a SUCCESS row for warm-start/reuse tests."""
    from workflows.rfgun_sao.evaluation_database_schema import ParameterIdentity
    pid = ParameterIdentity(param_names=["p0"], values=param_values)
    conn = __import__("sqlite3").connect(db_path)
    try:
        conn.execute(
            "INSERT INTO evaluation_records "
            "(schema_version, parameter_key, param_names, param_values, status, "
            "raw_metrics, objective_values, objective_names) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (current_schema_version(), pid.parameter_key(),
             json.dumps(["p0"]), json.dumps(param_values),
             "success", json.dumps({"m1": 0.5}), json.dumps({"m1": 0.5}),
             json.dumps(["m1"])),
        )
        conn.commit()
    finally:
        conn.close()


# ===================================================================
# Status validation support
# ===================================================================


class TestStatusValidation:
    def test_skip_statuses_now_validate(self):
        """SE2 extends v1 validation to accept skip statuses."""
        assert EvaluationDatabaseStatus.validate(SKIPPED_FAILURE_REUSE) == SKIPPED_FAILURE_REUSE
        assert EvaluationDatabaseStatus.validate(SKIPPED_PROBABLY_INFEASIBLE) == SKIPPED_PROBABLY_INFEASIBLE

    def test_v1_success_still_validates(self):
        EvaluationDatabaseStatus.validate("success")

    def test_invalid_status_still_rejected(self):
        with pytest.raises(ValueError, match="Unknown evaluation status"):
            EvaluationDatabaseStatus.validate("bogus_status")

    def test_schema_capability_updated(self):
        caps = get_schema_capabilities(1)
        assert caps.supports_skip_statuses is True
        assert caps.requires_migration_for_skip_rows is False


# ===================================================================
# Synthetic row write
# ===================================================================


class TestSyntheticRowWrite:
    def test_valid_payload_writes_one_row(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc123",
            source_row_ids=(1, 2),
            evidence_count=2,
            skip_reason="2 solver failures at same key",
        )
        row_id = write_failure_skip_synthetic_row(db_path, payload)
        assert row_id > 0, "should return a valid row id"

    def test_invalid_payload_raises(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(parameter_key="")
        with pytest.raises(ValueError, match="Cannot write skip row"):
            write_failure_skip_synthetic_row(db_path, payload)

    def test_invalid_payload_writes_zero_rows(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(parameter_key="")
        try:
            write_failure_skip_synthetic_row(db_path, payload)
        except ValueError:
            pass
        conn = __import__("sqlite3").connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
        conn.close()
        assert count == 0

    def test_inserted_status_is_skip(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        row_id = write_failure_skip_synthetic_row(db_path, payload)
        conn = __import__("sqlite3").connect(db_path)
        row = conn.execute("SELECT status, source, diagnostics, error_taxonomy FROM evaluation_records WHERE id = ?",
                          (row_id,)).fetchone()
        conn.close()
        assert row[0] == SKIPPED_FAILURE_REUSE
        assert row[1] == "failure_skip_enforce"

    def test_diagnostics_include_audit_fields(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1, 2), evidence_count=2,
            skip_reason="audit test", skip_policy_version=1,
            source_run_ids=("r1", "r2"),
        )
        row_id = write_failure_skip_synthetic_row(db_path, payload)
        conn = __import__("sqlite3").connect(db_path)
        row = conn.execute("SELECT diagnostics, error_taxonomy FROM evaluation_records WHERE id = ?",
                          (row_id,)).fetchone()
        conn.close()
        diag = json.loads(row[0])
        assert diag["record_kind"] == "skip"
        assert diag["skip_reason"] == "audit test"
        assert diag["evidence_count"] == 2
        assert diag["source_row_ids"] == [1, 2]
        assert diag["source_run_ids"] == ["r1", "r2"]
        assert diag["evaluator_called"] is False
        assert diag["retry_called"] is False
        assert diag["budget_consumed"] is False
        et = json.loads(row[1])
        assert et["environment_fault_flag"] is False

    def test_no_fabricated_success_metrics(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        row_id = write_failure_skip_synthetic_row(db_path, payload)
        conn = __import__("sqlite3").connect(db_path)
        row = conn.execute("SELECT raw_metrics, objective_values FROM evaluation_records WHERE id = ?",
                          (row_id,)).fetchone()
        conn.close()
        assert row[0] == "null" or row[0] is None
        assert row[1] == "null" or row[1] is None


# ===================================================================
# Read-back / classification
# ===================================================================


class TestReadBack:
    def test_skip_row_readable(self, tmp_path):
        db_path = _create_db(tmp_path)
        payload = EvaluationSkipRecordPayload(
            parameter_key="readable_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="readable",
        )
        write_failure_skip_synthetic_row(db_path, payload)
        conn = __import__("sqlite3").connect(db_path)
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute("SELECT * FROM evaluation_records").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["status"] == SKIPPED_FAILURE_REUSE

    def test_is_skip_status_recognized(self):
        assert is_skip_status(SKIPPED_FAILURE_REUSE)
        assert is_skip_status(SKIPPED_PROBABLY_INFEASIBLE)
        assert not is_skip_status("success")

    def test_not_reusable_success(self):
        assert not is_reusable_success_status(SKIPPED_FAILURE_REUSE)
        assert not is_reusable_success_status(SKIPPED_PROBABLY_INFEASIBLE)

    def test_not_warm_start_eligible(self):
        assert not is_reusable_success_status(SKIPPED_FAILURE_REUSE)
        assert not is_reusable_success_status(SKIPPED_PROBABLY_INFEASIBLE)

    def test_not_failure_skip_evidence_source(self):
        from workflows.rfgun_sao.evaluation_database_skip_records import (
            is_failure_skip_evidence_source_status,
        )
        assert not is_failure_skip_evidence_source_status(SKIPPED_FAILURE_REUSE)
        assert not is_failure_skip_evidence_source_status(SKIPPED_PROBABLY_INFEASIBLE)


# ===================================================================
# Decision-to-payload bridge
# ===================================================================


class TestDecisionToPayload:
    def test_enforce_decision_builds_payload(self):
        decision = FailureSkipEnforceDecision(
            enabled=True, mode="enforce",
            parameter_key="key123",
            enforce_skip=True,
            candidate_found=True,
            candidate_decision="enforce_eligible",
            evidence_count=2,
            source_row_ids=(1, 2),
            source_run_ids=("r1", "r2"),
            diagnostics={"policy_version": 1},
        )
        payload = build_skip_payload_from_enforce_decision(decision)
        assert payload.parameter_key == "key123"
        assert payload.evidence_count == 2
        assert payload.source_row_ids == (1, 2)
        assert payload.source_run_ids == ("r1", "r2")
        assert payload.evaluator_called is False
        assert payload.retry_called is False
        assert payload.budget_consumed is False

    def test_non_enforce_decision_raises(self):
        decision = FailureSkipEnforceDecision(
            enabled=True, mode="enforce",
            parameter_key="key123",
            enforce_skip=False,
        )
        with pytest.raises(ValueError, match="non-enforce decision"):
            build_skip_payload_from_enforce_decision(decision)

    def test_enforce_without_source_rows_raises(self):
        decision = FailureSkipEnforceDecision(
            enabled=True, mode="enforce",
            parameter_key="key123",
            enforce_skip=True,
            evidence_count=0,
        )
        with pytest.raises(ValueError, match="no source_row_ids"):
            build_skip_payload_from_enforce_decision(decision)


# ===================================================================
# Success reuse / warm-start / candidate loader exclusion
# ===================================================================


class TestExclusion:
    def test_candidate_loader_ignores_skip_row(self, tmp_path):
        """Failure skip candidate loader excludes skip rows as evidence."""
        db_path = _create_db(tmp_path)
        # Insert a skip row
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key="skip_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="test skip",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)
        # Load candidates
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        # Skip row should not create a candidate
        assert result.candidate_rows == 0

    def test_skip_row_not_affected_by_success_reuse(self, tmp_path):
        """Success reuse loader ignores skip row (only accepts 'success')."""
        db_path = _create_db(tmp_path)
        # Insert skip row
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key="skip_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)
        # Check status is not 'success'
        conn = __import__("sqlite3").connect(db_path)
        row = conn.execute("SELECT status FROM evaluation_records").fetchone()
        conn.close()
        assert row[0] != "success"

    def test_skip_row_with_success_row_candidate_loader(self, tmp_path):
        """Candidate loader only considers failure rows, not skip or success."""
        db_path = _create_db(tmp_path)
        # Insert a success row
        _insert_success_row(db_path, [1.0])
        # Insert a skip row
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key="skip_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)
        # Load candidates
        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        # Neither success nor skip rows should be candidates
        assert result.candidate_rows == 0
        assert result.by_classification.get("success", 0) == 1
        assert result.by_classification.get("skipped_failure_reuse", 0) == 1


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_subprocess(self):
        import workflows.rfgun_sao.evaluation_database_skip_storage as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "import subprocess" not in text
        assert "from subprocess" not in text

    def test_no_os_system(self):
        import workflows.rfgun_sao.evaluation_database_skip_storage as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "os.system" not in text

    def test_no_taskkill(self):
        import workflows.rfgun_sao.evaluation_database_skip_storage as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "taskkill" not in text
        assert "Stop-Process" not in text

    def test_no_cst_import(self):
        import workflows.rfgun_sao.evaluation_database_skip_storage as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"


# ===================================================================
# SE2.1: Real success_reuse + warm-start protection
# ===================================================================


class TestRealSuccessReuseProtection:
    """Call real success_reuse helper against synthetic skip rows."""

    def test_skip_row_only_no_reuse(self, tmp_path):
        """Skip row with same parameter_key -> success_reuse returns None."""
        from workflows.rfgun_sao.evaluation_database_schema import ParameterIdentity
        from workflows.rfgun_sao.evaluation_success_reuse import (
            SuccessReuseConfig,
            try_success_reuse,
        )

        db_path = _create_db(tmp_path)
        # Insert skip row with the same key that success_reuse will query
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        skip_key = pid.parameter_key()
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key=skip_key, source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)

        # Query via success_reuse helper with the same key
        cfg = SuccessReuseConfig(enabled=True)
        with SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True, path=db_path)) as db:
            result = try_success_reuse(db, pid, ["m1"], config=cfg)

        assert result is None, "skip row must not be reusable even when key matches"

    def test_success_and_skip_row_only_success_reused(self, tmp_path):
        """Skip and success rows -> only success row is reused (different keys)."""
        from workflows.rfgun_sao.evaluation_database_schema import ParameterIdentity
        from workflows.rfgun_sao.evaluation_success_reuse import (
            SuccessReuseConfig,
            try_success_reuse,
        )

        db_path = _create_db(tmp_path)
        # Insert success row
        pid_success = ParameterIdentity(param_names=["p0"], values=[1.0])
        conn = __import__("sqlite3").connect(db_path)
        conn.execute(
            "INSERT INTO evaluation_records "
            "(schema_version, parameter_key, param_names, param_values, status, "
            "raw_metrics, objective_values, objective_names, diagnostics) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (current_schema_version(), pid_success.parameter_key(),
             json.dumps(["p0"]), json.dumps([1.0]),
             "success", json.dumps({"m1": 0.5}), json.dumps({"m1": 0.5}),
             json.dumps(["m1"]), json.dumps({"__retry_penalty__": {"m1": 0.5}})),
        )
        conn.commit()
        conn.close()

        # Insert skip row with different key
        pid_skip = ParameterIdentity(param_names=["p0"], values=[999.0])
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key=pid_skip.parameter_key(), source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)

        # Query for success key
        cfg = SuccessReuseConfig(enabled=True)
        with SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True, path=db_path)) as db:
            result = try_success_reuse(db, pid_success, ["m1"], config=cfg)
        assert result is not None, "success row must be reusable"
        assert result.status.name == "SUCCESS"

        # Query for skip key (same key as skip row)
        with SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True, path=db_path)) as db:
            result_skip = try_success_reuse(db, pid_skip, ["m1"], config=cfg)
        assert result_skip is None, "skip row must not be reusable even when key matches"

    def test_success_and_skip_same_key_returns_success_only(self, tmp_path):
        """Success and skip row with same parameter_key -> returns SUCCESS only."""
        from workflows.rfgun_sao.evaluation_database_schema import ParameterIdentity
        from workflows.rfgun_sao.evaluation_success_reuse import (
            SuccessReuseConfig,
            try_success_reuse,
        )

        db_path = _create_db(tmp_path)
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        same_key = pid.parameter_key()

        # Insert success row
        conn = __import__("sqlite3").connect(db_path)
        conn.execute(
            "INSERT INTO evaluation_records "
            "(schema_version, parameter_key, param_names, param_values, status, "
            "raw_metrics, objective_values, objective_names, diagnostics) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (current_schema_version(), same_key,
             json.dumps(["p0"]), json.dumps([1.0]),
             "success", json.dumps({"m1": 0.5}), json.dumps({"m1": 0.5}),
             json.dumps(["m1"]), json.dumps({"__retry_penalty__": {"m1": 0.5}})),
        )
        conn.commit()
        conn.close()

        # Insert skip row with the same key
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key=same_key, source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)

        # Query for the shared key
        cfg = SuccessReuseConfig(enabled=True)
        with SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True, path=db_path)) as db:
            result = try_success_reuse(db, pid, ["m1"], config=cfg)

        # Must return the SUCCESS row, not the skip row
        assert result is not None, "must return a result from the success row"
        assert result.status.name == "SUCCESS"


class TestRealWarmStartProtection:
    """Call real warm-start prior loader against synthetic skip rows."""

    def test_skip_row_only_no_priors(self, tmp_path):
        """Only skip row in DB -> warm-start returns zero priors."""
        from workflows.rfgun_sao.evaluation_database_warm_start import (
            DbWarmStartConfig,
            load_warm_start_priors,
        )

        db_path = _create_db(tmp_path)
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key="skip_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)

        with SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True, path=db_path)) as db:
            rows = db.get_all_records()

        ws_cfg = DbWarmStartConfig(enabled=True, max_priors=10)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
        )
        assert report.accepted_priors == 0
        assert report.found_rows == 1

    def test_success_and_skip_row_only_success_prior(self, tmp_path):
        """Both skip and success rows -> warm-start returns only success prior."""
        from workflows.rfgun_sao.evaluation_database_schema import ParameterIdentity
        from workflows.rfgun_sao.evaluation_database_warm_start import (
            DbWarmStartConfig,
            load_warm_start_priors,
        )

        db_path = _create_db(tmp_path)
        # Insert success row
        pid = ParameterIdentity(param_names=["p0"], values=[1.0])
        conn = __import__("sqlite3").connect(db_path)
        conn.execute(
            "INSERT INTO evaluation_records "
            "(schema_version, parameter_key, param_names, param_values, status, "
            "raw_metrics, objective_values, objective_names, diagnostics) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (current_schema_version(), pid.parameter_key(),
             json.dumps(["p0"]), json.dumps([1.0]),
             "success", json.dumps({"m1": 0.5}), json.dumps({"m1": 0.5}),
             json.dumps(["m1"]), json.dumps({"__retry_penalty__": {"m1": 0.5}})),
        )
        conn.commit()
        conn.close()

        # Insert skip row
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key="skip_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)

        # Load warm-start priors
        with SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True, path=db_path)) as db:
            rows = db.get_all_records()

        ws_cfg = DbWarmStartConfig(enabled=True, max_priors=10)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
        )
        # Only the success row should become a prior
        assert report.accepted_priors == 1
        assert report.found_rows == 2
        priors_list = report.diagnostics.get("priors", [])
        assert len(priors_list) == 1


class TestCandidateLoaderExclusionDetail:
    """Additional candidate loader exclusion evidence."""

    def test_skip_row_excluded_with_blocked_reason(self, tmp_path):
        """Skip row is excluded from candidate evidence with blocked reason."""
        db_path = _create_db(tmp_path)
        skip_payload = EvaluationSkipRecordPayload(
            parameter_key="skip_key", source_row_ids=(1,), evidence_count=1,
            skip_reason="test",
        )
        write_failure_skip_synthetic_row(db_path, skip_payload)

        cfg = FailureSkipCandidateConfig(enabled=True, mode="dry_run", min_failures=1)
        result = load_failure_skip_candidates(db_path, cfg)
        assert result.candidate_rows == 0
        assert result.blocked_by_reason.get("skip_status_excluded", 0) >= 1
        assert result.by_classification.get("skipped_failure_reuse", 0) == 1
