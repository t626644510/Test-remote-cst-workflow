"""CST project management.

Provides CSTProject, a wrapper around ``cst.interface.Project`` that
handles parameter updates (with structured fallback strategies), geometry
rebuild, and guaranteed-clean project lifecycle.
"""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any

from .cleanup import ProjectCloser
from ..diagnostics import CSTConnectionLostError

_logger = logging.getLogger(__name__)

# CST 2026 rebuild time — 10 s gives the modeler enough headroom to
# finish the full_history_rebuild after StoreParameter, even for complex
# cavity geometries with many constraints.
_REBUILD_SETTLE_S = 10.0


class CSTProject:
    """Wraps a ``cst.interface.Project`` with high-level parameter management.

    Supports context-manager protocol for guaranteed close::

        with CSTProject(prj) as proj:
            proj.update_parameters({"width": 2.0})

    Parameters
    ----------
    prj : cst.interface.Project
        An already-open CST project handle.
    """

    def __init__(self, prj: Any) -> None:
        self._prj = prj
        self._model3d = prj.model3d if hasattr(prj, "model3d") else None
        # Cache the filename at construction time so it is available
        # even after the DesignEnvironment connection is lost.
        try:
            self._filename: str = prj.filename()
        except Exception:
            self._filename = "<unknown>"

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> CSTProject:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def filename(self) -> str:
        """Return the absolute path to the ``.cst`` file.

        Returns the cached filename if the DesignEnvironment is unreachable.
        """
        try:
            return self._prj.filename()
        except Exception:
            return self._filename

    @property
    def model3d(self) -> Any | None:
        """Return the ``Model3D`` interface, or ``None`` for schematic-only projects."""
        return self._model3d

    @property
    def project(self) -> Any:
        """Return the underlying ``cst.interface.Project`` instance."""
        return self._prj

    # ------------------------------------------------------------------
    # Parameter management
    # ------------------------------------------------------------------

    def update_parameters(
        self, params: dict[str, float], use_full_rebuild: bool = False,
    ) -> bool:
        """Update geometry parameters using a three-strategy fallback.

        Strategy 1 (primary): Native ``StoreParameter`` via Python API.
        Strategy 2 (fallback): VBA ``StoreParameter`` via ``add_to_history``,
        only if the DesignEnvironment is still alive.
        Strategy 3 (error): Raise ``CSTConnectionLostError`` if the DE is dead.

        Parameters
        ----------
        params : dict[str, float]
            Mapping of CST parameter names to new values.
        use_full_rebuild : bool
            If ``True``, call ``full_history_rebuild()`` after setting params.

        Returns
        -------
        bool
            ``True`` if all parameters were set successfully.
        """
        if self._model3d is None:
            raise RuntimeError("No 3D modeler available; cannot update parameters")

        # Strategy 1 — native Python API
        try:
            for name, value in params.items():
                self._model3d.StoreParameter(str(name), str(value))

            if use_full_rebuild:
                self._model3d.full_history_rebuild()
                time.sleep(_REBUILD_SETTLE_S)

            return True

        except AttributeError:
            # Check if the DesignEnvironment is still alive
            if not self._de_is_alive():
                raise CSTConnectionLostError(
                    "DesignEnvironment lost during parameter update"
                )

            _logger.info(
                "StoreParameter not available via native API, falling back to VBA"
            )
            return self._update_parameters_via_vba(params)

    def _update_parameters_via_vba(self, params: dict[str, float]) -> bool:
        """Strategy 2 — set parameters by executing VBA ``StoreParameter`` calls."""
        if self._model3d is None:
            return False

        vba_lines = [
            f'StoreParameter "{name}", {value}'
            for name, value in params.items()
        ]
        vba_code = "\n".join(vba_lines)

        try:
            self._model3d.add_to_history(
                f"Set parameters: {list(params.keys())}", vba_code
            )
            time.sleep(0.5)
            self._model3d.full_history_rebuild()
            time.sleep(_REBUILD_SETTLE_S)
            return True
        except Exception:
            _logger.warning(
                "VBA parameter update failed for: %s", list(params.keys()),
                exc_info=True,
            )
            return False

    def rebuild(self) -> None:
        """Trigger a full model rebuild (``full_history_rebuild``)."""
        if self._model3d is None:
            raise RuntimeError("No 3D modeler available")
        self._model3d.full_history_rebuild()

    def get_active_solver_name(self) -> str:
        """Return the currently active solver name (e.g. ``"Wakefield"``)."""
        if self._model3d is None:
            return ""
        try:
            return str(self._model3d.get_active_solver_name())
        except Exception:
            return "<error>"

    def execute_vba(self, vba_code: str, header: str = "") -> None:
        """Execute a VBA snippet via ``Model3D.add_to_history()``."""
        if self._model3d is None:
            raise RuntimeError("No 3D modeler available")
        if not vba_code.strip():
            return
        self._model3d.add_to_history(header or "VBA command", vba_code)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def save(
        self,
        path: str = "",
        include_results: bool = True,
        allow_overwrite: bool = False,
    ) -> bool:
        """Save the project.  Returns ``False`` on failure (never raises)."""
        try:
            self._prj.save(
                path=path or "",
                include_results=include_results,
                allow_overwrite=allow_overwrite,
            )
            return True
        except Exception:
            _logger.warning(
                "Failed to save project %s", self._filename, exc_info=True,
            )
            return False

    def close(self, save: bool = True) -> None:
        """Save (if requested) and close the project.

        Each phase is independently guarded — a save failure does not
        prevent close, and a dead DesignEnvironment does not cause a
        cascade of secondary errors.
        """
        fname = self._filename  # use cached copy, DE may already be dead

        if save:
            try:
                self._prj.save()
            except Exception:
                _logger.warning("Failed to save project %s", fname)

        try:
            self._prj.close()
        except Exception:
            _logger.warning("Failed to close project %s", fname)

        self._model3d = None

    def activate(self) -> None:
        """Make this project the active tab in the CST DesignEnvironment."""
        self._prj.activate()

    def get_messages(self) -> object:
        """Return messages from the CST Message Window."""
        return self._prj.get_messages()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _de_is_alive(self) -> bool:
        """Best-effort check whether the DesignEnvironment is still reachable."""
        try:
            _ = self._prj.filename()
            return True
        except Exception:
            return False
