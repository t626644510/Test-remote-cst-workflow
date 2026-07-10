"""Emit parametric geometry JSON records."""

from __future__ import annotations

from pathlib import Path

from rf_cem.parametric_geometry.core.types import AxisReport, BodySelection, FeatureBinding, to_plain
from rf_cem.parametric_geometry.reconstruction.derived_parameters import derive_curve_parameters


def build_parametric_geometry_json(
    *,
    source_step: Path,
    labels_path: Path,
    geometry_graph_path: Path,
    udsg_path: Path,
    axis_report: AxisReport,
    body_selection: BodySelection,
    parameters: dict,
    segments: list[dict],
    bindings: list[FeatureBinding],
    output_step: Path,
    resolved_prior_path: Path,
    resolved_prior_metadata: dict,
    variant_name: str = "expanded_smooth_nose",
) -> dict:
    named_parameters = {key: value for key, value in parameters.items() if not key.startswith("_")}
    derived_parameters = derive_curve_parameters(segments, variant_name=variant_name)
    return {
        "schema_version": "parametric_geometry.v0",
        "model_type": "axisymmetric_rf_vacuum_single_cell",
        "variant": {
            "name": variant_name,
            "selection_role": "candidate",
        },
        "units": {"length": "mm", "frequency": "MHz", "time": "ns"},
        "source": {
            "baseline_step": str(source_step),
            "reviewed_feature_labels": str(labels_path),
            "geometry_graph": str(geometry_graph_path),
            "udsg": str(udsg_path),
            "resolved_expert_prior": str(resolved_prior_path),
        },
        "expert_prior": {
            "schema_version": resolved_prior_metadata.get("schema_version"),
            "sources": resolved_prior_metadata.get("sources", []),
            "warnings": resolved_prior_metadata.get("warnings", []),
            "precedence": resolved_prior_metadata.get("precedence", []),
        },
        "target_body": to_plain(body_selection),
        "axis": {
            "name": axis_report.requested_axis,
            "origin_xyz": [0.0, 0.0, 0.0],
            "direction_xyz": [0.0, 0.0, 1.0],
            "confidence": axis_report.confidence,
            "evidence_refs": ["ev_axis_001"],
            "verification": to_plain(axis_report),
        },
        "named_parameters": named_parameters,
        "derived_parameters": derived_parameters,
        "profile": {
            "plane": "XZ",
            "representation": "rz_half_profile",
            "axis_side": "r>=0",
            "segments": segments,
        },
        "feature_bindings": [to_plain(binding) for binding in bindings],
        "constraints": [
            {"id": "c_profile_simple", "type": "global", "required": True, "expr": "profile_is_simple"},
            {"id": "c_axis_side", "type": "global", "required": True, "expr": "all_r_ge_0"},
            {"id": "c_min_curvature", "type": "global", "required": True, "expr": "rho_min_ge_threshold", "value_mm": 3.0},
        ],
        "source_evidence": [
            {"id": "ev_axis_001", "kind": "geometry_manifest", "source_ref": str(geometry_graph_path)},
            {"id": "ev_profile_001", "kind": "reviewed_feature_projection", "source_ref": str(labels_path)},
        ],
        "export_metadata": {
            "generator_backend": "cadquery_occt_worker",
            "step_output_unit": "MM",
            "generated_step": str(output_step),
        },
    }
