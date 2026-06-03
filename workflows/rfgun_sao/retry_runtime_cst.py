# CST adapter for the retry runtime (no-CST testable).
# Provides mappers, record builders, and evaluate_once factory
# that bridge between the CST evaluation pipeline and the
# no-CST retry loop (retry_runtime.py / retry_taxonomy.py).
#
# No CST imports at module level.  CST objects are injected or
# duck-typed.  Fully testable with fake evaluators.
#
# Phase RW2 — no-CST adapter implementation.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from workflows.rfgun_sao.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
)
from workflows.rfgun_sao.retry_runtime import (
    RetryRuntimeConfig,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


def map_evaluation_status_to_database_status(
    status: EvaluationStatus,
) -> str:
    """Map a legacy ``EvaluationStatus`` to an ``EvaluationDatabaseStatus`` string.

    The mapping drives retry eligibility classification:

    - ``SUCCESS`` -> ``SUCCESS`` (no retry).
    - ``COM_LOST`` -> ``TRANSIENT_FAILED`` (encourage retry; connection
      loss is transient by nature).
    - ``SOLVER_FAILED`` -> ``SOLVER_FAILED`` (retry eligible under
      default policy).
    - ``PHYSICS_INVALID`` -> ``SOLVER_FAILED`` (treated as solver failure).
    - ``UNKNOWN_ERROR`` -> ``UNKNOWN_FAILED`` (retry eligible if
      ``allow_unknown_retry`` is True, which is the default).

    Calibration-specific statuses (``CALIBRATION_FAILED``,
    ``GATE_REJECTED``) are not produced here — they belong in the
    two-pass calibration path which uses a separate runner.
    """
    _map: dict[EvaluationStatus, str] = {
        EvaluationStatus.SUCCESS: EvaluationDatabaseStatus.SUCCESS,
        EvaluationStatus.COM_LOST: EvaluationDatabaseStatus.TRANSIENT_FAILED,
        EvaluationStatus.SOLVER_FAILED: EvaluationDatabaseStatus.SOLVER_FAILED,
        EvaluationStatus.PHYSICS_INVALID: EvaluationDatabaseStatus.SOLVER_FAILED,
        EvaluationStatus.UNKNOWN_ERROR: EvaluationDatabaseStatus.UNKNOWN_FAILED,
    }
    return _map.get(status, EvaluationDatabaseStatus.UNKNOWN_FAILED)


# ---------------------------------------------------------------------------
# Record builder
# ---------------------------------------------------------------------------


def build_record_from_evaluation_result(
    parameter_identity: ParameterIdentity | None,
    result: EvaluationResult,
    *,
    schema_version: int = 1,
    source: str = "retry_runtime_cst",
    retry_count: int = 0,
) -> EvaluationDatabaseRecord:
    """Build an ``EvaluationDatabaseRecord`` from an ``EvaluationResult``.

    Parameters
    ----------
    parameter_identity : ParameterIdentity or None
        Identity of the evaluated parameter vector.
    result : EvaluationResult
        Structured evaluation result from the CST evaluator.
    schema_version : int
        Evaluation database schema version.
    source : str
        Source identifier.
    retry_count : int
        Number of retry attempts already consumed.

    Returns
    -------
    EvaluationDatabaseRecord
        Ready for ``classify_retry_eligibility()``.
    """
    from workflows.rfgun_sao.evaluation_database_schema import (
        RawEvaluationPayload,
    )

    db_status = map_evaluation_status_to_database_status(result.status)

    payload = RawEvaluationPayload(
        raw_metrics=dict(result.raw_metrics) if result.raw_metrics else None,
        objective_values=(
            dict(result.objective_values) if result.objective_values else None
        ),
        diagnostics=dict(result.diagnostics) if result.diagnostics else None,
    )

    return EvaluationDatabaseRecord(
        parameter_identity=parameter_identity,
        status=db_status,
        raw_payload=payload,
        objective_names=(
            list(result.objective_values.keys()) if result.objective_values else None
        ),
        source=source,
        schema_version=schema_version,
        retry_count=retry_count,
        error_taxonomy={
            "original_error": result.error,
            "original_status": result.status.value,
        } if result.error else None,
    )


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def make_cst_retry_evaluate_once(
    evaluator: Any,
    *,
    param_names: list[str] | None = None,
    recovery_callback: Callable[[int, EvaluationDatabaseRecord], bool] | None = None,
) -> Callable[[int, EvaluationDatabaseRecord], EvaluationDatabaseRecord]:
    """Create a CST-backed ``evaluate_once`` callback.

    The returned callback is compatible with
    ``retry_runtime.run_retry_loop_no_cst()``.

    Parameters
    ----------
    evaluator :
        An object duck-typed to ``Workflow1Evaluator``.  Must provide
        ``adapt_for_retry(params, iteration) -> EvaluationResult``.
        In tests, any object with that method works.
    param_names : list[str] or None
        Ordered parameter names matching the evaluator's expectations.
        If ``None``, attempts to extract from the ``EvaluationDatabaseRecord``
        passed to each ``evaluate_once`` call.
    recovery_callback : callable or None
        ``recovery_callback(tier, record) -> bool``.  Called before each
        retry evaluation.  If ``None``, the retry loop's own
        ``recovery_callback`` parameter is used instead.

    Returns
    -------
    Callable
        ``fn(tier, record) -> EvaluationDatabaseRecord``
    """
    def _evaluate_once(
        tier: int,
        record: EvaluationDatabaseRecord,
    ) -> EvaluationDatabaseRecord:
        """Evaluate one retry attempt and return a result record."""
        pid = record.parameter_identity

        # Build parameter vector from the record's identity
        if param_names is not None and pid is not None:
            param_dict = dict(zip(param_names, pid.values))
            params = list(pid.values)
        elif pid is not None:
            params = list(pid.values)
            param_dict = dict(zip(pid.param_names, params))
        else:
            # No identity — use empty params; will likely produce an error
            params = []
            param_dict = {}

        # Call the evaluator
        # The iteration counter is not meaningful for retry attempts;
        # we use a placeholder (-1) to distinguish retries from
        # initial evaluations.
        result = evaluator.adapt_for_retry(
            __import__("numpy").asarray(params), -1,
        )

        # Build the database record from the result
        next_retry_count = record.retry_count + 1
        db_record = build_record_from_evaluation_result(
            parameter_identity=pid,
            result=result,
            retry_count=next_retry_count,
        )

        return db_record

    return _evaluate_once


# ---------------------------------------------------------------------------
# Legacy retry mutex check
# ---------------------------------------------------------------------------


def check_legacy_retry_mutex(
    config: dict | None,
    *,
    logger: Any = None,
) -> tuple[RetryRuntimeConfig, str | None]:
    """Check if legacy retry conflicts with new retry runtime.

    If ``config`` has both ``optimization.retry.enabled=True`` AND
    ``retry_runtime.enabled=True``, the new retry runtime is disabled
    to prevent silent double retry.  A diagnostic message is returned.

    Parameters
    ----------
    config : dict or None
        The full workflow configuration dict.
    logger : logging.Logger or None
        Optional logger for the warning message.

    Returns
    -------
    tuple[RetryRuntimeConfig, str | None]
        ``(retry_runtime_config, diagnostic_message)``.
        If mutex triggers, the config is returned as disabled
        (``RetryRuntimeConfig()``) and the message describes why.
        If no conflict, the resolved config is returned with
        ``message=None``.
    """
    if config is None:
        return RetryRuntimeConfig(), None

    # Resolve the retry runtime config
    retry_raw = config.get("retry_runtime", None)
    if retry_raw is None:
        # No retry_runtime section at all → disabled by default
        return RetryRuntimeConfig(), None

    runtime_cfg = __import__(
        "workflows.rfgun_sao.retry_runtime",
        fromlist=["resolve_retry_runtime_config"],
    ).resolve_retry_runtime_config({"retry": retry_raw})

    if not runtime_cfg.enabled:
        return runtime_cfg, None

    # Check legacy retry
    legacy_raw = config.get("optimization", {}).get("retry", None)
    legacy_enabled = bool(
        legacy_raw.get("enabled", True) if isinstance(legacy_raw, dict) else False
    )

    if legacy_enabled:
        msg = (
            "retry_runtime.enabled=True but legacy optimization.retry.enabled=True. "
            "Disabling retry_runtime to prevent double retry. "
            "Set optimization.retry.enabled=false to use retry_runtime."
        )
        if logger is not None:
            logger.warning(msg)
        return RetryRuntimeConfig(), msg

    return runtime_cfg, None
