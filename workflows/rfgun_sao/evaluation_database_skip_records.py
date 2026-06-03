"""Schema extension hooks for failure skip records — SE1.

Extends the v1 evaluation DB schema with skip-specific statuses,
payload model, and compatibility helpers — without modifying the
v1 ``EvaluationDatabaseStatus.validate()`` closed set.

Skip statuses defined here are **not** accepted by v1 validation.
A production migration (SE2) is required before synthetic skip rows
can be inserted into a durable SQLite DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# ===================================================================
# Extended status constants
# ===================================================================

# These statuses extend the v1 closed set.  They are NOT accepted by
# EvaluationDatabaseStatus.validate() until a schema migration adds
# them to _VALID_STATUSES or replaces the validation function.

SKIPPED_FAILURE_REUSE = "skipped_failure_reuse"
SKIPPED_PROBABLY_INFEASIBLE = "skipped_probably_infeasible"

_EXTENSION_STATUSES = frozenset({
    SKIPPED_FAILURE_REUSE,
    SKIPPED_PROBABLY_INFEASIBLE,
})

# v1 canonical success status
_V1_SUCCESS = "success"


# ===================================================================
# Status helpers
# ===================================================================


def is_extended_evaluation_status(status: str) -> bool:
    """Return True if *status* is an SE1 extension status.

    Does not check v1 statuses.
    """
    return status in _EXTENSION_STATUSES


def is_skip_status(status: str) -> bool:
    """Return True if *status* represents a synthetic skipped evaluation."""
    return status in _EXTENSION_STATUSES


def is_success_status(status: str) -> bool:
    """Return True if *status* represents a successful evaluation.

    Only ``"success"`` is success for v1 + SE1.
    """
    return status == _V1_SUCCESS


def is_reusable_success_status(status: str) -> bool:
    """Return True if *status* is eligible for DB success reuse or warm-start.

    Only ``"success"`` is reusable.  Extended skip statuses are never reusable.
    """
    return status == _V1_SUCCESS


def is_failure_skip_evidence_source_status(status: str) -> bool:
    """Return True if *status* could be considered skip evidence.

    Success and skip statuses are excluded from evidence.
    """
    if status == _V1_SUCCESS:
        return False
    if status in _EXTENSION_STATUSES:
        return False
    return True


# ===================================================================
# Skip record payload
# ===================================================================


@dataclass(frozen=True)
class EvaluationSkipRecordPayload:
    """Structured payload for a synthetic skip row.

    Parameters
    ----------
    record_kind : str
        ``"skip"``.
    status : str
        ``"skipped_failure_reuse"`` or ``"skipped_probably_infeasible"``.
    parameter_key : str
    skip_policy_version : int
    skip_mode : str
        ``"enforce"``.
    skip_decision : str
        ``"enforced_skip"``.
    skip_reason : str
    source_row_ids : tuple of int
    source_run_ids : tuple of str
    evidence_count : int
    evaluator_called : bool
        ``False`` for enforce skip.
    retry_called : bool
        ``False`` for enforce skip.
    budget_consumed : bool
        ``False`` for enforce skip.
    failure_taxonomy_version : int or None
    environment_fault_flag : bool
        Should be ``False`` for accepted enforce skip.
    operator_override_id : str or None
    extra_json : Mapping
    """
    record_kind: str = "skip"
    status: str = SKIPPED_FAILURE_REUSE
    parameter_key: str = ""
    skip_policy_version: int = 1
    skip_mode: str = "enforce"
    skip_decision: str = "enforced_skip"
    skip_reason: str = ""
    source_row_ids: tuple[int, ...] = ()
    source_run_ids: tuple[str, ...] = ()
    evidence_count: int = 0
    evaluator_called: bool = False
    retry_called: bool = False
    budget_consumed: bool = False
    failure_taxonomy_version: int | None = None
    environment_fault_flag: bool = False
    operator_override_id: str | None = None
    extra_json: Mapping[str, Any] = field(default_factory=dict)


def validate_skip_record_payload(
    payload: EvaluationSkipRecordPayload,
) -> tuple[bool, tuple[str, ...]]:
    """Validate an ``EvaluationSkipRecordPayload`` for consistency.

    Returns ``(valid, reasons)``.
    """
    reasons: list[str] = []

    if payload.record_kind != "skip":
        reasons.append("record_kind_must_be_skip")

    if payload.status not in _EXTENSION_STATUSES:
        reasons.append(f"invalid_skip_status: {payload.status!r}")

    if not payload.parameter_key:
        reasons.append("parameter_key_required")

    if not payload.skip_reason or not payload.skip_reason.strip():
        reasons.append("skip_reason_required")

    if payload.evidence_count <= 0:
        reasons.append("evidence_count_required_for_enforce_skip")

    if payload.source_row_ids and payload.evidence_count != len(payload.source_row_ids):
        reasons.append("evidence_count_source_row_ids_mismatch")

    if not payload.source_row_ids and payload.skip_decision == "enforced_skip":
        reasons.append("source_row_ids_required_for_enforce_skip")

    if payload.environment_fault_flag:
        reasons.append("environment_fault_flag_should_be_false_for_enforce_skip")

    if payload.evaluator_called:
        reasons.append("evaluator_called_must_be_false_for_enforce_skip")

    if payload.retry_called:
        reasons.append("retry_called_must_be_false_for_enforce_skip")

    if payload.budget_consumed:
        reasons.append("budget_consumed_must_be_false_for_enforce_skip")

    if payload.skip_decision != "enforced_skip":
        reasons.append("skip_decision_must_be_enforced_skip")

    if payload.skip_policy_version <= 0:
        reasons.append("skip_policy_version_must_be_positive")

    if payload.skip_mode not in ("enforce",):
        reasons.append(f"skip_mode_must_be_enforce_got_{payload.skip_mode!r}")

    return (len(reasons) == 0, tuple(reasons))


# ===================================================================
# DB field mapping adapter
# ===================================================================


def build_skip_record_db_fields(
    payload: EvaluationSkipRecordPayload,
) -> dict[str, Any]:
    """Map an ``EvaluationSkipRecordPayload`` to v1-compatible DB fields.

    The returned dict can be used as a row-like mapping for diagnostics,
    testing, or future DB insertion after schema migration.

    Parameters
    ----------
    payload : EvaluationSkipRecordPayload

    Returns
    -------
    dict
        Fields matching the evaluation_records table schema.

    Raises
    ------
    ValueError
        If payload validation fails.
    """
    valid, reasons = validate_skip_record_payload(payload)
    if not valid:
        raise ValueError(
            f"Cannot build DB fields from invalid payload: {', '.join(reasons)}",
        )
    return {
        "id": None,
        "schema_version": 1,
        "parameter_key": payload.parameter_key,
        "status": payload.status,
        "source": "failure_skip_enforce",
        "raw_metrics": None,
        "objective_values": None,
        "objective_names": list(payload.extra_json.get("objective_names", [])),
        "diagnostics": {
            "record_kind": payload.record_kind,
            "skip_policy_version": payload.skip_policy_version,
            "skip_mode": payload.skip_mode,
            "skip_decision": payload.skip_decision,
            "skip_reason": payload.skip_reason,
            "source_row_ids": list(payload.source_row_ids),
            "source_run_ids": list(payload.source_run_ids),
            "evidence_count": payload.evidence_count,
            "evaluator_called": payload.evaluator_called,
            "retry_called": payload.retry_called,
            "budget_consumed": payload.budget_consumed,
            "synthetic_status": payload.status,
        },
        "error_taxonomy": {
            "failure_taxonomy_version": payload.failure_taxonomy_version,
            "environment_fault_flag": payload.environment_fault_flag,
        },
        "provenance": {
            "operator_override_id": payload.operator_override_id,
            "extra": dict(payload.extra_json),
        },
        "retry_count": 0,
        "run_id": payload.extra_json.get("run_id"),
        "created_at": payload.extra_json.get("created_at"),
    }


# ===================================================================
# Schema capability helper
# ===================================================================


@dataclass(frozen=True)
class EvaluationDatabaseSchemaCapabilities:
    """Capabilities of a given schema version for skip recording.

    Parameters
    ----------
    schema_version : int
    supports_skip_statuses : bool
        Whether the schema's validation accepts skip statuses.
    supports_skip_audit_fields : bool
        Whether diagnostics/error_taxonomy fields are available.
    supports_extra_json : bool
        Whether provenance or extra JSON is available.
    requires_migration_for_skip_rows : bool
        True if storage validation rejects skip statuses.
    """
    schema_version: int = 1
    supports_skip_statuses: bool = False
    supports_skip_audit_fields: bool = True
    supports_extra_json: bool = True
    requires_migration_for_skip_rows: bool = True


def get_schema_capabilities(schema_version: int) -> EvaluationDatabaseSchemaCapabilities:
    """Return the capabilities for a given *schema_version*.

    Currently only v1 is defined.  Future versions can override.
    """
    if schema_version == 1:
        return EvaluationDatabaseSchemaCapabilities(
            schema_version=1,
            # v1 validate() rejects unknown statuses
            supports_skip_statuses=False,
            # diagnostics and error_taxonomy fields exist in v1
            supports_skip_audit_fields=True,
            # provenance field exists in v1
            supports_extra_json=True,
            # storage's validate_evaluation_record calls validate() -> rejects
            requires_migration_for_skip_rows=True,
        )
    # Unknown version — conservative
    return EvaluationDatabaseSchemaCapabilities(
        schema_version=schema_version,
        supports_skip_statuses=False,
        supports_skip_audit_fields=False,
        supports_extra_json=False,
        requires_migration_for_skip_rows=True,
    )
