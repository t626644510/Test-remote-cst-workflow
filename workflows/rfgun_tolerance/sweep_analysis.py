"""No-CST tolerance sweep cross-level statistics — TSE3.

Builds on TSE2 sweep dataset and TAM2/TAM3 CV/clean CV summarizers
to produce per-level summaries, metric curves, monotonicity analysis,
and knee-candidate (largest-delta) detection.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Sequence

import numpy as np

from workflows.rfgun_tolerance.statistics import (
    summarize_dataset,
    summarize_dataset_clean,
)
from workflows.rfgun_tolerance.sweep_dataset import (
    ToleranceSweepDataset,
    ToleranceSweepGroup,
)


# ===================================================================
# Data model
# ===================================================================


@dataclasses.dataclass(frozen=True)
class SweepMetricLevelSummary:
    """One metric's statistics at one tolerance level.

    Parameters
    ----------
    tolerance_parameter : str
    tolerance_level_um : float
    tolerance_level_mm : float
    metric_name : str
    accepted_row_count : int
    source_row_count : int
    skipped_row_count : int
    mean : float
    std : float
    min_val : float
    max_val : float
    cv_percent : float
    clean_cv_percent : float
    n_outliers : int
    failure_rate : float
    notes : tuple of str
    """
    tolerance_parameter: str = ""
    tolerance_level_um: float = 0.0
    tolerance_level_mm: float = 0.0
    metric_name: str = ""
    accepted_row_count: int = 0
    source_row_count: int = 0
    skipped_row_count: int = 0
    mean: float = float("nan")
    std: float = float("nan")
    min_val: float = float("nan")
    max_val: float = float("nan")
    cv_percent: float = float("nan")
    clean_cv_percent: float = float("nan")
    n_outliers: int = 0
    failure_rate: float = float("nan")
    notes: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SweepMetricCurve:
    """One metric's behavior across tolerance levels.

    Parameters
    ----------
    tolerance_parameter : str
    metric_name : str
    levels_um : tuple of float
    summaries : tuple of SweepMetricLevelSummary
    mean_values : tuple of float
    cv_values : tuple of float
    clean_cv_values : tuple of float
    failure_rates : tuple of float
    monotonic_mean : str
    monotonic_cv : str
    largest_mean_delta_index : int or None
    largest_cv_delta_index : int or None
    """
    tolerance_parameter: str = ""
    metric_name: str = ""
    levels_um: tuple[float, ...] = ()
    summaries: tuple[SweepMetricLevelSummary, ...] = ()
    mean_values: tuple[float, ...] = ()
    cv_values: tuple[float, ...] = ()
    clean_cv_values: tuple[float, ...] = ()
    failure_rates: tuple[float, ...] = ()
    monotonic_mean: str = "unknown"
    monotonic_cv: str = "unknown"
    largest_mean_delta_index: int | None = None
    largest_cv_delta_index: int | None = None


@dataclasses.dataclass(frozen=True)
class SweepAnalysisReport:
    """Cross-level analysis of a tolerance sweep.

    Parameters
    ----------
    tolerance_parameter : str
    levels_um : tuple of float
    metric_curves : tuple of SweepMetricCurve
    metric_names : tuple of str
    notes : tuple of str
    """
    tolerance_parameter: str = ""
    levels_um: tuple[float, ...] = ()
    metric_curves: tuple[SweepMetricCurve, ...] = ()
    metric_names: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


# ===================================================================
# Monotonicity
# ===================================================================


def classify_monotonic(values: Sequence[float], *, atol: float = 1e-12) -> str:
    """Classify a sequence as monotonic, flat, or non_monotonic.

    NaN/inf values are ignored.  If fewer than 2 finite values remain,
    returns ``"unknown"``.

    Parameters
    ----------
    values : sequence of float
    atol : float
        Absolute tolerance for flat comparison.

    Returns
    -------
    str
        ``"increasing"``, ``"decreasing"``, ``"flat"``, ``"non_monotonic"``,
        or ``"unknown"``.
    """
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if len(finite) < 2:
        return "unknown"

    deltas = np.diff(finite)
    pos = np.sum(deltas > atol)
    neg = np.sum(deltas < -atol)

    if pos == 0 and neg == 0:
        return "flat"
    if neg == 0:
        return "increasing"
    if pos == 0:
        return "decreasing"
    return "non_monotonic"


# ===================================================================
# Largest adjacent delta
# ===================================================================


def largest_adjacent_delta_index(values: Sequence[float]) -> int | None:
    """Return the index of the largest absolute adjacent delta.

    NaN/inf adjacent pairs are skipped.  Returns ``None`` when fewer
    than 2 finite adjacent pairs exist.

    Parameters
    ----------
    values : sequence of float

    Returns
    -------
    int or None
    """
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return None

    max_delta = -1.0
    max_idx: int | None = None
    for i in range(len(arr) - 1):
        a, b = arr[i], arr[i + 1]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        delta = abs(b - a)
        if delta > max_delta:
            max_delta = delta
            max_idx = i
    return max_idx


# ===================================================================
# Group summary
# ===================================================================


def summarize_sweep_group(
    group: ToleranceSweepGroup,
    *,
    metric_names: Sequence[str] | None = None,
    include_clean_cv: bool = True,
    clean_method: str = "iqr",
    clean_multiplier: float = 3.0,
) -> tuple[SweepMetricLevelSummary, ...]:
    """Compute per-metric summaries for one sweep group.

    Parameters
    ----------
    group : ToleranceSweepGroup
    metric_names : sequence of str or None
        Desired metric names and order.  ``None`` uses
        ``group.dataset.metric_names``.
    include_clean_cv : bool
    clean_method : str
    clean_multiplier : float

    Returns
    -------
    tuple of SweepMetricLevelSummary
    """
    ds = group.dataset
    src = ds.source_row_count
    acc = ds.accepted_row_count
    skp = ds.skipped_row_count
    failure_rate = float("nan")
    if src > 0:
        failure_rate = skp / src

    mn = list(metric_names) if metric_names else list(ds.metric_names)

    # Basic and clean summaries
    basic_list = list(summarize_dataset(ds))
    clean_list = list(summarize_dataset_clean(
        ds, method=clean_method, multiplier=clean_multiplier,
    )) if include_clean_cv else []

    # Build a lookup by metric name
    basic_by_name: dict[str, Any] = {s.name: s for s in basic_list}
    clean_by_name: dict[str, Any] = {s.name: s for s in clean_list}

    results: list[SweepMetricLevelSummary] = []
    for mname in mn:
        bs = basic_by_name.get(mname)
        cs = clean_by_name.get(mname) if include_clean_cv else None
        n_outliers = cs.outliers.n_outliers if cs is not None else 0
        cv_clean = cs.clean.cv_percent if cs is not None else float("nan")

        if bs is not None:
            results.append(SweepMetricLevelSummary(
                tolerance_parameter=group.tolerance_parameter,
                tolerance_level_um=group.tolerance_level_um,
                tolerance_level_mm=group.tolerance_level_mm,
                metric_name=mname,
                accepted_row_count=acc,
                source_row_count=src,
                skipped_row_count=skp,
                mean=bs.mean, std=bs.std,
                min_val=bs.min_val, max_val=bs.max_val,
                cv_percent=bs.cv_percent,
                clean_cv_percent=cv_clean,
                n_outliers=n_outliers,
                failure_rate=failure_rate,
            ))
        else:
            results.append(SweepMetricLevelSummary(
                tolerance_parameter=group.tolerance_parameter,
                tolerance_level_um=group.tolerance_level_um,
                tolerance_level_mm=group.tolerance_level_mm,
                metric_name=mname,
                accepted_row_count=acc,
                source_row_count=src,
                skipped_row_count=skp,
                failure_rate=failure_rate,
                notes=("metric not found in dataset",),
            ))
    return tuple(results)


# ===================================================================
# Curve building
# ===================================================================


def build_metric_curves(
    level_summaries: Sequence[SweepMetricLevelSummary],
    metric_order: Sequence[str] | None = None,
) -> tuple[SweepMetricCurve, ...]:
    """Group per-level summaries by metric and build curves.

    Parameters
    ----------
    metric_order : sequence of str or None
        Desired metric order.  None uses sorted-by-name order.
    level_summaries : sequence of SweepMetricLevelSummary
        Output of ``summarize_sweep_group()`` for each group, flattened.

    Returns
    -------
    tuple of SweepMetricCurve
    """
    # Group by metric_name
    by_metric: dict[str, list[SweepMetricLevelSummary]] = {}
    tp = ""
    for s in level_summaries:
        tp = s.tolerance_parameter
        by_metric.setdefault(s.metric_name, []).append(s)

    if metric_order is not None:
        seen = set(metric_order)
        metric_keys = list(metric_order) + [k for k in by_metric if k not in seen]
    else:
        metric_keys = sorted(by_metric.keys())

    curves: list[SweepMetricCurve] = []
    for mname in metric_keys:
        if mname not in by_metric:
            continue
        summaries = sorted(
            by_metric[mname], key=lambda s: s.tolerance_level_um,
        )
        levels = tuple(s.tolerance_level_um for s in summaries)
        means = tuple(s.mean for s in summaries)
        cvs = tuple(s.cv_percent for s in summaries)
        clean_cvs = tuple(s.clean_cv_percent for s in summaries)
        rates = tuple(s.failure_rate for s in summaries)

        curves.append(SweepMetricCurve(
            tolerance_parameter=tp,
            metric_name=mname,
            levels_um=levels,
            summaries=tuple(summaries),
            mean_values=means,
            cv_values=cvs,
            clean_cv_values=clean_cvs,
            failure_rates=rates,
            monotonic_mean=classify_monotonic(means),
            monotonic_cv=classify_monotonic(cvs),
            largest_mean_delta_index=largest_adjacent_delta_index(means),
            largest_cv_delta_index=largest_adjacent_delta_index(cvs),
        ))
    return tuple(curves)


# ===================================================================
# Main entry point
# ===================================================================


def analyze_tolerance_sweep(
    sweep: ToleranceSweepDataset,
    *,
    metric_names: Sequence[str] | None = None,
    include_clean_cv: bool = True,
    clean_method: str = "iqr",
    clean_multiplier: float = 3.0,
) -> SweepAnalysisReport:
    """Run cross-level analysis on a tolerance sweep dataset.

    Parameters
    ----------
    sweep : ToleranceSweepDataset
    metric_names : sequence of str or None
    include_clean_cv : bool
    clean_method : str
    clean_multiplier : float

    Returns
    -------
    SweepAnalysisReport
    """
    # Summarize each group
    all_level: list[SweepMetricLevelSummary] = []
    notes: list[str] = []
    for g in sweep.groups:
        all_level.extend(summarize_sweep_group(
            g,
            metric_names=metric_names,
            include_clean_cv=include_clean_cv,
            clean_method=clean_method,
            clean_multiplier=clean_multiplier,
        ))

    if not all_level:
        notes.append("no groups to analyze")

    # Build curves
    curves = build_metric_curves(all_level, metric_order=metric_names)

    # Determine metric_names from curves if not provided
    if metric_names is None:
        metric_names = tuple(c.metric_name for c in curves)

    return SweepAnalysisReport(
        tolerance_parameter=sweep.tolerance_parameter,
        levels_um=sweep.tolerance_levels_um,
        metric_curves=curves,
        metric_names=tuple(metric_names),
        notes=tuple(notes),
    )
