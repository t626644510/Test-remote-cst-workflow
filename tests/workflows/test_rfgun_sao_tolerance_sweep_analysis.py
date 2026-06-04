"""No-CST tests for TSE3 tolerance sweep analysis.

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

from workflows.rfgun_sao.tolerance_sweep_analysis import (
    SweepAnalysisReport,
    SweepMetricCurve,
    SweepMetricLevelSummary,
    analyze_tolerance_sweep,
    build_metric_curves,
    classify_monotonic,
    largest_adjacent_delta_index,
    summarize_sweep_group,
)
from workflows.rfgun_sao.tolerance_sweep_dataset import (
    ToleranceSweepDataset,
    ToleranceSweepGroup,
    build_sweep_group_from_records,
    build_sweep_dataset,
)
from workflows.rfgun_sao.tolerance_dataset import (
    ToleranceDataset,
)


def _record(val, m1_val=None):
    if m1_val is None:
        m1_val = float(val)
    return {
        "status": "success", "solver_ok": True,
        "parameter_identity": {"param_names": ["a"], "values": [float(val)], "parameter_key": ""},
        "raw_metrics": {"m1": m1_val, "m2": float(val * 2)},
    }


def _group(param, level_um, records):
    return build_sweep_group_from_records(records, param, level_um, "um")


# ===================================================================
# Monotonicity
# ===================================================================


class TestMonotonic:
    def test_increasing(self):
        assert classify_monotonic([1.0, 2.0, 3.0]) == "increasing"

    def test_decreasing(self):
        assert classify_monotonic([3.0, 2.0, 1.0]) == "decreasing"

    def test_flat(self):
        assert classify_monotonic([5.0, 5.0, 5.0]) == "flat"

    def test_non_monotonic(self):
        assert classify_monotonic([1.0, 3.0, 2.0]) == "non_monotonic"

    def test_unknown_less_than_2(self):
        assert classify_monotonic([1.0]) == "unknown"

    def test_ignores_nan(self):
        assert classify_monotonic([1.0, float("nan"), 3.0]) == "increasing"


# ===================================================================
# Largest adjacent delta
# ===================================================================


class TestLargestDelta:
    def test_known_largest(self):
        idx = largest_adjacent_delta_index([1.0, 2.0, 10.0])
        assert idx == 1  # delta between 2 and 10 is largest

    def test_returns_first_max(self):
        idx = largest_adjacent_delta_index([1.0, 10.0, 11.0])
        assert idx == 0

    def test_skips_nan(self):
        idx = largest_adjacent_delta_index([1.0, float("nan"), 10.0])
        assert idx is None

    def test_insufficient_values(self):
        assert largest_adjacent_delta_index([1.0]) is None
        assert largest_adjacent_delta_index([]) is None

    def test_all_nan(self):
        assert largest_adjacent_delta_index([float("nan"), float("nan")]) is None


# ===================================================================
# Group summary
# ===================================================================


class TestGroupSummary:
    def test_one_summary_per_metric(self):
        records = [_record(i) for i in range(5)]
        g = _group("offset1", 3.0, records)
        summaries = summarize_sweep_group(g)
        assert len(summaries) == 2  # m1, m2
        assert summaries[0].metric_name in ("m1", "m2")
        assert summaries[0].accepted_row_count == 5

    def test_failure_rate_computed(self):
        # Create a group with mixed success/failure
        good = [{"status": "success", "solver_ok": True,
                 "parameter_identity": {"param_names": ["a"], "values": [1.0], "parameter_key": ""},
                 "raw_metrics": {"m1": 10.0}}]
        # Use build_sweep_group_from_records to create a group
        # where some records are non-success
        mixed = good + [{"status": "solver_failed", "solver_ok": False,
                         "parameter_identity": {"param_names": ["a"], "values": [2.0], "parameter_key": ""},
                         "raw_metrics": {}}]
        g = _group("offset1", 3.0, mixed)
        summaries = summarize_sweep_group(g)
        assert summaries[0].failure_rate == 0.5

    def test_clean_cv_disabled(self):
        records = [_record(i) for i in range(5)]
        g = _group("offset1", 3.0, records)
        summaries = summarize_sweep_group(g, include_clean_cv=False)
        assert np.isnan(summaries[0].clean_cv_percent)
        assert summaries[0].n_outliers == 0

    def test_clean_cv_enabled(self):
        records = [_record(i, m1_val=float(i * 10)) for i in range(5)]
        g = _group("offset1", 3.0, records)
        summaries = summarize_sweep_group(g, include_clean_cv=True)
        # With 5 unique values, clean CV should be finite
        for s in summaries:
            if s.metric_name == "m1":
                assert np.isfinite(s.clean_cv_percent) or s.n_outliers == 0

    def test_metric_names_filter(self):
        records = [_record(i) for i in range(5)]
        g = _group("offset1", 3.0, records)
        summaries = summarize_sweep_group(g, metric_names=["m1"])
        assert len(summaries) == 1
        assert summaries[0].metric_name == "m1"


# ===================================================================
# Curve building
# ===================================================================


class TestCurveBuilding:
    def test_groups_by_metric(self):
        g3 = _group("offset1", 3.0, [_record(i) for i in range(3)])
        g10 = _group("offset1", 10.0, [_record(i) for i in range(4)])
        s3 = summarize_sweep_group(g3)
        s10 = summarize_sweep_group(g10)
        curves = build_metric_curves(list(s3) + list(s10))
        assert len(curves) == 2  # m1, m2

    def test_monotonic_mean_set(self):
        records_3um = [_record(i, m1_val=i * 1.0) for i in range(3)]
        records_30um = [_record(i, m1_val=i * 5.0) for i in range(3)]
        g3 = _group("offset1", 3.0, records_3um)
        g30 = _group("offset1", 30.0, records_30um)
        s3 = summarize_sweep_group(g3)
        s30 = summarize_sweep_group(g30)
        curves = build_metric_curves(list(s3) + list(s30))
        for c in curves:
            assert c.monotonic_mean in ("increasing", "decreasing", "flat", "non_monotonic", "unknown")

    def test_largest_delta_index(self):
        records_3 = [_record(i, m1_val=10.0) for i in range(3)]
        records_10 = [_record(i, m1_val=20.0) for i in range(3)]
        records_30 = [_record(i, m1_val=100.0) for i in range(3)]
        g3 = _group("offset1", 3.0, records_3)
        g10 = _group("offset1", 10.0, records_10)
        g30 = _group("offset1", 30.0, records_30)
        s3 = summarize_sweep_group(g3)
        s10 = summarize_sweep_group(g10)
        s30 = summarize_sweep_group(g30)
        curves = build_metric_curves(list(s3) + list(s10) + list(s30))
        for c in curves:
            if c.largest_mean_delta_index is not None:
                assert 0 <= c.largest_mean_delta_index < len(c.levels_um) - 1

    def test_levels_sorted(self):
        g30 = _group("offset1", 30.0, [_record(i) for i in range(3)])
        g3 = _group("offset1", 3.0, [_record(i) for i in range(3)])
        s30 = summarize_sweep_group(g30)
        s3 = summarize_sweep_group(g3)
        curves = build_metric_curves(list(s30) + list(s3))
        for c in curves:
            assert list(c.levels_um) == sorted(c.levels_um)


# ===================================================================
# Full sweep analysis
# ===================================================================


class TestSweepAnalysis:
    def test_full_analysis(self):
        spec = [
            {"tolerance_parameter": "offset1", "tolerance_level": 3, "records": [_record(i) for i in range(5)]},
            {"tolerance_parameter": "offset1", "tolerance_level": 30, "records": [_record(i) for i in range(5)]},
        ]
        from workflows.rfgun_sao.tolerance_sweep_dataset import build_sweep_dataset_from_record_groups
        sweep = build_sweep_dataset_from_record_groups(spec)
        report = analyze_tolerance_sweep(sweep)
        assert report.tolerance_parameter == "offset1"
        assert len(report.metric_curves) >= 1
        assert len(report.levels_um) == 2

    def test_metric_names_order(self):
        spec = [
            {"tolerance_parameter": "offset1", "tolerance_level": 3, "records": [_record(i) for i in range(3)]},
        ]
        from workflows.rfgun_sao.tolerance_sweep_dataset import build_sweep_dataset_from_record_groups
        sweep = build_sweep_dataset_from_record_groups(spec)
        report = analyze_tolerance_sweep(sweep, metric_names=["m2", "m1"])
        assert [c.metric_name for c in report.metric_curves] == ["m2", "m1"]

    def test_field_flatness_degradation(self):
        """Synthetic field_flatness degradation: 3um low, 30um high."""
        def _ff_rec(val, ff):
            return {
                "status": "success", "solver_ok": True,
                "parameter_identity": {"param_names": ["a"], "values": [float(val)], "parameter_key": ""},
                "raw_metrics": {"field_flatness": ff},
            }
        records_3um = [_ff_rec(i, 0.02) for i in range(5)]
        records_30um = [_ff_rec(i, 0.15) for i in range(5)]
        from workflows.rfgun_sao.tolerance_sweep_dataset import build_sweep_group_from_records
        g3 = build_sweep_group_from_records(records_3um, "offset1", 3.0, "um")
        g30 = build_sweep_group_from_records(records_30um, "offset1", 30.0, "um")
        sweep = build_sweep_dataset([g3, g30])
        report = analyze_tolerance_sweep(sweep, metric_names=["field_flatness"])
        # Find field_flatness curve
        curve = [c for c in report.metric_curves if c.metric_name == "field_flatness"]
        assert len(curve) == 1
        c = curve[0]
        assert c.monotonic_mean == "increasing"
        assert c.mean_values[1] > c.mean_values[0]
        assert c.largest_mean_delta_index is not None


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_factory_import(self):
        import workflows.rfgun_sao.tolerance_sweep_analysis as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "cst_optimization.factory" not in text
        assert "cst_optimization.workflows.recovery" not in text

    def test_no_jsonl_excel(self):
        import workflows.rfgun_sao.tolerance_sweep_analysis as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert ".jsonl" not in text
        assert ".xlsx" not in text
        assert "openpyxl" not in text
        assert "xlrd" not in text
