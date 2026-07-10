# CST cleanup diagnostics helpers (no-CST).
# Pure diagnostic classification — no process manipulation, no CST imports,
# no kill calls, no file I/O.  Used to identify orphan design-environment
# windows after workflow cleanup, distinguishing them from the licensing
# service (cstd.exe) which should remain running.
#
# Phase P1 — Cleanup reliability gap analysis / hardening plan.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Process-name constants (case-insensitive, extension-stripped matching)
# ---------------------------------------------------------------------------

_LICENSING_SERVICE_NAMES: frozenset[str] = frozenset({
    "cstd",
})

_DESIGN_ENVIRONMENT_NAMES: frozenset[str] = frozenset({
    "cst_design_environment_amd64",
    "cst_design_environment",
})


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class CstProcessInfo:
    """Diagnostic information about a CST-related process.

    Parameters
    ----------
    pid : int
        Process ID.
    process_name : str
        Process name as reported by the OS (e.g. ``"cstd.exe"``,
        ``"CST DESIGN ENVIRONMENT_AMD64"``).
    has_window_title : bool
        Whether the process has a visible window.
    main_window_title : str
        The window title (if any).
    """
    pid: int = 0
    process_name: str = ""
    has_window_title: bool = False
    main_window_title: str = ""


# ---------------------------------------------------------------------------
# Process classification
# ---------------------------------------------------------------------------


def _normalise_process_name(name: str) -> str:
    """Lower-case, strip, remove ``.exe`` suffix."""
    raw = name.strip().lower()
    if raw.endswith(".exe"):
        raw = raw[:-4]
    return raw


def classify_cst_process(
    process_name: str,
    *,
    has_window_title: bool = False,
    main_window_title: str = "",
) -> str:
    """Classify a CST-related process by name and window state.

    Returns one of:
    - ``"licensing_service"`` — ``cstd.exe`` (background licensing daemon).
    - ``"design_environment"`` — CST Design Environment GUI process.
    - ``"unknown"`` — unrecognised process name.

    Parameters
    ----------
    process_name : str
        Raw process name from the OS.
    has_window_title : bool
        Whether the process has a visible window (informational only;
        does not change the classification result).
    main_window_title : str
        Window title (informational only; does not change classification).

    Returns
    -------
    str
        One of the three classification strings.

    Raises
    ------
    ValueError
        If *process_name* is empty or whitespace-only.
    """
    if not process_name or not process_name.strip():
        raise ValueError(
            f"process_name must be non-empty, got {process_name!r}",
        )

    normalised = _normalise_process_name(process_name)

    if normalised in _LICENSING_SERVICE_NAMES:
        return "licensing_service"

    if normalised in _DESIGN_ENVIRONMENT_NAMES:
        return "design_environment"

    # Heuristic: any name containing both "cst" and "design" is very likely
    # a design environment variant not in the known set.
    if "cst" in normalised and "design" in normalised:
        return "design_environment"

    return "unknown"


# ---------------------------------------------------------------------------
# Orphan DE detection
# ---------------------------------------------------------------------------


def should_force_kill_orphan_de(
    process_info: CstProcessInfo,
    *,
    workflow_claimed_closed: bool = False,
) -> tuple[bool, str]:
    """Determine whether a CST process is an orphan DE that needs force-kill.

    No actual kill is performed — this is purely diagnostic.

    Conservative policy:
    - Invalid PID (≤ 0) or empty process name → never kill.
    - Licensing service (``cstd.exe``) → never kill.
    - Unknown process type → never kill.
    - Design environment with visible window → always orphan candidate
      (the workflow should have closed it).
    - Design environment without visible window → orphan candidate only
      if *workflow_claimed_closed* is ``True`` (the process was left behind
      even though cleanup was attempted).
    - Design environment without visible window and cleanup not yet
      claimed → not an orphan; process may be starting or idle.

    Returns
    -------
    tuple[bool, str]
        ``(should_kill, reason)``.
    """
    if process_info.pid <= 0:
        return False, "invalid or missing PID"

    if not process_info.process_name or not process_info.process_name.strip():
        return False, "empty process name"

    cls = classify_cst_process(
        process_info.process_name,
        has_window_title=process_info.has_window_title,
        main_window_title=process_info.main_window_title,
    )

    if cls == "licensing_service":
        return False, "licensing service must remain running"

    if cls == "unknown":
        return False, "unknown process type; conservative skip"

    # cls == "design_environment"
    if process_info.has_window_title:
        return True, "DE window still present after workflow cleanup"
    if workflow_claimed_closed:
        return True, "DE process without window after claimed cleanup"
    return False, "DE process without window, cleanup not yet claimed"


# ---------------------------------------------------------------------------
# Cleanup observation summary
# ---------------------------------------------------------------------------


def summarize_cleanup_observation(
    *,
    workflow_claimed_closed: bool = False,
    workflow_pid: int | None = None,
    remaining_processes: list[CstProcessInfo] | None = None,
) -> dict[str, Any]:
    """Summarise a cleanup observation for diagnostic / reporting.

    No file I/O, no CST imports, no process manipulation.

    Parameters
    ----------
    workflow_claimed_closed : bool
        Whether the workflow cleanup routine reported success.
    workflow_pid : int or None
        The PID of the workflow's CST connection (if known).
    remaining_processes : list of CstProcessInfo or None
        List of CST-related processes still present after cleanup.

    Returns
    -------
    dict
        With keys:
        - ``workflow_claimed_closed`` (bool)
        - ``workflow_pid`` (int or None)
        - ``remaining_count`` (int)
        - ``orphan_candidates`` (list of dicts with pid, process_name,
          has_window_title, reason)
        - ``summary`` (str)
    """
    if remaining_processes is None:
        remaining_processes = []

    orphan_candidates: list[dict[str, Any]] = []
    for proc in remaining_processes:
        should_kill, reason = should_force_kill_orphan_de(
            proc, workflow_claimed_closed=workflow_claimed_closed,
        )
        if should_kill:
            orphan_candidates.append({
                "pid": proc.pid,
                "process_name": proc.process_name,
                "has_window_title": proc.has_window_title,
                "reason": reason,
            })

    total = len(remaining_processes)
    orphan_count = len(orphan_candidates)

    if orphan_count > 0:
        plural_proc = "es" if total != 1 else ""
        plural_orph = "s" if orphan_count != 1 else ""
        summary = (
            f"{orphan_count}/{total} process{plural_proc} identified as "
            f"orphan DE candidate{plural_orph}"
        )
    elif total == 0:
        summary = "no remaining CST processes"
    else:
        plural = "es" if total != 1 else ""
        summary = f"{total} process{plural} remaining, none orphan"

    return {
        "workflow_claimed_closed": workflow_claimed_closed,
        "workflow_pid": workflow_pid,
        "remaining_count": total,
        "orphan_candidates": orphan_candidates,
        "summary": summary,
    }
