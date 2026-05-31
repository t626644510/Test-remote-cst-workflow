"""Recompute CV with outlier exclusion for tolerance analysis results.

Usage:
    .venv\\Scripts\\python examples\\recompute_cv_clean.py
    .venv\\Scripts\\python examples\\recompute_cv_clean.py "D:/Results/tolerance_analysis.xlsx"
    .venv\\Scripts\\python examples\\recompute_cv_clean.py --method iqr --multiplier 3.0

Default: reads tolerance_analysis.xlsx from config logging.output_dir.
Detects outliers using IQR (Q3 + 3.0*IQR) per output column, prints
before/after comparison.
"""

import sys
import os as _os

_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_SRC_DIR = _os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import argparse
import numpy as np
import openpyxl


def detect_outliers_iqr(values: np.ndarray, multiplier: float = 3.0):
    """Return boolean mask: True for outliers (above Q3 + multiplier*IQR or below Q1 - multiplier*IQR)."""
    finite = values[np.isfinite(values)]
    if len(finite) < 4:
        return np.zeros(len(values), dtype=bool)
    q1, q3 = np.percentile(finite, [25, 75])
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    mask = (values < lower) | (values > upper)
    return mask & np.isfinite(values)


def detect_outliers_mad(values: np.ndarray, threshold: float = 5.0):
    """Return boolean mask using Median Absolute Deviation."""
    finite = values[np.isfinite(values)]
    if len(finite) < 4:
        return np.zeros(len(values), dtype=bool)
    median = np.median(finite)
    mad = np.median(np.abs(finite - median))
    if mad < 1e-15:
        return np.zeros(len(values), dtype=bool)
    z_scores = 0.6745 * (values - median) / mad
    return (np.abs(z_scores) > threshold) & np.isfinite(values)


def main():
    parser = argparse.ArgumentParser(description="Recompute CV with outlier cleaning")
    parser.add_argument("xlsx", nargs="?", default="",
                        help="Path to tolerance_analysis.xlsx (default: from config)")
    parser.add_argument("--method", choices=["iqr", "mad"], default="iqr",
                        help="Outlier detection method (default: iqr)")
    parser.add_argument("--multiplier", type=float, default=3.0,
                        help="IQR multiplier or MAD threshold (default: 3.0)")
    args = parser.parse_args()

    if args.xlsx:
        xlsx_path = args.xlsx
    else:
        import yaml
        cfg = yaml.safe_load(open(_os.path.join(_PROJECT_ROOT, "config", "default.yaml"),
                                  encoding="utf-8"))
        log_dir = cfg.get("logging", {}).get("output_dir", "D:/Results")
        xlsx_path = _os.path.join(log_dir, "tolerance_analysis.xlsx")

    if not _os.path.exists(xlsx_path):
        # Try workflow1_Result subfolder
        alt = _os.path.join(_os.path.dirname(xlsx_path), "workflow1_Result",
                           "tolerance_analysis.xlsx")
        if _os.path.exists(alt):
            xlsx_path = alt
        else:
            print(f"Not found: {xlsx_path}")
            sys.exit(1)

    print(f"Loading: {xlsx_path}")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    headers = rows[0]
    data = rows[1:]

    # Identify output columns (skip meta columns)
    meta_cols = {"#", "batch", "solver_ok", "elapsed_s", "error", "timestamp",
                 "f0_calibrated_ghz", "f0_ghz"}
    output_cols = []
    for j, h in enumerate(headers):
        if h and str(h) not in meta_cols and j < len(headers) - 4:
            output_cols.append((j, str(h)))

    # Build data arrays
    n_rows = len(data)
    arrays: dict[str, np.ndarray] = {}
    for j, name in output_cols:
        vals = []
        for row in data:
            try:
                v = float(row[j]) if row[j] is not None and row[j] != "NaN" else np.nan
            except (ValueError, TypeError):
                v = np.nan
            vals.append(v)
        arrays[name] = np.array(vals, dtype=float)

    detect_fn = detect_outliers_iqr if args.method == "iqr" else detect_outliers_mad
    param_str = f"mult={args.multiplier}" if args.method == "iqr" else f"thresh={args.multiplier}"

    print(f"\n{'='*78}")
    print(f"  CV COMPARISON  — {args.method.upper()} outlier detection ({param_str})")
    print(f"  {len(data)} rows, {n_rows} data rows")
    print(f"{'='*78}")

    total_outliers = 0
    for j, name in output_cols:
        vals = arrays[name]
        valid = vals[np.isfinite(vals)]
        if len(valid) < 3:
            continue

        outliers = detect_fn(vals, args.multiplier) if args.method == "iqr" else detect_fn(vals, args.multiplier)
        n_out = int(np.sum(outliers))
        total_outliers += n_out

        clean = vals[~outliers & np.isfinite(vals)]

        # Raw stats
        m_raw, s_raw = np.mean(valid), np.std(valid, ddof=1)
        cv_raw = s_raw / abs(m_raw) * 100 if abs(m_raw) > 1e-15 else 0

        # Clean stats
        if len(clean) >= 3:
            m_cln, s_cln = np.mean(clean), np.std(clean, ddof=1)
            cv_cln = s_cln / abs(m_cln) * 100 if abs(m_cln) > 1e-15 else 0
        else:
            m_cln, s_cln, cv_cln = m_raw, s_raw, cv_raw

        cv_delta = cv_raw - cv_cln
        marker = " ***" if cv_delta > 5 else ("  *" if cv_delta > 1 else "")

        print(f"\n  {name:24s}  n={len(valid):3d}  outliers={n_out}")
        print(f"    Raw:   mean={m_raw:.5g}  std={s_raw:.4g}  CV={cv_raw:.2f}%")
        print(f"    Clean: mean={m_cln:.5g}  std={s_cln:.4g}  CV={cv_cln:.2f}%  ΔCV={cv_delta:.1f}%{marker}")

    print(f"\n{'─'*78}")
    print(f"  Total outliers detected: {total_outliers}")
    print(f"{'─'*78}")

    # ── Specific outlier rows ─────────────────────────────────────────
    print(f"\n{'='*78}")
    print(f"  OUTLIER DETAIL BY OUTPUT")
    print(f"{'='*78}")
    for j, name in output_cols:
        vals = arrays[name]
        outliers = detect_fn(vals, args.multiplier) if args.method == "iqr" else detect_fn(vals, args.multiplier)
        outlier_indices = np.where(outliers)[0]
        if len(outlier_indices) > 0:
            print(f"\n  [{name}] ({len(outlier_indices)} outliers):")
            for idx in outlier_indices:
                excel_row = idx + 2
                val = vals[idx]
                valid_vals = vals[np.isfinite(vals)]
                median_val = np.median(valid_vals)
                ratio = val / median_val if abs(median_val) > 1e-15 else 0
                print(f"    Excel row {excel_row} (#{int(idx)}): {val:.5g}  "
                      f"(×{ratio:.1f} median)")


if __name__ == "__main__":
    main()
