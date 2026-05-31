"""Workflow 1 runner -- single-project single-pass frequency-domain SAO optimisation.

Usage from project root::

    .venv\\Scripts\\python -m workflows.rfgun_single_pass.run
    .venv\\Scripts\\python -m workflows.rfgun_single_pass.run --seed 43
    .venv\\Scripts\\python run_workflow_1.py --config workflows/rfgun_single_pass/config.yaml

Watchdog::

    .venv\\Scripts\\python run_watchdog.py -- run_workflow_1.py

The backwards-compatible entry point ``run_workflow_1.py`` (project root)
delegates directly to :func:`main` in this module.
"""

from __future__ import annotations

import argparse
import logging
import os as _os
import signal as _signal
import sys
from pathlib import Path

import numpy as np
import yaml

# ---- Paths ----------------------------------------------------------------
# Must be set up BEFORE any cst_optimization import.
# run.py lives at workflows/rfgun_single_pass/run.py  -->  parents[2] = project root
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_SRC_DIR: str = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Default config is the WF1-specific file co-located with this runner.
DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().with_name("config.yaml")

# ---- cst_optimization imports (require SRC_DIR on sys.path) ---------------
from cst_optimization.checkpoint import CheckpointManager

# ---- Module-level logger --------------------------------------------------
_logger: logging.Logger = logging.getLogger("workflow_1")


def _setup_logging(log_cfg: dict) -> str:
    """Configure root logger with file + stderr handlers.

    Returns the *output_dir* string so callers can derive checkpoint /
    record paths from it.
    """
    output_dir = log_cfg.get("output_dir", "D:/Results")
    wf_dir = _os.path.join(output_dir, "workflow1")
    _os.makedirs(wf_dir, exist_ok=True)
    log_path = _os.path.join(wf_dir, "workflow_1_runtime.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    return output_dir


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for Workflow 1 CLI."""
    parser = argparse.ArgumentParser(description="Workflow 1 SAO optimisation")
    parser.add_argument(
        "--config", type=str, default=str(DEFAULT_CONFIG_PATH),
        help="Path to Workflow 1 YAML config "
             f"(default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Override optimizer seed from config",
    )
    parser.add_argument(
        "--n-iter", type=int, default=None,
        help="Override n_iterations from config",
    )
    parser.add_argument(
        "--n-initial", type=int, default=None,
        help="Override n_initial_samples from config",
    )
    return parser


def main() -> None:
    """Entry point for Workflow 1 SAO optimisation.

    CLI overrides
    -------------
    --config     Path to Workflow 1 YAML config (default: ``config.yaml``
                 next to this runner).
    --seed       Override optimizer seed from config.
    --n-iter     Override ``n_iterations`` from config.
    --n-initial  Override ``n_initial_samples`` from config.
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    config_path: Path = Path(args.config).expanduser().resolve()
    cfg = yaml.safe_load(open(config_path, "r", encoding="utf-8"))
    log_dir = _setup_logging(cfg.get("logging", {}))
    _logger.info("Workflow 1 starting")
    _logger.info("Config: %s", config_path)
    _logger.info("Python: %s", sys.executable)

    # Apply CLI overrides
    if args.seed is not None:
        cfg.setdefault("optimization", {})["seed"] = int(args.seed)
    if args.n_iter is not None:
        cfg.setdefault("optimization", {})["n_iterations"] = int(args.n_iter)
    if args.n_initial is not None:
        cfg.setdefault("optimization", {})["n_initial_samples"] = int(args.n_initial)

    opt_cfg = cfg.get("optimization", {})
    n_initial = int(opt_cfg.get("n_initial_samples", 20))
    n_iterations = int(opt_cfg.get("n_iterations", 100))
    seed = int(opt_cfg.get("seed", 42))
    _logger.info(
        "Params: %d  Objectives: %d  n_initial=%d  n_iter=%d  seed=%d",
        len(cfg.get("parameters", [])),
        len(cfg.get("objectives", [])),
        n_initial, n_iterations, seed,
    )

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------
    ckpt_dir = _os.path.join(log_dir, "workflow1")
    _os.makedirs(ckpt_dir, exist_ok=True)
    ckpt_path = _os.path.join(ckpt_dir, "workflow1.ckpt")
    ckpt = CheckpointManager(ckpt_path)

    _wf_ref: list = []

    def _on_evaluation(x_phys, raw_values, penalties, solver_ok, error):
        idx = ckpt.add_pending(x_phys)
        all_finite = bool(np.all(np.isfinite(raw_values)))
        if all_finite and _wf_ref:
            metric_names = _wf_ref[0].objective_names
            raw_dict = dict(zip(metric_names, raw_values))
            pen_dict = dict(zip(metric_names, penalties))
            ckpt.mark_completed(
                idx, raw_values=raw_dict, penalties=pen_dict,
                solver_ok=solver_ok,
            )
        elif not all_finite:
            ckpt.mark_failed(idx, error=error)
        ckpt.save()

    from workflows.rfgun_single_pass.workflow import build_workflow_1  # noqa: F811

    workflow, opt, evaluator = build_workflow_1(
        cfg, checkpoint_callback=_on_evaluation,
    )
    _wf_ref.append(workflow)

    stage_name = "Workflow 1"
    print(f"[{stage_name}] Parameters: {workflow._params.n_parameters}")
    print(f"[{stage_name}] Objectives: {len(workflow.objective_names)}")
    print(
        f"[{stage_name}] Planned: {n_initial} initial + "
        f"{n_iterations} BO = {n_initial + n_iterations}",
    )
    print("-" * 60)

    _logger.info("Start: %d initial + %d iterations", n_initial, n_iterations)

    # Load prior data from checkpoint for warm-start
    prior_data = None
    if ckpt.loaded_count > 0:
        warm_xy = ckpt.get_warm_xy()
        if warm_xy is not None and len(warm_xy[0]) > 0:
            prior_data = warm_xy
            _logger.info(
                "Warm-start from checkpoint: %d prior evaluations",
                len(warm_xy[0]),
            )

    ctrl_c_count = [0]

    def _sigint_handler(signum, frame):
        ctrl_c_count[0] += 1
        if ctrl_c_count[0] >= 2:
            print("\nForce exit.", flush=True)
            _os._exit(130)
        print(
            "\nWaiting for current evaluation to finish "
            "(Ctrl+C again to force quit)...",
            flush=True,
        )

    try:
        _signal.signal(_signal.SIGINT, _sigint_handler)
    except Exception:
        pass

    try:
        result = opt.optimize(
            evaluator=evaluator,
            prior_data=prior_data,
            n_initial=n_initial,
            n_iterations=n_iterations,
        )
        ckpt.clear()
        _logger.info("Workflow 1 completed. Best: %s", result)
        print(f"\nDone. Best X: {result.get('x', 'N/A')}")
        print(f"Best F: {result.get('fun', 'N/A')}")
    except KeyboardInterrupt:
        _logger.info("Workflow 1 interrupted by user -- checkpoint preserved")
        print("\nInterrupted. Checkpoint saved.")

    print(f"Log: {_os.path.join(ckpt_dir, 'workflow_1_runtime.log')}")


if __name__ == "__main__":
    main()
