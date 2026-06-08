"""Factory functions that build optimisers and workflow evaluators from YAML config.

Usage::

    import yaml
    from cst_optimization.factory import build_workflow_2

    with open("config/default.yaml") as fh:
        cfg = yaml.safe_load(fh)

    orch, opt, evaluator, retry_handler = build_workflow_2(cfg["workflow_2"])
    result = opt.optimize(evaluator=evaluator)

Low-level config-to-object builders live in ``cst_optimization.builders``
and are re-exported here for backward compatibility.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import numpy as np

from .builders import (
    _build_objectives,
    _build_parameters,
    _build_parameters_from_nominal,
    _build_retry_handler,
    _build_sao,
    _build_workflow_3_metrics,
    _placeholder_objectives_for_metrics,
    _resolve_named_weights,
)
from .core.connection import CSTConnection
from .core.messages import MessageLogger
from .core.orchestrator import DualProjectOrchestrator, ProjectSpec
from .core.retry import EvaluationRetryHandler, RetryConfig  # RetryConfig kept for workflow_3
from .core.solver import SolverRunner
from .objectives import antenna     # noqa: F401  — @register_objective side-effects
from .objectives import field       # noqa: F401
from .objectives import frequency   # noqa: F401
from .objectives import modes       # noqa: F401  — @register_mode side-effects
from .objectives import quality     # noqa: F401
from .objectives import wakefield   # noqa: F401
from .objectives.base import ObjectiveFunction
from .objectives.registry import get_objective, get_mode
from .optimization.adaptive_bounds import AdaptiveBoundsConfig, AdaptiveBoundsController
from .optimization.base import BaseOptimizer
from .optimization.logging import OptimizationLogger
from .optimization.saea import SurrogateAssistedEA
from .optimization.sao import SurrogateAssistedOptimizer
from .parameters.base import ParameterSet
from .workflows.recovery import (
    FrequencyGate,
    MetricSpec,
    RecoveryWorkflowEvaluator,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level entry points
# ---------------------------------------------------------------------------


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

    W2-4B compatibility wrapper: delegates to
    ``workflows.rfgun_hom_antenna.workflow.build_workflow_2``.
    """
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2 as _wf2_build

    return _wf2_build(config, checkpoint_callback=checkpoint_callback)


def build_workflow_3(
    config: dict[str, Any],
    resume_jsonl_path: str = "",
    checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None] | None = None,
) -> tuple[RecoveryWorkflowEvaluator, BaseOptimizer, Callable[[np.ndarray], Any]]:
    """Build the workflow-3 single-project recovery optimiser from config."""
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
# Re-export for backward compatibility (Phase 3: moved to WF2 package)
# ---------------------------------------------------------------------------

from workflows.rfgun_hom_antenna.orchestrator import DualProjectOrchestrator  # noqa: F401, E402

