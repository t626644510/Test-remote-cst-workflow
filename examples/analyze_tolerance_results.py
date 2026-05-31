"""Post-process tolerance results stored inside the .cst project file.

Reads parametric-sweep results directly from the CST project (no Excel needed).
Usage:  python examples/analyze_tolerance_results.py
"""
import sys, os as _os
_project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_src = _os.path.join(_project_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import yaml, numpy as np
from cst_optimization.core import init_cst_path

CONFIG_PATH = _os.path.join(_project_root, "config", "default.yaml")
cfg = yaml.safe_load(open(CONFIG_PATH, "r", encoding="utf-8"))
init_cst_path(cfg.get("cst", {}).get("library_path"))

from cst_optimization.core.results import ResultReader, ResultBundle
from cst_optimization.physics.cavity import (
    ResonantFrequency, LoadedQ, CouplingBeta, IntrinsicQ,
    PeakSurfaceField, InputPower, MinS11,
)
from cst_optimization.utils.units import MV_per_m

tc = cfg.get("tolerance", {})
project_path = tc["project_path"]
output_entries = [o for o in tc.get("outputs", []) if o.get("enabled")]


def main() -> None:
    print(f"Reading: {project_path}")
    reader = ResultReader(project_path, allow_interactive=True)
    run_ids = reader.get_all_run_ids()
    print(f"Run IDs: {len(run_ids)} — {run_ids[:10]}{'...' if len(run_ids) > 10 else ''}")

    # ── Extract results from each run ────────────────────────────────
    results: list[dict] = []
    for run_id in run_ids:
        params = reader.get_parameter_combination(run_id)
        if not params:
            continue
        try:
            s11 = reader.get_s_parameter(reader.TREEPATH_S11, run_id=run_id)
            e_max = reader.get_scalar(reader.TREEPATH_MAX_E_Z0, run_id=run_id)
        except Exception:
            continue

        bundle = ResultBundle(
            s_parameters={"S1,1": s11}, scalars={"MaxE_Z0": e_max},
            run_id=run_id, parameter_combination=params,
        )

        row: dict = {
            "run_id": run_id,
            "f0_calibrated_ghz": 0.0,
            "q_loaded": np.nan, "coupling_beta": np.nan, "q0": np.nan,
            "e_peak": np.nan, "s11_db": np.nan, "p_input_mw": np.nan,
        }
        try:
            row["f0_calibrated_ghz"] = ResonantFrequency().compute(bundle) / 1e9
            row["q_loaded"] = LoadedQ().compute(bundle)
            row["coupling_beta"] = CouplingBeta().compute(bundle)
            row["q0"] = IntrinsicQ().compute(bundle)
            row["e_peak"] = PeakSurfaceField().compute(bundle)
            row["s11_db"] = 20 * np.log10(max(MinS11().compute(bundle), 1e-15))
            row["p_input_mw"] = InputPower(target_e_acc_vm=200 * MV_per_m).compute(bundle) / 1e6
            results.append(row)
        except Exception:
            continue

    n_total = len(run_ids)
    n_ok = len(results)
    print(f"Evaluations: {n_total} total, {n_ok} with readable results")

    if n_ok == 0:
        print("No readable results found.")
        return

    # ── Per-output statistics ────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  TOLERANCE ANALYSIS RESULTS  ({n_ok} / {n_total} OK)")
    print(f"{'='*80}")

    for out in output_entries:
        key = out["name"]
        vals = [r.get(key, np.nan) for r in results]
        vals = np.array([v for v in vals if np.isfinite(v)])
        if len(vals) < 3:
            print(f"\n  {key:25s}  insufficient data ({len(vals)} values)")
            continue

        m, s = np.mean(vals), np.std(vals, ddof=1)
        cv = s / abs(m) * 100 if abs(m) > 1e-15 else float("inf")
        print(f"\n  {key:25s}  {out.get('description','')}")
        print(f"    Mean  = {m:.6g}  ± {s:.3g}  (1σ)")
        print(f"    Range = [{np.min(vals):.6g}, {np.max(vals):.6g}]")
        print(f"    CV    = {cv:.2f}%")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
