"""Adapter from generated geometry package to current CSTTranslator."""

from __future__ import annotations

from pathlib import Path

from rf_cem.translator import translate_baseline


def build_cst_payload(*, generated_step: Path, parametric_geometry: Path, geometry_validation: Path) -> dict:
    """Build the minimal translator payload for generated RF vacuum geometry."""
    return {
        "schema_version": "cst_payload.v0",
        "geometry": {
            "step_path": str(generated_step),
            "role": "RFVacuumVolume",
            "units": "mm",
        },
        "metadata": {
            "parametric_geometry": str(parametric_geometry),
            "geometry_validation": str(geometry_validation),
        },
    }


def translate_generated_geometry(udsg: dict, templates: object, generated_step: Path) -> object:
    """Compile current CST actions with the generated STEP as import target."""
    return translate_baseline(udsg, templates, generated_step, filename_mode="absolute")
