"""No-CST failure skip candidate loader — FS2.

Pure helpers only.  No runtime skip, no evaluator wiring, no retry call,
no subprocess, no CST import.  Candidates are loaded from a durable
evaluation DB, classified against FS1 policy rules, and returned as
structured results.  Nothing is skipped, written, or enforced.
"""

from __future__ import annotations

import dataclasses
import json as _json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from cst_optimization.evaluation.warm_start import (
    _load_json_dict,
    _load_json_list,
)


# ===================================================================
# Config
# ===================================================================


@dataclass(frozen=True)
class FailureSkipCandidateConfig:
    """Configuration for failure skip candidate loading.

    Parameters
    ----------
    enabled : bool
        Master switch.  Default ``False``.
    mode : str
        ``"disabled"``, ``"dry_run"``, or ``"enforce"``.
    exact_key_only : bool
        Only consider exact ``parameter_key`` matches.
    min_failures : int
        Minimum number of evidence rows at the same key.
    allow_gate_reject : bool
        Include ``gate_rejected`` rows as candidate evidence.
    allow_calibration_failed : bool
        Include ``calibration_failed`` rows as candidate evidence.
    allow_solver_failed : bool
        Include ``solver_failed`` rows as candidate evidence.
    allow_objective_extraction_failed : bool
        Include objective-extraction failures as candidate evidence.
    allow_timeout : bool
        Include timeout rows as candidate evidence.
    allow_com_lost : bool
        Include COM-connection-lost rows as candidate evidence.
    allow_unknown_exception : bool
        Include unknown-exception rows as candidate evidence.
    allow_environment_faults : bool
        Include environment/process-kill rows as candidate evidence.
    max_candidates : int
        Maximum candidates to return.
    require_schema_compatible : bool
        Reject rows whose schema version differs.
    require_objective_signature_match : bool
        Reject rows whose objective names differ.
    objective_signature : str or None
        Expected objective signature for compatibility checks.
    max_age_days : int or None
        Maximum age of evidence rows in days.
    policy_version : int
        Skip policy version identifier.
    """
    enabled: bool = False
    mode: str = "disabled"
    exact_key_only: bool = True
    min_failures: int = 2
    allow_gate_reject: bool = True
    allow_calibration_failed: bool = True
    allow_solver_failed: bool = True
    allow_objective_extraction_failed: bool = True
    allow_timeout: bool = False
    allow_com_lost: bool = False
    allow_unknown_exception: bool = False
    allow_environment_faults: bool = False
    max_candidates: int = 100
    require_schema_compatible: bool = True
    require_objective_signature_match: bool = True
    objective_signature: str | None = None
    max_age_days: int | None = None
    policy_version: int = 1


_VALID_MODES = frozenset({"disabled", "dry_run", "enforce"})


def resolve_failure_skip_config(config: dict | None) -> FailureSkipCandidateConfig:
    """Resolve a ``FailureSkipCandidateConfig`` from a workflow config dict.

    Parameters
    ----------
    config : dict or None
        Full workflow configuration dict.

    Returns
    -------
    FailureSkipCandidateConfig
        Resolved config with safe defaults.
    """
    if config is None:
        return FailureSkipCandidateConfig()

    raw = config.get("evaluation_database", None)
    if raw is None:
        return FailureSkipCandidateConfig()

    fs_raw = raw.get("failure_skip", None)
    if fs_raw is None:
        return FailureSkipCandidateConfig()

    enabled = bool(fs_raw.get("enabled", False))
    if not enabled:
        return FailureSkipCandidateConfig()

    mode = str(fs_raw.get("mode", "disabled")).strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid failure_skip.mode={mode!r}. "
            f"Allowed: {sorted(_VALID_MODES)}",
        )

    exact_key_only = fs_raw.get("exact_key_only", True)
    if not bool(exact_key_only):
        raise ValueError(
            f"failure_skip.exact_key_only=False is not supported. "
            f"Region-wide or proximity-based skip is not implemented.",
        )

    return FailureSkipCandidateConfig(
        enabled=True,
        mode=mode,
        exact_key_only=bool(fs_raw.get("exact_key_only", True)),
        min_failures=int(fs_raw.get("min_failures", 2)),
        allow_gate_reject=bool(fs_raw.get("allow_gate_reject", True)),
        allow_calibration_failed=bool(fs_raw.get("allow_calibration_failed", True)),
        allow_solver_failed=bool(fs_raw.get("allow_solver_failed", True)),
        allow_objective_extraction_failed=bool(
            fs_raw.get("allow_objective_extraction_failed", True),
        ),
        allow_timeout=bool(fs_raw.get("allow_timeout", False)),
        allow_com_lost=bool(fs_raw.get("allow_com_lost", False)),
        allow_unknown_exception=bool(fs_raw.get("allow_unknown_exception", False)),
        allow_environment_faults=bool(fs_raw.get("allow_environment_faults", False)),
        max_candidates=int(fs_raw.get("max_candidates", 100)),
        require_schema_compatible=bool(fs_raw.get("require_schema_compatible", True)),
        require_objective_signature_match=bool(
            fs_raw.get("require_objective_signature_match", True),
        ),
        objective_signature=fs_raw.get("objective_signature", None),
        max_age_days=fs_raw.get("max_age_days", None),
        policy_version=int(fs_raw.get("policy_version", 1)),
    )


# ===================================================================
# Evidence classification
# ===================================================================


# Classification literal constants
GATE_REJECTED = "gate_rejected"
CALIBRATION_FAILED = "calibration_failed"
SOLVER_FAILED = "solver_failed"
OBJECTIVE_EXTRACTION_FAILED = "objective_extraction_failed"
PROBABLY_INFEASIBLE_CANDIDATE = "probably_infeasible_candidate"
SUCCESS = "success"
SUCCESS_REUSE = "success_reuse"
WARM_START_PRIOR = "warm_start_prior"
RAW_ONLY = "raw_only"
SCHEMA_INCOMPATIBLE = "schema_incompatible"
XR_PROCESS_KILL = "xr_process_kill"
COM_CONNECTION_LOST = "com_connection_lost"
COM_CALL_HANG = "com_call_hang"
CLEANUP_CLOSE_HANG = "cleanup_close_hang"
LICENSE_DAEMON_AMBIGUITY = "license_daemon_ambiguity"
UNKNOWN_CST_PROCESS_STATE = "unknown_cst_process_state"
UNKNOWN_EXCEPTION = "unknown_exception"
TIMEOUT = "timeout"
TRANSIENT_ENVIRONMENT_FAULT = "transient_environment_fault"
SOLVER_TIMEOUT = "solver_timeout"
SOLVER_FAILED_WITHOUT_TAXONOMY = "solver_failed_without_taxonomy"
MEASUREMENT_EXTRACTION_FAILED = "measurement_extraction_failed"
CALIBRATION_FAILED_INCOMPLETE_CONTEXT = "calibration_failed_incomplete_context"


def _check_error_taxonomy(
    error_taxonomy: Any,
) -> tuple[str, dict | None]:
    """Check the *error_taxonomy* JSON for environment/process-kill markers.

    Returns ``(classification, taxonomy_dict)``.
    """
    if error_taxonomy is None:
        return UNKNOWN_EXCEPTION, None
    if not isinstance(error_taxonomy, dict):
        return UNKNOWN_EXCEPTION, None

    # Check for XR process-kill markers
    orig = str(error_taxonomy.get("original_error", ""))
    orig_status = str(error_taxonomy.get("original_status", ""))

    # Process-kill / COM lost markers
    kill_markers = [
        "connection was lost",
        "Failed to call: run_solver",
        "tree path not found",
    ]
    for marker in kill_markers:
        if marker in orig or marker in orig_status:
            return XR_PROCESS_KILL, error_taxonomy

    # COM connection lost
    if "com" in orig.lower() or "rpc" in orig.lower():
        return COM_CONNECTION_LOST, error_taxonomy

    # Unknown
    return SOLVER_FAILED, error_taxonomy


def classify_failure_skip_evidence(
    row: dict[str, Any],
    config: FailureSkipCandidateConfig | None = None,
) -> str:
    """Classify a single DB row dict for failure skip evidence eligibility.

    Parameters
    ----------
    row : dict
        A row dict from ``get_all_records()``.
    config : FailureSkipCandidateConfig or None
        Optional config to guide classification.

    Returns
    -------
    str
        One of the classification literal constants.
    """
    if config is None:
        config = FailureSkipCandidateConfig()

    status = str(row.get("status", "")).strip().lower()
    source = str(row.get("source", "")).strip().lower() if row.get("source") else ""
    error_taxonomy = row.get("error_taxonomy")
    raw_metrics = row.get("raw_metrics")
    objective_values = row.get("objective_values")
    diagnostics = row.get("diagnostics")
    schema_version = row.get("schema_version")

    # --- Compatibility checks ---

    # Schema compatibility
    if config.require_schema_compatible:
        from cst_optimization.evaluation.schema import (
            current_schema_version,
        )
        if schema_version is None or int(schema_version) != current_schema_version():
            return SCHEMA_INCOMPATIBLE

    # --- Classification by status ---

    # SUCCESS / reuse / warm-start → excluded
    if status == "success":
        # Check if this is a reused-from-DB row
        if source and "reuse" in source:
            return SUCCESS_REUSE
        # Check diagnostics for warm-start marker
        if isinstance(diagnostics, dict) and diagnostics.get("is_warm_start_prior"):
            return WARM_START_PRIOR
        return SUCCESS

    # Gate rejected
    if status == "gate_rejected":
        return GATE_REJECTED

    # Calibration failed
    if status == "calibration_failed":
        return CALIBRATION_FAILED

    # Timeout
    if status == "timeout":
        return TIMEOUT
    if status == "solver_timeout":
        return SOLVER_TIMEOUT

    # Solver failed — need taxonomy check
    if status == "solver_failed":
        cls, _ = _check_error_taxonomy(error_taxonomy)
        if cls == XR_PROCESS_KILL:
            return XR_PROCESS_KILL
        if cls == COM_CONNECTION_LOST:
            return COM_CONNECTION_LOST
        if cls == UNKNOWN_EXCEPTION and error_taxonomy is None:
            return SOLVER_FAILED_WITHOUT_TAXONOMY
        return cls  # SOLVER_FAILED or XR_PROCESS_KILL

    # Transient failed
    if status == "transient_failed":
        return TRANSIENT_ENVIRONMENT_FAULT

    # Synthetic skip statuses — excluded from evidence
    if status in ("skipped_failure_reuse", "skipped_probably_infeasible"):
        return status

    # Unknown status
    return UNKNOWN_EXCEPTION


def is_environment_fault_classification(classification: str) -> bool:
    """Return True if *classification* represents an environment/COM/process-kill fault."""
    env_classes = frozenset({
        XR_PROCESS_KILL,
        COM_CONNECTION_LOST,
        COM_CALL_HANG,
        CLEANUP_CLOSE_HANG,
        LICENSE_DAEMON_AMBIGUITY,
        UNKNOWN_CST_PROCESS_STATE,
        TRANSIENT_ENVIRONMENT_FAULT,
    })
    return classification in env_classes


def is_candidate_evidence_classification(
    classification: str,
    config: FailureSkipCandidateConfig,
) -> bool:
    """Return True if *classification* is eligible as candidate skip evidence under *config*."""
    if classification == GATE_REJECTED:
        return config.allow_gate_reject
    if classification == CALIBRATION_FAILED:
        return config.allow_calibration_failed
    if classification == SOLVER_FAILED:
        return config.allow_solver_failed
    if classification == OBJECTIVE_EXTRACTION_FAILED:
        return config.allow_objective_extraction_failed
    if classification == PROBABLY_INFEASIBLE_CANDIDATE:
        return True
    if classification == TIMEOUT:
        return config.allow_timeout
    if classification == SOLVER_TIMEOUT:
        return config.allow_timeout
    if classification == UNKNOWN_EXCEPTION:
        return config.allow_unknown_exception
    # Excluded classes
    return False


def is_ambiguous_evidence_classification(classification: str) -> bool:
    """Return True if *classification* is ambiguous and should be dry-run only."""
    ambig = frozenset({
        SOLVER_TIMEOUT,
        SOLVER_FAILED_WITHOUT_TAXONOMY,
        MEASUREMENT_EXTRACTION_FAILED,
        CALIBRATION_FAILED_INCOMPLETE_CONTEXT,
    })
    return classification in ambig


# ===================================================================
# Evidence record
# ===================================================================


@dataclass(frozen=True)
class FailureSkipEvidenceRecord:
    """One evidence record extracted from a DB row.

    Parameters
    ----------
    row_id : int or None
    run_id : str or None
    parameter_key : str or None
    status : str
    classification : str
    source : str or None
    created_at : str or None
    error_taxonomy : dict or None
    objective_signature : str or None
    schema_version : int or None
    compatible : bool
    blocked_reason : str or None
    """
    row_id: int | None = None
    run_id: str | None = None
    parameter_key: str | None = None
    status: str = ""
    classification: str = ""
    source: str | None = None
    created_at: str | None = None
    error_taxonomy: Mapping[str, Any] | None = None
    objective_signature: str | None = None
    schema_version: int | None = None
    compatible: bool = True
    blocked_reason: str | None = None


# ===================================================================
# Candidate
# ===================================================================


@dataclass(frozen=True)
class FailureSkipCandidate:
    """One aggregated failure skip candidate for a single ``parameter_key``.

    Parameters
    ----------
    parameter_key : str
    evidence_count : int
    source_row_ids : tuple of int
    source_run_ids : tuple of str
    statuses : tuple of str
    classifications : tuple of str
    confidence : str
        ``"low"``, ``"medium"``, or ``"high"``.
    recommended_skip : bool
    decision : str
        ``"no_candidate"``, ``"would_skip"``, ``"enforce_eligible"``, or
        ``"blocked_..."``.
    blocked_reasons : tuple of str
    policy_version : int
    mode : str
    """
    parameter_key: str = ""
    evidence_count: int = 0
    source_row_ids: tuple[int, ...] = ()
    source_run_ids: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    confidence: str = "low"
    recommended_skip: bool = False
    decision: str = "no_candidate"
    blocked_reasons: tuple[str, ...] = ()
    policy_version: int = 1
    mode: str = "disabled"


# ===================================================================
# Load result
# ===================================================================


@dataclass(frozen=True)
class FailureSkipCandidateLoadResult:
    """Structured result of loading failure skip candidates from the DB.

    Parameters
    ----------
    enabled : bool
    mode : str
    found_rows : int
    classified_rows : int
    candidate_rows : int
    blocked_rows : int
    candidates : tuple of FailureSkipCandidate
    blocked_by_reason : dict
    by_classification : dict
    max_candidates_applied : bool
    diagnostics : dict
    """
    enabled: bool = False
    mode: str = "disabled"
    found_rows: int = 0
    classified_rows: int = 0
    candidate_rows: int = 0
    blocked_rows: int = 0
    candidates: tuple[FailureSkipCandidate, ...] = ()
    blocked_by_reason: dict[str, int] = field(default_factory=dict)
    by_classification: dict[str, int] = field(default_factory=dict)
    max_candidates_applied: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ===================================================================
# Evidence builders
# ===================================================================


def _row_to_evidence_record(row: dict[str, Any]) -> FailureSkipEvidenceRecord:
    """Convert a DB row dict to a ``FailureSkipEvidenceRecord``."""
    # Build objective signature from objective_names
    obj_names = row.get("objective_names")
    obj_sig: str | None = None
    if isinstance(obj_names, list) and obj_names:
        obj_sig = ",".join(sorted(str(n) for n in obj_names))

    return FailureSkipEvidenceRecord(
        row_id=row.get("id"),
        run_id=row.get("run_id"),
        parameter_key=row.get("parameter_key"),
        status=str(row.get("status", "")),
        classification="",
        source=str(row.get("source", "")) if row.get("source") else None,
        created_at=row.get("created_at"),
        error_taxonomy=row.get("error_taxonomy"),
        objective_signature=obj_sig,
        schema_version=row.get("schema_version"),
        compatible=True,
    )


# ===================================================================
# DB loader
# ===================================================================


def _check_objective_signature_match(
    evidence: FailureSkipEvidenceRecord,
    config: FailureSkipCandidateConfig,
) -> bool:
    """Check if evidence objective signature matches config expectation."""
    if not config.require_objective_signature_match:
        return True
    if config.objective_signature is None:
        return True  # No signature configured → skip check
    return evidence.objective_signature == config.objective_signature



def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON columns in a DB row dict (mirrors storage._row_to_dict)."""
    json_cols = frozenset({
        "param_names", "param_values", "raw_metrics", "objective_values",
        "objective_names", "gate_results", "diagnostics", "artifact_refs",
        "provenance", "error_taxonomy",
    })
    for col in json_cols:
        val = row.get(col)
        if val is not None and isinstance(val, str):
            try:
                row[col] = _json.loads(val)
            except (_json.JSONDecodeError, TypeError):
                pass
    return row


def load_failure_skip_candidates(
    db_path: str | Path,
    config: FailureSkipCandidateConfig,
    *,
    parameter_keys: Iterable[str] | None = None,
) -> FailureSkipCandidateLoadResult:
    """Load failure skip candidates from a durable evaluation DB.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite evaluation database.
    config : FailureSkipCandidateConfig
        Resolved skip candidate config.
    parameter_keys : iterable of str or None
        If provided, restrict candidates to these exact keys.

    Returns
    -------
    FailureSkipCandidateLoadResult
    """
    # --- exact_key_only enforcement ---
    if not config.exact_key_only:
        raise ValueError(
            "exact_key_only=False is not supported. "
            "Region-wide or proximity-based skip is not implemented.",
        )

    # --- Early return for disabled ---
    if not config.enabled or config.mode == "disabled":
        return FailureSkipCandidateLoadResult(
            enabled=False, mode="disabled",
            diagnostics={"reason": "skip candidate loading disabled"},
        )

    # --- Open DB ---
    path = Path(db_path)
    if not path.exists() or not path.is_file():
        return FailureSkipCandidateLoadResult(
            enabled=True, mode=config.mode,
            found_rows=0,
            diagnostics={"reason": f"DB path does not exist: {db_path}"},
        )

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(
            "SELECT * FROM evaluation_records ORDER BY created_at DESC",
        )
        raw_rows = [_decode_row(dict(row)) for row in cursor.fetchall()]
    finally:
        conn.close()

    found_rows = len(raw_rows)

    # --- Classify rows ---
    evidence_list: list[FailureSkipEvidenceRecord] = []
    blocked_by_reason: dict[str, int] = {}
    by_classification: dict[str, int] = {}

    for row in raw_rows:
        cls = classify_failure_skip_evidence(row, config)
        by_classification[cls] = by_classification.get(cls, 0) + 1

        ev = _row_to_evidence_record(row)
        ev = dataclasses.replace(ev, classification=cls)

        # Filter by parameter_keys if supplied
        pk = ev.parameter_key
        if parameter_keys is not None and pk is not None:
            if pk not in set(parameter_keys):
                continue

        # SUCCESS / reuse / warm-start → skip
        if cls in (SUCCESS, SUCCESS_REUSE, WARM_START_PRIOR):
            continue

        # Synthetic skip statuses → excluded from evidence
        if cls in ("skipped_failure_reuse", "skipped_probably_infeasible"):
            blocked_by_reason["skip_status_excluded"] = (
                blocked_by_reason.get("skip_status_excluded", 0) + 1
            )
            continue

        # Schema incompatible → skip
        if cls == SCHEMA_INCOMPATIBLE:
            blocked_by_reason["schema_incompatible"] = (
                blocked_by_reason.get("schema_incompatible", 0) + 1
            )
            continue

        # No parameter_key → skip
        if pk is None:
            blocked_by_reason["missing_parameter_key"] = (
                blocked_by_reason.get("missing_parameter_key", 0) + 1
            )
            continue

        # XR process-kill always hard-blocked in FS2
        if cls == XR_PROCESS_KILL:
            blocked_by_reason["xr_process_kill_hard_blocked"] = (
                blocked_by_reason.get("xr_process_kill_hard_blocked", 0) + 1
            )
            continue

        # Other environment faults blocked by default
        if is_environment_fault_classification(cls) and not config.allow_environment_faults:
            blocked_by_reason["environment_fault"] = (
                blocked_by_reason.get("environment_fault", 0) + 1
            )
            ev = dataclasses.replace(
                ev, compatible=False,
                blocked_reason="environment_fault_excluded_by_default",
            )
            continue

        # Objective signature check
        if not _check_objective_signature_match(ev, config):
            blocked_by_reason["objective_signature_mismatch"] = (
                blocked_by_reason.get("objective_signature_mismatch", 0) + 1
            )
            continue

        evidence_list.append(ev)

    classified_rows = len(evidence_list) + sum(blocked_by_reason.values())

    # --- Group by parameter_key ---
    grouped: dict[str, list[FailureSkipEvidenceRecord]] = {}
    seen_row_ids: dict[str, set[int]] = {}

    for ev in evidence_list:
        pk = ev.parameter_key or ""
        if pk not in grouped:
            grouped[pk] = []
            seen_row_ids[pk] = set()
        if ev.row_id is not None:
            if ev.row_id in seen_row_ids[pk]:
                continue  # dedup
            seen_row_ids[pk].add(ev.row_id)
        grouped[pk].append(ev)

    # --- Build candidates ---
    candidates: list[FailureSkipCandidate] = []

    for pk, evs in grouped.items():
        evidence_count = len(evs)
        source_row_ids = tuple(sorted(
            e.row_id for e in evs if e.row_id is not None
        ))
        source_run_ids = tuple(sorted(
            str(e.run_id) for e in evs if e.run_id
        ))
        statuses = tuple(sorted(e.status for e in evs))
        classifications = tuple(sorted(e.classification for e in evs))

        blocked_reasons: list[str] = []
        recommended = False
        decision = "no_candidate"

        # Check min_failures threshold
        if evidence_count < config.min_failures:
            blocked_reasons.append(f"insufficient_evidence:{evidence_count}<{config.min_failures}")

        # Check allowed statuses
        allowed_count = sum(
            1 for e in evs
            if is_candidate_evidence_classification(e.classification, config)
        )
        if allowed_count == 0:
            blocked_reasons.append("no_allowed_classifications")

        # Ambiguous evidence → dry-run only
        has_ambiguous = any(is_ambiguous_evidence_classification(e.classification) for e in evs)
        if has_ambiguous and config.mode != "dry_run":
            blocked_reasons.append("ambiguous_evidence_dry_run_only")

        # Decision
        if not blocked_reasons:
            if config.mode == "dry_run":
                recommended = True
                decision = "would_skip"
                confidence = "medium"
            elif config.mode == "enforce":
                recommended = True
                decision = "enforce_eligible"
                confidence = "high"
            else:
                decision = "no_candidate"
                confidence = "low"
        else:
            decision = f"blocked_{blocked_reasons[0]}"
            confidence = "low"

        candidate = FailureSkipCandidate(
            parameter_key=pk,
            evidence_count=evidence_count,
            source_row_ids=source_row_ids,
            source_run_ids=source_run_ids,
            statuses=statuses,
            classifications=classifications,
            confidence=confidence,
            recommended_skip=recommended,
            decision=decision,
            blocked_reasons=tuple(blocked_reasons),
            policy_version=config.policy_version,
            mode=config.mode,
        )
        candidates.append(candidate)

    # --- Sort deterministically ---
    candidates.sort(key=lambda c: (-c.evidence_count, c.parameter_key))

    # --- Apply max_candidates cap ---
    max_candidates_applied = False
    if len(candidates) > config.max_candidates:
        candidates = candidates[:config.max_candidates]
        max_candidates_applied = True

    # --- Counts ---
    blocked_rows = sum(blocked_by_reason.values())
    candidate_rows = len(candidates)

    return FailureSkipCandidateLoadResult(
        enabled=True,
        mode=config.mode,
        found_rows=found_rows,
        classified_rows=classified_rows,
        candidate_rows=candidate_rows,
        blocked_rows=blocked_rows,
        candidates=tuple(candidates),
        blocked_by_reason=dict(blocked_by_reason),
        by_classification=dict(by_classification),
        max_candidates_applied=max_candidates_applied,
        diagnostics={
            "policy_version": config.policy_version,
            "min_failures": config.min_failures,
        },
    )


# ===================================================================
# Single-key lookup helper
# ===================================================================


def find_failure_skip_candidate_for_key(
    db_path: str | Path,
    parameter_key: str,
    config: FailureSkipCandidateConfig,
) -> FailureSkipCandidate | None:
    """Find a failure skip candidate for a specific ``parameter_key``.

    Parameters
    ----------
    db_path : str or Path
    parameter_key : str
    config : FailureSkipCandidateConfig

    Returns
    -------
    FailureSkipCandidate or None
    """
    result = load_failure_skip_candidates(
        db_path, config, parameter_keys=[parameter_key],
    )
    if result.candidates:
        return result.candidates[0]
    return None
