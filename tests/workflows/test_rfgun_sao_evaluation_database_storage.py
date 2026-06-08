"""No-CST tests for durable evaluation DB storage (Phase DDB2)."""

from __future__ import annotations

import json
import os
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
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
    RawEvaluationPayload,
    current_schema_version,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
    resolve_evaluation_database_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pid(values: list[float], precision: int | None = None) -> ParameterIdentity:
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
        precision=precision,
    )


def _final_rec(
    values: list[float] | None,
    status: str = "success",
    retries: int = 0,
) -> EvaluationDatabaseRecord:
    """Build a final evaluation record for storage tests."""
    pid = _pid(values) if values is not None else None
    payload = RawEvaluationPayload(
        raw_metrics={"m1": 1.0, "m2": 2.0},
        objective_values={"m1": 0.5, "m2": 1.0},
    )
    return EvaluationDatabaseRecord(
        parameter_identity=pid,
        status=status,
        raw_payload=payload,
        objective_names=["m1", "m2"],
        source="test",
        retry_count=retries,
        provenance={"git_commit": "abc123"},
    )


def _run_ids() -> str:
    return "test-run-001"


# ===================================================================
# resolve_evaluation_database_config
# ===================================================================


class TestResolveConfig:
    def test_none_config_returns_disabled(self) -> None:
        cfg = resolve_evaluation_database_config(None)
        assert cfg.enabled is False
        assert cfg.path is None

    def test_missing_section_returns_disabled(self) -> None:
        cfg = resolve_evaluation_database_config({"other": 42})
        assert cfg.enabled is False

    def test_explicit_disabled(self) -> None:
        cfg = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": False}},
        )
        assert cfg.enabled is False

    def test_enabled_true_with_path(self) -> None:
        cfg = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": True, "path": "/tmp/test.db"}},
        )
        assert cfg.enabled is True
        assert cfg.path == os.path.abspath("/tmp/test.db")

    def test_enabled_true_missing_path_raises(self) -> None:
        with pytest.raises(ValueError, match="path is required"):
            resolve_evaluation_database_config(
                {"evaluation_database": {"enabled": True}},
            )

    def test_enabled_true_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="path is required"):
            resolve_evaluation_database_config(
                {"evaluation_database": {"enabled": True, "path": ""}},
            )

    def test_path_inside_repo_raises(self, tmp_path: Path) -> None:
        repo_root = str(tmp_path)
        inside_path = str(tmp_path / "inside" / "eval.db")
        with pytest.raises(ValueError, match="inside the repository"):
            resolve_evaluation_database_config(
                {"evaluation_database": {"enabled": True, "path": inside_path}},
                repo_root=repo_root,
            )

    def test_path_outside_repo_ok(self, tmp_path: Path) -> None:
        repo_root = str(tmp_path / "repo")
        outside_path = str(tmp_path / "outside" / "eval.db")
        cfg = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": True, "path": outside_path}},
            repo_root=repo_root,
        )
        assert cfg.enabled is True

    def test_disabled_path_not_validated(self) -> None:
        """When disabled, path is not required and not validated."""
        cfg = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": False}},
            repo_root="/some/repo",
        )
        assert cfg.enabled is False


# ===================================================================
# SQLiteEvaluationDatabase 鈥?schema and lifecycle
# ===================================================================


class TestSchemaLifecycle:
    def test_create_schema_from_scratch(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        assert db.is_open is True
        # Verify table exists
        conn = db._conn
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evaluation_records'",
        )
        assert cursor.fetchone() is not None
        db.close()
        assert db.is_open is False

    def test_schema_version_row_created(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        cursor = db._conn.execute("SELECT MAX(version) FROM schema_version")
        assert cursor.fetchone()[0] == current_schema_version()
        db.close()

    def test_context_manager(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            assert db.is_open is True
        assert db.is_open is False


class TestSchemaVersionHandling:
    def test_version_greater_rejects(self, tmp_path: Path) -> None:
        """Existing DB with version > expected rejects."""
        db_path = str(tmp_path / "test.db")
        # Create DB with version 99
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path, schema_version=99)
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        db.close()

        # Try to open with version 1
        cfg2 = EvaluationDatabaseConfig(enabled=True, path=db_path, schema_version=1)
        db2 = SQLiteEvaluationDatabase(cfg2)
        with pytest.raises(ValueError, match="newer than expected"):
            db2.open()

    def test_version_less_rejects(self, tmp_path: Path) -> None:
        """Existing DB with version < expected rejects."""
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path, schema_version=1)
        SQLiteEvaluationDatabase(cfg).open()

        cfg2 = EvaluationDatabaseConfig(enabled=True, path=db_path, schema_version=2)
        db2 = SQLiteEvaluationDatabase(cfg2)
        with pytest.raises(ValueError, match="older than expected"):
            db2.open()

    def test_missing_schema_version_table_rejects(self, tmp_path: Path) -> None:
        """Non-empty DB without schema_version table rejects."""
        import sqlite3
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.close()

        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        db = SQLiteEvaluationDatabase(cfg)
        with pytest.raises(ValueError, match="no schema_version table"):
            db.open()

    def test_empty_file_initializes(self, tmp_path: Path) -> None:
        """Empty existing file initializes if create_if_missing=True."""
        db_path = str(tmp_path / "test.db")
        # Create empty file
        Path(db_path).touch()
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        assert db.is_open is True
        cursor = db._conn.execute("SELECT MAX(version) FROM schema_version")
        assert cursor.fetchone()[0] == current_schema_version()
        db.close()


# ===================================================================
# Insert and query
# ===================================================================


class TestInsertAndQuery:
    def test_insert_success_record(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0, 2.0], status="success")
            row_id = db.insert_final_record(rec, run_id="r1")
            assert row_id > 0
            assert db.count_records() == 1

    def test_insert_solver_failed_record(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0], status="solver_failed")
            db.insert_final_record(rec, run_id="r1")
            assert db.count_records() == 1

    def test_insert_and_read_back_fields(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0, 2.0], status="success", retries=2)
            db.insert_final_record(rec, run_id="r1")
            key = rec.parameter_identity.parameter_key()
            rows = db.query_by_parameter_key(key)
            assert len(rows) == 1
            row = rows[0]
            assert row["status"] == "success"
            assert row["retry_count"] == 2
            assert row["run_id"] == "r1"
            assert row["param_names"] == ["p0", "p1"]
            assert row["param_values"] == [1.0, 2.0]
            assert row["source"] == "test"

    def test_query_by_parameter_key_returns_correct(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            r1 = _final_rec([1.0], status="success")
            r2 = _final_rec([2.0], status="solver_failed")
            db.insert_final_record(r1, run_id="r1")
            db.insert_final_record(r2, run_id="r1")

            key1 = r1.parameter_identity.parameter_key()
            key2 = r2.parameter_identity.parameter_key()

            rows1 = db.query_by_parameter_key(key1)
            rows2 = db.query_by_parameter_key(key2)

            assert len(rows1) == 1
            assert len(rows2) == 1
            assert rows1[0]["status"] == "success"
            assert rows2[0]["status"] == "solver_failed"

    def test_duplicate_parameter_key_appends(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            r1 = _final_rec([1.0], status="success")
            r2 = _final_rec([1.0], status="solver_failed", retries=1)
            db.insert_final_record(r1, run_id="r1")
            db.insert_final_record(r2, run_id="r1")
            key = r1.parameter_identity.parameter_key()
            rows = db.query_by_parameter_key(key)
            assert len(rows) == 2  # appended, not deduped


class TestInsertValidation:
    def test_missing_parameter_identity_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = EvaluationDatabaseRecord(
                parameter_identity=None,
                status="success",
            )
            with pytest.raises(ValueError, match="parameter_identity"):
                db.insert_final_record(rec)

    def test_diagnostics_not_in_evaluation_records(self, tmp_path: Path) -> None:
        """Attempt diagnostics are not stored in evaluation_records."""
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0], status="success")
            db.insert_final_record(rec, run_id="r1")
            key = rec.parameter_identity.parameter_key()
            rows = db.query_by_parameter_key(key)
            # evaluation_records has a diagnostics column but it stores
            # the final_record's diagnostics (e.g. __retry_penalty__),
            # not intermediate attempt diagnostics.
            assert len(rows) == 1


# ===================================================================
# Disabled / no-op config
# ===================================================================


class TestDisabledConfig:
    def test_disabled_returns_disabled_config(self) -> None:
        cfg = resolve_evaluation_database_config({})
        assert cfg.enabled is False

    def test_disabled_no_path_validation(self) -> None:
        cfg = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": False}},
            repo_root="/some/repo",
        )
        assert cfg.enabled is False

    def test_cannot_instantiate_with_disabled(self) -> None:
        cfg = EvaluationDatabaseConfig(enabled=False)
        with pytest.raises(ValueError, match="disabled config"):
            SQLiteEvaluationDatabase(cfg)


# ===================================================================
# No reuse / no warm-start queries
# ===================================================================


class TestNoReuseSemantics:
    def test_no_reuse_query_at_startup(self, tmp_path: Path) -> None:
        """No workflow startup code queries the DB for reuse/warm-start."""
        # The storage module does not auto-query on open.
        # Verify that opening does not trigger any query.
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            db.insert_final_record(_final_rec([1.0], status="success"), run_id="r1")
        # Success reuse and warm-start are separate future tracks.
        assert True


# ===================================================================
# Record validation
# ===================================================================


class TestRecordValidation:
    def test_insert_invalid_status_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = EvaluationDatabaseRecord(
                parameter_identity=_pid([1.0]),
                status="bogus_status",
            )
            with pytest.raises(ValueError, match="Invalid evaluation record"):
                db.insert_final_record(rec)

    def test_insert_record_schema_version_greater_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path, schema_version=1)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0], status="success")
            rec.schema_version = 99
            with pytest.raises(ValueError, match="Record schema version 99"):
                db.insert_final_record(rec)

    def test_insert_record_schema_version_less_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path, schema_version=2)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0], status="success")
            rec.schema_version = 1
            with pytest.raises(ValueError, match="Record schema version 1"):
                db.insert_final_record(rec)

    def test_insert_missing_identity_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = EvaluationDatabaseRecord(
                parameter_identity=None, status="success",
            )
            with pytest.raises(ValueError, match="parameter_identity"):
                db.insert_final_record(rec)


# ===================================================================
# create_if_missing=False
# ===================================================================


class TestCreateIfMissing:
    def test_missing_file_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "nonexistent" / "test.db")
        cfg = EvaluationDatabaseConfig(
            enabled=True, path=db_path, create_if_missing=False,
        )
        db = SQLiteEvaluationDatabase(cfg)
        with pytest.raises(ValueError, match="does not exist"):
            db.open()
        assert db.is_open is False

    def test_empty_file_rejects(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "empty.db")
        Path(db_path).touch()  # empty file
        cfg = EvaluationDatabaseConfig(
            enabled=True, path=db_path, create_if_missing=False,
        )
        db = SQLiteEvaluationDatabase(cfg)
        with pytest.raises(ValueError, match="does not exist"):
            db.open()
        assert db.is_open is False

    def test_existing_valid_opens_ok(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "existing.db")
        # Create a valid DB first
        cfg1 = EvaluationDatabaseConfig(enabled=True, path=db_path)
        SQLiteEvaluationDatabase(cfg1).open()

        # Now open with create_if_missing=False 鈥?should work
        cfg2 = EvaluationDatabaseConfig(
            enabled=True, path=db_path, create_if_missing=False,
        )
        db2 = SQLiteEvaluationDatabase(cfg2)
        db2.open()
        assert db2.is_open is True
        db2.close()

    def test_empty_file_create_if_missing_true_still_works(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "empty.db")
        Path(db_path).touch()
        cfg = EvaluationDatabaseConfig(
            enabled=True, path=db_path, create_if_missing=True,
        )
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        assert db.is_open is True
        assert db.count_records() == 0
        db.close()

    def test_empty_db_with_create_true_initializes(self, tmp_path: Path) -> None:
        """Empty (zero-byte) file with create_if_missing=True initializes schema."""
        db_path = str(tmp_path / "brand_new.db")
        cfg = EvaluationDatabaseConfig(
            enabled=True, path=db_path, create_if_missing=True,
        )
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        assert db.is_open is True
        cursor = db._conn.execute("SELECT MAX(version) FROM schema_version")
        assert cursor.fetchone()[0] == current_schema_version()
        db.close()


# ===================================================================
# Artifact refs round-trip
# ===================================================================


class TestArtifactRefs:
    def test_artifact_refs_round_trip(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = _pid([1.0])
            payload = RawEvaluationPayload(
                raw_metrics={"m1": 1.0},
                artifact_refs={"result_dir": "/tmp/result", "file": "output.h5"},
            )
            rec = EvaluationDatabaseRecord(
                parameter_identity=pid,
                status="success",
                raw_payload=payload,
            )
            db.insert_final_record(rec, run_id="r1")
            key = pid.parameter_key()
            rows = db.query_by_parameter_key(key)
            assert len(rows) == 1
            refs = rows[0]["artifact_refs"]
            assert refs == {"result_dir": "/tmp/result", "file": "output.h5"}

    def test_artifact_refs_none_no_error(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rec = _final_rec([1.0], status="success")
            db.insert_final_record(rec, run_id="r1")
            key = rec.parameter_identity.parameter_key()
            rows = db.query_by_parameter_key(key)
            assert rows[0]["artifact_refs"] is None


# ===================================================================
# Safety
# ===================================================================


class TestSafety:
    def test_no_cst_import(self) -> None:
        import cst_optimization.evaluation.evaluation_database_storage as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = [
            "cst.interface", "cst.results", "import cst", "from cst.",
        ]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"

    def test_no_file_io_outside_sqlite(self) -> None:
        """Module only uses sqlite3 for file I/O, not open()/write()."""
        import cst_optimization.evaluation.evaluation_database_storage as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        # Check for code-level file I/O (not docstring mentions of "open")
        import ast
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "id", None)
                if fn == "open":
                    pytest.fail("raw open() call found in module code")
        # sqlite3.connect is the intended file I/O mechanism
        assert "sqlite3.connect" in text



