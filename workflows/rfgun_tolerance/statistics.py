"""No-CST tolerance statistics — TAM2.

Pure numerical helpers for computing per-metric summary statistics
from a ``ToleranceDataset``: mean, std, min, max, CV.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Sequence

import numpy as np

from workflows.rfgun_tolerance.dataset import ToleranceDataset


# ===================================================================
# Metric summary
# ===================================================================


@dataclasses.dataclass(frozen=True)
class MetricSummary:
    """Summary statistics for one metric.

    Parameters
    ----------
    name : str
        Canonical metric name.
    n_total : int
        Number of rows before NaN removal.
    n_finite : int
        Number of finite (non-NaN, non-inf) values used.
    mean : float
        Arithmetic mean of finite values.
    std : float
        Sample standard deviation (ddof=1) if ``n_finite >= 2``;
        0.0 if ``n_finite == 1``; ``NaN`` if ``n_finite == 0``.
    min_val : float
        Minimum finite value.
    max_val : float
        Maximum finite value.
    cv_percent : float
        Coefficient of variation in percent: ``std / |mean| * 100``.
        ``NaN`` when ``n_finite < 2``.
        ``+inf`` when ``|mean| < epsilon`` and ``std > 0``.
        0.0 when ``std == 0`` (regardless of mean).
    """
    name: str = ""
    n_total: int = 0
    n_finite: int = 0
    mean: float = float("nan")
    std: float = float("nan")
    min_val: float = float("nan")
    max_val: float = float("nan")
    cv_percent: float = float("nan")


# Epsilon for near-zero mean detection
_ZERO_EPSILON = 1e-12


def summarize_metric(
    values: Sequence[float],
    name: str = "",
    *,
    ddof: int = 1,
    zero_epsilon: float = _ZERO_EPSILON,
) -> MetricSummary:
    """Compute summary statistics for a single metric.

    Parameters
    ----------
    values : sequence of float
        Raw metric values; NaN/inf values are ignored.
    name : str
        Human-readable metric name for diagnostics.
    ddof : int
        Delta degrees of freedom for standard deviation. Standard
        ``ddof=1`` for sample std, ``ddof=0`` for population std.
    zero_epsilon : float
        Threshold below which ``mean`` is considered near-zero for CV.

    Returns
    -------
    MetricSummary
    """
    arr = np.asarray(values, dtype=float)
    n_total = len(arr)
    finite_mask = np.isfinite(arr)
    n_finite = int(np.sum(finite_mask))

    if n_finite == 0:
        return MetricSummary(name=name, n_total=n_total, n_finite=0)

    finite_vals = arr[finite_mask]
    mean_val = float(np.mean(finite_vals))

    if n_finite >= 2:
        std_val = float(np.std(finite_vals, ddof=ddof))
    else:
        std_val = 0.0

    min_val = float(np.min(finite_vals))
    max_val = float(np.max(finite_vals))

    # CV percent
    if n_finite < 2:
        cv = float("nan")
    elif std_val == 0.0:
        cv = 0.0
    elif abs(mean_val) <= zero_epsilon:
        cv = float("inf")
    else:
        cv = std_val / abs(mean_val) * 100.0

    return MetricSummary(
        name=name,
        n_total=n_total,
        n_finite=n_finite,
        mean=mean_val,
        std=std_val,
        min_val=min_val,
        max_val=max_val,
        cv_percent=cv,
    )


def summarize_dataset(
    dataset: ToleranceDataset,
    *,
    metric_indices: Sequence[int] | None = None,
    ddof: int = 1,
) -> list[MetricSummary]:
    """Compute summary statistics for each metric in a dataset.

    Parameters
    ----------
    dataset : ToleranceDataset
        Input tolerance dataset.
    metric_indices : sequence of int or None
        Subset of metric column indices.  ``None`` means all metrics.
    ddof : int
        Delta degrees of freedom.

    Returns
    -------
    list of MetricSummary
        One summary per metric in *metric_indices* or all metrics.
    """
    if metric_indices is None:
        metric_indices = range(len(dataset.metric_names))
    summaries: list[MetricSummary] = []
    for idx in metric_indices:
        name = dataset.metric_names[idx]
        values = dataset.metric_values[:, idx]
        summaries.append(summarize_metric(values, name=name, ddof=ddof))
    return summaries


# ===================================================================
# Outlier detection -- TAM3
# ===================================================================

@dataclasses.dataclass(frozen=True)
class OutlierDetectionResult:
    """Result of an outlier detection pass."""
    method: str = ""
    n_total: int = 0
    n_finite: int = 0
    n_outliers: int = 0
    outlier_mask: np.ndarray = dataclasses.field(default_factory=lambda: np.array([], dtype=bool))
    lower_bound: float = float("nan")
    upper_bound: float = float("nan")
    center: float | None = None
    scale: float | None = None

def detect_outliers_iqr(values, multiplier=3.0):
    arr = np.asarray(values, dtype=float)
    n_total = len(arr)
    finite_mask = np.isfinite(arr)
    n_finite = int(np.sum(finite_mask))
    outlier_mask = np.zeros(n_total, dtype=bool)
    if n_finite < 4:
        return OutlierDetectionResult(method="iqr", n_total=n_total, n_finite=n_finite, outlier_mask=outlier_mask)
    fv = arr[finite_mask]
    q1 = float(np.percentile(fv, 25))
    q3 = float(np.percentile(fv, 75))
    iqr = q3 - q1
    if abs(iqr) <= 1e-15:
        return OutlierDetectionResult(method="iqr", n_total=n_total, n_finite=n_finite, outlier_mask=outlier_mask, lower_bound=q1, upper_bound=q3, center=float(np.median(fv)), scale=iqr)
    lo = q1 - multiplier * iqr
    hi = q3 + multiplier * iqr
    outlier_mask[finite_mask] = (fv < lo) | (fv > hi)
    return OutlierDetectionResult(method="iqr", n_total=n_total, n_finite=n_finite, n_outliers=int(np.sum(outlier_mask)), outlier_mask=outlier_mask, lower_bound=lo, upper_bound=hi, center=float(np.median(fv)), scale=iqr)

def detect_outliers_mad(values, threshold=5.0):
    arr = np.asarray(values, dtype=float)
    n_total = len(arr)
    finite_mask = np.isfinite(arr)
    n_finite = int(np.sum(finite_mask))
    outlier_mask = np.zeros(n_total, dtype=bool)
    if n_finite < 4:
        return OutlierDetectionResult(method="mad", n_total=n_total, n_finite=n_finite, outlier_mask=outlier_mask)
    fv = arr[finite_mask]
    med = float(np.median(fv))
    ad = np.abs(fv - med)
    mad = float(np.median(ad))
    if mad <= 1e-15:
        return OutlierDetectionResult(method="mad", n_total=n_total, n_finite=n_finite, outlier_mask=outlier_mask, center=med, scale=mad)
    lo = med - threshold * mad
    hi = med + threshold * mad
    outlier_mask[finite_mask] = (fv < lo) | (fv > hi)
    return OutlierDetectionResult(method="mad", n_total=n_total, n_finite=n_finite, n_outliers=int(np.sum(outlier_mask)), outlier_mask=outlier_mask, lower_bound=lo, upper_bound=hi, center=med, scale=mad)

@dataclasses.dataclass(frozen=True)
class CleanMetricSummary:
    name: str = ""
    raw: MetricSummary = dataclasses.field(default_factory=MetricSummary)
    clean: MetricSummary = dataclasses.field(default_factory=MetricSummary)
    outliers: OutlierDetectionResult = dataclasses.field(default_factory=OutlierDetectionResult)
    removed_indices: tuple[int, ...] = ()
    cv_delta_percent: float = float("nan")
    cv_delta_relative: float = float("nan")

def summarize_metric_clean(values, name="", method="iqr", multiplier=3.0, threshold=5.0):
    if method not in ("iqr", "mad"):
        raise ValueError(f"Unknown method={method!r}; supported: 'iqr', 'mad'")
    raw = summarize_metric(values, name=name)
    outliers = detect_outliers_mad(values, threshold=threshold) if method == "mad" else detect_outliers_iqr(values, multiplier=multiplier)
    arr = np.asarray(values, dtype=float)
    cm = np.ones(len(arr), dtype=bool)
    if outliers.n_outliers > 0:
        cm = ~outliers.outlier_mask
    cm[~np.isfinite(arr)] = False
    cv = arr[cm]
    cs = summarize_metric(list(cv), name=name)
    removed = tuple(int(i) for i in np.where(outliers.outlier_mask)[0])
    cvp = float("nan")
    cvr = float("nan")
    if np.isfinite(raw.cv_percent) and np.isfinite(cs.cv_percent):
        cvp = raw.cv_percent - cs.cv_percent
        if abs(raw.cv_percent) > 1e-12:
            cvr = cvp / raw.cv_percent
    return CleanMetricSummary(name=name, raw=raw, clean=cs, outliers=outliers, removed_indices=removed, cv_delta_percent=cvp, cv_delta_relative=cvr)

def summarize_dataset_clean(dataset, method="iqr", multiplier=3.0, threshold=5.0, metric_indices=None):
    if metric_indices is None:
        metric_indices = range(len(dataset.metric_names))
    return [summarize_metric_clean(dataset.metric_values[:, i], name=dataset.metric_names[i], method=method, multiplier=multiplier, threshold=threshold) for i in metric_indices]

