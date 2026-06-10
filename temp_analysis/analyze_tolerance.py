"""Temporary tolerance sweep analysis for wf3-campaign data.

Uses existing rfgun_tolerance modules only. Outputs markdown to stdout.
Usage:
    .venv\Scripts\python temp_analysis\analyze_tolerance.py > temp_analysis\report.md
"""
import sys
from pathlib import Path

import os

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
TOLERANCE_DIR = "D:/Results/tolerance"
LEVELS = sorted([
    (3, "tolerance_eval_3um.db"),
    (5, "tolerance_eval_5um.db"),
    (7, "tolerance_eval_7.0um.db"),
    (10, "tolerance_eval_10um.db"),
    (12, "tolerance_eval_12um.db"),
    (15, "tolerance_eval_15um.db"),
    (20, "tolerance_eval_20um.db"),
    (25, "tolerance_eval_25.0um.db"),
    (30, "tolerance_eval_30um.db"),
], key=lambda x: x[0])
TOLERANCE_PARAMETER = "tolerance_abs"
METRIC_NAMES = [
    "resonant_freq", "coupling_beta", "q0", "peak_e_field",
    "field_flatness", "max_modified_poynting", "pulsed_heating",
]


def main():
    # ---- 1. Load all groups -----------------------------------------------
    groups: list[ToleranceSweepGroup] = []
    for level_um, dirname in LEVELS:
        db_path = os.path.join(TOLERANCE_DIR, dirname)
        group = build_sweep_group_from_db(
            str(db_path),
            tolerance_parameter=TOLERANCE_PARAMETER,
            tolerance_level=float(level_um),
            tolerance_unit="um",
            source_label=f"{level_um}um",
        )
        groups.append(group)

    sweep = build_sweep_dataset(groups, TOLERANCE_PARAMETER)

    # ---- 1.5: Convert near-zero-target metrics to absolute offset ------------
    # CV% = std/|mean|*100 is meaningless when mean ≈ 0. Use |value - target|.
    FREQ_TARGET_GHZ = 11.424
    for group in groups:
        ds = group.dataset
        if ds is None:
            continue
        # resonant_freq -> |offset| in MHz
        try:
            fi = ds.metric_names.index("resonant_freq")
            ds.metric_values[:, fi] = np.abs(ds.metric_values[:, fi] - FREQ_TARGET_GHZ) * 1000.0
        except (ValueError, IndexError):
            pass
        # field_flatness -> |flatness| (target is 0)
        try:
            fi = ds.metric_names.index("field_flatness")
            ds.metric_values[:, fi] = np.abs(ds.metric_values[:, fi])
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

    # ---- 3.5: Cross-level rank stability ----------------------------------
    # For each (param, metric) pair, count how often it's rank=1 across levels.
    # Collect param/metric names from first available group
    all_param_names = []
    all_metric_names = []
    for group in groups:
        ds = group.dataset
        if ds is not None:
            all_param_names = list(ds.param_names)
            all_metric_names = list(ds.metric_names)
            break
    rank_stability: dict[str, dict[str, dict]] = {}  # param -> metric -> stats
    levels_with_data = [l for l, _ in LEVELS if float(l) in sensitivities and sensitivities[float(l)]]
    for pname in all_param_names:
        rank_stability[pname] = {}
        for mname in all_metric_names:
            ranks = []
            scores = []
            for lvl, _ in LEVELS:
                sr_map = sensitivities.get(float(lvl), {})
                sr = sr_map.get(mname)
                if sr is None or not sr.metric_reports:
                    continue
                mr = sr.metric_reports[0]
                for s in mr.sensitivities:
                    if s.parameter_name == pname:
                        ranks.append(s.rank)
                        scores.append(s.score)
                        break
            n_levels = len(ranks)
            rank1_count = sum(1 for r in ranks if r == 1)
            top3_count = sum(1 for r in ranks if r <= 3)
            mean_rank = sum(ranks) / n_levels if n_levels else float('inf')
            mean_score = sum(abs(s) for s in scores) / n_levels if n_levels else 0.0
            rank_stability[pname][mname] = {
                "n_levels": n_levels,
                "rank1_pct": rank1_count / n_levels * 100 if n_levels else 0,
                "top3_pct": top3_count / n_levels * 100 if n_levels else 0,
                "mean_rank": mean_rank,
                "mean_abs_score": mean_score,
            }

    # ---- 4. Tolerance Recommendation --------------------------------------
    # === CONFIGURABLE: acceptance rules for tolerance recommendation ===
    ACCEPTANCE_RULES = {
        "resonant_freq":  {"max_cv_percent": 50.0, "max_failure_rate": 20.0, "direction": "smaller_is_better"},
        "coupling_beta":  {"max_cv_percent": 25.0, "max_failure_rate": 20.0, "direction": "target", "target_mean": 3.0},
        "q0":             {"max_cv_percent": 20.0, "max_failure_rate": 20.0, "direction": "larger_is_better"},
        "field_flatness": {"max_cv_percent": 50.0, "max_failure_rate": 20.0, "direction": "smaller_is_better"},
        "max_modified_poynting": {"max_cv_percent": 30.0, "max_failure_rate": 20.0, "direction": "smaller_is_better"},
        "pulsed_heating": {"max_cv_percent": 20.0, "max_failure_rate": 20.0, "direction": "smaller_is_better"},
        # "peak_e_field": not included — user does not care about this metric
    }
    # freq is in abs MHz after conversion; target=0, 1 MHz max error
    rules = []
    for mname, rcfg in ACCEPTANCE_RULES.items():
        kwargs = dict(rcfg)
        rules.append(MetricAcceptanceRule(metric_name=mname, **kwargs))
    envelope = recommend_tolerance_envelope(report, rules)

    # ---- 5. Render Markdown -----------------------------------------------
    print("# Tolerance Sweep Analysis Report")
    print()
    level_list = ", ".join(f"{lvl:.0f}um" if lvl == int(lvl) else f"{lvl:.1f}um" for lvl, _ in LEVELS)
    print(f"**Campaign**: `wf3_tolerance`  |  **Parameter**: `{TOLERANCE_PARAMETER}`  |  **Levels**: {len(LEVELS)} ({level_list})")
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
    # Dynamic header from actual levels
    first_curve = report.metric_curves[0] if report.metric_curves else None
    if first_curve:
        lvl_labels = [f"{lvl:.0f}um" if lvl == int(lvl) else f"{lvl:.1f}um" for lvl in first_curve.levels_um]
    else:
        lvl_labels = []
    header_cols = ["Metric"] + lvl_labels + ["Monotonic", "Knee"]
    sep_cols = ["--------"] + [":---:"] * len(lvl_labels) + ["-----------", "------"]
    print("| " + " | ".join(header_cols) + " |")
    print("|" + "|".join(sep_cols) + "|")
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
    header_cols2 = ["Metric"] + lvl_labels + ["Monotonic"]
    sep_cols2 = ["--------"] + [":---:"] * len(lvl_labels) + ["-----------"]
    print("| " + " | ".join(header_cols2) + " |")
    print("|" + "|".join(sep_cols2) + "|")
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
    print("## 4. Parameter Sensitivity (Spearman |score| >= 0.2)")
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

    # 4.5: Cross-level Rank Stability
    print("## 5. Cross-Level Parameter Rank Stability")
    print()
    print("For each core metric, which parameters consistently dominate")
    print("across all 6 tolerance levels?")
    print()
    print("| Metric | Parameter | |ρ| mean | Rank=1 % | Top-3 % | Mean Rank | Verdict |")
    print("|--------|-----------|:-------:|:--------:|:-------:|:---------:|---------|")
    CORE_METRICS = ["resonant_freq", "coupling_beta", "field_flatness"]
    for mname in CORE_METRICS:
        if mname not in all_metric_names:
            continue
        entries = []
        for pname in all_param_names:
            stats = rank_stability.get(pname, {}).get(mname, {})
            if stats.get("n_levels", 0) >= 3:
                entries.append((pname, stats))
        entries.sort(key=lambda x: -x[1]["rank1_pct"])
        for pname, stats in entries[:5]:
            r1 = stats["rank1_pct"]
            t3 = stats["top3_pct"]
            mr = stats["mean_rank"]
            ms = stats["mean_abs_score"]
            nl = stats["n_levels"]
            if r1 >= 80:
                verdict = "**Dominant**"
            elif r1 >= 50:
                verdict = "Strong"
            elif t3 >= 50:
                verdict = "Consistent top-3"
            elif ms >= 0.3:
                verdict = "Moderate influence"
            else:
                verdict = "Weak / noise-level"
            print(f"| {mname} | `{pname}` | {ms:.2f} | {r1:.0f}% ({nl} lvls) | {t3:.0f}% | {mr:.1f} | {verdict} |")
        print()
    print("*Verdict: Dominant = rank-1 in >=80% levels; Strong = >=50%; Consistent top-3 = in top-3 >=50%; Moderate = mean |rho| >=0.3.*")
    print()

    # 5e. Tolerance Recommendation
    print("## 6. Tolerance Recommendation")
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

    # 5f. Per-Parameter Tolerance Budget
    print("## 7. Per-Parameter Tolerance Budget")
    print()
    print("For each parameter, actual perturbation values are binned,")
    print("and metric averages computed per bin. **All 22 parameters vary")
    print("simultaneously** — values reflect combined effects, not isolated impact.")
    print("Compare rows within a column to see degradation trends.")
    print("`n` = number of samples in that perturbation bin.")
    print()

    # Core metrics for per-param display: freq, beta, flatness + top CV metric
    core = ["resonant_freq", "coupling_beta", "field_flatness"]
    cv_curves = sorted(report.metric_curves, key=lambda c: max(s.cv_percent for s in c.summaries if s.cv_percent == s.cv_percent), reverse=True)
    top_cv = [c.metric_name for c in cv_curves if c.metric_name not in core]
    per_param_metrics = [m for m in core + top_cv if m in all_metric_names][:4]

    # Get nominal values from config
    import yaml as _yaml
    cfg_path = _project_root / "config" / "default.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = _yaml.safe_load(fh)
    tol_params = cfg.get("tolerance", {}).get("parameters", [])
    nominals = {}
    for p in tol_params:
        if p.get("enabled", True):
            nominals[p["name"]] = float(p["nominal"])

    # Pool ALL success records across all levels
    X_pool = []
    Y_pool = []
    for group in groups:
        ds = group.dataset
        if ds is None or ds.accepted_row_count < 3:
            continue
        X_pool.append(ds.parameter_values)
        Y_pool.append(ds.metric_values)
    if X_pool:
        X_all = np.vstack(X_pool)  # (N_total, 22)
        Y_all = np.vstack(Y_pool)  # (N_total, 7)

        # Perturbation bins (um): 0-3, 3-5, 5-10, 10-15, 15-20, 20-30
        BIN_EDGES = [0, 3, 5, 10, 15, 20, 30]
        BIN_LABELS = ["0-3", "3-5", "5-10", "10-15", "15-20", "20-30"]

        for pi, pname in enumerate(all_param_names):
            nom = nominals.get(pname, 0.0)
            perturb_um = np.abs(X_all[:, pi] - nom) * 1000.0
            print(f"### `{pname}` (nominal={nom:.4f} mm)")
            print()
            header = ["Perturb (um)"] + [f"{m} (CV%)" for m in per_param_metrics] + ["n"]
            print("| " + " | ".join(header) + " |")
            print("|" + "|".join([":---:"] * len(header)) + "|")

            for bi in range(len(BIN_EDGES) - 1):
                lo, hi = BIN_EDGES[bi], BIN_EDGES[bi + 1]
                mask = (perturb_um >= lo) & (perturb_um < hi)
                n_bin = mask.sum()
                if n_bin < 3:
                    continue
                row = [f"{lo}-{hi}"]
                for mname in per_param_metrics:
                    try:
                        mi = all_metric_names.index(mname)
                        vals = Y_all[mask, mi]
                        finite = np.isfinite(vals)
                        if finite.sum() < 3:
                            row.append("--")
                        else:
                            v = vals[finite]
                            cv = np.std(v, ddof=1) / abs(np.mean(v)) * 100 if abs(np.mean(v)) > 1e-12 else float('inf')
                            row.append(f"{np.mean(v):.3g} ({cv:.0f}%)")
                    except (ValueError, IndexError):
                        row.append("--")
                row.append(str(n_bin))
                print("| " + " | ".join(row) + " |")
            print()
    print()

    # 5g. Failure Rate
    print("## 8. Failure Rate by Level")
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
