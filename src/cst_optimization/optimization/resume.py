"""Load prior evaluation data from JSONL records for warm-continuation.

When resuming a workflow from a previous run, the GP surrogate should
start with as much prior knowledge as possible — not just the single
best point (warm_start) but ALL successful evaluations.

This module provides ``load_prior_data_from_jsonl`` which reads an
``evaluation_records.jsonl`` file and returns ``PriorData``: the
parameter vectors and penalty values for every successful evaluation.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import numpy as np

_logger = logging.getLogger(__name__)


@dataclass
class PriorData:
    """Pre-loaded evaluation data from a previous optimisation run.

    Attributes
    ----------
    x_phys : np.ndarray
        Shape ``(N, D)`` — physical-space parameter vectors.
    y_raw : np.ndarray
        Shape ``(N,)`` for SAO (scalar penalties) or ``(N, M)`` for SAEA.
    best_idx : int
        Index of the point with the lowest penalty sum.
    parameter_names : list[str]
        Names in the same order as *x_phys* columns.
    metric_names : list[str]
        Names in the same order as *y_raw* columns (for SAEA) or the
        names used in the weighted penalty sum (for SAO).
    """

    x_phys: np.ndarray
    y_raw: np.ndarray
    best_idx: int = 0
    parameter_names: list[str] = field(default_factory=list)
    metric_names: list[str] = field(default_factory=list)

    @property
    def n_points(self) -> int:
        return len(self.x_phys)

    @property
    def x_best(self) -> np.ndarray:
        return self.x_phys[self.best_idx].copy()

    @property
    def y_best(self) -> np.ndarray | float:
        return self.y_raw[self.best_idx].copy() if self.y_raw.ndim > 1 else float(self.y_raw[self.best_idx])


def load_prior_data_from_jsonl(
    jsonl_path: str,
    parameter_names: list[str],
    metric_names: list[str] | None = None,
    weights: np.ndarray | None = None,
) -> PriorData:
    """Load all successful evaluations from a JSONL record file.

    Parameters
    ----------
    jsonl_path : str
        Path to ``evaluation_records.jsonl``.
    parameter_names : list[str]
        Ordered parameter names matching the optimiser's parameter set.
    metric_names : list[str] or None
        Ordered objective/metric names whose penalty values to sum.
        If ``None``, all keys in ``penalty_values`` are used, sorted
        alphabetically.
    weights : np.ndarray or None
        Weight vector for scalarising multi-objective penalties into a
        single ``y_raw`` column for SAO.  If ``None`` and *metric_names*
        is provided, equal weights are used.  For SAEA (multi-objective)
        pass ``weights=None`` and handle *metric_names* downstream.

    Returns
    -------
    PriorData
        ``x_phys`` in physical space (same order as *parameter_names*),
        ``y_raw`` as a scalar penalty sum (SAO) or multi-column (SAEA).
    """
    records: list[dict] = []

    # Accept a directory path (look for evaluation_records.jsonl inside)
    if os.path.isdir(jsonl_path):
        jsonl_path = os.path.join(jsonl_path, "evaluation_records.jsonl")

    with open(jsonl_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                _logger.warning("Skipping malformed JSON line in %s", jsonl_path)
                continue

            status = rec.get("status", "")
            solver_ok = bool(rec.get("solver_ok", False))
            if status != "success" or not solver_ok:
                continue

            params = rec.get("parameters")
            penalties = rec.get("penalty_values")
            if not params or not penalties:
                continue

            records.append(rec)

    if not records:
        _logger.warning("No successful evaluations found in %s", jsonl_path)
        return PriorData(
            x_phys=np.empty((0, len(parameter_names))),
            y_raw=np.empty(0),
        )

    # Build parameter matrix
    n_dims = len(parameter_names)
    x_list = []
    for rec in records:
        params = rec["parameters"]
        row = [float(params.get(name, np.nan)) for name in parameter_names]
        x_list.append(row)
    x_phys = np.array(x_list, dtype=float)

    # Build y (penalty) matrix
    penalties_all = [rec["penalty_values"] for rec in records]

    if metric_names is None:
        # Collect all unique metric names across all records
        all_keys = set()
        for p in penalties_all:
            all_keys.update(p.keys())
        metric_names = sorted(all_keys)

    if weights is not None and len(weights) == len(metric_names):
        w = np.asarray(weights, dtype=float)
        w = w / np.sum(w)
        y_raw = np.array([
            sum(
                float(penalties.get(name, 1.0)) * w[i]
                for i, name in enumerate(metric_names)
            )
            for penalties in penalties_all
        ], dtype=float)
    else:
        # Multi-objective: return per-metric penalty values
        y_raw = np.array([
            [float(penalties.get(name, 1.0)) for name in metric_names]
            for penalties in penalties_all
        ], dtype=float)

    best_idx = int(np.argmin(y_raw if y_raw.ndim == 1 else np.sum(y_raw, axis=1)))

    _logger.info(
        "Loaded %d prior evaluations from %s (best idx=%d)",
        len(records), jsonl_path, best_idx,
    )

    return PriorData(
        x_phys=x_phys,
        y_raw=y_raw,
        best_idx=best_idx,
        parameter_names=list(parameter_names),
        metric_names=list(metric_names),
    )


def load_best_point_from_jsonl(
    jsonl_path: str,
    parameter_names: list[str],
) -> np.ndarray | None:
    """Convenience: return just the best point's physical parameter vector.

    Returns ``None`` if no successful records are found.
    """
    data = load_prior_data_from_jsonl(jsonl_path, parameter_names)
    if data.n_points == 0:
        return None
    return data.x_best
