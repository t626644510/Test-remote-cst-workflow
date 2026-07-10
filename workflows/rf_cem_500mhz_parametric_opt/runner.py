"""CLI runner for RF-CEM 500 MHz no-CST parametric scans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import yaml

from cst_optimization.optimization.sampling import latin_hypercube_sampling
from rf_cem.parametric_geometry.core.types import PipelineInputs
from rf_cem.parametric_geometry.optimization_adapter import (
    baseline_vector,
    build_parameter_set,
    build_parameter_specs,
)
from rf_cem.parametric_geometry.pipeline.reverse_pipeline import run_reverse_pipeline
from workflows.rf_cem_500mhz_parametric_opt.evaluator import RfCemParametricEvaluator


def main(argv: Sequence[str] | None = None) -> int:
    """Run a no-CST RF-CEM parametric scan."""
    parser = argparse.ArgumentParser(
        prog="python -m workflows.rf_cem_500mhz_parametric_opt.runner",
        description="Run no-CST RF-CEM 500 MHz parametric candidate generation.",
    )
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    output_dir = args.output_dir or Path(config.get("output_dir", "runs/rf_cem_500mhz_parametric_opt"))
    appendix = Path(config.get("appendix", "Appendix/500MHz_baseline"))
    baseline_parametric = Path(config.get("baseline_parametric_geometry", "runs/parametric_geometry_500mhz/metadata/parametric_geometry.v0.json"))
    selected_variant = str(config.get("selected_variant", "free_equator_smooth"))
    parameter_names = [str(item) for item in config.get("parameters", [])] or None
    parameter_preset = str(config.get("parameter_preset", "legacy_2d"))
    bounds = {str(key): value for key, value in (config.get("bounds", {}) or {}).items()}

    _ensure_baseline_parametric_geometry(config, appendix, baseline_parametric)
    specs = build_parameter_specs(
        baseline_parametric,
        bounds=bounds,
        parameter_names=parameter_names,
        parameter_preset=parameter_preset,
    )
    parameter_set = build_parameter_set(specs)
    x0 = baseline_vector(specs)
    evaluator = RfCemParametricEvaluator(
        appendix=appendix,
        output_dir=output_dir / "candidates",
        parameter_set=parameter_set,
        selected_variant=selected_variant,
    )
    records = []
    for index, point in enumerate(_scan_points(config, specs, x0), start=1):
        records.append(evaluator.evaluate_no_cst(np.array(point, dtype=float), index=index))

    parameter_table = {
        "schema_version": "rf_cem_parameter_table.v0",
        "selected_variant": selected_variant,
        "parameter_preset": parameter_preset,
        "dimension": len(specs),
        "parameters": [spec.__dict__ for spec in specs],
        "notes": [
            "All values are RF-CEM geometry controls in explicit units.",
            "These controls are written into expert prior overrides, then regenerated into STEP.",
        ],
    }
    report = {
        "schema_version": "rf_cem_parametric_scan_report.v0",
        "mode": "no_cst",
        "selected_variant": selected_variant,
        "parameter_preset": parameter_preset,
        "dimension": len(specs),
        "parameter_specs": [spec.__dict__ for spec in specs],
        "parameter_names": parameter_set.names,
        "records": [record.to_dict() for record in records],
        "notes": [
            "No CST solver was run by this runner.",
            "Records with POSTPROCESS_TEMPLATE_MISSING passed no-CST geometry generation but cannot produce Freq/RQ/Q objectives yet.",
            "Records with SOLVER_NOT_RUN have passed no-CST geometry and postprocessing-template checks but are not optimizer-success samples.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    parameter_table_path = output_dir / "parameter_table.json"
    parameter_table_path.write_text(json.dumps(parameter_table, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    report_path = output_dir / "scan_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote RF-CEM optimization parameter table to {parameter_table_path}")
    print(f"Wrote RF-CEM parametric no-CST scan report to {report_path}")
    return 0


def _ensure_baseline_parametric_geometry(config: dict, appendix: Path, parametric_path: Path) -> None:
    if parametric_path.exists():
        return
    if not appendix.exists():
        raise FileNotFoundError(
            f"Baseline parametric geometry is missing and appendix was not found: {appendix}. "
            "Copy Appendix/500MHz_baseline to this checkout, or set appendix/baseline_parametric_geometry in config.yaml."
        )
    output_dir = parametric_path.parent.parent
    print(f"Baseline parametric geometry not found: {parametric_path}")
    print(f"Generating baseline parametric package from {appendix} into {output_dir}")
    result = run_reverse_pipeline(
        PipelineInputs(
            appendix=appendix,
            output_dir=output_dir,
            target_body_index=int(config.get("target_body_index", 0)),
            axis=str(config.get("axis", "z")),  # type: ignore[arg-type]
            deflection_mm=float(config.get("deflection_mm", 0.25)),
        )
    )
    if result.get("blocking_errors"):
        raise RuntimeError(f"Baseline parametric package generation failed: {result['blocking_errors']}")
    if not parametric_path.exists():
        raise FileNotFoundError(f"Baseline generation completed but expected file is still missing: {parametric_path}")


def _scan_points(config: dict, specs: Sequence[object], x0: np.ndarray) -> list[list[float]]:
    names = [spec.name for spec in specs]  # type: ignore[attr-defined]
    points = [x0.tolist()]
    for item in config.get("scan_points", []):
        values = dict(zip(names, x0.tolist()))
        values.update({str(key): float(value) for key, value in item.items()})
        points.append([values[name] for name in names])
    quick_count = int(config.get("quick_scan_count", 0) or 0)
    missing = max(0, quick_count - (len(points) - 1))
    if missing:
        bounds = np.array([[float(spec.low), float(spec.high)] for spec in specs], dtype=float)  # type: ignore[attr-defined]
        lhs = latin_hypercube_sampling(bounds, missing, seed=int(config.get("quick_scan_seed", 42)))
        points.extend(lhs.tolist())
    return points


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
