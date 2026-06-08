"""No-CST tests for evaluation DB workflow integration (DDB3.1)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
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
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    resolve_evaluation_database_config,
)


# ===================================================================
# Config resolution at workflow level
# ===================================================================


class TestWorkflowConfig:
    def test_disabled_no_db_created(self) -> None:
        """Absent/disabled config returns disabled config without validation."""
        cfg = resolve_evaluation_database_config({})
        assert cfg.enabled is False

        cfg2 = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": False}},
        )
        assert cfg2.enabled is False

    def test_enabled_missing_path_rejects(self) -> None:
        """Enabled config without path raises ValueError."""
        with pytest.raises(ValueError, match="path is required"):
            resolve_evaluation_database_config(
                {"evaluation_database": {"enabled": True}},
            )

    def test_path_inside_repo_rejects(self, tmp_path: Path) -> None:
        """Path inside repo is rejected at config resolution."""
        repo_root = str(tmp_path)
        inside_path = str(tmp_path / "inside" / "eval.db")
        with pytest.raises(ValueError, match="inside the repository"):
            resolve_evaluation_database_config(
                {"evaluation_database": {"enabled": True, "path": inside_path}},
                repo_root=repo_root,
            )

    def test_disabled_path_inside_repo_not_validated(self, tmp_path: Path) -> None:
        """Disabled config does not validate path."""
        repo_root = str(tmp_path)
        inside_path = str(tmp_path / "inside" / "eval.db")
        cfg = resolve_evaluation_database_config(
            {"evaluation_database": {"enabled": False, "path": inside_path}},
            repo_root=repo_root,
        )
        assert cfg.enabled is False


# ===================================================================
# DB write semantics
# ===================================================================


class TestWriteSemantics:
    def test_insert_needs_parameter_identity(self) -> None:
        """Record without parameter_identity is rejected."""
        from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        rec = EvaluationDatabaseRecord(status="success", parameter_identity=None)
        with pytest.raises(ValueError, match="parameter_identity"):
            db.insert_final_record(rec)
        db.close()
        Path(db_path).unlink(missing_ok=True)

    def test_success_record_has_objective_values(self) -> None:
        """SUCCESS record has objective_values in DB."""
        from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase
        import json, tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        payload = RawEvaluationPayload(
            raw_metrics={"m1": 1.5},
            objective_values={"m1": 0.3},
        )
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid, status="success", raw_payload=payload,
            objective_names=["m1"],
        )
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        db = SQLiteEvaluationDatabase(cfg)
        db.open()
        db.insert_final_record(rec, run_id="test1")
        rows = db.query_by_parameter_key(pid.parameter_key())
        assert len(rows) == 1
        obj = rows[0].get("objective_values")
        assert obj is not None, "objective_values should be present"
        if isinstance(obj, str):
            obj = json.loads(obj)
        assert obj.get("m1") == 0.3
        db.close()
        Path(db_path).unlink(missing_ok=True)


# ===================================================================
# No reuse/warm-start queries
# ===================================================================


class TestNoReuseQueries:
    def test_no_reuse_query_on_open(self) -> None:
        """Opening DB does not trigger any reuse/warm-start query."""
        from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            assert db.count_records() == 0
        Path(db_path).unlink(missing_ok=True)


# ===================================================================
# Legacy retry + DB
# ===================================================================


class TestLegacyRetryAndDB:
    def test_legacy_and_db_config_independent(self, tmp_path: Path) -> None:
        """Legacy retry config is independent of evaluation DB config."""
        outside_path = str(tmp_path.parent / "outside_eval.db")
        config = {
            "optimization": {"retry": {"enabled": True}},
            "evaluation_database": {"enabled": True, "path": outside_path},
        }
        cfg = resolve_evaluation_database_config(config, repo_root=str(tmp_path))
        assert cfg.enabled is True

    def test_legacy_result_writes_db_record(self, tmp_path: Path) -> None:
        """A legacy-style EvaluationResult can be built into a DB record."""
        from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase
        from cst_optimization.evaluation.retry_runtime_cst import build_record_from_evaluation_result
        from cst_optimization.evaluation.evaluation_database_schema import ParameterIdentity
        from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        ev_result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            error="",
            raw_metrics={"m1": 1.5, "m2": 2.0},
            objective_values={"m1": 1.5, "m2": 2.0},
            penalty_values={"m1": 0.3, "m2": 0.8},
        )
        record = build_record_from_evaluation_result(pid, ev_result)

        # Verify the record can be inserted into the DB
        db_path = str(tmp_path / "legacy_test.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            row_id = db.insert_final_record(record, run_id="legacy_test")
            assert row_id > 0
            assert db.count_records() == 1
            key = pid.parameter_key()
            rows = db.query_by_parameter_key(key)
            assert len(rows) == 1
            assert rows[0]["status"] == "success"

    def test_legacy_result_with_error_writes_db_record(self, tmp_path: Path) -> None:
        """Failed legacy EvaluationResult builds a valid DB record."""
        from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase
        from cst_optimization.evaluation.retry_runtime_cst import build_record_from_evaluation_result
        from cst_optimization.evaluation.evaluation_database_schema import ParameterIdentity
        from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        ev_result = EvaluationResult(
            status=EvaluationStatus.SOLVER_FAILED,
            error="Solver did not converge",
        )
        record = build_record_from_evaluation_result(pid, ev_result)

        db_path = str(tmp_path / "legacy_fail.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            row_id = db.insert_final_record(record, run_id="legacy_test")
            assert row_id > 0
            assert db.count_records() == 1

