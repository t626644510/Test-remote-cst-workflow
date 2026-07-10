"""Minimal backend protocol for RF-CEM parametric geometry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class GeometryBackend(Protocol):
    """Backend operations needed by the single-cell RF vacuum MVP."""

    def recover(
        self,
        *,
        step_file: Path,
        output_step: Path,
        axis: str,
        body_index: int,
        profile_points: list[tuple[float, float]],
        deflection_mm: float,
    ) -> dict:
        """Generate a STEP file and return backend metrics/debug data."""
