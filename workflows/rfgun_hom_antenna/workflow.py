"""Workflow 2 — builder implementation (W2-4B).

This module is the OWNED home of ``build_workflow_2``.  The implementation
was migrated from ``src/cst_optimization/factory.py`` in W2-4B.

The shared factory module now re-exports this function as a thin
compatibility wrapper.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

# ── Core CST abstractions ──────────────────────────────────────────────────
from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.orchestrator import DualProjectOrchestrator, ProjectSpec
from cst_optimization.core.messages import MessageLogger
from cst_optimization.core.retry import EvaluationRetryHandler
from cst_optimization.core.solver import SolverRunner
from cst_optimization.parameters.base import ParameterSet
from cst_optimization.objectives.base import ObjectiveFunction

# ── Optimisers ──────────────────────────────────────────────────────────────
from cst_optimization.optimization.base import BaseOptimizer
from cst_optimization.optimization.sao import SurrogateAssistedOptimizer
from cst_optimization.optimization.saea import SurrogateAssistedEA
from cst_optimization.optimization.logging import OptimizationLogger
from cst_optimization.optimization.acquisition import (
    ExpectedImprovement,
    UpperConfidenceBound,
    ProbabilityOfImprovement,
)

# ── Shared helpers (imported from factory — no circular dependency because
#    factory's compatibility wrapper uses a lazy import) ─────────────────────
from cst_optimization.factory import (
    _build_parameters,
    _build_objectives,
    _build_sao,
    _build_retry_handler,
    _resolve_named_weights,
)

# ── Objective registrations (side-effect decorators must fire) ─────────────
from cst_optimization.objectives import modes       # noqa: F401
from cst_optimization.objectives import frequency   # noqa: F401
from cst_optimization.objectives import quality     # noqa: F401
from cst_optimization.objectives import field       # noqa: F401
from cst_optimization.objectives import wakefield   # noqa: F401
from cst_optimization.objectives import antenna     # noqa: F401

_logger = logging.getLogger(__name__)


def build_workflow_2(
    config: dict[str, Any],
    checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None]
    | None = None,
) -> tuple[
    DualProjectOrchestrator,
    BaseOptimizer,
    Callable[[np.ndarray], Any],
    EvaluationRetryHandler | None,
]:
    """Build the Phase-2 multi-project orchestrator and optimiser from config.

    Uses **one** CST DesignEnvironment connection for sequential project
    execution.  Conditional wakefield projects are isolated by orchestrator
    reset/reconnect steps between phases.

    Parameters
    ----------
    config : dict
        The ``workflow_2`` section of ``default.yaml``.

    Returns
    -------
    orch : DualProjectOrchestrator
    optimizer : BaseOptimizer
    evaluator : callable
        The evaluator to pass to ``optimizer.optimize(evaluator=...)``.
    retry_handler : EvaluationRetryHandler or None
        Retry manager used by the evaluator when enabled; callers should close
        it during shutdown to release any replacement CST connections.
    """
    # ── Single CST connection (projects run sequentially) ────────────
    cst_cfg = config.get("cst", {})
    library_path = cst_cfg.get("library_path", r"D:\CST\AMD64\python_cst_libraries")
    connect_mode = cst_cfg.get("connect_mode", "new")

    conn = CSTConnection(library_path=library_path, mode=connect_mode)
    conn.connect()
    conn.set_quiet_mode(True)
    _logger.info("CST connection established — PID %s", conn.pid)

    # ── Evaluation config ────────────────────────────────────────────
    eval_cfg = config.get("evaluation", {})
    post_eval_recovery = (eval_cfg.get("post_eval_recovery", "") or "").strip().lower()
    pre_eval_cleanup = bool(eval_cfg.get("pre_eval_cleanup", False))

    # ── Retry config from workflow_2.optimization.retry ──────────────
    opt_cfg = config.get("optimization", {})
    retry_cfg_raw = opt_cfg.get("retry", None)

    # ── Parameter set ────────────────────────────────────────────────
    parameters = _build_parameters(config.get("parameters", []))
    param_set = ParameterSet(parameters)

    # ── Constraints ──────────────────────────────────────────────────
    constraint_entries = config.get("constraints", [])
    if constraint_entries:
        from cst_optimization.parameters.base import build_constraint, ConstraintSet
        cs_list = [
            build_constraint(e, param_set.names) for e in constraint_entries
        ]
        param_set.constraints = ConstraintSet(cs_list)

    # ── Objectives ───────────────────────────────────────────────────
    objectives, obj_project_map, ref_project_map = _build_objectives(config.get("objectives", []))

    # ── Project specs ────────────────────────────────────────────────
    projects_cfg = config.get("projects", {})
    specs: list[ProjectSpec] = []
    for label, p in projects_cfg.items():
        specs.append(ProjectSpec(
            cst_path=p["cst_path"],
            label=label,
            is_pre_filter=bool(p.get("is_pre_filter", False)),
            condition_trigger=p.get("condition_trigger", ""),
            condition_max_penalty=float(p.get("condition_max_penalty", 0.2)),
        ))

    # ── Message logger ───────────────────────────────────────────────
    msg_cfg = config.get("message_log", {})
    message_logger = MessageLogger(
        output_dir=msg_cfg.get("output_dir", "D:/Results/cst_messages"),
        enabled=msg_cfg.get("enabled", True),
    )

    # ── Solver runner ────────────────────────────────────────────────
    solver_cfg = config.get("solver", {})
    solver_runner = SolverRunner(
        timeout_s=solver_cfg.get("stagnation_timeout_s", 0.0),
        settle_s=solver_cfg.get("settle_s", 2.0),
    )

    # ── Pre-filter ───────────────────────────────────────────────────
    pre_filter_cfg = config.get("pre_filter", {})
    pre_filter_enabled = pre_filter_cfg.get("enabled", True)
    pre_filter_threshold_db = pre_filter_cfg.get("absorption_threshold_db", -25.0)

    # ── Optimisation logger (Excel) ──────────────────────────────────
    log_cfg = config.get("logging", {})
    opt_logger = None
    if log_cfg.get("enabled", True):
        output_dir = log_cfg.get("output_dir", "D:/Results")
        excel_path = f"{output_dir}/optimization_log.xlsx"
        opt_logger = OptimizationLogger(
            filepath=excel_path,
            auto_flush_interval=log_cfg.get("auto_flush_interval", 5),
        )

    # ── Curves database directory ────────────────────────────────────
    curves_db_dir = ""
    log_cfg_db = config.get("logging", {})
    if log_cfg_db.get("enabled", True):
        output_dir = log_cfg_db.get("output_dir", "D:/Results")
        curves_db_dir = f"{output_dir}/raw_curves"

    # ── Adaptive conditional gate (three-phase + TCP sliding window) ──
    gate_cfg_raw = config.get("adaptive_gate", None)
    if gate_cfg_raw is not None:
        from cst_optimization.optimization.conditional_gate import (
            GateConfig,
            AdaptiveConditionalGate,
        )
        gate_cfg = GateConfig(
            warmup_n_evaluations=int(gate_cfg_raw.get("warmup_n_evaluations", 10)),
            gp_skip_threshold=float(gate_cfg_raw.get("gp_skip_threshold", 0.5)),
            validate_every_n=int(gate_cfg_raw.get("validate_every_n", 5)),
            trust_consecutive=int(gate_cfg_raw.get("trust_consecutive", 5)),
            max_consecutive_fail=int(gate_cfg_raw.get("max_consecutive_fail", 3)),
            prediction_error_epsilon=float(gate_cfg_raw.get("prediction_error_epsilon", 0.15)),
            delta_db=float(gate_cfg_raw.get("delta_db", 2.0)),
            db_initial=float(gate_cfg_raw.get("db_initial", -25.0)),
            db_min=float(gate_cfg_raw.get("db_min", -31.0)),
            pass_rate_threshold=float(gate_cfg_raw.get("pass_rate_threshold", 0.6)),
            gp_accuracy_threshold=float(gate_cfg_raw.get("gp_accuracy_threshold", 0.85)),
            pass_rate_critical=float(gate_cfg_raw.get("pass_rate_critical", 0.3)),
            gp_alpha=float(gate_cfg_raw.get("gp_alpha", 0.001)),
        )
        adaptive_gate = AdaptiveConditionalGate(
            gate_cfg, [o.name for o in objectives],
        )
        _logger.info(
            "Adaptive conditional gate enabled (initial phase: %s)",
            adaptive_gate.phase.value,
        )
    else:
        adaptive_gate = None

    # ── Orchestrator ─────────────────────────────────────────────────
    orchestrator = DualProjectOrchestrator(
        specs=specs,
        connection=conn,
        parameter_set=param_set,
        objectives=objectives,
        obj_project_map=obj_project_map,
        solver_runner=solver_runner,
        message_logger=message_logger,
        pre_filter_enabled=pre_filter_enabled,
        pre_filter_threshold_db=float(pre_filter_threshold_db),
        pre_eval_cleanup=pre_eval_cleanup,
        opt_logger=opt_logger,
        ref_project_map=ref_project_map,
        checkpoint_callback=checkpoint_callback,
        curves_db_dir=curves_db_dir,
        library_path=library_path,
        cooldown_s=float(retry_cfg_raw.get("cooldown_s", 5.0)) if retry_cfg_raw else 5.0,
        adaptive_gate=adaptive_gate,
    )

    # ── Extra result paths for retry-handler cleanup ─────────────────
    extra_result_paths = [s.cst_path for s in specs
                          if s.cst_path != specs[0].cst_path]

    # ── Optimiser ────────────────────────────────────────────────────
    algorithm = opt_cfg.get("algorithm", "sao")
    seed = opt_cfg.get("seed", 42)
    retry_handler = None  # may be set in SAO branch

    if algorithm == "sao":
        obj_names = [o.name for o in objectives]
        weights = _resolve_named_weights(opt_cfg.get("objective_weights", None), obj_names)

        # ── Retry handler ────────────────────────────────────────────
        retry_cfg_raw = opt_cfg.get("retry", None)
        retry_handler = _build_retry_handler(
            conn, specs[0].cst_path, library_path, retry_cfg_raw,
            config, extra_result_paths,
        )
        if retry_handler is not None:
            retry_handler._on_reconnect = lambda new_conn: setattr(
                orchestrator, '_conn', new_conn,
            )

        # ── Evaluation wrapper for retry handler ─────────────────────
        _retry_skip_phases: dict[int, set[str]] = {}

        def _evaluate_for_retry(x_phys: np.ndarray, iteration: int) -> Any:
            from cst_optimization.workflows.recovery import EvaluationResult, EvaluationStatus
            param_key = (
                hash(x_phys.tobytes()) if hasattr(x_phys, 'tobytes')
                else hash(tuple(x_phys))
            )
            skip = _retry_skip_phases.get(param_key, None)
            try:
                penalties = orchestrator.execute(
                    x_phys, iteration=iteration,
                    skip_phases=skip,
                )
            except Exception as exc:
                err = str(exc)[:200]
                is_com = any(
                    w in err.lower()
                    for w in ("com", "connection", "designenvironment")
                )
                return EvaluationResult(
                    status=EvaluationStatus.COM_LOST if is_com else EvaluationStatus.SOLVER_FAILED,
                    error=err,
                )
            _retry_skip_phases[param_key] = orchestrator.last_completed_labels.copy()

            solver_ok = orchestrator.last_solver_ok
            raw = orchestrator.last_raw_values
            pen = orchestrator.last_penalties
            raw_metrics = {
                obj_names[i]: float(raw[i]) if raw is not None and np.isfinite(raw[i]) else np.nan
                for i in range(len(obj_names))
            }
            penalty_dict = {
                obj_names[i]: float(pen[i]) if pen is not None else 1.0
                for i in range(len(obj_names))
            }
            if not solver_ok:
                return EvaluationResult(
                    status=EvaluationStatus.SOLVER_FAILED,
                    error="Solver failure (mesh/COM/pre-filter reject)",
                    raw_metrics=raw_metrics,
                    penalty_values=penalty_dict,
                )
            return EvaluationResult(
                status=EvaluationStatus.SUCCESS,
                raw_metrics=raw_metrics,
                penalty_values=penalty_dict,
            )

        # ── SAO evaluator (with retry wrapping) ──────────────────────
        from cst_optimization.workflows.recovery import EvaluationStatus as _ES

        def evaluator(x_phys: np.ndarray, _it=[0]) -> float:
            iteration = int(_it[0])
            _it[0] += 1

            if retry_handler is not None:
                result, tier = retry_handler.execute(
                    _evaluate_for_retry, x_phys, iteration,
                )
                if result.status == _ES.SUCCESS:
                    penalties_arr = np.array(
                        [result.penalty_values.get(name, 1.0) for name in obj_names],
                        dtype=float,
                    )
                    raw_arr = np.array(
                        [result.raw_metrics.get(name, np.nan) for name in obj_names],
                        dtype=float,
                    )
                else:
                    penalties_arr = np.full(len(obj_names), 1.0, dtype=float)
                    raw_arr = np.full(len(obj_names), np.nan, dtype=float)

                if checkpoint_callback is not None:
                    checkpoint_callback(
                        x_phys, raw_arr, penalties_arr,
                        result.status == _ES.SUCCESS,
                        result.error or "",
                    )

                if post_eval_recovery == "tier2" and retry_handler is not None:
                    try:
                        retry_handler.force_reset()
                    except Exception:
                        _logger.warning(
                            "Post-eval graceful reset failed (non-fatal)", exc_info=True,
                        )

                return float(np.dot(penalties_arr, weights))

            # No retry handler — direct evaluation
            penalties = orchestrator.execute(x_phys, iteration=iteration)
            raw = orchestrator.last_raw_values
            penalties_arr = np.asarray(penalties, dtype=float)
            if checkpoint_callback is not None:
                raw_arr = np.array(
                    [float(raw[i]) if raw is not None and np.isfinite(raw[i]) else np.nan
                     for i in range(len(obj_names))],
                    dtype=float,
                )
                checkpoint_callback(x_phys, raw_arr, penalties_arr, True, "")
            return float(np.dot(penalties_arr, weights))

        optimizer = _build_sao(opt_cfg, param_set, objectives, seed)
    elif algorithm == "saea":
        optimizer = SurrogateAssistedEA(
            parameter_set=param_set,
            objectives=objectives,
            seed=seed,
            n_initial=opt_cfg.get("n_initial", 30),
            n_iterations=opt_cfg.get("n_iterations", 20),
            pop_size=opt_cfg.get("pop_size", 100),
            n_gen_per_iteration=opt_cfg.get("n_gen_per_iteration", 50),
            n_candidates_per_iteration=opt_cfg.get("n_candidates_per_iteration", 5),
        )
        evaluator = orchestrator.execute  # SAEA consumes vector directly

        # W2-6E: wrap SAEA evaluator so checkpoint_callback fires exactly once.
        # Since orchestrator.execute no longer owns the callback, wrap it.
        if checkpoint_callback is not None:
            _saea_obj_names = [o.name for o in objectives]

            def _saea_evaluator(x_phys: np.ndarray) -> np.ndarray:
                result = orchestrator.execute(x_phys)
                raw = orchestrator.last_raw_values
                pen = orchestrator.last_penalties
                raw_arr = np.array(
                    [float(raw[i]) if raw is not None and np.isfinite(raw[i]) else np.nan
                     for i in range(len(_saea_obj_names))],
                    dtype=float,
                )
                pen_arr = np.asarray(pen, dtype=float) if pen is not None else np.zeros(len(_saea_obj_names))
                checkpoint_callback(x_phys, raw_arr, pen_arr, orchestrator.last_solver_ok, "")
                return result

            evaluator = _saea_evaluator
    else:
        raise ValueError(f"Unknown algorithm '{algorithm}'.  Choose 'sao' or 'saea'.")

    return orchestrator, optimizer, evaluator, retry_handler
