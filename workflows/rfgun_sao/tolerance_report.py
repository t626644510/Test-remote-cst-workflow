"""Deterministic tolerance analysis report serialization — TAM5.

Converts ``ToleranceAnalysisReport`` to JSON-serialisable dicts and
markdown tables.  No file I/O, no CST, no external dependencies.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from workflows.rfgun_sao.tolerance_statistics import (
    CleanMetricSummary,
    MetricSummary,
)
from workflows.rfgun_sao.tolerance_sensitivity import (
    ParameterSensitivity,
    SensitivityAnalysisReport,
)
from workflows.rfgun_sao.tolerance_analysis import (
    ToleranceAnalysisReport,
)


# ===================================================================
# Value serialisers
# ===================================================================


def _v(val: Any) -> Any:
    """Convert a value to a JSON-serialisable primitive.

    ``float`` → ``float`` (NaN/inf becomes ``"nan"``/``"inf"``/``"-inf"``).
    ``np.generic`` → native Python type.
    """
    if isinstance(val, float):
        if math.isnan(val):
            return "nan"
        if math.isinf(val):
            return "-inf" if val < 0 else "inf"
        return val
    # numpy types
    if hasattr(val, "dtype"):
        if isinstance(val, (int, float)):
            return _v(float(val))
        return val.item()  # converts np.int64/np.float64/np.bool_
    if isinstance(val, (int, bool)):
        return val
    if val is None:
        return None
    return val


def _maybe_none(val: Any, transform=str) -> Any:
    """Return ``None`` if *val* is NaN, else ``transform(val)``."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return transform(val)


# ===================================================================
# Individual serialisers
# ===================================================================


def metric_summary_to_dict(summary: MetricSummary) -> dict[str, Any]:
    """Convert a ``MetricSummary`` to a JSON-serialisable dict."""
    return {
        "name": summary.name,
        "n_total": _v(summary.n_total),
        "n_finite": _v(summary.n_finite),
        "mean": _v(summary.mean),
        "std": _v(summary.std),
        "min": _v(summary.min_val),
        "max": _v(summary.max_val),
        "cv_percent": _v(summary.cv_percent),
    }


def clean_metric_summary_to_dict(summary: CleanMetricSummary) -> dict[str, Any]:
    """Convert a ``CleanMetricSummary`` to a JSON-serialisable dict."""
    return {
        "name": summary.name,
        "raw_cv_percent": _v(summary.raw.cv_percent),
        "clean_cv_percent": _v(summary.clean.cv_percent),
        "cv_delta_percent": _v(summary.cv_delta_percent),
        "cv_delta_relative": _v(summary.cv_delta_relative),
        "n_outliers": summary.outliers.n_outliers,
        "method": summary.outliers.method,
        "n_finite_raw": summary.raw.n_finite,
        "n_finite_clean": summary.clean.n_finite,
    }


def sensitivity_report_to_dict(report: SensitivityAnalysisReport | None) -> dict[str, Any] | None:
    """Convert a ``SensitivityAnalysisReport`` to a JSON-serialisable dict."""
    if report is None:
        return None
    return {
        "method": report.method,
        "n_rows": report.n_rows,
        "metric_reports": [
            {
                "metric_name": mr.metric_name,
                "top_parameter": mr.top_parameter,
                "sensitivities": [
                    {
                        "parameter": s.parameter_name,
                        "score": _v(s.score),
                        "abs_score": _v(s.abs_score),
                        "direction": s.direction,
                        "rank": s.rank,
                        "n_finite": s.n_finite,
                    }
                    for s in mr.sensitivities
                ],
            }
            for mr in report.metric_reports
        ],
    }


def tolerance_analysis_report_to_dict(report: ToleranceAnalysisReport) -> dict[str, Any]:
    """Convert a full ``ToleranceAnalysisReport`` to a JSON-serialisable dict."""
    return {
        "source_row_count": report.dataset.source_row_count,
        "accepted_row_count": report.dataset.accepted_row_count,
        "skipped_row_count": report.dataset.skipped_row_count,
        "param_count": len(report.dataset.param_names),
        "metric_count": len(report.dataset.metric_names),
        "param_names": list(report.dataset.param_names),
        "metric_names": list(report.dataset.metric_names),
        "basic_summaries": [metric_summary_to_dict(s) for s in report.basic_summaries],
        "clean_summaries": (
            [clean_metric_summary_to_dict(s) for s in report.clean_summaries]
            if report.clean_summaries else []
        ),
        "sensitivity": sensitivity_report_to_dict(report.sensitivity),
        "notes": list(report.notes),
    }


# ===================================================================
# Markdown rendering
# ===================================================================


def _row(values: list[str], widths: list[int]) -> str:
    """Format one markdown table row."""
    cells = [str(v).ljust(w) for v, w in zip(values, widths)]
    return "| " + " | ".join(cells) + " |"


def _sep(widths: list[int]) -> str:
    """Format a markdown separator row."""
    return "| " + " | ".join("-" * w for w in widths) + " |"


def render_tolerance_markdown(
    report: ToleranceAnalysisReport,
    *,
    title: str = "WF3 tolerance analysis",
) -> str:
    """Render a ``ToleranceAnalysisReport`` as markdown.

    Parameters
    ----------
    report : ToleranceAnalysisReport
    title : str

    Returns
    -------
    str
        Deterministic markdown string.
    """
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")

    ds = report.dataset
    lines.append(f"- Source rows: **{ds.source_row_count}**")
    lines.append(f"- Accepted rows: **{ds.accepted_row_count}**")
    lines.append(f"- Skipped rows: **{ds.skipped_row_count}**")
    if ds.param_names:
        lines.append(f"- Parameters: **{', '.join(ds.param_names)}**")
    if ds.metric_names:
        lines.append(f"- Metrics: **{', '.join(ds.metric_names)}**")
    lines.append("")

    if report.notes:
        for note in report.notes:
            lines.append(f"> {note}")
        lines.append("")

    # Basic CV table
    if report.basic_summaries:
        lines.append("## Basic CV summary")
        lines.append("")
        headers = ["Metric", "N", "Mean", "Std", "Min", "Max", "CV%"]
        widths = [18, 4, 12, 12, 12, 12, 8]
        lines.append(_row(headers, widths))
        lines.append(_sep(widths))
        for s in report.basic_summaries:
            lines.append(_row(
                [s.name, str(s.n_finite), _fmt(s.mean), _fmt(s.std),
                 _fmt(s.min_val), _fmt(s.max_val), _fmt(s.cv_percent)],
                widths,
            ))
        lines.append("")

    # Clean CV table
    if report.clean_summaries:
        # Derive method from summaries
        methods = frozenset(cs.outliers.method for cs in report.clean_summaries if cs.outliers.method)
        method_label = "mixed" if len(methods) > 1 else (next(iter(methods)) if methods else "iqr")
        lines.append(f"## Clean CV summary ({method_label})")
        lines.append("")
        headers2 = ["Metric", "Outliers", "Raw CV%", "Clean CV%", "CV Δ%", "Method"]
        widths2 = [18, 8, 9, 10, 8, 7]
        lines.append(_row(headers2, widths2))
        lines.append(_sep(widths2))
        for cs in report.clean_summaries:
            lines.append(_row(
                [cs.name, str(cs.outliers.n_outliers), _fmt(cs.raw.cv_percent),
                 _fmt(cs.clean.cv_percent), _fmt(cs.cv_delta_percent),
                 cs.outliers.method or ""],
                widths2,
            ))
        lines.append("")

    # Sensitivity table
    if report.sensitivity:
        lines.append(f"## Sensitivity ({report.sensitivity.method})")
        lines.append("")
        headers3 = ["Metric", "Rank", "Parameter", "Score", "Direction", "N"]
        widths3 = [18, 5, 12, 8, 10, 4]
        lines.append(_row(headers3, widths3))
        lines.append(_sep(widths3))
        for mr in report.sensitivity.metric_reports:
            for s in mr.sensitivities:
                rank_str = str(s.rank) if s.rank is not None else ""
                lines.append(_row(
                    [mr.metric_name, rank_str, s.parameter_name,
                     _fmt(s.score), s.direction, str(s.n_finite)],
                    widths3,
                ))
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated by tolerance analysis (no-CST)_")
    return "\n".join(lines)


def _fmt(val: float) -> str:
    """Format a float for markdown tables.

    NaN → ``"nan"``, inf → ``"inf"``/``"-inf"``.
    """
    if isinstance(val, float):
        if math.isnan(val):
            return "nan"
        if math.isinf(val):
            return "-inf" if val < 0 else "inf"
        return f"{val:.4g}"
    return str(val)
