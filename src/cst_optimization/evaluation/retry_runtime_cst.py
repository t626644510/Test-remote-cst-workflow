# CST adapter for the retry runtime (no-CST testable).
# Provides mappers, record builders, and evaluate_once factory
# that bridge between the CST evaluation pipeline and the
# no-CST retry loop (retry_runtime.py / retry_taxonomy.py).
#
# No CST imports at module level.  CST objects are injected or
# duck-typed.  Fully testable with fake evaluators.
#
# Phase RW2 鈥?no-CST adapter implementation.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
)
from cst_optimization.evaluation.retry_runtime import (
    RetryRuntimeConfig,
    resolve_retry_runtime_config,
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
    ``GATE_REJECTED``) are not produced here 鈥?they belong in the
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
    penalty_values: dict[str, float] | None = None,
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
    penalty_values : dict[str, float] or None
        Per-metric penalty values.  Stored in ``raw_payload.diagnostics``
        under ``"__retry_penalty__"`` for extraction by the evaluator
        closure after the retry loop.

    Returns
    -------
    EvaluationDatabaseRecord
        Ready for ``classify_retry_eligibility()``.
    """
    from cst_optimization.evaluation.evaluation_database_schema import (
        RawEvaluationPayload,
    )

    db_status = map_evaluation_status_to_database_status(result.status)

    diag = dict(result.diagnostics) if result.diagnostics else {}
    if penalty_values is not None:
        diag["__retry_penalty__"] = dict(penalty_values)

    payload = RawEvaluationPayload(
        raw_metrics=dict(result.raw_metrics) if result.raw_metrics else None,
        objective_values=(
            dict(result.objective_values) if result.objective_values else None
        ),
        diagnostics=diag if diag else None,
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
) -> Callable[[int, EvaluationDatabaseRecord], EvaluationDatabaseRecord]:
    """Create a CST-backed ``evaluate_once`` callback.

    The returned callback is compatible with
    ``retry_runtime.run_retry_loop_no_cst()``.  It owns only the
    single-attempt evaluation 鈥?recovery callback and retry-loop
    orchestration are supplied separately to
    ``run_retry_loop_no_cst()``.

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
        if pid is not None:
            params = list(pid.values)
        else:
            params = []

        # Call the evaluator.
        # The iteration counter is not meaningful for retry attempts;
        # we use a placeholder (-1) to distinguish retries from
        # initial evaluations.
        result = evaluator.adapt_for_retry(
            np.asarray(params), -1,
        )

        # Build the database record from the result,
        # including penalty_values so the evaluator closure can
        # extract them from diagnostics after the retry loop.
        next_retry_count = record.retry_count + 1
        penalty_values = (
            dict(result.penalty_values) if result.penalty_values else None
        )
        db_record = build_record_from_evaluation_result(
            parameter_identity=pid,
            result=result,
            retry_count=next_retry_count,
            penalty_values=penalty_values,
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
        # No retry_runtime section at all 鈫?disabled by default
        return RetryRuntimeConfig(), None

    runtime_cfg = resolve_retry_runtime_config({"retry": retry_raw})

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


# ---------------------------------------------------------------------------
# Connection registry (RCR2, no-CST)
# ---------------------------------------------------------------------------


@dataclass
class CstConnectionRegistry:
    """Tracks CST connections created by the retry runtime recovery.

    No CST imports at module level.  Connections are duck-typed and
    must provide ``close(force=False)``.  Fully no-CST testable.
    """
    _connections: list[Any] = field(default_factory=list)

    def track(self, conn: Any) -> None:
        """Add a connection for lifecycle tracking."""
        self._connections.append(conn)

    @property
    def tracked_count(self) -> int:
        return len(self._connections)

    def close_all(self, force: bool = True) -> dict[str, Any]:
        """Close all tracked connections, best-effort.

        Iterates every tracked connection, calling ``close(force=force)``.
        Exceptions are captured in the diagnostics.  Registry is cleared
        after all close attempts.

        Returns dict with keys ``attempted``, ``closed_ok``, ``errors``.
        """
        diag: dict[str, Any] = {
            "attempted": len(self._connections),
            "closed_ok": 0,
            "errors": [],
        }
        for idx, conn in enumerate(self._connections):
            try:
                conn.close(force=force)
                diag["closed_ok"] += 1
            except Exception as exc:
                diag["errors"].append((idx, str(exc)[:200]))
        self._connections.clear()
        return diag


# ---------------------------------------------------------------------------
# Recovery callback factory (RCR2, no-CST)
# ---------------------------------------------------------------------------


def make_cst_recovery_callback(
    connection_factory: Callable[[], Any],
    evaluator: Any,
    registry: CstConnectionRegistry,
    *,
    logger: Any = None,
) -> Callable[[int, Any], bool]:
    """Create a recovery callback compatible with ``run_retry_loop_no_cst``.

    Tier 1: no-op (returns True, no new connection).
    Tier 2+: close old connections via registry, create new via factory,
             update evaluator, track in registry.

    Parameters
    ----------
    connection_factory : callable
        Zero-argument callable returning a new connection.
    evaluator : Workflow1Evaluator-like
        Must provide ``on_reconnect(new_conn)``.
    registry : CstConnectionRegistry
        Dedicated retry-runtime connection registry.
    logger : logging.Logger or None

    Returns
    -------
    callable ``fn(tier, record) -> bool``
    """
    def _recovery_callback(tier: int, record: Any) -> bool:
        if tier < 2:
            return True

        try:
            registry.close_all(force=True)
            new_conn = connection_factory()
            # Track immediately after factory so there is never an
            # untracked replacement.  If on_reconnect fails, we close
            # the tracked new connection via close_all.
            registry.track(new_conn)
            try:
                evaluator.on_reconnect(new_conn)
            except Exception:
                # on_reconnect failed 鈥?close the tracked new connection
                # and propagate the exception upward.
                registry.close_all(force=True)
                raise
            if logger is not None:
                pid = getattr(new_conn, "pid", "?")
                logger.info("RCR recovery: reconnected (tier=%d, PID=%s)", tier, pid)
            return True
        except Exception as exc:
            if logger is not None:
                logger.warning("RCR recovery failed (tier=%d): %s", tier, exc)
            return False

    return _recovery_callback

