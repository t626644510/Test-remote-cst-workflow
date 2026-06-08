"""Factory functions that build optimisers and workflow evaluators from YAML config.

Usage::

    import yaml
    from cst_optimization.factory import build_workflow_2

    with open("config/default.yaml") as fh:
        cfg = yaml.safe_load(fh)

    orch, opt, evaluator, retry_handler = build_workflow_2(cfg["workflow_2"])
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

    Parameters
    ----------
    config : dict
        The ``workflow_2`` section of ``default.yaml``.
    checkpoint_callback : callable or None
        Optional callback invoked after each evaluation.

    Returns
    -------
    orch : DualProjectOrchestrator
    optimizer : BaseOptimizer
    evaluator : callable
    retry_handler : EvaluationRetryHandler or None
    """
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2 as _wf2_build

    return _wf2_build(config, checkpoint_callback=checkpoint_callback)


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

    Accepts either ``n_initial`` or ``n_initial_samples`` (WF1 legacy) config key.
    """
    n_initial = opt_cfg.get("n_initial_samples", opt_cfg.get("n_initial", 20))
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
    """Resolve scalarisation weights from config.

    Returns a normalised weight vector (sum = 1).
    None or empty dict -> equal weights.
    Dict -> weights by objective_names order, missing names default to 1.0.
    List -> must match objective_names length.

    Raises ValueError on NaN, negative, or non-positive total sum.
    """
    if isinstance(configured, dict):
        if not configured:
            raw = np.ones(len(objective_names), dtype=float)
        else:
            raw = np.array(
                [float(configured.get(name, 1.0)) for name in objective_names],
                dtype=float,
            )
            unknown = [k for k in configured if k not in objective_names]
            if unknown:
                _logger.warning(
                    "objective_weights contains unknown metric(s): %s", unknown,
                )
    elif configured is not None and len(configured) == len(objective_names):
        raw = np.array(configured, dtype=float)
    else:
        raw = np.ones(len(objective_names), dtype=float)

    if not np.all(np.isfinite(raw)):
        raise ValueError(f"objective_weights contain non-finite values: {raw}")
    if np.any(raw < 0):
        raise ValueError(f"objective_weights contain negative values: {raw}")
    total = np.sum(raw)
    if total <= 0:
        raise ValueError(f"objective_weights sum to non-positive: {total}")
    return raw / total


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
