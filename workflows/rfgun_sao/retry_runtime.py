# Retry / recovery runtime wiring skeleton (no-CST).
# Injectable runners, no CST dependency, disabled by default.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from workflows.rfgun_sao.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
)
from workflows.rfgun_sao.retry_taxonomy import (
    RetryEligibilityAction,
    RetryPolicy,
    classify_retry_eligibility,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RetryRuntimeConfig:
    """Runtime retry/recovery configuration.

    All features disabled by default.  Opt-in only.
    """
    enabled: bool = False
    max_tier: int = 3
    allow_unknown_retry: bool = True
    allow_gate_retry: bool = False
    inter_pass_recovery_enabled: bool = False
    post_eval_recovery_enabled: bool = False
    use_probably_infeasible_for_skip: bool = False


def resolve_retry_runtime_config(config_dict: dict | None) -> RetryRuntimeConfig:
    """Resolve runtime config from a nested dict.

    Expected shape: ``{"retry": {"enabled": True, "max_tier": 3, ...}}``
    or a flat ``{"enabled": True, ...}``.  Missing/None returns disabled.
    """
    if config_dict is None:
        return RetryRuntimeConfig()

    # Accept both nested "retry" key and flat config
    raw = config_dict.get("retry", config_dict)
    if not isinstance(raw, dict):
        return RetryRuntimeConfig()

    enabled = bool(raw.get("enabled", False))
    cfg = RetryRuntimeConfig(enabled=enabled)

    if not enabled:
        return cfg

    cfg.max_tier = int(raw.get("max_tier", 3))
    cfg.allow_unknown_retry = bool(raw.get("allow_unknown_retry", True))
    cfg.allow_gate_retry = bool(raw.get("allow_gate_retry", False))
    cfg.inter_pass_recovery_enabled = bool(raw.get("inter_pass_recovery_enabled", False))
    cfg.post_eval_recovery_enabled = bool(raw.get("post_eval_recovery_enabled", False))
    cfg.use_probably_infeasible_for_skip = bool(raw.get("use_probably_infeasible_for_skip", False))

    return cfg


def should_use_retry_runtime(config: RetryRuntimeConfig) -> bool:
    """Check whether the retry runtime should be active."""
    return config.enabled


# ---------------------------------------------------------------------------
# Retry attempt / result records
# ---------------------------------------------------------------------------


@dataclass
class RetryAttemptRecord:
    """One retry attempt within a retry loop."""
    attempt_index: int = 0
    tier: int = 0
    status_before: str = ""
    status_after: str = ""
    recovered: bool = False
    recovery_label: str = ""
    error: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetryRuntimeResult:
    """Result of a retry loop execution."""
    final_status: str = ""
    attempts: list[RetryAttemptRecord] = field(default_factory=list)
    retry_count_consumed: int = 0
    succeeded: bool = False
    stopped_reason: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Retry loop (no-CST, injectable evaluate_once callback)
# ---------------------------------------------------------------------------


def run_retry_loop_no_cst(
    initial_record: EvaluationDatabaseRecord,
    evaluate_once: Callable[[int, EvaluationDatabaseRecord], EvaluationDatabaseRecord],
    *,
    config: RetryRuntimeConfig | None = None,
    recovery_callback: Callable[[int, EvaluationDatabaseRecord], bool] | None = None,
    current_schema: int | None = None,
) -> RetryRuntimeResult:
    """Run a no-CST retry loop with injectable ``evaluate_once``.

    Parameters
    ----------
    initial_record : EvaluationDatabaseRecord
        The initial (failed or first-attempt) record.
    evaluate_once : callable
        ``evaluate_once(tier, record) -> EvaluationDatabaseRecord``.
        Must return a record with ``status`` and ``retry_count`` reflecting
        the attempt outcome.  No CST dependency in tests.
    config : RetryRuntimeConfig or None
        Retry configuration.  Disabled by default.
    recovery_callback : callable or None
        ``recovery_callback(tier, record) -> bool``.  Called before each
        retry evaluation.  Return ``True`` if recovery succeeded.
        Exception → captured in diagnostics, does not stop loop.
    current_schema : int or None
        Schema version for classification.

    Returns
    -------
    RetryRuntimeResult
    """
    if config is None:
        config = RetryRuntimeConfig()

    if not config.enabled:
        result = RetryRuntimeResult(
            final_status=str(initial_record.status),
            succeeded=initial_record.status == EvaluationDatabaseStatus.SUCCESS,
            stopped_reason="retry disabled",
        )
        return result

    if config.use_probably_infeasible_for_skip:
        result = RetryRuntimeResult(
            stopped_reason="probably_infeasible_skip_not_supported",
            diagnostics={"error": "use_probably_infeasible_for_skip is not supported in Phase O"},
        )
        return result

    policy = RetryPolicy(
        max_tier=config.max_tier,
        allow_unknown_retry=config.allow_unknown_retry,
        allow_gate_retry=config.allow_gate_retry,
    )

    result = RetryRuntimeResult()
    current = initial_record
    attempts: list[RetryAttemptRecord] = []

    while True:
        eligibility = classify_retry_eligibility(
            current, policy=policy, current_schema=current_schema,
        )

        # Success → stop
        if eligibility.action == RetryEligibilityAction.NO_RETRY_SUCCESS:
            result.final_status = str(current.status)
            result.succeeded = True
            result.stopped_reason = "success"
            result.attempts = attempts
            result.retry_count_consumed = current.retry_count
            return result

        # Non-retryable terminal states
        if eligibility.action in (
            RetryEligibilityAction.NO_RETRY_GATE_REJECTED,
            RetryEligibilityAction.NO_RETRY_DIAGNOSTIC_ONLY,
            RetryEligibilityAction.NO_RETRY_INCOMPATIBLE_SCHEMA,
            RetryEligibilityAction.NO_RETRY_MISSING_IDENTITY,
            RetryEligibilityAction.NO_RETRY_MAX_TIERS_REACHED,
        ):
            result.final_status = str(current.status)
            result.succeeded = False
            result.stopped_reason = eligibility.action.value
            result.attempts = attempts
            result.retry_count_consumed = current.retry_count
            return result

        # Retry-eligible
        if eligibility.action == RetryEligibilityAction.RETRY_ELIGIBLE:
            tier = eligibility.next_tier

            # Recovery callback
            recovered = False
            recovery_label = ""
            if recovery_callback is not None:
                try:
                    recovered = recovery_callback(tier, current)
                    recovery_label = "recovery_success" if recovered else "recovery_failed"
                except Exception as exc:
                    recovered = False
                    recovery_label = f"recovery_exception:{str(exc)[:100]}"

            # Evaluate
            attempt_record = RetryAttemptRecord(
                attempt_index=len(attempts),
                tier=tier,
                status_before=str(current.status),
                recovered=recovered,
                recovery_label=recovery_label,
            )

            try:
                next_record = evaluate_once(tier, current)
                attempt_record.status_after = str(next_record.status)
                current = next_record
            except Exception as exc:
                attempt_record.status_after = "evaluate_exception"
                attempt_record.error = str(exc)[:200]
                # Create a failure record so the loop can classify and stop
                current = EvaluationDatabaseRecord(
                    parameter_identity=current.parameter_identity,
                    status=EvaluationDatabaseStatus.UNKNOWN_FAILED,
                    retry_count=current.retry_count + 1,
                    error_taxonomy={"evaluate_exception": str(exc)[:200]},
                )

            attempts.append(attempt_record)
            continue

        # Catch-all
        result.final_status = str(current.status)
        result.succeeded = False
        result.stopped_reason = f"unhandled_eligibility:{eligibility.action.value}"
        result.attempts = attempts
        result.retry_count_consumed = current.retry_count
        return result


# ---------------------------------------------------------------------------
# Inter-pass recovery (no-CST, callback-only)
# ---------------------------------------------------------------------------


def run_inter_pass_recovery_no_cst(
    calibration_record: EvaluationDatabaseRecord,
    recovery_callback: Callable[[], bool] | None = None,
    *,
    enabled: bool = False,
) -> dict[str, Any]:
    """Run inter-pass recovery (no-CST, callback-only).

    If disabled or no callback, returns diagnostic 'skipped_disabled'.
    """
    if not enabled or recovery_callback is None:
        return {"status": "skipped_disabled", "recovered": False}

    try:
        recovered = recovery_callback()
        return {"status": "completed", "recovered": recovered}
    except Exception as exc:
        return {"status": "callback_exception", "recovered": False, "error": str(exc)[:200]}


# ---------------------------------------------------------------------------
# Post-eval recovery (no-CST, callback-only)
# ---------------------------------------------------------------------------


def run_post_eval_recovery_no_cst(
    recovery_callback: Callable[[], bool] | None = None,
    *,
    enabled: bool = False,
) -> dict[str, Any]:
    """Run post-evaluation recovery (no-CST, callback-only)."""
    if not enabled or recovery_callback is None:
        return {"status": "skipped_disabled", "recovered": False}

    try:
        recovered = recovery_callback()
        return {"status": "completed", "recovered": recovered}
    except Exception as exc:
        return {"status": "callback_exception", "recovered": False, "error": str(exc)[:200]}
