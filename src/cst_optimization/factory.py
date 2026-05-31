"""Factory functions that build optimisers and workflow evaluators from YAML config.

Usage::

    import yaml
    from cst_optimization.factory import build_workflow_2

    with open("config/default.yaml") as fh:
        cfg = yaml.safe_load(fh)

    orch, opt, evaluator = build_workflow_2(cfg["workflow_2"])
    result = opt.optimize(evaluator=evaluator)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import numpy as np

from .core.connection import CSTConnection
from .core.orchestrator import DualProjectOrchestrator, ProjectSpec
from .core.messages import MessageLogger
from .core.retry import EvaluationRetryHandler, RetryConfig  # RetryConfig kept for workflow_3
from .core.solver import SolverRunner
from .parameters.base import ParameterSet, ParamRange
from .parameters.geometry import GeometryParameter
from .objectives.base import ObjectiveFunction
from .objectives.registry import get_objective, get_mode
from .objectives import modes       # noqa: F401  — @register_mode decorators
# Force import of all objective modules so @register_objective decorators fire
from .objectives import frequency   # noqa: F401  — ResonantFreqObjective
from .objectives import quality     # noqa: F401  — Q0, QL, CouplingBeta, InputPower
from .objectives import field       # noqa: F401  — PeakE, Poynting, Flatness, Heating
from .objectives import wakefield   # noqa: F401  — Z_longitudinal, Z_transverse
from .objectives import antenna     # noqa: F401  — AntennaAbsorption, AntennaAbsorptionDB
from .optimization.base import BaseOptimizer
from .optimization.sao import SurrogateAssistedOptimizer
from .optimization.saea import SurrogateAssistedEA
from .optimization.logging import OptimizationLogger
from .optimization.acquisition import (
    ExpectedImprovement, UpperConfidenceBound, ProbabilityOfImprovement,
)
from .optimization.adaptive_bounds import AdaptiveBoundsConfig, AdaptiveBoundsController
from .workflows.recovery import (
    FrequencyGate,
    MetricSpec,
    RecoveryWorkflowEvaluator,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def build_workflow_1(
    config: dict[str, Any],
    checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None] | None = None,
):
    """Build a single-project single-pass workflow-1 optimiser.

    Workflow 1 evaluates a single frequency-domain CST project with a
    one-pass solve (fixed ``f_data``), wrapped in a three-tier retry
    handler with post-evaluation graceful reset.
    """
    import time as _time
    from .core.results import ResultReader
    from .core.project import CSTProject
    from .physics.formulas import (
        half_power_bandwidth, loaded_q_from_bandwidth,
        coupling_beta as _coupling_beta_formula, intrinsic_q0,
    )
    from .physics.poynting import max_modified_poynting, discover_field_files
    from .physics.heating import max_h_from_field_file, pulsed_heating_delta_t
    from .workflows.recovery import EvaluationResult, EvaluationStatus as _ES

    library_path = config["cst"]["library_path"]

    # ── Parameters ──────────────────────────────────────────────────
    param_entries = config.get("parameters", [])
    params_list = _build_parameters(param_entries)
    param_set = ParameterSet(params_list)
    param_names = param_set.names

    # ── Objectives ──────────────────────────────────────────────────
    obj_entries = config.get("objectives", [])
    objectives, _, _ = _build_objectives(obj_entries)
    metric_names = [o.name for o in objectives]

    # ── Connection ──────────────────────────────────────────────────
    conn = CSTConnection(library_path, mode=config["cst"].get("connect_mode", "any_or_new"))
    conn.connect()
    conn.set_quiet_mode(True)
    _logger.info("Workflow 1: Connected to CST DE, PID=%s", conn.pid)

    # ── Solver ──────────────────────────────────────────────────────
    solver_cfg = config.get("solver", {})
    runner = SolverRunner(
        timeout_s=solver_cfg.get("stagnation_timeout_s", 300),
        settle_s=solver_cfg.get("settle_s", 2.0),
    )

    project_path = config["project"]["cst_path"]
    project_dir = os.path.splitext(project_path)[0]
    eval_cfg = config.get("evaluation", {})

    # ── Single-pass evaluate ───────────────────────────────────────
    _conn_ref = conn

    def _evaluate_single_pass(param_dict: dict[str, float], iteration: int):
        nonlocal _conn_ref
        raw_metrics: dict[str, float] = {}
        penalties: dict[str, float] = {}
        solver_ok = False
        error = ""
        project = None

        try:
            project = _conn_ref.open_project(project_path)
            ok = project.update_parameters(param_dict, use_full_rebuild=True)
            if not ok:
                raise RuntimeError("Parameter update failed")
            _logger.info("Workflow 1: rebuild done for iteration %d", iteration)

            solver_result = runner.run(project)
            if not solver_result.success:
                if solver_result.error_type == "com":
                    return raw_metrics, penalties, False, _ES.COM_LOST, "COM connection lost"

            try:
                project.save()
            except Exception:
                pass

            for _ in range(3):
                _time.sleep(5.0)
                e_file, _ = discover_field_files(project_dir)
                if e_file:
                    break

            reader = ResultReader(project.filename, allow_interactive=True)
            s11 = reader.get_s_parameter()
            mag = np.abs(s11.s_complex)

            f0, f1, f2, gamma_min = half_power_bandwidth(
                s11.frequencies, mag, target_freq=11.424,
            )
            raw_metrics["resonant_freq"] = float(f0)
            coupling = float(_coupling_beta_formula(gamma_min))
            raw_metrics["coupling_beta"] = coupling
            raw_metrics["q0"] = float(intrinsic_q0(
                loaded_q_from_bandwidth(f0, f1, f2), coupling,
            ))

            e_max = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
            e_sim = float(e_max.value)
            raw_metrics["peak_e_field"] = e_sim

            try:
                e1 = reader.get_scalar(reader.TREEPATH_MAX_E_Z1).value
                e2 = reader.get_scalar(reader.TREEPATH_MAX_E_Z2).value
                emx = max(e_sim, e1, e2)
                emn = min(e_sim, e1, e2)
                raw_metrics["field_flatness"] = 1.0 - emn / emx if emx > 0 else 1.0
            except Exception:
                raw_metrics["field_flatness"] = np.nan

            e_file, h_file = discover_field_files(project_dir)
            if e_file and h_file and e_sim > 0:
                scale = 200e6 / e_sim
                raw_metrics["max_modified_poynting"] = float(
                    max_modified_poynting(e_file, h_file, gc=0.125, field_scale=scale)
                )
                h_peak = max_h_from_field_file(h_file)
                raw_metrics["pulsed_heating"] = float(pulsed_heating_delta_t(
                    h_peak_sim=h_peak, e_peak_sim=e_sim,
                    e_target=200e6, pulse_width_ns=300,
                    frequency_hz=11.424e9, rrr=5.5,
                ))

            for obj in objectives:
                val = raw_metrics.get(obj.name, np.nan)
                penalties[obj.name] = float(obj.mode.compute(float(val))) if np.isfinite(val) else 1.0

            solver_ok = True
            _logger.info(
                "Workflow 1 iter %d done: %s", iteration,
                ", ".join(f"{k}={v:.6g}" for k, v in sorted(raw_metrics.items())
                         if np.isfinite(v)),
            )

        except Exception as exc:
            error = str(exc)[:200]
            if any(w in error.lower() for w in ("com", "connection", "designenvironment")):
                return raw_metrics, penalties, False, _ES.COM_LOST, error
            _logger.warning("Workflow 1 eval failed iter %d: %s", iteration, error)

        finally:
            if project is not None:
                try:
                    project.close(save=False)
                except Exception:
                    pass

        status = _ES.SUCCESS if solver_ok else _ES.SOLVER_FAILED
        return raw_metrics, penalties, solver_ok, status, error

    # ── Adapter for EvaluationRetryHandler ───────────────────────────
    def _adapt_for_retry(params: np.ndarray, iteration: int) -> EvaluationResult:
        param_dict = dict(zip(param_names, params))
        raw, pen, ok, status, err = _evaluate_single_pass(param_dict, iteration)
        return EvaluationResult(
            status=status,
            error=err,
            f0_ghz=float(raw.get("resonant_freq", np.nan)),
            raw_metrics=raw,
            penalty_values=pen,
            objective_values={k: raw.get(k, np.nan) for k in metric_names},
        )

    # ── Retry handler ────────────────────────────────────────────────
    retry_cfg_raw = config.get("optimization", {}).get("retry", None)
    if retry_cfg_raw and retry_cfg_raw.get("enabled", True):
        retry_config = RetryConfig(
            enabled=True,
            max_tier1=int(retry_cfg_raw.get("max_tier1", 3)),
            max_tier2=int(retry_cfg_raw.get("max_tier2", 2)),
            max_tier3=int(retry_cfg_raw.get("max_tier3", 1)),
            evaluation_timeout_s=float(
                retry_cfg_raw.get("evaluation_timeout_s",
                                   config.get("solver", {}).get("evaluation_timeout_s", 600.0))
            ),
            cooldown_s=float(retry_cfg_raw.get("cooldown_s", 5.0)),
        )

        def _on_reconnect_wf1(new_conn):
            nonlocal _conn_ref
            _conn_ref = new_conn

        retry_handler = EvaluationRetryHandler(
            connection=conn,
            project_path=project_path,
            library_path=library_path,
            config=retry_config,
            on_reconnect=_on_reconnect_wf1,
        )
        _logger.info("Workflow 1 retry handler: enabled (tier1=%d, tier2=%d, tier3=%d)",
                     retry_config.max_tier1, retry_config.max_tier2, retry_config.max_tier3)
    else:
        retry_handler = None
        _logger.info("Workflow 1 retry handler: disabled")

    _post_eval_recovery = (eval_cfg.get("post_eval_recovery", "") or "").strip().lower()

    # ── SAO evaluator wrapper ────────────────────────────────────────
    opt_cfg = config.get("optimization", {})
    weights = _resolve_named_weights(opt_cfg.get("objective_weights", None), metric_names)

    def evaluator(x_phys: np.ndarray, _it=[0]) -> float:
        iteration = int(_it[0])
        _it[0] += 1

        if retry_handler is not None:
            result, tier = retry_handler.execute(_adapt_for_retry, x_phys, iteration)
            if result.status == _ES.SUCCESS:
                penalties_arr = np.array(
                    [result.penalty_values.get(name, 1.0) for name in metric_names],
                    dtype=float,
                )
            else:
                penalties_arr = np.full(len(metric_names), 1.0, dtype=float)

            if checkpoint_callback is not None:
                raw_arr = np.array(
                    [result.objective_values.get(name, np.nan) if result.objective_values else np.nan
                     for name in metric_names],
                    dtype=float,
                )
                checkpoint_callback(x_phys, raw_arr, penalties_arr,
                                   result.status == _ES.SUCCESS,
                                   result.error or "")

            if _post_eval_recovery == "tier2" and retry_handler is not None:
                try:
                    retry_handler.force_reset()
                except Exception:
                    _logger.warning("Post-eval graceful reset failed (non-fatal)", exc_info=True)

            return float(np.dot(penalties_arr, weights))

        raw, pen, ok, status, err = _evaluate_single_pass(
            dict(zip(param_names, x_phys)), iteration,
        )
        penalties_arr = np.array([pen.get(n, 1.0) for n in metric_names], dtype=float)
        if checkpoint_callback is not None:
            raw_arr = np.array([raw.get(n, np.nan) for n in metric_names], dtype=float)
            checkpoint_callback(x_phys, raw_arr, penalties_arr, ok, err)
        return float(np.dot(penalties_arr, weights))

    # ── Optimizer ─────────────────────────────────────────────────────
    algorithm = opt_cfg.get("algorithm", "sao")
    seed = opt_cfg.get("seed", 42)
    _logger.info("Workflow 1 optimizer: %s (seed=%d)", algorithm, seed)
    optimizer = _build_sao(opt_cfg, param_set, objectives, seed)

    # ── Container ─────────────────────────────────────────────────────
    class _Workflow1Container:
        pass
    workflow = _Workflow1Container()
    workflow._params = param_set
    workflow._conn = conn
    workflow.objective_names = metric_names
    log_dir = config.get("logging", {}).get("output_dir", "D:/Results")
    workflow.record_path = os.path.join(log_dir, "workflow1", "evaluation_records.jsonl")

    return workflow, optimizer, evaluator


def build_workflow_2(
    config: dict[str, Any],
    checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None] | None = None,
) -> tuple[DualProjectOrchestrator, BaseOptimizer, Callable[[np.ndarray], Any]]:
    """Build the Phase-2 multi-project orchestrator and optimiser from config.

    Creates an independent ``CSTConnection(mode="new")`` for each project,
    so each opens in its own CST Studio Suite window.

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
        from .parameters.base import build_constraint, ConstraintSet
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
        from .optimization.conditional_gate import GateConfig, AdaptiveConditionalGate
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
        _logger.info("Adaptive conditional gate enabled (initial phase: %s)", adaptive_gate.phase.value)
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
    opt_cfg = config.get("optimization", {})
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
        _retry_skip_phases: dict[int, set[str]] = {}  # keyed by hash(params.tobytes())

        def _evaluate_for_retry(x_phys: np.ndarray, iteration: int) -> Any:
            from .workflows.recovery import EvaluationResult, EvaluationStatus
            param_key = hash(x_phys.tobytes()) if hasattr(x_phys, 'tobytes') else hash(tuple(x_phys))
            skip = _retry_skip_phases.get(param_key, None)
            try:
                penalties = orchestrator.execute(
                    x_phys, iteration=iteration,
                    skip_phases=skip,
                )
            except Exception as exc:
                err = str(exc)[:200]
                is_com = any(w in err.lower()
                             for w in ("com", "connection", "designenvironment"))
                return EvaluationResult(
                    status=EvaluationStatus.COM_LOST if is_com else EvaluationStatus.SOLVER_FAILED,
                    error=err,
                )
            # Save completed phases for per-phase retry on next attempt
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
        from .workflows.recovery import EvaluationStatus as _ES

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
    else:
        raise ValueError(f"Unknown algorithm '{algorithm}'.  Choose 'sao' or 'saea'.")

    return orchestrator, optimizer, evaluator, retry_handler


def build_workflow_3(
    config: dict[str, Any],
    resume_jsonl_path: str = "",
    checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None] | None = None,
) -> tuple[RecoveryWorkflowEvaluator, BaseOptimizer, Callable[[np.ndarray], Any]]:
    """Build the workflow-3 single-project recovery optimiser from config.

    Parameters
    ----------
    config : dict
        Parsed ``workflow_3.yaml``.
    resume_jsonl_path : str
        If non-empty, load prior evaluation data from this JSONL file
        and attach it to the evaluator for GP pre-seeding.
    """
    cst_cfg = config.get("cst", {})
    library_path = cst_cfg.get("library_path", r"D:\CST\AMD64\python_cst_libraries")
    connect_mode = cst_cfg.get("connect_mode", "any_or_new")
    _logger.info("Building workflow 3 with connect_mode=%s", connect_mode)
    _logger.info("CST library path: %s", library_path)

    parameters = _build_parameters_from_nominal(config.get("parameters", []))
    param_set = ParameterSet(parameters)
    _logger.info("Workflow 3 parameter count: %d", param_set.n_parameters)

    constraint_entries = config.get("constraints", [])
    if constraint_entries:
        from .parameters.base import ConstraintSet, build_constraint
        cs_list = [build_constraint(e, param_set.names) for e in constraint_entries]
        param_set.constraints = ConstraintSet(cs_list)

    metrics = _build_workflow_3_metrics(config.get("objectives", []))
    optimize_metrics = [m for m in metrics if m.role == "optimize"]
    threshold_metrics = [m for m in metrics if m.role == "threshold"]
    report_metrics = [m for m in metrics if m.role == "report_only"]
    _logger.info(
        "Workflow 3 metrics: optimize=%d threshold=%d report_only=%d",
        len(optimize_metrics), len(threshold_metrics), len(report_metrics),
    )

    _logger.info("Connecting to CST DesignEnvironment...")
    conn = CSTConnection(library_path=library_path, mode=connect_mode)
    conn.connect()
    conn.set_quiet_mode(True)
    _logger.info("Connected to CST DesignEnvironment. PID=%s", conn.pid)

    msg_cfg = config.get("message_log", {})
    if not msg_cfg:
        msg_cfg = {"enabled": True, "output_dir": config.get("logging", {}).get("output_dir", "D:/Results")}
    message_logger = MessageLogger(
        output_dir=msg_cfg.get("output_dir", "D:/Results/cst_messages"),
        enabled=msg_cfg.get("enabled", True),
    )
    _logger.info("CST message logs: %s", msg_cfg.get("output_dir", "D:/Results/cst_messages"))

    solver_cfg = config.get("solver", {})
    solver_runner = SolverRunner(
        timeout_s=solver_cfg.get("stagnation_timeout_s", 0.0),
        settle_s=solver_cfg.get("settle_s", 2.0),
    )

    log_cfg = config.get("logging", {})
    opt_logger = None
    if log_cfg.get("enabled", True):
        output_dir = log_cfg.get("output_dir", "D:/Results")
        excel_path = f"{output_dir}/workflow_3_log.xlsx"
        opt_logger = OptimizationLogger(
            filepath=excel_path,
            auto_flush_interval=log_cfg.get("auto_flush_interval", 5),
        )
        _logger.info("Workflow 3 Excel log: %s", excel_path)

    eval_cfg = config.get("evaluation", {})
    gate_cfg = eval_cfg.get("frequency_gate", {})
    gate = FrequencyGate(
        enabled=gate_cfg.get("enabled", True),
        target_ghz=float(gate_cfg.get("target_ghz", eval_cfg.get("calibration_guess_ghz", 11.424))),
        max_abs_offset_mhz=float(gate_cfg.get("max_abs_offset_mhz", 20.0)),
    )

    warm_start = np.array(
        [float(entry["nominal"]) for entry in config.get("parameters", []) if entry.get("enabled", True)],
        dtype=float,
    )

    workflow = RecoveryWorkflowEvaluator(
        connection=conn,
        cst_path=config["project"]["cst_path"],
        parameter_set=param_set,
        optimize_metrics=optimize_metrics,
        threshold_metrics=threshold_metrics,
        report_metrics=report_metrics,
        solver_runner=solver_runner,
        message_logger=message_logger,
        frequency_gate=gate,
        calibration_guess_ghz=float(eval_cfg.get("calibration_guess_ghz", 11.424)),
        warm_start=warm_start,
        opt_logger=opt_logger,
        record_dir=log_cfg.get("output_dir", "D:/Results"),
        s11_depth_threshold_db=float(eval_cfg.get("s11_depth_threshold_db", -1.0)),
        mode_spacing_ghz=float(eval_cfg.get("mode_spacing_ghz", 0.04)),
        library_path=library_path,
        inter_pass_recovery=(eval_cfg.get("inter_pass_recovery", False)),
    )
    _logger.info("Workflow 3 evaluation records: %s", workflow.record_path)

    opt_cfg = config.get("optimization", {})
    algorithm = opt_cfg.get("algorithm", "sao")
    seed = opt_cfg.get("seed", 42)
    _logger.info("Workflow 3 optimizer algorithm: %s (seed=%s)", algorithm, seed)

    if algorithm == "sao":
        metric_names = workflow.objective_names
        weights = _resolve_named_weights(opt_cfg.get("objective_weights", None), metric_names)

        # ── Retry handler (three-tier escalation) ──────────────────
        retry_cfg_raw = opt_cfg.get("retry", None)
        if retry_cfg_raw and retry_cfg_raw.get("enabled", True):
            retry_config = RetryConfig(
                enabled=True,
                max_tier1=int(retry_cfg_raw.get("max_tier1", 3)),
                max_tier2=int(retry_cfg_raw.get("max_tier2", 2)),
                max_tier3=int(retry_cfg_raw.get("max_tier3", 1)),
                evaluation_timeout_s=float(
                    retry_cfg_raw.get(
                        "evaluation_timeout_s",
                        config.get("solver", {}).get("evaluation_timeout_s", 600.0),
                    )
                ),
                cooldown_s=float(retry_cfg_raw.get("cooldown_s", 5.0)),
            )
            retry_handler = EvaluationRetryHandler(
                connection=conn,
                project_path=config["project"]["cst_path"],
                library_path=library_path,
                config=retry_config,
                on_reconnect=lambda new_conn: setattr(workflow, "_conn", new_conn),
            )
            _logger.info("Workflow 3 retry handler: enabled (tier1=%d, tier2=%d, tier3=%d)",
                         retry_config.max_tier1, retry_config.max_tier2, retry_config.max_tier3)
            workflow._retry_handler = retry_handler
        else:
            retry_handler = None
            _logger.info("Workflow 3 retry handler: disabled")

        from .workflows.recovery import EvaluationStatus as _EvaluationStatus

        _post_eval_recovery = (config.get("evaluation", {}).get("post_eval_recovery", "") or "").strip().lower()

        def evaluator(x_phys: np.ndarray, _it=[0]) -> float:
            iteration = int(_it[0])
            _it[0] += 1
            if retry_handler is not None:
                result, tier = retry_handler.execute(
                    workflow.evaluate, x_phys, iteration,
                )
                if result.status == _EvaluationStatus.SUCCESS:
                    penalties = np.array(
                        [result.penalty_values.get(name, 1.0) for name in metric_names],
                        dtype=float,
                    )
                else:
                    penalties = np.full(len(metric_names), 1.0, dtype=float)
                # Checkpoint callback
                if checkpoint_callback is not None:
                    raw_arr = np.array(
                        [result.objective_values.get(name, np.nan) if result.objective_values else np.nan
                         for name in metric_names],
                        dtype=float,
                    )
                    _tier_exhausted = (tier.name == "EXHAUSTED") if hasattr(tier, "name") else False
                    _err = result.error if result.status != _EvaluationStatus.SUCCESS else ""
                    # Treat tree-path errors (S-parameter missing) as permanent failures
                    # so they don't pollute future checkpoint resumes.
                    if "tree path" in _err.lower() or "s1(2),1(2)" in _err.lower():
                        _tier_exhausted = True
                    checkpoint_callback(
                        x_phys, raw_arr, penalties,
                        result.status == _EvaluationStatus.SUCCESS,
                        _err,
                    )

                # ── Proactive per-evaluation Tier-3 recovery ─────────
                if _post_eval_recovery == "tier3" and retry_handler is not None:
                    try:
                        retry_handler.force_reset()
                    except Exception:
                        _logger.warning(
                            "Post-eval Tier-3 reset failed (non-fatal)",
                            exc_info=True,
                        )

                return float(np.dot(penalties, weights))
            return workflow.scalar_evaluator(x_phys, iteration=iteration, weights=weights)

        optimizer = _build_sao(
            opt_cfg,
            param_set,
            _placeholder_objectives_for_metrics(metric_names),
            seed,
        )
    elif algorithm == "saea":
        def evaluator(x_phys: np.ndarray, _it=[0]) -> np.ndarray:
            iteration = int(_it[0])
            _it[0] += 1
            return workflow.evaluate_objectives(x_phys, iteration=iteration)

        optimizer = SurrogateAssistedEA(
            parameter_set=param_set,
            objectives=_placeholder_objectives_for_metrics(workflow.objective_names),
            seed=seed,
            n_initial=opt_cfg.get("n_initial", 30),
            n_iterations=opt_cfg.get("n_iterations", 20),
            pop_size=opt_cfg.get("pop_size", 100),
            n_gen_per_iteration=opt_cfg.get("n_gen_per_iteration", 50),
            n_candidates_per_iteration=opt_cfg.get("n_candidates_per_iteration", 5),
        )
    else:
        raise ValueError(f"Unknown algorithm '{algorithm}'. Choose 'sao' or 'saea'.")

    setattr(evaluator, "warm_start", workflow.warm_start)

    # ── Resume / prior-data pre-loading ──────────────────────────────
    resume_cfg = config.get("resume", {})
    _resume_path = resume_jsonl_path or resume_cfg.get("jsonl_path", "")
    if _resume_path and os.path.exists(_resume_path):
        from .optimization.resume import load_prior_data_from_jsonl
        _logger.info("Loading prior evaluation data from %s", _resume_path)
        metric_names = workflow.objective_names
        if algorithm == "sao":
            w = _resolve_named_weights(opt_cfg.get("objective_weights", None), metric_names)
            prior = load_prior_data_from_jsonl(
                _resume_path,
                parameter_names=param_set.names,
                metric_names=metric_names,
                weights=w,
            )
        else:
            prior = load_prior_data_from_jsonl(
                _resume_path,
                parameter_names=param_set.names,
                metric_names=metric_names,
                weights=None,
            )
        if prior.n_points > 0:
            setattr(evaluator, "warm_start", prior.x_best)
            setattr(evaluator, "prior_data", (prior.x_phys, prior.y_raw))
            _logger.info(
                "Resume: %d prior evaluations; best idx=%d, penalty=%.6f",
                prior.n_points, prior.best_idx, float(prior.y_best if prior.y_raw.ndim == 1 else np.sum(prior.y_best)),
            )
        else:
            _logger.warning("No valid prior records found in %s", _resume_path)

    # ── Adaptive bounds controller (Phase 1 shrink + Phase 2 expand) ──
    ab_cfg_raw = opt_cfg.get("adaptive_bounds", None)
    if ab_cfg_raw and ab_cfg_raw.get("enabled", True):
        ab_config = AdaptiveBoundsConfig(
            enabled=True,
            rejection_threshold=float(ab_cfg_raw.get("rejection_threshold", 0.4)),
            shrink_factor=float(ab_cfg_raw.get("shrink_factor", 0.7)),
            max_shrink_rounds=int(ab_cfg_raw.get("max_shrink_rounds", 3)),
            min_span_ratio=float(ab_cfg_raw.get("min_span_ratio", 0.1)),
            boundary_proximity=float(ab_cfg_raw.get("boundary_proximity", 0.1)),
            expand_factor=float(ab_cfg_raw.get("expand_factor", 1.5)),
            max_span_ratio=float(ab_cfg_raw.get("max_span_ratio", 2.0)),
        )
        bounds_ctrl = AdaptiveBoundsController(
            parameter_set=param_set,
            nominal_values=warm_start.copy(),
            config=ab_config,
            seed=seed,
        )
        setattr(evaluator, "bounds_controller", bounds_ctrl)
        _logger.info("Workflow 3 adaptive bounds: enabled")
    else:
        setattr(evaluator, "bounds_controller", None)
        _logger.info("Workflow 3 adaptive bounds: disabled")

    return workflow, optimizer, evaluator


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------


def _make_sao_evaluator(
    orchestrator: DualProjectOrchestrator,
    opt_cfg: dict[str, Any],
    n_objectives: int,
) -> Callable[[np.ndarray], float]:
    """Create a scalar evaluator wrapper around the orchestrator.

    The orchestrator returns shape ``(n_obj,)`` penalty vector.
    SAO needs ``float`` — this wrapper applies a weighted sum.
    """
    obj_weights = opt_cfg.get("objective_weights", None)
    if obj_weights and len(obj_weights) == n_objectives:
        w = np.array(obj_weights, dtype=float) / np.sum(obj_weights)
    else:
        w = np.ones(n_objectives) / n_objectives

    def _evaluator(x_phys: np.ndarray) -> float:
        penalties = orchestrator.execute(x_phys)
        return float(np.dot(penalties, w))

    return _evaluator


def _build_parameters(
    param_entries: list[dict[str, Any]],
) -> list[GeometryParameter]:
    """Build a list of ``GeometryParameter`` instances from config entries."""
    params = []
    for entry in param_entries:
        if not entry.get("enabled", True):
            continue
        params.append(GeometryParameter(
            cst_name=entry["name"],
            range=ParamRange(
                low=float(entry["low"]),
                high=float(entry["high"]),
                log_scale=bool(entry.get("log_scale", False)),
            ),
            display_name=entry.get("display_name", entry["name"]),
            unit=entry.get("unit", "mm"),
        ))
    return params


def _build_objectives(
    obj_entries: list[dict[str, Any]],
) -> tuple[list[ObjectiveFunction], list[str], list[str]]:
    """Build objective instances and their project-label map from config.

    Returns
    -------
    objectives : list[ObjectiveFunction]
    project_map : list[str]
        For each objective, the project label whose results it reads.
    ref_project_map : list[str]
        For each objective, an optional secondary project label
        (e.g. for reading reference-beam data from a different result file).
    """
    objectives: list[ObjectiveFunction] = []
    project_map: list[str] = []
    ref_project_map: list[str] = []

    for entry in obj_entries:
        if not entry.get("enabled", True):
            continue

        obj_name = entry["name"]
        obj_cls = get_objective(obj_name)

        mode_name = entry.get("mode", "minimize")
        mode_cls = get_mode(mode_name)
        mode_params = entry.get("mode_params", {})
        mode = mode_cls(**mode_params) if mode_params else mode_cls()

        obj_params = entry.get("obj_params", {})
        proj_label = obj_params.get("project", "")
        ref_proj_label = obj_params.get("ref_project", "")

        # reader_factory is patched at runtime by the orchestrator;
        # provide a sentinel that will be replaced on each call.
        obj = obj_cls(reader_factory=lambda: None, mode=mode, **obj_params)

        objectives.append(obj)
        project_map.append(proj_label)
        ref_project_map.append(ref_proj_label)

    return objectives, project_map, ref_project_map


def _build_sao(
    opt_cfg: dict[str, Any],
    param_set: ParameterSet,
    objectives: list[ObjectiveFunction],
    seed: int,
) -> SurrogateAssistedOptimizer:
    """Build a single-objective SAO optimiser.

    The *objectives* are passed for metadata (names, count).
    The true evaluator is passed to ``optimize(evaluator=...)`` at run time.
    """
    n_initial = opt_cfg.get("n_initial", 20)
    n_iterations = opt_cfg.get("n_iterations", 100)

    acq_name = opt_cfg.get("acquisition_function", "ei")
    acq_xi = opt_cfg.get("acquisition_xi", 0.01)
    acq_kappa = opt_cfg.get("acquisition_kappa", 2.0)

    if acq_name == "ucb":
        acq = UpperConfidenceBound(kappa=acq_kappa)
    elif acq_name == "pi":
        acq = ProbabilityOfImprovement(xi=acq_xi)
    else:
        acq = ExpectedImprovement(xi=acq_xi)

    # SAO requires exactly 1 objective at construction time.
    # Multi-objective aggregation is handled by the evaluator wrapper
    # (weighted sum of per-objective penalties from the orchestrator).
    # We pass a CompositeObjective so the constructor validation passes.
    if len(objectives) > 1:
        from .objectives.base import CompositeObjective
        weights = opt_cfg.get("objective_weights", None)
        if isinstance(weights, dict):
            weights = [float(weights.get(obj.name, 1.0)) for obj in objectives]
        composite = CompositeObjective(objectives, weights=weights)
        sao_objectives: list[ObjectiveFunction] = [composite]
    else:
        sao_objectives = objectives

    return SurrogateAssistedOptimizer(
        parameter_set=param_set,
        objectives=sao_objectives,
        seed=seed,
        acquisition=acq,
        n_initial=n_initial,
        n_iterations=n_iterations,
    )


def _build_parameters_from_nominal(
    param_entries: list[dict[str, Any]],
) -> list[GeometryParameter]:
    """Build local-search geometry parameters around a nominal point."""
    params = []
    for entry in param_entries:
        if not entry.get("enabled", True):
            continue
        nominal = float(entry["nominal"])
        delta_minus = float(entry.get("delta_minus", entry.get("delta", 0.0)))
        delta_plus = float(entry.get("delta_plus", entry.get("delta", 0.0)))
        low = float(entry.get("low", nominal - delta_minus))
        high = float(entry.get("high", nominal + delta_plus))
        params.append(
            GeometryParameter(
                cst_name=entry["name"],
                range=ParamRange(
                    low=low,
                    high=high,
                    log_scale=bool(entry.get("log_scale", False)),
                ),
                display_name=entry.get("display_name", entry["name"]),
                unit=entry.get("unit", "mm"),
            )
        )
    return params


def _build_workflow_3_metrics(
    obj_entries: list[dict[str, Any]],
) -> list[MetricSpec]:
    """Build workflow-3 metric specs from config."""
    metrics: list[MetricSpec] = []
    for entry in obj_entries:
        if not entry.get("enabled", True):
            continue
        role = str(entry.get("role", "optimize"))
        name = str(entry["name"])
        objective = None
        if role == "optimize":
            obj_cls = get_objective(name)
            mode_name = entry.get("mode", "minimize")
            mode_cls = get_mode(mode_name)
            mode_params = entry.get("mode_params", {})
            mode = mode_cls(**mode_params) if mode_params else mode_cls()
            obj_params = dict(entry.get("obj_params", {}))
            objective = obj_cls(reader_factory=lambda: None, mode=mode, **obj_params)
        metrics.append(
            MetricSpec(
                name=name,
                role=role,
                priority=int(entry.get("priority", 1)),
                enabled=bool(entry.get("enabled", True)),
                report_as=entry.get("report_as"),
                objective=objective,
                threshold=entry.get("threshold"),
                sigma=entry.get("sigma"),
                direction=str(entry.get("direction", "less_than")),
                obj_params=dict(entry.get("obj_params", {})),
            )
        )
    metrics.sort(key=lambda m: (m.priority, m.output_name))
    return metrics


def _resolve_named_weights(
    configured: Any,
    objective_names: list[str],
) -> np.ndarray:
    """Resolve workflow-3 scalarisation weights from config."""
    if isinstance(configured, dict):
        raw = np.array([float(configured.get(name, 1.0)) for name in objective_names], dtype=float)
    elif configured is not None and len(configured) == len(objective_names):
        raw = np.array(configured, dtype=float)
    else:
        raw = np.ones(len(objective_names), dtype=float)
    raw = np.where(raw > 0, raw, 1.0)
    return raw / np.sum(raw)


def _placeholder_objectives_for_metrics(names: list[str]) -> list[ObjectiveFunction]:
    """Create metadata-only objective placeholders for generic optimizers."""

    class _PlaceholderObjective(ObjectiveFunction):
        name = "placeholder"
        unit = ""

        def __init__(self, metric_name: str) -> None:
            super().__init__(reader_factory=lambda: None)
            self.name = metric_name

        def raw_value(self) -> float:
            raise RuntimeError("Placeholder objective should not be evaluated directly")

    return [_PlaceholderObjective(name) for name in names]


def _build_retry_handler(
    connection: Any,
    project_path: str,
    library_path: str,
    retry_cfg_raw: dict[str, Any] | None,
    config: dict[str, Any],
    extra_result_paths: list[str] | None = None,
) -> Any | None:
    """Build an ``EvaluationRetryHandler`` from workflow-2 config."""
    from .core.retry import EvaluationRetryHandler, RetryConfig

    if not retry_cfg_raw or not retry_cfg_raw.get("enabled", True):
        _logger.info("Workflow 2 retry handler: disabled")
        return None

    retry_config = RetryConfig(
        enabled=True,
        max_tier1=int(retry_cfg_raw.get("max_tier1", 0)),
        max_tier2=int(retry_cfg_raw.get("max_tier2", 2)),
        max_tier3=int(retry_cfg_raw.get("max_tier3", 2)),
        evaluation_timeout_s=float(
            retry_cfg_raw.get(
                "evaluation_timeout_s",
                config.get("solver", {}).get("evaluation_timeout_s", 600.0),
            )
        ),
        cooldown_s=float(retry_cfg_raw.get("cooldown_s", 5.0)),
    )

    handler = EvaluationRetryHandler(
        connection=connection,
        project_path=project_path,
        library_path=library_path,
        config=retry_config,
        on_reconnect=None,  # set after orchestrator creation
        extra_result_paths=extra_result_paths or [],
    )

    _logger.info(
        "Workflow 2 retry handler: enabled (tier1=%d, tier2=%d, tier3=%d, timeout=%.0fs)",
        retry_config.max_tier1, retry_config.max_tier2, retry_config.max_tier3,
        retry_config.evaluation_timeout_s,
    )
    return handler
