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
from workflows.rfgun_hom_antenna.recovery import (
    WF2_INDEX_SCHEMA_VERSION,
    parameter_hash,
    replay_snapshot,
)

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
        phase_checkpoint_callback: Callable[
            [np.ndarray, int, list[str], str], None
        ] | None = None,
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
        self._phase_checkpoint_callback = phase_checkpoint_callback
        self._curves_db_dir = curves_db_dir
        self._adaptive_gate = adaptive_gate
        self._gate_predictions: dict[str, float] | None = None
        self._gate_prediction_std: dict[str, float] | None = None
        self._gate_validation_forced: bool = False

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
        self.last_solvers_ok: bool = False
        self.last_postprocess_ok: bool = False
        self.last_evaluation_ok: bool = False
        self.last_solver_ok: bool = False
        self.last_completed_labels: set[str] = set()  # for per-phase retry
        self.last_skipped_labels: set[str] = set()
        self.last_phase_npz_path: str = ""
        self.last_attempt: int = 0
        self.last_source_iter: int | None = None

    def bootstrap_adaptive_gate(
        self,
        X: np.ndarray,
        penalty_matrix: np.ndarray,
        measurement_mask: np.ndarray,
        f2w_ran: np.ndarray,
    ) -> bool:
        """Seed the conditional gate from historical Workflow 2 data."""
        if self._adaptive_gate is None:
            return False
        self._adaptive_gate.bootstrap(
            X,
            penalty_matrix,
            measurement_mask,
            f2w_ran,
        )
        return True

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        params: np.ndarray,
        iteration: int = 0,
        start_phase: str = "f2f",
        f2f_npz_path: str = "",
        skip_phases: set[str] | None = None,
        source_iter: int | None = None,
        smoke_only: bool = False,
    ) -> np.ndarray:
        """Run Workflow 2 with replay-verified phase persistence.

        Solver success alone is not a durable phase boundary.  Each phase is
        post-processed and atomized before the next DesignEnvironment reset.
        The cumulative snapshot is then the source of truth for final
        objective evaluation and future crash recovery.
        """
        log_base = (
            os.path.dirname(self._curves_db_dir)
            if self._curves_db_dir
            else "D:/Results"
        )
        if not log_base or log_base == ".":
            log_base = "D:/Results"
        terminal_path = os.path.join(log_base, "workflow_2_terminal.log")

        def term_print(message: str) -> None:
            print(message, flush=True)
            try:
                with open(terminal_path, "a", encoding="utf-8") as stream:
                    stream.write(message + "\n")
            except Exception:
                pass

        param_dict = self._params.to_dict(params)
        term_print(
            f"[iter {iteration}] "
            + ", ".join(f"{key}={value:.4f}" for key, value in param_dict.items())
        )
        n_obj = len(self._objectives)
        raw_values = np.full(n_obj, np.nan, dtype=float)
        penalties = np.ones(n_obj, dtype=float)
        completed_labels: set[str] = set(skip_phases or ())
        solved_labels: set[str] = set(skip_phases or ())
        skipped_labels: set[str] = set()
        solver_errors: list[str] = []
        postprocess_errors: list[str] = []
        all_solvers_ok = True
        pre_filter_rejected = False
        opened: dict[str, CSTProject] = {}
        phase_base_npz = f2f_npz_path if f2f_npz_path else ""
        resume_reader: Any | None = None
        started = time.perf_counter()

        self.last_raw_values = raw_values.copy()
        self.last_penalties = penalties.copy()
        self.last_solvers_ok = False
        self.last_postprocess_ok = False
        self.last_evaluation_ok = False
        self.last_solver_ok = False
        self.last_completed_labels = set()
        self.last_skipped_labels = set()
        self.last_phase_npz_path = phase_base_npz
        self.last_source_iter = (
            source_iter if source_iter is not None else iteration
        )
        self.last_attempt = self._allocate_attempt(iteration)
        self._gate_predictions = None
        self._gate_prediction_std = None
        self._gate_validation_forced = False

        recording = bool(self._curves_db_dir)
        if recording:
            from cst_optimization.database import (
                make_recording_reader,
                start_recording_session,
            )
            start_recording_session()
            make_reader = make_recording_reader
        else:
            make_reader = _make_reader_factory

        f2f_label = next(
            (spec.label for spec in self._specs if spec.is_pre_filter),
            "",
        )
        conditional_specs = [
            spec for spec in self._specs if spec.condition_trigger
        ]

        try:
            if start_phase in {"f2w", "resume"}:
                if not phase_base_npz or not os.path.isfile(phase_base_npz):
                    raise FileNotFoundError(
                        "saved phase snapshot missing for resume"
                    )
                from cst_optimization.database import VirtualResultReader
                resume_reader = VirtualResultReader(phase_base_npz)
                term_print(
                    f"[start_phase={start_phase}] Replaying saved curves from "
                    f"{os.path.basename(phase_base_npz)}"
                )
                completed_labels.add(f2f_label)
                solved_labels.add(f2f_label)
                replayed = replay_snapshot(
                    phase_base_npz,
                    self._objectives,
                    self._obj_project_map,
                    self._ref_project_map,
                    completed_labels,
                )
                finite = np.isfinite(replayed.raw_values)
                raw_values[finite] = replayed.raw_values[finite]
                if not self._check_pre_filter(
                    f2f_label,
                    iteration,
                    lambda: resume_reader,
                ):
                    pre_filter_rejected = True
                    term_print(
                        f"[start_phase={start_phase}] Pre-filter REJECTED - "
                        "preserving F2F penalties"
                    )
                else:
                    term_print(
                        f"[start_phase={start_phase}] Pre-filter PASSED - "
                        "entering remaining phases"
                    )

            if start_phase == "f2f":
                f2f_ok = self._execute_phase_1(
                    params,
                    param_dict,
                    iteration,
                    opened,
                    completed_labels,
                    solver_errors,
                    all_solvers_ok,
                    make_reader,
                    term_print,
                    n_obj,
                    raw_values,
                )
                if f2f_label in completed_labels:
                    solved_labels.add(f2f_label)
                    errors = self._capture_project_objectives(
                        f2f_label,
                        self._project_paths.get(f2f_label, ""),
                        raw_values,
                        make_reader,
                    )
                    postprocess_errors.extend(errors)
                    if errors:
                        completed_labels.discard(f2f_label)
                    if not errors and recording:
                        candidate = self._save_phase_npz(
                            params=params,
                            iteration=iteration,
                            phase_label="f2f",
                            completed_phases=self._checkpoint_phases(
                                completed_labels
                            ),
                            base_npz_path="",
                            source_iter=self.last_source_iter,
                            smoke_only=smoke_only,
                        )
                        if candidate:
                            phase_base_npz = candidate
                            self.last_phase_npz_path = candidate
                            term_print(
                                "  [atomize] verified F2F snapshot "
                                + os.path.basename(candidate)
                            )
                        else:
                            completed_labels.discard(f2f_label)
                            postprocess_errors.append(
                                "frequency_domain: snapshot replay failed"
                            )
                if not f2f_ok:
                    if solver_errors:
                        all_solvers_ok = False
                    elif f2f_label in solved_labels:
                        pre_filter_rejected = True
                    else:
                        all_solvers_ok = False
                        solver_errors.append(
                            f"Solver '{f2f_label}' did not produce a "
                            "completed frequency-domain phase"
                        )
                if f2f_label in completed_labels:
                    term_print(
                        f"  [cooldown] {self._cooldown_s:.0f}s before "
                        "inter-pass reset"
                    )
                    time.sleep(self._cooldown_s)

            if pre_filter_rejected:
                skipped_labels.update(
                    spec.label for spec in conditional_specs
                )

            missing_conditional = any(
                spec.label not in completed_labels
                for spec in conditional_specs
            )
            if (
                not pre_filter_rejected
                and conditional_specs
                and (start_phase == "f2f" or missing_conditional)
            ):
                term_print(
                    "[Inter-pass] Resetting DE before conditional projects"
                )
                self._reset_connection(
                    cleanup_labels={
                        spec.label for spec in conditional_specs
                    }
                )
                term_print(f"[Inter-pass] New DE PID={self._conn.pid}")
                opened.clear()

            if conditional_specs:
                term_print(
                    f"[Phase 1.5] Conditional projects "
                    f"({len(conditional_specs)})"
                )
            first_conditional = True
            for spec in conditional_specs:
                if pre_filter_rejected:
                    term_print(
                        f"  [{spec.label}] SKIP - pre-filter rejected"
                    )
                    continue
                if spec.label in completed_labels:
                    term_print(
                        f"  [{spec.label}] SKIP - already completed in "
                        "saved phase data"
                    )
                    continue

                trigger_idx = next(
                    (
                        idx
                        for idx, obj in enumerate(self._objectives)
                        if obj.name == spec.condition_trigger
                    ),
                    None,
                )
                if trigger_idx is None:
                    skipped_labels.add(spec.label)
                    continue
                trigger_project = self._obj_project_map[trigger_idx]
                if trigger_project not in completed_labels:
                    term_print(
                        f"  [{spec.label}] SKIP - source project "
                        f"'{trigger_project}' has no durable snapshot"
                    )
                    skipped_labels.add(spec.label)
                    continue
                trigger_raw = raw_values[trigger_idx]
                trigger_penalty = 1.0
                trigger_raw_text = "N/A"
                if np.isfinite(trigger_raw):
                    trigger_raw_text = f"{trigger_raw:.2f}"
                    trigger_penalty = float(
                        self._objectives[trigger_idx].mode.compute(
                            float(trigger_raw)
                        )
                    )

                should_run, gate_reason = self._conditional_gate_decision(
                    params,
                    trigger_penalty,
                )
                if not should_run:
                    term_print(
                        f"  [{spec.label}] SKIP - {spec.condition_trigger} "
                        f"raw={trigger_raw_text} penalty={trigger_penalty:.3f}"
                        f"{gate_reason}"
                    )
                    skipped_labels.add(spec.label)
                    continue

                term_print(
                    f"  [{spec.label}] TRIGGER - {spec.condition_trigger} "
                    f"raw={trigger_raw_text} penalty={trigger_penalty:.3f}"
                    f"{gate_reason}"
                )
                if first_conditional:
                    first_conditional = False
                else:
                    term_print(
                        f"  [per-phase reset] new DE before {spec.label}"
                    )
                    self._reset_connection(cleanup_labels={spec.label})
                    term_print(
                        f"  [per-phase reset] DE PID={self._conn.pid}"
                    )
                    opened.clear()

                try:
                    project = self._conn.open_project(spec.cst_path)
                    opened[spec.label] = project
                    self._project_paths[spec.label] = project.filename
                except Exception as exc:
                    all_solvers_ok = False
                    solver_errors.append(
                        f"{spec.label}: project open failed: {exc}"
                    )
                    continue
                try:
                    project.update_parameters(
                        param_dict,
                        use_full_rebuild=True,
                    )
                except Exception:
                    pass
                self._msg.capture(project)
                self._msg.clear()
                result = self._run_solver_with_mesh_retry(project)
                self._msg.capture(project)
                if not result.success:
                    all_solvers_ok = False
                    solver_errors.append(
                        f"Solver '{spec.label}' failed "
                        f"[{result.error_type}]: "
                        f"{result.error_message or 'unknown'}"
                    )
                    term_print(
                        f"  [{spec.label}] FAIL [{result.error_type}] "
                        f"({result.elapsed_s:.0f}s)"
                    )
                    self._msg.write(
                        label=spec.label,
                        iteration=iteration,
                    )
                    continue

                solved_labels.add(spec.label)
                term_print(
                    f"  [{spec.label}] OK ({result.elapsed_s:.0f}s, "
                    f"{result.mesh_cells or '?'} cells)"
                )
                try:
                    project.save()
                except Exception:
                    pass
                errors = self._capture_project_objectives(
                    spec.label,
                    self._project_paths.get(spec.label, ""),
                    raw_values,
                    make_reader,
                    ref_npz_path=phase_base_npz,
                )
                postprocess_errors.extend(errors)
                if not errors:
                    completed_labels.add(spec.label)
                    if recording:
                        candidate = self._save_phase_npz(
                            params=params,
                            iteration=iteration,
                            phase_label=spec.label,
                            completed_phases=self._checkpoint_phases(
                                completed_labels
                            ),
                            base_npz_path=phase_base_npz,
                            source_iter=self.last_source_iter,
                            smoke_only=smoke_only,
                        )
                        if candidate:
                            phase_base_npz = candidate
                            self.last_phase_npz_path = candidate
                            replayed = replay_snapshot(
                                candidate,
                                self._objectives,
                                self._obj_project_map,
                                self._ref_project_map,
                                completed_labels,
                            )
                            finite = np.isfinite(replayed.raw_values)
                            raw_values[finite] = replayed.raw_values[finite]
                            term_print(
                                f"  [atomize] verified {spec.label} "
                                f"snapshot {os.path.basename(candidate)}"
                            )
                        else:
                            completed_labels.discard(spec.label)
                            postprocess_errors.append(
                                f"{spec.label}: snapshot replay failed"
                            )
                self._msg.write(label=spec.label, iteration=iteration)

            term_print(f"[Phase 2] Evaluating {n_obj} objectives")
            replay_errors: list[str] = []
            if phase_base_npz and os.path.isfile(phase_base_npz):
                replayed = replay_snapshot(
                    phase_base_npz,
                    self._objectives,
                    self._obj_project_map,
                    self._ref_project_map,
                    completed_labels,
                )
                finite = np.isfinite(replayed.raw_values)
                raw_values[finite] = replayed.raw_values[finite]
                replay_errors.extend(replayed.errors)

            for idx, obj in enumerate(self._objectives):
                owner = self._obj_project_map[idx]
                if np.isfinite(raw_values[idx]):
                    penalties[idx] = float(
                        obj.mode.compute(float(raw_values[idx]))
                    )
                elif owner in skipped_labels:
                    if pre_filter_rejected:
                        penalties[idx] = 1.0
                    elif (
                        self._gate_predictions is not None
                        and obj.name in self._gate_predictions
                    ):
                        penalties[idx] = float(
                            self._gate_predictions[obj.name]
                        )
                    else:
                        penalties[idx] = 0.0
                else:
                    penalties[idx] = 1.0

            missing = [
                obj.name
                for idx, obj in enumerate(self._objectives)
                if (
                    not np.isfinite(raw_values[idx])
                    and self._obj_project_map[idx] not in skipped_labels
                    and self._obj_project_map[idx] in solved_labels
                )
            ]
            all_postprocess_errors = [
                *postprocess_errors,
                *replay_errors,
            ]
            postprocess_ok = not missing and not all_postprocess_errors
            evaluation_ok = bool(
                all_solvers_ok
                and postprocess_ok
                and np.all(np.isfinite(penalties))
            )

            self.last_raw_values = raw_values.copy()
            self.last_penalties = penalties.copy()
            self.last_solvers_ok = all_solvers_ok
            self.last_postprocess_ok = postprocess_ok
            self.last_evaluation_ok = evaluation_ok
            self.last_solver_ok = all_solvers_ok
            self.last_completed_labels = completed_labels.copy()
            self.last_skipped_labels = skipped_labels.copy()
            self.last_phase_npz_path = phase_base_npz

            if self._adaptive_gate is not None and evaluation_ok:
                gate_penalties = {
                    obj.name: float(penalties[idx])
                    for idx, obj in enumerate(self._objectives)
                }
                measurement_mask = {
                    obj.name: bool(np.isfinite(raw_values[idx]))
                    for idx, obj in enumerate(self._objectives)
                }
                f2w_ran = "wakefield" in completed_labels
                self._adaptive_gate.record_evaluation(
                    params,
                    gate_penalties,
                    f2w_ran,
                    measurement_mask,
                    was_validation=self._gate_validation_forced,
                    predicted=self._gate_predictions,
                )

            objective_text = "  ".join(
                f"{obj.name}="
                + (
                    f"{raw_values[idx]:.4g}"
                    if np.isfinite(raw_values[idx])
                    else "N/A"
                )
                for idx, obj in enumerate(self._objectives)
            )
            term_print(f"  objectives: {objective_text}")
            errors = [*solver_errors, *all_postprocess_errors]
            if self._opt_logger is not None:
                self._opt_logger.log_evaluation(
                    iteration=iteration,
                    x=params,
                    param_names=self._params.names,
                    physics={
                        obj.name: (
                            float(raw_values[idx])
                            if np.isfinite(raw_values[idx])
                            else np.nan
                        )
                        for idx, obj in enumerate(self._objectives)
                    },
                    objective_values={
                        obj.name: float(penalties[idx])
                        for idx, obj in enumerate(self._objectives)
                    },
                    solver_ok=all_solvers_ok,
                    error="; ".join(errors),
                    elapsed_s=round(time.perf_counter() - started, 1),
                )
                term_print(
                    f"  [log] written to {self._opt_logger.filepath} "
                    f"({self._opt_logger.n_evaluations} evals)"
                )

            if recording:
                self._write_evaluation_index(
                    params=params,
                    iteration=iteration,
                    completed_labels=completed_labels,
                    skipped_labels=skipped_labels,
                    npz_path=phase_base_npz,
                    objective_manifest=[
                        obj.name
                        for idx, obj in enumerate(self._objectives)
                        if np.isfinite(raw_values[idx])
                    ],
                    solvers_ok=all_solvers_ok,
                    postprocess_ok=postprocess_ok,
                    evaluation_ok=evaluation_ok,
                    errors=errors,
                    source_iter=self.last_source_iter,
                    smoke_only=smoke_only,
                )

            if missing or all_postprocess_errors:
                detail = "; ".join(all_postprocess_errors) or ", ".join(
                    missing
                )
                raise RuntimeError(
                    "Objective post-processing incomplete for "
                    f"{', '.join(missing)}: {detail}"
                )
            return penalties
        finally:
            self.last_raw_values = raw_values.copy()
            self.last_penalties = penalties.copy()
            self.last_completed_labels = completed_labels.copy()
            self.last_skipped_labels = skipped_labels.copy()
            if resume_reader is not None:
                try:
                    resume_reader.close()
                except Exception:
                    pass
            import threading as _threading
            for spec in self._specs:
                project = opened.get(spec.label)
                if project is None:
                    continue
                thread = _threading.Thread(
                    target=self._safe_close_project,
                    args=(project, spec.label),
                    daemon=True,
                )
                thread.start()
                thread.join(timeout=30.0)
                if thread.is_alive():
                    _logger.warning(
                        "Phase 4: project.close() hung for '%s'",
                        spec.label,
                    )

    def _conditional_gate_decision(
        self,
        params: np.ndarray,
        trigger_penalty: float,
    ) -> tuple[bool, str]:
        """Return the Workflow 2 conditional-gate decision and log suffix."""
        if self._adaptive_gate is None:
            return True, ""
        if self._adaptive_gate.is_warmup:
            return True, " [WARMUP - force run]"
        predictions, uncertainty = (
            self._adaptive_gate.predict_with_uncertainty(params)
        )
        self._gate_predictions = predictions
        self._gate_prediction_std = uncertainty
        if self._adaptive_gate.should_validate_next():
            self._gate_validation_forced = True
            return True, " [validate - force run]"
        if self._adaptive_gate.should_run_conditional(
            trigger_penalty,
            predictions,
            uncertainty,
        ):
            return True, " [GP-gate: predicted good]"
        return False, " [GP-gate: predicted bad -> skip]"

    def _allocate_attempt(self, iteration: int) -> int:
        """Return the next non-overwriting attempt number for *iteration*."""
        if not self._curves_db_dir:
            return 1
        from cst_optimization.database import load_index
        index_path = os.path.join(self._curves_db_dir, "index.jsonl")
        attempts = [
            int(record.get("attempt", 0) or 0)
            for record in load_index(index_path)
            if record.get("iter") == iteration
        ]
        return (max(attempts) if attempts else 0) + 1

    def _capture_project_objectives(
        self,
        project_label: str,
        project_path: str,
        raw_values: np.ndarray,
        make_reader: Callable[[str], Callable[[], ResultReader]],
        ref_npz_path: str = "",
    ) -> list[str]:
        """Read a phase's objectives before its live results can be cleaned."""
        if not project_path:
            return [f"{project_label}: project path unavailable"]
        reader_factory = make_reader(project_path)
        errors: list[str] = []
        for idx, (obj, owner) in enumerate(
            zip(self._objectives, self._obj_project_map)
        ):
            if owner != project_label:
                continue
            saved_ref = getattr(obj, "_ref_reader_factory", None)
            ref_reader: Any | None = None
            try:
                ref_label = (
                    self._ref_project_map[idx]
                    if idx < len(self._ref_project_map)
                    else ""
                )
                if ref_label:
                    if not ref_npz_path or not os.path.isfile(ref_npz_path):
                        raise RuntimeError(
                            f"reference snapshot for '{ref_label}' unavailable"
                        )
                    from cst_optimization.database import VirtualResultReader
                    ref_reader = VirtualResultReader(ref_npz_path)
                    obj._ref_reader_factory = lambda vr=ref_reader: vr
                raw = self._evaluate_objective(obj, reader_factory)
                if not np.isfinite(raw):
                    raise ValueError(f"non-finite raw value {raw}")
                raw_values[idx] = float(raw)
            except Exception as exc:
                errors.append(f"{obj.name}: {exc}")
            finally:
                if hasattr(obj, "_ref_reader_factory"):
                    obj._ref_reader_factory = saved_ref
                if ref_reader is not None:
                    ref_reader.close()
        return errors

    def _write_evaluation_index(
        self,
        *,
        params: np.ndarray,
        iteration: int,
        completed_labels: set[str],
        skipped_labels: set[str],
        npz_path: str,
        objective_manifest: list[str],
        solvers_ok: bool,
        postprocess_ok: bool,
        evaluation_ok: bool,
        errors: list[str],
        source_iter: int | None,
        smoke_only: bool,
    ) -> None:
        """Append one schema-v3 evaluation record."""
        from cst_optimization.database import save_index_record
        phases = self._checkpoint_phases(completed_labels)
        phase_manifest = [
            spec.label
            for spec in self._specs
            if spec.label in completed_labels
        ]
        save_index_record(
            os.path.join(self._curves_db_dir, "index.jsonl"),
            {
                "iter": iteration,
                "attempt": self.last_attempt,
                "source_iter": source_iter,
                "record_type": "evaluation",
                "schema_version": WF2_INDEX_SCHEMA_VERSION,
                "params": dict(
                    zip(self._params.names, [float(value) for value in params])
                ),
                "params_hash": parameter_hash(self._params.names, params),
                "npz_file": os.path.basename(npz_path) if npz_path else "",
                "phase_manifest": phase_manifest,
                "phases_done": phases,
                "objective_manifest": list(objective_manifest),
                "skipped_phases": sorted(skipped_labels),
                "solver_ok": bool(solvers_ok),
                "solvers_ok": bool(solvers_ok),
                "postprocess_ok": bool(postprocess_ok),
                "evaluation_ok": bool(evaluation_ok),
                "error": "; ".join(error for error in errors if error),
                "has_f2f": "f2f" in phases,
                "has_f2w": "wakefield" in phases,
                "has_f2wo": "wakefield_offset" in phases,
                "smoke_only": bool(smoke_only),
            },
        )

    @staticmethod
    def _safe_close_project(project: CSTProject, label: str) -> None:
        """Best-effort project save/close used by the cleanup thread."""
        try:
            project.save()
        except Exception:
            pass
        try:
            project.close()
        except Exception:
            _logger.debug(
                "Failed to close project '%s'",
                label,
                exc_info=True,
            )

    def _execute_legacy(
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
        self.last_raw_values = raw_values.copy()
        self.last_penalties = np.full(n_obj, 1.0)
        self.last_solver_ok = False
        self.last_completed_labels = set()
        self.last_skipped_labels = set()
        self._gate_predictions = None  # reset per evaluation
        t_start = time.perf_counter()

        opened: dict[str, CSTProject] = {}
        completed_labels: set[str] = set()  # projects that finished successfully
        solver_errors: list[str] = []
        all_solvers_ok: bool = True
        if skip_phases:
            skipped_labels: set[str] = set()
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
        phase_base_npz = ""
        resume_reader: Any | None = None

        # ── Resume from atomized phase curves, skipping completed CST work ─
        if start_phase in {"f2w", "resume"}:
            if not f2f_npz_path or not os.path.isfile(f2f_npz_path):
                _term_print(
                    f"[start_phase={start_phase}] ERROR: "
                    "saved phase .npz missing or not found"
                )
                self.last_completed_labels = completed_labels.copy()
                return np.full(n_obj, 1.0)
            from cst_optimization.database import VirtualResultReader
            _term_print(
                f"[start_phase={start_phase}] Replaying saved curves from "
                f"{os.path.basename(f2f_npz_path)}"
            )
            _vreader = VirtualResultReader(f2f_npz_path)
            resume_reader = _vreader
            phase_base_npz = f2f_npz_path
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
                _vreader.close()
                return np.zeros(n_obj)
            _term_print(
                f"[start_phase={start_phase}] Pre-filter PASSED — "
                "entering remaining phases"
            )
            # Register saved projects so remaining gate/objective reads use the
            # atomized .npz instead of re-running completed CST solvers.
            completed_labels.add(_f2f_label)
            for _label in completed_labels:
                if _label in self._spec_by_label:
                    self._project_paths[_label] = "__virtual__"
            _orig_mk = _mk_reader
            _mk_reader = lambda pp: (lambda: _vreader) if pp == "__virtual__" else _orig_mk(pp)
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
                        self.last_completed_labels = completed_labels.copy()
                        phase_base_npz = self._save_phase_npz(
                            params,
                            iteration,
                            "f2f",
                            self._checkpoint_phases(completed_labels),
                            base_npz_path=phase_base_npz,
                        )
                    # Extra cooldown to let CST flush I/O before DE destroy
                    _term_print(f"  [cooldown] {self._cooldown_s:.0f}s before inter-pass reset")
                    time.sleep(self._cooldown_s)

            # ── Inter-pass reset: fresh DE for wakefield solvers ─────
            missing_conditional = any(
                s.condition_trigger and s.label not in completed_labels
                for s in self._specs
            )
            if any(s.condition_trigger for s in self._specs) and (
                start_phase == "f2f" or missing_conditional
            ):
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
                if spec.label in completed_labels:
                    _term_print(
                        f"  [{spec.label}] SKIP — already completed in saved phase data"
                    )
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
                        _term_print(f"  [atomize] saving {spec.label} .npz")
                        self.last_completed_labels = completed_labels.copy()
                        phase_base_npz = self._save_phase_npz(
                            params,
                            iteration,
                            spec.label,
                            self._checkpoint_phases(completed_labels),
                            base_npz_path=phase_base_npz,
                        )
                self._msg.write(label=spec.label, iteration=iteration)

            # ── Phase 2: Evaluate all objectives ──────────────────────
            _term_print(f"[Phase 2] Evaluating {n_obj} objectives")
            objective_errors: list[str] = []
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
                    objective_errors.append(f"{obj.name}: {exc}")

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

            unexpected_missing = [
                obj.name
                for idx, obj in enumerate(self._objectives)
                if (
                    not np.isfinite(raw_values[idx])
                    and self._obj_project_map[idx] not in skipped_labels
                )
            ]
            postprocess_missing = unexpected_missing if all_solvers_ok else []
            self.last_raw_values = raw_values.copy()
            self.last_penalties = penalties.copy()
            self.last_solver_ok = all_solvers_ok and not postprocess_missing
            self.last_completed_labels = completed_labels.copy()
            self.last_skipped_labels = skipped_labels.copy()

            # ── Gate recording ────────────────────────────────────────
            if (
                self._adaptive_gate is not None
                and all_solvers_ok
                and not postprocess_missing
            ):
                penalty_dict_for_gate = {
                    obj.name: float(penalties[idx])
                    for idx, obj in enumerate(self._objectives)
                }
                measurement_mask = {
                    obj.name: bool(np.isfinite(raw_values[idx]))
                    for idx, obj in enumerate(self._objectives)
                }
                f2w_ran = "wakefield" in completed_labels
                self._adaptive_gate.record_evaluation(
                    params,
                    penalty_dict_for_gate,
                    f2w_ran,
                    measurement_mask,
                    was_validation=self._gate_validation_forced,
                    predicted=self._gate_predictions,
                )

            # ── Phase 3.5: Log ────────────────────────────────────────
            if self._opt_logger is not None:
                elapsed_total = time.perf_counter() - t_start
                physics = {
                    obj.name: (
                        float(raw_values[idx])
                        if np.isfinite(raw_values[idx])
                        else np.nan
                    )
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
                    solver_ok=all_solvers_ok and not postprocess_missing,
                    error="; ".join(
                        part for part in [
                            error_str,
                            "; ".join(objective_errors),
                        ] if part
                    ),
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
                            "record_type": "evaluation",
                            "schema_version": 2,
                            "params": dict(zip(self._params.names, [float(v) for v in params])),
                            "npz_file": npz_name,
                            "solver_ok": all_solvers_ok and not postprocess_missing,
                            "error": "; ".join(
                                [*solver_errors, *objective_errors]
                            ),
                            "has_f2f": _has["has_f2f"],
                            "has_f2w": _has["has_f2w"],
                            "has_f2wo": _has["has_f2wo"],
                        },
                    )

            # NOTE: checkpoint_callback ownership is in the Workflow2
            # evaluator wrapper (workflow.py).  The orchestrator does NOT
            # fire the callback — it only exposes last_* state.
            # See W2-6E: evaluator-only callback ownership.
            if postprocess_missing:
                detail = "; ".join(objective_errors) or ", ".join(postprocess_missing)
                raise RuntimeError(
                    "Objective post-processing incomplete for "
                    f"{', '.join(postprocess_missing)}: {detail}"
                )
            return penalties

        finally:
            self.last_raw_values = raw_values.copy()
            if "penalties" in locals():
                self.last_penalties = penalties.copy()
            self.last_completed_labels = completed_labels.copy()
            self.last_skipped_labels = skipped_labels.copy()
            if resume_reader is not None:
                try:
                    resume_reader.close()
                except Exception:
                    pass
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
                solver_errors.append(
                    f"Failed to open project '{spec.label}': {exc}"
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
                        self._active_pre_filter_threshold(),
                    )
                    return False  # caller returns all-1.0

        return f2f_ok

    def _checkpoint_phases(self, completed_labels: set[str]) -> list[str]:
        """Return stable phase labels, including the legacy ``f2f`` alias."""
        phases: list[str] = []
        if any(
            spec.is_pre_filter and spec.label in completed_labels
            for spec in self._specs
        ):
            phases.append("f2f")
        phases.extend(
            spec.label for spec in self._specs if spec.label in completed_labels
        )
        return phases

    def _save_phase_npz(
        self,
        params: np.ndarray,
        iteration: int,
        phase_label: str,
        completed_phases: list[str],
        base_npz_path: str = "",
        source_iter: int | None = None,
        smoke_only: bool = False,
    ) -> str:
        """Save and replay-validate a cumulative phase NPZ.

        When recovering from an earlier atomized file, arrays from
        *base_npz_path* are merged with newly recorded curves so the newest
        phase file remains independently replayable.
        """
        from cst_optimization.database import collect_curves, save_curves_npz, save_index_record

        curves = collect_curves()
        if not curves:
            return ""
        attempt = int(getattr(self, "last_attempt", 1))
        npz_name = (
            f"eval_{iteration:04d}_a{attempt:03d}_"
            f"{phase_label}.npz"
        )
        npz_path = os.path.join(self._curves_db_dir, npz_name)
        os.makedirs(self._curves_db_dir, exist_ok=True)
        save_curves_npz(npz_path, curves)
        if (
            base_npz_path
            and os.path.isfile(base_npz_path)
            and os.path.abspath(base_npz_path) != os.path.abspath(npz_path)
        ):
            with np.load(base_npz_path, allow_pickle=True) as base_data:
                merged_payload = {
                    key: base_data[key] for key in base_data.files
                }
            with np.load(npz_path, allow_pickle=True) as new_data:
                merged_payload.update(
                    {key: new_data[key] for key in new_data.files}
                )
            np.savez_compressed(npz_path, **merged_payload)

        durable_labels = {
            phase
            for phase in completed_phases
            if phase in self._spec_by_label
        }
        phase_manifest = [
            spec.label
            for spec in self._specs
            if spec.label in durable_labels
        ]
        replayed = replay_snapshot(
            npz_path,
            self._objectives,
            self._obj_project_map,
            self._ref_project_map,
            durable_labels,
        )
        expected_objectives = {
            obj.name
            for obj, owner in zip(
                self._objectives,
                self._obj_project_map,
            )
            if owner in durable_labels
        }
        if (
            replayed.errors
            or not expected_objectives.issubset(
                set(replayed.objective_manifest)
            )
        ):
            _logger.error(
                "Phase snapshot validation failed for %s: expected=%s "
                "replayed=%s errors=%s",
                npz_path,
                sorted(expected_objectives),
                replayed.objective_manifest,
                replayed.errors,
            )
            return ""

        index_path = os.path.join(self._curves_db_dir, "index.jsonl")
        save_index_record(
            index_path,
            {
                "iter": iteration,
                "attempt": attempt,
                "source_iter": source_iter,
                "record_type": "phase",
                "schema_version": WF2_INDEX_SCHEMA_VERSION,
                "params": dict(
                    zip(self._params.names, [float(v) for v in params])
                ),
                "params_hash": parameter_hash(self._params.names, params),
                "npz_file": npz_name,
                "phase_manifest": phase_manifest,
                "objective_manifest": replayed.objective_manifest,
                "phases_done": list(completed_phases),
                "solver_ok": True,
                "solvers_ok": True,
                "postprocess_ok": True,
                "evaluation_ok": False,
                "has_f2f": "f2f" in completed_phases,
                "has_f2w": "wakefield" in completed_phases,
                "has_f2wo": "wakefield_offset" in completed_phases,
                "smoke_only": bool(smoke_only),
            },
        )
        if self._phase_checkpoint_callback is not None:
            try:
                self._phase_checkpoint_callback(
                    params.copy(), iteration, list(completed_phases), npz_path,
                )
            except Exception:
                _logger.exception(
                    "Phase checkpoint callback failed after saving %s",
                    npz_path,
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

    def _reset_connection(
        self,
        cleanup_labels: set[str] | None = None,
    ) -> None:
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
        selected = (
            set(cleanup_labels)
            if cleanup_labels is not None
            else {
                spec.label
                for spec in self._specs
                if not spec.is_pre_filter
            }
        )
        for spec in self._specs:
            if spec.label not in selected:
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
        threshold_db = self._active_pre_filter_threshold()
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

            if np.isfinite(raw) and raw > threshold_db:
                if (
                    self._adaptive_gate is not None
                    and not self._adaptive_gate.is_warmup
                    and self._adaptive_gate.should_validate_next()
                ):
                    _logger.info(
                        "Pre-filter validation bypass: '%s' = %.1f dB > "
                        "%.0f dB",
                        obj.name,
                        raw,
                        threshold_db,
                    )
                    continue
                _logger.info(
                    "Pre-filter: '%s' = %.1f dB > %.0f dB → REJECT",
                    obj.name, raw, threshold_db,
                )
                return False

        return True

    def _active_pre_filter_threshold(self) -> float:
        """Return the current dB threshold used by the live pre-filter."""
        if self._adaptive_gate is not None:
            return float(self._adaptive_gate.pre_filter_db_threshold)
        return self._pre_filter_threshold_db

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
        if cst_path == "__virtual__":
            return
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
