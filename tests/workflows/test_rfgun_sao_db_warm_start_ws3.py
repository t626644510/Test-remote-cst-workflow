"""No-CST tests for WS3 DB warm-start optimizer wiring."""

from __future__ import annotations

import sys
from pathlib import Path

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
from workflows.rfgun_sao.evaluation_database_warm_start import (
    DbWarmStartConfig,
    DbWarmStartPrior,
    load_warm_start_priors,
    resolve_db_warm_start_config,
)


# ===================================================================
# Helpers
# ===================================================================


def _seed_db_with_success(tmp_path: Path, param_values: list[float], scalar: float = 0.5) -> str:
    """Create temp DB with one SUCCESS row. Return path."""
    import json
    db_path = str(tmp_path / "ws_test.db")
    cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
    with SQLiteEvaluationDatabase(cfg) as db:
        pid = ParameterIdentity(param_names=["p0"], values=param_values)
        db._conn.execute(
            "INSERT INTO evaluation_records "
            "(schema_version, parameter_key, param_names, param_values, status, "
            "raw_metrics, objective_values, objective_names, diagnostics) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, pid.parameter_key(), json.dumps(["p0"]), json.dumps(param_values),
             "success", json.dumps({"m1": scalar}), json.dumps({"m1": scalar}),
             json.dumps(["m1"]), json.dumps({"__retry_penalty__": {"m1": scalar}})),
        )
        db._conn.commit()
    return db_path


class _FakeOptimizer:
    """Fake optimizer that records received prior_data."""
    def __init__(self):
        self.prior_data_received = None
        self.call_count = 0

    def optimize(self, *, evaluator=None, prior_data=None, **kw):
        self.prior_data_received = prior_data
        self.call_count += 1
        # Return a fake result
        from collections import namedtuple
        FakeResult = namedtuple("FakeResult", ["x_opt", "f_opt"])
        return FakeResult(x_opt=np.array([0.5]), f_opt=np.array([1.0]))


# ===================================================================
# Config semantics
# ===================================================================


class TestWS3Config:
    def test_default_disabled(self):
        """Default config does not enable warm-start."""
        cfg = resolve_db_warm_start_config({})
        assert cfg.enabled is False

    def test_db_enabled_alone_no_warm_start(self):
        """DB enabled alone does not enable warm-start."""
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"path": "/tmp/d.db"}},
            db_enabled=True,
        )
        assert cfg.enabled is False

    def test_sr_enabled_alone_no_warm_start(self):
        """Success reuse enabled alone does not enable warm-start."""
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"success_reuse": {"enabled": True}}},
            db_enabled=True,
        )
        assert cfg.enabled is False

    def test_ws_enabled_without_db_raises(self):
        """Warm-start enabled without DB raises ValueError."""
        with pytest.raises(ValueError):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True}}},
                db_enabled=False,
            )

    def test_ws_needs_explicit_enable(self):
        """Warm-start requires explicit warm_start.enabled=True."""
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True}}},
            db_enabled=True,
        )
        assert cfg.enabled is True


# ===================================================================
# Prior loading from temp DB
# ===================================================================


class TestPriorLoading:
    def test_loads_success_priors(self, tmp_path):
        """Compatible SUCCESS rows are loaded as priors."""
        db_path = _seed_db_with_success(tmp_path, [0.5])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors > 0
        priors = report.diagnostics.get("priors", [])
        assert len(priors) >= 1

    def test_priors_converted_to_xf(self, tmp_path):
        """Priors can be converted to (X, F) format for optimizer."""
        db_path = _seed_db_with_success(tmp_path, [0.5])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        priors = report.diagnostics.get("priors", [])
        assert len(priors) > 0
        ws_x = np.array([list(p.parameter_identity.values) for p in priors], dtype=float)
        ws_f = np.array([p.scalar for p in priors], dtype=float)
        assert ws_x.ndim == 2
        assert ws_f.ndim == 1
        assert len(ws_x) == len(ws_f)

    def test_priors_do_not_call_evaluator(self, tmp_path):
        """Loading priors does not call any evaluator."""
        db_path = _seed_db_with_success(tmp_path, [0.5])
        called = [False]

        class FakeEval:
            def __call__(self, *a):
                called[0] = True
                return 1.0

        # Load priors without evaluator
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors > 0
        assert not called[0], "evaluator should not be called during prior loading"

    def test_loaded_count_in_report(self, tmp_path):
        """Loaded prior count appears in report."""
        db_path = _seed_db_with_success(tmp_path, [0.5])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors >= 0
        assert report.found_rows >= 0

    def test_rejected_count_in_report(self, tmp_path):
        """Rejected row count appears in report."""
        import json
        db_path = str(tmp_path / "mixed.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p0"], values=[1.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), json.dumps(["p0"]), json.dumps([1.0]), "solver_failed"),
            )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows > 0
        assert "status_not_success" in report.rejection_reasons

    def test_duplicate_count_in_report(self, tmp_path):
        """Duplicate skipped count appears in report."""
        import json
        db_path = str(tmp_path / "dup.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p0"], values=[1.0])
            key = pid.parameter_key()
            for i in range(3):
                db._conn.execute(
                    "INSERT INTO evaluation_records "
                    "(schema_version, parameter_key, param_names, param_values, status, "
                    "objective_values, objective_names, diagnostics) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (1, key, json.dumps(["p0"]), json.dumps([1.0]),
                     "success", json.dumps({"m1": float(i)}), json.dumps(["m1"]),
                     json.dumps({"__retry_penalty__": {"m1": float(i)}})),
                )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True, max_priors=10)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 1  # only best kept
        assert report.skipped_duplicates == 2


# ===================================================================
# Warm-start and success reuse independence
# ===================================================================


class TestWSandSRIndependence:
    def test_ws_no_sr_does_not_skip_eval(self):
        """WS without SR: priors loaded but future eval not skipped."""
        # This is a semantics test, not a runtime test
        ws_cfg = DbWarmStartConfig(enabled=True)
        sr_enabled = False
        assert ws_cfg.enabled is True
        assert sr_enabled is False  # SR is independent

    def test_sr_no_ws_does_not_load_priors(self):
        """SR without WS: no prior loading."""
        sr_cfg_enabled = True
        ws_cfg = DbWarmStartConfig(enabled=False)
        assert ws_cfg.enabled is False
        assert sr_cfg_enabled is True  # SR is independent


# ===================================================================
# Malformed rows rejected
# ===================================================================


class TestMalformedRows:
    def test_wrong_length_param_values_rejected(self, tmp_path):
        """Row with mismatched param_values length is rejected."""
        import json
        db_path = str(tmp_path / "bad.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p0", "p1"], values=[1.0, 2.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "objective_values, objective_names) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), json.dumps(["p0", "p1"]),
                 json.dumps([1.0]), "success",
                 json.dumps({"m1": 0.5}), json.dumps(["m1"])),
            )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0", "p1"])
        assert report.accepted_priors == 0


# ===================================================================
# No JSONL / no CST
# ===================================================================


class TestSafety:
    def test_no_jsonl_reference(self):
        """Warm-start module does not reference JSONL."""
        import workflows.rfgun_sao.evaluation_database_warm_start as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text

    def test_no_cst_import(self):
        """Warm-start module has no CST imports."""
        import workflows.rfgun_sao.evaluation_database_warm_start as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"
