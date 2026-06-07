"""Workflow 2 runner — HOM antenna multi-project optimisation.

Usage from project root::

    python run_workflow_2.py
    python run_workflow_2.py --auto-resume
    python run_workflow_2.py --auto-resume --heartbeat
    python run_workflow_2.py --warmup-from-db D:/Results/raw_curves/index.jsonl

The root entry point ``run_workflow_2.py`` is a compatibility shim that
delegates here.  Use ``python run_workflow_2.py`` to run.

Reads ``config/default.yaml``, opens a single CST DesignEnvironment connection
with sequential frequency-domain and wakefield solver execution (inter-pass
reset may recreate the DE between phases), builds the orchestrator + optimiser,
and runs the full Bayesian optimisation loop.
"""

from __future__ import annotations

import argparse
import hashlib
import os
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
from workflows.rfgun_hom_antenna.workflow import build_workflow_2

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
    args = parser.parse_args()

    # ── 1. Load config ──────────────────────────────────────────────────────
    with open("config/default.yaml", "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    wf2_cfg = cfg.get("workflow_2", {})
    if not wf2_cfg.get("enabled", False):
        print("workflow_2.enabled is False — set to true in config/default.yaml")
        sys.exit(0)

    # Merge top-level cst, solver, logging sections into workflow_2 config.
    for section in ("cst", "solver", "logging"):
        if section in cfg and section not in wf2_cfg:
            wf2_cfg[section] = cfg[section]

    # ── 2. Checkpoint (resume from previous crash) ──────────────────────────
    log_dir = (
        wf2_cfg.get("logging", cfg.get("logging", {}))
        .get("output_dir", "D:/Results")
    )
    os.makedirs(log_dir, exist_ok=True)
    ckpt = CheckpointManager(f"{log_dir}/workflow_2")
    has_ckpt = ckpt.load()

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
        # Check if previous run crashed (heartbeat within last 10 min)
        if os.path.isfile(_hb_path):
            try:
                mtime = os.path.getmtime(_hb_path)
                if time.time() - mtime < 600:
                    print("[heartbeat] Previous run may have crashed — enabling auto-resume")
                    args.auto_resume = True
            except Exception:
                pass
        print(f"[heartbeat] writing to {_hb_path} every 60 s")

    # ── Crash recovery: resume partial evaluations ─────────────────────────
    prior_data: tuple[np.ndarray, np.ndarray] | None = None
    if has_ckpt and ckpt.completed_count > 0:
        prior_X, prior_y = ckpt.get_warm_xy()
        if len(prior_X) > 0:
            prior_data = (prior_X, prior_y)
            print(f"Resuming from checkpoint: {ckpt.completed_count} completed, "
                  f"{ckpt.pending_count} pending")
    if has_ckpt:
        partial = ckpt.partial_records
        if partial:
            print(f"Found {len(partial)} partially-evaluated records (F2F done, wakefield pending)")
            print("Resuming partial evaluations (skip completed phases)...")

    # ── 2b. Warmup from 1D curves database (overrides checkpoint prior_data) ─
    if args.warmup_from_db:
        from cst_optimization.database import curves_to_warmup
        from cst_optimization.factory import _build_objectives

        index_path = args.warmup_from_db
        print(f"Loading 1D curve database from: {index_path}")
        db_objectives, _, _ = _build_objectives(
            wf2_cfg.get("objectives", [])
        )

        opt_cfg = wf2_cfg.get("optimization", {})
        obj_weights = opt_cfg.get("objective_weights", None)
        n_obj = len(db_objectives)
        if obj_weights and len(obj_weights) == n_obj:
            w = np.array(obj_weights, dtype=float) / np.sum(obj_weights)
        else:
            w = np.ones(n_obj) / n_obj

        X_db, y_db = curves_to_warmup(index_path, db_objectives, weights=w)
        n_valid = len(X_db)
        print(f"  {n_valid} valid evaluations for warmup")
        if n_valid > 0:
            prior_data = (X_db, y_db)
            best_idx = int(np.argmin(y_db))
            print(f"  Best penalty: {float(y_db[best_idx]):.6f} (index {best_idx})")

    # ── 3. Checkpoint callback ─────────────────────────────────────────────
    def _on_evaluation(
        x_phys: np.ndarray,
        raw_values: np.ndarray,
        penalties: np.ndarray,
        solver_ok: bool,
        error: str,
    ) -> None:
        idx = ckpt.add_pending(x_phys)
        all_finite = bool(np.all(np.isfinite(raw_values)))
        obj_names = [obj.name for obj in orch.objectives]
        if all_finite:
            ckpt.mark_completed(
                idx,
                raw_values=dict(zip(obj_names, raw_values)),
                penalties=dict(zip(obj_names, penalties)),
                solver_ok=solver_ok,
                phases=list(orch.last_completed_labels) if orch.last_completed_labels else [],
            )
        else:
            # Record actually-completed phases from orchestrator state
            phases_done = list(orch.last_completed_labels) if orch.last_completed_labels else []
            if phases_done:
                ckpt.mark_phase_done(idx, phases=phases_done)
            else:
                ckpt.mark_failed(idx, error=error)
        ckpt.save()

    # ── 4. Build orchestrator + optimiser ───────────────────────────────────
    orch, opt, evaluator, retry_handler = build_workflow_2(
        wf2_cfg, checkpoint_callback=_on_evaluation,
    )

    print(f"Parameters: {orch.n_parameters}")
    print(f"Objectives: {orch.n_objectives}")
    if orch.parameter_set.constraints is not None:
        print(f"Constraints: {orch.parameter_set.constraints.n_constraints}")
    print(f"Algorithm: {type(opt).__name__}")
    print(f"Initial samples: {opt._n_initial},  Iterations: {opt._n_iterations}")
    print("-" * 60)

    # ── 4.5 Resume partial evaluations (F2F done, F2W pending) ──────────────
    if has_ckpt:
        partial = ckpt.partial_records
        curves_dir = os.path.join(log_dir, "raw_curves")
        for rec in partial:
            print(f"\nResuming partial eval: phases_done={rec.phases_done}")
            # Find the F2F .npz file for this evaluation
            # The index.jsonl tracks which .npz belongs to which iter
            npz_path = ""
            index_path = os.path.join(curves_dir, "index.jsonl")
            if os.path.isfile(index_path):
                from cst_optimization.database import load_index
                for entry in load_index(index_path):
                    if entry.get("has_f2f") and entry.get("iter") == ckpt.records.index(rec):
                        npz_name = entry.get("npz_file", "")
                        if npz_name:
                            # Try phase-specific .npz first
                            phase_npz = npz_name.replace(".npz", "_f2f.npz")
                            phase_path = os.path.join(curves_dir, phase_npz)
                            if os.path.isfile(phase_path):
                                npz_path = phase_path
                            else:
                                npz_path = os.path.join(curves_dir, npz_name)
                        break
            if not npz_path:
                print(f"  WARNING: No F2F .npz found — skipping recovery for this record")
                continue
            x_arr = np.array(rec.x, dtype=float)
            # Pass phases_done so already-completed projects are skipped
            skip = set(rec.phases_done) if hasattr(rec, 'phases_done') and rec.phases_done else set()
            try:
                penalties = orch.execute(
                    x_arr,
                    iteration=ckpt.records.index(rec),
                    start_phase="f2w",
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
                if raw is not None and np.all(np.isfinite(raw)):
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


if __name__ == "__main__":
    main()
