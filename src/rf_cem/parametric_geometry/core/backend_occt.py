"""OCCT backend facade.

The MVP routes OCCT work through the CadQuery/OCP worker so the main process
does not import the CAD kernel directly on Windows.
"""

from __future__ import annotations

from pathlib import Path

from .backend_cadquery import CadQueryGeometryBackend


class OCCTGeometryBackend(CadQueryGeometryBackend):
    """Compatibility facade for low-level OCCT-backed operations."""

    def __init__(self, python_executable: str | None = None) -> None:
        super().__init__(python_executable=python_executable)
