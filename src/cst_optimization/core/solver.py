"""CST solver execution with structured error classification.

Uses ``model3d.run_solver()`` (synchronous) — equivalent to the GUI
"Start" button — rather than ``start_solver()`` + polling which triggers
an internal ``full_history_rebuild()`` that can reset the active solver.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .errors import (
    SolverCOMError,
    SolverConvergenceError,
    SolverMeshError,
    SolverStagnationError,
    SolverTimeoutError,
)

if TYPE_CHECKING:
    from .project import CSTProject

_logger = logging.getLogger(__name__)

# Sensible default when the user does not configure a timeout.
# Prevents perpetual solver hangs on extreme geometry.
_DEFAULT_TIMEOUT_S = 7200.0


@dataclass
class SolverResult:
    """Structured result from a CST solver run.

    Replaces the old ``True``/``False`` return so the orchestrator can
    make informed recovery decisions based on the failure mode.
    """

    success: bool
    error_type: str | None = None
    """One of ``"timeout"``, ``"mesh"``, ``"com"``, ``"convergence"``, or ``None``."""
    error_message: str | None = None
    elapsed_s: float = 0.0
    mesh_cells: int | None = None


class SolverRunner:
    """Synchronous CST solver execution with structured error returns.

    Parameters
    ----------
    timeout_s : float
        CST solver timeout in seconds.  Defaults to 7200 s (2 h) when
        set to 0 or negative (prevents perpetual hangs).
    settle_s : float
        Pause after parameter update before running solver (default 2 s).
    """

    def __init__(
        self,
        timeout_s: float = 0.0,
        settle_s: float = 2.0,
    ) -> None:
        # CST 2026 supports real timeout values; never pass None
        self._timeout_s = float(timeout_s) if timeout_s > 0 else _DEFAULT_TIMEOUT_S
        self._settle_s = float(settle_s)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, project: CSTProject) -> SolverResult:
        """Run the solver synchronously.

        Parameters
        ----------
        project : CSTProject
            The project whose solver should be executed.

        Returns
        -------
        SolverResult
            Structured result with success flag and error classification.
        """
        model3d = project.model3d
        if model3d is None:
            return SolverResult(
                success=False,
                error_type="com",
                error_message="No 3D modeler available",
            )

        # Clear any leftover solver state
        try:
            model3d.abort_solver()
            time.sleep(0.5)
        except Exception:
            pass

        # Brief settle for CST parameter DB
        if self._settle_s > 0:
            time.sleep(self._settle_s)

        t0 = time.perf_counter()
        try:
            model3d.run_solver(timeout=self._timeout_s)
            elapsed = time.perf_counter() - t0
            mesh_cells = self._read_mesh_cells(model3d)
            return SolverResult(
                success=True, elapsed_s=elapsed, mesh_cells=mesh_cells,
            )

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            return self._classify_error(exc, elapsed)

    def abort(self, project: CSTProject) -> None:
        """Force-abort the currently running solver."""
        model3d = project.model3d
        if model3d is not None:
            try:
                model3d.abort_solver()
            except Exception:
                _logger.debug("abort_solver() failed", exc_info=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _classify_error(self, exc: Exception, elapsed_s: float) -> SolverResult:
        """Map a CST exception to a classified ``SolverResult``."""
        msg = str(exc)
        msg_lower = msg.lower()

        # Mesh-related errors (distortion, topology intersection, etc.)
        if any(kw in msg_lower for kw in (
            "mesh", "meshing", "tetrahedral", "hexahedral",
            "intersection", "distorted", "degenerate", "topology",
            "surface mesh", "volume mesh",
        )):
            _logger.warning("Solver mesh error (%.1f s): %s", elapsed_s, msg)
            return SolverResult(
                success=False,
                error_type="mesh",
                error_message=msg,
                elapsed_s=elapsed_s,
            )

        # Timeout
        if any(kw in msg_lower for kw in ("timeout", "time out", "timed out")):
            _logger.warning("Solver timeout after %.1f s", elapsed_s)
            return SolverResult(
                success=False,
                error_type="timeout",
                error_message=msg,
                elapsed_s=elapsed_s,
            )

        # COM / connectivity errors
        if any(kw in msg_lower for kw in (
            "com", "rpc", "dispatch", "interface not registered",
            "server threw", "connection", "disconnected",
        )):
            _logger.warning("Solver COM error (%.1f s): %s", elapsed_s, msg)
            return SolverResult(
                success=False,
                error_type="com",
                error_message=msg,
                elapsed_s=elapsed_s,
            )

        # Convergence
        if any(kw in msg_lower for kw in (
            "converge", "not converged", "iteration limit",
            "maximum number of", "did not reach",
        )):
            _logger.warning("Solver convergence error (%.1f s): %s", elapsed_s, msg)
            return SolverResult(
                success=False,
                error_type="convergence",
                error_message=msg,
                elapsed_s=elapsed_s,
            )

        # Catch-all — unknown error type
        _logger.warning(
            "Solver error (unclassified, %.1f s): %s", elapsed_s, msg
        )
        return SolverResult(
            success=False,
            error_type=None,
            error_message=msg,
            elapsed_s=elapsed_s,
        )

    @staticmethod
    def _read_mesh_cells(model3d: object) -> int | None:
        """Best-effort read of the mesh cell count for diagnostics."""
        try:
            return int(model3d.get_number_of_mesh_cells())
        except Exception:
            return None
