"""Three-tier escalation retry handler for transient CST errors.

Tier 1 — Simple retry (same connection):
    Retry the evaluation without modifying any state.  Suitable for
    transient COM timeouts or occasional mesh failures.

Tier 2 — Kill CST + reconnect:
    Terminate all CST processes, create a fresh ``DesignEnvironment``
    with ``mode="new"``, and retry.  Suitable when the COM connection
    is dead or the process is a zombie.

Tier 3 — Kill CST + clean result folder + reconnect:
    Tier 2 plus deletion of the CST result folder (the directory next to
    the ``.cst`` file with the same basename).  Suitable when cached
    results are corrupted (e.g. ``ResultItem does not exist`` errors).

All tiers exhausted → skip the evaluation and return an error record.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

import numpy as np

from .cleanup import (
    force_kill_cst, kill_all_cst_processes, remove_lock_file,
    remove_result_folder, verify_process_cleanup,
)
from .connection import CSTConnection
from .timeout import EvaluationTimeoutError, run_with_wall_clock_timeout

_logger = logging.getLogger(__name__)


class RetryTier(Enum):
    """The tier at which a retry succeeded (or ``EXHAUSTED``)."""

    TIER1 = 1       # simple retry
    TIER2 = 2       # kill + reconnect
    TIER3 = 3       # kill + clean + reconnect
    EXHAUSTED = 0   # all tiers failed


@dataclass
class RetryConfig:
    """Configuration for ``EvaluationRetryHandler``.

    Attributes
    ----------
    enabled : bool
        Master switch.
    max_tier1 : int
        Number of simple retries on the same connection (default 3).
    max_tier2 : int
        Number of retries after killing CST and reconnecting (default 2).
        Tier 3 is always exactly 1 attempt.
    evaluation_timeout_s : float
        Wall-clock timeout per evaluation attempt (default 600 s).
        When exceeded the handler triggers Tier 3 recovery automatically.
    """

    enabled: bool = True
    max_tier1: int = 3
    max_tier2: int = 2
    max_tier3: int = 1
    evaluation_timeout_s: float = 600.0
    cooldown_s: float = 5.0


class EvaluationRetryHandler:
    """Three-tier escalation retry for workflow-3 evaluations.

    Wraps an ``evaluate(params, iteration) -> EvaluationResult`` callable
    and retries when the result status is retryable (``COM_LOST`` or
    ``SOLVER_FAILED``).

    Parameters
    ----------
    connection : CSTConnection
        The active CST connection (will be replaced on Tier 2/3).
    project_path : str
        Path to the ``.cst`` file (used for result-folder cleanup).
    library_path : str
        Path to the CST Python libraries (for creating new connections).
    config : RetryConfig or None
    on_reconnect : callable or None
        ``f(new_connection: CSTConnection)`` — called after Tier 2/3
        reconnection so the evaluator can update its internal reference.
    """

    def __init__(
        self,
        connection: CSTConnection,
        project_path: str,
        library_path: str,
        config: RetryConfig | None = None,
        on_reconnect: Callable[[CSTConnection], None] | None = None,
        connection_factory: Callable[[], CSTConnection] | None = None,
        extra_result_paths: list[str] | None = None,
    ) -> None:
        self._conn = connection
        self._project_path = project_path
        self._library_path = library_path
        self._config = config or RetryConfig()
        self._on_reconnect = on_reconnect
        self._connection_factory = connection_factory
        self._evaluation_timeout_s = self._config.evaluation_timeout_s
        self._extra_result_paths = list(extra_result_paths) if extra_result_paths else []
        self._all_connections: list[CSTConnection] = [connection]

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def close_all(self, force: bool = True) -> None:
        """Close every CST connection created by this handler.

        Call during cleanup to prevent orphan CST processes after Tier 2/3
        escalation creates fresh connections.
        """
        for c in self._all_connections:
            try:
                c.close(force=force)
            except Exception:
                pass
        self._all_connections.clear()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        evaluate_fn: Callable[[np.ndarray, int], Any],
        params: np.ndarray,
        iteration: int,
    ) -> tuple[Any, RetryTier]:
        """Evaluate, retrying on transient failures with escalating tiers.

        Each ``evaluate_fn`` call is wrapped in a wall-clock timeout.
        When the timeout fires the handler performs Tier-3 recovery
        automatically and the attempt is treated as a retryable COM_LOST.

        Parameters
        ----------
        evaluate_fn : callable
            ``f(params, iteration) -> EvaluationResult``.
        params : np.ndarray
            Physical-space parameter vector.
        iteration : int
            Evaluation index (for logging).

        Returns
        -------
        (result, tier) : (EvaluationResult, RetryTier)
            ``tier`` is the tier at which the evaluation finally succeeded,
            or ``EXHAUSTED`` if all tiers failed.
        """
        # Import here to avoid circular dependency at module level
        from ..workflows.recovery import EvaluationStatus  # noqa: F811

        RETRYABLE = {EvaluationStatus.COM_LOST, EvaluationStatus.SOLVER_FAILED}

        def _timed_eval(fn, p, it, timeout_override=None):
            """Call *fn(p, it)* with a wall-clock timeout, using the
            ultimate recovery (kill + clean + reconnect) if it hangs."""
            t = (timeout_override if timeout_override is not None
                 else self._evaluation_timeout_s)

            def _on_hang():
                _logger.error(
                    "Wall-clock timeout (%.1f s) for iteration %d — "
                    "Executing ultimate recovery (force kill + clean + reconnect).",
                    t, it,
                )
                self._kill_and_clean()
                # After cleanup, rebuild connection so subsequent retries work
                self._conn = self._make_new_connection()
                if self._on_reconnect is not None:
                    self._on_reconnect(self._conn)

            return run_with_wall_clock_timeout(
                fn, args=(p, it), timeout_s=t, on_timeout=_on_hang,
            )

        try:
            result = _timed_eval(evaluate_fn, params, iteration)
        except EvaluationTimeoutError:
            _logger.warning(
                "Evaluation timed out for iteration %d after %.1f s; "
                "recovery executed, treating as COM_LOST",
                iteration, self._evaluation_timeout_s,
            )
            result = _make_com_lost_result(
                f"Timed out after {self._evaluation_timeout_s:.0f} s"
            )

        if result.status not in RETRYABLE:
            return result, RetryTier.TIER1

        # ── Tier 1: simple retry ──────────────────────────────────────
        for attempt in range(1, self._config.max_tier1 + 1):
            _logger.warning(
                "Tier 1 retry %d/%d for iteration %d: %s",
                attempt, self._config.max_tier1, iteration, result.status.value,
            )
            try:
                result = _timed_eval(evaluate_fn, params, iteration)
            except EvaluationTimeoutError:
                _logger.warning(
                    "Tier 1 retry %d timed out for iteration %d",
                    attempt, iteration,
                )
                result = _make_com_lost_result(
                    f"Timed out during Tier 1 retry {attempt}"
                )
            if result.status not in RETRYABLE:
                _logger.info(
                    "Tier 1 succeeded on attempt %d for iteration %d", attempt, iteration,
                )
                return result, RetryTier.TIER1

        _logger.warning(
            "Tier 1 exhausted for iteration %d after %d attempts",
            iteration, self._config.max_tier1,
        )

        # ── Tier 2: graceful close + clean + reconnect ──────────────
        if self._config.max_tier2 > 0:
            self._graceful_clean_and_reconnect()
            for attempt in range(1, self._config.max_tier2 + 1):
                _logger.warning(
                    "Tier 2 retry %d/%d for iteration %d",
                    attempt, self._config.max_tier2, iteration,
                )
                try:
                    result = _timed_eval(evaluate_fn, params, iteration)
                except EvaluationTimeoutError:
                    _logger.warning(
                        "Tier 2 retry %d timed out for iteration %d",
                        attempt, iteration,
                    )
                    result = _make_com_lost_result(
                        f"Timed out during Tier 2 retry {attempt}"
                    )
                if result.status not in RETRYABLE:
                    _logger.info(
                        "Tier 2 succeeded on attempt %d for iteration %d", attempt, iteration,
                    )
                    return result, RetryTier.TIER2

            _logger.warning(
                "Tier 2 exhausted for iteration %d after %d attempts",
                iteration, self._config.max_tier2,
            )
        else:
            _logger.info("Tier 2 disabled (max_tier2=0), escalating to Tier 3")

        # ── Tier 3: kill + clean result folder + new connection ───────
        for attempt in range(1, self._config.max_tier3 + 1):
            _logger.warning(
                "Tier 3 attempt %d/%d for iteration %d: cleaning result folder and reconnecting",
                attempt, self._config.max_tier3, iteration,
            )
            self._kill_and_clean()
            try:
                result = _timed_eval(evaluate_fn, params, iteration)
            except EvaluationTimeoutError:
                _logger.error(
                    "Tier 3 attempt %d timed out for iteration %d",
                    attempt, iteration,
                )
                result = _make_com_lost_result(
                    f"Timed out during Tier 3 attempt {attempt}"
                )
            if result.status not in RETRYABLE:
                _logger.info(
                    "Tier 3 succeeded on attempt %d for iteration %d", attempt, iteration,
                )
                return result, RetryTier.TIER3

        _logger.warning(
            "Tier 3 exhausted for iteration %d after %d attempts",
            iteration, self._config.max_tier3,
        )

        # ── All tiers exhausted ───────────────────────────────────────
        _logger.error(
            "All retry tiers exhausted for iteration %d: %s. Skipping.",
            iteration, result.status.value,
        )
        return result, RetryTier.EXHAUSTED

    def force_reset(self) -> None:
        """Proactive graceful reset for per-evaluation recovery.

        Normal close (no force kill), remove result folder, reconnect —
        preserving the license server and avoiding Qt6 crashes.
        """
        _logger.info("Proactive graceful reset requested")
        self._graceful_clean_and_reconnect()

    # ------------------------------------------------------------------
    # Escalation actions
    # ------------------------------------------------------------------

    def _make_new_connection(self) -> CSTConnection:
        """Create and connect a new CST DesignEnvironment."""
        if self._connection_factory is not None:
            new_conn = self._connection_factory()
        else:
            new_conn = CSTConnection(library_path=self._library_path, mode="new")
            new_conn.connect()
            new_conn.set_quiet_mode(True)
        _logger.info("Connected to new CST DE, PID=%s", new_conn.pid)
        self._all_connections.append(new_conn)
        return new_conn

    def _clean_all_result_folders(self) -> None:
        """Remove result folders for the primary project and all extras."""
        remove_result_folder(self._project_path)
        remove_lock_file(os.path.dirname(self._project_path))
        for p in self._extra_result_paths:
            remove_result_folder(p)
            try:
                remove_lock_file(os.path.dirname(p))
            except Exception:
                pass

    def _graceful_clean_and_reconnect(self) -> None:
        """Graceful close + clean result folder + reconnect (Tier 2).

        Normal exit (not force kill), then remove the result folder
        and create a fresh connection for a clean-slate retry.
        """
        import time as _time

        pid = self._conn.pid
        try:
            self._conn.close(force=False)
        except Exception:
            pass

        # Verify the process actually exited after graceful close
        if pid is not None and pid > 0:
            if not verify_process_cleanup(pid, timeout_s=5.0):
                _logger.warning(
                    "Tier 2: PID=%d still alive after graceful close — "
                    "force_kill", pid,
                )
                force_kill_cst(pid)
                verify_process_cleanup(pid, timeout_s=5.0)

        _time.sleep(self._config.cooldown_s)

        kill_all_cst_processes()
        self._clean_all_result_folders()

        _time.sleep(self._config.cooldown_s)

        self._conn = self._make_new_connection()
        if self._on_reconnect is not None:
            self._on_reconnect(self._conn)

    def _kill_and_reconnect(self) -> None:
        """Kill the current CST process and create a fresh connection."""
        pid = self._conn.pid
        if pid is not None and pid > 0:
            _logger.info("Tier 2 (legacy): killing CST PID=%s", pid)
            force_kill_cst(pid)
            verify_process_cleanup(pid, timeout_s=10.0)

        try:
            self._conn.close(force=True)
        except Exception:
            pass

        kill_all_cst_processes()
        remove_lock_file(os.path.dirname(self._project_path))

        self._conn = self._make_new_connection()
        if self._on_reconnect is not None:
            self._on_reconnect(self._conn)

    def _kill_and_clean(self) -> None:
        """Kill CST processes, delete the result folder, and reconnect."""
        import time as _time

        pid = self._conn.pid
        if pid is not None and pid > 0:
            _logger.info("Tier 3: killing CST PID=%s", pid)
            force_kill_cst(pid)
            verify_process_cleanup(pid, timeout_s=10.0)

        _time.sleep(self._config.cooldown_s)

        try:
            self._conn.close(force=True)
        except Exception:
            pass

        kill_all_cst_processes()
        self._clean_all_result_folders()

        _time.sleep(self._config.cooldown_s)

        self._conn = self._make_new_connection()
        if self._on_reconnect is not None:
            self._on_reconnect(self._conn)


def _make_com_lost_result(error_msg: str = "") -> Any:
    """Create a minimal COM_LOST EvaluationResult for timeout paths.

    Defined at module level to avoid importing ``EvaluationResult``
    at the top of the retry module (circular import with workflows).
    """
    from ..workflows.recovery import EvaluationResult, EvaluationStatus
    return EvaluationResult(status=EvaluationStatus.COM_LOST, error=error_msg)

