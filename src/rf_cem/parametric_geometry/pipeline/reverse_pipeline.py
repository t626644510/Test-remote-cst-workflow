"""End-to-end RF-CEM parametric vacuum geometry recovery pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import yaml

from rf_cem.build_500mhz_baseline import write_artifacts
from rf_cem.design_package import BaselinePaths
from rf_cem.parametric_geometry.expert_prior import load_expert_prior, write_resolved_prior
from rf_cem.parametric_geometry.analysis.feature_projector import build_feature_bindings, derive_key_parameters
from rf_cem.parametric_geometry.analysis.section_extractor import build_section_debug
from rf_cem.parametric_geometry.core.types import GeometryThresholds, PipelineInputs, to_plain
from rf_cem.parametric_geometry.grammar.continuity import check_profile_continuity
from rf_cem.parametric_geometry.grammar.cavity_grammar_v0 import selected_variant_from_prior, variants_from_prior
from rf_cem.parametric_geometry.grammar.segment_fit import build_fit_report
from rf_cem.parametric_geometry.interfaces.audit_html import write_parametric_audit_html
from rf_cem.parametric_geometry.ingest.axis_estimator import verify_axis
from rf_cem.parametric_geometry.ingest.step_loader import load_geometry_manifest
from rf_cem.parametric_geometry.ingest.vacuum_selector import select_target_body
from rf_cem.parametric_geometry.interfaces.cst_package_adapter import build_cst_payload, translate_generated_geometry
from rf_cem.parametric_geometry.interfaces.udsg_bridge import build_current_udsg
from rf_cem.parametric_geometry.reconstruction.json_emitter import build_parametric_geometry_json
from rf_cem.parametric_geometry.reconstruction.profile_builder import build_profile
from rf_cem.parametric_geometry.reconstruction.step_generator import generate_step
from rf_cem.parametric_geometry.validation.occt_checker import build_validation_report


def run_reverse_pipeline(inputs: PipelineInputs) -> dict:
    """Run the 500 MHz RF vacuum reverse-parameterization MVP."""
    inputs.output_dir.mkdir(parents=True, exist_ok=True)
    resolved_prior, _ = load_expert_prior(appendix=inputs.appendix, explicit_prior=inputs.expert_prior)
    enabled_variants = variants_from_prior(resolved_prior)
    selected_variant = selected_variant_from_prior(resolved_prior)
    variant_results = []
    for variant_name in enabled_variants:
        variant_inputs = PipelineInputs(
            appendix=inputs.appendix,
            output_dir=inputs.output_dir / "variants" / variant_name,
            target_body_index=inputs.target_body_index,
            axis=inputs.axis,
            deflection_mm=inputs.deflection_mm,
            expert_prior=inputs.expert_prior,
        )
        variant_results.append(_run_single_package(variant_inputs, variant_name=variant_name))

    selected = next(item for item in variant_results if item["variant"] == selected_variant)
    _copy_selected_package(Path(selected["output_dir"]), inputs.output_dir)
    variant_index = _variant_index(inputs.output_dir, variant_results, selected)
    _write_json(inputs.output_dir / "variant_index.json", variant_index)
    _write_variant_comparison_html(inputs.output_dir / "audit" / "variant_comparison.html", variant_index)
    selected_result = dict(selected)
    selected_result["output_dir"] = str(inputs.output_dir)
    selected_result["variants"] = variant_results
    selected_result["variant_index"] = str(inputs.output_dir / "variant_index.json")
    selected_result["variant_comparison_html"] = str(inputs.output_dir / "audit" / "variant_comparison.html")
    return selected_result


def _run_single_package(inputs: PipelineInputs, *, variant_name: str) -> dict:
    paths = BaselinePaths.from_appendix(inputs.appendix)
    paths.validate()
    geometry_dir = inputs.output_dir / "geometry"
    metadata_dir = inputs.output_dir / "metadata"
    translator_dir = inputs.output_dir / "translator"
    audit_dir = inputs.output_dir / "audit"
    for directory in (geometry_dir, metadata_dir, translator_dir, audit_dir):
        directory.mkdir(parents=True, exist_ok=True)

    baseline_copy = geometry_dir / "baseline_vacuum.step"
    generated_step = geometry_dir / "generated_vacuum.step"
    shutil.copyfile(paths.step_file, baseline_copy)

    manifest = load_geometry_manifest(paths.geometry_manifest)
    labels = yaml.safe_load(paths.reviewed_feature_labels.read_text(encoding="utf-8")) or {}
    resolved_prior, prior_metadata = load_expert_prior(appendix=inputs.appendix, explicit_prior=inputs.expert_prior)
    body_selection = select_target_body(manifest, inputs.target_body_index)
    axis_report = verify_axis(manifest, inputs.axis)
    bindings = build_feature_bindings(labels, resolved_prior)
    parameters = derive_key_parameters(manifest, labels, resolved_prior)
    profile_points, segments = build_profile(parameters, resolved_prior, variant_name=variant_name)
    continuity = check_profile_continuity(segments)
    kernel_report = generate_step(
        step_file=paths.step_file,
        output_step=generated_step,
        axis=inputs.axis,
        body_index=inputs.target_body_index,
        profile_points=profile_points,
        profile_segments=segments,
        deflection_mm=inputs.deflection_mm,
    )
    section_debug = build_section_debug(profile_points)
    section_debug["kernel_sections"] = kernel_report.get("sections", [])
    validation = build_validation_report(kernel_report, profile_points, _thresholds_from_prior(resolved_prior))
    validation["profile_checks"]["continuity"] = continuity
    warnings = list(validation.get("warnings", []))
    if not axis_report.accepted:
        warnings.append("requested axis was not fully verified")
    fit_report = build_fit_report(segments, warnings)
    udsg, review_diff, templates = build_current_udsg(paths)

    parametric_path = metadata_dir / "parametric_geometry.v0.json"
    validation_path = metadata_dir / "geometry_validation.json"
    source_evidence_path = metadata_dir / "source_evidence.json"
    udsg_path = metadata_dir / "udsg.v0.json"
    resolved_prior_base = metadata_dir / "resolved_expert_prior.v0"
    section_debug_path = geometry_dir / "section_debug.json"
    fit_report_path = metadata_dir / "reverse_fit_report.json"
    profile_preview_path = geometry_dir / "profile_preview.svg"
    cst_payload_path = translator_dir / "cst_payload.json"
    mapping_patch_path = translator_dir / "mapping_table_patch.json"
    audit_html_path = audit_dir / "parametric_geometry_audit.html"
    resolved_prior_yaml_path, resolved_prior_json_path = write_resolved_prior(resolved_prior_base, resolved_prior, prior_metadata)

    parametric_geometry = build_parametric_geometry_json(
        source_step=paths.step_file,
        labels_path=paths.reviewed_feature_labels,
        geometry_graph_path=paths.geometry_graph,
        udsg_path=udsg_path,
        axis_report=axis_report,
        body_selection=body_selection,
        parameters=parameters,
        segments=segments,
        bindings=bindings,
        output_step=generated_step,
        resolved_prior_path=resolved_prior_yaml_path,
        resolved_prior_metadata=prior_metadata,
        variant_name=variant_name,
    )
    _write_json(parametric_path, parametric_geometry)
    _write_json(udsg_path, udsg)
    _write_json(validation_path, validation)
    _write_json(section_debug_path, section_debug)
    _write_json(fit_report_path, fit_report)
    _write_json(source_evidence_path, _source_evidence(paths, body_selection, axis_report, bindings, kernel_report))
    profile_preview_path.write_text(_svg_profile(profile_points), encoding="utf-8")

    artifacts = translate_generated_geometry(udsg, templates, generated_step)
    write_artifacts(inputs.output_dir / "translator" / "rf_cem_artifacts", udsg, review_diff, artifacts)
    cst_payload = build_cst_payload(generated_step=generated_step, parametric_geometry=parametric_path, geometry_validation=validation_path)
    _write_json(cst_payload_path, cst_payload)
    _write_json(
        mapping_patch_path,
        {
            "schema_version": "mapping_table_patch.v0",
            "generated_step": str(generated_step),
            "notes": ["CSTTranslator import target is switched to generated_vacuum.step."],
        },
    )
    write_parametric_audit_html(
        audit_html_path,
        parametric_geometry=parametric_geometry,
        geometry_validation=validation,
        reverse_fit_report=fit_report,
        source_evidence=_source_evidence(paths, body_selection, axis_report, bindings, kernel_report),
        cst_payload=cst_payload,
        resolved_prior=resolved_prior,
    )
    return {
        "schema_version": "parametric_geometry_pipeline_result.v0",
        "variant": variant_name,
        "status": "ok" if validation["pass"] else "geometry_warning",
        "output_dir": str(inputs.output_dir),
        "generated_step": str(generated_step),
        "parametric_geometry": str(parametric_path),
        "geometry_validation": str(validation_path),
        "audit_html": str(audit_html_path),
        "resolved_expert_prior": str(resolved_prior_yaml_path),
        "blocking_errors": validation.get("blocking_errors", []),
        "warnings": validation.get("warnings", []),
    }


def _source_evidence(paths: BaselinePaths, body_selection: object, axis_report: object, bindings: list[object], kernel_report: dict) -> dict:
    return {
        "schema_version": "source_evidence.v0",
        "inputs": {
            "step_file": str(paths.step_file),
            "reviewed_feature_labels": str(paths.reviewed_feature_labels),
            "geometry_manifest": str(paths.geometry_manifest),
        },
        "body_selection": to_plain(body_selection),
        "axis_report": to_plain(axis_report),
        "feature_bindings": [to_plain(binding) for binding in bindings],
        "kernel_report": kernel_report,
    }


def _thresholds_from_prior(prior: dict) -> GeometryThresholds:
    validation = prior.get("validation", {})
    return GeometryThresholds(
        bbox_abs_mm=float(validation.get("bbox_abs_error_mm", 0.3)),
        bbox_rel=float(validation.get("bbox_rel_error", 0.002)),
        volume_rel=float(validation.get("volume_rel_error", 0.01)),
        surface_area_rel=float(validation.get("surface_area_rel_error", 0.01)),
        profile_rms_mm=float(validation.get("profile_rms_error_mm", 0.15)),
        profile_max_mm=float(validation.get("profile_max_error_mm", 0.50)),
        baseline_difference_policy={
            str(key): str(value)
            for key, value in validation.get("baseline_difference_policy", {}).items()
        },
    )


def _svg_profile(profile_points: list[tuple[float, float]]) -> str:
    width, height = 800, 360
    z_values = [z for z, _ in profile_points]
    r_values = [r for _, r in profile_points]
    zmin, zmax = min(z_values), max(z_values)
    rmax = max(r_values)

    def xy(point: tuple[float, float]) -> tuple[float, float]:
        z, r = point
        x = 40 + (z - zmin) / (zmax - zmin) * (width - 80)
        y = height - 40 - r / rmax * (height - 80)
        return x, y

    points = " ".join(f"{x:.2f},{y:.2f}" for x, y in map(xy, profile_points))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="white"/>\n'
        f'<polyline points="{points}" fill="none" stroke="#1f77b4" stroke-width="3"/>\n'
        '<line x1="40" y1="320" x2="760" y2="320" stroke="#999" stroke-width="1"/>\n'
        "</svg>\n"
    )


def _copy_selected_package(selected_dir: Path, output_dir: Path) -> None:
    for name in ("geometry", "metadata", "translator", "audit"):
        source = selected_dir / name
        target = output_dir / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)


def _variant_index(output_dir: Path, variant_results: list[dict], selected: dict) -> dict:
    variants = []
    for result in variant_results:
        variant_dir = Path(result["output_dir"])
        validation_path = variant_dir / "metadata" / "geometry_validation.json"
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        parametric_path = variant_dir / "metadata" / "parametric_geometry.v0.json"
        parametric = json.loads(parametric_path.read_text(encoding="utf-8"))
        kinds = sorted({segment.get("kind") for segment in parametric.get("profile", {}).get("segments", [])})
        variants.append(
            {
                "name": result["variant"],
                "output_dir": str(variant_dir),
                "selected": result["variant"] == selected["variant"],
                "generated_step": result["generated_step"],
                "parametric_geometry": result["parametric_geometry"],
                "geometry_validation": result["geometry_validation"],
                "audit_html": result["audit_html"],
                "translator_payload": str(variant_dir / "translator" / "cst_payload.json"),
                "status": result["status"],
                "blocking_errors": result.get("blocking_errors", []),
                "warnings": result.get("warnings", []),
                "segment_kinds": kinds,
                "curve_generation_mode": validation.get("source_kernel_curve_generation_mode"),
            }
        )
    return {
        "schema_version": "parametric_geometry_variant_index.v0",
        "selected_variant": selected["variant"],
        "selected_policy": "expanded_smooth_nose is copied to the top-level compatibility package.",
        "output_dir": str(output_dir),
        "variants": variants,
    }


def _write_variant_comparison_html(path: Path, variant_index: dict) -> None:
    rows = []
    for variant in variant_index["variants"]:
        rows.append(
            "<tr>"
            f"<td>{variant['name']}</td>"
            f"<td>{'yes' if variant['selected'] else 'no'}</td>"
            f"<td>{variant['status']}</td>"
            f"<td>{', '.join(str(kind) for kind in variant['segment_kinds'])}</td>"
            f"<td>{variant['generated_step']}</td>"
            f"<td>{variant['audit_html']}</td>"
            "</tr>"
        )
    html = (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>RF-CEM Variant Comparison</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;color:#1f2933}"
        "table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #ccd3dd;padding:7px;text-align:left}"
        "th{background:#edf1f5}</style></head><body>"
        "<h1>RF-CEM Nose / Blend Variant Comparison</h1>"
        "<p>Each variant is a complete design package. The selected variant is copied to the top-level compatibility package.</p>"
        "<table><thead><tr><th>Variant</th><th>Selected</th><th>Status</th><th>Segment kinds</th><th>STEP</th><th>Audit</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<h2>Raw variant_index.json</h2><pre>"
        f"{json.dumps(variant_index, indent=2, ensure_ascii=False)}"
        "</pre></body></html>\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
