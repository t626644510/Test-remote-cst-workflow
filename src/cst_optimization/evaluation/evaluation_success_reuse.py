# DB-backed success reuse lookup helper (no-CST).
# Read-only helper for finding eligible SUCCESS records and
# reconstructing EvaluationResult from DB rows.
# No runtime skip, no workflow integration.
#
# Phase SR2 -no-CST lookup implementation.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
    current_schema_version,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class SuccessReuseConfig:
    """Configuration for DB-backed success reuse.

    Parameters
    ----------
    enabled : bool
        Master switch.
    require_objective_values : bool
        If True, only rows with non-null objective_values are eligible.
    allow_raw_recompute : bool
        If True, recompute penalties from raw_metrics when objective_values
        is missing (not yet implemented in SR2).
    max_age_days : int or None
        Optional age-based rejection.
    log_decisions : bool
        Whether to log each reuse decision.
    """
    enabled: bool = False
    require_objective_values: bool = True
    allow_raw_recompute: bool = False
    max_age_days: int | None = None
    log_decisions: bool = True


def resolve_success_reuse_config(config: dict | None, *, db_enabled: bool = False) -> SuccessReuseConfig:
    """Resolve success reuse config from a workflow config dict.

    Parameters
    ----------
    config : dict or None
        Full workflow configuration.
    db_enabled : bool
        Whether the evaluation database is enabled (from pre-resolved config).

    Returns
    -------
    SuccessReuseConfig
        Resolved config.  ``enabled=False`` when section absent or disabled.

    Raises
    ------
    ValueError
        If ``success_reuse.enabled=True`` but *db_enabled* is False.
    """
    if config is None:
        return SuccessReuseConfig()

    raw = config.get("success_reuse", None)
    if raw is None:
        return SuccessReuseConfig()

    enabled = bool(raw.get("enabled", False))
    if not enabled:
        return SuccessReuseConfig()

    if not db_enabled:
        raise ValueError(
            "success_reuse.enabled=True requires evaluation_database.enabled=True. "
            "Enable the evaluation database first.",
        )

    max_age_days = raw.get("max_age_days", None)
    if max_age_days is not None:
        raise ValueError(
            "max_age_days is not supported in SR2. "
            "Set max_age_days to null or remove it.",
        )

    return SuccessReuseConfig(
        enabled=True,
        require_objective_values=bool(raw.get("require_objective_values", True)),
        allow_raw_recompute=bool(raw.get("allow_raw_recompute", False)),
        max_age_days=None,
        log_decisions=bool(raw.get("log_decisions", True)),
    )


# ---------------------------------------------------------------------------
# Lookup helper
# ---------------------------------------------------------------------------


def _names_match(db_param_names: Any, current_names: list[str]) -> bool:
    """Check that parameter names stored in DB match current names."""
    if db_param_names is None:
        return False
    if isinstance(db_param_names, str):
        try:
            db_param_names = json.loads(db_param_names)
        except (json.JSONDecodeError, TypeError):
            return False
    if not isinstance(db_param_names, (list, tuple)):
        return False
    return list(db_param_names) == current_names


def _objective_names_match(db_obj_names: Any, current_metric_names: list[str]) -> bool:
    """Check that objective_names stored in DB match current metric names."""
    if db_obj_names is None:
        return False
    if isinstance(db_obj_names, str):
        try:
            db_obj_names = json.loads(db_obj_names)
        except (json.JSONDecodeError, TypeError):
            return False
    if not isinstance(db_obj_names, (list, tuple)):
        return False
    return list(db_obj_names) == current_metric_names


def find_eligible_success_record(
    db: Any,
    parameter_identity: ParameterIdentity | None,
    metric_names: list[str],
    config: SuccessReuseConfig,
    *,
    current_schema: int | None = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """Find an eligible SUCCESS record for a parameter identity.

    Parameters
    ----------
    db :
        An object duck-typed to ``SQLiteEvaluationDatabase``.  Must provide
        ``query_by_parameter_key(parameter_key) -> list[dict]``.
    parameter_identity : ParameterIdentity or None
        The identity to look up.
    metric_names : list[str]
        Current ordered metric names.
    config : SuccessReuseConfig
        Resolved reuse configuration.
    current_schema : int or None
        Expected schema version.  Defaults to ``current_schema_version()``.
    logger : logging.Logger or None
        Optional logger.

    Returns
    -------
    dict or None
        The selected DB row, or ``None`` if no eligible record found.
    """
    log = logger or _logger

    if not config.enabled:
        return None

    if parameter_identity is None:
        return None

    if current_schema is None:
        current_schema = current_schema_version()

    # Query DB
    key = parameter_identity.parameter_key()
    try:
        rows = db.query_by_parameter_key(key)
    except Exception as exc:
        log.warning("Success reuse query failed: %s", exc)
        return None

    if not rows:
        return None

    # Filter and select the best eligible row
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if not _is_row_eligible(
            row, parameter_identity, metric_names, config, current_schema, log,
        ):
            continue
        eligible.append(row)

    if not eligible:
        return None

    # Tie-breaking: newest created_at, then highest id
    def _sort_key(r: dict[str, Any]) -> tuple:
        return (r.get("created_at", "") or "", r.get("id", 0) or 0)

    eligible.sort(key=_sort_key, reverse=True)
    chosen = eligible[0]

    if config.log_decisions:
        log.info(
            "Success reuse: found eligible row (id=%s, run_id=%s, created_at=%s, key=%s)",
            chosen.get("id"), chosen.get("run_id"), chosen.get("created_at"),
            key[:8],
        )

    return chosen


def _is_row_eligible(
    row: dict[str, Any],
    parameter_identity: ParameterIdentity,
    metric_names: list[str],
    config: SuccessReuseConfig,
    current_schema: int,
    logger: Any,
) -> bool:
    """Check a single DB row for success reuse eligibility."""
    # Status must be SUCCESS
    status = row.get("status", "")
    if str(status).strip().lower() != EvaluationDatabaseStatus.SUCCESS:
        return False

    # Schema version compatibility
    row_schema = row.get("schema_version")
    if row_schema is None or int(row_schema) != current_schema:
        return False

    # Parameter names must match
    param_names = row.get("param_names")
    if not _names_match(param_names, parameter_identity.param_names):
        return False

    # Objective names must match current metric names
    obj_names = row.get("objective_names")
    if not _objective_names_match(obj_names, metric_names):
        return False

    # Payload validation: objective_values is always required in SR2.
    # Raw-only rows are never eligible -no safe recompute helper exists.
    objective_values = row.get("objective_values")
    if objective_values is None:
        return False
    if isinstance(objective_values, str):
        try:
            objective_values = json.loads(objective_values)
        except (json.JSONDecodeError, TypeError):
            return False
    if not isinstance(objective_values, dict) or len(objective_values) == 0:
        return False

    # Max age check is not implemented in SR2 -raise if set.
    if config.max_age_days is not None:
        raise ValueError(
            "max_age_days is not supported in SR2. "
            "Set max_age_days to null or remove it.",
        )

    return True


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


def reconstruct_evaluation_result(
    row: dict[str, Any],
    metric_names: list[str],
    *,
    config: SuccessReuseConfig | None = None,
    logger: Any = None,
) -> EvaluationResult | None:
    """Reconstruct an ``EvaluationResult`` from a DB row for reuse.

    Parameters
    ----------
    row : dict
        A DB row from ``query_by_parameter_key`` (decoded by ``_row_to_dict``).
    metric_names : list[str]
        Current ordered metric names.
    config : SuccessReuseConfig or None
        Resolved reuse configuration.
    logger : logging.Logger or None
        Optional logger.

    Returns
    -------
    EvaluationResult or None
        Reconstructed result, or ``None`` if the row cannot be used.
    """
    log = logger or _logger

    raw_metrics_raw = row.get("raw_metrics")
    objective_values_raw = row.get("objective_values")
    diagnostics_raw = row.get("diagnostics")

    # Parse JSON strings to dicts
    raw_metrics: dict[str, float] = {}
    if raw_metrics_raw is not None:
        if isinstance(raw_metrics_raw, str):
            try:
                raw_metrics = json.loads(raw_metrics_raw)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(raw_metrics_raw, dict):
            raw_metrics = raw_metrics_raw

    # Parse objective_values; if missing or empty, return None (SR2 policy)
    objective_values: dict[str, float] = {}
    if objective_values_raw is not None:
        if isinstance(objective_values_raw, str):
            try:
                objective_values = json.loads(objective_values_raw)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(objective_values_raw, dict):
            objective_values = objective_values_raw
    if not objective_values:
        log.warning("Success reuse reconstruction: objective_values missing or empty, returning None")
        return None

    diagnostics: dict[str, Any] = {}
    if diagnostics_raw is not None:
        if isinstance(diagnostics_raw, str):
            try:
                diagnostics = json.loads(diagnostics_raw)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(diagnostics_raw, dict):
            diagnostics = diagnostics_raw

    # Extract penalty values from diagnostics if available
    penalty_values = diagnostics.get("__retry_penalty__", None)

    # If penalty_values is missing, fall back to objective_values only
    # when allow_raw_recompute is explicitly enabled.
    if penalty_values is None:
        cfg_allow = config is not None and config.allow_raw_recompute
        if cfg_allow and objective_values:
            penalty_values = dict(objective_values)
        else:
            log.warning(
                "Success reuse reconstruction: __retry_penalty__ not found "
                "and allow_raw_recompute=False, returning None",
            )
            return None

    # Add reuse provenance to diagnostics
    reuse_info = {
        "reused_from_db": True,
        "source_row_id": row.get("id"),
        "source_run_id": row.get("run_id"),
        "source_created_at": row.get("created_at"),
    }
    diagnostics.update(reuse_info)

    # Compute f0_ghz from raw metrics
    f0_ghz = float(raw_metrics.get("resonant_freq", float("nan")))

    result = EvaluationResult(
        status=EvaluationStatus.SUCCESS,
        error="",
        f0_ghz=f0_ghz,
        raw_metrics=raw_metrics,
        objective_values=objective_values,
        penalty_values=penalty_values,
        diagnostics=diagnostics,
    )
    return result


# ---------------------------------------------------------------------------
# Combined lookup + reconstruction for workflow use
# ---------------------------------------------------------------------------


def try_success_reuse(
    db: Any,
    parameter_identity: ParameterIdentity | None,
    metric_names: list[str],
    *,
    config: SuccessReuseConfig | None = None,
    current_schema: int | None = None,
    logger: Any = None,
) -> EvaluationResult | None:
    """Try to reuse a previous SUCCESS result from the evaluation DB.

    Combines ``find_eligible_success_record`` and
    ``reconstruct_evaluation_result`` into one call for workflow
    integration.  Returns ``None`` if no eligible record is found or
    if reconstruction fails.

    Parameters
    ----------
    db :
        Duck-typed ``SQLiteEvaluationDatabase`` (must provide
        ``query_by_parameter_key``).
    parameter_identity : ParameterIdentity or None
        The identity to look up.
    metric_names : list[str]
        Current ordered metric names.
    config : SuccessReuseConfig or None
        Resolved reuse configuration.
    current_schema : int or None
        Expected schema version.
    logger : logging.Logger or None

    Returns
    -------
    EvaluationResult or None
    """
    log = logger or _logger

    if config is None or not config.enabled:
        return None

    row = find_eligible_success_record(
        db, parameter_identity, metric_names, config,
        current_schema=current_schema, logger=log,
    )
    if row is None:
        return None

    result = reconstruct_evaluation_result(
        row, metric_names, config=config, logger=log,
    )
    if result is None:
        return None

    if config.log_decisions:
        log.info(
            "Success reuse: hit (key=%s, row_id=%s, run_id=%s)",
            (parameter_identity.parameter_key()[:8]
             if parameter_identity else "?"),
            row.get("id"), row.get("run_id"),
        )

    return result
