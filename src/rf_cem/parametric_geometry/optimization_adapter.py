"""No-CST adapter between RF-CEM curve controls and optimization parameters."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import yaml

from cst_optimization.parameters.base import ParameterSet, ParamRange
from cst_optimization.parameters.geometry import GeometryParameter
from rf_cem.parametric_geometry.core.types import PipelineInputs
from rf_cem.parametric_geometry.pipeline.reverse_pipeline import run_reverse_pipeline


LEGACY_2D_PARAMETERS = (
    "shared_equator_crown_delta_r_mm",
    "shared_equator_crown_shoulder_z_abs_mm",
)

EXPLORATORY_12D_PARAMETERS = (
    "equator_crown_delta_r_mm",
    "equator_crown_z_mid_mm",
    "equator_left_shoulder_z_abs_mm",
    "equator_right_shoulder_z_abs_mm",
    "equator_left_shoulder_delta_r_mm",
    "equator_right_shoulder_delta_r_mm",
    "nose_left_inner_delta_r_mm",
    "nose_right_inner_delta_r_mm",
    "nose_left_inner_delta_z_mm",
    "nose_right_inner_delta_z_mm",
    "blend_left_radius_delta_mm",
    "blend_right_radius_delta_mm",
)

SUPPORTED_PRIOR_OVERRIDE_PARAMETERS = {
    *LEGACY_2D_PARAMETERS,
    *EXPLORATORY_12D_PARAMETERS,
    "shared_equator_crown_delta_r_mm",
    "shared_equator_crown_shoulder_z_abs_mm",
    "shared_equator_crown_z_mid_mm",
}

PARAMETER_PRESETS = {
    "legacy_2d": LEGACY_2D_PARAMETERS,
    "exploratory_12d": EXPLORATORY_12D_PARAMETERS,
}


@dataclass(frozen=True)
class ParametricOptimizationSpec:
    """A stable optimization parameter specification in RF-CEM units."""

    name: str
    unit: str
    baseline: float
    low: float
    high: float
    source_parameter: str
    parameter_group: str = "legacy"
    risk_level: str = "stable"
    feature_refs: tuple[str, ...] = ()
    segment_refs: tuple[str, ...] = ()


def build_parameter_specs(
    parametric_geometry_path: Path,
    *,
    bounds: Mapping[str, Sequence[float]] | None = None,
    parameter_names: Sequence[str] | None = None,
    parameter_preset: str = "legacy_2d",
) -> list[ParametricOptimizationSpec]:
    """Build RF-CEM optimization specs from explicit names or a named preset."""
    data = json.loads(parametric_geometry_path.read_text(encoding="utf-8"))
    derived = data.get("derived_parameters", {})
    if parameter_names is None:
        parameter_names = PARAMETER_PRESETS.get(parameter_preset)
        if parameter_names is None:
            raise ValueError(f"Unknown RF-CEM parameter preset: {parameter_preset!r}")
    specs: list[ParametricOptimizationSpec] = []
    for name in parameter_names:
        if name not in SUPPORTED_PRIOR_OVERRIDE_PARAMETERS:
            raise ValueError(f"RF-CEM parameter {name!r} has no v0 prior override mapping")
        spec = _spec_from_parametric_geometry(name, data, derived, bounds)
        if spec is None:
            continue
        specs.append(spec)
    if not specs:
        raise ValueError("No optimizable RF-CEM derived curve parameters found")
    return specs


def build_parameter_set(specs: Sequence[ParametricOptimizationSpec]) -> ParameterSet:
    """Build the existing optimizer ParameterSet abstraction for RF-CEM controls."""
    return ParameterSet(
        [
            GeometryParameter(
                spec.name,
                ParamRange(spec.low, spec.high),
                display_name=spec.name,
                unit=spec.unit or "mm",
            )
            for spec in specs
        ]
    )


def baseline_vector(specs: Sequence[ParametricOptimizationSpec]) -> np.ndarray:
    """Return the baseline physical vector in the same order as specs."""
    return np.array([spec.baseline for spec in specs], dtype=float)


def apply_curve_parameter_overrides(
    values: Mapping[str, float],
    *,
    selected_variant: str = "free_equator_smooth",
) -> dict:
    """Return an expert-prior override that maps optimizer values to curve controls."""
    equator: dict[str, dict[str, float]] = {selected_variant: {}}
    nose: dict[str, dict[str, float]] = {selected_variant: {}}
    blend: dict[str, dict[str, float]] = {selected_variant: {}}
    for name, value in values.items():
        if name in {"shared_equator_crown_delta_r_mm", "equator_crown_delta_r_mm"}:
            equator[selected_variant]["crown_radius_delta_mm"] = float(value)
        elif name == "shared_equator_crown_shoulder_z_abs_mm":
            equator[selected_variant]["shoulder_z_abs_mm"] = float(value)
        elif name == "shared_equator_crown_z_mid_mm" or name == "equator_crown_z_mid_mm":
            equator[selected_variant]["crown_z_mid_mm"] = float(value)
        elif name == "equator_left_shoulder_z_abs_mm":
            equator[selected_variant]["left_shoulder_z_abs_mm"] = float(value)
        elif name == "equator_right_shoulder_z_abs_mm":
            equator[selected_variant]["right_shoulder_z_abs_mm"] = float(value)
        elif name == "equator_left_shoulder_delta_r_mm":
            equator[selected_variant]["left_shoulder_delta_r_mm"] = float(value)
        elif name == "equator_right_shoulder_delta_r_mm":
            equator[selected_variant]["right_shoulder_delta_r_mm"] = float(value)
        elif name == "nose_left_inner_delta_r_mm":
            nose[selected_variant]["left_inner_delta_r_mm"] = float(value)
        elif name == "nose_right_inner_delta_r_mm":
            nose[selected_variant]["right_inner_delta_r_mm"] = float(value)
        elif name == "nose_left_inner_delta_z_mm":
            nose[selected_variant]["left_inner_delta_z_mm"] = float(value)
        elif name == "nose_right_inner_delta_z_mm":
            nose[selected_variant]["right_inner_delta_z_mm"] = float(value)
        elif name == "blend_left_radius_delta_mm":
            blend[selected_variant]["left_radius_delta_mm"] = float(value)
        elif name == "blend_right_radius_delta_mm":
            blend[selected_variant]["right_radius_delta_mm"] = float(value)
        else:
            raise ValueError(f"Unsupported RF-CEM curve optimization parameter: {name}")
    return {
        "schema_version": "expert_prior.v0",
        "model_family": "axisymmetric_single_cell_rf_vacuum",
        "grammar": {
            "variant_policy": {
                "default_selected_variant": selected_variant,
                "enabled_variants": [selected_variant],
                "curve_parameters": {
                    "equator": equator,
                    "nose": nose,
                    "blend": blend,
                },
            }
        },
    }


def generate_candidate_package(
    *,
    appendix: Path,
    output_dir: Path,
    parameter_values: Mapping[str, float],
    selected_variant: str = "free_equator_smooth",
    target_body_index: int = 0,
    axis: str = "z",
    deflection_mm: float = 0.25,
) -> dict:
    """Generate a complete RF-CEM design package for one optimizer candidate."""
    output_dir.mkdir(parents=True, exist_ok=True)
    prior_override = apply_curve_parameter_overrides(parameter_values, selected_variant=selected_variant)
    prior_path = output_dir / "expert_prior_override.v0.yaml"
    prior_path.write_text(yaml.safe_dump(prior_override, sort_keys=False, allow_unicode=True), encoding="utf-8")
    result = run_reverse_pipeline(
        PipelineInputs(
            appendix=appendix,
            output_dir=output_dir,
            target_body_index=target_body_index,
            axis=axis,  # type: ignore[arg-type]
            deflection_mm=deflection_mm,
            expert_prior=prior_path,
        )
    )
    result["generated_step"] = str(output_dir / "geometry" / "generated_vacuum.step")
    result["parametric_geometry"] = str(output_dir / "metadata" / "parametric_geometry.v0.json")
    result["geometry_validation"] = str(output_dir / "metadata" / "geometry_validation.json")
    result["cst_payload"] = str(output_dir / "translator" / "cst_payload.json")
    result["parameter_values"] = dict(parameter_values)
    result["expert_prior_override"] = str(prior_path)
    return result


def _is_optimizable_numeric(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if not entry.get("optimization_candidate") or not entry.get("affects_generated_step"):
        return False
    value = entry.get("value")
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _spec_from_parametric_geometry(
    name: str,
    data: dict,
    derived: Mapping[str, object],
    bounds: Mapping[str, Sequence[float]] | None,
) -> ParametricOptimizationSpec | None:
    entry = derived.get(name)
    if _is_optimizable_numeric(entry):
        entry_d = entry  # type: ignore[assignment]
        baseline = float(entry_d["value"])  # type: ignore[index]
        low, high = _bounds_for(name, baseline, bounds)
        return ParametricOptimizationSpec(
            name=name,
            unit=str(entry_d.get("unit", "mm")),  # type: ignore[union-attr]
            baseline=baseline,
            low=low,
            high=high,
            source_parameter=name,
            parameter_group=_parameter_group(name),
            risk_level=_risk_level(name),
            feature_refs=tuple(str(item) for item in entry_d.get("feature_refs", [])),  # type: ignore[union-attr]
            segment_refs=(str(entry_d.get("segment_id", "")),),  # type: ignore[union-attr]
        )

    baseline, source_parameter, feature_refs, segment_refs = _virtual_baseline(name, data, derived)
    if baseline is None:
        return None
    low, high = _bounds_for(name, baseline, bounds)
    return ParametricOptimizationSpec(
        name=name,
        unit="mm",
        baseline=float(baseline),
        low=low,
        high=high,
        source_parameter=source_parameter,
        parameter_group=_parameter_group(name),
        risk_level=_risk_level(name),
        feature_refs=feature_refs,
        segment_refs=segment_refs,
    )


def _virtual_baseline(name: str, data: dict, derived: Mapping[str, object]) -> tuple[float | None, str, tuple[str, ...], tuple[str, ...]]:
    if name == "equator_crown_delta_r_mm":
        return _numeric(derived, "shared_equator_crown_delta_r_mm", default=0.0), "shared_equator_crown_delta_r_mm", ("EquatorRegion",), ("seg_equator_free_crown",)
    if name == "equator_crown_z_mid_mm":
        return _numeric(derived, "nurbs_cp2_z__seg_equator_free_crown", default=0.0), "nurbs_cp2_z__seg_equator_free_crown", ("EquatorRegion",), ("seg_equator_free_crown",)
    if name == "shared_equator_crown_z_mid_mm":
        return _numeric(derived, "nurbs_cp2_z__seg_equator_free_crown", default=0.0), "nurbs_cp2_z__seg_equator_free_crown", ("EquatorRegion",), ("seg_equator_free_crown",)
    if name == "equator_left_shoulder_z_abs_mm":
        value = abs(_numeric(derived, "nurbs_cp1_z__seg_equator_free_crown", default=-30.0))
        return value, "nurbs_cp1_z__seg_equator_free_crown", ("EquatorRegion",), ("seg_equator_free_crown",)
    if name == "equator_right_shoulder_z_abs_mm":
        value = abs(_numeric(derived, "nurbs_cp3_z__seg_equator_free_crown", default=30.0))
        return value, "nurbs_cp3_z__seg_equator_free_crown", ("EquatorRegion",), ("seg_equator_free_crown",)
    if name in {"equator_left_shoulder_delta_r_mm", "equator_right_shoulder_delta_r_mm"}:
        return 0.0, name.replace("_delta_r_mm", "_source_cp_r"), ("EquatorRegion",), ("seg_equator_free_crown",)
    if name.startswith("nose_left_"):
        return 0.0, "seg_nose_left_smooth_nurbs.control_points", ("NoseCone", "TransitionBlend"), ("seg_nose_left_smooth_nurbs",)
    if name.startswith("nose_right_"):
        return 0.0, "seg_nose_right_smooth_nurbs.control_points", ("NoseCone", "TransitionBlend"), ("seg_nose_right_smooth_nurbs",)
    if name == "blend_left_radius_delta_mm":
        return 0.0, "arc_radius__seg_blend_left", ("TransitionBlend", "EquatorRegion"), ("seg_blend_left",)
    if name == "blend_right_radius_delta_mm":
        return 0.0, "arc_radius__seg_blend_right", ("TransitionBlend", "EquatorRegion"), ("seg_blend_right",)
    return None, name, (), ()


def _numeric(derived: Mapping[str, object], key: str, *, default: float) -> float:
    entry = derived.get(key)
    if isinstance(entry, dict) and isinstance(entry.get("value"), (int, float)):
        return float(entry["value"])
    return float(default)


def _bounds_for(name: str, baseline: float, bounds: Mapping[str, Sequence[float]] | None) -> tuple[float, float]:
    if bounds and name in bounds:
        low, high = bounds[name]
        return float(low), float(high)
    if name == "equator_crown_delta_r_mm":
        return baseline - 8.0, baseline + 8.0
    if name == "shared_equator_crown_delta_r_mm":
        return baseline - 3.0, baseline + 3.0
    if name == "equator_crown_z_mid_mm":
        return baseline - 15.0, baseline + 15.0
    if name in {"shared_equator_crown_shoulder_z_abs_mm", "equator_left_shoulder_z_abs_mm", "equator_right_shoulder_z_abs_mm"}:
        return max(5.0, baseline - 15.0), baseline + 15.0
    if name in {"equator_left_shoulder_delta_r_mm", "equator_right_shoulder_delta_r_mm"}:
        return baseline - 6.0, baseline + 8.0
    if name in {"nose_left_inner_delta_r_mm", "nose_right_inner_delta_r_mm"}:
        return baseline - 5.0, baseline + 8.0
    if name in {"nose_left_inner_delta_z_mm", "nose_right_inner_delta_z_mm"}:
        return baseline - 8.0, baseline + 8.0
    if name in {"blend_left_radius_delta_mm", "blend_right_radius_delta_mm"}:
        return baseline - 8.0, baseline + 12.0
    return baseline - 1.0, baseline + 1.0


def _parameter_group(name: str) -> str:
    if name.startswith("equator_"):
        return "equator_nurbs" if "shoulder_delta" in name else "equator_global"
    if name.startswith("nose_"):
        return "nose_nurbs"
    if name.startswith("blend_"):
        return "blend_arc"
    return "legacy"


def _risk_level(name: str) -> str:
    if name.startswith("nose_") or name.startswith("blend_"):
        return "exploratory"
    if "delta_r" in name or "z_mid" in name:
        return "moderate"
    return "stable"
