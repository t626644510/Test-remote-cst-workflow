"""Process and project cleanup utilities for CST Studio Suite.

Provides context managers and verification helpers to guarantee that
CST projects are closed, lock files are cleaned up, and orphaned
``modelerAMD64.exe`` processes are detected / terminated.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .project import CSTProject

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class ProjectCloser:
    """Context manager that guarantees ``project.close()`` is called on exit.

    Usage::

        with ProjectCloser(project, label="pre-filter"):
            # ... work that may raise ...
        # project.close() is called here, even on exception
    """

    def __init__(self, project: CSTProject, label: str = "") -> None:
        self._project = project
        self._label = label

    def __enter__(self) -> CSTProject:
        return self._project

    def __exit__(self, *exc_info: object) -> None:
        try:
            self._project.close()
        except Exception:
            _logger.warning(
                "Failed to close project%s during cleanup",
                f" ({self._label})" if self._label else "",
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Process verification
# ---------------------------------------------------------------------------


def verify_process_cleanup(pid: int, timeout_s: float = 10.0) -> bool:
    """Wait for a CST process to exit; return ``True`` if it exited cleanly.

    Polls ``tasklist /PID <pid>`` on Windows.  Returns ``False`` if the
    process is still alive after *timeout_s* seconds.

    Parameters
    ----------
    pid : int
        Process ID to monitor.
    timeout_s : float
        Maximum time to wait (seconds).  Poll interval is 0.5 s.
    """
    if pid <= 0:
        return True  # no pid to wait for

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _process_exists(pid):
            return True
        time.sleep(0.5)

    return False


def force_kill_cst(pid: int) -> bool:
    """Terminate a stuck CST process.

    Parameters
    ----------
    pid : int
        Windows process ID to kill.

    Returns
    -------
    bool
        ``True`` if the process was successfully terminated or was not
        found (already dead), ``False`` if termination failed.
    """
    if pid <= 0:
        return True

    try:
        # /F = force, /T = tree kill (child processes too)
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            # Exit code 128 = "process not found" = already dead → success
            if result.returncode == 128:
                _logger.info("CST process PID=%d was already dead", pid)
                return True
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            _logger.error(
                "taskkill returned exit code %d for PID=%d. stderr=%r stdout=%r",
                result.returncode, pid, stderr[:200], stdout[:200],
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        _logger.warning("taskkill timed out for CST process PID=%d", pid)
        return False
    except Exception:
        _logger.warning("Failed to force-kill CST process PID=%d", pid, exc_info=True)
        return False


def find_lock_file(project_dir: str) -> str | None:
    """Check for a stray ``ProjectDir.lock`` file in a project directory.

    Returns the full path if found, ``None`` otherwise.
    """
    lock_path = os.path.join(project_dir, "ProjectDir.lock")
    return lock_path if os.path.isfile(lock_path) else None


def remove_lock_file(project_dir: str) -> bool:
    """Safely remove a ``ProjectDir.lock`` if it exists.

    Returns ``True`` on success or if the file did not exist.
    """
    lock_path = os.path.join(project_dir, "ProjectDir.lock")
    try:
        if os.path.isfile(lock_path):
            os.remove(lock_path)
            _logger.info("Removed stale lock file: %s", lock_path)
        return True
    except OSError:
        _logger.warning("Failed to remove lock file: %s", lock_path, exc_info=True)
        return False


def remove_result_folder(project_path: str) -> bool:
    """Delete the CST result folder associated with a project file.

    CST stores results in a folder named after the project (without the
    ``.cst`` extension).  Removing it forces CST to regenerate the folder,
    which can resolve corrupted cached results.

    For example, ``F:/workflow/PickupDesign.cst`` →
    ``F:/workflow/PickupDesign/``.

    Returns ``True`` if the folder was deleted, ``False`` if it did not
    exist or could not be removed.
    """
    folder = os.path.splitext(project_path)[0]
    if not os.path.isdir(folder):
        return False
    try:
        shutil.rmtree(folder)
        _logger.info("Removed CST result folder: %s", folder)
        return True
    except OSError:
        _logger.debug("Failed to remove result folder: %s", folder, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Kill all CST processes
# ---------------------------------------------------------------------------

# Processes that don't start with "CST" but are part of the CST toolchain.
# Add entries as ``"exe_name.exe"`` — they will be killed by exact image name.
CST_RELATED_PROCESSES: list[str] = [
    "modelerAMD64.exe",  # CST modelling / solver engine (no "CST" prefix)
    # Add other known CST sub-processes below:
    # "PostProcessor.exe",
    # "CSTUpdater.exe",
]

# Process names that must NEVER be killed (e.g. license server).
# Applies to both Pass 1 (prefix scan) and Pass 2 (exact-name kill).
CST_PROCESS_WHITELIST: set[str] = {"cstd.exe"}


def kill_all_cst_processes(extra_names: list[str] | None = None) -> int:
    """Kill all CST-related processes on the system.

    Two-pass strategy:

    1. Enumerate processes via ``tasklist``, filter those whose image name
       starts with ``"CST"`` (case-insensitive), and kill them by PID.
    2. Kill each entry in `CST_RELATED_PROCESSES`_ plus *extra_names*
       via ``taskkill /F /IM <name>``.

    Parameters
    ----------
    extra_names : list[str] or None
        Additional process image names to kill on this call.

    Returns
    -------
    int
        Total number of processes killed (best-effort count).
    """
    killed = 0
    names_to_kill = list(CST_RELATED_PROCESSES)
    if extra_names:
        names_to_kill.extend(extra_names)

    # Pass 1: kill by "CST" prefix
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.replace('"', "").split(",")
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            pid_str = parts[1].strip()
            if name.upper().startswith("CST") and pid_str.isdigit():
                if name.lower() in CST_PROCESS_WHITELIST:
                    continue
                pid = int(pid_str)
                _logger.info("Killing CST process: %s (PID=%s)", name, pid)
                if force_kill_cst(pid):
                    killed += 1
    except Exception:
        _logger.warning("Failed to enumerate CST processes by prefix", exc_info=True)

    # Pass 2: kill by exact image name
    for exe_name in names_to_kill:
        if exe_name.lower() in CST_PROCESS_WHITELIST:
            continue
        try:
            sub_result = subprocess.run(
                ["taskkill", "/F", "/IM", exe_name],
                capture_output=True, text=True, timeout=10,
            )
            if sub_result.returncode == 0:
                _logger.info("Killed process by name: %s", exe_name)
                killed += 1
        except Exception:
            _logger.warning("Failed to kill process '%s'", exe_name, exc_info=True)

    return killed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _process_exists(pid: int) -> bool:
    """Return ``True`` if a process with *pid* is running on Windows."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        # On any error, assume the process might still be alive
        return True
