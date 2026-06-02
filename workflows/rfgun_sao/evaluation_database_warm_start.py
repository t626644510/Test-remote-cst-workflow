# Evaluation database warm-start / prior construction helpers (in-memory skeleton).
# No durable I/O, no optimizer injection, no CST dependency.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from workflows.rfgun_sao.evaluation_database_dedup import (
    DedupDecisionAction,
    InMemoryEvaluationRecordIndex,
    build_in_memory_index,
)
from workflows.rfgun_sao.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
    is_schema_compatible,
)
from workflows.rfgun_sao.stage_search import (
    StageCandidateStatus,
    StageObservation,
)


# ---------------------------------------------------------------------------
# Prior candidate taxonomy
# ---------------------------------------------------------------------------


class PriorCandidateStatus(str, Enum):
    """Classification of a record's eligibility for prior construction."""
    USABLE_SUCCESS = "usable_success"
    IGNORED_FAILURE = "ignored_failure"
    IGNORED_MISSING_IDENTITY = "ignored_missing_identity"
    IGNORED_INCOMPATIBLE_SCHEMA = "ignored_incompatible_schema"
    IGNORED_MISSING_RAW_PAYLOAD = "ignored_missing_raw_payload"
    IGNORED_DIAGNOSTIC_ONLY = "ignored_diagnostic_only"


# ---------------------------------------------------------------------------
# Prior candidate
# ---------------------------------------------------------------------------


@dataclass
class PriorCandidate:
    """One prior candidate extracted from a compatible SUCCESS record.

    Parameters
    ----------
    parameter_identity : ParameterIdentity
        The parameter identity from the source record.
    parameter_key : str
        Deterministic key from the identity.
    param_names : list[str]
        Ordered parameter names.
    param_values : list[float]
        Ordered parameter values.
    raw_metrics : dict[str, float] or None
        Raw physics values from the record payload.
    objective_value : float or None
        Weighted scalar or primary objective, if available.
    gate_results : dict[str, bool] or None
        Gate pass/fail from the record payload.
    provenance : dict or None
        Diagnostic metadata from the source record.
    source_record_index : int or None
        Index of the source record in the original record list.
    """
    parameter_identity: ParameterIdentity
    parameter_key: str
    param_names: list[str]
    param_values: list[float]
    raw_metrics: dict[str, float] | None = None
    objective_value: float | None = None
    gate_results: dict[str, bool] | None = None
    provenance: dict[str, Any] | None = None
    source_record_index: int | None = None


@dataclass
class PriorConstructionReport:
    """Summary of a prior-construction run.

    Parameters
    ----------
    candidates : list[PriorCandidate]
        Successfully extracted prior candidates.
    ignored_counts : dict[str, int]
        Count of ignored records by reason key.
    total_input_records : int
        Total records provided as input.
    diagnostics : dict
        Extra information.
    """
    candidates: list[PriorCandidate] = field(default_factory=list)
    ignored_counts: dict[str, int] = field(default_factory=dict)
    total_input_records: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Record classification for prior construction
# ---------------------------------------------------------------------------


_DIAGNOSTIC_ONLY_MARKER = "diagnostic_only"


def _is_diagnostic_only(record: EvaluationDatabaseRecord) -> bool:
    """Check if a record is explicitly marked diagnostic-only.

    Diagnostic-only records are recognised by having a status string
    equal to ``"diagnostic_only"`` or via a marker in their error
    taxonomy.
    """
    if str(record.status).strip().lower() == _DIAGNOSTIC_ONLY_MARKER:
        return True
    if record.error_taxonomy and isinstance(record.error_taxonomy, dict):
        if record.error_taxonomy.get("category") == _DIAGNOSTIC_ONLY_MARKER:
            return True
    return False


def classify_record_for_prior(
    record: EvaluationDatabaseRecord,
    *,
    current_schema: int | None = None,
    require_raw_metrics: bool = True,
) -> tuple[PriorCandidateStatus, str]:
    """Classify a single record's eligibility for prior construction.

    Returns ``(PriorCandidateStatus.USABLE_SUCCESS, "")`` if eligible,
    or ``(status, reason)`` if not.
    """
    if current_schema is None:
        from workflows.rfgun_sao.evaluation_database_schema import (
            current_schema_version,
        )
        current_schema = current_schema_version()

    if not is_schema_compatible(record.schema_version, current_schema):
        return PriorCandidateStatus.IGNORED_INCOMPATIBLE_SCHEMA, \
            f"schema v{record.schema_version} incompatible"

    pid = record.parameter_identity
    if pid is None:
        return PriorCandidateStatus.IGNORED_MISSING_IDENTITY, \
            "missing parameter identity"

    # Diagnostic-only check before generic failure classification
    if _is_diagnostic_only(record):
        return PriorCandidateStatus.IGNORED_DIAGNOSTIC_ONLY, \
            "record is diagnostic-only"

    if record.status != EvaluationDatabaseStatus.SUCCESS:
        return PriorCandidateStatus.IGNORED_FAILURE, \
            f"status {record.status} is not SUCCESS"

    if record.raw_payload is None:
        if require_raw_metrics:
            return PriorCandidateStatus.IGNORED_MISSING_RAW_PAYLOAD, \
                "missing raw payload"
        return PriorCandidateStatus.USABLE_SUCCESS, ""

    if require_raw_metrics:
        has_metrics = bool(record.raw_payload.raw_metrics) or bool(record.raw_payload.objective_values)
        if not has_metrics:
            return PriorCandidateStatus.IGNORED_MISSING_RAW_PAYLOAD, \
                "raw payload has no metrics or objective values"

    return PriorCandidateStatus.USABLE_SUCCESS, ""


# ---------------------------------------------------------------------------
# Record → PriorCandidate conversion
# ---------------------------------------------------------------------------


def record_to_prior_candidate(
    record: EvaluationDatabaseRecord,
    *,
    source_index: int | None = None,
    current_schema: int | None = None,
    require_raw_metrics: bool = True,
) -> PriorCandidate | None:
    """Convert a compatible SUCCESS record to a ``PriorCandidate``.

    Applies the same eligibility checks as ``classify_record_for_prior``;
    returns ``None`` if the record is not usable.
    """
    status, _ = classify_record_for_prior(
        record,
        current_schema=current_schema,
        require_raw_metrics=require_raw_metrics,
    )
    if status != PriorCandidateStatus.USABLE_SUCCESS:
        return None

    pid = record.parameter_identity
    # pid is guaranteed non-None here (classify checks it)

    raw_metrics = None
    objective_val = None
    gate_results = None

    if record.raw_payload is not None:
        raw_metrics = record.raw_payload.raw_metrics
        gate_results = record.raw_payload.gate_results
        # Pick first finite objective value as primary objective
        obj_sources = []
        if record.raw_payload.objective_values:
            obj_sources.append(record.raw_payload.objective_values)
        if record.raw_payload.raw_metrics:
            obj_sources.append(record.raw_payload.raw_metrics)
        for src in obj_sources:
            for v in src.values():
                if v is not None and isinstance(v, (int, float)):
                    objective_val = float(v)
                    break
            if objective_val is not None:
                break

    return PriorCandidate(
        parameter_identity=pid,
        parameter_key=pid.parameter_key(),
        param_names=list(pid.param_names),
        param_values=[float(v) for v in pid.values],
        raw_metrics=dict(raw_metrics) if raw_metrics else None,
        objective_value=objective_val,
        gate_results=dict(gate_results) if gate_results else None,
        provenance=dict(record.provenance) if record.provenance else None,
        source_record_index=source_index,
    )


# ---------------------------------------------------------------------------
# Bulk prior construction
# ---------------------------------------------------------------------------


def build_prior_candidates_from_records(
    records: list[EvaluationDatabaseRecord],
    *,
    current_schema: int | None = None,
    require_raw_metrics: bool = True,
    max_candidates: int | None = None,
) -> PriorConstructionReport:
    """Build prior candidates from a list of evaluation database records.

    Only compatible SUCCESS records with valid parameter identity and raw
    payload (when ``require_raw_metrics`` is True) are converted.
    """
    if current_schema is None:
        from workflows.rfgun_sao.evaluation_database_schema import (
            current_schema_version,
        )
        current_schema = current_schema_version()

    report = PriorConstructionReport(total_input_records=len(records))
    candidates: list[PriorCandidate] = []

    for i, rec in enumerate(records):
        status, reason = classify_record_for_prior(
            rec, current_schema=current_schema,
            require_raw_metrics=require_raw_metrics,
        )
        if status == PriorCandidateStatus.USABLE_SUCCESS:
            cand = record_to_prior_candidate(
                rec, source_index=i,
                current_schema=current_schema,
                require_raw_metrics=require_raw_metrics,
            )
            if cand is not None:
                candidates.append(cand)
            continue

        # Count ignored
        key = status.value
        report.ignored_counts[key] = report.ignored_counts.get(key, 0) + 1

    if max_candidates is not None:
        candidates = candidates[:max_candidates]

    report.candidates = candidates
    report.diagnostics = {
        "require_raw_metrics": require_raw_metrics,
        "current_schema": current_schema,
    }
    return report


# ---------------------------------------------------------------------------
# Candidate selection / ordering
# ---------------------------------------------------------------------------


def select_prior_candidates(
    candidates: list[PriorCandidate],
    *,
    max_count: int | None = None,
    objective_name: str | None = None,
    prefer_low_objective: bool = True,
) -> list[PriorCandidate]:
    """Select and order prior candidates.

    If *objective_name* is provided, uses it from ``raw_metrics``;
    otherwise uses the candidate's ``objective_value``.
    Sorted by objective (ascending if ``prefer_low_objective``).
    """
    def _key(c: PriorCandidate) -> float:
        obj = None
        if objective_name and c.raw_metrics:
            obj = c.raw_metrics.get(objective_name)
        if obj is None:
            obj = c.objective_value
        if obj is None or obj != obj:  # NaN check
            return float("inf")
        return float(obj)

    sorted_candidates = sorted(candidates, key=_key)
    if not prefer_low_objective:
        sorted_candidates.reverse()

    if max_count is not None:
        sorted_candidates = sorted_candidates[:max_count]

    return sorted_candidates


# ---------------------------------------------------------------------------
# Optional stage observation derivation (no-CST)
# ---------------------------------------------------------------------------


def derive_stage_observations_from_prior_candidates(
    candidates: list[PriorCandidate],
) -> list[StageObservation]:
    """Convert prior candidates to no-CST ``StageObservation`` objects.

    Only candidates with finite objective values are included.
    Observations are marked ``COMPLETED`` and ``reused=True``.
    """
    obs: list[StageObservation] = []
    for c in candidates:
        obj = c.objective_value
        if obj is None or not (obj == obj):  # NaN check
            continue
        gate_pass: bool | None = None
        if c.gate_results is not None:
            gate_pass = all(c.gate_results.values()) if c.gate_results else None
        obs.append(StageObservation(
            x=list(c.param_values),
            status=StageCandidateStatus.COMPLETED,
            objective_value=float(obj),
            gate_pass=gate_pass,
            reused=True,
        ))
    return obs
