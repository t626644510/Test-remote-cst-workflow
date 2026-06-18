# Evaluation database schema for the RF gun SAO workflow.
# Schema/design only — no durable storage, no dedup, no warm-start.
# Independent from the Phase C JSONL diagnostic sidecar.

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

_SCHEMA_VERSION: int = 1


def current_schema_version() -> int:
    """Return the current evaluation database schema version."""
    return _SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Evaluation status
# ---------------------------------------------------------------------------


class EvaluationDatabaseStatus(str):
    """Classification of an evaluation record's outcome.

    Future phases may extend this taxonomy; this phase provides a
    minimal stable set for schema validation.
    """
    SUCCESS = "success"
    GATE_REJECTED = "gate_rejected"
    CALIBRATION_FAILED = "calibration_failed"
    SOLVER_FAILED = "solver_failed"
    TRANSIENT_FAILED = "transient_failed"
    UNKNOWN_FAILED = "unknown_failed"

    _VALID_STATUSES = frozenset({
        SUCCESS, GATE_REJECTED, CALIBRATION_FAILED,
        SOLVER_FAILED, TRANSIENT_FAILED, UNKNOWN_FAILED,
        "skipped_failure_reuse", "skipped_probably_infeasible",
    })

    @classmethod
    def validate(cls, status: str) -> str:
        if status not in cls._VALID_STATUSES:
            raise ValueError(f"Unknown evaluation status: {status!r}")
        return status


# ---------------------------------------------------------------------------
# Schema compatibility
# ---------------------------------------------------------------------------


def is_schema_compatible(
    record_version: int,
    current_version: int | None = None,
) -> bool:
    """Check if a stored record's schema version is compatible.

    Currently requires exact match (``record_version == current_version``).
    """
    if current_version is None:
        current_version = _SCHEMA_VERSION
    return record_version == current_version


# ---------------------------------------------------------------------------
# Parameter identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterIdentity:
    """Ordered parameter name/value pairs forming a unique identity key.

    Parameters
    ----------
    param_names : list[str]
        Ordered parameter names.
    values : list[float]
        Ordered parameter values, same length as *param_names*.
    precision : int or None
        Decimal places for rounding when computing the deterministic key.
        ``None`` means full float precision is used.
    """
    param_names: list[str]
    values: list[float]
    precision: int | None = None

    def __post_init__(self) -> None:
        if len(self.param_names) != len(self.values):
            raise ValueError(
                f"param_names ({len(self.param_names)}) and values "
                f"({len(self.values)}) length mismatch",
            )

    def parameter_key(self) -> str:
        """Deterministic key for dedup/identity comparison.

        Includes rounded values (if *precision* is set) and ordered names.
        """
        parts: list[str] = []
        for name, val in zip(self.param_names, self.values):
            if self.precision is not None:
                rounded = round(val, self.precision)
                parts.append(f"{name}={rounded}")
            else:
                parts.append(f"{name}={val:.16g}")
        raw = ";".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "param_names": list(self.param_names),
            "values": [float(v) for v in self.values],
            "precision": self.precision,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParameterIdentity:
        return cls(
            param_names=list(d["param_names"]),
            values=[float(v) for v in d["values"]],
            precision=d.get("precision"),
        )


# ---------------------------------------------------------------------------
# Raw evaluation payload
# ---------------------------------------------------------------------------


@dataclass
class RawEvaluationPayload:
    """Computed raw data from a single evaluation.

    Parameters
    ----------
    raw_metrics : dict[str, float] or None
        Raw physics values keyed by metric name.
    objective_values : dict[str, float] or None
        Computed objective values keyed by metric name.
    gate_results : dict[str, bool] or None
        Gate pass/fail results keyed by output name.
    diagnostics : dict[str, Any] or None
        Report-only / diagnostics-shaped metadata.
        This schema does **not** read the Phase C JSONL diagnostic sidecar.
    artifact_refs : dict[str, str] or None
        References to external artifacts (paths, file names).
        String-only — no artifact writes.
    """
    raw_metrics: dict[str, float] | None = None
    objective_values: dict[str, float] | None = None
    gate_results: dict[str, bool] | None = None
    diagnostics: dict[str, Any] | None = None
    artifact_refs: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Reuse eligibility
# ---------------------------------------------------------------------------


class ReuseEligibility(str):
    """Future eligibility classification (design-only, not implemented).

    Categories:
    - ``ELIGIBLE_SUCCESS_RAW_REDERIVE``: success with finite raw metrics;
      raw data could re-derive current metrics/gates if schema changes.
    - ``INELIGIBLE_FAILURE_RETRY_POLICY_MISSING``: failure without explicit
      retry taxonomy; reuse deferred until Phase M+.
    - ``DIAGNOSTIC_ONLY``: record kept for diagnostic/historical reference
      only; not suitable for warm-start or dedup.
    """
    ELIGIBLE_SUCCESS_RAW_REDERIVE = "eligible_success_raw_rederive"
    INELIGIBLE_FAILURE_RETRY_POLICY_MISSING = "ineligible_failure_retry_policy_missing"
    DIAGNOSTIC_ONLY = "diagnostic_only"


# ---------------------------------------------------------------------------
# Evaluation database record
# ---------------------------------------------------------------------------


@dataclass
class EvaluationDatabaseRecord:
    """One evaluation record for the database.

    Parameters
    ----------
    schema_version : int
        Schema version for forward-compatibility.
    parameter_identity : ParameterIdentity
        Parameter vector identity.
    status : EvaluationDatabaseStatus
        Outcome classification.
    raw_payload : RawEvaluationPayload or None
        Computed raw data.
    objective_names : list[str] or None
        Objective metric names snapshot.
    source : str or None
        Source identifier (e.g. ``"rfgun_sao.run"``).
    provenance : dict or None
        Metadata (git commit, config fingerprint, CST version, hostname).
    retry_count : int
        Number of retry attempts consumed (placeholder for future use).
    error_taxonomy : dict or None
        Future error taxonomy classification (placeholder).
    """
    schema_version: int = _SCHEMA_VERSION
    parameter_identity: ParameterIdentity | None = None
    status: str = EvaluationDatabaseStatus.UNKNOWN_FAILED
    raw_payload: RawEvaluationPayload | None = None
    objective_names: list[str] | None = None
    source: str | None = None
    provenance: dict[str, Any] | None = None
    retry_count: int = 0
    error_taxonomy: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_parameter_identity(
    param_names: list[str],
    values: list[float],
    *,
    precision: int | None = None,
) -> ParameterIdentity:
    """Validate and construct a ``ParameterIdentity``.

    Returns the identity object on success.
    Raises ``ValueError`` on length mismatch or missing names/values.
    """
    if not param_names:
        raise ValueError("param_names must not be empty")
    if not values:
        raise ValueError("values must not be empty")
    if len(param_names) != len(values):
        raise ValueError(
            f"param_names ({len(param_names)}) and values "
            f"({len(values)}) length mismatch",
        )
    return ParameterIdentity(
        param_names=list(param_names),
        values=[float(v) for v in values],
        precision=precision,
    )


def validate_evaluation_record(record: EvaluationDatabaseRecord) -> None:
    """Validate an evaluation record's fields.

    Raises ``ValueError`` on invalid fields.
    """
    EvaluationDatabaseStatus.validate(record.status)
    if record.parameter_identity is not None:
        _ = validate_parameter_identity(
            record.parameter_identity.param_names,
            record.parameter_identity.values,
            precision=record.parameter_identity.precision,
        )


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def _make_json_safe(value: object) -> object:
    """Convert a value to a JSON-safe Python object."""
    if isinstance(value, (bool, int, float, str, type(None))):
        if isinstance(value, float) and (value != value or value == float("inf") or value == -float("inf")):
            return None
        return value
    if isinstance(value, np.generic):
        return _make_json_safe(value.item())
    if isinstance(value, dict):
        return {str(k): _make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_safe(v) for v in value]
    return str(value)


def record_to_json_dict(record: EvaluationDatabaseRecord) -> dict[str, Any]:
    """Convert an ``EvaluationDatabaseRecord`` to a JSON-safe dict.

    No file writes.  The output can be serialised with ``json.dumps``.
    """
    param = record.parameter_identity
    payload = record.raw_payload
    return _make_json_safe({
        "schema_version": record.schema_version,
        "parameter_identity": param.to_dict() if param is not None else None,
        "status": record.status,
        "raw_payload": {
            "raw_metrics": payload.raw_metrics if payload else None,
            "objective_values": payload.objective_values if payload else None,
            "gate_results": payload.gate_results if payload else None,
            "diagnostics": payload.diagnostics if payload else None,
            "artifact_refs": payload.artifact_refs if payload else None,
        } if payload else None,
        "objective_names": record.objective_names,
        "source": record.source,
        "provenance": record.provenance,
        "retry_count": record.retry_count,
        "error_taxonomy": record.error_taxonomy,
    })


def record_from_json_dict(d: dict[str, Any]) -> EvaluationDatabaseRecord:
    """Reconstruct an ``EvaluationDatabaseRecord`` from a JSON-safe dict.

    No file reads.  Input must be the output of ``record_to_json_dict``.
    """
    param = None
    pid = d.get("parameter_identity")
    if pid is not None and pid.get("param_names"):
        param = ParameterIdentity.from_dict(pid)

    payload = None
    rp = d.get("raw_payload")
    if rp is not None:
        payload = RawEvaluationPayload(
            raw_metrics=rp.get("raw_metrics"),
            objective_values=rp.get("objective_values"),
            gate_results=rp.get("gate_results"),
            diagnostics=rp.get("diagnostics"),
            artifact_refs=rp.get("artifact_refs"),
        )

    return EvaluationDatabaseRecord(
        schema_version=d.get("schema_version", _SCHEMA_VERSION),
        parameter_identity=param,
        status=d.get("status", EvaluationDatabaseStatus.UNKNOWN_FAILED),
        raw_payload=payload,
        objective_names=d.get("objective_names"),
        source=d.get("source"),
        provenance=d.get("provenance"),
        retry_count=d.get("retry_count", 0),
        error_taxonomy=d.get("error_taxonomy"),
    )


# ---------------------------------------------------------------------------
# DDL (design-only, not executed)
# ---------------------------------------------------------------------------


def schema_ddl_sqlite() -> str:
    """Return a DDL string suitable for creating the evaluation database.

    Includes schema version tracking table.  The ``schema_version`` table
    is created first so that ``_initialize_schema`` can insert the
    initial version row.
    """
    return """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evaluation_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    parameter_key TEXT NOT NULL,
    param_names TEXT NOT NULL,
    param_values TEXT NOT NULL,
    param_precision INTEGER,
    status TEXT NOT NULL,
    raw_metrics TEXT,
    objective_values TEXT,
    gate_results TEXT,
    diagnostics TEXT,
    artifact_refs TEXT,
    objective_names TEXT,
    source TEXT,
    provenance TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_taxonomy TEXT,
    run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_parameter_key ON evaluation_records(parameter_key);
CREATE INDEX IF NOT EXISTS idx_status ON evaluation_records(status);
CREATE INDEX IF NOT EXISTS idx_run_id ON evaluation_records(run_id);
"""
