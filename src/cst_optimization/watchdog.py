"""External watchdog process — monitors a workflow subprocess and restarts
it on unexpected termination, enabling checkpoint-based resume.

Usage (standalone)::

    python -m cst_optimization.watchdog -- run_workflow_2.py

Usage (programmatic)::

    from cst_optimization.watchdog import WatchdogConfig, WatchdogRunner
    wd = WatchdogRunner(WatchdogConfig(max_restarts=5, cooldown_s=30))
    wd.run(["python", "run_workflow_2.py"], ckpt_path="D:/Results/checkpoint")
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Sequence

_logger = logging.getLogger(__name__)


@dataclass
class WatchdogConfig:
    """Configuration for ``WatchdogRunner``.

    Attributes
    ----------
    max_restarts : int
        Maximum number of automatic restarts before giving up (default 5).
    cooldown_s : float
        Seconds to wait between process death and restart (default 30).
        Gives CST processes time to fully terminate and release file locks.
    """

    max_restarts: int = 5
    cooldown_s: float = 30.0


class WatchdogRunner:
    """Launch a workflow subprocess and restart it on crash.

    The subprocess is expected to be checkpoint-aware: it loads a
    checkpoint on startup (if present), saves progress after each
    evaluation, and exits with code 0 on normal completion.
    """

    def __init__(self, config: WatchdogConfig | None = None) -> None:
        self._cfg = config or WatchdogConfig()
        self._restarts = 0
        self._killed = False
        signal.signal(signal.SIGINT, self._on_sigint)
        signal.signal(signal.SIGTERM, self._on_sigint)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, cmd: Sequence[str]) -> int:
        """Launch *cmd* and restart on non-zero exit.

        Parameters
        ----------
        cmd : sequence of str
            The command to run, e.g. ``["python", "run_workflow_2.py"]``.

        Returns
        -------
        int
            Exit code: 0 on success, 1 if max restarts exceeded,
            130 if killed by user (Ctrl+C).
        """
        while self._restarts <= self._cfg.max_restarts:
            if self._killed:
                print("\nWatchdog: killed by user.", flush=True)
                return 130

            tag = f"[restart {self._restarts}/{self._cfg.max_restarts}]" if self._restarts > 0 else "[start]"
            print(f"Watchdog {tag} launching: {' '.join(cmd)}", flush=True)
            _logger.info("Watchdog %s launching: %s", tag, cmd)

            proc = subprocess.Popen(
                cmd,
                stdout=sys.stdout,
                stderr=sys.stderr,
                stdin=subprocess.DEVNULL,
            )

            try:
                ret = proc.wait()
                self._cleanup_cst()
            except KeyboardInterrupt:
                # Forward Ctrl+C to child, then wait for it
                print("\nWatchdog: Ctrl+C — signaling child process...", flush=True)
                self._killed = True
                try:
                    proc.send_signal(signal.SIGINT)
                    proc.wait(timeout=30)
                except Exception:
                    proc.kill()
                    proc.wait()
                return 130

            if ret == 0:
                print(f"Watchdog: child exited 0 — done.", flush=True)
                _logger.info("Watchdog: child exited 0")
                return 0

            self._restarts += 1
            print(
                f"Watchdog: child exited {ret} — "
                f"restarting in {self._cfg.cooldown_s:.0f}s "
                f"({self._restarts}/{self._cfg.max_restarts})",
                flush=True,
            )
            _logger.warning(
                "Watchdog: child exited %d — restart %d/%d after %.0fs cooldown",
                ret, self._restarts, self._cfg.max_restarts, self._cfg.cooldown_s,
            )

            if self._restarts > self._cfg.max_restarts:
                print(
                    f"Watchdog: max restarts ({self._cfg.max_restarts}) exceeded — giving up.",
                    flush=True,
                )
                _logger.error("Watchdog: max restarts exceeded")
                self._cleanup_cst()
                return 1

            time.sleep(self._cfg.cooldown_s)

        self._cleanup_cst()
        return 1  # unreachable

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _cleanup_cst() -> None:
        """Kill any remaining CST processes as a belt-and-suspenders cleanup."""
        try:
            from cst_optimization.core.cleanup import kill_all_cst_processes
            kill_all_cst_processes()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _on_sigint(self, signum: int, frame: object) -> None:
        del signum, frame
        self._killed = True


# ---------------------------------------------------------------------------
# CLI entry point  (python -m cst_optimization.watchdog -- script.py)
# ---------------------------------------------------------------------------


def _main() -> None:
    """Parse ``--`` separated arguments and run the watchdog."""
    args = sys.argv[1:]
    try:
        sep = args.index("--")
    except ValueError:
        print(
            "Usage: python -m cst_optimization.watchdog -- <workflow_script> [args...]",
            file=sys.stderr,
        )
        sys.exit(2)

    cmd = [sys.executable] + args[sep + 1:]

    # Optional --max-restarts and --cooldown before --
    pre = args[:sep]
    cfg = WatchdogConfig()
    it = iter(pre)
    for a in it:
        if a == "--max-restarts":
            cfg.max_restarts = int(next(it))
        elif a == "--cooldown":
            cfg.cooldown_s = float(next(it))
        else:
            print(f"Unknown watchdog option: {a}", file=sys.stderr)
            sys.exit(2)

    wd = WatchdogRunner(cfg)
    sys.exit(wd.run(cmd))


if __name__ == "__main__":
    _main()
