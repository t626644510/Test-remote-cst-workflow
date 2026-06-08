# Evaluation database dedup helpers (in-memory skeleton, no durable I/O).
# Independent from the Phase C diagnostic sidecar.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
    is_schema_compatible,
)


# ---------------------------------------------------------------------------
# Dedup decision taxonomy
# ---------------------------------------------------------------------------


class DedupDecisionAction(str, Enum):
    """Possible outcomes of a dedup query."""
    USE_EXISTING_SUCCESS = "use_existing_success"
    EVALUATE_NEW = "evaluate_new"
    IGNORE_INCOMPATIBLE_SCHEMA = "ignore_incompatible_schema"
    IGNORE_MISSING_PARAMETER_IDENTITY = "ignore_missing_parameter_identity"
    IGNORE_FAILURE_RETRY_POLICY_MISSING = "ignore_failure_retry_policy_missing"
    IGNORE_DIAGNOSTIC_ONLY = "ignore_diagnostic_only"


@dataclass
class DedupDecision:
    """Result of a dedup evaluation.

    Parameters
    ----------
    action : DedupDecisionAction
        Recommended action.
    reason : str
        Human-readable justification.
    parameter_key : str or None
        Parameter identity key used for lookup.
    matched_record : EvaluationDatabaseRecord or None
        The matched record, if ``action`` is ``USE_EXISTING_SUCCESS``.
    diagnostics : dict
        Extra information (matched status, provenance, count of records).
    """
    action: DedupDecisionAction = DedupDecisionAction.EVALUATE_NEW
    reason: str = ""
    parameter_key: str | None = None
    matched_record: EvaluationDatabaseRecord | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-memory index
# ---------------------------------------------------------------------------


@dataclass
class InMemoryEvaluationRecordIndex:
    """In-memory index keyed by ``ParameterIdentity.parameter_key()``.

    Built from a list of ``EvaluationDatabaseRecord`` objects.  No file or
    database I/O.  Records with missing parameter identity or incompatible
    schema version are stored in ``ignored_records`` with diagnostics.
    """
    records_by_key: dict[str, list[EvaluationDatabaseRecord]] = field(
        default_factory=dict,
    )
    ignored_records: list[dict[str, Any]] = field(default_factory=list)


def build_in_memory_index(
    records: list[EvaluationDatabaseRecord],
    current_schema: int | None = None,
) -> InMemoryEvaluationRecordIndex:
    """Build an index from *records*.

    Records with missing parameter identity or incompatible schema version
    are not indexed; they are recorded in ``ignored_records`` with
    diagnostics.
    """
    if current_schema is None:
        from cst_optimization.evaluation.evaluation_database_schema import (
            current_schema_version,
        )
        current_schema = current_schema_version()

    index = InMemoryEvaluationRecordIndex()

    for rec in records:
        diag: dict[str, Any] = {"reason": None}

        # Check schema version
        if not is_schema_compatible(rec.schema_version, current_schema):
            diag["reason"] = "incompatible_schema"
            diag["schema_version"] = rec.schema_version
            index.ignored_records.append(diag)
            continue

        # Check parameter identity
        pid = rec.parameter_identity
        if pid is None:
            diag["reason"] = "missing_parameter_identity"
            index.ignored_records.append(diag)
            continue

        key = pid.parameter_key()
        diag["parameter_key"] = key
        if key not in index.records_by_key:
            index.records_by_key[key] = []
        index.records_by_key[key].append(rec)

    return index


# ---------------------------------------------------------------------------
# Record classification
# ---------------------------------------------------------------------------


def classify_record_for_dedup(
    record: EvaluationDatabaseRecord,
    *,
    current_schema: int | None = None,
) -> DedupDecision:
    """Classify a single record for dedup eligibility.

    Returns a ``DedupDecision`` suitable for the *record* in isolation.
    Does **not** query an index.
    """
    if current_schema is None:
        from cst_optimization.evaluation.evaluation_database_schema import (
            current_schema_version,
        )
        current_schema = current_schema_version()

    diag: dict[str, Any] = {
        "record_status": record.status,
        "record_schema": record.schema_version,
    }

    if not is_schema_compatible(record.schema_version, current_schema):
        return DedupDecision(
            action=DedupDecisionAction.IGNORE_INCOMPATIBLE_SCHEMA,
            reason=f"Schema version {record.schema_version} incompatible.",
            diagnostics=diag,
        )

    if record.parameter_identity is None:
        return DedupDecision(
            action=DedupDecisionAction.IGNORE_MISSING_PARAMETER_IDENTITY,
            reason="Record has no parameter identity.",
            diagnostics=diag,
        )

    if record.status == EvaluationDatabaseStatus.SUCCESS:
        key = record.parameter_identity.parameter_key()
        return DedupDecision(
            action=DedupDecisionAction.USE_EXISTING_SUCCESS,
            reason="Success record with compatible schema and identity.",
            parameter_key=key,
            matched_record=record,
            diagnostics=diag,
        )

    if record.status in (
        EvaluationDatabaseStatus.GATE_REJECTED,
        EvaluationDatabaseStatus.CALIBRATION_FAILED,
        EvaluationDatabaseStatus.SOLVER_FAILED,
        EvaluationDatabaseStatus.TRANSIENT_FAILED,
        EvaluationDatabaseStatus.UNKNOWN_FAILED,
    ):
        return DedupDecision(
            action=DedupDecisionAction.IGNORE_FAILURE_RETRY_POLICY_MISSING,
            reason=f"Failure ({record.status}) cannot be reused without retry taxonomy.",
            parameter_key=record.parameter_identity.parameter_key(),
            diagnostics=diag,
        )

    return DedupDecision(
        action=DedupDecisionAction.IGNORE_DIAGNOSTIC_ONLY,
        reason=f"Unrecognised status {record.status}.",
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Dedup query
# ---------------------------------------------------------------------------


def find_records_by_parameter_identity(
    index: InMemoryEvaluationRecordIndex,
    pid: ParameterIdentity,
) -> list[EvaluationDatabaseRecord]:
    """Find records matching *pid* in the index.

    *pid* must not be ``None`` 鈥?callers must check before calling.
    Returns an empty list if no match.
    """
    key = pid.parameter_key()
    return index.records_by_key.get(key, [])


def decide_dedup_for_parameter(
    pid: ParameterIdentity | None,
    index: InMemoryEvaluationRecordIndex,
    *,
    allow_failure_reuse: bool = False,
) -> DedupDecision:
    """Decide whether a new evaluation for *pid* can be skipped.

    *allow_failure_reuse* defaults to ``False`` and must remain
    no-op in Phase K (returns ``IGNORE_FAILURE_RETRY_POLICY_MISSING``).

    Returns
    -------
    DedupDecision
    """
    diag: dict[str, Any] = {}

    if pid is None:
        return DedupDecision(
            action=DedupDecisionAction.IGNORE_MISSING_PARAMETER_IDENTITY,
            reason="No parameter identity provided.",
            diagnostics=diag,
        )

    key = pid.parameter_key()
    diag["parameter_key"] = key

    matches = find_records_by_parameter_identity(index, pid)
    if not matches:
        return DedupDecision(
            action=DedupDecisionAction.EVALUATE_NEW,
            reason="No existing record for this parameter key.",
            parameter_key=key,
            diagnostics=diag,
        )

    # Prefer success records
    successes = [
        r for r in matches
        if r.status == EvaluationDatabaseStatus.SUCCESS
    ]
    if successes:
        chosen = successes[0]
        diag["matched_count"] = len(successes)
        diag["matched_status"] = chosen.status
        diag["provenance"] = chosen.provenance

        return DedupDecision(
            action=DedupDecisionAction.USE_EXISTING_SUCCESS,
            reason=f"Found {len(successes)} success record(s) for this parameter.",
            parameter_key=key,
            matched_record=chosen,
            diagnostics=diag,
        )

    if allow_failure_reuse:
        # Phase K: not implemented, always falls through to evaluate_new
        pass

    return DedupDecision(
        action=DedupDecisionAction.IGNORE_FAILURE_RETRY_POLICY_MISSING,
        reason="No success records; failure reuse not available.",
        parameter_key=key,
        diagnostics=diag,
    )

