"""Workflow 2 runner — HOM antenna multi-project optimisation.

Usage from project root::

    python run_workflow_2.py
    python run_workflow_2.py --auto-resume
    python run_workflow_2.py --auto-resume --heartbeat
    python run_workflow_2.py --warmup-from-db D:/Results/wf2_warmup_total/index.total.jsonl

The root entry point ``run_workflow_2.py`` is a compatibility shim that
delegates here.  Use ``python run_workflow_2.py`` to run.

Reads its co-located ``config.yaml`` (W2-8 runtime source), opens a single CST
with sequential frequency-domain and wakefield solver execution (inter-pass
reset may recreate the DE between phases), builds the orchestrator + optimiser,
and runs the full Bayesian optimisation loop.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path

# ---- Path setup ----------------------------------------------------------------
# run.py lives at workflows/rfgun_hom_antenna/run.py  -->  parents[2] = project root
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_SRC_DIR: str = str(_PROJECT_ROOT / "src")
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import yaml

import numpy as np

from cst_optimization.checkpoint import CheckpointManager
from cst_optimization.runner import BaseRunner
from workflows.rfgun_hom_antenna.recovery import (
    build_recovery_seed,
    infer_checkpoint_source_iterations,
    write_recovery_report,
)
from workflows.rfgun_hom_antenna.workflow import build_workflow_2

# ── Config loader ────────────────────────────────────────────────────────────
# Co-located config.yaml is the Workflow2 runtime source of truth (W2-8).
_DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().with_name("config.yaml")


def _load_workflow2_config(config_path: Path | None = None) -> dict:
    """Load the effective Workflow2 config with fallback section precedence.

    Parameters
    ----------
    config_path : Path or None
        Path to a YAML config file.  If ``None``, the co-located
        ``config.yaml`` is used.

    Returns
    -------
    dict
        The ``workflow_2`` subtree with top-level ``cst``, ``solver``, and
        ``logging`` sections merged in as fallbacks (only when the subtree
        does not already define them).

    Precedence rules (W2-6F, W2-8):
        - ``workflow_2.optimization.solver`` overrides
          ``workflow_2.solver`` for overlapping keys (builder precedence).
        - Top-level fallback sections are only merged when the workflow_2
          subtree does NOT already carry them.
        - The merge is a **reference copy** — mutating the returned dict
          affects the source (current runtime contract, not a safer design).
    """
    if config_path is None:
        config_path = _DEFAULT_CONFIG_PATH

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    wf2_cfg = cfg.get("workflow_2", {})
    if not isinstance(wf2_cfg, dict):
        wf2_cfg = {}

    # Merge top-level cst, solver, logging sections as fallbacks.
    for section in ("cst", "solver", "logging"):
        if section in cfg and section not in wf2_cfg:
            wf2_cfg[section] = cfg[section]

    return wf2_cfg


def _recovery_candidate_indices(ckpt: CheckpointManager) -> list[int]:
    """Return checkpoint rows eligible for cross-process WF2 recovery.

    ``failed_permanent`` remains meaningful for ordinary optimisation, but a
    recovery campaign must be restartable after one process exhausts its local
    retry budget.  Historical rows with that status are therefore reopened by
    the Workflow 2 recovery runner.
    """
    return [
        index
        for index, record in enumerate(ckpt.records)
        if record.status in {"pending", "failed_permanent"}
    ]


def _mark_recovery_retryable(
    ckpt: CheckpointManager,
    checkpoint_index: int,
    *,
    error: str,
    phases_done: list[str],
) -> None:
    """Persist a failed recovery attempt without making it terminal."""
    if phases_done:
        ckpt.mark_phase_done(checkpoint_index, phases=phases_done)
    ckpt.mark_failed(
        checkpoint_index,
        error=error,
        tier_exhausted=False,
    )


def _should_load_warmup(
    warmup_from_db: str,
    *,
    recovery_only: bool,
) -> bool:
    """Whether cleaned prior data is needed for this invocation."""
    return bool(warmup_from_db) and not recovery_only

# ── Ctrl+C handling ──────────────────────────────────────────────────────────
# COM calls (run_solver, DesignEnvironment.close) block the main thread,
# so Python cannot deliver KeyboardInterrupt until the call returns.
# A signal handler gives immediate feedback and a double-tap escape hatch.

_interrupt_count = 0


def _on_interrupt(signum: int, frame: object) -> None:
    global _interrupt_count
    _interrupt_count += 1
    if _interrupt_count == 1:
        print(
            "\nCtrl+C received — waiting for current CST operation to finish...\n"
            "  (press Ctrl+C again to force-exit immediately)",
            flush=True,
        )
    else:
        print("\nForce exiting.", flush=True)
        os._exit(130)


def main() -> None:
    """Run Workflow 2 HOM antenna multi-project optimisation.

    CLI flags
    ---------
    --warmup-from-db PATH
        Load raw evaluation records from JSONL database for GP warmup.
    --auto-resume
        Automatically resume from checkpoint if pending records exist.
    --heartbeat
        Write a heartbeat timestamp file every 60 s for crash detection.
    """
    # ── Signal handler (installed each call; avoids side effects on import) ─
    global _interrupt_count
    _interrupt_count = 0
    signal.signal(signal.SIGINT, _on_interrupt)

    # ── 0. Parse CLI arguments ──────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Workflow 2 — HOM Antenna Multi-Project Optimisation"
    )
    parser.add_argument(
        "--warmup-from-db",
        type=str,
        default="",
        metavar="PATH",
        help="Load raw evaluation records from JSONL database for GP warmup",
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        default=False,
        help="Automatically resume from checkpoint if pending records exist",
    )
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        default=False,
        help="Write a heartbeat timestamp file every 60 s for crash detection",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="",
        metavar="PATH",
        help="Use an explicit Workflow 2 YAML configuration",
    )
    parser.add_argument(
        "--recovery-only",
        action="store_true",
        default=False,
        help="Recover all pending checkpoint records, then exit",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        default=False,
        help="Mark generated schema-v3 records as non-production smoke data",
    )
    args = parser.parse_args()
    if args.recovery_only:
        args.auto_resume = True

    # ── 1. Load config ──────────────────────────────────────────────────────
    config_path = Path(args.config).resolve() if args.config else None
    wf2_cfg = _load_workflow2_config(config_path)
    if not wf2_cfg.get("enabled", False):
        print(
            "workflow_2.enabled is False — set to true in "
            f"{config_path or _DEFAULT_CONFIG_PATH}"
        )
        sys.exit(0)

    # ── 2. Checkpoint (resume from previous crash) ──────────────────────────
    log_dir = (
        wf2_cfg.get("logging", {})
        .get("output_dir", "D:/Results")
    )
    os.makedirs(log_dir, exist_ok=True)

    # Hold a Windows byte-range lock for the lifetime of this process.  A
    # crashed process releases it automatically, while overlapping scheduler
    # and watchdog launches exit before opening a second CST session.
    _run_lock_path = os.path.join(log_dir, "workflow_2.lock")
    _run_lock_file = open(_run_lock_path, "a+b")
    if os.path.getsize(_run_lock_path) == 0:
        _run_lock_file.write(b"0")
        _run_lock_file.flush()
    _run_lock_file.seek(0)
    try:
        import msvcrt
        msvcrt.locking(_run_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print(
            f"Workflow 2 is already running (lock busy: {_run_lock_path})."
        )
        _run_lock_file.close()
        sys.exit(0)

    # ── Terminal log header (so truncated logs have a recoverable start) ─
    _term_log_path = os.path.join(log_dir, "workflow_2_terminal.log")
    try:
        with open(_term_log_path, "a", encoding="utf-8") as _f:
            _f.write(f"\n=== Workflow 2 started {time.strftime('%Y-%m-%d %H:%M:%S')} "
                     f"PID={os.getpid()} ===\n")
    except Exception:
        pass

    ckpt = CheckpointManager(f"{log_dir}/workflow_2")
    has_ckpt = ckpt.load()
    objective_names = [
        entry["name"]
        for entry in wf2_cfg.get("objectives", [])
        if entry.get("enabled", True)
    ]
    from cst_optimization.factory import _resolve_named_weights

    objective_weights = _resolve_named_weights(
        wf2_cfg.get("optimization", {}).get("objective_weights"),
        objective_names,
    )

    # ── Heartbeat thread ────────────────────────────────────────────────────
    _heartbeat_stop = threading.Event()
    if args.heartbeat:
        _hb_path = os.path.join(log_dir, "workflow_2_heartbeat.txt")

        def _heartbeat_loop() -> None:
            while not _heartbeat_stop.is_set():
                try:
                    with open(_hb_path, "w") as f:
                        f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
                _heartbeat_stop.wait(60.0)

        _hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        _hb_thread.start()
        print(f"[heartbeat] writing to {_hb_path} every 60 s")

    # ── Crash recovery: resume partial evaluations ─────────────────────────
    prior_data: tuple[np.ndarray, np.ndarray] | None = None
    gate_prior: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None
    if has_ckpt and ckpt.completed_count > 0:
        prior_X, prior_y = ckpt.get_warm_xy(
            objective_names,
            objective_weights,
        )
        if len(prior_X) > 0:
            prior_data = (prior_X, prior_y)
            print(f"Resuming from checkpoint: {ckpt.completed_count} completed, "
                  f"{ckpt.pending_count} pending")
    if has_ckpt:
        partial = ckpt.partial_records
        if partial:
            print(f"Found {len(partial)} partially-evaluated records")
            if args.auto_resume:
                print("Resuming partial evaluations from saved phase curves...")
            else:
                print("Use --auto-resume to replay saved phases before optimisation.")

    # ── 2b. Warmup from 1D curves database (overrides checkpoint prior_data) ─
    next_db_iteration = 0
    if args.warmup_from_db and not _should_load_warmup(
        args.warmup_from_db,
        recovery_only=args.recovery_only,
    ):
        print(
            "Recovery-only mode: warmup database loading is deferred until "
            "normal optimisation."
        )
    elif _should_load_warmup(
        args.warmup_from_db,
        recovery_only=args.recovery_only,
    ):
        from cst_optimization.database import load_index
        from cst_optimization.factory import _build_objectives
        from workflows.rfgun_hom_antenna.warmup import (
            load_workflow2_warmup,
        )

        index_path = args.warmup_from_db
        print(f"Loading 1D curve database from: {index_path}")
        db_objectives, _, _ = _build_objectives(
            wf2_cfg.get("objectives", [])
        )

        index_records = load_index(index_path)
        db_iterations = [
            int(rec["iter"])
            for rec in index_records
            if isinstance(rec.get("iter"), int)
        ]
        if db_iterations:
            next_db_iteration = max(db_iterations) + 1

        parameter_cfg = wf2_cfg.get("parameters", [])
        parameter_names = [entry["name"] for entry in parameter_cfg]
        warmup_data = load_workflow2_warmup(
            index_path,
            db_objectives,
            weights=objective_weights,
            parameter_names=parameter_names,
        )
        X_db = warmup_data.X
        y_db = warmup_data.scalar_penalties
        penalties_db = warmup_data.penalty_matrix
        measurement_mask_db = warmup_data.measurement_mask
        f2w_ran_db = warmup_data.f2w_ran
        if len(X_db) > 0:
            lows = np.array([float(p["low"]) for p in parameter_cfg])
            highs = np.array([float(p["high"]) for p in parameter_cfg])
            finite = np.all(np.isfinite(X_db), axis=1) & np.isfinite(y_db)
            in_bounds = np.all((X_db >= lows) & (X_db <= highs), axis=1)
            keep = finite & in_bounds
            rejected = int(len(X_db) - np.count_nonzero(keep))
            X_db = X_db[keep]
            y_db = y_db[keep]
            penalties_db = penalties_db[keep]
            measurement_mask_db = measurement_mask_db[keep]
            f2w_ran_db = f2w_ran_db[keep]

            unique_indices: list[int] = []
            seen: set[bytes] = set()
            for i, row in enumerate(X_db):
                key = np.asarray(row, dtype=np.float64).tobytes()
                if key not in seen:
                    seen.add(key)
                    unique_indices.append(i)
            duplicates = len(X_db) - len(unique_indices)
            X_db = X_db[unique_indices]
            y_db = y_db[unique_indices]
            penalties_db = penalties_db[unique_indices]
            measurement_mask_db = measurement_mask_db[unique_indices]
            f2w_ran_db = f2w_ran_db[unique_indices]
            if rejected or duplicates:
                print(
                    f"  filtered: {rejected} invalid/out-of-bounds, "
                    f"{duplicates} duplicate"
                )
        n_valid = len(X_db)
        print(f"  {n_valid} valid evaluations for warmup")
        if n_valid > 0:
            prior_data = (X_db, y_db)
            gate_prior = (
                X_db,
                penalties_db,
                measurement_mask_db,
                f2w_ran_db,
            )
            best_idx = int(np.argmin(y_db))
            print(f"  Best penalty: {float(y_db[best_idx]):.6f} (index {best_idx})")
            measured_counts = {
                name: int(np.count_nonzero(measurement_mask_db[:, index]))
                for index, name in enumerate(objective_names)
            }
            print(f"  Gate measured targets: {measured_counts}")

    # Never overwrite an existing atomized curve file, even when the warmup
    # index was sanitized or renumbered independently of the output folder.
    next_output_iteration = 0
    curves_output_dir = Path(log_dir) / "raw_curves"
    if curves_output_dir.is_dir():
        existing_iterations = []
        for npz_path in curves_output_dir.glob("eval_*.npz"):
            match = re.match(r"eval_(\d+)", npz_path.name)
            if match:
                existing_iterations.append(int(match.group(1)))
        if existing_iterations:
            next_output_iteration = max(existing_iterations) + 1

    # ── 3. Checkpoint callbacks ────────────────────────────────────────────
    def _x_key(x_phys: np.ndarray) -> bytes:
        return np.asarray(x_phys, dtype=np.float64).tobytes()

    _pending_by_x: dict[bytes, int] = {
        _x_key(np.asarray(rec.x, dtype=float)): idx
        for idx, rec in enumerate(ckpt.records)
        if rec.status == "pending"
    }

    def _ensure_pending(x_phys: np.ndarray) -> int:
        key = _x_key(x_phys)
        idx = _pending_by_x.get(key)
        if idx is None:
            idx = ckpt.add_pending(x_phys)
            _pending_by_x[key] = idx
        return idx

    def _on_phase_completed(
        x_phys: np.ndarray,
        iteration: int,
        phases_done: list[str],
        npz_path: str,
    ) -> None:
        idx = _ensure_pending(x_phys)
        ckpt.mark_phase_done(idx, phases=phases_done)
        ckpt.records[idx].error = ""
        ckpt.save()

    def _on_evaluation(
        x_phys: np.ndarray,
        raw_values: np.ndarray,
        penalties: np.ndarray,
        solver_ok: bool,
        error: str,
    ) -> None:
        idx = _ensure_pending(x_phys)
        success = bool(
            solver_ok and np.all(np.isfinite(penalties))
        )
        obj_names = [obj.name for obj in orch.objectives]
        if success:
            ckpt.mark_completed(
                idx,
                raw_values=dict(zip(obj_names, raw_values)),
                penalties=dict(zip(obj_names, penalties)),
                solver_ok=solver_ok,
                phases=list(orch.last_completed_labels) if orch.last_completed_labels else [],
            )
            _pending_by_x.pop(_x_key(x_phys), None)
        else:
            # Record actually-completed phases from orchestrator state
            phases_done = list(orch.last_completed_labels) if orch.last_completed_labels else []
            if phases_done:
                ckpt.mark_phase_done(idx, phases=phases_done)
                ckpt.records[idx].error = error
                ckpt.records[idx].solver_ok = False
            else:
                ckpt.mark_failed(idx, error=error)
        ckpt.save()

    # ── 4. Build orchestrator + optimiser ───────────────────────────────────
    recovery_indices = (
        _recovery_candidate_indices(ckpt)
        if has_ckpt and args.auto_resume
        else []
    )
    recovery_start_iteration = max(
        len(ckpt.records),
        next_db_iteration,
        next_output_iteration,
    )
    optimiser_start_iteration = recovery_start_iteration + (
        len(recovery_indices)
    )
    orch, opt, evaluator, retry_handler = build_workflow_2(
        wf2_cfg,
        checkpoint_callback=_on_evaluation,
        phase_checkpoint_callback=_on_phase_completed,
        start_iteration=optimiser_start_iteration,
    )
    if gate_prior is not None:
        gate_bootstrapped = orch.bootstrap_adaptive_gate(*gate_prior)
        if gate_bootstrapped:
            calibration_count = int(
                wf2_cfg.get("adaptive_gate", {}).get(
                    "calibration_evaluations",
                    2,
                )
            )
            print(
                "Adaptive gate bootstrapped from historical measurements; "
                f"{calibration_count} live full evaluations will be forced "
                "for calibration."
            )

    print(f"Parameters: {orch.n_parameters}")
    print(f"Objectives: {orch.n_objectives}")
    if orch.parameter_set.constraints is not None:
        print(f"Constraints: {orch.parameter_set.constraints.n_constraints}")
    print(f"Algorithm: {type(opt).__name__}")
    print(f"Initial samples: {opt._n_initial},  Iterations: {opt._n_iterations}")
    print("-" * 60)

    # Recover every pending checkpoint point before the optimiser may propose
    # new points. Historical files are selected by physical-parameter hash,
    # never by checkpoint-list position.
    recovery_failures = 0
    if recovery_indices:
        from cst_optimization.database import load_index
        from cst_optimization.workflows.recovery import (
            EvaluationResult,
            EvaluationStatus,
        )

        curves_dir = os.path.join(log_dir, "raw_curves")
        index_path = os.path.join(curves_dir, "index.jsonl")
        index_records = load_index(index_path)
        parameter_names = list(orch.parameter_set.names)
        checkpoint_values = [record.x for record in ckpt.records]
        source_iterations = infer_checkpoint_source_iterations(
            checkpoint_values,
            index_records,
            parameter_names,
        )
        phase_order = [spec.label for spec in orch._specs]
        f2f_label = next(
            spec.label for spec in orch._specs if spec.is_pre_filter
        )
        recovery_jobs: list[dict[str, object]] = []
        output_iteration = recovery_start_iteration

        for checkpoint_index in recovery_indices:
            record = ckpt.records[checkpoint_index]
            x_phys = np.asarray(record.x, dtype=float)
            seed = build_recovery_seed(
                index_path=index_path,
                curves_dir=curves_dir,
                parameter_names=parameter_names,
                parameter_values=x_phys,
                objectives=orch.objectives,
                obj_project_map=orch._obj_project_map,
                ref_project_map=orch._ref_project_map,
                phase_order=phase_order,
                output_iteration=output_iteration,
                smoke_only=args.smoke_only,
                include_smoke_sources=args.smoke_only,
            )
            if seed.source_iter is None:
                seed.source_iter = source_iterations.get(checkpoint_index)
            recovery_jobs.append(
                {
                    "checkpoint_index": checkpoint_index,
                    "x": x_phys,
                    "seed": seed,
                    "source_iter": seed.source_iter,
                    "output_iteration": output_iteration,
                    "recovered_phases": list(seed.recovered_phases),
                    "replay_values": dict(seed.replay_values),
                    "source_files": list(seed.source_files),
                }
            )
            output_iteration += 1

        report_path = os.path.join(
            log_dir,
            "recovery_reports",
            time.strftime("recovery_%Y%m%d_%H%M%S.md"),
        )
        write_recovery_report(report_path, recovery_jobs)
        print(f"Recovery analysis written to: {report_path}")

        for job in recovery_jobs:
            checkpoint_index = int(job["checkpoint_index"])
            x_phys = np.asarray(job["x"], dtype=float)
            output_iteration = int(job["output_iteration"])
            source_iter = job["source_iter"]
            seed = job["seed"]
            resume_path = str(seed.npz_path)
            recovered_phases = set(seed.recovered_phases)
            print(
                "\nRecovering checkpoint "
                f"{checkpoint_index} (source_iter={source_iter}, "
                f"output_iter={output_iteration}, "
                f"phases={sorted(recovered_phases) or ['none']})"
            )

            def _recover_once(
                retry_params: np.ndarray,
                retry_iteration: int,
            ) -> EvaluationResult:
                nonlocal resume_path, recovered_phases
                can_resume = bool(
                    resume_path
                    and os.path.isfile(resume_path)
                    and f2f_label in recovered_phases
                )
                try:
                    orch.execute(
                        retry_params,
                        iteration=retry_iteration,
                        start_phase="resume" if can_resume else "f2f",
                        f2f_npz_path=resume_path if can_resume else "",
                        skip_phases=recovered_phases if can_resume else set(),
                        source_iter=(
                            int(source_iter)
                            if isinstance(source_iter, int)
                            else None
                        ),
                        smoke_only=args.smoke_only,
                    )
                except Exception as exc:
                    if orch.last_phase_npz_path:
                        resume_path = orch.last_phase_npz_path
                    if orch.last_completed_labels:
                        recovered_phases = set(orch.last_completed_labels)
                    error = str(exc)
                    status = (
                        EvaluationStatus.COM_LOST
                        if "COM" in error.upper()
                        else EvaluationStatus.SOLVER_FAILED
                    )
                    return EvaluationResult(status=status, error=error)

                raw = orch.last_raw_values
                penalties = orch.last_penalties
                raw_metrics = {
                    objective.name: (
                        float(raw[index])
                        if raw is not None and np.isfinite(raw[index])
                        else np.nan
                    )
                    for index, objective in enumerate(orch.objectives)
                }
                penalty_values = {
                    objective.name: (
                        float(penalties[index])
                        if penalties is not None
                        else np.nan
                    )
                    for index, objective in enumerate(orch.objectives)
                }
                if not orch.last_evaluation_ok:
                    return EvaluationResult(
                        status=EvaluationStatus.SOLVER_FAILED,
                        error="Workflow 2 recovery evaluation incomplete",
                        raw_metrics=raw_metrics,
                        penalty_values=penalty_values,
                    )
                return EvaluationResult(
                    status=EvaluationStatus.SUCCESS,
                    raw_metrics=raw_metrics,
                    objective_values=penalty_values,
                    penalty_values=penalty_values,
                )

            if retry_handler is not None:
                result, _tier = retry_handler.execute(
                    _recover_once,
                    x_phys,
                    output_iteration,
                )
            else:
                result = _recover_once(x_phys, output_iteration)

            if result.status == EvaluationStatus.SUCCESS:
                raw = orch.last_raw_values
                penalties = orch.last_penalties
                objective_names = [
                    objective.name for objective in orch.objectives
                ]
                assert raw is not None
                assert penalties is not None
                ckpt.mark_completed(
                    checkpoint_index,
                    raw_values=dict(zip(objective_names, raw)),
                    penalties=dict(zip(objective_names, penalties)),
                    solver_ok=orch.last_solvers_ok,
                    phases=list(orch.last_completed_labels),
                )
                _pending_by_x.pop(_x_key(x_phys), None)
                print(
                    "  Recovery completed: "
                    f"attempt={orch.last_attempt}, "
                    f"penalties={penalties.tolist()}"
                )
            else:
                recovery_failures += 1
                phases_done = list(orch.last_completed_labels)
                _mark_recovery_retryable(
                    ckpt,
                    checkpoint_index,
                    error=result.error,
                    phases_done=phases_done,
                )
                print(
                    "  Recovery failed; checkpoint remains retryable on the "
                    f"next process start: {result.error}"
                )
            ckpt.save()

        remaining_recovery = _recovery_candidate_indices(ckpt)
        if recovery_failures or remaining_recovery:
            print(
                "Recovery did not complete every pending evaluation; "
                "new optimisation points will not be generated."
            )
            if retry_handler is not None:
                retry_handler.close_all(force=True)
            orch.close_all_connections(force=True)
            _heartbeat_stop.set()
            sys.exit(1)

    if args.recovery_only:
        if has_ckpt:
            print(
                "Recovery-only complete: "
                f"{ckpt.completed_count} completed, "
                f"{ckpt.pending_count} pending."
            )
        else:
            print("Recovery-only complete: no checkpoint was found.")
        if retry_handler is not None:
            retry_handler.close_all(force=False)
        orch.close_all_connections()
        _heartbeat_stop.set()
        return

    # ── 4.5 Resume partial evaluations (F2F done, F2W pending) ──────────────
    if False and has_ckpt and args.auto_resume:
        partial = ckpt.partial_records
        curves_dir = os.path.join(log_dir, "raw_curves")
        for rec in partial:
            print(f"\nResuming partial eval: phases_done={rec.phases_done}")
            # Find the most complete atomized .npz for this evaluation.
            npz_path = ""
            index_path = os.path.join(curves_dir, "index.jsonl")
            if os.path.isfile(index_path):
                from cst_optimization.database import load_index
                candidates: list[tuple[int, str, str]] = []
                for entry in load_index(index_path):
                    if entry.get("iter") != ckpt.records.index(rec):
                        continue
                    npz_name = entry.get("npz_file", "")
                    candidate_path = os.path.join(curves_dir, npz_name)
                    if not npz_name or not os.path.isfile(candidate_path):
                        continue
                    phases = entry.get("phases_done", [])
                    score = len(phases)
                    if not phases:
                        score = sum(
                            bool(entry.get(flag))
                            for flag in ("has_f2f", "has_f2w", "has_f2wo")
                        )
                    candidates.append(
                        (score, entry.get("timestamp", ""), candidate_path)
                    )
                if candidates:
                    npz_path = max(candidates)[2]
            if not npz_path:
                print("  WARNING: No saved phase .npz found — skipping recovery")
                continue
            x_arr = np.array(rec.x, dtype=float)
            # Pass phases_done so already-completed projects are skipped
            skip = set(rec.phases_done) if hasattr(rec, 'phases_done') and rec.phases_done else set()
            try:
                penalties = orch.execute(
                    x_arr,
                    iteration=ckpt.records.index(rec),
                    start_phase="resume",
                    f2f_npz_path=npz_path,
                    skip_phases=skip,
                )
                # Save the updated skip_phases (from orchestrator's completed_labels)
                # so that if this recovery also fails, the next retry knows what's done
                orch_skip = orch.last_completed_labels
                if orch_skip and orch_skip != skip:
                    ckpt.mark_phase_done(
                        ckpt.records.index(rec),
                        phases=list(orch_skip),
                    )
                    ckpt.save()
                print(f"  Recovery eval done: penalties={penalties}")
                # Update checkpoint
                idx = ckpt.records.index(rec)
                raw = orch.last_raw_values
                pen = orch.last_penalties
                obj_names = [obj.name for obj in orch.objectives]
                if (
                    orch.last_solver_ok
                    and pen is not None
                    and np.all(np.isfinite(pen))
                ):
                    ckpt.mark_completed(
                        idx,
                        raw_values=dict(zip(obj_names, raw)),
                        penalties=dict(zip(obj_names, pen)),
                        solver_ok=orch.last_solver_ok,
                    )
                else:
                    phases_done = list(orch.last_completed_labels) if orch.last_completed_labels else ["f2f", "f2w"]
                    ckpt.mark_phase_done(idx, phases=phases_done)
                ckpt.save()
            except Exception as e:
                print(f"  Recovery eval FAILED: {e}")

    # Refresh checkpoint priors after phase replay and merge them with any
    # sanitized curve-database warm start without duplicating parameter rows.
    checkpoint_X, checkpoint_y = ckpt.get_warm_xy(
        objective_names,
        objective_weights,
    )
    if len(checkpoint_X) > 0:
        if prior_data is None:
            prior_data = (checkpoint_X, checkpoint_y)
        else:
            merged_X = [*np.asarray(prior_data[0], dtype=float)]
            merged_y = [*np.asarray(prior_data[1], dtype=float)]
            seen = {
                np.asarray(row, dtype=np.float64).tobytes()
                for row in merged_X
            }
            for row, value in zip(checkpoint_X, checkpoint_y):
                key = np.asarray(row, dtype=np.float64).tobytes()
                if key not in seen:
                    seen.add(key)
                    merged_X.append(row)
                    merged_y.append(value)
            prior_data = (
                np.asarray(merged_X, dtype=float),
                np.asarray(merged_y, dtype=float),
            )

    # ── 5. Run optimisation ─────────────────────────────────────────────────
    try:
        result = opt.optimize(evaluator=evaluator, prior_data=prior_data)

        print("=" * 60)
        print("Optimisation complete.")
        print(f"Total evaluations: {result.n_evaluations}")
        print(f"Best params (physical):  {result.x_opt}")
        print(f"Best obj value (penalty): {result.f_opt}")

        ckpt.clear()
        print("Checkpoint cleared.")

    except KeyboardInterrupt:
        print("\nInterrupted by user (Ctrl+C) — shutting down...")
        print(f"Checkpoint preserved at {ckpt._path} ({ckpt.completed_count} completed)")
        if retry_handler is not None:
            retry_handler.close_all(force=True)
        orch.close_all_connections(force=True)
        print("CST connections force-closed.")
        _heartbeat_stop.set()
        sys.exit(130)

    except Exception:
        print("Fatal error during optimisation:", file=sys.stderr)
        import traceback
        traceback.print_exc()
        print(f"Checkpoint preserved at {ckpt._path} ({ckpt.completed_count} completed)")
        if retry_handler is not None:
            retry_handler.close_all(force=True)
        orch.close_all_connections(force=True)
        print("CST connections force-closed.")
        _heartbeat_stop.set()
        sys.exit(1)

    else:
        if retry_handler is not None:
            retry_handler.close_all(force=False)
        orch.close_all_connections()
        print("All CST connections closed.")
        _heartbeat_stop.set()


# -- BaseRunner integration (Phase 13) ----------------------------------


class WF2Runner(BaseRunner):
    """WF2 HOM antenna runner — delegates to standalone functions."""

    def __init__(self):
        super().__init__(
            wf_name="workflow_2",
            default_config=str(Path(__file__).resolve().with_name("config.yaml")),
        )

    def run(self):
        main()


if __name__ == "__main__":
    WF2Runner().run()
