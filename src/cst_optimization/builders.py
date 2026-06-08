"""Config-to-object builders — shared across all workflows.

These functions are the single canonical source for translating YAML
config entries into optimizer parameters, objectives, SAO instances, and
named weight vectors.  Workflow-specific builders live in their respective
``workflows/*/workflow.py`` modules; this module only contains helpers
with stable cross-workflow contracts.

Usage::

    from cst_optimization.builders import (
        _build_parameters,
        _build_objectives,
        _build_sao,
        _resolve_named_weights,
        _build_retry_handler,
    )
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .core.retry import EvaluationRetryHandler, RetryConfig
from .objectives.base import ObjectiveFunction
from .objectives.registry import get_objective, get_mode
from .optimization.acquisition import (
    ExpectedImprovement,
    ProbabilityOfImprovement,
    UpperConfidenceBound,
)
from .optimization.sao import SurrogateAssistedOptimizer
from .parameters.base import ParameterSet, ParamRange
from .parameters.geometry import GeometryParameter
from .workflows.recovery import MetricSpec

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter builders
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


# ---------------------------------------------------------------------------
# Objective builders
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Optimizer builders
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Metric / weight builders
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Retry handler builder
# ---------------------------------------------------------------------------


def _build_retry_handler(
    connection: Any,
    project_path: str,
    library_path: str,
    retry_cfg_raw: dict[str, Any] | None,
    config: dict[str, Any],
    extra_result_paths: list[str] | None = None,
) -> Any | None:
    """Build an ``EvaluationRetryHandler`` from workflow-2 config."""
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
