# Retry taxonomy helpers for the RF gun SAO workflow.
# No-CST helper skeleton — no runtime wiring, no durable DB, no failure reuse.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from workflows.rfgun_sao.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    current_schema_version,
    is_schema_compatible,
)


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


class RetryFailureClass(str, Enum):
    """Taxonomy of failure outcomes for retry classification."""
    SUCCESS = "success"
    GATE_REJECTED = "gate_rejected"
    CALIBRATION_FAILED = "calibration_failed"
    SOLVER_FAILED = "solver_failed"
    TRANSIENT_FAILED = "transient_failed"
    UNKNOWN_FAILED = "unknown_failed"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    INCOMPATIBLE_SCHEMA = "incompatible_schema"
    MISSING_PARAMETER_IDENTITY = "missing_parameter_identity"
    UNSUPPORTED_STATUS = "unsupported_status"


class RetryEligibilityAction(str, Enum):
    """Recommended action based on retry eligibility."""
    NO_RETRY_SUCCESS = "no_retry_success"
    RETRY_ELIGIBLE = "retry_eligible"
    NO_RETRY_GATE_REJECTED = "no_retry_gate_rejected"
    NO_RETRY_DIAGNOSTIC_ONLY = "no_retry_diagnostic_only"
    NO_RETRY_INCOMPATIBLE_SCHEMA = "no_retry_incompatible_schema"
    NO_RETRY_MISSING_IDENTITY = "no_retry_missing_identity"
    NO_RETRY_MAX_TIERS_REACHED = "no_retry_max_tiers_reached"
    DEFER_PERMANENT_CLASSIFICATION = "defer_permanent_classification"


# ---------------------------------------------------------------------------
# Retry tier taxonomy
# ---------------------------------------------------------------------------


class RetryTier(int, Enum):
    """Retry escalation tiers.

    Descriptive taxonomy only — no CST or cleanup functions called.
    """
    NO_RETRY = 0
    TIER_1_RECONNECT = 1
    TIER_2_REBUILD = 2
    TIER_3_FORCE_CLOSE = 3

    @classmethod
    def from_int(cls, value: int) -> RetryTier:
        for tier in cls:
            if tier.value == value:
                return tier
        return cls.NO_RETRY


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Safe default retry policy.

    Defaults must not make a single failure permanently infeasible.
    """
    max_tier: int = 3
    allow_unknown_retry: bool = True
    allow_gate_retry: bool = False
    enable_permanent_infeasible: bool = False
    permanent_failure_threshold: int | None = None


# ---------------------------------------------------------------------------
# Retry classification result
# ---------------------------------------------------------------------------


@dataclass
class RetryClassification:
    """Result of classifying a record for retry eligibility.

    Parameters
    ----------
    failure_class : RetryFailureClass
        Classified failure type.
    action : RetryEligibilityAction
        Recommended action.
    next_tier : int
        Suggested next retry tier (0 if no retry).
    reason : str
        Human-readable justification.
    probably_infeasible : bool
        Whether the record is classified as probably infeasible.
        Default ``False``; never ``True`` under default policy.
    should_count_failure : bool
        Whether this record should increment the failure count.
    diagnostics : dict
        Extra information.
    """
    failure_class: RetryFailureClass = RetryFailureClass.UNSUPPORTED_STATUS
    action: RetryEligibilityAction = RetryEligibilityAction.DEFER_PERMANENT_CLASSIFICATION
    next_tier: int = 0
    reason: str = ""
    probably_infeasible: bool = False
    should_count_failure: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Diagnostic-only detection (compatible with L1 semantics)
# ---------------------------------------------------------------------------


def is_diagnostic_only_record(record: EvaluationDatabaseRecord) -> bool:
    """Check if a record is explicitly marked diagnostic-only."""
    if str(record.status).strip().lower() == "diagnostic_only":
        return True
    if record.error_taxonomy and isinstance(record.error_taxonomy, dict):
        if record.error_taxonomy.get("category") == "diagnostic_only":
            return True
    return False


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


def classify_failure_record(
    record: EvaluationDatabaseRecord,
    *,
    current_schema: int | None = None,
) -> RetryFailureClass:
    """Classify a single record's failure type.

    Precedence:
    1. Schema incompatible
    2. Missing parameter identity
    3. Diagnostic-only (explicit marker)
    4. Known status → corresponding failure class
    5. Unknown status → UNSUPPORTED_STATUS
    """
    if current_schema is None:
        current_schema = current_schema_version()

    if not is_schema_compatible(record.schema_version, current_schema):
        return RetryFailureClass.INCOMPATIBLE_SCHEMA

    pid = record.parameter_identity
    if pid is None:
        return RetryFailureClass.MISSING_PARAMETER_IDENTITY

    if is_diagnostic_only_record(record):
        return RetryFailureClass.DIAGNOSTIC_ONLY

    status_map = {
        EvaluationDatabaseStatus.SUCCESS: RetryFailureClass.SUCCESS,
        EvaluationDatabaseStatus.GATE_REJECTED: RetryFailureClass.GATE_REJECTED,
        EvaluationDatabaseStatus.CALIBRATION_FAILED: RetryFailureClass.CALIBRATION_FAILED,
        EvaluationDatabaseStatus.SOLVER_FAILED: RetryFailureClass.SOLVER_FAILED,
        EvaluationDatabaseStatus.TRANSIENT_FAILED: RetryFailureClass.TRANSIENT_FAILED,
        EvaluationDatabaseStatus.UNKNOWN_FAILED: RetryFailureClass.UNKNOWN_FAILED,
    }

    raw_status = str(record.status).strip().lower() if record.status else ""
    if raw_status in status_map:
        return status_map[raw_status]

    return RetryFailureClass.UNSUPPORTED_STATUS


# ---------------------------------------------------------------------------
# Retry eligibility
# --------------------------------------------------------------------------


def classify_retry_eligibility(
    record: EvaluationDatabaseRecord,
    *,
    policy: RetryPolicy | None = None,
    current_schema: int | None = None,
) -> RetryClassification:
    """Determine retry eligibility for a single record.

    Returns a ``RetryClassification`` with action, next tier, and
    diagnostics.  Never returns ``probably_infeasible=True`` under
    default policy.
    """
    if policy is None:
        policy = RetryPolicy()
    if current_schema is None:
        current_schema = current_schema_version()

    failure_class = classify_failure_record(
        record, current_schema=current_schema,
    )

    diag: dict[str, Any] = {
        "failure_class": failure_class.value,
        "retry_count": record.retry_count,
        "max_tier": policy.max_tier,
    }

    # Handle non-retryable classes
    if failure_class == RetryFailureClass.SUCCESS:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.NO_RETRY_SUCCESS,
            reason="Record is SUCCESS; no retry needed.",
            should_count_failure=False,
            diagnostics=diag,
        )

    if failure_class == RetryFailureClass.GATE_REJECTED:
        # Gate rejection is not a solver failure
        if not policy.allow_gate_retry:
            return RetryClassification(
                failure_class=failure_class,
                action=RetryEligibilityAction.NO_RETRY_GATE_REJECTED,
                reason="Gate rejection is not a solver failure; no auto retry.",
                should_count_failure=True,
                diagnostics=diag,
            )
        # Fall through to retry eligible if policy allows (default False)

    if failure_class == RetryFailureClass.DIAGNOSTIC_ONLY:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.NO_RETRY_DIAGNOSTIC_ONLY,
            reason="Diagnostic-only records are not retry sources.",
            should_count_failure=False,
            diagnostics=diag,
        )

    if failure_class == RetryFailureClass.INCOMPATIBLE_SCHEMA:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.NO_RETRY_INCOMPATIBLE_SCHEMA,
            reason="Incompatible schema; cannot determine retry eligibility.",
            should_count_failure=False,
            diagnostics=diag,
        )

    if failure_class == RetryFailureClass.MISSING_PARAMETER_IDENTITY:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.NO_RETRY_MISSING_IDENTITY,
            reason="Missing parameter identity; cannot retry.",
            should_count_failure=False,
            diagnostics=diag,
        )

    if failure_class == RetryFailureClass.UNSUPPORTED_STATUS:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.DEFER_PERMANENT_CLASSIFICATION,
            reason="Unsupported status; deferring classification.",
            should_count_failure=True,
            diagnostics=diag,
        )

    # Retry-eligible classes: calibration, solver, transient, unknown
    already_retried = record.retry_count

    if failure_class == RetryFailureClass.UNKNOWN_FAILED and not policy.allow_unknown_retry:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.DEFER_PERMANENT_CLASSIFICATION,
            reason="Unknown failure and policy disallows unknown retry.",
            should_count_failure=True,
            diagnostics=diag,
        )

    if already_retried >= policy.max_tier:
        return RetryClassification(
            failure_class=failure_class,
            action=RetryEligibilityAction.NO_RETRY_MAX_TIERS_REACHED,
            reason=f"Max retry tier ({policy.max_tier}) reached; not permanent.",
            next_tier=0,
            probably_infeasible=False,
            should_count_failure=True,
            diagnostics=diag,
        )

    next_tier = min(already_retried + 1, policy.max_tier)
    return RetryClassification(
        failure_class=failure_class,
        action=RetryEligibilityAction.RETRY_ELIGIBLE,
        next_tier=next_tier,
        reason=f"Retry eligible at tier {next_tier}.",
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Tier suggestion
# ---------------------------------------------------------------------------


def suggest_next_retry_tier(
    record: EvaluationDatabaseRecord,
    *,
    policy: RetryPolicy | None = None,
) -> int | None:
    """Suggest the next retry tier for a record.

    Returns ``None`` if the record is not retry-eligible.
    """
    classification = classify_retry_eligibility(record, policy=policy)
    if classification.action != RetryEligibilityAction.RETRY_ELIGIBLE:
        return None
    return classification.next_tier


# ---------------------------------------------------------------------------
# Probably-infeasible guard (conservative)
# ---------------------------------------------------------------------------


def _record_parameter_key(record: EvaluationDatabaseRecord) -> str | None:
    """Extract the parameter key from a record, or ``None`` if unavailable."""
    pid = record.parameter_identity
    if pid is None:
        return None
    return pid.parameter_key()


def _is_stable_permanent_candidate_class(
    failure_class: RetryFailureClass,
    policy: RetryPolicy,
) -> bool:
    """Check if a failure class can contribute to permanent infeasibility
    classification.

    Only non-transient, non-diagnostic, structurally valid failure classes
    are allowed to escalate.
    """
    allowed = {
        RetryFailureClass.CALIBRATION_FAILED,
        RetryFailureClass.SOLVER_FAILED,
    }
    if policy.allow_unknown_retry:
        allowed.add(RetryFailureClass.UNKNOWN_FAILED)

    return failure_class in allowed


def should_escalate_to_probably_infeasible(
    failure_history: list[EvaluationDatabaseRecord],
    *,
    policy: RetryPolicy | None = None,
) -> bool:
    """Check if a failure history qualifies for permanent infeasibility
    classification.

    Conservative guard — returns ``False`` for most inputs.

    Requirements for ``True``:
    1. Policy must explicitly enable permanent classification
       (``enable_permanent_infeasible=True``).
    2. ``permanent_failure_threshold`` must be set and at least 2.
    3. All records must have:
       - compatible schema
       - non-missing parameter identity
       - same parameter key
    4. All records must classify as a stable permanent candidate class
       (``CALIBRATION_FAILED``, ``SOLVER_FAILED``, or ``UNKNOWN_FAILED``
       only if ``allow_unknown_retry=True``).
    5. History length must meet or exceed the threshold.

    Any record classified as ``TRANSIENT_FAILED``, ``GATE_REJECTED``,
    ``SUCCESS``, ``DIAGNOSTIC_ONLY``, ``INCOMPATIBLE_SCHEMA``,
    ``MISSING_PARAMETER_IDENTITY``, or ``UNSUPPORTED_STATUS`` forces
    a ``False`` return.
    """
    if policy is None:
        policy = RetryPolicy()

    if not policy.enable_permanent_infeasible:
        return False

    if policy.permanent_failure_threshold is None:
        return False

    threshold = max(int(policy.permanent_failure_threshold), 2)

    if len(failure_history) < threshold:
        return False

    # Track parameter key consistency
    first_key: str | None = None
    for rec in failure_history:
        # Schema compatibility
        fc = classify_failure_record(rec)
        if fc in (
            RetryFailureClass.INCOMPATIBLE_SCHEMA,
            RetryFailureClass.MISSING_PARAMETER_IDENTITY,
            RetryFailureClass.DIAGNOSTIC_ONLY,
            RetryFailureClass.UNSUPPORTED_STATUS,
        ):
            return False

        # Parameter identity consistency
        key = _record_parameter_key(rec)
        if key is None:
            return False
        if first_key is None:
            first_key = key
        elif key != first_key:
            return False

        # Stable permanent candidate class check
        if not _is_stable_permanent_candidate_class(fc, policy):
            return False

    return True


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------


def summarize_retry_classifications(
    records: list[EvaluationDatabaseRecord],
    *,
    policy: RetryPolicy | None = None,
) -> dict[str, int]:
    """Summarise retry classifications by action type.

    Returns a dict mapping action value → count.  No I/O.
    """
    counts: dict[str, int] = {}
    for rec in records:
        cl = classify_retry_eligibility(rec, policy=policy)
        key = cl.action.value
        counts[key] = counts.get(key, 0) + 1
    return counts
