"""Live-CST campaign runner for RF-CEM 500 MHz parametric optimization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence

import numpy as np
import yaml

from cst_optimization.objectives.base import ObjectiveFunction
from cst_optimization.objectives.modes import Minimize
from cst_optimization.optimization.sao import SurrogateAssistedOptimizer
from cst_optimization.parameters.base import ParamRange
from cst_optimization.parameters.geometry import GeometryParameter
from rf_cem.parametric_geometry.optimization_adapter import (
    baseline_vector,
    build_parameter_set,
    build_parameter_specs,
    generate_candidate_package,
)
from workflows.rf_cem_500mhz_parametric_opt.evaluator import scalar_penalty
from workflows.rf_cem_500mhz_parametric_opt.runner import (
    _ensure_baseline_parametric_geometry,
    _scan_points,
)


class _ScalarPenaltyObjective(ObjectiveFunction):
    """Placeholder objective name for SAO when live evaluator supplies values."""

    name = "rf_cem_scalar_penalty"
    unit = "penalty"

    def __init__(self) -> None:
        super().__init__(reader_factory=lambda: None, mode=Minimize())  # type: ignore[arg-type]

    def raw_value(self) -> float:  # pragma: no cover - SAO uses external evaluator.
        raise RuntimeError("RF-CEM live campaigns supply objective values through evaluator(x)")


class LiveCampaignEvaluator:
    """Generate RF-CEM candidates, run verified live-CST diagnostic, and record results."""

    def __init__(
        self,
        *,
        appendix: Path,
        output_dir: Path,
        parameter_set,
        selected_variant: str,
        template_project_dir: Path,
        library_path: str,
        baseline: np.ndarray,
        target_frequency_mhz: float,
        frequency_window_mhz: tuple[float, float],
        q_soft_floor: float,
        connect_mode: str,
        timeout_s: float,
        solver_timeout_s: float,
        evaluate_templates: bool,
        campaign_metadata: dict | None = None,
    ) -> None:
        self.appendix = appendix
        self.output_dir = output_dir
        self.parameter_set = parameter_set
        self.selected_variant = selected_variant
        self.template_project_dir = template_project_dir
        self.library_path = library_path
        self.baseline = np.asarray(baseline, dtype=float)
        self.target_frequency_mhz = target_frequency_mhz
        self.frequency_window_mhz = frequency_window_mhz
        self.q_soft_floor = q_soft_floor
        self.connect_mode = connect_mode
        self.timeout_s = timeout_s
        self.solver_timeout_s = solver_timeout_s
        self.evaluate_templates = evaluate_templates
        self.campaign_metadata = campaign_metadata or {}
        self.records_path = output_dir / "live_records.jsonl"
        self._next_index = 1
        self.warm_start = self.baseline

    def evaluate(self, values: np.ndarray, *, index: int | None = None) -> dict:
        """Evaluate one physical parameter vector and append a JSONL record."""
        if index is None:
            index = self._next_index
            self._next_index += 1
        started = time.time()
        parameter_values = self.parameter_set.to_dict(np.asarray(values, dtype=float))
        candidate_id = f"candidate_{index:03d}"
        candidate_dir = self.output_dir / "candidates" / candidate_id
        project_dir = self.output_dir / "cst_projects"
        project_path = project_dir / f"{candidate_id}_postprocess_solver.cst"
        project_dir.mkdir(parents=True, exist_ok=True)
        try:
            package = generate_candidate_package(
                appendix=self.appendix,
                output_dir=candidate_dir,
                parameter_values=parameter_values,
                selected_variant=self.selected_variant,
            )
            validation = json.loads(Path(package["geometry_validation"]).read_text(encoding="utf-8"))
            if validation.get("blocking_errors"):
                record = self._record(
                    index=index,
                    status="GEOMETRY_INVALID",
                    parameter_values=parameter_values,
                    candidate_dir=candidate_dir,
                    project_path=project_path,
                    elapsed_s=time.time() - started,
                    error="; ".join(str(item) for item in validation.get("blocking_errors", [])),
                )
                self._append_record(record)
                return record
            completed = subprocess.run(
                self._live_command(candidate_dir, project_path),
                cwd=Path.cwd(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=max(self.solver_timeout_s + 600.0, self.timeout_s + 600.0),
            )
            report_path = candidate_dir / "live_postprocessing" / "live_postprocessing_diagnostic_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            objective_values = _read_objective_values(report)
            novelty = _novelty_score(np.asarray(values, dtype=float), self.baseline, self.parameter_set.bounds)
            status = "SUCCESS" if objective_values else "RESULT_READBACK_FAILED"
            objective = (
                scalar_penalty(
                    objective_values,
                    target_frequency_mhz=self.target_frequency_mhz,
                    frequency_window_mhz=self.frequency_window_mhz,
                    q_soft_floor=self.q_soft_floor,
                    novelty_score=novelty,
                )
                if objective_values
                else 1.0e9
            )
            record = self._record(
                index=index,
                status=status,
                parameter_values=parameter_values,
                candidate_dir=candidate_dir,
                project_path=project_path,
                elapsed_s=time.time() - started,
                objective_values=objective_values,
                scalar_objective=objective,
                novelty_score=novelty,
                returncode=completed.returncode,
                diagnostic_report=report_path,
                process_output=completed.stdout[-8000:],
            )
        except Exception as exc:
            record = self._record(
                index=index,
                status="UNKNOWN_ERROR",
                parameter_values=parameter_values,
                candidate_dir=candidate_dir,
                project_path=project_path,
                elapsed_s=time.time() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        self._append_record(record)
        return record

    def __call__(self, values: np.ndarray) -> float:
        record = self.evaluate(values)
        return float(record.get("scalar_objective", 1.0e9))

    def _live_command(self, candidate_dir: Path, project_path: Path) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "rf_cem.live_500mhz_postprocessing_diagnostic",
            "--package-dir",
            str(candidate_dir),
            "--template-project-dir",
            str(self.template_project_dir),
            "--library-path",
            self.library_path,
            "--project-path",
            str(project_path),
            "--connect-mode",
            self.connect_mode,
            "--timeout-s",
            str(self.timeout_s),
            "--solver-timeout-s",
            str(self.solver_timeout_s),
            "--run-solver",
        ]
        if self.evaluate_templates:
            command.append("--evaluate-templates")
        return command

    def _record(self, **kwargs) -> dict:
        return {
            "schema_version": "rf_cem_live_campaign_record.v0",
            "timestamp_unix": time.time(),
            "selected_variant": self.selected_variant,
            "campaign_metadata": self.campaign_metadata,
            **kwargs,
            "candidate_dir": str(kwargs["candidate_dir"]),
            "project_path": str(kwargs["project_path"]),
            "diagnostic_report": str(kwargs.get("diagnostic_report", "")),
        }

    def _append_record(self, record: dict) -> None:
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        with self.records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run quick live-CST campaign or SAO campaign."""
    parser = argparse.ArgumentParser(
        prog="python -m workflows.rf_cem_500mhz_parametric_opt.live_campaign",
        description="Run RF-CEM 500 MHz live-CST campaign using verified diagnostic path.",
    )
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--mode", choices=("quick-live", "sao"), default="quick-live")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--template-project-dir", type=Path, required=True)
    parser.add_argument("--library-path", required=True)
    parser.add_argument("--connect-mode", choices=("new", "any", "any_or_new"), default="new")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--solver-timeout-s", type=float, default=7200.0)
    parser.add_argument("--evaluate-templates", action="store_true")
    parser.add_argument("--start-at-index", type=int, default=1)
    parser.add_argument("--max-evals", type=int, default=None)
    parser.add_argument("--n-initial", type=int, default=None)
    parser.add_argument("--n-iterations", type=int, default=None)
    parser.add_argument(
        "--seed-candidate-index",
        type=int,
        default=None,
        help="Use a configured quick-scan candidate as the SAO warm start, e.g. 4 for candidate_004.",
    )
    parser.add_argument(
        "--local-bounds-scale",
        type=float,
        default=1.0,
        help="For seeded SAO, shrink each parameter bound around the seed. 1.0 keeps full bounds; 0.35 uses a local trust region.",
    )
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    output_dir = args.output_dir or Path(config.get("live_campaign_output_dir", "runs/rf_cem_500mhz_live_campaign"))
    appendix = Path(config.get("appendix", "Appendix/500MHz_baseline"))
    baseline_parametric = Path(config.get("baseline_parametric_geometry", "runs/parametric_geometry_500mhz/metadata/parametric_geometry.v0.json"))
    selected_variant = str(config.get("selected_variant", "free_equator_smooth"))
    parameter_names = [str(item) for item in config.get("parameters", [])] or None
    parameter_preset = str(config.get("parameter_preset", "exploratory_12d"))
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
    seed_info = _seed_from_quick_scan(args.seed_candidate_index, config, specs, x0)
    if seed_info:
        x0 = seed_info["vector"]
        parameter_set = _localized_parameter_set(parameter_set, x0, args.local_bounds_scale)
    evaluator = LiveCampaignEvaluator(
        appendix=appendix,
        output_dir=output_dir,
        parameter_set=parameter_set,
        selected_variant=selected_variant,
        template_project_dir=args.template_project_dir,
        library_path=args.library_path,
        baseline=x0,
        target_frequency_mhz=float(config.get("objectives", {}).get("frequency_mhz", {}).get("target", config.get("target_frequency_mhz", 500.0))),
        frequency_window_mhz=tuple(float(v) for v in config.get("frequency_window_mhz", [490.0, 510.0])),  # type: ignore[arg-type]
        q_soft_floor=float(config.get("q_soft_floor", 30000.0)),
        connect_mode=args.connect_mode,
        timeout_s=args.timeout_s,
        solver_timeout_s=args.solver_timeout_s,
        evaluate_templates=args.evaluate_templates,
        campaign_metadata={
            "mode": args.mode,
            "seed_candidate_index": args.seed_candidate_index,
            "seed_parameter_values": parameter_set.to_dict(x0),
            "local_bounds_scale": args.local_bounds_scale,
            "search_semantics": "seeded_local_sao" if args.mode == "sao" and args.seed_candidate_index else "quick_scan_or_global_sao",
        },
    )
    if args.mode == "quick-live":
        points = _scan_points(config, specs, x0)
        selected = [
            (index, np.asarray(point, dtype=float))
            for index, point in enumerate(points, start=1)
            if index >= args.start_at_index
        ]
        if args.max_evals is not None:
            selected = selected[: args.max_evals]
        for index, point in selected:
            print(f"Running live-CST candidate_{index:03d}")
            evaluator.evaluate(point, index=index)
    else:
        sao_cfg = config.get("sao_exploratory", {}) or {}
        n_dims = len(specs)
        n_initial = args.n_initial or max(int(sao_cfg.get("n_initial_min", 36)), int(sao_cfg.get("n_initial_per_dimension", 3)) * n_dims)
        n_iterations = args.n_iterations if args.n_iterations is not None else int(sao_cfg.get("n_iterations", 120))
        if args.max_evals is not None:
            n_initial = min(n_initial, args.max_evals)
            n_iterations = max(0, min(n_iterations, args.max_evals - n_initial))
        optimizer = SurrogateAssistedOptimizer(
            parameter_set,
            [_ScalarPenaltyObjective()],
            seed=int(sao_cfg.get("seed", 42)),
            n_initial=n_initial,
            n_iterations=n_iterations,
        )
        result = optimizer.optimize(evaluator=evaluator)
        _write_json(
            output_dir / "sao_result.json",
            {
                "schema_version": "rf_cem_sao_result.v0",
                "x_opt": result.x_opt.tolist(),
                "f_opt": result.f_opt.tolist(),
                "history_x": [item.tolist() for item in result.history_x],
                "history_f": [item.tolist() for item in result.history_f],
                "n_evaluations": result.n_evaluations,
                "metadata": result.metadata,
                "parameter_names": parameter_set.names,
                "seed_candidate_index": args.seed_candidate_index,
                "seed_parameter_values": parameter_set.to_dict(x0),
                "local_bounds_scale": args.local_bounds_scale,
            },
        )
    _write_summary(output_dir)
    print(f"Wrote live campaign records to {output_dir / 'live_records.jsonl'}")
    print(f"Wrote live campaign summary to {output_dir / 'live_summary.json'}")
    return 0


def _read_objective_values(report: dict) -> dict[str, float]:
    values = report.get("result_tree_probe", {}).get("scalar_readback", {})
    result = {}
    for key in ("frequency_mhz", "r_over_q_ohm", "q_factor"):
        item = values.get(key, {})
        if item.get("status") != "ok":
            return {}
        result[key] = float(item["value"])
    result["shunt_impedance_ohm"] = result["r_over_q_ohm"] * result["q_factor"]
    return result


def _novelty_score(values: np.ndarray, baseline: np.ndarray, bounds: np.ndarray) -> float:
    span = np.maximum(bounds[:, 1] - bounds[:, 0], 1e-12)
    normalized = (values - baseline) / span
    return float(np.linalg.norm(normalized) / max(len(values) ** 0.5, 1.0))


def _seed_from_quick_scan(index: int | None, config: dict, specs: Sequence[object], x0: np.ndarray) -> dict | None:
    if index is None:
        return None
    points = _scan_points(config, specs, x0)
    if index < 1 or index > len(points):
        raise ValueError(f"seed candidate index {index} is outside configured quick scan range 1..{len(points)}")
    return {
        "index": index,
        "vector": np.asarray(points[index - 1], dtype=float),
    }


def _localized_parameter_set(parameter_set, seed: np.ndarray, scale: float):
    scale = float(scale)
    if scale <= 0.0:
        raise ValueError("--local-bounds-scale must be > 0")
    if scale >= 0.999999:
        return parameter_set
    bounds = parameter_set.bounds
    localized = []
    for idx, parameter in enumerate(parameter_set.parameters):
        low, high = float(bounds[idx, 0]), float(bounds[idx, 1])
        center = float(seed[idx])
        half_width = (high - low) * scale / 2.0
        local_low = max(low, center - half_width)
        local_high = min(high, center + half_width)
        if local_high <= local_low:
            local_low, local_high = low, high
        localized.append(
            GeometryParameter(
                parameter.name,
                ParamRange(local_low, local_high),
                display_name=getattr(parameter, "display_name", parameter.name),
                unit=getattr(parameter, "unit", "mm"),
            )
        )
    return type(parameter_set)(localized)


def _write_summary(output_dir: Path) -> None:
    records = []
    path = output_dir / "live_records.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    successful = [record for record in records if record.get("status") == "SUCCESS"]

    def best_by(key: str, reverse: bool = False) -> dict | None:
        if not successful:
            return None
        return sorted(successful, key=lambda item: float(item.get("objective_values", {}).get(key, float("-inf") if reverse else float("inf"))), reverse=reverse)[0]

    summary = {
        "schema_version": "rf_cem_live_campaign_summary.v0",
        "record_count": len(records),
        "success_count": len(successful),
        "best_frequency_fit": _best_frequency_fit(successful),
        "best_r_over_q": best_by("r_over_q_ohm", reverse=True),
        "best_shunt_impedance": best_by("shunt_impedance_ohm", reverse=True),
        "records_path": str(path),
    }
    _write_json(output_dir / "live_summary.json", summary)


def _best_frequency_fit(records: list[dict]) -> dict | None:
    if not records:
        return None
    return sorted(records, key=lambda item: abs(float(item.get("objective_values", {}).get("frequency_mhz", 1e9)) - 500.0))[0]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
