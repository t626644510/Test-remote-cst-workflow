"""Build MVP section debug data from the grammar profile."""

from __future__ import annotations


def build_section_debug(profile_points: list[tuple[float, float]]) -> dict:
    """Return deterministic section debug records for four meridional planes."""
    return {
        "schema_version": "section_debug.v0",
        "section_strategy": "grammar_profile_from_feature_manifest",
        "sections": [
            {
                "phi_deg": phi,
                "section_source": "grammar_profile",
                "points": [[z, r] for z, r in profile_points],
                "curve_types": ["line", "local_spline_fallback"],
                "valid": True,
            }
            for phi in (0, 45, 90, 135)
        ],
    }
