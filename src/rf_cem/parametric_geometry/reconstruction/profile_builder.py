"""Build profile records for parametric geometry JSON."""

from __future__ import annotations

from rf_cem.parametric_geometry.grammar.cavity_grammar_v0 import build_single_cell_profile


def build_profile(
    parameters: dict,
    prior: dict | None = None,
    *,
    variant_name: str = "expanded_smooth_nose",
) -> tuple[list[tuple[float, float]], list[dict]]:
    """Build the MVP single-cell r-z profile."""
    return build_single_cell_profile(parameters, prior, variant_name=variant_name)
