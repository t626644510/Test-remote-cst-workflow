"""Read-only, exact-PID recovery gate for campaign-owned CST sessions.

This module never imports CST, connects to a process, or terminates anything.
An occupied/reused PID is conservatively treated as alive; ownership is never
inferred from executable names. Unknown process state blocks automatic resume.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Callable, Literal

PidState = Literal["alive", "absent", "unknown"]


class SessionRecoveryBlocked(RuntimeError):
    """An earlier owned session is alive or cannot be proved inactive."""


def _query_windows_pid(pid: int, kernel32: object, last_error: Callable[[], int]) -> PidState:
    """Probe one exact PID using a wait-only handle; injectable for offline tests."""
    # SYNCHRONIZE grants waiting, not termination or process manipulation.
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        # Windows reports ERROR_INVALID_PARAMETER for a PID that no longer exists.
        return "absent" if last_error() == 87 else "unknown"
    try:
        result = kernel32.WaitForSingleObject(handle, 0)
        if result == 0:  # WAIT_OBJECT_0: process has exited.
            return "absent"
        if result == 258:  # WAIT_TIMEOUT: process remains alive.
            return "alive"
        return "unknown"
    finally:
        kernel32.CloseHandle(handle)


def query_pid(pid: int) -> PidState:
    """Return exact PID liveness, failing closed on unsupported hosts/errors."""
    if isinstance(pid, bool) or not isinstance(pid, int) or not 0 < pid <= 0xFFFFFFFF:
        return "unknown"
    if os.name != "nt":
        return "unknown"
    try:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        return _query_windows_pid(pid, kernel32, ctypes.get_last_error)
    except Exception:
        return "unknown"


def ensure_sessions_inactive(evaluation_dir: Path, *, probe: Callable[[int], PidState] | None = None) -> None:
    """Refuse recovery until every recorded session is known to be inactive.

    New cleanup certificates require the same UUID, PID, and project plus a
    verified exit. Legacy records have no UUID: even an old cleanup-success
    record is insufficient, and the exact recorded PID is conservatively probed.
    """
    probe = probe or query_pid
    # Fresh station-wide absence certificates close unknown-PID startup records.
    # They never authorize termination; every exact session digest must match.
    from .io import digest
    certificate = Path(evaluation_dir)/'station_quiescence.json'
    absence = {}
    if certificate.exists():
        try: absence = json.loads(certificate.read_text(encoding='utf-8'))
        except (OSError, ValueError): pass
    for record_path in sorted(Path(evaluation_dir).glob("attempt_*/*_session.json")):
        try:
            session = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(session, dict):
                raise ValueError("session must be an object")
        except Exception as exc:
            raise SessionRecoveryBlocked(f"Cannot read session record {record_path}: {exc}") from exc
        relative = str(record_path.relative_to(evaluation_dir))
        if (absence.get('kind') == 'read_only_global_absence'
            and absence.get('processes') == []
            and absence.get('session_hashes', {}).get(relative) == digest(record_path)
            and absence.get('observed_at', 0) >= record_path.stat().st_mtime):
            continue
        cleanup_path = record_path.with_name(record_path.name.replace("_session.json", "_cleanup.json"))
        cleanup = {}
        if cleanup_path.exists():
            try:
                cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
                if not isinstance(cleanup, dict):
                    cleanup = {}
            except (OSError, ValueError):
                cleanup = {}
        token, pid = session.get("session_id"), session.get("pid")
        associated = (isinstance(token, str) and bool(token)
                      and cleanup.get("session_id") == token
                      and cleanup.get("pid") == pid
                      and cleanup.get("project") == session.get("project"))
        if associated and cleanup.get("success") is True:
            if cleanup.get("exit_verified") is True and isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                continue
            if pid is None and cleanup.get("no_session_started") is True:
                continue
        valid_pid = isinstance(pid, int) and not isinstance(pid, bool) and 0 < pid <= 0xFFFFFFFF
        try:
            status = probe(pid) if valid_pid else "unknown"
        except Exception:
            status = "unknown"
        if status != "absent":
            raise SessionRecoveryBlocked(
                f"Recorded CST session {record_path.name} PID={pid!r} is {status}; "
                "pending evaluation and consumed solve budget are preserved. "
                "No new CST session was started. Confirm the old session has exited before resuming."
            )
