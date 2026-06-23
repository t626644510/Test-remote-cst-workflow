"""CST Studio Suite connection management.

Provides CSTConnection, the single entry point for all CST DesignEnvironment
interactions.  Uses the lazy ``init_cst_path()`` pattern from ``core``
(no side-effect sys.path mutation on import).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from types import TracebackType
from typing import Any

from . import init_cst_path
from .cleanup import verify_process_cleanup
from ..diagnostics import CSTConnectionLostError

_logger = logging.getLogger(__name__)

# ── Lazy imports: resolved when __init__ runs ─────────────────────────
_DE_CLASS = None  # DesignEnvironment class, populated on first use


def _ensure_cst_imported(library_path: str) -> None:
    """One-time CST library import with explicit sys.path setup."""
    global _DE_CLASS
    if _DE_CLASS is not None:
        return

    init_cst_path(library_path)

    try:
        import cst.interface  # noqa: F401
        from cst.interface import DesignEnvironment as DE
    except ImportError as e:
        raise ImportError(
            f"Failed to import cst.interface from '{library_path}'. "
            f"Verify CST Studio Suite is installed at that path. "
            f"Original error: {e}"
        ) from e

    _DE_CLASS = DE


# ---------------------------------------------------------------------------
# CSTConnection
# ---------------------------------------------------------------------------


class CSTConnection:
    """Manages the lifecycle of a CST Studio Suite DesignEnvironment.

    Usage as context manager::

        with CSTConnection(library_path="D:/CST/AMD64/python_cst_libraries") as conn:
            project = conn.open_project("C:/path/to/file.cst")
            # ... work with project ...
        # conn.close() called automatically, with PID verification

    Parameters
    ----------
    library_path : str
        Filesystem path to the CST Python library directory.
    mode : str
        Connection mode: ``"new"``, ``"any"``, or ``"any_or_new"`` (default).
    """

    def __init__(self, library_path: str, mode: str = "any_or_new") -> None:
        self._mode = mode
        self._de: Any = None
        _ensure_cst_imported(library_path)

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> CSTConnection:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection to a CST DesignEnvironment.

        When ``mode="any_or_new"`` and a stale DE from a crashed
        session is present, ``connect_to_any_or_new`` may time out
        trying to reach it.  We catch the timeout and force a fresh
        instance via ``DE.new()``.
        """
        if self._de is not None:
            return

        DE = _DE_CLASS

        if self._mode == "new":
            self._de = DE.new()
        elif self._mode == "any":
            self._de = DE.connect_to_any()
        else:
            try:
                self._de = DE.connect_to_any_or_new()
            except Exception:
                _logger.warning(
                    "connect_to_any_or_new failed (stale DE / COM issue?) "
                    "— forcing a fresh instance",
                    exc_info=True,
                )
                self._de = DE.new()

        if self._de is None:
            raise RuntimeError(
                f"Failed to connect to CST DesignEnvironment (mode={self._mode})"
            )

    @property
    def design_environment(self) -> Any:
        """Return the underlying ``DesignEnvironment`` instance (or ``None``)."""
        return self._de

    @property
    def is_connected(self) -> bool:
        """Return ``True`` if connected to a live DesignEnvironment."""
        return self._de is not None and self._de.is_connected()

    def set_quiet_mode(self, enable: bool = True) -> None:
        """Suppress / restore CST message boxes."""
        if self._de is not None:
            try:
                self._de.set_quiet_mode(enable)
            except Exception:
                _logger.debug("set_quiet_mode(%s) failed", enable, exc_info=True)

    def close(self, force: bool = False) -> None:
        """Close the DesignEnvironment with PID-verified cleanup.

        Three-phase shutdown:
        1. Call ``DesignEnvironment.close()`` with a 5 s timeout guard
           (COM calls to a killed process can hang indefinitely).
        2. Poll for process exit via ``verify_process_cleanup``.
        3. Always null the reference.

        Parameters
        ----------
        force : bool
            If ``True`` (use during Ctrl+C / KeyboardInterrupt), skips
            the graceful COM close and directly force-kills the CST
            process, then removes stale lock files.
        """
        de = self._de
        if de is None:
            return

        pid = self.pid

        if force:
            # Fast shutdown — skip graceful COM close, force-kill immediately
            _logger.info("Force-closing CST connection (PID=%s)", pid)
            if pid is not None:
                from .cleanup import force_kill_cst, kill_all_cst_processes
                if not force_kill_cst(pid):
                    _logger.warning(
                        "force_kill_cst failed for PID=%d — "
                        "falling back to kill_all_cst_processes",
                        pid,
                    )
                    kill_all_cst_processes()
                elif not verify_process_cleanup(pid, timeout_s=10.0):
                    _logger.warning(
                        "CST PID=%d still alive after force close; "
                        "falling back to process sweep",
                        pid,
                    )
                    kill_all_cst_processes()
            self._de = None
            return

        # Phase 1 — close the DesignEnvironment (with COM hang guard)
        _close_de_with_timeout(de, pid)

        # Phase 2 — verify the backend process actually exited
        if pid is not None:
            from .cleanup import force_kill_cst, kill_all_cst_processes
            if not verify_process_cleanup(pid, timeout_s=10.0):
                _logger.warning(
                    "CST process PID=%d did not exit within 10 s — "
                    "forcing termination",
                    pid,
                )
                # Retry force_kill up to 2 times with verification between
                killed = False
                for attempt in (1, 2):
                    if not force_kill_cst(pid):
                        continue
                    time.sleep(2.0)
                    if verify_process_cleanup(pid, timeout_s=5.0):
                        killed = True
                        break
                    _logger.warning(
                        "CST process PID=%d still alive after force_kill "
                        "attempt %d/2", pid, attempt,
                    )
                if not killed:
                    _logger.error(
                        "Failed to kill CST PID=%d after 2 attempts — "
                        "falling back to kill_all_cst_processes",
                        pid,
                    )
                    kill_all_cst_processes()

        # Phase 3 — always null the reference
        self._de = None

    def close_targeted(
        self,
        *,
        pid_override: int | None = None,
        timeout_s: float = 15.0,
    ) -> dict[str, Any]:
        """Stop only this connection's recorded CST process tree.

        This avoids the potentially hanging DesignEnvironment ``close`` COM
        call and never falls back to a machine-wide CST process sweep.
        It is intended for workflows that own a dedicated ``mode="new"``
        DesignEnvironment and have already explicitly saved/closed projects.
        """

        from .cleanup import force_kill_cst

        started = time.perf_counter()
        if pid_override and pid_override > 0:
            pid = pid_override
            pid_source = "override"
        else:
            pid = self.pid
            pid_source = "live"
        self._de = None
        if pid is None or pid <= 0:
            return {
                "success": False,
                "strategy": "targeted_process_tree",
                "com_close_attempted": False,
                "global_sweep_attempted": False,
                "pid": None,
                "pid_source": "unavailable",
                "force_kill_ok": False,
                "exit_verified": False,
                "elapsed_s": time.perf_counter() - started,
                "reason": "pid_unavailable",
            }
        force_kill_ok = force_kill_cst(pid)
        exit_verified = verify_process_cleanup(pid, timeout_s=timeout_s)
        return {
            "success": bool(force_kill_ok and exit_verified),
            "strategy": "targeted_process_tree",
            "com_close_attempted": False,
            "global_sweep_attempted": False,
            "pid": pid,
            "pid_source": pid_source,
            "force_kill_ok": force_kill_ok,
            "exit_verified": exit_verified,
            "elapsed_s": time.perf_counter() - started,
            "reason": "" if force_kill_ok and exit_verified else (
                "targeted_process_cleanup_failed"
            ),
        }

    def reconnect(self) -> None:
        """Close the current connection (if any) and establish a new one.

        Waits for the old process to fully exit before reconnecting.
        This replaces the old ``sleep(3)`` + blind reconnect pattern.
        """
        pid = self.pid

        if self._de is not None:
            try:
                self._de.close()
            except Exception:
                _logger.debug("close() during reconnect failed", exc_info=True)
            self._de = None

        # Wait for the old process to exit
        if pid is not None:
            if not verify_process_cleanup(pid, timeout_s=15.0):
                _logger.warning(
                    "Old CST process PID=%d still alive after 15 s during reconnect",
                    pid,
                )

        self.connect()

    # ------------------------------------------------------------------
    # Project operations
    # ------------------------------------------------------------------

    def open_project(self, path: str) -> CSTProject:
        """Open a ``.cst`` project file and return a ``CSTProject`` wrapper."""
        if not self.is_connected:
            raise CSTConnectionLostError("Not connected to a CST DesignEnvironment")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Project file not found: {path}")

        from .project import CSTProject  # lazy — avoids circular import

        prj = self._de.open_project(path)
        return CSTProject(prj)

    def get_open_projects(self, pattern: str = ".*") -> list[Any]:
        """Return open projects matching a regex pattern."""
        if not self.is_connected:
            return []
        return self._de.get_open_projects(pattern)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def version() -> str:
        """Return the CST version string."""
        global _DE_CLASS
        if _DE_CLASS is None:
            raise RuntimeError("CST not imported yet — create a CSTConnection first")
        return _DE_CLASS.version()

    @property
    def pid(self) -> int | None:
        """Process ID of the connected DesignEnvironment.

        Returns ``None`` if the DE is not connected or the connection
        has been lost (COM dead).
        """
        if self._de is None:
            return None
        try:
            return self._de.pid()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _close_de_with_timeout(de: Any, pid: int | None) -> None:
    """Call ``de.close()`` with a 5 s timeout guard.

    COM calls to a CST process that was killed by Ctrl+C can hang
    indefinitely.  This wrapper runs the close in a daemon thread and
    abandons it if it doesn't return within the timeout.
    """
    result = {"ok": False, "exc": None}

    def _do_close() -> None:
        try:
            de.close()
            result["ok"] = True
        except Exception as exc:
            result["exc"] = exc

    t = threading.Thread(target=_do_close, daemon=True)
    t.start()
    t.join(timeout=5.0)

    if t.is_alive():
        _logger.warning(
            "DesignEnvironment.close() hung (PID=%s) — abandoning COM thread. "
            "The CST process may need a manual taskkill.",
            pid,
        )
    elif result["exc"] is not None:
        _logger.warning(
            "DesignEnvironment.close() raised an exception (PID=%s)",
            pid,
            exc_info=result["exc"],
        )
