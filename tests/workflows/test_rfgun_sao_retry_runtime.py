"""No-CST tests for retry runtime wiring skeleton (Phase O).

Covers config resolution, retry loop, inter-pass/post-eval recovery,
and safety boundaries (no JSONL, no cst_optimisation, no file I/O).
"""

from __future__ import annotations

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
)
from cst_optimization.evaluation.retry_runtime import (
    RetryRuntimeConfig,
    RetryRuntimeResult,
    RetryAttemptRecord,
    resolve_retry_runtime_config,
    should_use_retry_runtime,
    run_retry_loop_no_cst,
    run_inter_pass_recovery_no_cst,
    run_post_eval_recovery_no_cst,
    _normalize_retry_record,
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
    error_tax: dict | None = None,
) -> EvaluationDatabaseRecord:
    rec = EvaluationDatabaseRecord(
        parameter_identity=_pid(values) if values is not None else None,
        status=status,
        retry_count=retries,
        schema_version=schema,
    )
    if error_tax is not None:
        rec.error_taxonomy = error_tax
    return rec


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class TestResolveRetryRuntimeConfig:
    def test_none_returns_disabled(self) -> None:
        cfg = resolve_retry_runtime_config(None)
        assert cfg.enabled is False

    def test_empty_dict_returns_disabled(self) -> None:
        cfg = resolve_retry_runtime_config({})
        assert cfg.enabled is False

    def test_missing_retry_key_returns_disabled(self) -> None:
        cfg = resolve_retry_runtime_config({"other": 42})
        assert cfg.enabled is False

    def test_non_dict_raw_returns_disabled(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": "not_a_dict"})
        assert cfg.enabled is False

    def test_explicit_enabled(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert cfg.enabled is True

    def test_explicit_enabled_flat(self) -> None:
        cfg = resolve_retry_runtime_config({"enabled": True})
        assert cfg.enabled is True

    def test_default_max_tier(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert cfg.max_tier == 3

    def test_custom_max_tier(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True, "max_tier": 5}})
        assert cfg.max_tier == 5

    def test_default_inter_pass_recovery_disabled(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert cfg.inter_pass_recovery_enabled is False

    def test_default_post_eval_recovery_disabled(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert cfg.post_eval_recovery_enabled is False

    def test_retry_disabled_does_not_set_recovery(self) -> None:
        """When retry is disabled, recovery fields remain default (False)."""
        cfg = resolve_retry_runtime_config(
            {"retry": {"enabled": False, "inter_pass_recovery_enabled": True}}
        )
        assert cfg.enabled is False
        # Because enabled is False, the parser returns before setting other fields,
        # so inter_pass_recovery_enabled stays at the default False.
        assert cfg.inter_pass_recovery_enabled is False

    def test_inter_pass_recovery_enabled(self) -> None:
        cfg = resolve_retry_runtime_config(
            {"retry": {"enabled": True, "inter_pass_recovery_enabled": True}}
        )
        assert cfg.inter_pass_recovery_enabled is True

    def test_post_eval_recovery_enabled(self) -> None:
        cfg = resolve_retry_runtime_config(
            {"retry": {"enabled": True, "post_eval_recovery_enabled": True}}
        )
        assert cfg.post_eval_recovery_enabled is True

    def test_default_allow_unknown_retry(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert cfg.allow_unknown_retry is True

    def test_default_allow_gate_retry(self) -> None:
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert cfg.allow_gate_retry is False


class TestShouldUseRetryRuntime:
    def test_disabled_returns_false(self) -> None:
        assert should_use_retry_runtime(RetryRuntimeConfig()) is False

    def test_enabled_returns_true(self) -> None:
        assert should_use_retry_runtime(RetryRuntimeConfig(enabled=True)) is True


# ---------------------------------------------------------------------------
# Retry loop 鈥?disabled config
# ---------------------------------------------------------------------------


class TestRetryLoopDisabled:
    def test_disabled_config_returns_immediately(self) -> None:
        """When retry is disabled, the loop does not call evaluate_once."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="calibration_failed")
        config = RetryRuntimeConfig(enabled=False)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is False
        assert result.stopped_reason == "retry disabled"
        assert result.final_status == "calibration_failed"

    def test_disabled_initial_success_returns_immediately(self) -> None:
        """Even a success record returns immediately when retry disabled."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="success")
        config = RetryRuntimeConfig(enabled=False)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is True
        assert result.stopped_reason == "retry disabled"


# ---------------------------------------------------------------------------
# Retry loop 鈥?success stops immediately
# ---------------------------------------------------------------------------


class TestRetryLoopSuccess:
    def test_success_initial_record_stops(self) -> None:
        """A success initial record stops without calling evaluate_once."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="success")
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is True
        assert result.stopped_reason == "success"
        assert len(result.attempts) == 0


# ---------------------------------------------------------------------------
# Retry loop 鈥?retry-eligible failures
# ---------------------------------------------------------------------------


class TestRetryLoopEligible:
    def test_calibration_failed_then_success(self) -> None:
        """calibration_failed is retried once at tier 1."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is True
        assert result.stopped_reason == "success"
        assert call_count == 1
        assert len(result.attempts) == 1
        assert result.attempts[0].tier == 1
        assert result.attempts[0].status_before == "calibration_failed"
        assert result.attempts[0].status_after == "success"
        assert result.retry_count_consumed == 1

    def test_solver_failed_retries_at_tier_2(self) -> None:
        """solver_failed with retry_count=1 retries at tier 2."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="solver_failed", retries=1)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is True
        assert result.attempts[0].tier == 2
        assert result.retry_count_consumed == 2

    def test_transient_failed_retries(self) -> None:
        """transient_failed is retry-eligible."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="transient_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert result.attempts[0].tier == 1

    def test_unknown_failed_retries_by_default(self) -> None:
        """unknown_failed is retry-eligible when allow_unknown_retry=True."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="unknown_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, allow_unknown_retry=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 1


# ---------------------------------------------------------------------------
# Retry loop 鈥?terminal non-retryable states
# ---------------------------------------------------------------------------


class TestRetryLoopTerminal:
    def test_gate_rejected_does_not_retry(self) -> None:
        """gate_rejected is not retried by default."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="gate_rejected")
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_gate_rejected"

    def test_diagnostic_only_does_not_retry(self) -> None:
        """diagnostic-only records are not retried."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="diagnostic_only")
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.stopped_reason == "no_retry_diagnostic_only"

    def test_incompatible_schema_does_not_retry(self) -> None:
        """Incompatible schema stops the loop."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="calibration_failed", schema=99)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.stopped_reason == "no_retry_incompatible_schema"

    def test_missing_identity_does_not_retry(self) -> None:
        """Missing parameter identity stops the loop."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = EvaluationDatabaseRecord(status="calibration_failed")
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.stopped_reason == "no_retry_missing_identity"

    def test_max_tier_reached_does_not_retry(self) -> None:
        """max_tier reached stops without attempting retry."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="calibration_failed", retries=3)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert result.retry_count_consumed == 3

    def test_max_tier_not_probably_infeasible(self) -> None:
        """max_tier reached does not mark probably_infeasible."""
        initial = _rec([1.0], status="calibration_failed", retries=3)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(
            initial, lambda t, r: _rec([1.0], status="success"), config=config
        )
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        # Check that diagnostics do not contain probably_infeasible
        assert "probably_infeasible" not in result.diagnostics


# ---------------------------------------------------------------------------
# Retry loop 鈥?recovery callback
# ---------------------------------------------------------------------------


class TestRetryLoopRecoveryCallback:
    def test_recovery_callback_called_before_retry(self) -> None:
        """recovery_callback is called before each retry attempt."""
        callback_tiers: list[int] = []

        def recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool:
            callback_tiers.append(tier)
            return True

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(
            initial, evaluate_once, config=config, recovery_callback=recovery_callback,
        )

        assert len(callback_tiers) == 1
        assert callback_tiers[0] == 1
        assert result.attempts[0].recovered is True
        assert result.attempts[0].recovery_label == "recovery_success"

    def test_recovery_callback_failure_does_not_stop(self) -> None:
        """A recovery callback returning False does not stop the loop."""
        def recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool:
            return False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(
            initial, evaluate_once, config=config, recovery_callback=recovery_callback,
        )

        assert result.succeeded is True
        assert result.attempts[0].recovered is False
        assert result.attempts[0].recovery_label == "recovery_failed"

    def test_recovery_callback_exception_captured(self) -> None:
        """An exception in recovery_callback is captured in diagnostics."""
        def recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool:
            raise ValueError("recovery failed")

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(
            initial, evaluate_once, config=config, recovery_callback=recovery_callback,
        )

        assert result.succeeded is True
        assert result.attempts[0].recovered is False
        assert "recovery_exception" in result.attempts[0].recovery_label
        assert "recovery failed" in result.attempts[0].recovery_label

    def test_no_recovery_callback_skips_gracefully(self) -> None:
        """No recovery_callback means recovery_label is empty and recovered is False."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is True
        assert result.attempts[0].recovered is False
        assert result.attempts[0].recovery_label == ""


# ---------------------------------------------------------------------------
# Retry loop 鈥?exception handling
# ---------------------------------------------------------------------------


class TestRetryLoopException:
    def test_evaluate_once_exception_captured(self) -> None:
        """An evaluate_once exception is captured as a failure diagnostic."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            raise RuntimeError("simulated failure")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=1)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert len(result.attempts) == 1
        assert result.attempts[0].status_after == "evaluate_exception"
        assert "simulated failure" in result.attempts[0].error
        # With max_tier=1, the exception-produced unknown_failed exceeds tier
        assert result.stopped_reason == "no_retry_max_tiers_reached"

    def test_multiple_exceptions_reach_max_tier(self) -> None:
        """Repeated evaluate_once exceptions eventually hit max_tier."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            raise RuntimeError("persistent failure")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert len(result.attempts) == 2
        assert all(a.status_after == "evaluate_exception" for a in result.attempts)
        assert result.stopped_reason == "no_retry_max_tiers_reached"


# ---------------------------------------------------------------------------
# Retry loop 鈥?probably-infeasible guard rejected
# ---------------------------------------------------------------------------


class TestRetryLoopProbablyInfeasible:
    def test_probably_infeasible_skip_rejected(self) -> None:
        """use_probably_infeasible_for_skip=True is rejected with diagnostic."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, use_probably_infeasible_for_skip=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert result.stopped_reason == "probably_infeasible_skip_not_supported"
        assert "not supported in Phase O" in result.diagnostics.get("error", "")

    def test_probably_infeasible_default_config_false(self) -> None:
        """Default config has use_probably_infeasible_for_skip=False."""
        cfg = RetryRuntimeConfig()
        assert cfg.use_probably_infeasible_for_skip is False

    def test_probably_infeasible_resolved_config_stores_value(self) -> None:
        """The config resolver stores the probably-infeasible flag."""
        cfg = resolve_retry_runtime_config(
            {"retry": {"enabled": True, "use_probably_infeasible_for_skip": True}}
        )
        assert cfg.use_probably_infeasible_for_skip is True


    def test_probably_infeasible_still_rejected_before_evaluate(self) -> None:
        """use_probably_infeasible_for_skip=True rejects before calling evaluate_once."""
        called = False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal called
            called = True
            return _rec([1.0], status="success")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, use_probably_infeasible_for_skip=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert called is False
        assert result.stopped_reason == "probably_infeasible_skip_not_supported"


# ---------------------------------------------------------------------------
# O1 鈥?_normalize_retry_record unit tests
# ---------------------------------------------------------------------------


class TestNormalizeRetryRecord:
    def test_success_passthrough(self) -> None:
        """SUCCESS records are returned as-is (no normalisation)."""
        rec = _rec([1.0], status="success", retries=0)
        result, diag = _normalize_retry_record(rec, 3)
        assert result.retry_count == 0
        assert result.status == "success"
        assert diag == {}

    def test_already_advanced_passthrough(self) -> None:
        """Records with retry_count > previous are returned as-is."""
        rec = _rec([1.0], status="calibration_failed", retries=5)
        result, diag = _normalize_retry_record(rec, 3)
        assert result.retry_count == 5
        assert diag == {}

    def test_same_retry_count_advanced(self) -> None:
        """Records with retry_count == previous are advanced by 1."""
        rec = _rec([1.0], status="calibration_failed", retries=2)
        result, diag = _normalize_retry_record(rec, 2)
        assert result.retry_count == 3
        assert result.status == "calibration_failed"
        assert diag["retry_count_advanced"] is True
        assert diag["retry_count_before"] == 2
        assert diag["retry_count_after"] == 3

    def test_lower_retry_count_advanced(self) -> None:
        """Records with retry_count < previous are advanced to previous + 1."""
        rec = _rec([1.0], status="solver_failed", retries=0)
        result, diag = _normalize_retry_record(rec, 5)
        assert result.retry_count == 6
        assert diag["retry_count_advanced"] is True
        assert diag["retry_count_before"] == 0
        assert diag["retry_count_after"] == 6

    def test_preserves_other_fields(self) -> None:
        """Normalisation preserves fields other than retry_count."""
        pid = _pid([1.0, 2.0])
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status="transient_failed",
            retry_count=1,
            schema_version=2,
            source="test",
            error_taxonomy={"cause": "network"},
        )
        result, diag = _normalize_retry_record(rec, 1)
        assert result.retry_count == 2
        assert result.parameter_identity == pid
        assert result.status == "transient_failed"
        assert result.schema_version == 2
        assert result.source == "test"
        assert result.error_taxonomy == {"cause": "network"}
        assert diag["retry_count_advanced"] is True


# ---------------------------------------------------------------------------
# O1 鈥?progress guard: same retry_count repeated
# ---------------------------------------------------------------------------


class TestRetryLoopProgressSameFailure:
    def test_same_retry_count_terminates_at_max_tier(self) -> None:
        """Same retryable failure with unchanged retry_count terminates at max_tier."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="calibration_failed", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert len(result.attempts) == 3
        assert call_count == 3
        assert result.retry_count_consumed == 3
        # Progress guard should have activated for each attempt
        assert len(result.diagnostics.get("progress_guard_activations", [])) == 3

    def test_same_retry_count_max_tier_1_terminates(self) -> None:
        """With max_tier=1, repeated same failures stop after 1 attempt."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="calibration_failed", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=1)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert len(result.attempts) == 1
        assert call_count == 1

    def test_same_retry_count_solver_failed(self) -> None:
        """Same retry_count with solver_failed also terminates."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="solver_failed", retries=2)

        initial = _rec([1.0], status="solver_failed", retries=2)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        # One attempt brings retry_count from 2 to 3 (capped at max_tier)
        assert len(result.attempts) == 1

    def test_multiple_same_retry_count_unknown_failed(self) -> None:
        """Same unknown_failed with unchanged retry_count terminates."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="unknown_failed", retries=0)

        initial = _rec([1.0], status="unknown_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, allow_unknown_retry=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert len(result.attempts) == 3


# ---------------------------------------------------------------------------
# O1 鈥?progress guard: lower retry_count returned
# ---------------------------------------------------------------------------


class TestRetryLoopProgressLowerRetryCount:
    def test_lower_retry_count_terminates_at_max_tier(self) -> None:
        """evaluate_once returning lower retry_count terminates at max_tier."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="solver_failed", retries=0)

        initial = _rec([1.0], status="solver_failed", retries=3)
        config = RetryRuntimeConfig(enabled=True, max_tier=5)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        # Each normalisation advances: 3->4->5, so 2 attempts
        assert len(result.attempts) == 2
        # Progress guard should have activated
        assert len(result.diagnostics.get("progress_guard_activations", [])) >= 1

    def test_decreasing_then_increasing(self) -> None:
        """Decreasing then increasing retry_count still terminates."""
        call_count = 0

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            nonlocal call_count
            call_count += 1
            return _rec([1.0], status="calibration_failed", retries=1)

        initial = _rec([1.0], status="calibration_failed", retries=5)
        config = RetryRuntimeConfig(enabled=True, max_tier=8)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        # 5 -> normalise 6, 6 -> 7, 7 -> 8 (max_tier), so 3 attempts
        assert len(result.attempts) == 3


# ---------------------------------------------------------------------------
# O1 鈥?progress guard: terminal after retry
# ---------------------------------------------------------------------------


class TestRetryLoopProgressTerminalAfterRetry:
    def test_gate_rejected_after_retry_stops(self) -> None:
        """evaluate_once returning gate_rejected after a retry stops."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="gate_rejected", retries=1)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_gate_rejected"
        assert len(result.attempts) == 1

    def test_diagnostic_only_after_retry_stops(self) -> None:
        """evaluate_once returning diagnostic_only after a retry stops."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="diagnostic_only")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.stopped_reason == "no_retry_diagnostic_only"

    def test_incompatible_schema_after_retry_stops(self) -> None:
        """evaluate_once returning incompatible schema stops."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="calibration_failed", schema=99)

        initial = _rec([1.0], status="calibration_failed", retries=0, schema=1)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.stopped_reason == "no_retry_incompatible_schema"

    def test_missing_identity_after_retry_stops(self) -> None:
        """evaluate_once returning missing identity stops."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return EvaluationDatabaseRecord(status="calibration_failed")

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.stopped_reason == "no_retry_missing_identity"


# ---------------------------------------------------------------------------
# O1 鈥?progress guard: success with no retry_count advance
# ---------------------------------------------------------------------------


class TestRetryLoopProgressSuccess:
    def test_success_with_unchanged_retry_count(self) -> None:
        """evaluate_once returning SUCCESS with unchanged retry_count stops as success."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is True
        assert result.stopped_reason == "success"
        assert len(result.attempts) == 1
        assert result.attempts[0].status_after == "success"
        # retry_count_consumed = max(current.retry_count=0, attempts_consumed=1)
        assert result.retry_count_consumed == 1

    def test_success_with_lower_retry_count(self) -> None:
        """evaluate_once returning SUCCESS with lower retry_count stops as success."""
        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)

        assert result.succeeded is True
        assert result.stopped_reason == "success"
        assert len(result.attempts) == 1


# ---------------------------------------------------------------------------
# O1 鈥?progress guard: recovery + same failure
# ---------------------------------------------------------------------------


class TestRetryLoopProgressRecovery:
    def test_recovery_exception_and_same_failure_terminates(self) -> None:
        """recovery exception + same failed retry_count terminates at max_tier."""
        def recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool:
            raise ValueError("recovery problem")

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="calibration_failed", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(
            initial, evaluate_once, config=config, recovery_callback=recovery_callback,
        )

        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert len(result.attempts) == 2
        for attempt in result.attempts:
            assert "recovery_exception" in attempt.recovery_label
        assert len(result.diagnostics.get("progress_guard_activations", [])) == 2

    def test_recovery_false_and_same_failure_terminates(self) -> None:
        """recovery callback returning False + same failure terminates."""
        def recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool:
            return False

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="calibration_failed", retries=0)

        initial = _rec([1.0], status="calibration_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(
            initial, evaluate_once, config=config, recovery_callback=recovery_callback,
        )

        assert result.succeeded is False
        assert len(result.attempts) == 3


# ---------------------------------------------------------------------------
# O1 鈥?safety: internal progress guard present in source
# ---------------------------------------------------------------------------


class TestO1Safety:
    def test_normalize_retry_record_in_source(self) -> None:
        """retry_runtime module contains _normalize_retry_record."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "_normalize_retry_record" in text

    def test_attempts_consumed_in_source(self) -> None:
        """retry_runtime contains the internal attempts_consumed guard."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "attempts_consumed" in text

    def test_no_should_escalate_to_probably_infeasible(self) -> None:
        """retry_runtime does not call should_escalate_to_probably_infeasible."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "should_escalate_to_probably_infeasible" not in text


# ---------------------------------------------------------------------------
# Inter-pass recovery
# ---------------------------------------------------------------------------


class TestInterPassRecovery:
    def test_disabled_callback_not_called(self) -> None:
        """When disabled, the callback is not invoked."""
        called = False

        def callback() -> bool:
            nonlocal called
            called = True
            return True

        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, callback, enabled=False)
        assert called is False
        assert result["status"] == "skipped_disabled"
        assert result["recovered"] is False

    def test_disabled_no_callback(self) -> None:
        """When disabled and no callback, returns skipped_disabled."""
        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, enabled=False)
        assert result["status"] == "skipped_disabled"

    def test_enabled_callback_called(self) -> None:
        """When enabled, the callback is invoked once."""
        called = False

        def callback() -> bool:
            nonlocal called
            called = True
            return True

        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, callback, enabled=True)
        assert called is True
        assert result["status"] == "completed"
        assert result["recovered"] is True

    def test_enabled_callback_returns_false(self) -> None:
        """Callback returning False is reported correctly."""
        def callback() -> bool:
            return False

        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, callback, enabled=True)
        assert result["status"] == "completed"
        assert result["recovered"] is False

    def test_callback_exception_captured(self) -> None:
        """Callback exception is captured in the result."""
        def callback() -> bool:
            raise RuntimeError("inter-pass recovery failed")

        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, callback, enabled=True)
        assert result["status"] == "callback_exception"
        assert result["recovered"] is False
        assert "inter-pass recovery failed" in result.get("error", "")

    def test_enabled_no_callback_skips(self) -> None:
        """When enabled but no callback provided, returns skipped_disabled."""
        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, enabled=True)
        assert result["status"] == "skipped_disabled"
        assert result["recovered"] is False

    def test_calibration_record_passed_through(self) -> None:
        """The calibration record is accepted as an argument (not used in callback)."""
        def callback() -> bool:
            return True

        record = _rec([1.0], status="calibration_failed")
        result = run_inter_pass_recovery_no_cst(record, callback, enabled=True)
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Post-eval recovery
# ---------------------------------------------------------------------------


class TestPostEvalRecovery:
    def test_disabled_callback_not_called(self) -> None:
        """When disabled, the callback is not invoked."""
        called = False

        def callback() -> bool:
            nonlocal called
            called = True
            return True

        result = run_post_eval_recovery_no_cst(callback, enabled=False)
        assert called is False
        assert result["status"] == "skipped_disabled"
        assert result["recovered"] is False

    def test_disabled_no_callback(self) -> None:
        """When disabled and no callback, returns skipped_disabled."""
        result = run_post_eval_recovery_no_cst(enabled=False)
        assert result["status"] == "skipped_disabled"

    def test_enabled_callback_called(self) -> None:
        """When enabled, the callback is invoked once."""
        called = False

        def callback() -> bool:
            nonlocal called
            called = True
            return True

        result = run_post_eval_recovery_no_cst(callback, enabled=True)
        assert called is True
        assert result["status"] == "completed"
        assert result["recovered"] is True

    def test_callback_returns_false(self) -> None:
        """Callback returning False is reported correctly."""
        def callback() -> bool:
            return False

        result = run_post_eval_recovery_no_cst(callback, enabled=True)
        assert result["status"] == "completed"
        assert result["recovered"] is False

    def test_callback_exception_captured(self) -> None:
        """Callback exception is captured in the result."""
        def callback() -> bool:
            raise RuntimeError("post-eval recovery failed")

        result = run_post_eval_recovery_no_cst(callback, enabled=True)
        assert result["status"] == "callback_exception"
        assert result["recovered"] is False
        assert "post-eval recovery failed" in result.get("error", "")

    def test_enabled_no_callback_skips(self) -> None:
        """When enabled but no callback provided, returns skipped_disabled."""
        result = run_post_eval_recovery_no_cst(enabled=True)
        assert result["status"] == "skipped_disabled"


# ---------------------------------------------------------------------------
# Safety 鈥?no forbidden imports / references
# ---------------------------------------------------------------------------


class TestSafety:
    def test_no_jsonl_reference(self) -> None:
        """retry_runtime module does not reference Phase C JSONL sidecar."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = [
            "records.py", "resolve_records_config", ".jsonl",
            "evaluation_records", "append_jsonl_record", "read_jsonl_records",
        ]
        for item in forbidden:
            assert item not in text, (
                f"retry_runtime should not reference {item!r}"
            )

    def test_no_cst_optimization_factory(self) -> None:
        """retry_runtime does not import cst_optimization.factory."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "cst_optimization.factory" not in text

    def test_no_cst_optimization_recovery(self) -> None:
        """retry_runtime does not import cst_optimization.workflows.recovery."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "cst_optimization.workflows.recovery" not in text

    def test_no_file_io_in_retry_loop(self) -> None:
        """run_retry_loop_no_cst does not read or write files."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        file_io_keywords = ['open(', 'Path(', 'pathlib', '.write_text', '.read_text',
                            '.write_bytes', '.read_bytes']
        for kw in file_io_keywords:
            assert kw not in text, (
                f"retry_runtime should not do file I/O (found {kw!r})"
            )

    def test_no_durable_db_reference(self) -> None:
        """retry_runtime does not reference durable database operations."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        db_keywords = ['.sqlite', '.db', 'sqlite3', 'CREATE TABLE', 'INSERT INTO',
                       'database_lookup', 'database_append']
        for kw in db_keywords:
            assert kw not in text, (
                f"retry_runtime should not reference durable DB (found {kw!r})"
            )

    def test_no_legacy_recovery_import(self) -> None:
        """retry_runtime does not import or reference legacy RecoveryWorkflowEvaluator."""
        import cst_optimization.evaluation.retry_runtime as rt
        src_path = rt.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "RecoveryWorkflowEvaluator" not in text


# ---------------------------------------------------------------------------
# No I/O 鈥?pure function checks
# ---------------------------------------------------------------------------


class TestNoIO:
    def test_config_resolution_no_side_effects(self) -> None:
        """resolve_retry_runtime_config has no side effects."""
        cfg = resolve_retry_runtime_config({"retry": {"enabled": True}})
        assert isinstance(cfg, RetryRuntimeConfig)

    def test_retry_loop_no_side_effects_outside_args(self) -> None:
        """run_retry_loop_no_cst does not mutate the initial record."""
        initial = _rec([1.0], status="calibration_failed", retries=0)
        original_retries = initial.retry_count

        def evaluate_once(tier: int, record: EvaluationDatabaseRecord) -> EvaluationDatabaseRecord:
            return _rec([1.0], status="success", retries=record.retry_count + 1)

        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert initial.retry_count == original_retries
        assert isinstance(result, RetryRuntimeResult)


