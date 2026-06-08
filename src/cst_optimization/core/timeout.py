"""Thread-based wall-clock timeout for blocking COM calls.

CST Studio Suite can show error popup dialogs even in quiet mode,
causing COM method calls to hang indefinitely.  This module provides a
``run_with_wall_clock_timeout`` wrapper that executes a callable in a
daemon thread and raises ``EvaluationTimeoutError`` if it does not
return within the configured deadline.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from ..diagnostics import CSTError

_logger = logging.getLogger(__name__)


class EvaluationTimeoutError(CSTError):
    """Raised when an evaluation exceeds its wall-clock timeout.

    The CST process likely shows a blocking popup dialog and must be
    killed externally before retrying.
    """


def run_with_wall_clock_timeout(
    func: Callable[..., Any],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    timeout_s: float = 600.0,
    on_timeout: Callable[[], None] | None = None,
) -> Any:
    """Execute *func* in a daemon thread with a wall-clock deadline.

    If the thread does not return within *timeout_s* seconds:

    1. *on_timeout()* is called (intended to kill CST processes / clean up).
    2. ``EvaluationTimeoutError`` is raised.

    If the thread completes normally its return value is forwarded.
    If the thread raises an exception it is re-raised in the caller.

    Parameters
    ----------
    func : callable
        The function to execute (typically a CST-backed evaluation).
    args : tuple
        Positional arguments forwarded to *func*.
    kwargs : dict or None
        Keyword arguments forwarded to *func*.
    timeout_s : float
        Wall-clock deadline in seconds.  Default 600 s (10 min).
    on_timeout : callable or None
        Called **once** when the timeout fires, before the exception is
        raised.  Should perform the "ultimate recovery" (kill CST, delete
        lock file and result folder, etc.).

    Returns
    -------
    Any
        The return value of ``func(*args, **kwargs)``.

    Raises
    ------
    EvaluationTimeoutError
        If the deadline expires.
    """
    _kwargs = kwargs or {}

    result_container: list[Any] = []
    exception_container: list[Exception | None] = [None]
    done_event = threading.Event()

    def _target() -> None:
        try:
            result_container.append(func(*args, **_kwargs))
        except Exception as exc:
            exception_container[0] = exc
        finally:
            done_event.set()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    finished = done_event.wait(timeout=timeout_s)

    if not finished:
        _logger.error(
            "Evaluation timed out after %.1f s — triggering emergency recovery. "
            "This may be a slow solver (> timeout) or a CST popup dialog.",
            timeout_s,
        )
        if on_timeout is not None:
            try:
                on_timeout()
            except Exception:
                _logger.exception("on_timeout callback raised an exception")

        raise EvaluationTimeoutError(
            f"Evaluation timed out after {timeout_s:.0f} s"
        )

    # Thread finished — check for exception
    exc = exception_container[0]
    if exc is not None:
        raise exc

    return result_container[0]
