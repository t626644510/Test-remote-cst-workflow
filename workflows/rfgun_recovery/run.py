from __future__ import annotations

"""Workflow 3 runner — single-project recovery optimisation.

Usage as module::

    python -m workflows.rfgun_recovery.run
    python -m workflows.rfgun_recovery.run --resume-from D:/Results/workflow3/stage_2
"""

import argparse
import copy
import logging
import os
import signal
import sys

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

try:
    import yaml
except ModuleNotFoundError as exc:
    if exc.name == "yaml":
        print(
            "Missing dependency: PyYAML.\n"
            "Run this script with the project virtual environment, e.g.:\n"
            r"  .\.venv\Scripts\python.exe run_workflow_3.py"
        )
        sys.exit(1)
    raise

import numpy as np

from cst_optimization.checkpoint import CheckpointManager
from cst_optimization.runner import BaseRunner
from workflows.rfgun_recovery.workflow import build_workflow_3

_interrupt_count = 0
_logger = logging.getLogger("workflow_3")


def _on_interrupt(signum: int, frame: object) -> None:
    global _interrupt_count
    _interrupt_count += 1
    if _interrupt_count == 1:
        print(
            "\nCtrl+C received - waiting for current CST operation to finish...\n"
            "  (press Ctrl+C again to force-exit immediately)",
            flush=True,
        )
    else:
        print("\nForce exiting.", flush=True)
        os._exit(130)


signal.signal(signal.SIGINT, _on_interrupt)


def _setup_runtime_logging(cfg: dict) -> str:
    output_dir = cfg.get("logging", {}).get("output_dir", "D:/Results/workflow3")
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "workflow_3_runtime.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    return log_path


def _parameter_bounds(entry: dict) -> tuple[float, float]:
    nominal = float(entry["nominal"])
    delta_minus = float(entry.get("delta_minus", entry.get("delta", 0.0)))
    delta_plus = float(entry.get("delta_plus", entry.get("delta", 0.0)))
    low = float(entry.get("low", nominal - delta_minus))
    high = float(entry.get("high", nominal + delta_plus))
    return low, high


def _make_stage_config(
    base_cfg: dict,
    stage_name: str,
    stage_index: int,
    best_x: object | None = None,
) -> dict:
    cfg = copy.deepcopy(base_cfg)

    base_output = cfg.get("logging", {}).get("output_dir", "D:/Results/workflow3")
    cfg.setdefault("logging", {})
    cfg["logging"]["output_dir"] = os.path.join(base_output, stage_name)

    staged = cfg.get("optimization", {}).get("staged_search", {})
    stage2_cfg = staged.get("stage_2", {})

    if stage_index == 1 and best_x is not None:
        cfg["optimization"]["n_initial"] = int(stage2_cfg.get("n_initial", cfg["optimization"].get("n_initial", 12)))
        cfg["optimization"]["n_iterations"] = int(stage2_cfg.get("n_iterations", cfg["optimization"].get("n_iterations", 40)))

        shrink_factor = float(stage2_cfg.get("shrink_factor", 0.35))
        recenter = bool(stage2_cfg.get("recenter_on_best", True))

        for idx, entry in enumerate(cfg.get("parameters", [])):
            if not entry.get("enabled", True):
                continue
            current_low, current_high = _parameter_bounds(entry)
            current_span = current_high - current_low
            center = float(best_x[idx]) if recenter else float(entry["nominal"])
            half_span = 0.5 * current_span * shrink_factor
            min_step = float(entry.get("min_step", 0.0))
            half_span = max(half_span, 2.0 * min_step)
            new_low = max(current_low, center - half_span)
            new_high = min(current_high, center + half_span)
            if new_low >= new_high:
                new_low = center - max(min_step, 1e-6)
                new_high = center + max(min_step, 1e-6)

            entry["nominal"] = center
            entry["low"] = float(new_low)
            entry["high"] = float(new_high)
            entry.pop("delta_minus", None)
            entry.pop("delta_plus", None)
            entry.pop("delta", None)

    return cfg


def _merge_prior_data(
    ckpt_data: tuple | None,
    resume_data: tuple | None,
) -> tuple | None:
    """Merge checkpoint and JSONL-resume prior datasets, deduplicating by X."""
    if ckpt_data is None and resume_data is None:
        return None
    parts = []
    if ckpt_data is not None:
        parts.append(ckpt_data)
    if resume_data is not None:
        parts.append(resume_data)
    X_all = np.vstack([p[0] for p in parts])
    y_all = np.concatenate([p[1] for p in parts])
    # Deduplicate by rounded X (1e-6 tolerance)
    _, unique_idx = np.unique(np.round(X_all, 6), axis=0, return_index=True)
    return X_all[unique_idx], y_all[unique_idx]


def _run_single_stage(cfg: dict, stage_name: str, resume_jsonl_path: str = ""):
    _logger.info(
        "%s: building workflow and connecting to CST (project=%s)",
        stage_name,
        cfg.get("project", {}).get("cst_path", "<missing>"),
    )

    # 鈹€鈹€ Checkpoint for this stage 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    output_dir = cfg.get("logging", {}).get("output_dir", "D:/Results/workflow3")
    ckpt = CheckpointManager(f"{output_dir}/{stage_name}")
    has_ckpt = ckpt.load()
    prior_data = None
    if has_ckpt and ckpt.completed_count > 0:
        prior_X, prior_y = ckpt.get_warm_xy()
        if len(prior_X) > 0:
            prior_data = (prior_X, prior_y)
            print(f"[{stage_name}] Resuming from checkpoint: "
                  f"{ckpt.completed_count} completed, {ckpt.pending_count} pending")

    # 鈹€鈹€ Checkpoint callback 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    # _wf_ref will be assigned after build_workflow_3; closure captures
    # the name, not the value, so it resolves at call time.
    _wf_ref: list = []

    def _on_evaluation(
        x_phys: np.ndarray,
        raw_values: np.ndarray,
        penalties: np.ndarray,
        solver_ok: bool,
        error: str,
    ) -> None:
        idx = ckpt.add_pending(x_phys)
        all_finite = bool(np.all(np.isfinite(raw_values)))
        if all_finite and _wf_ref:
            metric_names = _wf_ref[0].objective_names
            raw_dict = dict(zip(metric_names, raw_values))
            pen_dict = dict(zip(metric_names, penalties))
            ckpt.mark_completed(idx, raw_values=raw_dict, penalties=pen_dict, solver_ok=solver_ok)
        elif not all_finite:
            ckpt.mark_failed(idx, error=error)
        ckpt.save()

    workflow, opt, evaluator = build_workflow_3(
        cfg, resume_jsonl_path=resume_jsonl_path, checkpoint_callback=_on_evaluation,
    )
    _wf_ref.append(workflow)

    print(f"[{stage_name}] Parameters: {workflow._params.n_parameters}")
    print(f"[{stage_name}] Objectives: {len(workflow.objective_names)}")
    n_initial = int(cfg.get("optimization", {}).get("n_initial", 0))
    n_iterations = int(cfg.get("optimization", {}).get("n_iterations", 0))
    planned_total = n_initial + n_iterations
    print(
        f"[{stage_name}] Planned evaluations: "
        f"{n_initial} initial + {n_iterations} BO = {planned_total}"
    )
    if workflow._params.constraints is not None:
        print(f"[{stage_name}] Constraints: {workflow._params.constraints.n_constraints}")
    print(f"[{stage_name}] Algorithm: {type(opt).__name__}")
    print("-" * 60)
    _logger.info("%s: evaluation record file = %s", stage_name, workflow.record_path)
    _logger.info(
        "%s: planned evaluations = %d initial + %d iterations = %d",
        stage_name, n_initial, n_iterations, planned_total,
    )

    try:
        bounds_ctrl = getattr(evaluator, "bounds_controller", None)
        # Merge checkpoint prior_data with JSONL resume prior_data
        resume_prior = getattr(evaluator, "prior_data", None)
        merged_prior = _merge_prior_data(prior_data, resume_prior)
        n_extra = int(cfg.get("resume", {}).get("n_initial_extra", 0))
        result = opt.optimize(
            evaluator=evaluator, bounds_controller=bounds_ctrl,
            prior_data=merged_prior, n_initial_extra=n_extra,
        )
        if bounds_ctrl is not None and bounds_ctrl.enabled:
            expanded = result.metadata.get("bounds_expanded", [])
            if expanded:
                names = result.metadata.get("expanded_param_names", [str(i) for i in expanded])
                print(f"[{stage_name}] Phase-2 bounds expanded for: {names}")
        print("=" * 60)
        print(f"{stage_name} complete.")
        print(f"Total evaluations: {result.n_evaluations}")
        print(f"Best params (physical): {result.x_opt}")
        print(f"Best objective value: {result.f_opt}")
        ckpt.clear()
        return result
    except Exception:
        _logger.exception(
            "%s failed after %d logged CST evaluations",
            stage_name,
            workflow.logged_evaluations,
        )
        print(f"[{stage_name}] Checkpoint preserved at {ckpt._path} ({ckpt.completed_count} completed)")
        raise
    finally:
        workflow.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Workflow 3: single-project recovery optimisation")
    parser.add_argument(
        "--resume-from", type=str, default="",
        help="Path to a stage_N/evaluation_records.jsonl from a previous run "
             "(e.g. workflow3/stage_2).  All successful evaluations are pre-loaded "
             "into the GP surrogate and the best point is used as warm_start.",
    )
    args = parser.parse_args()

    cfg_path = os.path.join("config", "workflow_3.yaml")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    runtime_log = _setup_runtime_logging(cfg)
    _logger.info("Workflow 3 starting")
    _logger.info("Runtime log file: %s", runtime_log)
    _logger.info("Working directory: %s", os.getcwd())
    _logger.info("Python executable: %s", sys.executable)
    _logger.info("Config path: %s", os.path.abspath(cfg_path))
    _logger.info(
        "CST library path exists: %s",
        os.path.exists(cfg.get("cst", {}).get("library_path", "")),
    )
    _logger.info(
        "Project path exists: %s",
        os.path.exists(cfg.get("project", {}).get("cst_path", "")),
    )
    _logger.info(
        "connect_mode=%s algorithm=%s",
        cfg.get("cst", {}).get("connect_mode", "any_or_new"),
        cfg.get("optimization", {}).get("algorithm", "sao"),
    )

    try:
        resume_path = args.resume_from
        if resume_path:
            # Resume mode: single stage with prior data, skip staged search
            _logger.info("Resume mode from %s 鈥?skipping staged search", resume_path)
            stage1_cfg = _make_stage_config(cfg, stage_name="resume", stage_index=0)
            result = _run_single_stage(stage1_cfg, "Resume", resume_jsonl_path=resume_path)
        else:
            staged = cfg.get("optimization", {}).get("staged_search", {})
            stage1_cfg = _make_stage_config(cfg, stage_name="stage_1", stage_index=0)
            result = _run_single_stage(stage1_cfg, "Stage 1")

            if staged.get("enabled", False):
                print("=" * 60)
                print("Starting Stage 2 refinement around Stage 1 best point.")
                stage2_cfg = _make_stage_config(
                    cfg,
                    stage_name="stage_2",
                    stage_index=1,
                    best_x=result.x_opt,
                )
                result = _run_single_stage(stage2_cfg, "Stage 2")

        print("=" * 60)
        print("Optimisation complete.")
        print(f"Final best params (physical): {result.x_opt}")
        print(f"Final best objective value: {result.f_opt}")

    except KeyboardInterrupt:
        print("\nInterrupted by user (Ctrl+C) - shutting down...")
        sys.exit(130)

    except Exception:
        print("Fatal error during optimisation:", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


# -- BaseRunner integration (Phase 13) ----------------------------------


class WF3Runner(BaseRunner):
    """WF3 recovery runner — delegates to standalone functions."""

    def __init__(self):
        super().__init__(wf_name="workflow_3", default_config="config/workflow_3.yaml")

    def run(self):
        main()
