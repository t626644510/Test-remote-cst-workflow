"""Dual-project multi-solver workflow orchestrator.

Manages independent CST project files (e.g. one for wakefield solver,
one for frequency-domain), synchronises geometry parameters across both,
runs solvers sequentially, and aggregates objective values into a single
penalty vector for the optimiser.

CST 2026 refactor: guaranteed ``try/finally`` cleanup, structured
``SolverResult``-based error recovery, no shared ``_reader_factory``
mutation.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

import numpy as np

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.project import CSTProject
from cst_optimization.core.results import ResultReader
from cst_optimization.core.solver import SolverResult, SolverRunner
from cst_optimization.diagnostics import CSTConnectionLostError, MessageLogger, OptimizationLogger
from cst_optimization.parameters.base import ParameterSet
from cst_optimization.objectives.base import ObjectiveFunction

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Project specification
# ---------------------------------------------------------------------------


@dataclass
class ProjectSpec:
    """Descriptor for one CST project within a multi-solver workflow.

    Attributes
    ----------
    condition_trigger : str
        If set, this project only runs when the objective named *condition_trigger*
        has a penalty below *condition_max_penalty* in the preceding project.
    condition_max_penalty : float
        Penalty threshold for triggering this conditional project.
    """

    cst_path: str
    label: str
    is_pre_filter: bool = False
    condition_trigger: str = ""
    condition_max_penalty: float = 0.2


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class DualProjectOrchestrator:
    """Execute a multi-project CST workflow and return objective penalties.

    Uses a **single** ``CSTConnection`` — projects run sequentially within
    one DesignEnvironment window.  Retry escalation is handled externally
    by ``EvaluationRetryHandler``.
    """

    def __init__(
        self,
        specs: list[ProjectSpec],
        connection: CSTConnection,
        parameter_set: ParameterSet,
        objectives: list[ObjectiveFunction],
        obj_project_map: list[str],
        solver_runner: SolverRunner,
        message_logger: MessageLogger,
        pre_filter_enabled: bool = True,
        pre_filter_threshold_db: float = -25.0,
        pre_eval_cleanup: bool = False,
        library_path: str = "",
        opt_logger: OptimizationLogger | None = None,
        ref_project_map: list[str] | None = None,
        checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None] | None = None,
        curves_db_dir: str = "",
        cooldown_s: float = 5.0,
        adaptive_gate: Any | None = None,
    ) -> None:
        if len(specs) < 1:
            raise ValueError("At least one ProjectSpec is required")
        if len(objectives) != len(obj_project_map):
            raise ValueError(
                f"Length mismatch: {len(objectives)} objectives vs "
                f"{len(obj_project_map)} project-map entries"
            )

        self._conn = connection
        self._library_path = library_path
        self._cooldown_s = float(cooldown_s)
        self._params = parameter_set
        self._objectives = list(objectives)
        self._obj_project_map = list(obj_project_map)
        self._ref_project_map = list(ref_project_map) if ref_project_map else []
        self._solver = solver_runner
        self._msg = message_logger
        self._pre_filter_enabled = pre_filter_enabled
        self._pre_filter_threshold_db = float(pre_filter_threshold_db)
        self._pre_eval_cleanup = pre_eval_cleanup
        self._opt_logger = opt_logger
        self._checkpoint_callback = checkpoint_callback
        self._curves_db_dir = curves_db_dir
        self._adaptive_gate = adaptive_gate
        self._gate_predictions: dict[str, float] | None = None

        self._specs = sorted(
            specs,
            key=lambda s: (
                0 if s.is_pre_filter else (1 if not s.condition_trigger else 2)
            ),
        )

        self._spec_by_label: dict[str, ProjectSpec] = {
            s.label: s for s in self._specs
        }

        # Per-project string interning for reader paths
        self._project_paths: dict[str, str] = {}
        self.last_raw_values: np.ndarray | None = None
        self.last_penalties: np.ndarray | None = None
        self.last_solver_ok: bool = False
        self.last_completed_labels: set[str] = set()  # for per-phase retry

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(
        self, params: np.ndarray, iteration: int = 0,
        start_phase: str = "f2f",
        f2f_npz_path: str = "",
        skip_phases: set[str] | None = None,
    ) -> np.ndarray:
        """Run the full multi-project workflow and return objective penalties.

        Guaranteed cleanup: all opened projects are saved and closed in a
        ``finally`` block regardless of which phase raises.

        Parameters
        ----------
        start_phase : str
            ``"f2f"`` (default) — normal full workflow.
            ``"f2w"`` — skip Phase 1; replay F2F S-params from *f2f_npz_path*
            via ``VirtualResultReader`` (zero COM), then jump to inter-pass
            reset → F2W → F2WO.
        f2f_npz_path : str
            Path to ``eval_NNNN_f2f.npz`` used when *start_phase* is ``"f2w"``.
        """
        # ── Terminal log (define BEFORE first use) ─────────────────
        log_base = os.path.dirname(self._curves_db_dir) if self._curves_db_dir else "D:/Results"
        if not log_base or log_base == ".":
            log_base = "D:/Results"
        _term_log_path = os.path.join(log_base, "workflow_2_terminal.log")
        def _term_print(msg: str) -> None:
            print(msg, flush=True)
            try:
                with open(_term_log_path, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception:
                pass

        param_dict = self._params.to_dict(params)
        vals = ", ".join(f"{k}={v:.4f}" for k, v in param_dict.items())
        _term_print(f"[iter {iteration}] {vals}")
        n_obj = len(self._objectives)
        raw_values = np.full(n_obj, np.nan)
        self._gate_predictions = None  # reset per evaluation
        t_start = time.perf_counter()

        opened: dict[str, CSTProject] = {}
        completed_labels: set[str] = set()  # projects that finished successfully
        solver_errors: list[str] = []
        all_solvers_ok: bool = True
        if skip_phases:
            skipped_labels = set(skip_phases)
            # Also seed completed_labels so Phase 1 and Phase 1.5 gate checks
            # recognise already-done projects from a prior retry attempt
            for spec in self._specs:
                if spec.label in skip_phases:
                    completed_labels.add(spec.label)
        else:
            skipped_labels = set()
        reader_factories: dict[int, Callable[[], ResultReader]] = {}

        # ── Recording session (1D curve capture) ─────────────────────
        _recording = bool(self._curves_db_dir)
        if _recording:
            from cst_optimization.database import start_recording_session, make_recording_reader
            start_recording_session()
            _mk_reader = make_recording_reader
        else:
            _mk_reader = _make_reader_factory

        # ── start_phase="f2w": load F2F from .npz, skip Phase 1 ─────
        if start_phase == "f2w":
            if not f2f_npz_path or not os.path.isfile(f2f_npz_path):
                _term_print("[start_phase=f2w] ERROR: f2f_npz_path missing or not found")
                self.last_completed_labels = completed_labels.copy()
                return np.full(n_obj, 1.0)
            from cst_optimization.database import VirtualResultReader
            _term_print(f"[start_phase=f2w] Replaying F2F S-params from {os.path.basename(f2f_npz_path)}")
            _vreader = VirtualResultReader(f2f_npz_path)
            # Locate the pre_filter (F2F) project label
            _f2f_label = ""
            for _s in self._specs:
                if _s.is_pre_filter:
                    _f2f_label = _s.label
                    break
            if not self._check_pre_filter(_f2f_label, iteration, lambda: _vreader):
                _term_print("[start_phase=f2w] Pre-filter REJECTED — marking complete")
                self.last_raw_values = np.full(n_obj, np.nan)
                self.last_penalties = np.zeros(n_obj)
                self.last_solver_ok = True
                self.last_completed_labels = completed_labels.copy()
                return np.zeros(n_obj)
            _term_print("[start_phase=f2w] Pre-filter PASSED — entering Phase 1.5")
            # Register virtual F2F so Phase 1.5 gate check finds the reader
            completed_labels.add(_f2f_label)
            self._project_paths[_f2f_label] = "__virtual__"
            _orig_mk = _mk_reader
            _mk_reader = lambda pp: (lambda: _vreader) if pp == "__virtual__" else _orig_mk(pp)
            # Inter-pass reset → fresh DE for wakefield
            _term_print("[Inter-pass] Resetting DE before conditional projects (F2F replayed)")
            self._reset_connection()
            _term_print(f"[Inter-pass] New DE PID={self._conn.pid}")

        try:
            # ── Phase 1: Run non-conditional solvers with pre-filter gate ──
            if start_phase == "f2f":
                f2f_ok = self._execute_phase_1(
                    params, param_dict, iteration, opened, completed_labels,
                    solver_errors, all_solvers_ok, _mk_reader, _term_print,
                    n_obj, raw_values,
                )
                if not f2f_ok:
                    # Phase 1 failed or pre-filter rejected
                    if not any(e for e in solver_errors):
                        # pre-filter rejection — continue to Phase 1.5 / 2 / 3
                        # so that F2F-based objectives get real penalties with
                        # gradient; F2W/F2WO will be skipped by conditional gate
                        pass
                    else:
                        # solver failure — fall through to Phase 2/3 with
                        # penalty = 1.0 for all objectives
                        all_solvers_ok = False
                else:
                    # ── Atomize: save F2F .npz + extra cooldown before inter-pass ──
                    if _recording:
                        _term_print("  [atomize] saving F2F .npz")
                        self._save_phase_npz(iteration, "f2f", ["f2f"])
                    # Extra cooldown to let CST flush I/O before DE destroy
                    _term_print(f"  [cooldown] {self._cooldown_s:.0f}s before inter-pass reset")
                    time.sleep(self._cooldown_s)

            # ── Inter-pass reset: fresh DE for wakefield solvers ─────
            if any(s.condition_trigger for s in self._specs):
                _term_print("[Inter-pass] Resetting DE before conditional projects")
                self._reset_connection()
                _term_print(f"[Inter-pass] New DE PID={self._conn.pid}")
                # Drop dead DE1 project handles so finally block won't
                # try to close them (DE1 is already killed).
                opened.clear()

            # ── Phase 1.5: Conditional projects ─────────────────────────
            cond_specs = [s for s in self._specs if s.condition_trigger]
            if cond_specs:
                _term_print(f"[Phase 1.5] Conditional projects ({len(cond_specs)})")
            _first_conditional = True  # first cond already has fresh DE from inter-pass
            for spec in self._specs:
                if not spec.condition_trigger:
                    continue
                # Find the trigger objective and its project
                trigger_idx = None
                for idx, obj in enumerate(self._objectives):
                    if obj.name == spec.condition_trigger:
                        trigger_idx = idx
                        break
                if trigger_idx is None:
                    _logger.warning(
                        "Conditional project '%s': trigger '%s' not found in objectives",
                        spec.label, spec.condition_trigger,
                    )
                    skipped_labels.add(spec.label)
                    continue

                trigger_proj_label = self._obj_project_map[trigger_idx]
                # Gate: source project must have completed successfully.
                if trigger_proj_label not in completed_labels:
                    _term_print(f"  [{spec.label}] SKIP — source project '{trigger_proj_label}' "
                          f"not opened this eval (stale data guard)")
                    skipped_labels.add(spec.label)
                    continue
                trigger_penalty = 1.0
                trigger_raw_str = "N/A"
                # Evaluate trigger objective on-the-fly using the source project's reader
                trigger_project_path = self._project_paths.get(trigger_proj_label, "")
                if trigger_project_path:
                    trigger_rf = _mk_reader(trigger_project_path)
                    try:
                        trigger_raw = self._evaluate_objective(
                            self._objectives[trigger_idx], trigger_rf,
                        )
                        if np.isfinite(trigger_raw):
                            trigger_raw_str = f"{float(trigger_raw):.2f}"
                            trigger_penalty = self._objectives[trigger_idx].mode.compute(
                                float(trigger_raw)
                            )
                        raw_values[trigger_idx] = trigger_raw
                    except Exception:
                        trigger_penalty = 1.0

                # ── Gate decision (primary decision point) ──────────────
                should_run = True
                gate_reason = ""
                if self._adaptive_gate is not None:
                    if self._adaptive_gate.is_warmup:
                        should_run = True
                        gate_reason = " [WARMUP — force run]"
                    elif self._adaptive_gate.should_validate_next():
                        should_run = True
                        gate_reason = " [validate — force run]"
                    else:
                        gp_preds = self._adaptive_gate.predict(params)
                        if self._adaptive_gate.should_run_conditional(
                            trigger_penalty, gp_preds,
                        ):
                            should_run = True
                            gate_reason = " [GP-gate: predicted good]"
                        else:
                            should_run = False
                            gate_reason = " [GP-gate: predicted bad → skip]"
                            self._gate_predictions = gp_preds
                else:
                    # No adaptive gate — fall back to hard penalty threshold
                    should_run = trigger_penalty < spec.condition_max_penalty
                    if not should_run:
                        gate_reason = (
                            f" [penalty={trigger_penalty:.3f}>="
                            f"{spec.condition_max_penalty}]"
                        )

                if not should_run:
                    _term_print(f"  [{spec.label}] SKIP — {spec.condition_trigger} "
                          f"raw={trigger_raw_str} penalty={trigger_penalty:.3f}"
                          f"{gate_reason}")
                    skipped_labels.add(spec.label)
                    continue

                # Run conditional project
                _term_print(f"  [{spec.label}] TRIGGER — {spec.condition_trigger} "
                      f"raw={trigger_raw_str} penalty={trigger_penalty:.3f}"
                      f"{gate_reason}")

                # Per-phase DE reset: fresh DE for each conditional project
                # (the first conditional already got a clean DE from inter-pass reset)
                if _first_conditional:
                    _first_conditional = False
                else:
                    _term_print(f"  [per-phase reset] new DE before {spec.label}")
                    self._reset_connection()
                    _term_print(f"  [per-phase reset] DE PID={self._conn.pid}")

                try:
                    proj = self._conn.open_project(spec.cst_path)
                    opened[spec.label] = proj
                    self._project_paths[spec.label] = proj.filename
                except Exception as exc:
                    _logger.error("Failed to open conditional '%s': %s", spec.label, exc)
                    skipped_labels.add(spec.label)
                    continue
                try:
                    proj.update_parameters(param_dict, use_full_rebuild=True)
                except Exception:
                    pass
                self._msg.capture(proj)
                self._msg.clear()
                result = self._run_solver_with_mesh_retry(proj)
                self._msg.capture(proj)
                if not result.success:
                    _term_print(f"  [{spec.label}] FAIL [{result.error_type}] "
                          f"({result.elapsed_s:.0f}s)")
                    all_solvers_ok = False
                else:
                    _term_print(f"  [{spec.label}] OK ({result.elapsed_s:.0f}s, "
                          f"{result.mesh_cells or '?'} cells)")
                if result.success:
                    try:
                        proj.save()
                    except Exception:
                        pass
                    completed_labels.add(spec.label)
                    # ── Atomize: save incremental .npz after each conditional phase ──
                    if _recording:
                        phases = ["f2f"] if start_phase == "f2w" else []
                        for s2 in self._specs:
                            if not s2.condition_trigger and s2.label in completed_labels:
                                phases.append(s2.label)
                            elif s2.condition_trigger and s2.label in completed_labels:
                                phases.append(s2.label)
                        _term_print(f"  [atomize] saving {spec.label} .npz")
                        self._save_phase_npz(iteration, spec.label, phases)
                self._msg.write(label=spec.label, iteration=iteration)

            # ── Phase 2: Evaluate all objectives ──────────────────────
            _term_print(f"[Phase 2] Evaluating {n_obj} objectives")
            for idx, (obj, proj_label) in enumerate(
                zip(self._objectives, self._obj_project_map)
            ):
                if proj_label not in opened and proj_label not in completed_labels:
                    _logger.warning(
                        "Objective '%s' references project '%s' — no results available",
                        obj.name, proj_label,
                    )
                    continue

                project_path = self._project_paths.get(proj_label, "")
                if not project_path:
                    continue

                # Ensure .cst is unpacked (CST may archive it after long solves)
                self._ensure_unpacked(project_path)

                # Build per-objective reader factory (no shared state mutation)
                rf = reader_factories.setdefault(
                    idx, _mk_reader(project_path)
                )

                # Handle ref_project_map for dual-file transverse impedance
                if idx < len(self._ref_project_map) and self._ref_project_map[idx]:
                    ref_label = self._ref_project_map[idx]
                    ref_path = self._project_paths.get(ref_label, "")
                    if ref_path:
                        self._ensure_unpacked(ref_path)
                        ref_rf = _mk_reader(ref_path)
                        saved_ref = getattr(obj, "_ref_reader_factory", None)
                        obj._ref_reader_factory = ref_rf

                try:
                    raw_values[idx] = self._evaluate_objective(obj, rf)
                except Exception as exc:
                    _logger.error(
                        "Failed to evaluate objective '%s' (project '%s'): %s",
                        obj.name, proj_label, exc,
                    )

            # ── Phase 3: Apply penalty modes → objective vector ───────
            penalties = np.empty(n_obj)
            for idx, obj in enumerate(self._objectives):
                proj_label = self._obj_project_map[idx]
                if np.isfinite(raw_values[idx]):
                    try:
                        penalties[idx] = obj.mode.compute(float(raw_values[idx]))
                    except Exception:
                        penalties[idx] = 1.0
                elif proj_label in skipped_labels:
                    # Conditional project was skipped — use GP prediction if available
                    if self._gate_predictions is not None and obj.name in self._gate_predictions:
                        penalties[idx] = float(self._gate_predictions[obj.name])
                    else:
                        penalties[idx] = 0.0
                elif all_solvers_ok:
                    # Solvers ran OK but evaluation failed (e.g. code error) — neutral
                    penalties[idx] = 0.0
                else:
                    penalties[idx] = 1.0

            # ── Gate recording ────────────────────────────────────────
            if self._adaptive_gate is not None:
                penalty_dict_for_gate = {
                    obj.name: float(penalties[idx])
                    for idx, obj in enumerate(self._objectives)
                }
                f2w_ran = "wakefield" in completed_labels
                self._adaptive_gate.record_evaluation(
                    params, penalty_dict_for_gate, f2w_ran,
                )
                # Validation check: if gate requested validation, record it
                if self._adaptive_gate.should_validate() and f2w_ran:
                    predicted = self._gate_predictions or {}
                    self._adaptive_gate.record_validation(
                        predicted, penalty_dict_for_gate,
                    )

            # ── Phase 3.5: Log ────────────────────────────────────────
            if self._opt_logger is not None:
                elapsed_total = time.perf_counter() - t_start
                physics = {
                    obj.name: float(raw_values[idx]) if np.isfinite(raw_values[idx]) else "NaN"
                    for idx, obj in enumerate(self._objectives)
                }
                penalty_dict = {
                    obj.name: float(penalties[idx])
                    for idx, obj in enumerate(self._objectives)
                }
                # Print objective summary
                obj_parts = []
                for idx, obj in enumerate(self._objectives):
                    if np.isfinite(raw_values[idx]):
                        obj_parts.append(f"{obj.name}={raw_values[idx]:.4g}")
                    else:
                        obj_parts.append(f"{obj.name}=N/A")
                _term_print(f"  objectives: {'  '.join(obj_parts)}")

                error_str = "; ".join(solver_errors) if solver_errors else ""
                self._opt_logger.log_evaluation(
                    iteration=iteration,
                    x=params,
                    param_names=self._params.names,
                    physics=physics,
                    objective_values=penalty_dict,
                    solver_ok=all_solvers_ok,
                    error=error_str,
                    elapsed_s=round(elapsed_total, 1),
                )
                _term_print(f"  [log] written to {self._opt_logger.filepath} "
                      f"({self._opt_logger.n_evaluations} evals)")

            if _recording:
                from cst_optimization.database import collect_curves, save_curves_npz, save_index_record

                curves = collect_curves()
                if curves:
                    npz_name = f"eval_{iteration:04d}.npz"
                    npz_path = os.path.join(self._curves_db_dir, npz_name)
                    save_curves_npz(npz_path, curves)
                    index_path = os.path.join(self._curves_db_dir, "index.jsonl")
                    # Determine which phases produced data
                    _has = {"has_f2f": False, "has_f2w": False, "has_f2wo": False}
                    for _s in self._specs:
                        if _s.label in completed_labels:
                            if "frequency_domain" in _s.label or _s.is_pre_filter:
                                _has["has_f2f"] = True
                            elif "wakefield_offset" in _s.label:
                                _has["has_f2wo"] = True
                            elif "wakefield" in _s.label:
                                _has["has_f2w"] = True
                    save_index_record(
                        index_path,
                        {
                            "iter": iteration,
                            "params": dict(zip(self._params.names, [float(v) for v in params])),
                            "npz_file": npz_name,
                            "solver_ok": all_solvers_ok,
                            "error": "; ".join(solver_errors) if solver_errors else "",
                            "has_f2f": _has["has_f2f"],
                            "has_f2w": _has["has_f2w"],
                            "has_f2wo": _has["has_f2wo"],
                        },
                    )

            # NOTE: checkpoint_callback ownership is in the Workflow2
            # evaluator wrapper (workflow.py).  The orchestrator does NOT
            # fire the callback — it only exposes last_* state.
            # See W2-6E: evaluator-only callback ownership.
            self.last_raw_values = raw_values.copy()
            self.last_penalties = penalties.copy()
            self.last_solver_ok = all_solvers_ok
            self.last_completed_labels = completed_labels.copy()
            return penalties

        finally:
            # ── Phase 4: Guaranteed cleanup ──────────────────────────
            import threading as _th
            # Close projects with timeout — raw COM close() can hang
            for spec in self._specs:
                if spec.label not in opened:
                    continue
                proj = opened[spec.label]
                result = {"done": False}

                def _do_close(_p: CSTProject = proj) -> None:
                    try:
                        _p.close(save=True)
                    except Exception:
                        pass
                    result["done"] = True

                t = _th.Thread(target=_do_close, daemon=True)
                t.start()
                t.join(timeout=10.0)
                if t.is_alive():
                    _logger.warning(
                        "Phase 4: project.close() hung for '%s' — "
                        "abandoning COM thread", spec.label,
                    )

            # DE connection intentionally left alive — it persists across
            # evaluate() calls and is only closed by _reset_connection()
            # (inter-pass) or close_all_connections() (final shutdown).

    def _execute_phase_1(
        self,
        params: np.ndarray,
        param_dict: dict[str, float],
        iteration: int,
        opened: dict[str, CSTProject],
        completed_labels: set[str],
        solver_errors: list[str],
        all_solvers_ok: bool,
        _mk_reader: Any,
        _term_print: Any,
        n_obj: int,
        raw_values: np.ndarray,
    ) -> bool:
        """Run Phase 1 (non-conditional solvers). Returns True if F2F succeeded."""
        n_non_cond = len([s for s in self._specs if not s.condition_trigger])
        _term_print(f"[Phase 1] Non-conditional projects ({n_non_cond})")
        f2f_ok = False

        # If F2F was already completed in a previous retry attempt, skip it
        for spec in self._specs:
            if spec.is_pre_filter and spec.label in completed_labels:
                _term_print(f"  [{spec.label}] SKIP — already completed in prior retry attempt")
                self._project_paths[spec.label] = spec.cst_path
                f2f_ok = True
                return True

        for spec in self._specs:
            if spec.condition_trigger:
                continue
            if spec.label in self._spec_by_label:
                pass  # not skipped

            # Pre-solve cleanup: ensure clean result folder before each solve
            from cst_optimization.core.cleanup import remove_result_folder, remove_lock_file
            remove_result_folder(spec.cst_path)
            remove_lock_file(os.path.splitext(spec.cst_path)[0])

            # Open project
            try:
                proj = self._conn.open_project(spec.cst_path)
                opened[spec.label] = proj
                self._project_paths[spec.label] = proj.filename
            except Exception as exc:
                _logger.error(
                    "Failed to open project '%s' (%s): %s",
                    spec.label, spec.cst_path, exc,
                )
                if spec.is_pre_filter:
                    return False
                continue

            # Store parameters + full_history_rebuild
            try:
                ok = proj.update_parameters(param_dict, use_full_rebuild=True)
                if not ok:
                    _logger.warning("Parameter update failed for project '%s'", spec.label)
            except CSTConnectionLostError:
                _logger.error("Connection lost during parameter update for '%s'", spec.label)
                solver_errors.append(f"Connection lost during update for '{spec.label}'")
                if spec.is_pre_filter:
                    return False
                continue

            # Discard rebuild-phase messages
            self._msg.capture(proj)
            self._msg.clear()

            # Run solver
            result = self._solver.run(proj)

            # Detect history-list incompleteness
            self._msg.capture(proj)
            if self._msg.has_history_failure():
                _logger.warning(
                    "History list incomplete for '%s' — extreme parameters; skipping",
                    spec.label,
                )
                result = SolverResult(
                    success=False, error_type="mesh",
                    error_message="VBA history replay did not reach end",
                )

            self._msg.write(label=spec.label, iteration=iteration)

            if not result.success:
                err_msg = (
                    f"Solver '{spec.label}' failed [{result.error_type}]: "
                    f"{result.error_message or 'unknown'}"
                )
                _term_print(f"  [{spec.label}] FAIL [{result.error_type}] "
                      f"({result.elapsed_s:.0f}s)")
                _logger.error(err_msg)
                self._msg.write_now(err_msg, label=spec.label, iteration=iteration)
                solver_errors.append(err_msg)
                if spec.is_pre_filter:
                    return False
            else:
                _term_print(f"  [{spec.label}] OK ({result.elapsed_s:.0f}s, "
                      f"{result.mesh_cells or '?'} cells)")
                _logger.info(
                    "Solver '%s' completed in %.1f s (%s mesh cells)",
                    spec.label, result.elapsed_s, result.mesh_cells or "?",
                )

            # Save project
            if result.success:
                try:
                    proj.save()
                except Exception:
                    _logger.warning("Failed to save project '%s'", spec.label, exc_info=True)
                completed_labels.add(spec.label)
                if spec.is_pre_filter:
                    f2f_ok = True

            # Pre-filter check
            if spec.is_pre_filter and self._pre_filter_enabled:
                rf = _mk_reader(self._project_paths.get(spec.label, ""))
                passed = self._check_pre_filter(spec.label, iteration, rf)
                if not passed:
                    _logger.info(
                        "Pre-filter REJECTED — antenna absorption > %.0f dB",
                        self._pre_filter_threshold_db,
                    )
                    return False  # caller returns all-1.0

        return f2f_ok

    def _save_phase_npz(
        self,
        iteration: int,
        phase_label: str,
        completed_phases: list[str],
    ) -> str:
        """Save incremental .npz for a phase and return the file path."""
        from cst_optimization.database import collect_curves, save_curves_npz, save_index_record

        curves = collect_curves()
        if not curves:
            return ""
        npz_name = f"eval_{iteration:04d}_{phase_label}.npz"
        npz_path = os.path.join(self._curves_db_dir, npz_name)
        os.makedirs(self._curves_db_dir, exist_ok=True)
        save_curves_npz(npz_path, curves)
        index_path = os.path.join(self._curves_db_dir, "index.jsonl")
        save_index_record(
            index_path,
            {
                "iter": iteration,
                "params": dict(zip(self._params.names, self.last_raw_values.tolist() if self.last_raw_values is not None else [])),
                "npz_file": npz_name,
                "phases_done": list(completed_phases),
                "solver_ok": self.last_solver_ok,
            },
        )
        return npz_path

    def _run_solver_with_mesh_retry(self, proj: CSTProject) -> SolverResult:
        """Run solver; on any mesh error, increment rebuildlength (6→25)."""
        result = self._solver.run(proj)

        if result.success:
            return result
        if result.error_type != "mesh":
            return result

        rl = 6
        max_rl = 25
        _logger.info(
            "Mesh error — retrying with rebuildlength %d→%d", rl, max_rl,
        )
        while rl <= max_rl:
            rl += 1
            try:
                proj.model3d.StoreParameter("rebuildlength", rl)
                proj.model3d.full_history_rebuild()
            except Exception:
                break
            result = self._solver.run(proj)
            if result.success:
                _logger.info("Mesh retry succeeded at rebuildlength=%d", rl)
                return result
            if result.error_type != "mesh":
                break

        try:
            proj.model3d.StoreParameter("rebuildlength", 6)
            proj.rebuild()
        except Exception:
            pass
        _logger.warning("Mesh error persisted after rebuildlength %d", rl - 1)
        return SolverResult(
            success=False, error_type="mesh",
            error_message=f"Mesh error persisted after rebuildlength {rl - 1}",
        )

    def _reset_connection(self) -> None:
        """Kill current DE, clean up, create a fresh connection.

        Used between Phase 1 (F2F) and Phase 1.5 (wakefield) to give the
        wakefield solver a pristine DE context, avoiding PBA matrix race
        conditions left over from the frequency-domain run.
        """
        import time as _t
        from cst_optimization.core.cleanup import (
            kill_all_cst_processes, remove_result_folder, remove_lock_file,
            force_kill_cst, verify_process_cleanup,
        )

        pid = self._conn.pid
        try:
            self._conn.close(force=False)
        except Exception:
            pass
        _t.sleep(self._cooldown_s)

        if pid is not None and pid > 0:
            try:
                force_kill_cst(pid)
                verify_process_cleanup(pid, timeout_s=10.0)
            except Exception:
                pass

        kill_all_cst_processes()
        # Only clean conditional-project result folders — keep F2F results
        # so Phase 1.5 can read antenna S-parameters.
        for spec in self._specs:
            if spec.is_pre_filter:
                continue
            try:
                remove_result_folder(spec.cst_path)
            except Exception:
                pass
            try:
                remove_lock_file(os.path.splitext(spec.cst_path)[0])
            except Exception:
                pass

        _t.sleep(self._cooldown_s)

        new_conn = CSTConnection(library_path=self._library_path, mode="new")
        new_conn.connect()
        new_conn.set_quiet_mode(True)
        _logger.info("Inter-pass reset: new CST DE, PID=%s", new_conn.pid)
        self._conn = new_conn

    def _check_pre_filter(
        self, label: str, iteration: int, reader_factory: Callable[[], ResultReader],
    ) -> bool:
        """Evaluate pre-filter objectives; return True if candidate passes."""
        for idx, (obj, proj_label) in enumerate(
            zip(self._objectives, self._obj_project_map)
        ):
            if proj_label != label:
                continue
            try:
                raw = self._evaluate_objective(obj, reader_factory)
            except Exception as exc:
                _logger.warning(
                    "Pre-filter: cannot evaluate '%s': %s", obj.name, exc,
                )
                return False

            if np.isfinite(raw) and raw > self._pre_filter_threshold_db:
                _logger.info(
                    "Pre-filter: '%s' = %.1f dB > %.0f dB → REJECT",
                    obj.name, raw, self._pre_filter_threshold_db,
                )
                return False

        return True

    @staticmethod
    def _evaluate_objective(
        obj: ObjectiveFunction, reader_factory: Callable[[], ResultReader],
    ) -> float:
        """Evaluate a single objective using a local reader factory."""
        saved = getattr(obj, "_reader_factory", None)
        obj._reader_factory = reader_factory
        try:
            return obj.raw_value()
        finally:
            obj._reader_factory = saved  # restore on both success and failure

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __call__(self, params: np.ndarray) -> np.ndarray:
        return self.execute(params)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def _ensure_unpacked(self, cst_path: str) -> None:
        """Open a .cst via COM to trigger CST auto-unpack (archived → unpacked).

        CST periodically archives project files (ZIP format).  Once archived,
        ``cst.results.ProjectFile`` cannot read the result folder because it
        is buried inside the archive.  Opening the project through the COM
        ``DesignEnvironment`` triggers CST to unpack it back to a normal
        folder-based layout.
        """
        try:
            proj = self._conn.open_project(cst_path)
            proj.close()
        except Exception:
            pass

    def close_all_connections(self, force: bool = False) -> None:
        """Close the CST DesignEnvironment connection.

        Parameters
        ----------
        force : bool
            If ``True``, skip graceful COM close and force-kill CST processes.
        """
        if self._conn is not None:
            try:
                self._conn.close(force=force)
            except Exception:
                _logger.warning("Error closing CST connection", exc_info=True)

    @property
    def parameter_set(self) -> ParameterSet:
        return self._params

    @property
    def objectives(self) -> list[ObjectiveFunction]:
        return list(self._objectives)

    @property
    def n_objectives(self) -> int:
        return len(self._objectives)

    @property
    def n_parameters(self) -> int:
        return self._params.n_parameters


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reader_factory(project_path: str) -> Callable[[], ResultReader]:
    """Return a zero-argument callable that creates a ``ResultReader``."""
    return lambda: ResultReader(str(project_path), allow_interactive=True)
