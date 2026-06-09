"""Temporary tolerance sweep analysis for wf3-campaign data.

Uses existing rfgun_tolerance modules only. Outputs markdown to stdout.
Usage:
    .venv\Scripts\python temp_analysis\analyze_tolerance.py > temp_analysis\report.md
"""
import sys
from pathlib import Path

import numpy as np

_project_root = Path(__file__).resolve().parents[1]
_src = str(_project_root / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from workflows.rfgun_tolerance.sweep_dataset import (
    build_sweep_group_from_db,
    build_sweep_dataset,
    ToleranceSweepDataset,
    ToleranceSweepGroup,
)
from workflows.rfgun_tolerance.sweep_analysis import (
    analyze_tolerance_sweep,
    SweepAnalysisReport,
    SweepMetricCurve,
    classify_monotonic,
    largest_adjacent_delta_index,
)
from workflows.rfgun_tolerance.sweep_recommendation import (
    recommend_tolerance_envelope,
    MetricAcceptanceRule,
)
from workflows.rfgun_tolerance.sensitivity import (
    analyze_parameter_sensitivity,
    SensitivityAnalysisReport,
)
from workflows.rfgun_tolerance.statistics import (
    summarize_dataset,
    MetricSummary,
)

# ---- Config -----------------------------------------------------------
CAMPAIGN_DIR = _project_root / "wf3-campaign" / "wf3-campaign" / "wf3_tolerance_6x60"
LEVELS = [
    (3, "3um"),
    (5, "5um"),
    (10, "10um"),
    (15, "15um"),
    (20, "20um"),
    (30, "30um"),
]
TOLERANCE_PARAMETER = "tolerance_abs"
METRIC_NAMES = [
    "resonant_freq", "coupling_beta", "q0", "peak_e_field",
    "field_flatness", "max_modified_poynting", "pulsed_heating",
]


def main():
    # ---- 1. Load all groups -----------------------------------------------
    groups: list[ToleranceSweepGroup] = []
    for level_um, dirname in LEVELS:
        db_path = CAMPAIGN_DIR / dirname / "evaluations.db"
        group = build_sweep_group_from_db(
            str(db_path),
            tolerance_parameter=TOLERANCE_PARAMETER,
            tolerance_level=float(level_um),
            tolerance_unit="um",
            source_label=f"{level_um}um",
        )
        groups.append(group)

    sweep = build_sweep_dataset(groups, TOLERANCE_PARAMETER)

    # ---- 1.5: Convert resonant_freq to MHz offset ------------------------
    FREQ_TARGET_GHZ = 11.424
    for group in groups:
        ds = group.dataset
        if ds is None:
            continue
        try:
            fi = ds.metric_names.index("resonant_freq")
            ds.metric_values[:, fi] = (ds.metric_values[:, fi] - FREQ_TARGET_GHZ) * 1000.0
        except (ValueError, IndexError):
            pass
    # Update sweep references after mutation
    sweep = build_sweep_dataset(groups, TOLERANCE_PARAMETER)

    # ---- 2. Sweep Analysis ------------------------------------------------
    report: SweepAnalysisReport = analyze_tolerance_sweep(
        sweep,
        metric_names=METRIC_NAMES,
        include_clean_cv=True,
        clean_method="iqr",
        clean_multiplier=3.0,
    )

    # ---- 3. Per-level Sensitivity -----------------------------------------
    sensitivities: dict[float, dict[str, SensitivityAnalysisReport]] = {}
    for group in groups:
        level = group.tolerance_level_um
        ds = group.dataset
        if ds is None or ds.accepted_row_count < 5:
            sensitivities[level] = {}
            continue
        sens_reports = {}
        for metric in METRIC_NAMES:
            if metric not in ds.metric_names:
                continue
            mi = ds.metric_names.index(metric)
            try:
                sr = analyze_parameter_sensitivity(
                    ds, method="spearman", metric_indices=[mi], min_finite=5
                )
                sens_reports[metric] = sr
            except Exception:
                pass
        sensitivities[level] = sens_reports

    # ---- 4. Tolerance Recommendation --------------------------------------
    rules = [
        MetricAcceptanceRule(metric_name="resonant_freq", max_cv_percent=2.0, max_failure_rate=20.0, direction="target", target_mean=11.424, max_abs_error_from_target=0.005),
        MetricAcceptanceRule(metric_name="field_flatness", max_cv_percent=40.0, max_failure_rate=20.0, direction="target", target_mean=0.0),
        MetricAcceptanceRule(metric_name="pulsed_heating", max_cv_percent=15.0, max_failure_rate=20.0, direction="smaller_is_better"),
        MetricAcceptanceRule(metric_name="max_modified_poynting", max_cv_percent=15.0, max_failure_rate=20.0, direction="smaller_is_better"),
        MetricAcceptanceRule(metric_name="coupling_beta", max_cv_percent=25.0, max_failure_rate=20.0, direction="target", target_mean=3.0),
        MetricAcceptanceRule(metric_name="q0", max_cv_percent=20.0, max_failure_rate=20.0, direction="larger_is_better"),
        MetricAcceptanceRule(metric_name="peak_e_field", max_cv_percent=5.0, max_failure_rate=20.0, direction="larger_is_better"),
    ]
    envelope = recommend_tolerance_envelope(report, rules)

    # ---- 5. Render Markdown -----------------------------------------------
    print("# Tolerance Sweep Analysis Report")
    print()
    print(f"**Campaign**: `wf3_tolerance_6x60`  |  **Parameter**: `{TOLERANCE_PARAMETER}`  |  **Levels**: 3, 5, 10, 15, 20, 30 um")
    print()

    # 5a. Data Overview
    print("## 1. Data Overview")
    print()
    print("| Level | Source | Accepted | Failed | Success Rate |")
    print("|-------|--------|----------|--------|-------------|")
    for g in groups:
        ds = g.dataset
        if ds is None:
            continue
        total = ds.source_row_count
        accepted = ds.accepted_row_count
        skipped = ds.skipped_row_count
        rate = f"{accepted / total * 100:.1f}%" if total > 0 else "N/A"
        print(f"| {g.tolerance_level_um:.0f} um | {g.source_label} | {accepted} | {skipped} | {rate} |")
    print()

    # 5b. CV% Table
    print("## 2. Coefficient of Variation (CV%)")
    print()
    print("| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic | Knee |")
    print("|--------|-----|-----|------|------|------|------|-----------|------|")
    for curve in report.metric_curves:
        parts = [curve.metric_name]
        for s in curve.summaries:
            cv = s.cv_percent
            parts.append(f"{cv:.1f}" if cv is not None and cv == cv else "N/A")
        parts.append(curve.monotonic_cv or "?")
        knee_idx = curve.largest_cv_delta_index
        parts.append(f"{curve.levels_um[knee_idx]:.0f}um" if knee_idx is not None else "?")
        print("| " + " | ".join(parts) + " |")
    print()

    # 5c. Mean Table
    print("## 3. Mean Values by Tolerance Level")
    print()
    print("| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic |")
    print("|--------|-----|-----|------|------|------|------|-----------|")
    for curve in report.metric_curves:
        parts = [curve.metric_name]
        for s in curve.summaries:
            m = s.mean
            if m is not None and m == m:
                parts.append(f"{m:.4g}")
            else:
                parts.append("N/A")
        parts.append(curve.monotonic_mean or "?")
        print("| " + " | ".join(parts) + " |")
    print()

    # 5d. Parameter Sensitivity (Top-5 per metric at each level)
    print("## 4. Parameter Sensitivity (Spearman |score| ≥ 0.2)")
    print()
    for level_um, _ in LEVELS:
        sr_map = sensitivities.get(float(level_um), {})
        if not sr_map:
            continue
        print(f"### {level_um} um")
        print()
        for metric in METRIC_NAMES:
            sr = sr_map.get(metric)
            if sr is None:
                continue
            mreport = sr.metric_reports[0] if sr.metric_reports else None
            if mreport is None:
                continue
            sig = [s for s in mreport.sensitivities if s.abs_score >= 0.2]
            sig.sort(key=lambda s: -s.abs_score)
            if sig:
                print(f"**{metric}** (n={mreport.n_rows}):")
                for s in sig[:5]:
                    print(f"  - `{s.parameter_name}`: {s.score:+.3f} (rank={s.rank})")
                print()
        print()

    # 5e. Tolerance Recommendation
    print("## 5. Tolerance Recommendation")
    print()
    print(f"**Overall recommended max tolerance**: **{envelope.overall_recommended_max_tolerance_um or 'N/A'} um**")
    print()
    if envelope.limiting_metrics:
        print(f"**Limiting metrics**: {', '.join(envelope.limiting_metrics)}")
    print()
    print("| Metric | Recommended Max | First Warning | First Failure | Knee Candidate |")
    print("|--------|----------------|---------------|---------------|----------------|")
    for rec in envelope.metric_recommendations:
        print(f"| {rec.metric_name} | {rec.recommended_max_tolerance_um or 'N/A'} um | "
              f"{rec.first_warning_tolerance_um or 'N/A'} um | "
              f"{rec.first_failure_tolerance_um or 'N/A'} um | "
              f"{rec.knee_candidate_um or 'N/A'} um |")
    print()

    # 5f. Per-Parameter Tolerance Analysis
    print("## 7. Per-Parameter Tolerance Budget")
    print()
    print("Analysis: for each parameter, compute max perturbation (um) before")
    print("key metrics cross thresholds. Based on pooled data across all levels.")
    print()

    # Pool all success records across all levels
    all_param_vals = []
    all_metric_vals = []
    all_param_names = []
    all_metric_names = []
    for group in groups:
        ds = group.dataset
        if ds is None:
            continue
        all_param_vals.append(ds.parameter_values)
        all_metric_vals.append(ds.metric_values)
        if not all_param_names:
            all_param_names = list(ds.param_names)
        if not all_metric_names:
            all_metric_names = list(ds.metric_names)

    if all_param_vals:
        X_all = np.vstack(all_param_vals)
        Y_all = np.vstack(all_metric_vals)

        # Get nominal values from config
        import yaml
        cfg_path = _project_root / "config" / "default.yaml"
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        tol_params = cfg.get("tolerance", {}).get("parameters", [])
        nominals = {}
        for p in tol_params:
            if p.get("enabled", True):
                nominals[p["name"]] = float(p["nominal"])

        # For each parameter, compute perturbation (um) and correlate with metrics
        param_perturb = {}
        for pi, pname in enumerate(all_param_names):
            nom = nominals.get(pname, 0.0)
            perturb_um = np.abs(X_all[:, pi] - nom) * 1000.0  # um
            param_perturb[pname] = perturb_um

        print("| Parameter | Max Perturb (um) | resonant_freq | coupling_beta | field_flatness | peak_e_field | q0 | pulsed_heating |")
        print("|-----------|:----------------:|:-------------:|:------------:|:-------------:|:------------:|:--:|:-------------:|")
        for pname in all_param_names:
            pu = param_perturb[pname]
            max_pu = np.max(pu)
            row = [f"`{pname}`", f"{max_pu:.0f}"]
            for mi, mname in enumerate(all_metric_names):
                y = Y_all[:, mi]
                finite = np.isfinite(y) & np.isfinite(pu)
                if finite.sum() < 10:
                    row.append("insufficient")
                    continue
                # Linear regression slope: metric change per um
                try:
                    slope, intercept = np.polyfit(pu[finite], y[finite], 1)
                    # Metric change at max perturbation
                    delta = slope * max_pu
                    row.append(f"{delta:+.3g}")
                except Exception:
                    row.append("N/A")
            print("| " + " | ".join(row) + " |")
        print()
        print("*Values show estimated metric change at max perturbation (linear regression slope × max μm).*")
        print()

    # 5g. Failure Rate
    print("## 6. Failure Rate by Level")
    print()
    print("| Level | Failure Rate |")
    print("|-------|-------------|")
    for curve in report.metric_curves:
        for s in curve.summaries:
            pass  # group level shown once
        break
    for g in groups:
        ds = g.dataset
        if ds is None:
            continue
        fail = ds.skipped_row_count
        total = ds.source_row_count
        print(f"| {g.tolerance_level_um:.0f} um | {fail}/{total} ({fail/total*100:.1f}%) |")
    print()

    print("---")
    print(f"*Report generated from {len(groups)} tolerance levels, {sum(g.dataset.source_row_count if g.dataset else 0 for g in groups)} total records.*")


if __name__ == "__main__":
    main()
