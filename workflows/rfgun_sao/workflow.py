"""Workflow 1 builder -- local alternative to ``cst_optimization.factory.build_workflow_1``.

Extracted from the monolithic factory during Phase 5.  Behaviour is
identical to the original ``cst_optimization.factory.build_workflow_1``
but only imports the objective modules that Workflow 1 actually needs
(no wakefield, no antenna).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup (must be before cst_optimization imports)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import logging
import os
from typing import Any, Callable

import numpy as np

# ---- Shared core classes (reused, not duplicated) -------------------------
from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.retry import EvaluationRetryHandler, RetryConfig
from cst_optimization.core.solver import SolverRunner
from cst_optimization.objectives import modes       # noqa: F401  @register_mode
from cst_optimization.objectives import frequency   # noqa: F401  ResonantFreqObjective
from cst_optimization.objectives import quality     # noqa: F401  Q0, CouplingBeta
from cst_optimization.objectives import field       # noqa: F401  PeakE, Poynting, Flatness, Heating
from cst_optimization.objectives.base import CompositeObjective, ObjectiveFunction
from cst_optimization.objectives.registry import get_objective, get_mode
from cst_optimization.optimization.acquisition import (
    ExpectedImprovement,
    ProbabilityOfImprovement,
    UpperConfidenceBound,
)
from cst_optimization.optimization.sao import SurrogateAssistedOptimizer
from cst_optimization.parameters.base import ParameterSet, ParamRange
from cst_optimization.parameters.geometry import GeometryParameter
from workflows.rfgun_sao.types import (
    EvaluationResult,
    EvaluationStatus as _ES,
)

# ---- Local evaluator ------------------------------------------------------
from workflows.rfgun_sao.evaluator import Workflow1Evaluator
from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate, MultiDipDetector
from workflows.rfgun_sao.metrics import (
    build_metric_specs,
    gate_metric_names,
    objective_metric_names,
    optimize_metric_names,
    report_metric_names,
    threshold_metric_names,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------




def _resolve_evaluation_mode(config: dict[str, Any]) -> str:
    """Resolve the evaluation mode from config."""
    mode = str(config.get("evaluation", {}).get("mode", "single_pass")).strip().lower()
    if mode not in {"single_pass", "two_pass"}:
        raise ValueError(f"Unsupported evaluation.mode: {mode}")
    return mode


def _resolve_two_pass_runtime(config: dict[str, Any]) -> str:
    """Resolve the two-pass runtime backend.

    Reads ``evaluation.two_pass.runtime`` from config.
    Defaults to ``"placeholder"`` (no CST connection).

    Raises
    ------
    ValueError
        If runtime is not one of ``{"placeholder", "cst"}``.
    """
    eval_cfg = config.get("evaluation", {})
    two_pass_cfg = eval_cfg.get("two_pass", {})
    runtime = str(two_pass_cfg.get("runtime", "placeholder")).strip().lower()
    if runtime not in {"placeholder", "cst"}:
        raise ValueError(
            f"Unsupported evaluation.two_pass.runtime: {runtime}. "
            f"Expected 'placeholder' or 'cst'.",
        )
    return runtime


def build_workflow_1(
    config: dict[str, Any],
    checkpoint_callback: (
        Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None] | None
    ) = None,
    evaluation_record_callback: Callable[..., None] | None = None,
):
    """Build the Workflow 1 SAO optimiser with evaluator and retry handler.

    This replaces the original ``cst_optimization.factory.build_workflow_1``
    call.  All behaviour is identical.

    Parameters
    ----------
    config : dict
        Full YAML config (WF1 sections only).
    checkpoint_callback : callable or None
        Called after each evaluation for checkpoint persistence.

    Returns
    -------
    workflow : object
        Container with ``.objective_names``, ``._params``, ``._conn``.
    optimizer : SurrogateAssistedOptimizer
    evaluator : callable
        ``f(x_phys) -> float`` weighted-penalty scalar.
    """
    from cst_optimization.objectives.base import CompositeObjective  # noqa: F811

    eval_mode = _resolve_evaluation_mode(config)
    if eval_mode == "two_pass":
        settings = _resolve_two_pass_settings(config)
        param_entries = config.get("parameters", [])
        params_list = _build_parameters(param_entries)
        param_set = ParameterSet(params_list)
        param_names = param_set.names
        obj_entries = config.get("objectives", [])
        specs = build_metric_specs(obj_entries)
        metric_names = objective_metric_names(specs)
        report_names = report_metric_names(specs)
        optimize_entries = [e for e in obj_entries if e.get("name") in metric_names]
        objectives = _build_objectives(optimize_entries)
        opt_cfg = config.get("optimization", {})
        weights = _resolve_named_weights(
            opt_cfg.get("objective_weights", None), metric_names,
        )

        runtime = _resolve_two_pass_runtime(config)

        from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator

        if runtime == "placeholder":
            from workflows.rfgun_sao.two_pass import (
                make_placeholder_calibration_runner,
                make_placeholder_measurement_runner,
            )
            cal_runner = make_placeholder_calibration_runner()
            meas_runner = make_placeholder_measurement_runner()
            cst_conn = None
            _logger.info("Workflow 1 (two_pass placeholder): no CST connection")
        else:
            library_path = config["cst"]["library_path"]
            cst_conn = CSTConnection(
                library_path,
                mode=config["cst"].get("connect_mode", "any_or_new"),
            )
            cst_conn.connect()
            cst_conn.set_quiet_mode(True)
            _logger.info(
                "Workflow 1 (two_pass CST): connected to CST DE, PID=%s",
                cst_conn.pid,
            )

            solver_cfg = config.get("solver", {})
            solver_runner = SolverRunner(
                timeout_s=solver_cfg.get("stagnation_timeout_s", 300),
                settle_s=solver_cfg.get("settle_s", 2.0),
            )

            project_path = config["project"]["cst_path"]

            wf1_evaluator = Workflow1Evaluator(
                connection=cst_conn,
                project_path=project_path,
                solver_runner=solver_runner,
                objectives=objectives,
                param_names=param_names,
                metric_names=metric_names,
                metric_specs=specs,
            )

            from workflows.rfgun_sao.two_pass_cst import (
                make_cst_calibration_runner,
                make_cst_measurement_runner,
            )
            cal_runner = make_cst_calibration_runner(
                connection=cst_conn,
                project_path=project_path,
                solver_runner=solver_runner,
                calibration_guess_ghz=settings["calibration_guess_ghz"],
            )
            meas_runner = make_cst_measurement_runner(
                wf1_evaluator=wf1_evaluator,
                metric_names=metric_names,
            )

            if settings.get("inter_pass_recovery", False):
                _logger.warning(
                    "Workflow 1 (two_pass CST): "
                    "inter_pass_recovery=True not implemented; ignoring",
                )

        evaluator = make_two_pass_runtime_evaluator(
            param_names=param_names,
            metric_names=metric_names,
            objectives=objectives,
            weights=weights,
            fallback_ghz=settings["calibration_guess_ghz"],
            frequency_gate=settings["frequency_gate"],
            s11_depth_gate=settings["s11_depth_gate"],
            multi_dip_detector=settings["multi_dip_detector"],
            calibration_runner=cal_runner,
            measurement_runner=meas_runner,
            checkpoint_callback=checkpoint_callback,
            metric_specs=specs,
            evaluation_record_callback=evaluation_record_callback,
        )

        seed = opt_cfg.get("seed", 42)
        optimizer = _build_sao(opt_cfg, param_set, objectives, seed)

        class _TwoPassContainer:
            pass
        workflow = _TwoPassContainer()
        workflow._params = param_set
        workflow._conn = cst_conn
        workflow._retry_handler = None
        workflow.objective_names = metric_names
        workflow.report_metric_names = report_names
        workflow.metric_specs = specs
        workflow.optimize_metric_names = optimize_metric_names(specs)
        workflow.threshold_metric_names = threshold_metric_names(specs)
        workflow.gate_metric_names = gate_metric_names(specs)
        log_dir = config.get("logging", {}).get("output_dir", "D:/Results")
        workflow.record_path = os.path.join(log_dir, "workflow1", "evaluation_records.jsonl")
        return workflow, optimizer, evaluator

    library_path = config["cst"]["library_path"]

    # ---------------------------------------------------------------
    # Parameters
    # ---------------------------------------------------------------
    param_entries = config.get("parameters", [])
    params_list = _build_parameters(param_entries)
    param_set = ParameterSet(params_list)
    param_names = param_set.names

    # ---------------------------------------------------------------
    # Objectives
    # ---------------------------------------------------------------
    obj_entries = config.get("objectives", [])
    specs = build_metric_specs(obj_entries)
    metric_names = objective_metric_names(specs)
    report_names = report_metric_names(specs)
    optimize_entries = [e for e in obj_entries if e.get("name") in metric_names]
    objectives = _build_objectives(optimize_entries)

    # ---------------------------------------------------------------
    # CST connection
    # ---------------------------------------------------------------
    conn = CSTConnection(library_path, mode=config["cst"].get("connect_mode", "any_or_new"))
    conn.connect()
    conn.set_quiet_mode(True)
    _logger.info("Workflow 1: Connected to CST DE, PID=%s", conn.pid)

    # ---------------------------------------------------------------
    # Solver
    # ---------------------------------------------------------------
    solver_cfg = config.get("solver", {})
    runner = SolverRunner(
        timeout_s=solver_cfg.get("stagnation_timeout_s", 300),
        settle_s=solver_cfg.get("settle_s", 2.0),
    )

    project_path = config["project"]["cst_path"]
    project_dir = os.path.splitext(project_path)[0]
    eval_cfg = config.get("evaluation", {})

    # ---------------------------------------------------------------
    # Evaluator
    # ---------------------------------------------------------------
    wf1_evaluator = Workflow1Evaluator(
        connection=conn,
        project_path=project_path,
        solver_runner=runner,
        objectives=objectives,
        param_names=param_names,
        metric_names=metric_names,
        metric_specs=specs,
    )

    # ---------------------------------------------------------------
    # Retry handler
    # ---------------------------------------------------------------
    retry_cfg_raw = config.get("optimization", {}).get("retry", None)
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
            project_path=project_path,
            library_path=library_path,
            config=retry_config,
            on_reconnect=wf1_evaluator.on_reconnect,
        )
        _logger.info(
            "Workflow 1 retry handler: enabled (tier1=%d, tier2=%d, tier3=%d)",
            retry_config.max_tier1, retry_config.max_tier2, retry_config.max_tier3,
        )
    else:
        retry_handler = None
        _logger.info("Workflow 1 retry handler: disabled")

    _post_eval_recovery = (eval_cfg.get("post_eval_recovery", "") or "").strip().lower()

    # ---------------------------------------------------------------
    # Retry runtime config (RW3)
    # ---------------------------------------------------------------
    from workflows.rfgun_sao.retry_runtime_cst import check_legacy_retry_mutex as _check_mutex
    _retry_runtime_cfg, _rt_diag = _check_mutex(config, logger=_logger)
    if _rt_diag:
        _logger.warning("Retry runtime disabled: %s", _rt_diag)
    if _retry_runtime_cfg and _retry_runtime_cfg.enabled:
        from workflows.rfgun_sao.retry_runtime_cst import (
            build_record_from_evaluation_result,
            make_cst_retry_evaluate_once,
        )
        from workflows.rfgun_sao.retry_runtime import run_retry_loop_no_cst
        from workflows.rfgun_sao.evaluation_database_schema import (
            EvaluationDatabaseStatus as _EDS,
            ParameterIdentity,
            current_schema_version,
        )
        _logger.info("Workflow 1 retry runtime: enabled (max_tier=%d)", _retry_runtime_cfg.max_tier)

    # RW3 synthetic validation hook: env-var + config gated
    _smoke_injection_enabled: bool = (
        os.environ.get("WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION", "") == "1"
        and config.get("retry_runtime", {}).get("smoke_injection", False)
    )
    _smoke_already_injected: list[bool] = [False]

    # ---------------------------------------------------------------
    # SAO evaluator wrapper
    # ---------------------------------------------------------------
    opt_cfg = config.get("optimization", {})
    weights = _resolve_named_weights(opt_cfg.get("objective_weights", None), metric_names)

    def evaluator(x_phys: np.ndarray, _it=[0]) -> float:
        iteration = int(_it[0])
        _it[0] += 1

        if retry_handler is not None:
            result, tier = retry_handler.execute(
                wf1_evaluator.adapt_for_retry, x_phys, iteration,
            )
            if result.status == _ES.SUCCESS:
                penalties_arr = np.array(
                    [result.penalty_values.get(name, 1.0) for name in metric_names],
                    dtype=float,
                )
            else:
                penalties_arr = np.full(len(metric_names), 1.0, dtype=float)

            if checkpoint_callback is not None:
                raw_arr = np.array(
                    [
                        result.objective_values.get(name, np.nan)
                        if result.objective_values else np.nan
                        for name in metric_names
                    ],
                    dtype=float,
                )
                checkpoint_callback(
                    x_phys, raw_arr, penalties_arr,
                    result.status == _ES.SUCCESS,
                    result.error or "",
                )

            if _post_eval_recovery == "tier2" and retry_handler is not None:
                try:
                    retry_handler.force_reset()
                except Exception:
                    _logger.warning(
                        "Post-eval graceful reset failed (non-fatal)", exc_info=True,
                    )

            return float(np.dot(penalties_arr, weights))

        # --- Retry runtime path (RW3) ---
        if _retry_runtime_cfg is not None and _retry_runtime_cfg.enabled:
            # RW3 synthetic smoke injection: inject one initial SOLVER_FAILED
            # to exercise the retry loop without needing an actual CST failure.
            if _smoke_injection_enabled and not _smoke_already_injected[0]:
                _smoke_already_injected[0] = True
                _logger.info(
                    "Retry runtime smoke: injecting synthetic SOLVER_FAILED "
                    "for iteration %d", iteration,
                )
                raw = {n: np.nan for n in metric_names}
                pen = {n: 1.0 for n in metric_names}
                ok = False
                status = _ES.SOLVER_FAILED
                err = "Synthetic SOLVER_FAILED for retry runtime smoke test"
            else:
                raw, pen, ok, status, err = wf1_evaluator.evaluate_single_pass(
                    dict(zip(param_names, x_phys)), iteration,
                )

            if status == _ES.SUCCESS:
                # No retry needed — use directly
                penalties_arr = np.array(
                    [pen.get(n, 1.0) for n in metric_names], dtype=float,
                )
                if checkpoint_callback is not None:
                    raw_arr = np.array(
                        [raw.get(n, np.nan) for n in metric_names], dtype=float,
                    )
                    checkpoint_callback(x_phys, raw_arr, penalties_arr, ok, err)
                return float(np.dot(penalties_arr, weights))

            # Initial evaluation failed — build record and consider retry
            pid = ParameterIdentity(param_names=list(param_names), values=list(x_phys))
            eval_result = EvaluationResult(
                status=status, error=err,
                raw_metrics=dict(raw),
                objective_values={n: raw.get(n, np.nan) for n in metric_names},
                penalty_values=dict(pen),
            )
            initial_record = build_record_from_evaluation_result(
                pid, eval_result, retry_count=0,
            )

            # Run retry loop
            evaluate_once = make_cst_retry_evaluate_once(
                wf1_evaluator, param_names=list(param_names),
            )
            retry_result = run_retry_loop_no_cst(
                initial_record=initial_record,
                evaluate_once=evaluate_once,
                config=_retry_runtime_cfg,
                current_schema=current_schema_version(),
                recovery_callback=None,
            )

            # Use final result
            if retry_result.succeeded and retry_result.final_record is not None:
                fr = retry_result.final_record
                # Extract penalty values from final record diagnostics
                fr_diag = fr.raw_payload.diagnostics if fr.raw_payload else {}
                pen_values = (fr_diag or {}).get("__retry_penalty__", None)
                if pen_values is not None:
                    penalties_arr = np.array(
                        [pen_values.get(n, 1.0) for n in metric_names], dtype=float,
                    )
                    ok = True
                    err = ""
                else:
                    # Fallback: use all-ones
                    penalties_arr = np.full(len(metric_names), 1.0, dtype=float)
                    ok = False
                # Checkpoint records final result only
                if checkpoint_callback is not None:
                    raw_metrics = fr.raw_payload.raw_metrics if fr.raw_payload else {}
                    raw_arr = np.array(
                        [raw_metrics.get(n, np.nan) for n in metric_names], dtype=float,
                    )
                    checkpoint_callback(x_phys, raw_arr, penalties_arr, ok, err)
            else:
                penalties_arr = np.full(len(metric_names), 1.0, dtype=float)
                if checkpoint_callback is not None:
                    checkpoint_callback(
                        x_phys, np.full(len(metric_names), np.nan), penalties_arr,
                        False, retry_result.stopped_reason,
                    )

            return float(np.dot(penalties_arr, weights))

        # --- Plain single_pass path (no retry) ---
        raw, pen, ok, status, err = wf1_evaluator.evaluate_single_pass(
            dict(zip(param_names, x_phys)), iteration,
        )
        penalties_arr = np.array([pen.get(n, 1.0) for n in metric_names], dtype=float)
        if checkpoint_callback is not None:
            raw_arr = np.array([raw.get(n, np.nan) for n in metric_names], dtype=float)
            checkpoint_callback(x_phys, raw_arr, penalties_arr, ok, err)
        return float(np.dot(penalties_arr, weights))

    # ---------------------------------------------------------------
    # Optimizer
    # ---------------------------------------------------------------
    algorithm = opt_cfg.get("algorithm", "sao")
    seed = opt_cfg.get("seed", 42)
    _logger.info("Workflow 1 optimizer: %s (seed=%d)", algorithm, seed)
    optimizer = _build_sao(opt_cfg, param_set, objectives, seed)

    # ---------------------------------------------------------------
    # Workflow container
    # ---------------------------------------------------------------
    class _Workflow1Container:
        pass
    workflow = _Workflow1Container()
    workflow._params = param_set
    workflow._conn = conn
    workflow._retry_handler = retry_handler
    workflow.objective_names = metric_names
    workflow.report_metric_names = report_names
    workflow.metric_specs = specs
    workflow.optimize_metric_names = optimize_metric_names(specs)
    workflow.threshold_metric_names = threshold_metric_names(specs)
    workflow.gate_metric_names = gate_metric_names(specs)
    log_dir = config.get("logging", {}).get("output_dir", "D:/Results")
    workflow.record_path = os.path.join(log_dir, "workflow1", "evaluation_records.jsonl")

    return workflow, optimizer, evaluator


# ---------------------------------------------------------------------------
# Local helpers (copied from factory.py, WF1-only)
# ---------------------------------------------------------------------------


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
) -> list[ObjectiveFunction]:
    """Build objective instances from config entries (WF1-single-project).

    Returns only the objective list (no project_map / ref_project_map
    since WF1 has a single project).
    """
    objectives: list[ObjectiveFunction] = []
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
        obj = obj_cls(reader_factory=lambda: None, mode=mode, **obj_params)
        objectives.append(obj)

    return objectives


def _build_sao(
    opt_cfg: dict[str, Any],
    param_set: ParameterSet,
    objectives: list[ObjectiveFunction],
    seed: int,
) -> SurrogateAssistedOptimizer:
    """Build a single-objective SAO optimiser."""
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

    if len(objectives) > 1:
        objective_names = [obj.name for obj in objectives]
        weights_arr = _resolve_named_weights(
            opt_cfg.get("objective_weights", None),
            objective_names,
        )
        weights = list(weights_arr)
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

def _build_frequency_gate(eval_cfg: dict) -> FrequencyGate:
    cfg = eval_cfg.get("frequency_gate", {})
    return FrequencyGate(
        enabled=bool(cfg.get("enabled", False)),
        target_ghz=float(cfg.get("target_ghz", 11.424)),
        max_abs_offset_mhz=float(cfg.get("max_abs_offset_mhz", 20.0)),
    )


def _build_s11_depth_gate(eval_cfg: dict) -> S11DepthGate:
    cfg = eval_cfg.get("s11_depth_gate", {})
    return S11DepthGate(
        enabled=bool(cfg.get("enabled", False)),
        threshold_db=float(cfg.get("threshold_db", -1.0)),
    )


def _build_multi_dip_detector(eval_cfg: dict) -> MultiDipDetector:
    cfg = eval_cfg.get("multi_dip_detection", {})
    return MultiDipDetector(
        enabled=bool(cfg.get("enabled", False)),
        mode_spacing_ghz=float(cfg.get("mode_spacing_ghz", 0.04)),
    )


def _resolve_two_pass_settings(config: dict) -> dict:
    eval_cfg = config.get("evaluation", {})
    return {
        "mode": str(eval_cfg.get("mode", "single_pass")).strip().lower(),
        "target_freq_ghz": float(eval_cfg.get("target_freq_ghz", 11.424)),
        "calibration_guess_ghz": float(eval_cfg.get("calibration_guess_ghz", 11.424)),
        "inter_pass_recovery": bool(eval_cfg.get("inter_pass_recovery", False)),
        "frequency_gate": _build_frequency_gate(eval_cfg),
        "s11_depth_gate": _build_s11_depth_gate(eval_cfg),
        "multi_dip_detector": _build_multi_dip_detector(eval_cfg),
    }
