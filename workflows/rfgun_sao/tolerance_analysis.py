"""No-CST tolerance analysis orchestration — TAM5.

Composes TAM2 dataset loader, TAM3 clean CV, and TAM4 sensitivity
into a single ``ToleranceAnalysisReport``.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Sequence

from workflows.rfgun_sao.tolerance_dataset import (
    ToleranceDataset,
    build_tolerance_dataset_from_records,
)
from workflows.rfgun_sao.tolerance_statistics import (
    CleanMetricSummary,
    MetricSummary,
    summarize_dataset,
    summarize_dataset_clean,
)
from workflows.rfgun_sao.tolerance_sensitivity import (
    SensitivityAnalysisReport,
    analyze_parameter_sensitivity,
)


@dataclasses.dataclass(frozen=True)
class ToleranceAnalysisConfig:
    """Configuration for a tolerance analysis run.

    Parameters
    ----------
    metric_names : tuple of str or None
    param_names : tuple of str or None
    clean_method : str
        ``"iqr"`` or ``"mad"``.
    clean_multiplier : float
        IQR multiplier.
    clean_threshold : float
        MAD threshold.
    sensitivity_method : str
        ``"spearman"``, ``"pearson"``, or ``"linear_beta"``.
    sensitivity_min_finite : int
    include_clean_cv : bool
    include_sensitivity : bool
    """
    metric_names: tuple[str, ...] | None = None
    param_names: tuple[str, ...] | None = None
    clean_method: str = "iqr"
    clean_multiplier: float = 3.0
    clean_threshold: float = 5.0
    sensitivity_method: str = "spearman"
    sensitivity_min_finite: int = 5
    include_clean_cv: bool = True
    include_sensitivity: bool = True


@dataclasses.dataclass(frozen=True)
class ToleranceAnalysisReport:
    """Structured result of a complete tolerance analysis.

    Parameters
    ----------
    dataset : ToleranceDataset
    basic_summaries : tuple of MetricSummary
    clean_summaries : tuple of CleanMetricSummary
    sensitivity : SensitivityAnalysisReport or None
    notes : tuple of str
    """
    dataset: ToleranceDataset = dataclasses.field(default_factory=ToleranceDataset)
    basic_summaries: tuple[MetricSummary, ...] = ()
    clean_summaries: tuple[CleanMetricSummary, ...] = ()
    sensitivity: SensitivityAnalysisReport | None = None
    notes: tuple[str, ...] = ()


def analyze_tolerance_records(
    records: Sequence[dict[str, Any]],
    config: ToleranceAnalysisConfig | None = None,
) -> ToleranceAnalysisReport:
    """Analyze tolerance from a sequence of record dicts.

    Parameters
    ----------
    records : sequence of dict
        Input records (TAM2-compatible).
    config : ToleranceAnalysisConfig or None

    Returns
    -------
    ToleranceAnalysisReport
    """
    if config is None:
        config = ToleranceAnalysisConfig()
    mn = list(config.metric_names) if config.metric_names else None
    pn = list(config.param_names) if config.param_names else None
    ds = build_tolerance_dataset_from_records(records, metric_names=mn, param_names=pn)
    return analyze_tolerance_dataset(ds, config=config)


def analyze_tolerance_dataset(
    dataset: ToleranceDataset,
    config: ToleranceAnalysisConfig | None = None,
) -> ToleranceAnalysisReport:
    """Analyze tolerance from a prebuilt ``ToleranceDataset``.

    Parameters
    ----------
    dataset : ToleranceDataset
    config : ToleranceAnalysisConfig or None

    Returns
    -------
    ToleranceAnalysisReport
    """
    if config is None:
        config = ToleranceAnalysisConfig()

    notes: list[str] = []

    if dataset.accepted_row_count == 0:
        notes.append("dataset is empty: no SUCCESS rows found")

    # Basic summaries
    basic = tuple(summarize_dataset(dataset))

    # Clean summaries
    clean: tuple[CleanMetricSummary, ...] = ()
    if config.include_clean_cv:
        clean = tuple(summarize_dataset_clean(
            dataset, method=config.clean_method,
            multiplier=config.clean_multiplier,
            threshold=config.clean_threshold,
        ))

    # Sensitivity
    sensitivity: SensitivityAnalysisReport | None = None
    if config.include_sensitivity:
        n_params = len(dataset.param_names)
        n_metrics = len(dataset.metric_names)
        n_rows = dataset.metric_values.shape[0]
        if n_params == 0:
            notes.append("sensitivity skipped: no parameters")
        elif n_metrics == 0:
            notes.append("sensitivity skipped: no metrics")
        elif n_rows < config.sensitivity_min_finite:
            notes.append(
                f"sensitivity skipped: rows ({n_rows}) < min_finite "
                f"({config.sensitivity_min_finite})",
            )
        else:
            sensitivity = analyze_parameter_sensitivity(
                dataset,
                method=config.sensitivity_method,
                min_finite=config.sensitivity_min_finite,
            )

    return ToleranceAnalysisReport(
        dataset=dataset,
        basic_summaries=basic,
        clean_summaries=clean,
        sensitivity=sensitivity,
        notes=tuple(notes),
    )
