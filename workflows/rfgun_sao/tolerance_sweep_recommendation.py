"""No-CST tolerance sweep recommendation rules — TSE4.

Evaluates TSE3 sweep analysis against configurable ``MetricAcceptanceRule``
thresholds and produces ``SweepToleranceRecommendation`` with per-metric
recommendations and overall envelope limits.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Sequence

from workflows.rfgun_sao.tolerance_sweep_analysis import (
    SweepAnalysisReport,
    SweepMetricCurve,
    SweepMetricLevelSummary,
)


# ===================================================================
# Rule definition
# ===================================================================


@dataclasses.dataclass(frozen=True)
class MetricAcceptanceRule:
    """Threshold-based acceptance rule for one metric.

    Parameters
    ----------
    metric_name : str
    max_mean : float or None
    min_mean : float or None
    max_cv_percent : float or None
    max_clean_cv_percent : float or None
    max_failure_rate : float or None
    max_outliers : int or None
    max_delta_from_baseline : float or None
    max_relative_delta_from_baseline : float or None
    direction : str
        ``"smaller_is_better"``, ``"larger_is_better"``, ``"target"``,
        or ``"unknown"``.
    target_mean : float or None
    max_abs_error_from_target : float or None
    """
    metric_name: str = ""
    max_mean: float | None = None
    min_mean: float | None = None
    max_cv_percent: float | None = None
    max_clean_cv_percent: float | None = None
    max_failure_rate: float | None = None
    max_outliers: int | None = None
    max_delta_from_baseline: float | None = None
    max_relative_delta_from_baseline: float | None = None
    direction: str = "smaller_is_better"
    target_mean: float | None = None
    max_abs_error_from_target: float | None = None


def default_field_flatness_rule(*, max_mean: float = 0.08) -> MetricAcceptanceRule:
    """Return a conservative placeholder rule for ``field_flatness``.

    Parameters
    ----------
    max_mean : float
        Default threshold; should be overridden by the project.

    Returns
    -------
    MetricAcceptanceRule
    """
    return MetricAcceptanceRule(
        metric_name="field_flatness",
        max_mean=max_mean,
        max_cv_percent=50.0,
        max_delta_from_baseline=0.05,
        direction="smaller_is_better",
    )


# ===================================================================
# Level evaluation
# ===================================================================


def _finite(val: float) -> bool:
    """True if val is finite and not NaN."""
    return isinstance(val, (int, float)) and math.isfinite(val)


def evaluate_metric_level(
    summary: SweepMetricLevelSummary,
    rule: MetricAcceptanceRule,
    baseline_summary: SweepMetricLevelSummary | None = None,
) -> MetricLevelDecision:
    """Evaluate one tolerance level against a rule."""
    reasons: list[str] = []
    status = "pass"

    def _fail(reason: str) -> None:
        nonlocal status
        status = "fail"
        reasons.append(reason)

    def _warn(reason: str) -> None:
        nonlocal status
        if status != "fail":
            status = "warning"
        reasons.append(reason)

    def _unknown(reason: str) -> None:
        nonlocal status
        if status == "pass":
            status = "unknown"
        reasons.append(reason)

    m = summary.mean
    cv = summary.cv_percent
    ccv = summary.clean_cv_percent
    fr = summary.failure_rate
    no = summary.n_outliers

    # Check if any thresholds are configured
    has_threshold = any(x is not None for x in [
        rule.max_mean, rule.min_mean, rule.max_cv_percent,
        rule.max_clean_cv_percent, rule.max_failure_rate,
        rule.max_outliers, rule.target_mean, rule.max_abs_error_from_target,
        rule.max_delta_from_baseline, rule.max_relative_delta_from_baseline,
    ])
    if not has_threshold:
        _unknown("no evaluable thresholds configured")

    # Hard thresholds with non-finite checks
    if rule.max_mean is not None:
        if not _finite(m): _unknown("mean is non-finite for max_mean")
        elif m > rule.max_mean: _fail(f"mean {m:.4g} > max_mean {rule.max_mean}")

    if rule.min_mean is not None:
        if not _finite(m): _unknown("mean is non-finite for min_mean")
        elif m < rule.min_mean: _fail(f"mean {m:.4g} < min_mean {rule.min_mean}")

    if rule.max_cv_percent is not None:
        if not _finite(cv): _unknown("cv_percent is non-finite for max_cv_percent")
        elif cv > rule.max_cv_percent: _fail(f"CV {cv:.4g}% > max_cv_percent {rule.max_cv_percent}%")

    if rule.max_clean_cv_percent is not None:
        if not _finite(ccv): _unknown("clean_cv_percent is non-finite for max_clean_cv_percent")
        elif ccv > rule.max_clean_cv_percent: _fail(f"clean CV {ccv:.4g}% > max_clean_cv_percent {rule.max_clean_cv_percent}%")

    if rule.max_failure_rate is not None:
        if not _finite(fr): _unknown("failure_rate is non-finite for max_failure_rate")
        elif fr > rule.max_failure_rate: _fail(f"failure rate {fr:.4g} > max_failure_rate {rule.max_failure_rate}")

    if rule.max_outliers is not None and no > rule.max_outliers:
        _fail(f"outliers {no} > max_outliers {rule.max_outliers}")

    if rule.target_mean is not None and rule.max_abs_error_from_target is not None:
        if not _finite(m): _unknown("mean is non-finite for target error")
        else:
            err = abs(m - rule.target_mean)
            if err > rule.max_abs_error_from_target:
                _fail(f"|mean - target| {err:.4g} > max_abs_error {rule.max_abs_error_from_target}")

    # Baseline delta
    if status in ("pass", "unknown") and baseline_summary is not None:
        bm = baseline_summary.mean
        if _finite(m) and _finite(bm):
            delta = abs(m - bm)
            if rule.max_delta_from_baseline is not None and delta > rule.max_delta_from_baseline:
                _warn(f"delta from baseline {delta:.4g} > {rule.max_delta_from_baseline}")
            if rule.max_relative_delta_from_baseline is not None and abs(bm) > 1e-12:
                rel = delta / abs(bm)
                if rel > rule.max_relative_delta_from_baseline:
                    _warn(f"relative delta from baseline {rel:.4g} > {rule.max_relative_delta_from_baseline}")
        elif (rule.max_delta_from_baseline is not None or rule.max_relative_delta_from_baseline is not None) and not (_finite(m) and _finite(bm)):
            _unknown("baseline or current mean is non-finite for delta rule")

    return MetricLevelDecision(
        metric_name=summary.metric_name,
        tolerance_level_um=summary.tolerance_level_um,
        status=status,
        reasons=tuple(reasons),
        mean=summary.mean,
        cv_percent=summary.cv_percent,
        clean_cv_percent=summary.clean_cv_percent,
        failure_rate=summary.failure_rate,
        n_outliers=summary.n_outliers,
    )



def recommend_metric_tolerance(
    curve: SweepMetricCurve,
    rule: MetricAcceptanceRule,
) -> MetricToleranceRecommendation:
    """Recommend the maximum acceptable tolerance for one metric.

    Parameters
    ----------
    curve : SweepMetricCurve
    rule : MetricAcceptanceRule

    Returns
    -------
    MetricToleranceRecommendation
    """
    if not curve.summaries:
        return MetricToleranceRecommendation(
            metric_name=rule.metric_name,
            reason_summary=("no level summaries available",),
        )

    baseline = curve.summaries[0]  # lowest tolerance level
    decisions: list[MetricLevelDecision] = []
    for s in curve.summaries:
        decisions.append(evaluate_metric_level(s, rule, baseline_summary=baseline))

    # Determine boundaries (ascending tolerance order)
    recommended: float | None = None
    first_warning: float | None = None
    first_failure: float | None = None
    last_valid_pass: float | None = None
    expanded_blocked = False

    for d in decisions:
        if d.status == "fail":
            if first_failure is None:
                first_failure = d.tolerance_level_um
            expanded_blocked = True
            break
        if d.status == "warning":
            if first_warning is None:
                first_warning = d.tolerance_level_um
            expanded_blocked = True
        if d.status == "unknown":
            expanded_blocked = True
        if d.status == "pass" and not expanded_blocked:
            last_valid_pass = d.tolerance_level_um

    recommended = last_valid_pass

    # Knee candidate from curve
    knee: float | None = None
    if curve.largest_mean_delta_index is not None:
        idx = curve.largest_mean_delta_index
        if idx + 1 < len(curve.levels_um):
            knee = curve.levels_um[idx + 1]

    # Build summary
    reasons: list[str] = []
    for d in decisions:
        if d.reasons:
            reasons.append(f"{int(d.tolerance_level_um)}um: {', '.join(d.reasons)}")

    return MetricToleranceRecommendation(
        metric_name=rule.metric_name,
        recommended_max_tolerance_um=recommended,
        first_warning_tolerance_um=first_warning,
        first_failure_tolerance_um=first_failure,
        status_by_level=tuple(decisions),
        knee_candidate_um=knee,
        reason_summary=tuple(reasons),
    )


# ===================================================================
# Full envelope recommendation
# ===================================================================


def recommend_tolerance_envelope(
    report: SweepAnalysisReport,
    rules: Sequence[MetricAcceptanceRule],
) -> SweepToleranceRecommendation:
    """Run recommendation rules against a sweep analysis report.

    Parameters
    ----------
    report : SweepAnalysisReport
    rules : sequence of MetricAcceptanceRule
        Rules are matched to curves by ``metric_name``.

    Returns
    -------
    SweepToleranceRecommendation
    """
    notes: list[str] = []
    rule_map = {r.metric_name: r for r in rules}
    curve_map = {c.metric_name: c for c in report.metric_curves}
    metric_recs: list[MetricToleranceRecommendation] = []

    matched_metrics = set()

    for rule in rules:
        curve = curve_map.get(rule.metric_name)
        if curve is None:
            notes.append(f"no curve for rule metric={rule.metric_name}")
            continue
        matched_metrics.add(rule.metric_name)
        metric_recs.append(recommend_metric_tolerance(curve, rule))

    # Add curves without matching rules
    for c in report.metric_curves:
        if c.metric_name not in matched_metrics:
            metric_recs.append(MetricToleranceRecommendation(
                metric_name=c.metric_name,
                reason_summary=("no rule provided",),
            ))

    # Overall recommendation: minimum non-None recommendation
    non_none = [r.recommended_max_tolerance_um for r in metric_recs
                if r.recommended_max_tolerance_um is not None]
    overall = min(non_none) if non_none else None

    # Limiting metrics: whose recommendation equals overall, or whose first_failure is first level
    limiting: list[str] = []
    for r in metric_recs:
        if overall is not None and r.recommended_max_tolerance_um == overall:
            limiting.append(r.metric_name)
        elif overall is None and r.first_failure_tolerance_um is not None:
            # Check if this metric fails at the first level
            if r.first_failure_tolerance_um == report.levels_um[0]:
                limiting.append(r.metric_name)

    return SweepToleranceRecommendation(
        tolerance_parameter=report.tolerance_parameter,
        levels_um=report.levels_um,
        metric_recommendations=tuple(metric_recs),
        overall_recommended_max_tolerance_um=overall,
        limiting_metrics=tuple(sorted(set(limiting))),
        notes=tuple(notes),
    )


# ===================================================================
# Dataclasses
# ===================================================================


@dataclasses.dataclass(frozen=True)
class MetricLevelDecision:
    """Result of evaluating one tolerance level against a rule.

    Parameters
    ----------
    metric_name : str
    tolerance_level_um : float
    status : str
        ``"pass"``, ``"warning"``, ``"fail"``, or ``"unknown"``.
    reasons : tuple of str
    mean : float
    cv_percent : float
    clean_cv_percent : float
    failure_rate : float
    n_outliers : int
    """
    metric_name: str = ""
    tolerance_level_um: float = 0.0
    status: str = "unknown"
    reasons: tuple[str, ...] = ()
    mean: float = float("nan")
    cv_percent: float = float("nan")
    clean_cv_percent: float = float("nan")
    failure_rate: float = float("nan")
    n_outliers: int = 0


@dataclasses.dataclass(frozen=True)
class MetricToleranceRecommendation:
    """Recommended max tolerance for one metric across all levels.

    Parameters
    ----------
    metric_name : str
    recommended_max_tolerance_um : float or None
    first_warning_tolerance_um : float or None
    first_failure_tolerance_um : float or None
    status_by_level : tuple of MetricLevelDecision
    knee_candidate_um : float or None
    reason_summary : tuple of str
    """
    metric_name: str = ""
    recommended_max_tolerance_um: float | None = None
    first_warning_tolerance_um: float | None = None
    first_failure_tolerance_um: float | None = None
    status_by_level: tuple[MetricLevelDecision, ...] = ()
    knee_candidate_um: float | None = None
    reason_summary: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SweepToleranceRecommendation:
    """Overall tolerance envelope recommendation.

    Parameters
    ----------
    tolerance_parameter : str
    levels_um : tuple of float
    metric_recommendations : tuple of MetricToleranceRecommendation
    overall_recommended_max_tolerance_um : float or None
    limiting_metrics : tuple of str
    notes : tuple of str
    """
    tolerance_parameter: str = ""
    levels_um: tuple[float, ...] = ()
    metric_recommendations: tuple[MetricToleranceRecommendation, ...] = ()
    overall_recommended_max_tolerance_um: float | None = None
    limiting_metrics: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
