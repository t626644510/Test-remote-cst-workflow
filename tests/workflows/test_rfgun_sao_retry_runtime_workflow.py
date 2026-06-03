"""No-CST regression tests for RW3 retry runtime workflow wiring.

Tests final_record semantics, mutex, synthetic smoke hook gating,
checkpoint interaction, and penalty extraction — all without CST.
"""

from __future__ import annotations

import os
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
    RetryRuntimeResult,
    run_retry_loop_no_cst,
)
from workflows.rfgun_sao.retry_runtime_cst import (
    build_record_from_evaluation_result,
    make_cst_retry_evaluate_once,
    check_legacy_retry_mutex,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus
from workflows.rfgun_sao.workflow import (
    _is_retry_runtime_smoke_injection_enabled,
    _extract_retry_penalty_values,
    _build_retry_runtime_checkpoint_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pid(values: list[float]) -> ParameterIdentity:
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
    )


def _rec(
    values: list[float] | None,
    status: str = "success",
    retries: int = 0,
    schema: int = 1,
) -> EvaluationDatabaseRecord:
    return EvaluationDatabaseRecord(
        parameter_identity=_pid(values) if values is not None else None,
        status=status,
        retry_count=retries,
        schema_version=schema,
    )


class FakeCstEvaluator:
    """Duck-typed Workflow1Evaluator for no-CST tests."""

    def __init__(
        self,
        results: list[EvaluationResult],
        param_names: list[str] | None = None,
    ) -> None:
        self._results = results
        self._call_count = 0
        self._param_names = param_names or [f"p{i}" for i in range(10)]

    @property
    def call_count(self) -> int:
        return self._call_count

    def adapt_for_retry(
        self, params: np.ndarray, iteration: int,
    ) -> EvaluationResult:
        idx = self._call_count % len(self._results) if self._results else 0
        self._call_count += 1
        return self._results[idx]


# ---------------------------------------------------------------------------
# final_record semantics
# ---------------------------------------------------------------------------


class TestFinalRecord:
    def test_disabled_returns_initial_record(self) -> None:
        """Retry disabled: final_record = initial_record, no evaluate_once call."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return record

        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=False)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.final_record is initial
        assert result.final_record is not None
        assert result.final_record.status == "solver_failed"
        assert result.succeeded is False
        assert result.stopped_reason == "retry disabled"

    def test_initial_success_returns_success_record_attempts_zero(self) -> None:
        """Initial SUCCESS: final_record success, attempts=0."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="success", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is True
        assert len(result.attempts) == 0
        assert result.final_record is not None
        assert result.final_record.status == "success"

    def test_retry_success_returns_final_record_from_retry(self) -> None:
        """Failed initial -> retry success: final_record from retry attempt."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 1
        assert call_count == 1
        assert result.final_record is not None
        assert result.final_record.status == "success"
        assert result.final_record.retry_count == 1

    def test_max_tier_exhausted_final_record_terminal_failure(self) -> None:
        """max_tier exhausted: final_record terminal failure, not probably-infeasible."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="calibration_failed", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert result.final_record is not None
        assert "probably_infeasible" not in result.diagnostics
        assert result.final_record.status != "success"

    def test_probably_infeasible_skip_rejected_final_record_initial(self) -> None:
        """probably_infeasible skip rejected: final_record=initial, evaluate_once not called."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, use_probably_infeasible_for_skip=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is False
        assert result.stopped_reason == "probably_infeasible_skip_not_supported"
        assert result.final_record is initial
        assert "not supported" in result.diagnostics.get("error", "")


# ---------------------------------------------------------------------------
# Legacy retry mutex (workflow-level)
# ---------------------------------------------------------------------------


class TestWorkflowMutex:
    def test_no_config_returns_disabled(self) -> None:
        cfg, msg = check_legacy_retry_mutex(None)
        assert cfg.enabled is False
        assert msg is None

    def test_no_retry_runtime_section_returns_disabled(self) -> None:
        cfg, msg = check_legacy_retry_mutex({"optimization": {}})
        assert cfg.enabled is False
        assert msg is None

    def test_retry_runtime_enabled_legacy_disabled_ok(self) -> None:
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
            "optimization": {"retry": {"enabled": False}},
        })
        assert cfg.enabled is True
        assert msg is None

    def test_mutex_disables_runtime_when_legacy_enabled(self) -> None:
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
            "optimization": {"retry": {"enabled": True}},
        })
        assert cfg.enabled is False
        assert msg is not None
        assert "double retry" in msg

    def test_legacy_enabled_default_true(self) -> None:
        """No explicit enabled in legacy retry defaults to enabled=True."""
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
            "optimization": {"retry": {"max_tier1": 3}},
        })
        assert cfg.enabled is False
        assert msg is not None


# ---------------------------------------------------------------------------
# Synthetic smoke hook gating
# ---------------------------------------------------------------------------


class TestSmokeHookGating:
    def test_no_config_returns_false(self) -> None:
        assert _is_retry_runtime_smoke_injection_enabled(None) is False

    def test_config_no_smoke_section_returns_false(self) -> None:
        assert _is_retry_runtime_smoke_injection_enabled({}) is False

    def test_config_smoke_false_returns_false(self) -> None:
        cfg = {"retry_runtime": {"smoke_injection": False}}
        assert _is_retry_runtime_smoke_injection_enabled(cfg) is False

    def test_env_missing_returns_false(self) -> None:
        cfg = {"retry_runtime": {"smoke_injection": True}}
        env = {}  # no env var
        assert _is_retry_runtime_smoke_injection_enabled(cfg, environ=env) is False

    def test_env_wrong_value_returns_false(self) -> None:
        cfg = {"retry_runtime": {"smoke_injection": True}}
        env = {"WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION": "0"}
        assert _is_retry_runtime_smoke_injection_enabled(cfg, environ=env) is False

    def test_both_set_returns_true(self) -> None:
        cfg = {"retry_runtime": {"smoke_injection": True}}
        env = {"WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION": "1"}
        assert _is_retry_runtime_smoke_injection_enabled(cfg, environ=env) is True

    def test_config_none_with_env_still_false(self) -> None:
        env = {"WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION": "1"}
        assert _is_retry_runtime_smoke_injection_enabled(None, environ=env) is False


# ---------------------------------------------------------------------------
# penalty extraction via __retry_penalty__
# ---------------------------------------------------------------------------


class TestPenaltyExtraction:
    def test_extract_from_record_with_penalty(self) -> None:
        """Helper extracts penalty values from record with __retry_penalty__."""
        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            penalty_values={"m1": 0.5, "m2": 1.0},
        )
        record = build_record_from_evaluation_result(pid, result, penalty_values={"m1": 0.5, "m2": 1.0})
        pen_arr = _extract_retry_penalty_values(record, ["m1", "m2"])
        assert pen_arr is not None
        assert list(pen_arr) == [0.5, 1.0]

    def test_extract_from_record_no_penalty_returns_none(self) -> None:
        """No __retry_penalty__ key -> helper returns None."""
        pid = _pid([1.0])
        result = EvaluationResult(status=EvaluationStatus.SUCCESS)
        record = build_record_from_evaluation_result(pid, result)
        assert _extract_retry_penalty_values(record, ["m1"]) is None

    def test_extract_from_none_record_returns_none(self) -> None:
        assert _extract_retry_penalty_values(None, ["m1"]) is None

    def test_extract_partial_penalty_defaults_to_one(self) -> None:
        """Missing metric in penalty_values defaults to 1.0."""
        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            penalty_values={"m1": 0.5},
        )
        record = build_record_from_evaluation_result(pid, result, penalty_values={"m1": 0.5})
        pen_arr = _extract_retry_penalty_values(record, ["m1", "m2"])
        assert pen_arr is not None
        assert list(pen_arr) == [0.5, 1.0]


# ---------------------------------------------------------------------------
# Checkpoint records only final result
# ---------------------------------------------------------------------------


class TestCheckpointSemantics:
    def test_build_payload_with_valid_record(self) -> None:
        """Helper builds checkpoint payload with metrics from final_record."""
        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            raw_metrics={"m1": 11.4, "m2": 0.5},
        )
        record = build_record_from_evaluation_result(pid, result)
        x_phys = np.array([1.0])
        pen_arr = np.array([0.3, 1.0], dtype=float)
        x, raw, pen, ok, err = _build_retry_runtime_checkpoint_payload(
            record, x_phys, ["m1", "m2"], pen_arr, True, "",
        )
        assert list(raw) == [11.4, 0.5]
        assert list(pen) == [0.3, 1.0]
        assert ok is True
        assert err == ""

    def test_build_payload_with_none_record_uses_nan(self) -> None:
        """None record results in all-NaN raw_arr."""
        x_phys = np.array([1.0])
        pen_arr = np.array([1.0, 1.0], dtype=float)
        x, raw, pen, ok, err = _build_retry_runtime_checkpoint_payload(
            None, x_phys, ["m1", "m2"], pen_arr, False, "retry exhausted",
        )
        assert np.all(np.isnan(raw))
        assert ok is False
        assert "retry exhausted" in err

    def test_build_payload_partial_metrics_defaults_nan(self) -> None:
        """Missing metric in raw_metrics defaults to NaN."""
        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            raw_metrics={"m1": 11.4},
        )
        record = build_record_from_evaluation_result(pid, result)
        x_phys = np.array([1.0])
        pen_arr = np.array([0.3], dtype=float)
        x, raw, pen, ok, err = _build_retry_runtime_checkpoint_payload(
            record, x_phys, ["m1", "m2"], pen_arr, True, "",
        )
        assert raw[0] == 11.4
        assert np.isnan(raw[1])


# ---------------------------------------------------------------------------
# Integrated: adapter + retry loop + final_record
# ---------------------------------------------------------------------------


class TestAdapterIntegrationFinalRecord:
    def test_adapter_retry_produces_final_record_with_penalty(self) -> None:
        """Adapter retry success: final_record has penalty_values in diagnostics."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="fail"),
            EvaluationResult(
                status=EvaluationStatus.SUCCESS, error="",
                raw_metrics={"m1": 1.0},
                objective_values={"m1": 1.0},
                penalty_values={"m1": 0.3},
            ),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert result.final_record is not None
        fr = result.final_record
        fr_diag = fr.raw_payload.diagnostics if fr.raw_payload else {}
        pen_values = (fr_diag or {}).get("__retry_penalty__", {})
        assert pen_values.get("m1") == 0.3, f"Expected m1=0.3 in {pen_values}"

    def test_adapter_max_tier_record_is_last_failure(self) -> None:
        """Adapter max_tier exhaustion: final_record is last SOLVER_FAILED record."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="fail"),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is False
        assert result.final_record is not None
        assert result.final_record.status == "solver_failed"

    def test_gate_rejected_via_adapter_not_retried(self) -> None:
        """Gate rejected record: evaluate_once not called."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="gate_rejected", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is False
        assert fake.call_count == 0
        assert result.stopped_reason == "no_retry_gate_rejected"
