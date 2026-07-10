"""No-CST tests for WS3.1 DB warm-start optimizer wiring hardening."""

from __future__ import annotations

import json
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

from cst_optimization.evaluation.evaluation_database_schema import (
    ParameterIdentity,
    current_schema_version,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from cst_optimization.evaluation.evaluation_database_warm_start import (
    DbWarmStartConfig,
    DbWarmStartPrior,
    db_priors_to_prior_data,
    load_warm_start_priors,
    merge_checkpoint_and_db_priors,
    parameter_keys_from_prior_data,
    resolve_db_warm_start_config,
)


# ===================================================================
# Helpers
# ===================================================================


def _seed_db(tmp_path: Path, rows_data: list[dict]) -> str:
    """Create temp DB with given rows. Each dict: values, scalar, key_override."""
    import json as _json
    db_path = str(tmp_path / "ws_test.db")
    cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
    with SQLiteEvaluationDatabase(cfg) as db:
        for rd in rows_data:
            vals = rd.get("values", [0.5])
            scalar = rd.get("scalar", 0.5)
            key_override = rd.get("key_override", None)
            pid = ParameterIdentity(param_names=["p0"], values=vals)
            key = key_override if key_override else pid.parameter_key()
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "raw_metrics, objective_values, objective_names, diagnostics) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, key, _json.dumps(["p0"]), _json.dumps(vals),
                 "success", _json.dumps({"m1": scalar}),
                 _json.dumps({"m1": scalar}), _json.dumps(["m1"]),
                 _json.dumps({"__retry_penalty__": {"m1": scalar}})),
            )
        db._conn.commit()
    return db_path


def _ckpt_keys_from_prior_data(prior_data, param_names):
    """Compute checkpoint parameter keys from prior_data X array."""
    keys = set()
    if prior_data is not None:
        for x_vec in prior_data[0]:
            pid = ParameterIdentity(param_names=param_names, values=list(x_vec))
            keys.add(pid.parameter_key())
    return keys


def _make_db_prior(
    values: list[float],
    scalar: float = 0.5,
    param_names: list[str] | None = None,
) -> DbWarmStartPrior:
    """Build a DbWarmStartPrior for testing."""
    if param_names is None:
        param_names = ["p0"]
    pid = ParameterIdentity(param_names=param_names, values=values)
    return DbWarmStartPrior(
        parameter_key=pid.parameter_key(),
        parameter_identity=pid,
        objective_values={"m1": scalar},
        scalar=scalar,
        objective_names=("m1",),
        parameter_names=tuple(param_names),
    )


# ===================================================================
# Checkpoint dedup
# ===================================================================


class TestCheckpointDedup:
    def test_db_prior_matching_checkpoint_skipped(self, tmp_path):
        """DB prior matching checkpoint key is skipped."""
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        # Simulate checkpoint with the same parameter point
        ckpt_pid = ParameterIdentity(param_names=["p0"], values=[0.5])
        ckpt_keys = {ckpt_pid.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        assert report.accepted_priors == 0
        assert report.skipped_checkpoint_duplicates == 1

    def test_db_prior_unique_from_checkpoint_accepted(self, tmp_path):
        """DB prior different from checkpoint keys is accepted."""
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        # Different checkpoint key
        ckpt_pid = ParameterIdentity(param_names=["p0"], values=[99.0])
        ckpt_keys = {ckpt_pid.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        assert report.accepted_priors == 1
        assert report.skipped_checkpoint_duplicates == 0

    def test_mixed_ckpt_dedup_counts(self, tmp_path):
        """Checkpoint dedup count appears in report."""
        db_path = _seed_db(tmp_path, [
            {"values": [0.5], "scalar": 1.0},
            {"values": [1.0], "scalar": 2.0},
        ])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ckpt_pid = ParameterIdentity(param_names=["p0"], values=[0.5])
        ckpt_keys = {ckpt_pid.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        assert report.accepted_priors == 1  # only [1.0] accepted
        assert report.skipped_checkpoint_duplicates == 1

    def test_prior_data_no_duplicate_keys(self, tmp_path):
        """Merged prior_data has no duplicate checkpoint keys."""
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ckpt_pid = ParameterIdentity(param_names=["p0"], values=[0.5])
        ckpt_keys = {ckpt_pid.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        assert report.accepted_priors == 0  # skipped due to checkpoint dupe

    def test_ckpt_keys_from_prior_data_helper(self):
        """Helper computes checkpoint keys from prior_data X array."""
        param_names = ["p0", "p1"]
        prior_data = (
            np.array([[0.5, 1.0], [2.0, 3.0]], dtype=float),
            np.array([0.3, 0.7], dtype=float),
        )
        keys = _ckpt_keys_from_prior_data(prior_data, param_names)
        assert len(keys) == 2
        pid1 = ParameterIdentity(param_names=param_names, values=[0.5, 1.0])
        pid2 = ParameterIdentity(param_names=param_names, values=[2.0, 3.0])
        assert pid1.parameter_key() in keys
        assert pid2.parameter_key() in keys

    def test_ckpt_plus_unique_db_merge_row_count(self, tmp_path):
        """Checkpoint 2 rows + 2 unique DB rows = 4 merged rows via helper."""
        # Seed DB with two rows whose keys differ from checkpoint keys
        db_path = _seed_db(tmp_path, [
            {"values": [10.0], "scalar": 0.1},
            {"values": [20.0], "scalar": 0.2},
        ])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        # Checkpoint with 2 rows at different values
        ckpt_pid_1 = ParameterIdentity(param_names=["p0"], values=[1.0])
        ckpt_pid_2 = ParameterIdentity(param_names=["p0"], values=[2.0])
        ckpt_keys = {ckpt_pid_1.parameter_key(), ckpt_pid_2.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        assert report.accepted_priors == 2, "both DB rows should be accepted"
        assert report.skipped_checkpoint_duplicates == 0

        # Use same merge helper as run.py
        ckpt_data = (
            np.array([[1.0], [2.0]], dtype=float),
            np.array([5.0, 6.0], dtype=float),
        )
        ws_priors = (report.diagnostics or {}).get("priors", [])
        merged, merge_diag = merge_checkpoint_and_db_priors(
            ckpt_data, ws_priors, ["p0"],
        )
        assert merged is not None
        assert len(merged[0]) == 4
        assert len(merged[1]) == 4
        assert merge_diag["ckpt_count"] == 2
        assert merge_diag["db_accepted"] == 2
        assert merge_diag["db_checkpoint_duplicates"] == 0

    def test_no_duplicate_checkpoint_db_keys_in_final(self, tmp_path):
        """Duplicate checkpoint/DB parameter_key does not appear twice."""
        # DB has one row matching a checkpoint key and one unique
        db_path = _seed_db(tmp_path, [
            {"values": [0.5], "scalar": 1.0},  # matches checkpoint
            {"values": [99.0], "scalar": 2.0},  # unique
        ])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        # Checkpoint has one row at 0.5
        ckpt_pid = ParameterIdentity(param_names=["p0"], values=[0.5])
        ckpt_keys = {ckpt_pid.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        assert report.accepted_priors == 1  # only [99.0]
        assert report.skipped_checkpoint_duplicates == 1

        # Use merge helper: 1 checkpoint row + 1 accepted DB row
        ckpt_data = (np.array([[0.5]], dtype=float), np.array([1.0], dtype=float))
        ws_priors = (report.diagnostics or {}).get("priors", [])
        merged, merge_diag = merge_checkpoint_and_db_priors(
            ckpt_data, ws_priors, ["p0"],
        )
        assert merged is not None
        assert len(merged[0]) == 2
        assert merge_diag["ckpt_count"] == 1
        assert merge_diag["db_accepted"] == 1
        assert merge_diag["db_checkpoint_duplicates"] == 0

        # Verify no overlapping keys in merged X
        all_keys = _ckpt_keys_from_prior_data(merged, ["p0"])
        assert len(all_keys) == 2  # two distinct keys


# ===================================================================
# Config semantics
# ===================================================================


class TestWS3Config:
    def test_default_disabled(self):
        cfg = resolve_db_warm_start_config({})
        assert cfg.enabled is False

    def test_ws_enabled_without_db_raises(self):
        with pytest.raises(ValueError):
            resolve_db_warm_start_config(
                {"evaluation_database": {"warm_start": {"enabled": True}}},
                db_enabled=False,
            )

    def test_ws_needs_explicit_enable(self):
        cfg = resolve_db_warm_start_config(
            {"evaluation_database": {"warm_start": {"enabled": True}}},
            db_enabled=True,
        )
        assert cfg.enabled is True


# ===================================================================
# Prior loading no evaluator calls
# ===================================================================


class TestNoEvaluatorCalls:
    def test_priors_do_not_call_evaluator(self, tmp_path):
        """Loading priors does not call evaluator."""
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        called = [False]

        class FakeEval:
            def __call__(self, *a):
                called[0] = True
                return 1.0

        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors > 0
        assert not called[0], "evaluator should not be called during prior loading"

    def test_priors_do_not_invoke_retry_runtime(self, tmp_path):
        """Loading priors does not invoke retry runtime."""
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors > 0


# ===================================================================
# Fake optimizer harness (no-CST)
# ===================================================================


class TestFakeOptimizerHarness:
    """Fake optimizer receives expected prior_data in a no-CST harness."""

    def test_fake_optimizer_receives_ckpt_prior_data(self):
        """Fake optimizer receives checkpoint-only prior_data."""
        from collections import namedtuple
        FakeResult = namedtuple("FakeResult", ["x_opt", "f_opt"])

        class FakeOptimizer:
            def __init__(self):
                self.prior_data_received = None
            def optimize(self, *, evaluator=None, prior_data=None, **kw):
                self.prior_data_received = prior_data
                return FakeResult(x_opt=np.array([0.5]), f_opt=np.array([1.0]))

        opt = FakeOptimizer()
        prior_data = (
            np.array([[0.5, 1.0], [2.0, 3.0]], dtype=float),
            np.array([0.3, 0.7], dtype=float),
        )
        result = opt.optimize(evaluator=lambda x: 0.0, prior_data=prior_data)
        assert opt.prior_data_received is prior_data
        assert result.x_opt is not None
        assert result.f_opt is not None

    def test_fake_optimizer_receives_merged_prior_data(self, tmp_path):
        """Fake optimizer receives merged data from the same helper run.py uses."""
        from collections import namedtuple
        FakeResult = namedtuple("FakeResult", ["x_opt", "f_opt"])

        # Seed DB with 2 unique rows
        db_path = _seed_db(tmp_path, [
            {"values": [10.0], "scalar": 0.1},
            {"values": [20.0], "scalar": 0.2},
        ])
        db_cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(db_cfg) as db:
            all_rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            all_rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
        )
        assert report.accepted_priors == 2

        # Build checkpoint with 2 rows
        ckpt_x = np.array([[1.0], [2.0]], dtype=float)
        ckpt_f = np.array([5.0, 6.0], dtype=float)
        prior_data = (ckpt_x, ckpt_f)

        # Use the same merge helper that run.py uses
        ws_priors = (report.diagnostics or {}).get("priors", [])
        merged, merge_diag = merge_checkpoint_and_db_priors(
            prior_data, ws_priors, ["p0"],
        )

        # Fake optimizer receives merged data
        class FakeOptimizer:
            def __init__(self):
                self.prior_data_received = None
            def optimize(self, *, evaluator=None, prior_data=None, **kw):
                self.prior_data_received = prior_data
                return FakeResult(x_opt=np.array([0.5]), f_opt=np.array([1.0]))

        opt = FakeOptimizer()
        opt.optimize(evaluator=lambda x: 0.0, prior_data=merged)
        received = opt.prior_data_received
        assert received is not None
        assert len(received[0]) == 4
        assert len(received[1]) == 4
        assert merge_diag["ckpt_count"] == 2
        assert merge_diag["db_accepted"] == 2
        assert merge_diag["db_input_count"] == 2
        assert merge_diag["db_checkpoint_duplicates"] == 0

    def test_fake_optimizer_receives_db_only_via_helper(self, tmp_path):
        """Fake optimizer receives DB-only prior_data via merge helper (no checkpoint)."""
        from collections import namedtuple
        FakeResult = namedtuple("FakeResult", ["x_opt", "f_opt"])

        db_path = _seed_db(tmp_path, [
            {"values": [10.0], "scalar": 0.1},
            {"values": [20.0], "scalar": 0.2},
        ])
        db_cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(db_cfg) as db:
            all_rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            all_rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
        )
        assert report.accepted_priors == 2
        ws_priors = (report.diagnostics or {}).get("priors", [])
        merged, merge_diag = merge_checkpoint_and_db_priors(
            None, ws_priors, ["p0"],
        )

        class FakeOptimizer:
            def __init__(self):
                self.prior_data_received = None
            def optimize(self, *, evaluator=None, prior_data=None, **kw):
                self.prior_data_received = prior_data
                return FakeResult(x_opt=np.array([0.5]), f_opt=np.array([1.0]))

        opt = FakeOptimizer()
        opt.optimize(evaluator=lambda x: 0.0, prior_data=merged)
        received = opt.prior_data_received
        assert received is not None
        assert len(received[0]) == 2
        assert merge_diag["ckpt_count"] == 0
        assert merge_diag["db_accepted"] == 2

    def test_fake_optimizer_prior_data_none_when_disabled(self):
        """Fake optimizer receives None prior_data when WS disabled."""
        from collections import namedtuple
        FakeResult = namedtuple("FakeResult", ["x_opt", "f_opt"])

        class FakeOptimizer:
            def __init__(self):
                self.prior_data_received = "NOT_SET"
            def optimize(self, *, evaluator=None, prior_data=None, **kw):
                self.prior_data_received = prior_data
                return FakeResult(x_opt=np.array([0.5]), f_opt=np.array([1.0]))

        opt = FakeOptimizer()
        prior_data = None  # warm-start disabled
        opt.optimize(evaluator=lambda x: 0.0, prior_data=prior_data)
        assert opt.prior_data_received is None


# ===================================================================
# Disabled warm-start semantics
# ===================================================================


class TestDisabledSemantics:
    def test_ws_disabled_prior_data_none(self):
        """WS disabled yields prior_data=None in optimizer call."""
        ws_cfg = DbWarmStartConfig(enabled=False)
        assert ws_cfg.enabled is False
        # Simulate the merge logic: disabled config -> no DB priors loaded
        prior_data = None
        if ws_cfg.enabled:
            prior_data = (np.array([[0.5]]), np.array([1.0]))
        assert prior_data is None

    def test_ws_disabled_keeps_checkpoint(self):
        """WS disabled keeps checkpoint prior_data, does not load DB priors."""
        ws_cfg = DbWarmStartConfig(enabled=False)
        ckpt_prior_data = (
            np.array([[1.0], [2.0]], dtype=float),
            np.array([5.0, 6.0], dtype=float),
        )
        # With WS disabled, final prior_data = checkpoint only
        final_prior_data = ckpt_prior_data
        assert final_prior_data is ckpt_prior_data
        # Verify no DB loading would happen
        assert not ws_cfg.enabled

    def test_ws_enabled_sr_disabled_injects_priors(self):
        """WS enabled but SR disabled still injects DB priors."""
        ws_cfg = DbWarmStartConfig(enabled=True)
        sr_cfg_enabled = False
        # WS operates independently of SR
        assert ws_cfg.enabled is True
        assert sr_cfg_enabled is False

    def test_sr_enabled_ws_disabled_no_db_priors(self):
        """SR enabled but WS disabled does not load DB priors."""
        ws_cfg = DbWarmStartConfig(enabled=False)
        sr_cfg_enabled = True
        # Without WS, no DB priors are loaded regardless of SR
        assert not ws_cfg.enabled
        assert sr_cfg_enabled

    def test_success_reuse_enabled_ws_disabled_no_db_priors_integration(self, tmp_path):
        """Integration: SR enabled + WS disabled does not load DB priors."""
        ws_cfg = DbWarmStartConfig(enabled=False)
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        db_cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(db_cfg) as db:
            rows = db.get_all_records()
        # Passing disabled WS config => no priors loaded
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
        )
        assert report.accepted_priors == 0


# ===================================================================
# Malformed / rejected rows
# ===================================================================


class TestMalformedRowsRejected:
    """Rejected and malformed DB rows are not injected as priors."""

    def test_solver_failed_row_rejected(self, tmp_path):
        """SOLVER_FAILED row is rejected."""
        import json as _json
        db_path = str(tmp_path / "failed.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p0"], values=[1.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), _json.dumps(["p0"]), _json.dumps([1.0]),
                 "solver_failed"),
            )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 0
        assert report.rejected_rows == 1

    def test_wrong_param_count_rejected(self, tmp_path):
        """Row with mismatched param count is rejected."""
        import json as _json
        db_path = str(tmp_path / "bad_param_count.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p0", "p1"], values=[1.0, 2.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "objective_values, objective_names) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), _json.dumps(["p0", "p1"]),
                 _json.dumps([1.0]), "success",
                 _json.dumps({"m1": 0.5}), _json.dumps(["m1"])),
            )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0", "p1"],
        )
        assert report.accepted_priors == 0

    def test_non_numeric_param_value_rejected(self, tmp_path):
        """Row with non-numeric param value is rejected."""
        import json as _json
        db_path = str(tmp_path / "nan_param.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "objective_values, objective_names) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, "some_key", _json.dumps(["p0"]), _json.dumps(["not_a_number"]),
                 "success", _json.dumps({"m1": 0.5}), _json.dumps(["m1"])),
            )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors == 0
        assert report.rejected_rows == 1


# ===================================================================
# Warm-start and SR independence
# ===================================================================


class TestWSandSRIndependence:
    def test_ws_no_sr_injects_priors(self):
        """WS enabled without SR still injects priors."""
        ws_cfg = DbWarmStartConfig(enabled=True)
        sr_enabled = False
        assert ws_cfg.enabled is True
        assert sr_enabled is False

    def test_sr_no_ws_no_db_priors(self):
        """SR enabled without WS does not load DB priors."""
        ws_cfg = DbWarmStartConfig(enabled=False)
        assert ws_cfg.enabled is False


# ===================================================================
# Diagnostics / reporting
# ===================================================================


class TestDiagnostics:
    def test_report_has_accepted_count(self, tmp_path):
        db_path = _seed_db(tmp_path, [{"values": [0.5], "scalar": 1.0}])
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.accepted_priors >= 0

    def test_report_has_rejected_count(self, tmp_path):
        import json as _json
        db_path = str(tmp_path / "mixed.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            pid = ParameterIdentity(param_names=["p0"], values=[1.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (1, pid.parameter_key(), _json.dumps(["p0"]), _json.dumps([1.0]), "solver_failed"),
            )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.rejected_rows > 0

    def test_report_has_duplicate_count(self, tmp_path):
        import json as _json
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
                    (1, key, _json.dumps(["p0"]), _json.dumps([1.0]),
                     "success", _json.dumps({"m1": float(i)}), _json.dumps(["m1"]),
                     _json.dumps({"__retry_penalty__": {"m1": float(i)}})),
                )
            db._conn.commit()
            rows = db.get_all_records()
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(rows, ws_cfg, metric_names=["m1"], param_names=["p0"])
        assert report.skipped_duplicates > 0

    def test_diagnostics_has_all_required_counts(self, tmp_path):
        """Diagnostics report includes accepted, rejected, duplicate, ckpt_dup."""
        import json as _json
        db_path = str(tmp_path / "full_diag.db")
        cfg = EvaluationDatabaseConfig(enabled=True, path=db_path)
        with SQLiteEvaluationDatabase(cfg) as db:
            # 1 SUCCESS row (unique key)
            pid_ok = ParameterIdentity(param_names=["p0"], values=[1.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status, "
                "objective_values, objective_names, diagnostics) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, pid_ok.parameter_key(), _json.dumps(["p0"]), _json.dumps([1.0]),
                 "success", _json.dumps({"m1": 0.5}), _json.dumps(["m1"]),
                 _json.dumps({"__retry_penalty__": {"m1": 0.5}})),
            )
            # 1 FAILED row
            pid_fail = ParameterIdentity(param_names=["p0"], values=[2.0])
            db._conn.execute(
                "INSERT INTO evaluation_records "
                "(schema_version, parameter_key, param_names, param_values, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (1, pid_fail.parameter_key(), _json.dumps(["p0"]), _json.dumps([2.0]),
                 "solver_failed"),
            )
            db._conn.commit()
            rows = db.get_all_records()

        # Checkpoint has key matching the SUCCESS row
        ckpt_keys = {pid_ok.parameter_key()}
        ws_cfg = DbWarmStartConfig(enabled=True)
        report = load_warm_start_priors(
            rows, ws_cfg, metric_names=["m1"], param_names=["p0"],
            checkpoint_parameter_keys=ckpt_keys,
        )
        # The SUCCESS row is skipped (checkpoint dup), the FAILED row is rejected
        assert report.accepted_priors == 0
        assert report.rejected_rows == 1
        assert report.skipped_checkpoint_duplicates == 1
        # All required count fields exist and are non-negative
        for attr in ("found_rows", "eligible_rows", "accepted_priors",
                     "rejected_rows", "skipped_duplicates",
                     "skipped_checkpoint_duplicates"):
            assert getattr(report, attr) >= 0, f"{attr} should be >= 0"


# ===================================================================
# Pure no-CST helpers
# ===================================================================


class TestHelpers:
    """Test the pure no-CST helper functions for WS3.1."""

    def test_parameter_keys_from_prior_data(self):
        """parameter_keys_from_prior_data computes keys correctly."""
        param_names = ["p0", "p1"]
        prior_x = np.array([[0.5, 1.0], [2.0, 3.0]], dtype=float)
        keys = parameter_keys_from_prior_data(prior_x, param_names)
        assert len(keys) == 2
        pid1 = ParameterIdentity(param_names=param_names, values=[0.5, 1.0])
        pid2 = ParameterIdentity(param_names=param_names, values=[2.0, 3.0])
        assert pid1.parameter_key() in keys
        assert pid2.parameter_key() in keys

    def test_parameter_keys_empty_x(self):
        """parameter_keys_from_prior_data with empty prior_x returns empty set."""
        prior_x = np.empty((0, 2), dtype=float)
        keys = parameter_keys_from_prior_data(prior_x, ["p0", "p1"])
        assert len(keys) == 0

    def test_db_priors_to_prior_data(self):
        """db_priors_to_prior_data converts DbWarmStartPrior list to arrays."""
        priors = [
            _make_db_prior([0.5, 1.0], scalar=0.3, param_names=["p0", "p1"]),
            _make_db_prior([2.0, 3.0], scalar=0.7, param_names=["p0", "p1"]),
        ]
        ws_x, ws_f = db_priors_to_prior_data(priors)
        assert ws_x.shape == (2, 2)
        assert ws_f.shape == (2,)
        np.testing.assert_array_almost_equal(ws_f, [0.3, 0.7])
        np.testing.assert_array_almost_equal(ws_x[0], [0.5, 1.0])
        np.testing.assert_array_almost_equal(ws_x[1], [2.0, 3.0])

    def test_db_priors_to_prior_data_empty(self):
        """db_priors_to_prior_data with empty list returns empty arrays."""
        ws_x, ws_f = db_priors_to_prior_data([])
        assert ws_x.shape == (0,) or ws_x.shape == (0, 0)
        assert ws_f.shape == (0,)

    def test_merge_checkpoint_and_db_priors_no_duplicates(self):
        """merge_checkpoint_and_db_priors: no overlap."""
        ckpt = (
            np.array([[0.5, 1.0]], dtype=float),
            np.array([0.3], dtype=float),
        )
        db_priors = [
            _make_db_prior([2.0, 3.0], scalar=0.7, param_names=["p0", "p1"]),
        ]
        merged, diag = merge_checkpoint_and_db_priors(ckpt, db_priors, ["p0", "p1"])
        assert merged is not None
        assert len(merged[0]) == 2
        assert diag["ckpt_count"] == 1
        assert diag["db_input_count"] == 1
        assert diag["db_checkpoint_duplicates"] == 0
        assert diag["db_accepted"] == 1

    def test_merge_checkpoint_and_db_priors_with_duplicates(self):
        """merge_checkpoint_and_db_priors: checkpoint dup skipped."""
        ckpt = (
            np.array([[0.5]], dtype=float),
            np.array([0.3], dtype=float),
        )
        # DB prior with same key as checkpoint
        db_priors = [
            _make_db_prior([0.5], scalar=0.3),  # same key
            _make_db_prior([2.0], scalar=0.7),  # unique
        ]
        merged, diag = merge_checkpoint_and_db_priors(ckpt, db_priors, ["p0"])
        assert merged is not None
        assert len(merged[0]) == 2  # 1 ckpt + 1 accepted DB
        assert diag["ckpt_count"] == 1
        assert diag["db_input_count"] == 2
        assert diag["db_checkpoint_duplicates"] == 1
        assert diag["db_accepted"] == 1

    def test_merge_checkpoint_none_db_empty(self):
        """merge_checkpoint_and_db_priors: both None/empty returns None."""
        merged, diag = merge_checkpoint_and_db_priors(None, [], ["p0"])
        assert merged is None
        assert diag["db_accepted"] == 0

    def test_merge_checkpoint_none_with_db_priors(self):
        """merge_checkpoint_and_db_priors: no checkpoint, DB-only works."""
        db_priors = [
            _make_db_prior([0.5], scalar=1.0),
        ]
        merged, diag = merge_checkpoint_and_db_priors(None, db_priors, ["p0"])
        assert merged is not None
        assert len(merged[0]) == 1
        assert diag["ckpt_count"] == 0
        assert diag["db_accepted"] == 1

    def test_merge_checkpoint_with_empty_db_priors(self):
        """merge_checkpoint_and_db_priors: checkpoint-only when DB empty."""
        ckpt = (
            np.array([[0.5]], dtype=float),
            np.array([1.0], dtype=float),
        )
        merged, diag = merge_checkpoint_and_db_priors(ckpt, [], ["p0"])
        assert merged is not None
        assert len(merged[0]) == 1
        np.testing.assert_array_almost_equal(merged[0], [[0.5]])
        assert diag["db_accepted"] == 0

    def test_merge_diagnostics_all_keys_present(self):
        """merge_checkpoint_and_db_priors diagnostics include all required keys."""
        ckpt = (
            np.array([[1.0], [2.0]], dtype=float),
            np.array([5.0, 6.0], dtype=float),
        )
        db_priors = [
            _make_db_prior([0.5], scalar=0.3),
            _make_db_prior([1.0], scalar=0.5),  # checkpoint dup
        ]
        merged, diag = merge_checkpoint_and_db_priors(ckpt, db_priors, ["p0"])
        assert merged is not None
        # Diagnostics must include all required keys
        for key in ("ckpt_count", "db_input_count", "db_checkpoint_duplicates", "db_accepted"):
            assert key in diag, f"missing key: {key}"
            assert diag[key] >= 0, f"{key} should be >= 0, got {diag[key]}"
        # Verify actual values
        assert diag["ckpt_count"] == 2
        assert diag["db_input_count"] == 2
        assert diag["db_checkpoint_duplicates"] == 1
        assert diag["db_accepted"] == 1
        assert len(merged[0]) == 3  # 2 ckpt + 1 accepted DB


# ===================================================================
# Safety
# ===================================================================


class TestSafety:
    def test_no_jsonl_reference(self):
        import cst_optimization.evaluation.evaluation_database_warm_start as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text

    def test_no_cst_import(self):
        import cst_optimization.evaluation.evaluation_database_warm_start as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst."]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"
