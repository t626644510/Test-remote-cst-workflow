"""Segment fitting report helpers."""

from __future__ import annotations


def build_fit_report(segments: list[dict], warnings: list[str]) -> dict:
    """Build a deterministic reverse-fit report."""
    return {
        "schema_version": "reverse_fit_report.v0",
        "fitting_ladder": ["exact_inheritance", "line", "arc", "ellipse", "local_spline_fallback"],
        "segments": segments,
        "warnings": warnings,
        "notes": [
            "MVP recovers a grammar-constrained profile from reviewed feature evidence, not the original CAD history tree.",
            "Nose/blend transitions prefer torus-derived arc evidence and use local NURBS only as a smoothness fallback.",
        ],
    }
