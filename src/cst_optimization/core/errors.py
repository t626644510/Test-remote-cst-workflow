"""Structured exception hierarchy for CST interaction errors.

Replaces the old pattern of ``except Exception: pass`` and bare ``True/False``
returns with typed exceptions that carry enough context for the orchestrator
to decide on recovery strategy (retry, skip sample, abort workflow).
"""

from __future__ import annotations


class CSTError(Exception):
    """Base exception for all CST interaction errors."""


class CSTConnectionLostError(CSTError):
    """DesignEnvironment connection was lost (COM dead, process killed).

    The orchestrator should attempt a full reconnect + single retry
    when this is raised.
    """


# ---------------------------------------------------------------------------
# Solver errors
# ---------------------------------------------------------------------------


class SolverError(CSTError):
    """Base class for solver execution failures.

    Attributes
    ----------
    elapsed_s : float | None
        Wall-clock time spent in the solver before failure.
    """

    def __init__(self, *args: object, elapsed_s: float | None = None) -> None:
        super().__init__(*args)
        self.elapsed_s = elapsed_s


class SolverTimeoutError(SolverError):
    """Solver exceeded the configured timeout."""


class SolverMeshError(SolverError):
    """Mesh generation failed (distortion, topology intersection, etc.).

    The orchestrator should log this as a geometry issue and skip the
    current sample rather than attempting a retry.
    """


class SolverConvergenceError(SolverError):
    """Solver failed to converge within the allowed number of iterations."""


class SolverCOMError(SolverError):
    """COM layer communication failure — the connection to CST is broken.

    The orchestrator should attempt a reconnect + single retry.
    """


class SolverStagnationError(SolverError):
    """Solver progress stalled beyond the stagnation timeout."""
