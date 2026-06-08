"""Synthetic skip row storage helper 鈥?SE2.

Inserts enforced-skip rows into a durable evaluation DB.  Validates
payloads, writes full audit diagnostics, and does not fabricate SUCCESS
metrics.  Designed for FS5 live enforce use.
"""

from __future__ import annotations

import json
import datetime
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from cst_optimization.evaluation.evaluation_database_schema import (
    current_schema_version,
)
from cst_optimization.evaluation.evaluation_database_skip_records import (
    SKIPPED_FAILURE_REUSE,
    SKIPPED_PROBABLY_INFEASIBLE,
    EvaluationSkipRecordPayload,
    build_skip_record_db_fields,
    validate_skip_record_payload,
)
from cst_optimization.evaluation.failure_skip_enforce import (
    FailureSkipEnforceDecision,
)


# ===================================================================
# Synthetic skip row writer
# ===================================================================


def write_failure_skip_synthetic_row(
    db_path: str | Path,
    payload: EvaluationSkipRecordPayload,
    *,
    param_names: Sequence[str] | None = None,
    param_values: Sequence[float] | None = None,
    run_id: str | None = None,
    created_at: str | None = None,
) -> int:
    """Write one synthetic skip row to the evaluation DB.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite evaluation database.
    payload : EvaluationSkipRecordPayload
        Validated skip payload.  Must pass ``validate_skip_record_payload()``.
    param_names : sequence of str or None
        Parameter names for the skipped point.
    param_values : sequence of float or None
        Parameter values for the skipped point.
    run_id : str or None
        Run identifier.
    created_at : str or None
        ISO-format timestamp.

    Returns
    -------
    int
        The row ID of the inserted record.

    Raises
    ------
    ValueError
        If payload validation fails.
    """
    if created_at is None:
        created_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Validate payload
    valid, reasons = validate_skip_record_payload(payload)
    if not valid:
        raise ValueError(
            f"Cannot write skip row: invalid payload: {', '.join(reasons)}",
        )

    # Build DB fields via mapper
    fields = build_skip_record_db_fields(payload)

    # Parameter identity
    pn = list(param_names) if param_names is not None else ["p0"]
    pv = [float(v) for v in param_values] if param_values is not None else [0.0]

    # Open DB
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            """
            INSERT INTO evaluation_records (
                schema_version, parameter_key, param_names, param_values,
                status, raw_metrics, objective_values, objective_names,
                source, diagnostics, error_taxonomy, provenance, run_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current_schema_version(),
                payload.parameter_key,
                json.dumps(pn),
                json.dumps(pv),
                payload.status,
                json.dumps(fields.get("raw_metrics")),
                json.dumps(fields.get("objective_values")),
                json.dumps(fields.get("objective_names", [])),
                "failure_skip_enforce",
                json.dumps(fields.get("diagnostics", {})),
                json.dumps(fields.get("error_taxonomy", {})),
                json.dumps(fields.get("provenance", {})),
                run_id,
                created_at,
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid or -1
    finally:
        conn.close()

    return row_id


# ===================================================================
# Decision-to-payload bridge
# ===================================================================


def build_skip_payload_from_enforce_decision(
    decision: FailureSkipEnforceDecision,
    *,
    skip_reason: str | None = None,
    status: str = SKIPPED_FAILURE_REUSE,
    operator_override_id: str | None = None,
    extra_json: Mapping[str, Any] | None = None,
) -> EvaluationSkipRecordPayload:
    """Build a skip payload from an enforce decision.

    Parameters
    ----------
    decision : FailureSkipEnforceDecision
        Must have ``enforce_skip=True``.
    skip_reason : str or None
        Override reason.  Defaults to decision.skip_reason.
    status : str
        ``"skipped_failure_reuse"`` or ``"skipped_probably_infeasible"``.
    operator_override_id : str or None
    extra_json : Mapping or None

    Returns
    -------
    EvaluationSkipRecordPayload

    Raises
    ------
    ValueError
        If decision does not enforce skip or lacks source rows.
    """
    if not decision.enforce_skip:
        raise ValueError(
            "Cannot build skip payload from non-enforce decision "
            f"(enforce_skip={decision.enforce_skip})",
        )
    if not decision.source_row_ids:
        raise ValueError(
            "Cannot build skip payload: enforce decision has no source_row_ids",
        )

    reason = skip_reason if skip_reason else (decision.skip_reason or "enforced skip")

    return EvaluationSkipRecordPayload(
        record_kind="skip",
        status=status,
        parameter_key=decision.parameter_key or "",
        skip_policy_version=decision.diagnostics.get("policy_version", 1)
            if isinstance(decision.diagnostics, dict) else 1,
        skip_mode=decision.mode,
        skip_decision="enforced_skip",
        skip_reason=reason,
        source_row_ids=decision.source_row_ids,
        source_run_ids=decision.source_run_ids,
        evidence_count=decision.evidence_count,
        evaluator_called=False,
        retry_called=False,
        budget_consumed=False,
        environment_fault_flag=False,
        operator_override_id=operator_override_id,
        extra_json=dict(extra_json) if extra_json else {},
    )

