"""No-CST per-parameter sensitivity analysis — TAM4.

Computes Pearson correlation, Spearman rank correlation, and
standardised linear beta coefficients from a ``ToleranceDataset``.
All helpers are pure, deterministic, and no-CST.
"""

from __future__ import annotations

import dataclasses
from typing import Sequence

import numpy as np

from workflows.rfgun_tolerance.dataset import ToleranceDataset


# ===================================================================
# Data model
# ===================================================================


@dataclasses.dataclass(frozen=True)
class ParameterSensitivity:
    """Sensitivity score for one parameter-metric pair.

    Parameters
    ----------
    parameter_name : str
    metric_name : str
    method : str
    score : float
        Correlation or beta coefficient.
    abs_score : float
        Absolute value of *score* (for ranking).
    direction : str
        ``"positive"``, ``"negative"``, ``"zero"``, or ``"unknown"``.
    n_finite : int
        Number of finite rows used.
    rank : int or None
        Rank within the report (1 = most sensitive).
    p_value : float or None
        P-value if computed; ``None`` when unavailable.
    """
    parameter_name: str = ""
    metric_name: str = ""
    method: str = ""
    score: float = float("nan")
    abs_score: float = float("nan")
    direction: str = "unknown"
    n_finite: int = 0
    rank: int | None = None
    p_value: float | None = None


@dataclasses.dataclass(frozen=True)
class MetricSensitivityReport:
    """Sensitivity report for one metric across all parameters.

    Parameters
    ----------
    metric_name : str
    method : str
    n_parameters : int
    n_rows : int
    sensitivities : tuple of ParameterSensitivity
    top_parameter : str or None
    notes : tuple of str
    """
    metric_name: str = ""
    method: str = ""
    n_parameters: int = 0
    n_rows: int = 0
    sensitivities: tuple[ParameterSensitivity, ...] = ()
    top_parameter: str | None = None
    notes: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SensitivityAnalysisReport:
    """Full sensitivity analysis over a dataset.

    Parameters
    ----------
    method : str
    metric_reports : tuple of MetricSensitivityReport
    param_names : tuple of str
    metric_names : tuple of str
    n_rows : int
    """
    method: str = ""
    metric_reports: tuple[MetricSensitivityReport, ...] = ()
    param_names: tuple[str, ...] = ()
    metric_names: tuple[str, ...] = ()
    n_rows: int = 0


# ===================================================================
# Helpers
# ===================================================================


def _finite_mask(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Return a boolean mask where both x and y are finite."""
    return np.isfinite(x) & np.isfinite(y)


def _direction(score: float) -> str:
    if np.isnan(score):
        return "unknown"
    if score > 1e-15:
        return "positive"
    if score < -1e-15:
        return "negative"
    return "zero"


def _rank_sensitivities(
    sensitivities: list[ParameterSensitivity],
) -> list[ParameterSensitivity]:
    """Rank a list by descending abs_score; finite scores before NaN."""
    # Split into finite-score and NaN-score groups
    finite = [s for s in sensitivities if np.isfinite(s.abs_score)]
    nan_s = [s for s in sensitivities if not np.isfinite(s.abs_score)]

    # Sort finite by descending abs_score
    finite.sort(key=lambda s: -s.abs_score)

    ranked: list[ParameterSensitivity] = []
    for i, s in enumerate(finite):
        ranked.append(dataclasses.replace(s, rank=i + 1))
    for s in nan_s:
        ranked.append(dataclasses.replace(s, rank=None))

    return ranked


# ===================================================================
# Pearson correlation
# ===================================================================


def _pearson_r(x: np.ndarray, y: np.ndarray) -> tuple[float, float | None]:
    """Compute Pearson r and p_value for two arrays."""
    mask = _finite_mask(x, y)
    n = int(np.sum(mask))
    if n < 3:
        return float("nan"), None
    xf, yf = x[mask], y[mask]
    xstd = float(np.std(xf))
    ystd = float(np.std(yf))
    if xstd < 1e-15 or ystd < 1e-15:
        return 0.0, None
    try:
        from scipy.stats import pearsonr
        r, p = pearsonr(xf, yf)
        return float(r), float(p)
    except ImportError:
        # Fallback: manual r computation
        xm = np.mean(xf)
        ym = np.mean(yf)
        num = np.sum((xf - xm) * (yf - ym))
        den = np.sqrt(np.sum((xf - xm)**2) * np.sum((yf - ym)**2)) + 1e-30
        r = num / den
        return float(r), None


def _compute_pearson_metric(
    param_values: np.ndarray,
    metric_values: np.ndarray,
    param_names: list[str],
    metric_name: str,
    min_finite: int,
) -> list[ParameterSensitivity]:
    n_params = param_values.shape[1]
    sens: list[ParameterSensitivity] = []
    for j in range(n_params):
        x = param_values[:, j]
        mask = _finite_mask(x, metric_values)
        nf = int(np.sum(mask))
        if nf < min_finite:
            sens.append(ParameterSensitivity(
                parameter_name=param_names[j], metric_name=metric_name,
                method="pearson", n_finite=nf,
            ))
            continue
        score, pv = _pearson_r(x, metric_values)
        sens.append(ParameterSensitivity(
            parameter_name=param_names[j], metric_name=metric_name,
            method="pearson", score=score, abs_score=abs(score),
            direction=_direction(score), n_finite=nf, p_value=pv,
        ))
    return _rank_sensitivities(sens)


# ===================================================================
# Spearman rank correlation
# ===================================================================


def _spearman_r(x: np.ndarray, y: np.ndarray) -> tuple[float, float | None]:
    """Compute Spearman rho and p_value."""
    mask = _finite_mask(x, y)
    n = int(np.sum(mask))
    if n < 3:
        return float("nan"), None
    xf, yf = x[mask], y[mask]
    xstd = float(np.std(xf))
    ystd = float(np.std(yf))
    if xstd < 1e-15 or ystd < 1e-15:
        return 0.0, None
    try:
        from scipy.stats import spearmanr
        r, p = spearmanr(xf, yf)
        return float(r), float(p)
    except ImportError:
        # Fallback: rank-based Pearson
        xr = np.argsort(np.argsort(xf)).astype(float)
        yr = np.argsort(np.argsort(yf)).astype(float)
        xm, ym = np.mean(xr), np.mean(yr)
        num = np.sum((xr - xm) * (yr - ym))
        den = np.sqrt(np.sum((xr - xm)**2) * np.sum((yr - ym)**2)) + 1e-30
        return float(num / den), None


def _compute_spearman_metric(
    param_values: np.ndarray,
    metric_values: np.ndarray,
    param_names: list[str],
    metric_name: str,
    min_finite: int,
) -> list[ParameterSensitivity]:
    n_params = param_values.shape[1]
    sens: list[ParameterSensitivity] = []
    for j in range(n_params):
        x = param_values[:, j]
        mask = _finite_mask(x, metric_values)
        nf = int(np.sum(mask))
        if nf < min_finite:
            sens.append(ParameterSensitivity(
                parameter_name=param_names[j], metric_name=metric_name,
                method="spearman", n_finite=nf,
            ))
            continue
        score, pv = _spearman_r(x, metric_values)
        sens.append(ParameterSensitivity(
            parameter_name=param_names[j], metric_name=metric_name,
            method="spearman", score=score, abs_score=abs(score),
            direction=_direction(score), n_finite=nf, p_value=pv,
        ))
    return _rank_sensitivities(sens)


def _unknown_sensitivity(name, metric, method, nf):
    """Return a ParameterSensitivity with NaN scores."""
    return ParameterSensitivity(
        parameter_name=name, metric_name=metric,
        method=method, n_finite=nf,
    )


# ===================================================================
# Linear beta (standardised regression coefficients)
# ===================================================================


def _compute_linear_beta_metric(
    param_values: np.ndarray,
    metric_values: np.ndarray,
    param_names: list[str],
    metric_name: str,
    min_finite: int,
) -> list[ParameterSensitivity]:
    n_params = param_values.shape[1]
    # Finite rows across all selected params and metric
    mask = np.isfinite(metric_values)
    for j in range(n_params):
        mask &= np.isfinite(param_values[:, j])
    nf = int(np.sum(mask))
    if nf < min_finite or nf < n_params + 1:
        # Not enough rows for reliable regression
        return [
            ParameterSensitivity(
                parameter_name=pn, metric_name=metric_name,
                method="linear_beta", n_finite=nf,
            )
            for pn in param_names
        ]

    # Standardise
    X = param_values[mask, :]
    y = metric_values[mask]
    X_z = (X - np.mean(X, axis=0)) / (np.std(X, axis=0) + 1e-30)
    y_z = (y - np.mean(y)) / (np.std(y) + 1e-30)

    # Check column variances
    col_std = np.std(X, axis=0)
    has_constant = np.any(col_std < 1e-15)

    # Build a list tracking which columns are non-constant
    non_constant_cols = [j for j in range(n_params) if col_std[j] >= 1e-15]
    n_non_constant = len(non_constant_cols)

    if n_non_constant == 0:
        # All columns are constant — return zeros
        return _rank_sensitivities([
            ParameterSensitivity(
                parameter_name=param_names[j], metric_name=metric_name,
                method="linear_beta", score=0.0, abs_score=0.0,
                direction="zero", n_finite=nf,
            )
            for j in range(n_params)
        ])

    # Solve least squares on non-constant columns only — capture rank
    try:
        X_nc = X_z[:, non_constant_cols]
        beta_nc, _, rank, _ = np.linalg.lstsq(X_nc, y_z, rcond=None)
    except np.linalg.LinAlgError:
        beta_nc = np.full(n_non_constant, float("nan"))
        rank = 0  # force rank_deficient for non-constant columns

    rank_deficient = rank < n_non_constant

    sens: list[ParameterSensitivity] = []
    nc_idx = 0
    for j in range(n_params):
        if col_std[j] < 1e-15:
            sens.append(ParameterSensitivity(
                parameter_name=param_names[j], metric_name=metric_name,
                method="linear_beta", score=0.0, abs_score=0.0,
                direction="zero", n_finite=nf,
            ))
        elif rank_deficient:
            sens.append(_unknown_sensitivity(param_names[j], metric_name, "linear_beta", nf))
        else:
            b = float(beta_nc[nc_idx]) if nc_idx < len(beta_nc) else float("nan")
            nc_idx += 1
            sens.append(ParameterSensitivity(
                parameter_name=param_names[j], metric_name=metric_name,
                method="linear_beta", score=b, abs_score=abs(b),
                direction=_direction(b), n_finite=nf,
            ))
    return _rank_sensitivities(sens)


# ===================================================================
# Main entry point
# ===================================================================


def analyze_parameter_sensitivity(
    dataset: ToleranceDataset,
    *,
    method: str = "spearman",
    metric_indices: Sequence[int] | None = None,
    param_indices: Sequence[int] | None = None,
    min_finite: int = 5,
) -> SensitivityAnalysisReport:
    """Compute per-parameter sensitivity for each metric.

    Parameters
    ----------
    dataset : ToleranceDataset
    method : str
        ``"pearson"``, ``"spearman"``, or ``"linear_beta"``.
    metric_indices : sequence of int or None
        Subset of metric columns.  ``None`` means all.
    param_indices : sequence of int or None
        Subset of parameter columns.  ``None`` means all.
    min_finite : int
        Minimum number of finite rows required for computation.

    Returns
    -------
    SensitivityAnalysisReport
    """
    allowed_methods = {"pearson", "spearman", "linear_beta"}
    if method not in allowed_methods:
        raise ValueError(
            f"Unknown method={method!r}; allowed: {sorted(allowed_methods)}",
        )

    if metric_indices is None:
        metric_indices = list(range(len(dataset.metric_names)))
    if param_indices is None:
        param_indices = list(range(len(dataset.param_names)))

    param_names = [dataset.param_names[i] for i in param_indices]
    metric_names = [dataset.metric_names[i] for i in metric_indices]
    n_rows = dataset.metric_values.shape[0]

    metric_reports: list[MetricSensitivityReport] = []

    for mi in metric_indices:
        mv = dataset.metric_values[:, mi]
        pv = dataset.parameter_values[:, param_indices]

        if method == "pearson":
            sens = _compute_pearson_metric(pv, mv, param_names, dataset.metric_names[mi], min_finite)
        elif method == "spearman":
            sens = _compute_spearman_metric(pv, mv, param_names, dataset.metric_names[mi], min_finite)
        elif method == "linear_beta":
            sens = _compute_linear_beta_metric(pv, mv, param_names, dataset.metric_names[mi], min_finite)
        else:
            raise ValueError(f"Unsupported method: {method}")

        top = sens[0].parameter_name if sens and sens[0].rank is not None else None

        metric_reports.append(MetricSensitivityReport(
            metric_name=dataset.metric_names[mi],
            method=method, n_parameters=len(sens), n_rows=n_rows,
            sensitivities=tuple(sens), top_parameter=top,
        ))

    return SensitivityAnalysisReport(
        method=method,
        metric_reports=tuple(metric_reports),
        param_names=tuple(param_names),
        metric_names=tuple(metric_names),
        n_rows=n_rows,
    )
