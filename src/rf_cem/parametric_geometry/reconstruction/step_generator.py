"""STEP generation facade."""

from __future__ import annotations

from pathlib import Path

from rf_cem.parametric_geometry.core.backend_cadquery import CadQueryGeometryBackend


def generate_step(
    *,
    step_file: Path,
    output_step: Path,
    axis: str,
    body_index: int,
    profile_points: list[tuple[float, float]],
    profile_segments: list[dict] | None = None,
    deflection_mm: float,
) -> dict:
    """Generate the RF vacuum STEP through the isolated CadQuery worker."""
    backend = CadQueryGeometryBackend()
    return backend.recover(
        step_file=step_file,
        output_step=output_step,
        axis=axis,
        body_index=body_index,
        profile_points=profile_points,
        profile_segments=profile_segments or [],
        deflection_mm=deflection_mm,
    )
