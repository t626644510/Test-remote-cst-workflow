# Retry / recovery runtime wiring skeleton (no-CST).
# Injectable runners, no CST dependency, disabled by default.
#
# Phase O1 — Retry runtime no-CST progress hardening:
#   - Internal attempts_consumed guard prevents infinite loops when
#     injectable evaluate_once() returns failed records without
#     advancing retry_count.
#   - _normalize_retry_record() ensures each attempt consumes at least
#     1 retry_count unit so the taxonomy classifier sees progress.
#   - Gateway statuses (gate_rejected, diagnostic_only, etc.) are
#     handled by classify_retry_eligibility() before retry_count
#     matters, so normalization does not change terminal behaviour.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from cst_optimization.evaluation.schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
)
from cst_optimization.evaluation.retry_taxonomy import (
    RetryEligibilityAction,
    RetryPolicy,
    classify_retry_eligibility,
)

_logger = logging.getLogger(__name__)


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
    """Result of a retry loop execution.

    Parameters
    ----------
    final_status : str
        Status of the final record in the loop.
    final_record : EvaluationDatabaseRecord or None
        The last ``EvaluationDatabaseRecord`` produced by the loop.
        This is the record the optimizer / checkpoint should use.
        ``None`` if the loop was disabled or no evaluation was attempted.
    attempts : list[RetryAttemptRecord]
        Records of each retry attempt.
    retry_count_consumed : int
        Number of retry attempts consumed.
        Determined as ``max(final_record.retry_count, internal_attempts_counter)``
        where the internal counter reflects the number of ``evaluate_once()``
        calls made.  This may be higher than the final record's ``retry_count``
        if ``evaluate_once()`` does not increment ``retry_count`` and the
        progress guard normalises it.
    succeeded : bool
        Whether the loop ended with a success status.
    stopped_reason : str
        Reason the loop stopped (e.g. ``"success"``, ``"retry disabled"``,
        ``"no_retry_max_tiers_reached"``).
    diagnostics : dict
        Extra information including progress guard activations.
    """
    final_status: str = ""
    final_record: EvaluationDatabaseRecord | None = None
    attempts: list[RetryAttemptRecord] = field(default_factory=list)
    retry_count_consumed: int = 0
    succeeded: bool = False
    stopped_reason: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Progress normalisation helper (Phase O1)
# ---------------------------------------------------------------------------


def _normalize_retry_record(
    record: EvaluationDatabaseRecord,
    previous_retry_count: int,
) -> tuple[EvaluationDatabaseRecord, dict[str, Any]]:
    """Ensure a returned evaluation record's retry_count reflects progress.

    If the record is SUCCESS, return as-is (the classifier handles it).
    If ``record.retry_count > previous_retry_count``, already advanced.
    Otherwise, create a shallow copy with ``retry_count = previous + 1``
    so that the taxonomy classifier sees monotonic progress and the loop
    cannot infinite-loop on a callback that never advances retry_count.

    Returns ``(normalized_record, diagnostics)`` where *diagnostics* is
    empty when no normalisation was needed and contains
    ``retry_count_advanced`` / ``retry_count_before`` / ``retry_count_after``
    when advancement was applied.

    No file I/O, no CST, no database calls.
    """
    diag: dict[str, Any] = {}

    if record.status == EvaluationDatabaseStatus.SUCCESS:
        return record, diag

    if record.retry_count > previous_retry_count:
        return record, diag

    advanced = EvaluationDatabaseRecord(
        schema_version=record.schema_version,
        parameter_identity=record.parameter_identity,
        status=record.status,
        raw_payload=record.raw_payload,
        objective_names=record.objective_names,
        source=record.source,
        provenance=record.provenance,
        retry_count=previous_retry_count + 1,
        error_taxonomy=record.error_taxonomy,
    )
    diag["retry_count_advanced"] = True
    diag["retry_count_before"] = record.retry_count
    diag["retry_count_after"] = advanced.retry_count
    return advanced, diag


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

    The loop is guaranteed to terminate within ``max_tier`` retry attempts.
    An internal ``attempts_consumed`` counter (Phase O1 progress guard)
    bounds the loop independently of the returned record's ``retry_count``,
    preventing infinite loops when ``evaluate_once`` returns retryable
    failures without advancing ``retry_count``.

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
        Exception -> captured in diagnostics, does not stop loop.
    current_schema : int or None
        Schema version for classification.

    Returns
    -------
    RetryRuntimeResult
        Final result with ``retry_count_consumed`` set to
        ``max(final_record.retry_count, internal_attempts_counter)``.
    """
    if config is None:
        config = RetryRuntimeConfig()

    if not config.enabled:
        result = RetryRuntimeResult(
            final_status=str(initial_record.status),
            final_record=initial_record,
            succeeded=initial_record.status == EvaluationDatabaseStatus.SUCCESS,
            stopped_reason="retry disabled",
        )
        _logger.debug(
            "Retry disabled: final_status=%s succeeded=%s",
            result.final_status, result.succeeded,
        )
        return result

    if config.use_probably_infeasible_for_skip:
        result = RetryRuntimeResult(
            final_record=initial_record,
            stopped_reason="probably_infeasible_skip_not_supported",
            diagnostics={"error": "use_probably_infeasible_for_skip is not supported in Phase O"},
        )
        _logger.debug("Retry: probably_infeasible_skip rejected by design")
        return result

    policy = RetryPolicy(
        max_tier=config.max_tier,
        allow_unknown_retry=config.allow_unknown_retry,
        allow_gate_retry=config.allow_gate_retry,
    )

    result = RetryRuntimeResult()
    current = initial_record
    attempts: list[RetryAttemptRecord] = []
    attempts_consumed: int = 0  # Phase O1 internal progress guard

    def _make_result() -> RetryRuntimeResult:
        """Build the final result from current state."""
        result.final_status = str(current.status)
        result.final_record = current
        result.attempts = attempts
        result.retry_count_consumed = max(current.retry_count, attempts_consumed)
        _logger.debug(
            "Retry result: final_status=%s succeeded=%s stopped=%s "
            "attempts=%d retry_consumed=%d",
            result.final_status, result.succeeded, result.stopped_reason,
            len(attempts), result.retry_count_consumed,
        )
        return result

    while True:
        eligibility = classify_retry_eligibility(
            current, policy=policy, current_schema=current_schema,
        )

        # Success -> stop
        if eligibility.action == RetryEligibilityAction.NO_RETRY_SUCCESS:
            result.succeeded = True
            result.stopped_reason = "success"
            _logger.debug("Retry: success after %d attempt(s)", len(attempts))
            return _make_result()

        # Non-retryable terminal states
        if eligibility.action in (
            RetryEligibilityAction.NO_RETRY_GATE_REJECTED,
            RetryEligibilityAction.NO_RETRY_DIAGNOSTIC_ONLY,
            RetryEligibilityAction.NO_RETRY_INCOMPATIBLE_SCHEMA,
            RetryEligibilityAction.NO_RETRY_MISSING_IDENTITY,
            RetryEligibilityAction.NO_RETRY_MAX_TIERS_REACHED,
        ):
            result.succeeded = False
            result.stopped_reason = eligibility.action.value
            _logger.debug("Retry: terminal (%s) after %d attempt(s)", eligibility.action.value, len(attempts))
            return _make_result()

        # Retry-eligible
        if eligibility.action == RetryEligibilityAction.RETRY_ELIGIBLE:
            # Phase O1 internal progress guard: do not exceed max_tier
            # attempts regardless of the returned record's retry_count.
            if attempts_consumed >= config.max_tier:
                result.succeeded = False
                result.stopped_reason = "no_retry_max_tiers_reached"
                result.diagnostics["internal_max_tier_guard_fired"] = True
                _logger.debug(
                    "Retry: max_tier (%d) exhausted, terminal failure",
                    config.max_tier,
                )
                return _make_result()

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

            # Capture baseline retry_count *before* evaluate_once
            # so _normalize_retry_record can detect whether the returned
            # record advanced retry_count.
            prev_retry = current.retry_count

            try:
                next_record = evaluate_once(tier, current)
                attempt_record.status_after = str(next_record.status)
                current = next_record
            except Exception as exc:
                attempt_record.status_after = "evaluate_exception"
                attempt_record.error = str(exc)[:200]
                # Create a failure record so the loop can classify and stop.
                # Exception handler already advances retry_count by 1.
                current = EvaluationDatabaseRecord(
                    parameter_identity=current.parameter_identity,
                    status=EvaluationDatabaseStatus.UNKNOWN_FAILED,
                    retry_count=prev_retry + 1,
                    error_taxonomy={"evaluate_exception": str(exc)[:200]},
                )

            attempts_consumed += 1

            # Phase O1 normalisation: ensure retry_count reflects progress.
            # If evaluate_once returned a retryable failed record without
            # advancing retry_count, this forces advancement so the next
            # classification sees progress and the loop terminates at
            # max_tier rather than looping infinitely.
            current, norm_diag = _normalize_retry_record(
                current, prev_retry,
            )
            if norm_diag:
                attempt_record.diagnostics.update(norm_diag)
                result.diagnostics.setdefault("progress_guard_activations", []).append(
                    {
                        "attempt": attempt_record.attempt_index,
                        **norm_diag,
                    },
                )

            attempts.append(attempt_record)
            continue

        # Catch-all
        result.succeeded = False
        result.stopped_reason = f"unhandled_eligibility:{eligibility.action.value}"
        return _make_result()


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
