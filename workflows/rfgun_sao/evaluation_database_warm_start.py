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


# ===================================================================
# WS2 -- DB warm-start prior loader (no-CST)
# ===================================================================


@dataclass(frozen=True)
class DbWarmStartConfig:
    """Configuration for DB-backed optimizer warm-start.

    Parameters
    ----------
    enabled : bool
        Master switch.  Independent of success_reuse.
    max_priors : int
        Maximum number of prior observations to load (default 50).
    order_by : str
        Ordering strategy: ``"best_objective"`` (ascending scalar) or
        ``"newest"`` (descending created_at).
    require_objective_values : bool
        Reject rows without objective payload when True.
    allow_raw_recompute : bool
        Not implemented in WS2; must remain False.
    """
    enabled: bool = False
    max_priors: int = 50
    order_by: str = "best_objective"
    require_objective_values: bool = True
    allow_raw_recompute: bool = False


@dataclass(frozen=True)
class DbWarmStartPrior:
    """One prior observation extracted from an eligible DB row.

    Parameters
    ----------
    parameter_key : str
        Deterministic key from the parameter identity.
    parameter_identity : ParameterIdentity
        Full parameter identity.
    objective_values : dict[str, float]
        Objective values from the DB row.
    scalar : float
        Computed objective scalar (sum of objective_values or from penalty).
    objective_names : tuple[str, ...]
        Ordered objective/metric names.
    parameter_names : tuple[str, ...]
        Ordered parameter names.
    source_row_id : int or None
        Row ID from evaluation_records.
    source_run_id : str or None
        Run ID from evaluation_records.
    source_created_at : str or None
        Creation timestamp from evaluation_records.
    """
    parameter_key: str
    parameter_identity: ParameterIdentity
    objective_values: dict[str, float]
    scalar: float
    objective_names: tuple[str, ...]
    parameter_names: tuple[str, ...]
    source_row_id: int | None = None
    source_run_id: str | None = None
    source_created_at: str | None = None


@dataclass
class DbWarmStartLoadReport:
    """Structured report of a warm-start prior loading operation.

    Parameters
    ----------
    found_rows : int
        Total rows in the DB matching queried keys.
    eligible_rows : int
        Rows passing basic eligibility (SUCCESS, schema, identity).
    accepted_priors : int
        Priors finally accepted after capping and dedup.
    rejected_rows : int
        Rows that failed eligibility checks.
    skipped_duplicates : int
        Rows skipped because parameter_key already accepted (duplicate).
    skipped_checkpoint_duplicates : int
        Rows skipped because parameter_key already in checkpoint.
    capped : bool
        Whether max_priors limit was reached.
    rejection_reasons : dict[str, int]
        Counts of rejection by reason.
    """
    found_rows: int = 0
    eligible_rows: int = 0
    accepted_priors: int = 0
    rejected_rows: int = 0
    skipped_duplicates: int = 0
    skipped_checkpoint_duplicates: int = 0
    capped: bool = False
    rejection_reasons: dict[str, int] = field(default_factory=dict)


def resolve_db_warm_start_config(
    config: dict | None,
    *,
    db_enabled: bool = False,
) -> DbWarmStartConfig:
    """Resolve warm-start config from a workflow configuration dict.

    Parameters
    ----------
    config : dict or None
        Full workflow configuration dict.
    db_enabled : bool
        Whether the evaluation database is enabled.

    Returns
    -------
    DbWarmStartConfig
        Resolved config.  ``enabled=False`` when section absent/disabled.

    Raises
    ------
    ValueError
        If ``warm_start.enabled=True`` but *db_enabled* is False,
        or invalid ``order_by``, or negative ``max_priors``.
    """
    if config is None:
        return DbWarmStartConfig()

    raw = config.get("evaluation_database", None)
    if raw is None:
        return DbWarmStartConfig()

    ws_raw = raw.get("warm_start", None)
    if ws_raw is None:
        return DbWarmStartConfig()

    enabled = bool(ws_raw.get("enabled", False))
    if not enabled:
        return DbWarmStartConfig()

    if not db_enabled:
        raise ValueError(
            "evaluation_database.warm_start.enabled=True requires "
            "evaluation_database.enabled=True.",
        )

    order_by = str(ws_raw.get("order_by", "best_objective")).strip().lower()
    if order_by not in ("best_objective", "newest"):
        raise ValueError(
            f"Invalid order_by={order_by!r}. Allowed: 'best_objective', 'newest'.",
        )

    max_priors = int(ws_raw.get("max_priors", 50))
    if max_priors < 0:
        raise ValueError(
            f"max_priors={max_priors} is negative. Must be >= 0.",
        )

    allow_raw = bool(ws_raw.get("allow_raw_recompute", False))
    if allow_raw:
        raise ValueError(
            "allow_raw_recompute=True is not supported in WS2. "
            "Set allow_raw_recompute to false or remove it.",
        )

    return DbWarmStartConfig(
        enabled=True,
        max_priors=max_priors,
        order_by=order_by,
        require_objective_values=bool(ws_raw.get("require_objective_values", True)),
        allow_raw_recompute=bool(ws_raw.get("allow_raw_recompute", False)),
    )


def _negate_str(s: str) -> str:
    """Reverse a string for min() tie-breaking preferring larger values."""
    return s[::-1]


def _is_finite_numeric(value: object) -> bool:
    """Check if value is a finite number."""
    if not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and (value != value or value == float("inf") or value == -float("inf")):
        return False
    return True


def _row_scalar(row: dict[str, Any]) -> float:
    """Compute a scalar from a DB row for ordering."""
    obj_raw = row.get("objective_values")
    diag_raw = row.get("diagnostics")
    if isinstance(obj_raw, str):
        import json
        try:
            obj_raw = json.loads(obj_raw)
        except (json.JSONDecodeError, TypeError):
            obj_raw = None
    if isinstance(diag_raw, str):
        import json
        try:
            diag_raw = json.loads(diag_raw)
        except (json.JSONDecodeError, TypeError):
            diag_raw = None

    # Prefer __retry_penalty__ for scalar
    if isinstance(diag_raw, dict):
        pen = diag_raw.get("__retry_penalty__")
        if isinstance(pen, dict) and pen:
            return sum(float(v) for v in pen.values() if isinstance(v, (int, float)))

    # Fallback: sum objective_values
    if isinstance(obj_raw, dict) and obj_raw:
        return sum(float(v) for v in obj_raw.values() if isinstance(v, (int, float)))

    return float("inf")


def load_warm_start_priors(
    rows: list[dict[str, Any]],
    config: DbWarmStartConfig,
    *,
    metric_names: list[str],
    param_names: list[str],
    checkpoint_parameter_keys: set[str] | None = None,
    current_schema: int | None = None,
) -> DbWarmStartLoadReport:
    """Build warm-start priors from a list of DB row dicts.

    Parameters
    ----------
    rows : list[dict]
        List of DB rows from ``query_by_parameter_key`` or a full scan.
    config : DbWarmStartConfig
        Resolved warm-start configuration.
    metric_names : list[str]
        Current ordered metric names.
    param_names : list[str]
        Current ordered parameter names.
    checkpoint_parameter_keys : set[str] or None
        Parameter keys already in the checkpoint (skip on match).
    current_schema : int or None
        Expected schema version.

    Returns
    -------
    DbWarmStartLoadReport
        Loading report with accepted priors and rejection stats.
    """
    from workflows.rfgun_sao.evaluation_database_schema import current_schema_version
    import math

    if current_schema is None:
        current_schema = current_schema_version()

    report = DbWarmStartLoadReport(found_rows=len(rows))

    # Respect disabled config
    if not config.enabled:
        report.accepted_priors = 0
        report.diagnostics = {"priors": []}
        return report

    # max_priors=0 means no priors accepted
    if config.max_priors == 0:
        report.accepted_priors = 0
        report.diagnostics = {"priors": []}
        return report

    accepted: list[DbWarmStartPrior] = []
    # Per-key tracking for duplicate resolution: key -> list of eligible priors
    per_key: dict[str, list[DbWarmStartPrior]] = {}
    rejection_reasons: dict[str, int] = {}
    if checkpoint_parameter_keys is None:
        checkpoint_parameter_keys = set()

    for row in rows:
        # Status must be SUCCESS
        status = str(row.get("status", "")).strip().lower()
        if status != "success":
            _count(rejection_reasons, "status_not_success")
            report.rejected_rows += 1
            continue

        # Schema version
        row_schema = row.get("schema_version")
        if row_schema is None or int(row_schema) != current_schema:
            _count(rejection_reasons, "schema_incompatible")
            report.rejected_rows += 1
            continue

        # Parameter key
        param_key = row.get("parameter_key")
        if not param_key:
            _count(rejection_reasons, "missing_parameter_key")
            report.rejected_rows += 1
            continue

        # Parameter names
        pn_raw = row.get("param_names")
        pn = _load_json_list(pn_raw)
        if pn is None or list(pn) != param_names:
            _count(rejection_reasons, "param_names_mismatch")
            report.rejected_rows += 1
            continue

        # Parameter values
        pv_raw = row.get("param_values")
        pv = _load_json_list(pv_raw)
        if pv is None:
            _count(rejection_reasons, "missing_param_values")
            report.rejected_rows += 1
            continue
        if len(pv) != len(param_names):
            _count(rejection_reasons, "param_values_mismatch")
            report.rejected_rows += 1
            continue
        # Validate all values are numeric
        try:
            pv_float = [float(v) for v in pv]
        except (ValueError, TypeError):
            _count(rejection_reasons, "invalid_param_values")
            report.rejected_rows += 1
            continue

        # Parameter key consistency
        pid_check = ParameterIdentity(param_names=list(pn), values=pv_float)
        if pid_check.parameter_key() != param_key:
            _count(rejection_reasons, "parameter_key_mismatch")
            report.rejected_rows += 1
            continue

        # Objective names matching
        on_raw = row.get("objective_names")
        on = _load_json_list(on_raw)
        if on is None or list(on) != metric_names:
            _count(rejection_reasons, "objective_names_mismatch")
            report.rejected_rows += 1
            continue

        # Objective values
        ov_raw = row.get("objective_values")
        ov = _load_json_dict(ov_raw)

        if config.require_objective_values:
            if ov is None or not ov:
                _count(rejection_reasons, "missing_objective_values")
                report.rejected_rows += 1
                continue
            # Objective values keys must match metric_names
            if set(ov.keys()) != set(metric_names):
                _count(rejection_reasons, "objective_values_keys_mismatch")
                report.rejected_rows += 1
                continue
            # All objective values must be numeric and finite
            obj_valid = True
            for val in ov.values():
                if not isinstance(val, (int, float)):
                    _count(rejection_reasons, "invalid_objective_values")
                    obj_valid = False
                    break
            if obj_valid:
                for val in ov.values():
                    if not _is_finite_numeric(val):
                        _count(rejection_reasons, "nonfinite_objective_values")
                        obj_valid = False
                        break
            if not obj_valid:
                report.rejected_rows += 1
                continue

        # Checkpoint dedup (before per-key storage)
        if param_key in checkpoint_parameter_keys:
            _count(rejection_reasons, "checkpoint_duplicate")
            report.skipped_checkpoint_duplicates += 1
            continue

        report.eligible_rows += 1

        # Build prior
        ov = ov or {}
        scalar = _row_scalar(row)

        prior = DbWarmStartPrior(
            parameter_key=param_key,
            parameter_identity=pid_check,
            objective_values=dict(ov),
            scalar=scalar,
            objective_names=tuple(on) if on else tuple(metric_names),
            parameter_names=tuple(pn),
            source_row_id=row.get("id"),
            source_run_id=row.get("run_id"),
            source_created_at=row.get("created_at"),
        )

        # Store per-key for dedup
        if param_key not in per_key:
            per_key[param_key] = []
        per_key[param_key].append(prior)

    # Per-key dedup: keep best row per key
    for key, candidates in per_key.items():
        if len(candidates) == 1:
            accepted.append(candidates[0])
        else:
            # Select best per key
            if config.order_by == "newest":
                # Keep newest created_at, then highest id
                best = max(candidates, key=lambda p: (
                    str(p.source_created_at or ""),
                    p.source_row_id or 0,
                ))
                report.skipped_duplicates += len(candidates) - 1
                accepted.append(best)
            else:
                # Keep lowest scalar (best objective), then newer created_at,
                # then higher id.  Use max() with negated scalar because
                # the lowest scalar is the most negative.
                best = max(candidates, key=lambda p: (
                    -p.scalar,
                    str(p.source_created_at or ""),
                    p.source_row_id or 0,
                ))
                report.skipped_duplicates += len(candidates) - 1
                accepted.append(best)

    # Apply ordering
    if config.order_by == "best_objective":
        accepted.sort(key=lambda p: (p.scalar, str(p.source_created_at or ""), p.source_row_id or 0))
    elif config.order_by == "newest":
        accepted.sort(
            key=lambda p: (str(p.source_created_at or ""), p.source_row_id or 0),
            reverse=True,
        )

    # Apply capping
    if len(accepted) > config.max_priors:
        accepted = accepted[:config.max_priors]
        report.capped = True

    report.accepted_priors = len(accepted)
    report.rejection_reasons = dict(rejection_reasons)
    report.diagnostics = {"priors": accepted}

    return report


def _count(d: dict[str, int], key: str) -> None:
    """Increment a counter in a dict."""
    d[key] = d.get(key, 0) + 1


def _load_json_list(raw: Any) -> list | None:
    """Parse a JSON string to a list, or return None."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _load_json_dict(raw: Any) -> dict | None:
    """Parse a JSON string to a dict, or return None."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


# ===================================================================
# WS3.1 — Pure no-CST helpers for checkpoint-dedup merging
# ===================================================================


def parameter_keys_from_prior_data(
    prior_x: np.ndarray,
    param_names: list[str],
) -> set[str]:
    """Compute checkpoint-style parameter keys from a prior_data X array.

    Each row of *prior_x* is converted to a ``ParameterIdentity`` key
    using *param_names*.

    Parameters
    ----------
    prior_x : np.ndarray
        2-D array of shape ``(N, D)`` where ``D == len(param_names)``.
    param_names : list[str]
        Ordered parameter names for constructing identities.

    Returns
    -------
    set[str]
        One ``parameter_key`` per row.
    """
    keys: set[str] = set()
    for x_vec in prior_x:
        pid = ParameterIdentity(param_names=param_names, values=list(x_vec))
        keys.add(pid.parameter_key())
    return keys


def db_priors_to_prior_data(
    priors: list[DbWarmStartPrior],
) -> tuple[np.ndarray, np.ndarray]:
    """Convert a list of ``DbWarmStartPrior`` to ``(X, F)`` arrays.

    Parameters
    ----------
    priors : list[DbWarmStartPrior]
        Accepted warm-start priors.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(X, F)`` where ``X.shape == (N, D)`` and ``F.shape == (N,)``.
    """
    import numpy as np

    ws_x = np.array(
        [list(p.parameter_identity.values) for p in priors], dtype=float,
    )
    ws_f = np.array([p.scalar for p in priors], dtype=float)
    return ws_x, ws_f


def merge_checkpoint_and_db_priors(
    checkpoint_prior_data: tuple[np.ndarray, np.ndarray] | None,
    db_priors: list[DbWarmStartPrior],
    param_names: list[str],
) -> tuple[tuple[np.ndarray, np.ndarray] | None, dict[str, int]]:
    """Merge checkpoint and DB priors, deduplicating by parameter key.

    Checkpoint observations remain authoritative — any DB prior whose
    ``parameter_key`` already appears in the checkpoint is omitted.

    Parameters
    ----------
    checkpoint_prior_data : tuple[np.ndarray, np.ndarray] or None
        ``(X, F)`` from checkpoint, or ``None``.
    db_priors : list[DbWarmStartPrior]
        Accepted DB warm-start priors.
    param_names : list[str]
        Ordered parameter names for key computation.

    Returns
    -------
    merged : tuple[np.ndarray, np.ndarray] or None
        Merged ``(X, F)``, or ``None`` when both inputs are empty.
    diagnostics : dict[str, int]
        Keys: ``"ckpt_count"``, ``"db_input_count"``,
        ``"db_checkpoint_duplicates"``, ``"db_accepted"``.
    """
    import numpy as np

    ckpt_count = 0
    ckpt_keys: set[str] = set()
    if checkpoint_prior_data is not None:
        ckpt_x = checkpoint_prior_data[0]
        ckpt_count = len(ckpt_x)
        ckpt_keys = parameter_keys_from_prior_data(ckpt_x, param_names)

    db_input_count = len(db_priors)

    # Separate DB priors into checkpoint dup vs accepted
    accepted_db: list[DbWarmStartPrior] = []
    checkpoint_dups = 0
    for prior in db_priors:
        if prior.parameter_key in ckpt_keys:
            checkpoint_dups += 1
        else:
            accepted_db.append(prior)

    if checkpoint_prior_data is None and not accepted_db:
        return None, {
            "ckpt_count": ckpt_count,
            "db_input_count": db_input_count,
            "db_checkpoint_duplicates": checkpoint_dups,
            "db_accepted": 0,
        }

    if checkpoint_prior_data is None:
        merged_x, merged_f = db_priors_to_prior_data(accepted_db)
    elif not accepted_db:
        merged_x, merged_f = checkpoint_prior_data
    else:
        db_x, db_f = db_priors_to_prior_data(accepted_db)
        merged_x = np.vstack([checkpoint_prior_data[0], db_x])
        merged_f = np.concatenate([checkpoint_prior_data[1], db_f])

    return (merged_x, merged_f), {
        "ckpt_count": ckpt_count,
        "db_input_count": db_input_count,
        "db_checkpoint_duplicates": checkpoint_dups,
        "db_accepted": len(accepted_db),
    }