"""No-CST process/fault safety harness for extreme/recovery test scenarios.

Phase XR2 — pure no-CST helpers and classifiers.  No OS calls, no
subprocess, no taskkill, no CST import.  All functions are testable
with standard Python test doubles.

Safety policy (from XR1):
- Never kill by broad process name; always PID-specific.
- Target PID must be registry-confirmed before any action.
- ``cstd.exe`` / license daemon is protected in all circumstances.
- Pre-run and post-run process inventory required.
- Emergency cleanup must be recorded if it happens.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


# ===================================================================
# Fault taxonomy — matches XR1 design document sections 2 and 3
# ===================================================================


class ExtremeRecoveryFaultKind(str, enum.Enum):
    """Fault kinds from the XR1 destructive recovery taxonomy.

    Each member maps to one scenario defined in the XR1 design report.
    """

    DE_PROCESS_KILLED_BEFORE_SOLVE = "de_process_killed_before_solve"
    DE_PROCESS_KILLED_DURING_SOLVE = "de_process_killed_during_solve"
    DE_PROCESS_KILLED_AFTER_SOLVE_BEFORE_CLEANUP = (
        "de_process_killed_after_solve_before_cleanup"
    )
    COM_CALL_HANG = "com_call_hang"
    COM_CONNECTION_LOST = "com_connection_lost"
    SOLVER_TIMEOUT = "solver_timeout"
    REPLACEMENT_DE_ORPHAN_CANDIDATE = "replacement_de_orphan_candidate"
    CLEANUP_CLOSE_HANG = "cleanup_close_hang"
    LICENSE_DAEMON_MUST_NOT_KILL = "license_daemon_must_not_kill"
    UNKNOWN_CST_PROCESS_STATE = "unknown_cst_process_state"


# -------------------------------------------------------------------
# Classification helpers
# -------------------------------------------------------------------


def is_destructive_fault_kind(kind: ExtremeRecoveryFaultKind) -> bool:
    """Return True if *kind* represents a destructive (process-kill or COM-sever) scenario.

    Taxonomy IDs involving process death, COM hang, or connection loss
    are destructive.  Solver timeout and cleanup hang are non-destructive
    but are included as part of the recovery taxonomy.
    """
    destructive = frozenset({
        ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
        ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_DURING_SOLVE,
        ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_AFTER_SOLVE_BEFORE_CLEANUP,
        ExtremeRecoveryFaultKind.COM_CALL_HANG,
        ExtremeRecoveryFaultKind.COM_CONNECTION_LOST,
        ExtremeRecoveryFaultKind.REPLACEMENT_DE_ORPHAN_CANDIDATE,
    })
    return kind in destructive


def requires_operator_approval(kind: ExtremeRecoveryFaultKind) -> bool:
    """Return True if *kind* requires explicit operator approval before execution.

    Every destructive fault kind requires approval.  Solver timeout and
    cleanup hang are already covered by existing retry/cleanup paths and
    do not require a new approval gate.
    """
    return is_destructive_fault_kind(kind)


def is_environment_fault(kind: ExtremeRecoveryFaultKind) -> bool:
    """Return True if *kind* represents a transient environment / COM failure.

    Environment faults are transient by nature (process died, network
    glitch, COM hang).  They should generally be excluded from skip
    evidence because they do not reflect geometry or physics infeasibility.
    """
    env = frozenset({
        ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
        ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_DURING_SOLVE,
        ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_AFTER_SOLVE_BEFORE_CLEANUP,
        ExtremeRecoveryFaultKind.COM_CALL_HANG,
        ExtremeRecoveryFaultKind.COM_CONNECTION_LOST,
        ExtremeRecoveryFaultKind.CLEANUP_CLOSE_HANG,
    })
    return kind in env


def is_skip_evidence_candidate(kind: ExtremeRecoveryFaultKind) -> bool:
    """Return True if *kind* could contribute to a future failure-skip decision.

    XR2 policy:
    - Environment / COM / process-kill faults are transient by default and
      should generally be excluded from skip evidence.
    - Skip evidence should focus on deterministic / repeated exact-key
      geometry, physics, gate, calibration, or solver failures.
    - ``solver_timeout`` is ambiguous: it may reflect a genuinely hard
      geometry or a transient workstation issue.  It defaults to
      non-skip evidence until explicitly classified by a future skip policy.
    """
    # All environment faults are excluded from skip evidence
    if is_environment_fault(kind):
        return False
    # Taxonomy entries that are not environment faults may still be
    # excluded by future policy.  Default to False for safety.
    return False


# ===================================================================
# Process snapshot — a pure record of an observed process
# ===================================================================


@dataclass(frozen=True)
class ProcessSnapshot:
    """Immutable representation of one process observed during inventory.

    Parameters
    ----------
    pid : int
        Process ID.  Must be positive.
    name : str
        Process executable name (e.g. ``"CSTDesignEnvironment.exe"``).
    command_line : str or None
        Full command line, if available.
    window_title : str or None
        Window title, if available.
    parent_pid : int or None
        Parent process ID.
    created_at : str or None
        ISO-format timestamp or similar.
    source : str
        Diagnostic source label (e.g. ``"mock"``, ``"Get-Process"``).
    """
    pid: int
    name: str
    command_line: str | None = None
    window_title: str | None = None
    parent_pid: int | None = None
    created_at: str | None = None
    source: str = "mock"


def validate_process_snapshot(snapshot: ProcessSnapshot) -> tuple[bool, tuple[str, ...]]:
    """Validate a *snapshot* for internal consistency.

    Returns ``(valid, reasons)`` where *reasons* is empty when valid.
    """
    reasons: list[str] = []
    if snapshot.pid <= 0:
        reasons.append("pid_must_be_positive")
    if not snapshot.name or not snapshot.name.strip():
        reasons.append("name_must_be_non_empty")
    return (len(reasons) == 0, tuple(reasons))


# ===================================================================
# Known CST connection — a PID tracked by the recovery registry
# ===================================================================


@dataclass(frozen=True)
class KnownCstConnection:
    """A CST Design Environment connection known to the recovery registry.

    Parameters
    ----------
    pid : int
        Process ID of the CST DE.
    label : str
        Human-readable label (e.g. ``"workflow._conn"``).
    role : str
        Role string; default ``"design_environment"``.
    tracked_by : str
        Registry component that tracks this PID; default ``"retry_handler"``.
    active : bool
        Whether the connection is still considered active.
    """
    pid: int
    label: str
    role: str = "design_environment"
    tracked_by: str = "retry_handler"
    active: bool = True


# ===================================================================
# Process classification
# ===================================================================


@dataclass(frozen=True)
class ProcessClassification:
    """Result of classifying one process against known connections and policy.

    Parameters
    ----------
    pid : int
        Process ID of the classified process.
    name : str
        Process name.
    classification : str
        One of the required classification labels.
    protected : bool
        Whether this process must never be targeted for kill.
    kill_candidate : bool
        Whether this process could be a valid destructive-test target.
    reason : str
        Human-readable explanation of the classification decision.
    matched_connection_label : str or None
        If classification matched a ``KnownCstConnection``, its label.
    """
    pid: int
    name: str
    classification: str
    protected: bool
    kill_candidate: bool
    reason: str
    matched_connection_label: str | None = None


# ---- Classification constants ----------------------------------------------

LICENSE_DAEMON_PROTECTED = "license_daemon_protected"
KNOWN_DESIGN_ENVIRONMENT = "known_design_environment"
KNOWN_PID_UNEXPECTED_PROCESS = "known_pid_unexpected_process"
UNKNOWN_CST_PROCESS = "unknown_cst_process"
NON_CST_PROCESS = "non_cst_process"
INVALID_SNAPSHOT = "invalid_snapshot"

_ALLOWED_DE_NAMES = frozenset({
    "CSTDesignEnvironment.exe",
})

_PROTECTED_PROCESS_NAMES = frozenset({
    "cstd.exe",
})

# ---- Classifier ------------------------------------------------------------


def _lookup_connection(
    pid: int,
    known_connections: dict[int, KnownCstConnection],
) -> KnownCstConnection | None:
    """Look up a PID in *known_connections*; return the connection or None."""
    return known_connections.get(pid)


def classify_cst_process(
    process: ProcessSnapshot,
    known_connections: Iterable[KnownCstConnection],
) -> ProcessClassification:
    """Classify a single *process* against *known_connections* and safety policy.

    Parameters
    ----------
    process : ProcessSnapshot
        The process to classify.
    known_connections : iterable of KnownCstConnection
        PIDs tracked by the recovery registry.

    Returns
    -------
    ProcessClassification
    """
    # Validate snapshot first
    valid, reasons = validate_process_snapshot(process)
    if not valid:
        return ProcessClassification(
            pid=process.pid,
            name=process.name,
            classification=INVALID_SNAPSHOT,
            protected=True,
            kill_candidate=False,
            reason=f"invalid snapshot: {', '.join(reasons)}",
        )

    name_lower = process.name.lower()

    # Build lookup dict for known connections
    conn_map: dict[int, KnownCstConnection] = {
        c.pid: c for c in known_connections
    }

    # 1. License daemon — always protected
    if name_lower in {"cstd.exe", "cstd"}:
        return ProcessClassification(
            pid=process.pid,
            name=process.name,
            classification=LICENSE_DAEMON_PROTECTED,
            protected=True,
            kill_candidate=False,
            reason="license daemon is protected in all circumstances",
        )

    # 2. Non-CST process
    if not any(process.name.lower().startswith(p.lower().rstrip(".exe").split(".")[0])
               for p in _ALLOWED_DE_NAMES | _PROTECTED_PROCESS_NAMES):
        # Broader check: does the name contain "cst"?
        if "cst" not in name_lower:
            return ProcessClassification(
                pid=process.pid,
                name=process.name,
                classification=NON_CST_PROCESS,
                protected=False,
                kill_candidate=False,
                reason="process name does not appear to be CST-related",
            )

    # 3. Known PID — check process name matches allowed DE names
    conn = _lookup_connection(process.pid, conn_map)
    if conn is not None:
        # PID matched a known connection; verify the process name
        if process.name in _ALLOWED_DE_NAMES:
            if conn.active:
                return ProcessClassification(
                    pid=process.pid,
                    name=process.name,
                    classification=KNOWN_DESIGN_ENVIRONMENT,
                    protected=False,
                    kill_candidate=True,
                    reason="PID matches active known CST DE connection with allowed process name",
                    matched_connection_label=conn.label,
                )
            else:
                return ProcessClassification(
                    pid=process.pid,
                    name=process.name,
                    classification=KNOWN_DESIGN_ENVIRONMENT,
                    protected=False,
                    kill_candidate=False,
                    reason="PID matches inactive known CST DE connection (already closed)",
                    matched_connection_label=conn.label,
                )
        else:
            return ProcessClassification(
                pid=process.pid,
                name=process.name,
                classification=KNOWN_PID_UNEXPECTED_PROCESS,
                protected=True,
                kill_candidate=False,
                reason=(
                    f"PID matches known connection but process name {process.name!r} "
                    f"is not an allowed Design Environment executable"
                ),
                matched_connection_label=conn.label,
            )

    # 5. Unknown CST-like process
    return ProcessClassification(
        pid=process.pid,
        name=process.name,
        classification=UNKNOWN_CST_PROCESS,
        protected=True,
        kill_candidate=False,
        reason="CST-like process not tracked by registry; cannot positively identify",
    )


# ===================================================================
# Operator approval model
# ===================================================================


@dataclass(frozen=True)
class OperatorApproval:
    """Explicit operator approval for a destructive XR phase.

    Parameters
    ----------
    phase : str
        Approved phase identifier (e.g. ``"XR3"``).
    scenario : str
        Approved fault scenario ID from the taxonomy.
    max_evals : int
        Maximum CST evaluations allowed (1-3 for XR3/XR4).
    planned_taskkill_allowed : bool
        Whether manual taskkill is approved as a planned injection.
    emergency_cleanup_allowed : bool
        Whether emergency manual cleanup is allowed.
    protected_license_daemon_confirmed : bool
        Whether the operator confirms ``cstd.exe`` is protected.
    artifact_root : str or None
        Outside-repo path for DB, logs, etc.
    """
    phase: str
    scenario: str
    max_evals: int = 1
    planned_taskkill_allowed: bool = False
    emergency_cleanup_allowed: bool = False
    protected_license_daemon_confirmed: bool = False
    artifact_root: str | None = None


# ===================================================================
# Target selection
# ===================================================================


@dataclass(frozen=True)
class TargetSelection:
    """Result of evaluating whether a destructive action may proceed.

    Parameters
    ----------
    allowed : bool
        Whether the destructive action is permitted.
    target_pid : int or None
        The selected PID, if any.
    reason : str
        Summary of the decision.
    classification : ProcessClassification or None
        The classification of the target process.
    blocked_by : tuple of str
        List of reasons that blocked selection (empty when allowed).
    """
    allowed: bool
    target_pid: int | None
    reason: str
    classification: ProcessClassification | None = None
    blocked_by: tuple[str, ...] = ()


# ---- Allowed phase prefixes for destructive action -------------------------
_DESTRUCTIVE_ALLOWED_PHASE_PREFIXES = ("XR3", "XR4", "XR5")


def select_destructive_target(
    processes: Iterable[ProcessSnapshot],
    known_connections: Iterable[KnownCstConnection],
    *,
    requested_pid: int | None = None,
    scenario: ExtremeRecoveryFaultKind,
    approval: OperatorApproval | None = None,
) -> TargetSelection:
    """Evaluate whether a destructive action is permitted under *approval*.

    This helper returns a **decision only**.  It does not execute any
    destructive action, spawn processes, or call the OS.

    Parameters
    ----------
    processes : iterable of ProcessSnapshot
        Current process inventory.
    known_connections : iterable of KnownCstConnection
        Registry-tracked CST DE connections.
    requested_pid : int or None
        Specific PID to target, or None for auto-selection.
    scenario : ExtremeRecoveryFaultKind
        The fault scenario to simulate.
    approval : OperatorApproval or None
        Operator approval for this phase.  ``None`` blocks everything.

    Returns
    -------
    TargetSelection
    """
    blocked: list[str] = []

    # --- Gate 1: Approval exists ---
    if approval is None:
        return TargetSelection(
            allowed=False, target_pid=None,
            reason="no operator approval provided",
            blocked_by=("no_approval",),
        )

    # --- Gate 2: Phase prefix check ---
    if not any(approval.phase.startswith(prefix) for prefix in _DESTRUCTIVE_ALLOWED_PHASE_PREFIXES):
        blocked.append("phase_not_approved_for_destructive_action")

    # --- Gate 3: Scenario match ---
    if approval.scenario != scenario.value:
        blocked.append("scenario_mismatch")

    # --- Gate 4: Max evals within range ---
    if not (1 <= approval.max_evals <= 3):
        blocked.append("max_evals_out_of_range")

    # --- Gate 5: License daemon protected ---
    if not approval.protected_license_daemon_confirmed:
        blocked.append("license_daemon_not_confirmed")

    # --- Gate 6: Planned taskkill allowed ---
    if not approval.planned_taskkill_allowed:
        blocked.append("planned_taskkill_not_allowed")

    # --- Gate 7: License daemon scenario always blocked ---
    if scenario == ExtremeRecoveryFaultKind.LICENSE_DAEMON_MUST_NOT_KILL:
        blocked.append("license_daemon_scenario_always_blocked")

    # If already blocked, return early
    if blocked:
        return TargetSelection(
            allowed=False, target_pid=None,
            reason="target selection blocked", blocked_by=tuple(blocked),
        )

    # --- Classify processes ---
    conn_list = list(known_connections)
    classifications = [classify_cst_process(p, conn_list) for p in processes]

    # Find kill candidates
    kill_candidates = [c for c in classifications if c.kill_candidate]

    # --- Gate 8: Requested PID ---
    if requested_pid is not None:
        match = next((c for c in classifications if c.pid == requested_pid), None)
        if match is None:
            blocked.append("requested_pid_not_in_inventory")
        elif not match.kill_candidate:
            blocked.append("requested_pid_not_kill_candidate")
        else:
            return TargetSelection(
                allowed=True,
                target_pid=requested_pid,
                reason=f"requested PID {requested_pid} is a valid kill candidate",
                classification=match,
            )
        if blocked:
            return TargetSelection(
                allowed=False, target_pid=requested_pid,
                reason="requested PID rejected", blocked_by=tuple(blocked),
            )

    # --- Gate 9: Auto-select (no requested PID) ---
    if len(kill_candidates) == 0:
        blocked.append("no_kill_candidates_available")
    elif len(kill_candidates) == 1:
        target = kill_candidates[0]
        return TargetSelection(
            allowed=True,
            target_pid=target.pid,
            reason=f"auto-selected only kill candidate PID {target.pid}",
            classification=target,
        )
    else:
        blocked.append("multiple_kill_candidates_ambiguous")

    return TargetSelection(
        allowed=False, target_pid=None,
        reason="target selection blocked", blocked_by=tuple(blocked),
    )


# ===================================================================
# Process inventory diff
# ===================================================================


@dataclass(frozen=True)
class ProcessInventoryDiff:
    """Result of comparing a pre-run and post-run process inventory.

    Parameters
    ----------
    started_pids : tuple of int
        PIDs present in ``after`` but not in ``before``.
    ended_pids : tuple of int
        PIDs present in ``before`` but not in ``after``.
    remaining_known_de_pids : tuple of int
        Known active DE PIDs still running after run.
    remaining_unknown_cst_pids : tuple of int
        Unknown CST-like PIDs still running after run.
    protected_license_daemon_pids : tuple of int
        License daemon PIDs detected (always protected).
    orphan_candidate_pids : tuple of int
        Active or inactive known DE PIDs still running after cleanup
        that are not expected.
    summary : str
        Short human-readable summary.
    """
    started_pids: tuple[int, ...] = ()
    ended_pids: tuple[int, ...] = ()
    remaining_known_de_pids: tuple[int, ...] = ()
    remaining_unknown_cst_pids: tuple[int, ...] = ()
    protected_license_daemon_pids: tuple[int, ...] = ()
    orphan_candidate_pids: tuple[int, ...] = ()
    summary: str = ""


def diff_process_inventory(
    before: Iterable[ProcessSnapshot],
    after: Iterable[ProcessSnapshot],
    known_connections: Iterable[KnownCstConnection],
) -> ProcessInventoryDiff:
    """Compute a deterministic diff between pre-run and post-run inventories.

    Parameters
    ----------
    before : iterable of ProcessSnapshot
        Pre-run process snapshots.
    after : iterable of ProcessSnapshot
        Post-run process snapshots.
    known_connections : iterable of KnownCstConnection
        Registry-tracked CST DE connections.

    Returns
    -------
    ProcessInventoryDiff
    """
    conn_map: dict[int, KnownCstConnection] = {
        c.pid: c for c in known_connections
    }

    # Classify all processes
    conn_list = list(known_connections)
    before_classified = {
        p.pid: classify_cst_process(p, conn_list) for p in before
    }
    after_classified = {
        p.pid: classify_cst_process(p, conn_list) for p in after
    }

    before_pids = set(before_classified)
    after_pids = set(after_classified)

    started_pids = tuple(sorted(after_pids - before_pids))
    ended_pids = tuple(sorted(before_pids - after_pids))

    # Remaining known DE PIDs (active or inactive)
    remaining_known_de = [
        pid for pid, c in after_classified.items()
        if c.classification == KNOWN_DESIGN_ENVIRONMENT
    ]
    remaining_known_de_pids = tuple(sorted(remaining_known_de))

    # Remaining unknown CST-like PIDs
    remaining_unknown = [
        pid for pid, c in after_classified.items()
        if c.classification == UNKNOWN_CST_PROCESS
    ]
    remaining_unknown_cst_pids = tuple(sorted(remaining_unknown))

    # Protected license daemon PIDs
    license_daemon = [
        pid for pid, c in after_classified.items()
        if c.classification == LICENSE_DAEMON_PROTECTED
    ]
    protected_license_daemon_pids = tuple(sorted(license_daemon))

    # Orphan candidates: known DE PIDs that are still running but either
    # inactive (already closed) or not expected to persist after run.
    orphan_candidates = [
        pid for pid, c in after_classified.items()
        if c.classification == KNOWN_DESIGN_ENVIRONMENT
        and (
            not (conn_map.get(pid) and conn_map[pid].active)
            or pid in started_pids
        )
    ]
    # Also include remaining unknown CST processes as warnings (not as
    # kill candidates, but as orphan candidates for reporting).
    orphan_candidate_pids = tuple(sorted(orphan_candidates))

    # Build summary
    parts: list[str] = []
    if len(started_pids) > 0:
        parts.append(f"started={len(started_pids)}")
    parts.append(f"ended={len(ended_pids)}")
    parts.append(f"known_de={len(remaining_known_de_pids)}")
    if remaining_unknown_cst_pids:
        parts.append(f"unknown_cst={len(remaining_unknown_cst_pids)} (warning)")
    parts.append(f"orphan_candidates={len(orphan_candidate_pids)}")
    summary = "; ".join(parts)

    return ProcessInventoryDiff(
        started_pids=started_pids,
        ended_pids=ended_pids,
        remaining_known_de_pids=remaining_known_de_pids,
        remaining_unknown_cst_pids=remaining_unknown_cst_pids,
        protected_license_daemon_pids=protected_license_daemon_pids,
        orphan_candidate_pids=orphan_candidate_pids,
        summary=summary,
    )


# ===================================================================
# Emergency cleanup record
# ===================================================================


@dataclass(frozen=True)
class EmergencyCleanupRecord:
    """Audit record for an emergency manual cleanup action.

    Parameters
    ----------
    allowed_by_approval : bool
        Whether the operator approval permitted emergency cleanup.
    reason : str
        Human-readable explanation of why emergency cleanup was needed.
    target_pid : int or None
        PID that was killed, if a kill action was taken.
    command_summary : str or None
        Short description of the command used (e.g. ``"pid_specific_cleanup_redacted"``).
    timestamp : str or None
        ISO-format or similar timestamp of the action.
    residual_process_count : int or None
        Number of CST-related processes still running after cleanup.
    """
    allowed_by_approval: bool
    reason: str | None = None
    target_pid: int | None = None
    command_summary: str | None = None
    timestamp: str | None = None
    residual_process_count: int | None = None


def validate_emergency_cleanup_record(
    record: EmergencyCleanupRecord,
) -> tuple[bool, tuple[str, ...]]:
    """Validate an *EmergencyCleanupRecord* for completeness.

    Returns ``(valid, reasons)`` where *reasons* lists missing or
    inconsistent fields.
    """
    reasons: list[str] = []
    if not record.allowed_by_approval:
        reasons.append("emergency_cleanup_not_allowed_by_approval")
    if not record.reason or not record.reason.strip():
        reasons.append("reason_required")
    if record.command_summary and record.target_pid is None:
        reasons.append("target_pid_required_when_kill_command")
    if not record.timestamp:
        reasons.append("timestamp_required")
    if record.residual_process_count is None:
        reasons.append("residual_process_count_required")
    return (len(reasons) == 0, tuple(reasons))


# ===================================================================
# XR safety summary report model
# ===================================================================


def build_xr_safety_summary(
    scenario: ExtremeRecoveryFaultKind,
    approval: OperatorApproval | None = None,
    target_selection: TargetSelection | None = None,
    inventory_diff: ProcessInventoryDiff | None = None,
    emergency_cleanup: EmergencyCleanupRecord | None = None,
) -> Mapping[str, Any]:
    """Build a deterministic safety-summary mapping for reporting.

    This helper returns a **report model only**.  It does not execute
    any destructive action, call the OS, or spawn processes.

    Parameters
    ----------
    scenario : ExtremeRecoveryFaultKind
        The fault scenario under evaluation.
    approval : OperatorApproval or None
        Operator approval, if provided.
    target_selection : TargetSelection or None
        Result of ``select_destructive_target()``, if evaluated.
    inventory_diff : ProcessInventoryDiff or None
        Result of ``diff_process_inventory()``, if available.
    emergency_cleanup : EmergencyCleanupRecord or None
        Emergency cleanup record, if any emergency action occurred.

    Returns
    -------
    Mapping[str, Any]
        Deterministic dictionary suitable for logging or report generation.
    """
    # Determine safe-to-execute
    safe_to_execute = True
    reasons_not_safe: list[str] = []

    if approval is None:
        safe_to_execute = False
        reasons_not_safe.append("no_approval")

    if target_selection is None:
        safe_to_execute = False
        reasons_not_safe.append("no_target_selection")
    elif not target_selection.allowed:
        safe_to_execute = False
        reasons_not_safe.append(f"target_blocked: {target_selection.reason}")

    if approval is not None and not approval.protected_license_daemon_confirmed:
        safe_to_execute = False
        reasons_not_safe.append("license_daemon_not_confirmed")

    if emergency_cleanup is not None:
        valid, cleanup_reasons = validate_emergency_cleanup_record(emergency_cleanup)
        if not valid:
            safe_to_execute = False
            reasons_not_safe.append(f"invalid_emergency_cleanup: {','.join(cleanup_reasons)}")

    result: dict[str, Any] = {
        "scenario": scenario.value,
        "approved": approval is not None,
        "target_allowed": target_selection.allowed if target_selection is not None else False,
        "target_pid": target_selection.target_pid if target_selection is not None else None,
        "blocked_by": tuple(target_selection.blocked_by if target_selection is not None else ()),
        "protected_license_daemon_confirmed": (
            approval.protected_license_daemon_confirmed if approval is not None else False
        ),
        "orphan_candidate_count": (
            len(inventory_diff.orphan_candidate_pids) if inventory_diff is not None else None
        ),
        "emergency_cleanup_recorded": emergency_cleanup is not None,
        "safe_to_execute_destructive_action": safe_to_execute,
    }
    if reasons_not_safe:
        result["not_safe_reasons"] = tuple(reasons_not_safe)
    return result
