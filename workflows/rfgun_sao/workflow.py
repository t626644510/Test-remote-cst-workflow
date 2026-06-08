"""Workflow 1 canonical builder -- the authoritative ``build_workflow_1`` for the
active SAO workflow package.

The root ``run_workflow_1.py`` shim delegates to
``workflows.rfgun_sao.run``, which calls this builder.
Workflow 1 imports only the objective modules it needs
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

# ---- Shared helpers (single canonical source in factory.py) -----------------
from cst_optimization.factory import _build_objectives, _build_parameters, _build_sao, _resolve_named_weights

from workflows.rfgun_sao.types import (
    EvaluationResult,
    EvaluationStatus as _ES,
)
from cst_optimization.evaluation.evaluation_database_schema import (
    ParameterIdentity,
)
from cst_optimization.evaluation.retry_runtime_cst import (
    build_record_from_evaluation_result,
)

# ---- Retry runtime helpers (no-CST pure functions) -----------------------


def _is_retry_runtime_smoke_injection_enabled(config, environ=None):
    """Check RW3 smoke injection hook gating."""
    if config is None:
        return False
    if environ is None:
        import os
        environ = os.environ
    cfg_smoke = config.get("retry_runtime", {}).get("smoke_injection", False)
    env_set = environ.get("WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION", "") == "1"
    return bool(cfg_smoke and env_set)


def _is_retry_runtime_tier2_smoke_enabled(
    config: dict | None,
    environ: dict[str, str] | None = None,
) -> bool:
    """Check whether RCR3 synthetic tier-2 recovery smoke should fire.

    Requires BOTH:
    1. ``config["retry_runtime"]["synthetic_tier2_recovery_smoke"]`` is True.
    2. Environment ``WF1_SAO_ALLOW_RCR_TIER2_SMOKE=1``.
    """
    if config is None:
        return False
    if environ is None:
        environ = os.environ
    cfg_val = config.get("retry_runtime", {}).get("synthetic_tier2_recovery_smoke", False)
    env_val = environ.get("WF1_SAO_ALLOW_RCR_TIER2_SMOKE", "") == "1"
    return bool(cfg_val and env_val)


def _extract_retry_penalty_values(final_record, metric_names):
    """Extract penalty values from retry runtime final_record diagnostics."""
    if final_record is None:
        return None
    rp = getattr(final_record, "raw_payload", None)
    if rp is None:
        return None
    diag = getattr(rp, "diagnostics", None) or {}
    pen_values = diag.get("__retry_penalty__")
    if pen_values is None:
        return None
    import numpy as np
    return np.array([pen_values.get(n, 1.0) for n in metric_names], dtype=float)


def _build_retry_runtime_checkpoint_payload(final_record, x_phys, metric_names, penalties_arr, ok, err):
    """Build checkpoint callback args from a retry runtime final_record."""
    if final_record is None:
        import numpy as np
        raw_arr = np.full(len(metric_names), np.nan, dtype=float)
    else:
        rp = getattr(final_record, "raw_payload", None)
        raw_metrics = getattr(rp, "raw_metrics", None) or {}
        import numpy as np
        raw_arr = np.array([raw_metrics.get(n, np.nan) for n in metric_names], dtype=float)
    return (x_phys, raw_arr, penalties_arr, ok, err)


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
        objectives, _, _ = _build_objectives(optimize_entries)
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
        workflow._retry_connection_registry = None
        workflow._evaluation_db = None
        workflow._db_warm_start_cfg = None
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
    from cst_optimization.evaluation.retry_runtime_cst import check_legacy_retry_mutex as _check_mutex
    _retry_runtime_cfg, _rt_diag = _check_mutex(config, logger=_logger)
    if _rt_diag:
        _logger.warning("Retry runtime disabled: %s", _rt_diag)
    # Retry runtime registry and recovery callback (RCR2)
    _retry_runtime_recovery: Any = None
    _retry_runtime_registry: Any = None
    if _retry_runtime_cfg and _retry_runtime_cfg.enabled:
        from cst_optimization.evaluation.retry_runtime_cst import (
            CstConnectionRegistry,
            make_cst_recovery_callback,
            make_cst_retry_evaluate_once,
        )
        from cst_optimization.evaluation.retry_runtime import run_retry_loop_no_cst
        from cst_optimization.evaluation.evaluation_database_schema import (
            EvaluationDatabaseStatus as _EDS,
            current_schema_version,
        )
        def _retry_connection_factory():
            """Create a new CST connection for retry recovery."""
            new_conn = CSTConnection(library_path, mode="new")
            new_conn.connect()
            new_conn.set_quiet_mode(True)
            return new_conn

        _retry_runtime_registry = CstConnectionRegistry()
        # Track the initial CST connection so it is closed via
        # registry.close_all(force) on tier-2 recovery or final cleanup.
        if conn is not None:
            _retry_runtime_registry.track(conn)
        _retry_runtime_recovery = make_cst_recovery_callback(
            connection_factory=_retry_connection_factory,
            evaluator=wf1_evaluator,
            registry=_retry_runtime_registry,
            logger=_logger,
        )
        _logger.info("Workflow 1 retry runtime: enabled (max_tier=%d)", _retry_runtime_cfg.max_tier)

    # RW3 synthetic validation hook: env-var + config gated
    _smoke_injection_enabled: bool = _is_retry_runtime_smoke_injection_enabled(config)
    _smoke_already_injected: list[bool] = [False]

    # RCR3 synthetic tier-2 recovery smoke: config + env gated
    _tier2_smoke_enabled: bool = _is_retry_runtime_tier2_smoke_enabled(config)
    _tier2_smoke_consumed: list[bool] = [False]

    # ---------------------------------------------------------------
    # Evaluation database config (DDB3)
    # ---------------------------------------------------------------
    from cst_optimization.evaluation.evaluation_database_storage import (
        EvaluationDatabaseConfig as _EDBConfig,
        SQLiteEvaluationDatabase as _SQDB,
        resolve_evaluation_database_config as _resolve_db_cfg,
    )
    _evaluation_db_cfg = _resolve_db_cfg(config, repo_root=str(_PROJECT_ROOT))
    _evaluation_db: _SQDB | None = None
    _db_run_id: str | None = None
    if _evaluation_db_cfg.enabled:
        _evaluation_db = _SQDB(_evaluation_db_cfg)
        _evaluation_db.open()
        import uuid
        _db_run_id = str(uuid.uuid4())[:8]
        _logger.info("Evaluation DB enabled: path=%s run_id=%s", _evaluation_db_cfg.path, _db_run_id)

    def _write_eval_db(record):
        """Write final_record to evaluation DB (non-fatal on failure)."""
        if _evaluation_db is None or record is None:
            return
        try:
            row_id = _evaluation_db.insert_final_record(record, run_id=_db_run_id)
            _logger.debug(
                "Evaluation DB: written (id=%d, status=%s, key=%s)",
                row_id, record.status,
                record.parameter_identity.parameter_key()[:8] if record.parameter_identity else "?",
            )
        except Exception as exc:
            _logger.warning("Evaluation DB write failed (non-fatal): %s", exc)

    # ---------------------------------------------------------------
    # Success reuse config (SR3)
    # ---------------------------------------------------------------
    from cst_optimization.evaluation.evaluation_success_reuse import (
        SuccessReuseConfig as _SRConfig,
        resolve_success_reuse_config as _resolve_sr_cfg,
        try_success_reuse as _try_success_reuse,
    )
    _sr_cfg = _resolve_sr_cfg(
        config,
        db_enabled=_evaluation_db is not None,
    )

    def _try_sr_reuse(x_phys):
        """Try to reuse a previous SUCCESS result for the given parameters."""
        if _evaluation_db is None or not _sr_cfg.enabled:
            return None
        pid = ParameterIdentity(
            param_names=list(param_names), values=list(x_phys),
        )
        return _try_success_reuse(
            _evaluation_db, pid, metric_names,
            config=_sr_cfg, logger=_logger,
        )

    # Resolve DB warm-start config (WS3) -- stored on workflow for run.py
    from cst_optimization.evaluation.evaluation_database_warm_start import (
        resolve_db_warm_start_config as _resolve_ws_cfg,
    )
    _ws_cfg = _resolve_ws_cfg(config, db_enabled=_evaluation_db is not None)

    # Resolve failure skip config (FS5.1) -- opt-in exact-key enforce only
    from cst_optimization.evaluation.failure_skip_candidates import (
        resolve_failure_skip_config as _resolve_fs_cfg,
    )
    _failure_skip_cfg = _resolve_fs_cfg(config)
    _failure_skip_db_path = None
    if _failure_skip_cfg.enabled and _evaluation_db_cfg and _evaluation_db_cfg.enabled and _evaluation_db_cfg.path:
        _failure_skip_db_path = str(_evaluation_db_cfg.path)

    def _handle_sr_reuse(reuse_result, x_phys):
        """Process a success reuse hit: compute penalty, checkpoint, DB write."""
        # Compute penalties from reuse result
        if reuse_result.penalty_values:
            penalties_arr = np.array(
                [reuse_result.penalty_values.get(n, 1.0) for n in metric_names],
                dtype=float,
            )
        else:
            penalties_arr = np.full(len(metric_names), 1.0, dtype=float)
        scalar = float(np.dot(penalties_arr, weights))

        # Checkpoint
        if checkpoint_callback is not None:
            raw_arr = np.array(
                [reuse_result.raw_metrics.get(n, np.nan) if reuse_result.raw_metrics else np.nan
                 for n in metric_names],
                dtype=float,
            )
            checkpoint_callback(x_phys, raw_arr, penalties_arr, True, "")

        # DB write with reuse provenance
        if _evaluation_db is not None:
            pid = ParameterIdentity(
                param_names=list(param_names), values=list(x_phys),
            )
            from cst_optimization.evaluation.retry_runtime_cst import build_record_from_evaluation_result
            rec = build_record_from_evaluation_result(
                pid, reuse_result,
                source="db_success_reuse",
                penalty_values=dict(reuse_result.penalty_values) if reuse_result.penalty_values else None,
            )
            _write_eval_db(rec)

        return scalar

    # ---------------------------------------------------------------
    # SAO evaluator wrapper
    # ---------------------------------------------------------------
    opt_cfg = config.get("optimization", {})
    weights = _resolve_named_weights(opt_cfg.get("objective_weights", None), metric_names)

    def evaluator(x_phys: np.ndarray, _it=[0]) -> float:
        iteration = int(_it[0])
        _it[0] += 1

        # FS5.1: failure skip check before any retry/evaluator call
        if _failure_skip_db_path is not None and _failure_skip_cfg.enabled:
            from cst_optimization.evaluation.failure_skip_enforce import run_failure_skip_evaluator
            _fs_pid = ParameterIdentity(param_names=list(param_names), values=list(x_phys))
            _fs_key = _fs_pid.parameter_key()
            _fs_result = run_failure_skip_evaluator(
                _failure_skip_db_path, _fs_key, _failure_skip_cfg,
                lambda pk: None,  # dummy evaluator (never called on hit)
                param_names=list(param_names), param_values=list(x_phys),
                write_synthetic_row=True,
            )
            if _fs_result.enforced_skip:
                _logger.info(
                    "Failure skip enforced for key=%s evidence=%d row=%s",
                    _fs_key[:16], _fs_result.diagnostics.get("evidence_count", 0),
                    _fs_result.synthetic_row_id,
                )
                # Return penalty-based scalar matching fallback behavior
                penalties_arr = np.full(len(metric_names), 1.0, dtype=float)
                return float(np.dot(penalties_arr, weights))

        if retry_handler is not None:
            # SR3 success reuse check before legacy retry path
            if _sr_cfg.enabled:
                reuse_result = _try_sr_reuse(x_phys)
                if reuse_result is not None:
                    return _handle_sr_reuse(reuse_result, x_phys)
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

            # Write final DB record for legacy retry path
            if _evaluation_db is not None:
                _pid_legacy = ParameterIdentity(
                    param_names=list(param_names), values=list(x_phys),
                )
                _ev_legacy = EvaluationResult(
                    status=result.status, error=result.error,
                    raw_metrics=dict(result.raw_metrics) if result.raw_metrics else {},
                    objective_values=dict(result.objective_values) if result.objective_values else {},
                    penalty_values=dict(result.penalty_values) if result.penalty_values else {},
                )
                _write_eval_db(build_record_from_evaluation_result(
                    _pid_legacy, _ev_legacy,
                    penalty_values=dict(_ev_legacy.penalty_values) if _ev_legacy.penalty_values else None,
                ))
            return float(np.dot(penalties_arr, weights))

        # --- Retry runtime path (RW3) ---
        if _retry_runtime_cfg is not None and _retry_runtime_cfg.enabled:
            # SR3 success reuse check before retry runtime path
            if _sr_cfg.enabled:
                reuse_result = _try_sr_reuse(x_phys)
                if reuse_result is not None:
                    return _handle_sr_reuse(reuse_result, x_phys)
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
                # No retry needed 锟?use directly
                penalties_arr = np.array(
                    [pen.get(n, 1.0) for n in metric_names], dtype=float,
                )
                if checkpoint_callback is not None:
                    raw_arr = np.array(
                        [raw.get(n, np.nan) for n in metric_names], dtype=float,
                    )
                    checkpoint_callback(x_phys, raw_arr, penalties_arr, ok, err)
                # Write final DB record for initial-success path
                if _evaluation_db is not None and status == _ES.SUCCESS:
                    _pid_rec = ParameterIdentity(param_names=list(param_names), values=list(x_phys))
                    _ev_res = EvaluationResult(
                        status=status, error=err,
                        raw_metrics=dict(raw),
                        objective_values={n: raw.get(n, np.nan) for n in metric_names},
                        penalty_values=dict(pen),
                    )
                    _write_eval_db(build_record_from_evaluation_result(
                        _pid_rec, _ev_res,
                        penalty_values=dict(pen) if pen else None,
                    ))
                return float(np.dot(penalties_arr, weights))

            # Initial evaluation failed -- build record and consider retry
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

            # RCR3 synthetic tier-2 recovery smoke: inject a second
            # synthetic failure on the first retry attempt so that
            # the recovery callback is exercised at tier 2.  Only
            # fires once and only when explicitly enabled.
            if _tier2_smoke_enabled and not _tier2_smoke_consumed[0]:
                _tier2_smoke_consumed[0] = True
                _real_evaluate_once = evaluate_once

                def _tier2_smoke_evaluate_once(tier, record):
                    _logger.info(
                        "RCR3 tier-2 smoke: injecting synthetic SOLVER_FAILED "
                        "for retry attempt (tier=%d)", tier,
                    )
                    # Return a synthetic SOLVER_FAILED record that preserves
                    # parameter identity and advances retry_count.
                    syn_rec = EvaluationDatabaseRecord(
                        parameter_identity=record.parameter_identity,
                        status=_EDS.SOLVER_FAILED,
                        retry_count=record.retry_count + 1,
                        error_taxonomy={
                            "original_error": "RCR3 tier-2 synthetic failure",
                            "original_status": "solver_failed",
                        },
                    )
                    return syn_rec

                # Return the synthetic failure for the first call,
                # then delegate to the real adapter for all subsequent calls.
                _tier2_call_count = [0]

                def _wrapped_evaluate_once(tier, record):
                    if _tier2_call_count[0] == 0:
                        _tier2_call_count[0] += 1
                        return _tier2_smoke_evaluate_once(tier, record)
                    return _real_evaluate_once(tier, record)

                evaluate_once = _wrapped_evaluate_once
                _logger.info("RCR3 tier-2 recovery smoke: wrapped evaluate_once")
            retry_result = run_retry_loop_no_cst(
                initial_record=initial_record,
                evaluate_once=evaluate_once,
                config=_retry_runtime_cfg,
                current_schema=current_schema_version(),
                recovery_callback=_retry_runtime_recovery,
            )

            # Use final result 鈥?extract penalty or fall back to all-ones
            fr = retry_result.final_record
            pen_arr = _extract_retry_penalty_values(fr, metric_names) if retry_result.succeeded else None
            if pen_arr is not None:
                penalties_arr = pen_arr
                ok = True
                err = ""
            else:
                penalties_arr = np.full(len(metric_names), 1.0, dtype=float)
                ok = False
            # Checkpoint records final result only (never intermediate attempts)
            if checkpoint_callback is not None:
                cp_args = _build_retry_runtime_checkpoint_payload(
                    fr, x_phys, metric_names, penalties_arr, ok, err,
                )
                checkpoint_callback(*cp_args)

            # Write final DB record from retry runtime final_record
            if _evaluation_db is not None and fr is not None:
                _write_eval_db(fr)
            return float(np.dot(penalties_arr, weights))

        # --- Plain single_pass path (no retry) ---
        # SR3 success reuse check before plain CST eval
        if _sr_cfg.enabled:
            reuse_result = _try_sr_reuse(x_phys)
            if reuse_result is not None:
                return _handle_sr_reuse(reuse_result, x_phys)
        raw, pen, ok, status, err = wf1_evaluator.evaluate_single_pass(
            dict(zip(param_names, x_phys)), iteration,
        )
        penalties_arr = np.array([pen.get(n, 1.0) for n in metric_names], dtype=float)
        if checkpoint_callback is not None:
            raw_arr = np.array([raw.get(n, np.nan) for n in metric_names], dtype=float)
            checkpoint_callback(x_phys, raw_arr, penalties_arr, ok, err)
        # Write final DB record for plain single_pass path
        if _evaluation_db is not None:
            _pid_plain = ParameterIdentity(param_names=list(param_names), values=list(x_phys))
            _ev_plain = EvaluationResult(
                status=status, error=err,
                raw_metrics=dict(raw),
                objective_values={n: raw.get(n, np.nan) for n in metric_names},
                penalty_values=dict(pen),
            )
            _write_eval_db(build_record_from_evaluation_result(
                _pid_plain, _ev_plain,
                penalty_values=dict(pen) if pen else None,
            ))
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
    workflow._retry_connection_registry = _retry_runtime_registry
    workflow._evaluation_db = _evaluation_db
    workflow._db_warm_start_cfg = _ws_cfg
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
# Local helpers (WF1-specific)
# ---------------------------------------------------------------------------


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

