"""No-CST tests for TSE4 tolerance sweep recommendation.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from workflows.rfgun_sao.tolerance_sweep_recommendation import (
    MetricAcceptanceRule,
    MetricLevelDecision,
    MetricToleranceRecommendation,
    SweepToleranceRecommendation,
    default_field_flatness_rule,
    evaluate_metric_level,
    recommend_metric_tolerance,
    recommend_tolerance_envelope,
)
from workflows.rfgun_sao.tolerance_sweep_analysis import (
    SweepAnalysisReport,
    SweepMetricCurve,
    SweepMetricLevelSummary,
    build_metric_curves,
)


def _summary(metric, level_um, mean=0.05, cv=5.0, ccv=5.0, fr=0.0, no=0, n=5):
    return SweepMetricLevelSummary(
        tolerance_parameter="offset1", tolerance_level_um=level_um,
        tolerance_level_mm=level_um / 1000, metric_name=metric,
        accepted_row_count=n, source_row_count=n, skipped_row_count=0,
        mean=mean, std=mean * cv / 100, min_val=mean * 0.9, max_val=mean * 1.1,
        cv_percent=cv, clean_cv_percent=ccv, n_outliers=no,
        failure_rate=fr,
    )


def _curve(metric, level_ums, means, cvs=None):
    if cvs is None:
        cvs = [5.0] * len(level_ums)
    summaries = [_summary(metric, lu, m, cv=cv) for lu, m, cv in zip(level_ums, means, cvs)]
    means_t = tuple(s.mean for s in summaries)
    cvs_t = tuple(s.cv_percent for s in summaries)
    return SweepMetricCurve(
        tolerance_parameter="offset1", metric_name=metric,
        levels_um=tuple(level_ums), summaries=tuple(summaries),
        mean_values=means_t, cv_values=cvs_t,
        clean_cv_values=tuple(s.clean_cv_percent for s in summaries),
        failure_rates=tuple(s.failure_rate for s in summaries),
        monotonic_mean="increasing", monotonic_cv="flat",
        largest_mean_delta_index=1,
    )


# ===================================================================
# Level evaluation
# ===================================================================


class TestLevelEvaluation:
    def test_pass_when_thresholds_satisfied(self):
        s = _summary("ff", 3.0, mean=0.02, cv=5.0)
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08)
        d = evaluate_metric_level(s, rule)
        assert d.status == "pass"

    def test_fail_on_max_mean(self):
        s = _summary("ff", 30.0, mean=0.15)
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08)
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"
        assert any("max_mean" in r for r in d.reasons)

    def test_fail_on_min_mean(self):
        s = _summary("ff", 3.0, mean=0.01)
        rule = MetricAcceptanceRule(metric_name="ff", min_mean=0.02)
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"

    def test_fail_on_max_cv(self):
        s = _summary("ff", 3.0, cv=60.0)
        rule = MetricAcceptanceRule(metric_name="ff", max_cv_percent=50.0)
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"

    def test_fail_on_max_clean_cv(self):
        s = _summary("ff", 3.0, ccv=60.0)
        rule = MetricAcceptanceRule(metric_name="ff", max_clean_cv_percent=50.0)
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"

    def test_fail_on_max_failure_rate(self):
        s = _summary("ff", 3.0, fr=0.3)
        rule = MetricAcceptanceRule(metric_name="ff", max_failure_rate=0.2)
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"

    def test_fail_on_max_outliers(self):
        s = _summary("ff", 3.0, no=5)
        rule = MetricAcceptanceRule(metric_name="ff", max_outliers=3)
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"

    def test_fail_on_target_abs_error(self):
        s = _summary("ff", 3.0, mean=0.1)
        rule = MetricAcceptanceRule(
            metric_name="ff", target_mean=0.05, max_abs_error_from_target=0.02,
        )
        d = evaluate_metric_level(s, rule)
        assert d.status == "fail"

    def test_warning_on_delta_from_baseline(self):
        baseline = _summary("ff", 3.0, mean=0.02)
        current = _summary("ff", 10.0, mean=0.08)
        rule = MetricAcceptanceRule(metric_name="ff", max_delta_from_baseline=0.05)
        d = evaluate_metric_level(current, rule, baseline_summary=baseline)
        assert d.status == "warning"  # delta = 0.06 > 0.05 -> warning
        rule2 = MetricAcceptanceRule(metric_name="ff", max_delta_from_baseline=0.03)
        d2 = evaluate_metric_level(current, rule2, baseline_summary=baseline)
        assert d2.status == "warning" or d2.status == "fail"


# ===================================================================
# Per-metric recommendation
# ===================================================================


class TestMetricRecommendation:
    def test_all_pass_recommended_max(self):
        curve = _curve("ff", [3, 10, 30], [0.02, 0.03, 0.04])
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08)
        rec = recommend_metric_tolerance(curve, rule)
        assert rec.recommended_max_tolerance_um == 30.0

    def test_first_level_fails(self):
        curve = _curve("ff", [3, 10, 30], [0.15, 0.02, 0.03])
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08)
        rec = recommend_metric_tolerance(curve, rule)
        assert rec.recommended_max_tolerance_um is None

    def test_pass_then_fail(self):
        curve = _curve("ff", [3, 10, 30], [0.02, 0.04, 0.15])
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08)
        rec = recommend_metric_tolerance(curve, rule)
        assert rec.recommended_max_tolerance_um == 10.0
        assert rec.first_failure_tolerance_um == 30.0

    def test_pass_then_warning(self):
        curve = _curve("ff", [3, 10, 30], [0.02, 0.04, 0.07])
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08, max_delta_from_baseline=0.03)
        rec = recommend_metric_tolerance(curve, rule)
        # 3um pass, 10um warning (delta 0.02 > 0.03? no — 0.02 < 0.03 so pass)
        # Actually 0.04-0.02=0.02 < 0.03 so pass; 0.07-0.02=0.05 > 0.03 so warning
        assert rec.first_warning_tolerance_um == 30.0

    def test_knee_candidate(self):
        curve = _curve("ff", [3, 10, 30], [0.02, 0.04, 0.15])
        rule = MetricAcceptanceRule(metric_name="ff", max_mean=0.08)
        rec = recommend_metric_tolerance(curve, rule)
        assert rec.knee_candidate_um is not None

    def test_empty_curve(self):
        curve = SweepMetricCurve()
        rule = MetricAcceptanceRule(metric_name="ff")
        rec = recommend_metric_tolerance(curve, rule)
        assert rec.recommended_max_tolerance_um is None
        assert "no level summaries" in rec.reason_summary[0]


# ===================================================================
# Field_flatness synthetic example
# ===================================================================


class TestFieldFlatnessExample:
    def test_offset1_envelope(self):
        """offset1 sweep: 3um pass, 10um pass/warning, 30um fail."""
        curve = _curve("field_flatness", [3, 10, 30], [0.02, 0.04, 0.15])
        rule = MetricAcceptanceRule(
            metric_name="field_flatness", max_mean=0.08,
            max_cv_percent=50.0, max_delta_from_baseline=0.05,
            direction="smaller_is_better",
        )
        rec = recommend_metric_tolerance(curve, rule)
        assert rec.recommended_max_tolerance_um == 10.0
        assert rec.first_failure_tolerance_um == 30.0

    def test_full_envelope(self):
        """Multiple metrics; overall limited by field_flatness."""
        curve_ff = _curve("field_flatness", [3, 10, 30], [0.02, 0.04, 0.15])
        curve_q0 = _curve("q0", [3, 10, 30], [18000, 17900, 17800])
        report = SweepAnalysisReport(
            tolerance_parameter="offset1",
            levels_um=(3, 10, 30),
            metric_curves=(curve_ff, curve_q0),
            metric_names=("field_flatness", "q0"),
        )
        rules = [
            MetricAcceptanceRule(metric_name="field_flatness", max_mean=0.08),
            MetricAcceptanceRule(metric_name="q0", min_mean=15000),
        ]
        envelope = recommend_tolerance_envelope(report, rules)
        assert envelope.overall_recommended_max_tolerance_um == 10.0
        assert "field_flatness" in envelope.limiting_metrics


# ===================================================================
# Full envelope
# ===================================================================


class TestEnvelope:
    def test_limiting_metrics(self):
        curve_a = _curve("a", [3, 10, 30], [10, 10, 10])
        curve_b = _curve("b", [3, 10, 30], [0.02, 0.04, 0.15])
        report = SweepAnalysisReport(
            tolerance_parameter="p", levels_um=(3, 10, 30),
            metric_curves=(curve_a, curve_b),
            metric_names=("a", "b"),
        )
        rules = [
            MetricAcceptanceRule(metric_name="a", max_mean=20),
            MetricAcceptanceRule(metric_name="b", max_mean=0.08),
        ]
        env = recommend_tolerance_envelope(report, rules)
        assert env.overall_recommended_max_tolerance_um == 10.0
        assert "b" in env.limiting_metrics

    def test_metric_without_rule(self):
        curve = _curve("orphan", [3, 10], [1.0, 2.0])
        report = SweepAnalysisReport(
            tolerance_parameter="p", levels_um=(3, 10),
            metric_curves=(curve,),
            metric_names=("orphan",),
        )
        env = recommend_tolerance_envelope(report, [])
        assert len(env.metric_recommendations) == 1
        assert "no rule provided" in env.metric_recommendations[0].reason_summary

    def test_default_field_flatness_rule(self):
        rule = default_field_flatness_rule()
        assert rule.metric_name == "field_flatness"
        assert rule.max_mean == 0.08
        assert rule.direction == "smaller_is_better"


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_factory_import(self):
        import workflows.rfgun_sao.tolerance_sweep_recommendation as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "cst_optimization.factory" not in text
        assert "cst_optimization.workflows.recovery" not in text

    def test_no_jsonl_excel(self):
        import workflows.rfgun_sao.tolerance_sweep_recommendation as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text
        assert ".xlsx" not in text
        assert "openpyxl" not in text
        assert "xlrd" not in text
