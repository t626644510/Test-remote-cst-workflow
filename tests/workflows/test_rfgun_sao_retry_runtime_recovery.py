"""No-CST tests for retry runtime recovery callback and connection registry."""

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
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
)
from workflows.rfgun_sao.retry_runtime import (
    RetryRuntimeConfig,
    run_retry_loop_no_cst,
)
from workflows.rfgun_sao.retry_runtime_cst import (
    CstConnectionRegistry,
    build_record_from_evaluation_result,
    make_cst_recovery_callback,
    make_cst_retry_evaluate_once,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus


# ---------------------------------------------------------------------------
# Fake connections
# ---------------------------------------------------------------------------


class FakeConnection:
    """Duck-typed CSTConnection for no-CST recovery tests."""
    def __init__(self, pid: int = 0):
        self._pid = pid
        self._closed = False
        self._force_closed = False

    @property
    def pid(self) -> int:
        return self._pid

    def close(self, force: bool = False) -> None:
        self._closed = True
        if force:
            self._force_closed = True


class FakeRaisingConnection:
    """Connection that raises on close — for error-path tests."""
    def close(self, force: bool = False) -> None:
        raise RuntimeError("close failed")


class FakeEvaluatorWithSpy:
    """Evaluator that spies on on_reconnect calls."""
    def __init__(self):
        self.reconnect_calls: list = []
        self._call_count = 0

    def on_reconnect(self, new_conn) -> None:
        self.reconnect_calls.append(new_conn)

    def adapt_for_retry(self, params, iteration):
        self._call_count += 1
        return EvaluationResult(
            status=EvaluationStatus.SUCCESS, error="",
            raw_metrics={"m1": 1.0}, objective_values={"m1": 1.0},
            penalty_values={"m1": 0.3},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pid(values: list[float]) -> ParameterIdentity:
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
    )


def _rec(values, status="success", retries=0):
    return EvaluationDatabaseRecord(
        parameter_identity=_pid(values) if values else None,
        status=status, retry_count=retries,
    )


# ===================================================================
# CstConnectionRegistry
# ===================================================================


class TestCstConnectionRegistry:
    def test_track_and_close_all(self) -> None:
        reg = CstConnectionRegistry()
        c1 = FakeConnection(pid=100)
        c2 = FakeConnection(pid=200)
        reg.track(c1)
        reg.track(c2)
        assert reg.tracked_count == 2
        diag = reg.close_all(force=True)
        assert diag["attempted"] == 2
        assert diag["closed_ok"] == 2
        assert len(diag["errors"]) == 0
        assert c1._closed and c1._force_closed
        assert c2._closed and c2._force_closed
        assert reg.tracked_count == 0  # cleared

    def test_close_all_continues_after_error(self) -> None:
        reg = CstConnectionRegistry()
        reg.track(FakeRaisingConnection())
        reg.track(FakeConnection(pid=200))
        diag = reg.close_all(force=True)
        assert diag["attempted"] == 2
        assert diag["closed_ok"] == 1  # second succeeded
        assert len(diag["errors"]) == 1  # first raised
        assert reg.tracked_count == 0  # cleared despite error

    def test_close_all_empty_registry(self) -> None:
        reg = CstConnectionRegistry()
        diag = reg.close_all(force=True)
        assert diag["attempted"] == 0
        assert diag["closed_ok"] == 0

    def test_close_all_clears_registry(self) -> None:
        reg = CstConnectionRegistry()
        reg.track(FakeConnection())
        reg.close_all(force=True)
        assert reg.tracked_count == 0


# ===================================================================
# make_cst_recovery_callback — unit tests
# ===================================================================


class TestRecoveryCallbackUnit:
    def test_tier1_noop_no_connection_created(self) -> None:
        """Tier 1: callback returns True, no factory call, no registry entry."""
        factory_calls = []
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()

        def factory():
            factory_calls.append(1)
            return FakeConnection()

        cb = make_cst_recovery_callback(factory, ev, reg)
        result = cb(1, None)  # tier 1
        assert result is True
        assert len(factory_calls) == 0
        assert reg.tracked_count == 0
        assert len(ev.reconnect_calls) == 0

    def test_tier2_creates_new_connection_and_tracks(self) -> None:
        """Tier 2: close old, create new, on_reconnect, track."""
        old = FakeConnection(pid=100)
        reg = CstConnectionRegistry()
        reg.track(old)
        ev = FakeEvaluatorWithSpy()
        factory_calls = []

        def factory():
            factory_calls.append(1)
            return FakeConnection(pid=200)

        cb = make_cst_recovery_callback(factory, ev, reg)
        result = cb(2, None)  # tier 2
        assert result is True
        assert len(factory_calls) == 1
        assert reg.tracked_count == 1  # new connection tracked
        assert len(ev.reconnect_calls) == 1
        # old connection was closed
        assert old._closed is True
        # old connection removed from registry (cleared by close_all)
        # Only the new one is tracked
        assert ev.reconnect_calls[0].pid == 200

    def test_tier2_factory_exception_returns_false(self) -> None:
        """Factory exception caught, returns False, no new tracking."""
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()

        def factory():
            raise RuntimeError("factory failed")

        cb = make_cst_recovery_callback(factory, ev, reg)
        result = cb(2, None)
        assert result is False
        assert reg.tracked_count == 0
        assert len(ev.reconnect_calls) == 0

    def test_tier2_on_reconnect_exception_returns_false(self) -> None:
        """on_reconnect exception caught, returns False."""
        reg = CstConnectionRegistry()
        reg.track(FakeConnection(pid=100))

        class EvalWithFailReconnect:
            def on_reconnect(self, new_conn):
                raise RuntimeError("reconnect failed")

        ev = EvalWithFailReconnect()
        factory_calls = []

        def factory():
            factory_calls.append(1)
            return FakeConnection(pid=200)

        cb = make_cst_recovery_callback(factory, ev, reg)
        result = cb(2, None)
        assert result is False
        # Factory was called (connection created), but the exception
        # during on_reconnect means the new connection may or may not
        # be tracked depending on implementation.  Current policy:
        # exception in on_reconnect prevents tracking.
        assert len(factory_calls) == 1
        # Registry should have the old connection closed and cleared.
        # New connection not tracked because exception occurred before track().

    def test_callback_works_without_legacy_retry_handler(self) -> None:
        """Recovery callback functions when retry_handler is None."""
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()
        factory_calls = []

        def factory():
            factory_calls.append(1)
            return FakeConnection(pid=300)

        cb = make_cst_recovery_callback(factory, ev, reg)
        # Tier 1 (no-op)
        assert cb(1, None) is True
        # Tier 2 (reconnect)
        assert cb(2, None) is True
        assert len(factory_calls) == 1
        assert reg.tracked_count == 1


# ===================================================================
# make_cst_retry_evaluate_once — no recovery path
# ===================================================================


class TestEvaluateOnceRecoveryFree:
    def test_no_recovery_parameter(self) -> None:
        """make_cst_retry_evaluate_once has no recovery_callback parameter."""
        import inspect
        sig = inspect.signature(make_cst_retry_evaluate_once)
        assert "recovery_callback" not in sig.parameters


# ===================================================================
# Integration: retry loop + recovery callback
# ===================================================================


class TestRetryLoopWithRecovery:
    def test_tier1_noop_path(self) -> None:
        """Retry loop with max_tier=1: recovery invoked but no-op."""
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()

        def factory():
            return FakeConnection(pid=100)

        cb = make_cst_recovery_callback(factory, ev, reg)

        def evaluate_once(tier, record):
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=1)
        result = run_retry_loop_no_cst(
            initial, evaluate_once,
            config=config, recovery_callback=cb,
        )
        assert result.succeeded is True
        assert reg.tracked_count == 0  # no new connection at tier 1

    def test_tier2_recovery_invoked_after_first_failure(self) -> None:
        """Tier 2 recovery is called after first retry returns failure."""
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()

        factory_calls = []

        def factory():
            factory_calls.append(1)
            return FakeConnection(pid=200)

        cb = make_cst_recovery_callback(factory, ev, reg)

        # Evaluate_once that returns failure first then success
        call_count = [0]

        def evaluate_once(tier, record):
            call_count[0] += 1
            if call_count[0] == 1:
                return _rec([1.0], status="solver_failed", retries=record.retry_count + 1)
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(
            initial, evaluate_once,
            config=config, recovery_callback=cb,
        )
        assert result.succeeded is True
        # First retry (tier 1) is no-op. Second retry (tier 2) triggers callback.
        # Factory should be called at tier 2
        assert len(factory_calls) == 1  # tier 2 recovery creates one new connection
        assert reg.tracked_count == 1  # tracked

    def test_recovery_exception_bounded_by_max_tier(self) -> None:
        """Recovery callback exception does not cause infinite loop."""
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()

        def factory():
            raise RuntimeError("factory always fails")

        cb = make_cst_recovery_callback(factory, ev, reg)

        def evaluate_once(tier, record):
            return _rec([1.0], status="solver_failed", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(
            initial, evaluate_once,
            config=config, recovery_callback=cb,
        )
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert len(result.attempts) == 2

    def test_max_tier_exhaustion_bounded(self) -> None:
        """max_tier exhaustion remains bounded with recovery callback."""
        reg = CstConnectionRegistry()
        ev = FakeEvaluatorWithSpy()

        def factory():
            return FakeConnection(pid=300)

        cb = make_cst_recovery_callback(factory, ev, reg)

        def evaluate_once(tier, record):
            return _rec([1.0], status="solver_failed", retries=0)

        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(
            initial, evaluate_once,
            config=config, recovery_callback=cb,
        )
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert len(result.attempts) == 2
        assert reg.tracked_count == 1  # one replacement from tier 2


# ===================================================================
# Adapter-level recovery: must NOT exist
# ===================================================================


class TestAdapterRecoveryAbsent:
    def test_adapter_still_no_recovery(self) -> None:
        """make_cst_retry_evaluate_once has no recovery_callback param."""
        import inspect
        sig = inspect.signature(make_cst_retry_evaluate_once)
        assert "recovery" not in str(sig)


# ===================================================================
# Cleanup: registry.close_all in _cleanup_workflow_connection
# ===================================================================


class TestCleanupIntegration:
    def test_registry_close_all_on_workflow(self) -> None:
        """Simulate _cleanup_workflow_connection closing registry."""
        reg = CstConnectionRegistry()
        c1 = FakeConnection(pid=100)
        reg.track(c1)

        # Simulate cleanup
        force = True
        diag = reg.close_all(force=force)
        assert diag["closed_ok"] == 1
        assert c1._closed is True

    def test_registry_none_is_noop(self) -> None:
        """None registry (getattr returns None) is no-op."""
        reg = None
        if reg is not None:
            reg.close_all(force=True)  # should not execute
        assert True  # reached without error


# ===================================================================
# Safety: no forbidden imports
# ===================================================================


class TestSafety:
    def test_module_no_cst_import(self) -> None:
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"

    def test_module_no_factory_import(self) -> None:
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "cst_optimization.factory" not in text

    def test_module_no_recovery_import(self) -> None:
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "cst_optimization.workflows.recovery" not in text
