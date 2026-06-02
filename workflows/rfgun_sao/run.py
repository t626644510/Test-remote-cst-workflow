"""Experimental RF gun SAO runner -- single-pass baseline.

Usage from project root::

    .venv\Scripts\python -m workflows.rfgun_sao.run
    .venv\Scripts\python -m workflows.rfgun_sao.run --seed 43
    .venv\Scripts\python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.yaml

The backwards-compatible root entry point ``run_workflow_1.py`` still
delegates to ``workflows.rfgun_single_pass.run`` during A-series
consolidation.  It is intentionally not repointed to this module yet.
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
# run.py lives at workflows/rfgun_sao/run.py  -->  parents[2] = project root
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_SRC_DIR: str = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Default config is the WF1-specific file co-located with this runner.
DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().with_name("config.yaml")

# ---- cst_optimization imports (require SRC_DIR on sys.path) ---------------
from cst_optimization.checkpoint import CheckpointManager
from workflows.rfgun_sao.records import (
    append_jsonl_record,
    build_evaluation_record,
    resolve_records_config,
)

# ---- Module-level logger --------------------------------------------------
_logger: logging.Logger = logging.getLogger("workflow_1")


def _checkpoint_metric_names_from_wf_ref(wf_ref: list) -> list[str] | None:
    """Extract and validate metric names from *wf_ref* for checkpoint recording.

    Returns ``None`` (with no exception) when the names are unavailable
    or fail validation, so the caller can fall back to ``mark_failed``
    with a stable error.

    Validation rules
    ----------------
    - *wf_ref* must be non-empty.
    - ``wf_ref[0]`` must have ``.objective_names``.
    - ``.objective_names`` must be an iterable of non-empty ``str``.
    - ``.objective_names`` must not be a ``str`` or ``bytes`` (which would
      be misinterpreted as a sequence of characters).
    - Each element must be a non-empty ``str``.
    - Names must not contain duplicates.
    """
    if not wf_ref:
        return None
    obj = wf_ref[0]
    names = getattr(obj, "objective_names", None)
    if names is None:
        return None
    if isinstance(names, (str, bytes)):
        return None
    try:
        result = list(names)
    except TypeError:
        return None
    if not result:
        return None
    for n in result:
        if not isinstance(n, str) or not n.strip():
            return None
    if len(set(result)) != len(result):
        return None
    return result


def _record_checkpoint_evaluation(
    ckpt: CheckpointManager,
    wf_ref: list,
    x_phys: np.ndarray,
    raw_values: np.ndarray,
    penalties: np.ndarray,
    solver_ok: bool,
    error: str,
) -> None:
    """Record one evaluation result into *ckpt* with stable semantics.

    The decision to ``mark_completed`` or ``mark_failed`` is driven by
    ``solver_ok`` first, then by ``all_finite(raw_values)``, and finally
    by whether *wf_ref* contains an object with ``.objective_names``.

    Rules
    -----
    1. ``solver_ok=True`` **and** all raw values finite **and** *wf_ref*
       populated → ``mark_completed`` with ``solver_ok=True``.
    2. Otherwise → ``mark_failed`` with a stable error string (preserving
       the passed *error* if non-empty; falling back to an explanatory
       string otherwise).

    This replaces the old heuristic that based the decision on
    ``all_finite(raw_values)`` alone, which could ``mark_completed`` a
    record whose solver had actually failed.
    """
    idx = ckpt.add_pending(x_phys)
    all_finite = bool(np.all(np.isfinite(raw_values)))
    metric_names = _checkpoint_metric_names_from_wf_ref(wf_ref)

    if solver_ok and all_finite and metric_names is not None:
        if (len(metric_names) != len(raw_values)
                or len(metric_names) != len(penalties)):
            ckpt.mark_failed(
                idx, error="checkpoint_metric_length_mismatch",
            )
            ckpt.save()
            return
        raw_dict = dict(zip(metric_names, raw_values))
        pen_dict = dict(zip(metric_names, penalties))
        ckpt.mark_completed(
            idx,
            raw_values=raw_dict,
            penalties=pen_dict,
            solver_ok=True,
        )
    else:
        if not error:
            if not solver_ok:
                error = "checkpoint_solver_failed"
            elif not all_finite:
                error = "non_finite_raw_values"
            elif metric_names is None:
                error = "checkpoint_objective_names_unavailable"
            else:
                error = "checkpoint_record_failed"
        ckpt.mark_failed(idx, error=error)

    ckpt.save()


def _record_jsonl_sidecar_evaluation(
    records_cfg: dict,
    wf_ref: list,
    iteration: int,
    x_phys: np.ndarray,
    raw_values: np.ndarray,
    penalties: np.ndarray,
    solver_ok: bool,
    error: str,
    *,
    diagnostics: dict | None = None,
    gate_results: dict | None = None,
    extra_metadata: dict | None = None,
) -> bool:
    """Optionally append an evaluation record to the JSONL sidecar.

    This is a best-effort diagnostic ledger only.  Failures are logged as
    warnings and do **not** propagate to the checkpoint, optimizer, or
    exit path.

    Parameters
    ----------
    records_cfg : dict
        Resolved records config (``{"enabled": bool, "path": str|None}``).
    wf_ref : list
        Workflow reference for metric name extraction.
    iteration : int
        Evaluation iteration index.
    x_phys : np.ndarray
        Physical parameter vector.
    raw_values : np.ndarray
        Raw objective values.
    penalties : np.ndarray
        Penalty values.
    solver_ok : bool
        Whether the solver completed.
    error : str
        Error message.

    Returns
    -------
    bool
        ``True`` if a record was written, ``False`` if disabled or failed.
    """
    if not records_cfg.get("enabled"):
        return False
    path = records_cfg.get("path")
    if not path:
        return False

    try:
        metric_names = _checkpoint_metric_names_from_wf_ref(wf_ref)
        if metric_names is None:
            _logger.warning("JSONL sidecar: metric names unavailable, skipping")
            return False

        if len(metric_names) != len(raw_values) or len(metric_names) != len(penalties):
            _logger.warning(
                "JSONL sidecar: length mismatch (names=%d, raw=%d, pen=%d), skipping",
                len(metric_names), len(raw_values), len(penalties),
            )
            return False

        meta: dict[str, object] = {
            "source": "rfgun_sao.run.checkpoint_callback",
            "authoritative_record": "checkpoint",
        }
        if extra_metadata:
            meta.update(extra_metadata)

        record = build_evaluation_record(
            iteration=iteration,
            x_phys=x_phys,
            objective_names=metric_names,
            raw_values=raw_values,
            penalties=penalties,
            solver_ok=solver_ok,
            error=error,
            diagnostics=diagnostics,
            gate_results=gate_results,
            metadata=meta,
        )
        append_jsonl_record(path, record)
        return True
    except Exception as exc:
        _logger.warning("JSONL sidecar write failed: %s", exc)
        return False


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


def _cleanup_workflow_connection(
    workflow,
    *,
    force: bool = False,
) -> dict:
    """Best-effort cleanup of the CST connection on a workflow container.

    Parameters
    ----------
    workflow :
        A workflow container (may be ``None``, lack ``_conn``, or have
        ``_conn = None``).
    force : bool
        Whether to force-close the connection (used on interrupt paths).

    Returns
    -------
    dict
        Cleanup outcome summary: ``{"attempted", "force", "pid",
        "closed", "error"}``.
    """
    result: dict = {
        "attempted": False,
        "force": force,
        "pid": None,
        "closed": False,
        "error": "",
    }
    if workflow is None:
        return result
    conn = getattr(workflow, "_conn", None)
    if conn is None:
        return result
    result["attempted"] = True
    try:
        pid = getattr(conn, "pid", None)
        result["pid"] = pid
    except Exception:
        pass
    try:
        conn.close(force=force)
        result["closed"] = True
    except Exception as exc:
        msg = str(exc)[:200]
        result["error"] = msg
        _logger.warning("CST cleanup (force=%s, pid=%s): %s", force, result["pid"], msg)
    return result


def _should_use_enriched_jsonl(cfg: dict, records_cfg: dict) -> bool:
    """Whether to use the two-pass enriched JSONL callback.

    The enriched callback carries diagnostics, gate_results, and contextual
    metadata.  It is only applicable when:
    - JSONL records are enabled, and
    - evaluation mode is ``two_pass``.

    single_pass mode always uses the core-only fallback in ``_on_evaluation``.
    """
    if not records_cfg.get("enabled"):
        return False
    eval_mode = str(cfg.get("evaluation", {}).get("mode", "single_pass")).strip().lower()
    return eval_mode == "two_pass"


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
    records_cfg = resolve_records_config(cfg)
    if records_cfg.get("enabled"):
        _logger.info(
            "JSONL evaluation records enabled: %s",
            records_cfg.get("path"),
        )
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
    _eval_counter: list[int] = [0]

    # Determine whether the two-pass enriched JSONL callback should be used.
    # single_pass + enabled -> use core-only fallback in _on_evaluation.
    # two_pass + enabled -> use enrichment callback from the evaluator,
    #   and skip core-only fallback to avoid duplicate JSONL writes.
    use_enriched_jsonl: bool = _should_use_enriched_jsonl(cfg, records_cfg)

    def _enrichment_callback(
        *,
        x_phys,
        raw_values,
        penalties,
        solver_ok,
        error,
        diagnostics=None,
        gate_results=None,
        metadata=None,
    ):
        iteration = int(_eval_counter[0])
        _eval_counter[0] += 1
        _record_jsonl_sidecar_evaluation(
            records_cfg, _wf_ref, iteration,
            np.asarray(x_phys), np.asarray(raw_values),
            np.asarray(penalties), solver_ok, error,
            diagnostics=diagnostics,
            gate_results=gate_results,
            extra_metadata=metadata,
        )

    def _on_evaluation(x_phys, raw_values, penalties, solver_ok, error):
        _record_checkpoint_evaluation(
            ckpt, _wf_ref, x_phys, raw_values, penalties,
            solver_ok, error,
        )
        # Core-only JSONL sidecar: used for single_pass or when JSONL disabled.
        # When use_enriched_jsonl is True, the enriched callback from the
        # two-pass evaluator handles the JSONL write instead, so we skip here.
        if not use_enriched_jsonl:
            _record_jsonl_sidecar_evaluation(
                records_cfg, _wf_ref, int(_eval_counter[0]),
                x_phys, raw_values, penalties, solver_ok, error,
            )
        _eval_counter[0] += 1

    from workflows.rfgun_sao.workflow import build_workflow_1  # noqa: F811

    workflow, opt, evaluator = build_workflow_1(
        cfg,
        checkpoint_callback=_on_evaluation,
        evaluation_record_callback=(
            _enrichment_callback if use_enriched_jsonl else None
        ),
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
    if ckpt.load():
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

    cleanup_info: dict = {}
    try:
        result = opt.optimize(
            evaluator=evaluator,
            prior_data=prior_data,
        )
        ckpt.clear()
        _logger.info("Workflow 1 completed. Best: %s", result)
        print(f"\nDone. Best X: {result.x_opt}")
        print(f"Best F: {result.f_opt}")
    except KeyboardInterrupt:
        _logger.info("Workflow 1 interrupted by user -- checkpoint preserved")
        cleanup_info = _cleanup_workflow_connection(workflow, force=True)
        print("\nInterrupted. Checkpoint saved.")
    finally:
        if not cleanup_info.get("attempted"):
            cleanup_info = _cleanup_workflow_connection(workflow)
        _logger.info(
            "CST cleanup: attempted=%s closed=%s pid=%s",
            cleanup_info.get("attempted"),
            cleanup_info.get("closed"),
            cleanup_info.get("pid"),
        )
        print(
            f"CST cleanup: attempted={cleanup_info.get('attempted')} "
            f"closed={cleanup_info.get('closed')} "
            f"pid={cleanup_info.get('pid') or 'none'}"
        )

    print(f"Log: {_os.path.join(ckpt_dir, 'workflow_1_runtime.log')}")


if __name__ == "__main__":
    main()
