"""No-CST cross-level tolerance campaign analysis.

The command consumes two or more existing evaluation databases and writes an
auditable Markdown report. Tolerance levels are expressed in micrometres (um);
parameter nominal values and perturbations are read in millimetres (mm) and
converted to um for reporting.

Example::

    python -m workflows.rfgun_tolerance.campaign_cli \
        --config config/default.yaml \
        --db 3=runs/tolerance/tolerance_eval_3um.db \
        --db 5=runs/tolerance/tolerance_eval_5um.db \
        --output runs/tolerance/campaign_report.md
"""

from __future__ import annotations

import argparse
import io
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import yaml

from workflows.rfgun_tolerance.sensitivity import (
    SensitivityAnalysisReport,
    analyze_parameter_sensitivity,
)
from workflows.rfgun_tolerance.sweep_analysis import (
    SweepAnalysisReport,
    analyze_tolerance_sweep,
)
from workflows.rfgun_tolerance.sweep_dataset import (
    ToleranceSweepGroup,
    build_sweep_dataset,
    build_sweep_group_from_db,
)
from workflows.rfgun_tolerance.sweep_recommendation import (
    MetricAcceptanceRule,
    recommend_tolerance_envelope,
)


DEFAULT_METRICS = (
    "resonant_freq",
    "coupling_beta",
    "q0",
    "peak_e_field",
    "field_flatness",
    "max_modified_poynting",
    "pulsed_heating",
)

DEFAULT_ACCEPTANCE_RULES = {
    "resonant_freq": {
        # Resonant frequency is converted to absolute target offset in MHz.
        "max_mean": 1.0,
        "max_cv_percent": 50.0,
        "max_failure_rate": 0.20,
        "direction": "smaller_is_better",
    },
    "coupling_beta": {
        "max_cv_percent": 25.0,
        "max_failure_rate": 0.20,
        "direction": "unknown",
    },
    "q0": {
        "max_cv_percent": 20.0,
        "max_failure_rate": 0.20,
        "direction": "larger_is_better",
    },
    "field_flatness": {
        "max_cv_percent": 50.0,
        "max_failure_rate": 0.20,
        "direction": "smaller_is_better",
    },
    "max_modified_poynting": {
        "max_cv_percent": 30.0,
        "max_failure_rate": 0.20,
        "direction": "smaller_is_better",
    },
    "pulsed_heating": {
        "max_cv_percent": 20.0,
        "max_failure_rate": 0.20,
        "direction": "smaller_is_better",
    },
}


@dataclass(frozen=True)
class CampaignDatabase:
    """One tolerance level and its SQLite evaluation database."""

    level_um: float
    path: Path


def parse_database_spec(value: str) -> CampaignDatabase:
    """Parse ``LEVEL_UM=PATH`` into a campaign database reference."""

    level_text, separator, path_text = value.partition("=")
    if not separator or not level_text.strip() or not path_text.strip():
        raise argparse.ArgumentTypeError(
            "database must use LEVEL_UM=PATH, for example 3=runs/3um.db"
        )
    try:
        level_um = float(level_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid tolerance level: {level_text!r}"
        ) from exc
    if not math.isfinite(level_um) or level_um <= 0:
        raise argparse.ArgumentTypeError("tolerance level must be positive")
    return CampaignDatabase(level_um=level_um, path=Path(path_text))


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the campaign-analysis argument parser."""

    parser = argparse.ArgumentParser(
        description="Analyze multiple tolerance evaluation databases.",
    )
    parser.add_argument(
        "--db",
        action="append",
        required=True,
        type=parse_database_spec,
        metavar="LEVEL_UM=PATH",
        help="Tolerance level in um and SQLite DB path; repeat for each level.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="YAML config containing tolerance parameter nominal values.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown output path; print to stdout when omitted.",
    )
    parser.add_argument(
        "--campaign-name",
        default="wf3_tolerance",
        help="Human-readable campaign name used in the report.",
    )
    parser.add_argument(
        "--tolerance-parameter",
        default="tolerance_abs",
        help="Name of the swept tolerance parameter.",
    )
    parser.add_argument(
        "--frequency-target-ghz",
        type=float,
        default=11.424,
        help="Frequency target in GHz for absolute offset reporting.",
    )
    parser.add_argument(
        "--metrics",
        default=",".join(DEFAULT_METRICS),
        help="Comma-separated metric names.",
    )
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the campaign analysis command."""

    args = build_arg_parser().parse_args(argv)
    databases = sorted(args.db, key=lambda item: item.level_um)
    levels = [item.level_um for item in databases]
    if len(databases) < 2:
        print("Error: at least two --db values are required.", file=sys.stderr)
        return 2
    if len(levels) != len(set(levels)):
        print("Error: tolerance levels must be unique.", file=sys.stderr)
        return 2

    missing = [str(item.path) for item in databases if not item.path.is_file()]
    if missing:
        print(f"Error: database not found: {missing[0]}", file=sys.stderr)
        return 1
    if not args.config.is_file():
        print(f"Error: config not found: {args.config}", file=sys.stderr)
        return 1
    if not math.isfinite(args.frequency_target_ghz):
        print("Error: --frequency-target-ghz must be finite.", file=sys.stderr)
        return 2

    metrics = tuple(
        part.strip() for part in args.metrics.split(",") if part.strip()
    )
    if not metrics:
        print("Error: --metrics must contain at least one name.", file=sys.stderr)
        return 2

    try:
        report = build_campaign_markdown(
            databases=databases,
            config_path=args.config,
            campaign_name=args.campaign_name,
            tolerance_parameter=args.tolerance_parameter,
            frequency_target_ghz=args.frequency_target_ghz,
            metric_names=metrics,
        )
    except Exception as exc:
        print(f"Error analyzing tolerance campaign: {exc}", file=sys.stderr)
        return 1

    if args.output is None:
        sys.stdout.write(report)
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    return 0


def build_campaign_markdown(
    *,
    databases: Sequence[CampaignDatabase],
    config_path: Path,
    campaign_name: str,
    tolerance_parameter: str,
    frequency_target_ghz: float,
    metric_names: Sequence[str],
) -> str:
    """Analyze campaign databases and return a Markdown report."""

    groups = _load_groups(databases, tolerance_parameter)
    _convert_offset_metrics(groups, frequency_target_ghz)
    sweep = build_sweep_dataset(groups, tolerance_parameter)
    analysis = analyze_tolerance_sweep(
        sweep,
        metric_names=metric_names,
        include_clean_cv=True,
        clean_method="iqr",
        clean_multiplier=3.0,
    )
    sensitivities = _build_sensitivities(groups, metric_names)
    rank_stability = _build_rank_stability(groups, sensitivities)
    rules = [
        MetricAcceptanceRule(metric_name=name, **settings)
        for name, settings in DEFAULT_ACCEPTANCE_RULES.items()
        if name in metric_names
    ]
    envelope = recommend_tolerance_envelope(analysis, rules)
    nominals = _load_nominals(config_path)

    output = io.StringIO()
    write = output.write
    level_list = ", ".join(_format_level(item.level_um) for item in databases)
    write("# Tolerance Sweep Analysis Report\n\n")
    write(
        f"**Campaign**: `{campaign_name}`  |  **Parameter**: "
        f"`{tolerance_parameter}`  |  **Levels**: {len(databases)} "
        f"({level_list})\n\n"
    )
    _render_data_overview(write, groups)
    _render_metric_tables(write, analysis)
    _render_sensitivities(write, databases, sensitivities, metric_names)
    _render_rank_stability(write, rank_stability, analysis.metric_names)
    _render_recommendation(write, envelope)
    _render_parameter_budget(write, groups, analysis, nominals)
    _render_failure_rates(write, groups)
    total_records = sum(
        group.dataset.source_row_count if group.dataset else 0 for group in groups
    )
    write(
        f"---\n\n*Report generated from {len(groups)} tolerance levels, "
        f"{total_records} total records.*\n"
    )
    return output.getvalue()


def _load_groups(
    databases: Sequence[CampaignDatabase],
    tolerance_parameter: str,
) -> list[ToleranceSweepGroup]:
    groups = []
    for database in databases:
        groups.append(
            build_sweep_group_from_db(
                str(database.path),
                tolerance_parameter=tolerance_parameter,
                tolerance_level=database.level_um,
                tolerance_unit="um",
                source_label=_format_level(database.level_um),
            )
        )
    return groups


def _convert_offset_metrics(
    groups: Sequence[ToleranceSweepGroup],
    frequency_target_ghz: float,
) -> None:
    """Convert frequency to absolute MHz offset and flatness to magnitude."""

    for group in groups:
        dataset = group.dataset
        if dataset is None:
            continue
        try:
            index = dataset.metric_names.index("resonant_freq")
            dataset.metric_values[:, index] = (
                np.abs(
                    dataset.metric_values[:, index] - frequency_target_ghz
                )
                * 1000.0
            )
        except (ValueError, IndexError):
            pass
        try:
            index = dataset.metric_names.index("field_flatness")
            dataset.metric_values[:, index] = np.abs(
                dataset.metric_values[:, index]
            )
        except (ValueError, IndexError):
            pass


def _build_sensitivities(
    groups: Sequence[ToleranceSweepGroup],
    metric_names: Sequence[str],
) -> dict[float, dict[str, SensitivityAnalysisReport]]:
    results: dict[float, dict[str, SensitivityAnalysisReport]] = {}
    for group in groups:
        dataset = group.dataset
        level_results: dict[str, SensitivityAnalysisReport] = {}
        if dataset is not None and dataset.accepted_row_count >= 5:
            for metric_name in metric_names:
                if metric_name not in dataset.metric_names:
                    continue
                metric_index = dataset.metric_names.index(metric_name)
                try:
                    level_results[metric_name] = analyze_parameter_sensitivity(
                        dataset,
                        method="spearman",
                        metric_indices=[metric_index],
                        min_finite=5,
                    )
                except (ValueError, IndexError):
                    continue
        results[group.tolerance_level_um] = level_results
    return results


def _build_rank_stability(
    groups: Sequence[ToleranceSweepGroup],
    sensitivities: dict[float, dict[str, SensitivityAnalysisReport]],
) -> dict[str, dict[str, dict[str, float]]]:
    dataset = next(
        (group.dataset for group in groups if group.dataset is not None),
        None,
    )
    if dataset is None:
        return {}

    stability: dict[str, dict[str, dict[str, float]]] = {}
    for parameter_name in dataset.param_names:
        stability[parameter_name] = {}
        for metric_name in dataset.metric_names:
            ranks: list[int] = []
            scores: list[float] = []
            for group in groups:
                sensitivity = sensitivities.get(
                    group.tolerance_level_um, {}
                ).get(metric_name)
                if sensitivity is None or not sensitivity.metric_reports:
                    continue
                for item in sensitivity.metric_reports[0].sensitivities:
                    if item.parameter_name == parameter_name:
                        ranks.append(item.rank)
                        scores.append(item.score)
                        break
            count = len(ranks)
            stability[parameter_name][metric_name] = {
                "n_levels": float(count),
                "rank1_pct": (
                    sum(rank == 1 for rank in ranks) / count * 100
                    if count
                    else 0.0
                ),
                "top3_pct": (
                    sum(rank <= 3 for rank in ranks) / count * 100
                    if count
                    else 0.0
                ),
                "mean_rank": (
                    sum(ranks) / count if count else float("inf")
                ),
                "mean_abs_score": (
                    sum(abs(score) for score in scores) / count
                    if count
                    else 0.0
                ),
            }
    return stability


def _load_nominals(config_path: Path) -> dict[str, float]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("tolerance", {}).get("parameters", [])
    return {
        str(item["name"]): float(item["nominal"])
        for item in parameters
        if item.get("enabled", True)
        and item.get("name") is not None
        and item.get("nominal") is not None
    }


def _render_data_overview(write, groups: Sequence[ToleranceSweepGroup]) -> None:
    write("## 1. Data Overview\n\n")
    write("| Level | Source | Accepted | Failed | Success Rate |\n")
    write("|-------|--------|----------|--------|-------------|\n")
    for group in groups:
        dataset = group.dataset
        if dataset is None:
            continue
        total = dataset.source_row_count
        rate = (
            f"{dataset.accepted_row_count / total * 100:.1f}%"
            if total
            else "N/A"
        )
        write(
            f"| {_format_level(group.tolerance_level_um)} | "
            f"{group.source_label} | {dataset.accepted_row_count} | "
            f"{dataset.skipped_row_count} | {rate} |\n"
        )
    write("\n")


def _render_metric_tables(write, report: SweepAnalysisReport) -> None:
    labels = (
        [_format_level(level) for level in report.metric_curves[0].levels_um]
        if report.metric_curves
        else []
    )
    write("## 2. Coefficient of Variation (CV%)\n\n")
    _write_table_header(write, ["Metric", *labels, "Monotonic", "Knee"])
    for curve in report.metric_curves:
        values = [
            f"{summary.cv_percent:.1f}"
            if math.isfinite(summary.cv_percent)
            else "N/A"
            for summary in curve.summaries
        ]
        knee = (
            _format_level(curve.levels_um[curve.largest_cv_delta_index])
            if curve.largest_cv_delta_index is not None
            else "N/A"
        )
        _write_table_row(
            write,
            [curve.metric_name, *values, curve.monotonic_cv, knee],
        )
    write("\n## 3. Mean Values by Tolerance Level\n\n")
    _write_table_header(write, ["Metric", *labels, "Monotonic"])
    for curve in report.metric_curves:
        values = [
            f"{summary.mean:.4g}"
            if math.isfinite(summary.mean)
            else "N/A"
            for summary in curve.summaries
        ]
        _write_table_row(
            write,
            [curve.metric_name, *values, curve.monotonic_mean],
        )
    write("\n")


def _render_sensitivities(
    write,
    databases: Sequence[CampaignDatabase],
    sensitivities: dict[float, dict[str, SensitivityAnalysisReport]],
    metric_names: Sequence[str],
) -> None:
    write("## 4. Parameter Sensitivity (Spearman |score| >= 0.2)\n\n")
    for database in databases:
        reports = sensitivities.get(database.level_um, {})
        if not reports:
            continue
        write(f"### {_format_level(database.level_um)}\n\n")
        for metric_name in metric_names:
            report = reports.get(metric_name)
            if report is None or not report.metric_reports:
                continue
            metric_report = report.metric_reports[0]
            significant = sorted(
                (
                    item
                    for item in metric_report.sensitivities
                    if item.abs_score >= 0.2
                ),
                key=lambda item: -item.abs_score,
            )
            if not significant:
                continue
            write(f"**{metric_name}** (n={metric_report.n_rows}):\n\n")
            for item in significant[:5]:
                write(
                    f"- `{item.parameter_name}`: {item.score:+.3f} "
                    f"(rank={item.rank})\n"
                )
            write("\n")


def _render_rank_stability(
    write,
    stability: dict[str, dict[str, dict[str, float]]],
    metric_names: Sequence[str],
) -> None:
    write("## 5. Cross-Level Parameter Rank Stability\n\n")
    write(
        "This section identifies parameters that repeatedly dominate across "
        "the available tolerance levels.\n\n"
    )
    _write_table_header(
        write,
        [
            "Metric",
            "Parameter",
            "|rho| mean",
            "Rank=1 %",
            "Top-3 %",
            "Mean Rank",
            "Verdict",
        ],
    )
    for metric_name in (
        "resonant_freq",
        "coupling_beta",
        "field_flatness",
    ):
        if metric_name not in metric_names:
            continue
        entries = [
            (name, metrics[metric_name])
            for name, metrics in stability.items()
            if metric_name in metrics
            and metrics[metric_name]["n_levels"] >= 2
        ]
        entries.sort(
            key=lambda item: (
                -item[1]["rank1_pct"],
                item[1]["mean_rank"],
            )
        )
        for parameter_name, stats in entries[:5]:
            rank1 = stats["rank1_pct"]
            top3 = stats["top3_pct"]
            mean_score = stats["mean_abs_score"]
            if rank1 >= 80:
                verdict = "Dominant"
            elif rank1 >= 50:
                verdict = "Strong"
            elif top3 >= 50:
                verdict = "Consistent top-3"
            elif mean_score >= 0.3:
                verdict = "Moderate influence"
            else:
                verdict = "Weak or noise-level"
            _write_table_row(
                write,
                [
                    metric_name,
                    f"`{parameter_name}`",
                    f"{mean_score:.2f}",
                    f"{rank1:.0f}%",
                    f"{top3:.0f}%",
                    f"{stats['mean_rank']:.1f}",
                    verdict,
                ],
            )
    write("\n")


def _render_recommendation(write, envelope) -> None:
    write("## 6. Tolerance Recommendation\n\n")
    overall = envelope.overall_recommended_max_tolerance_um
    overall_text = _format_level(overall) if overall is not None else "N/A"
    write(f"**Overall recommended max tolerance**: **{overall_text}**\n\n")
    if envelope.limiting_metrics:
        write(
            f"**Limiting metrics**: {', '.join(envelope.limiting_metrics)}\n\n"
        )
    _write_table_header(
        write,
        [
            "Metric",
            "Recommended Max",
            "First Warning",
            "First Failure",
            "Knee Candidate",
        ],
    )
    for item in envelope.metric_recommendations:
        _write_table_row(
            write,
            [
                item.metric_name,
                _optional_level(item.recommended_max_tolerance_um),
                _optional_level(item.first_warning_tolerance_um),
                _optional_level(item.first_failure_tolerance_um),
                _optional_level(item.knee_candidate_um),
            ],
        )
    write("\n")


def _render_parameter_budget(
    write,
    groups: Sequence[ToleranceSweepGroup],
    report: SweepAnalysisReport,
    nominals: dict[str, float],
) -> None:
    write("## 7. Per-Parameter Tolerance Budget\n\n")
    write(
        "All parameters vary simultaneously. Values show combined campaign "
        "effects and must not be interpreted as isolated causal sweeps. "
        "Perturbations are reported in um.\n\n"
    )
    dataset = next(
        (group.dataset for group in groups if group.dataset is not None),
        None,
    )
    if dataset is None:
        write("No accepted records are available.\n\n")
        return

    core_metrics = ["resonant_freq", "coupling_beta", "field_flatness"]
    ranked_curves = sorted(
        report.metric_curves,
        key=_max_finite_cv,
        reverse=True,
    )
    extras = [
        curve.metric_name
        for curve in ranked_curves
        if curve.metric_name not in core_metrics
    ]
    display_metrics = [
        name
        for name in [*core_metrics, *extras]
        if name in dataset.metric_names
    ][:4]

    x_parts = [
        group.dataset.parameter_values
        for group in groups
        if group.dataset is not None and group.dataset.accepted_row_count >= 3
    ]
    y_parts = [
        group.dataset.metric_values
        for group in groups
        if group.dataset is not None and group.dataset.accepted_row_count >= 3
    ]
    if not x_parts:
        write("Insufficient accepted records for perturbation bins.\n\n")
        return
    x_values = np.vstack(x_parts)
    y_values = np.vstack(y_parts)
    bin_edges = (0.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0)

    for parameter_index, parameter_name in enumerate(dataset.param_names):
        nominal = nominals.get(parameter_name)
        if nominal is None:
            continue
        perturbation_um = (
            np.abs(x_values[:, parameter_index] - nominal) * 1000.0
        )
        write(
            f"### `{parameter_name}` (nominal={nominal:.4f} mm)\n\n"
        )
        _write_table_header(
            write,
            [
                "Perturbation (um)",
                *[f"{name} (CV%)" for name in display_metrics],
                "n",
            ],
        )
        for lower, upper in zip(bin_edges, bin_edges[1:]):
            mask = (perturbation_um >= lower) & (perturbation_um < upper)
            count = int(mask.sum())
            if count < 3:
                continue
            row = [f"{lower:g}-{upper:g}"]
            for metric_name in display_metrics:
                metric_index = dataset.metric_names.index(metric_name)
                finite = y_values[mask, metric_index]
                finite = finite[np.isfinite(finite)]
                if len(finite) < 3:
                    row.append("N/A")
                    continue
                mean = float(np.mean(finite))
                cv = (
                    float(np.std(finite, ddof=1) / abs(mean) * 100)
                    if abs(mean) > 1e-12
                    else float("inf")
                )
                row.append(
                    f"{mean:.3g} ({cv:.0f}%)"
                    if math.isfinite(cv)
                    else f"{mean:.3g} (N/A)"
                )
            _write_table_row(write, [*row, str(count)])
        write("\n")


def _render_failure_rates(
    write,
    groups: Sequence[ToleranceSweepGroup],
) -> None:
    write("## 8. Failure Rate by Level\n\n")
    _write_table_header(write, ["Level", "Failure Rate"])
    for group in groups:
        dataset = group.dataset
        if dataset is None:
            continue
        total = dataset.source_row_count
        rate = (
            dataset.skipped_row_count / total * 100 if total else float("nan")
        )
        text = (
            f"{dataset.skipped_row_count}/{total} ({rate:.1f}%)"
            if math.isfinite(rate)
            else "N/A"
        )
        _write_table_row(
            write,
            [_format_level(group.tolerance_level_um), text],
        )
    write("\n")


def _write_table_header(write, columns: Sequence[str]) -> None:
    _write_table_row(write, columns)
    _write_table_row(write, ["---"] * len(columns))


def _write_table_row(write, columns: Sequence[object]) -> None:
    write("| " + " | ".join(str(value) for value in columns) + " |\n")


def _max_finite_cv(curve) -> float:
    values = [
        summary.cv_percent
        for summary in curve.summaries
        if math.isfinite(summary.cv_percent)
    ]
    return max(values, default=float("-inf"))


def _format_level(level_um: float) -> str:
    if float(level_um).is_integer():
        return f"{level_um:.0f} um"
    return f"{level_um:g} um"


def _optional_level(level_um: float | None) -> str:
    return _format_level(level_um) if level_um is not None else "N/A"


def main() -> int:
    """Entry point for ``python -m`` invocation."""

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
