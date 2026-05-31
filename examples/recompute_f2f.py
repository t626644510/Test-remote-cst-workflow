"""Re-run frequency-domain solver for eval groups missing F2F data, and
merge the new S-parameter curves into the existing ``.npz`` database.

Reads ``D:/Results/raw_curves/missing_f2f_params.jsonl`` produced by
``extract_curves_to_db.py``, runs the F2F.cst frequency-domain solver
for each parameter set, and merges the resulting 1D curves back into the
corresponding ``eval_NNNN.npz`` file.

Usage::

    python examples/recompute_f2f.py
"""

from __future__ import annotations

import json
import os
import sys
import time

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_project_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import yaml
import numpy as np

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.project import CSTProject
from cst_optimization.core.solver import SolverRunner
from cst_optimization.core.results import ResultReader
from cst_optimization.database import (
    RecordingResultReader,
    save_curves_npz,
    load_index,
    save_index_record,
)


def main() -> None:
    # ── Load config ───────────────────────────────────────────────────
    with open("config/default.yaml", "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    wf2 = cfg["workflow_2"]
    cst_cfg = cfg.get("cst", {})
    library_path = cst_cfg.get(
        "library_path", r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries"
    )
    f2f_path = wf2["projects"]["frequency_domain"]["cst_path"]

    # ── S-parameter tree paths (from config, fallback to class defaults) ─
    rp = wf2.get("result_paths", {})
    s11_tp = rp.get("s11", "1D Results\\S-Parameters\\S1,1")
    s21_tp = rp.get("s21", "1D Results\\S-Parameters\\S2,1")
    s31_tp = rp.get("s31", "1D Results\\S-Parameters\\S3,1")

    # ── Read missing-F2F list ─────────────────────────────────────────
    db_dir = cfg.get("logging", {}).get("output_dir", "D:/Results") + "/raw_curves"
    missing_path = os.path.join(db_dir, "missing_f2f_params.jsonl")
    if not os.path.isfile(missing_path):
        print(f"No missing-F2F list found at {missing_path}")
        print("Run extract_curves_to_db.py first.")
        return

    missing: list[dict] = []
    with open(missing_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                missing.append(json.loads(line))

    if not missing:
        print("Missing-F2F list is empty — nothing to do.")
        return

    print(f"F2F re-computation needed for {len(missing)} eval groups")
    print(f"Target project: {f2f_path}")

    # ── Load existing index for updating ──────────────────────────────
    index_path = os.path.join(db_dir, "index.jsonl")
    index_records = load_index(index_path)
    if not index_records:
        print("No index records — run extract_curves_to_db.py first.")
        return
    print(f"Loaded {len(index_records)} index records")

    # ── Connect to CST ────────────────────────────────────────────────
    print("\nConnecting to CST DesignEnvironment ...")
    conn = CSTConnection(library_path=library_path, mode="any_or_new")
    conn.connect()
    conn.set_quiet_mode(True)
    print(f"Connected — PID {conn.pid}")

    solver = SolverRunner(
        timeout_s=float(cfg.get("solver", {}).get("stagnation_timeout_s", 300)),
        settle_s=float(cfg.get("solver", {}).get("settle_s", 2.0)),
    )

    n_done = 0
    n_failed = 0

    for entry in missing:
        eval_idx = entry["eval_idx"]
        params = entry["params"]
        npz_name = f"eval_{eval_idx:04d}.npz"
        npz_path = os.path.join(db_dir, npz_name)

        short = ", ".join(f"{k}={v:.4f}" for k, v in sorted(params.items()))
        print(f"\n--- eval_{eval_idx:04d} ---")
        print(f"  Params: {short}")

        if not os.path.isfile(npz_path):
            print(f"  SKIP — .npz not found: {npz_path}")
            n_failed += 1
            continue

        project = None
        try:
            # ── Open F2F, set params, rebuild ────────────────────────
            project = conn.open_project(f2f_path)
            ok = project.update_parameters(params, use_full_rebuild=True)
            if not ok:
                print(f"  FAIL — parameter update returned False")
                n_failed += 1
                continue

            # ── Run frequency-domain solver ─────────────────────────
            print(f"  Running solver ...")
            t0 = time.perf_counter()
            result = solver.run(project)
            elapsed = time.perf_counter() - t0

            if not result.success:
                print(f"  FAIL [{result.error_type}] ({elapsed:.0f}s): {result.error_message}")
                n_failed += 1
                continue

            print(f"  Solver OK ({elapsed:.0f}s, {result.mesh_cells or '?'} cells)")

            # ── Save so cst.results can read ────────────────────────
            try:
                project.save()
            except Exception:
                pass

            # ── Read new S-parameter curves (latest run_id) ───────────
            reader = ResultReader(project.filename, allow_interactive=True)
            run_ids = reader.get_all_run_ids()
            latest_run = max(run_ids) if run_ids else 0
            rec = RecordingResultReader(reader)
            _read_fd_curves(rec, run_id=latest_run,
                            s11_tp=s11_tp, s21_tp=s21_tp, s31_tp=s31_tp)

            new_curves = rec.recorded_curves
            if not new_curves:
                print(f"  WARNING — no S-parameter curves read after solve")
                n_failed += 1
                continue

            print(f"  Read {len(new_curves)} S-parameter curves")

            # ── Load existing .npz and merge ────────────────────────
            existing = dict(np.load(npz_path, allow_pickle=True))
            # Re-save with merged curves (save_curves_npz handles formatting)
            merged = _load_curves_from_npz(existing)
            merged.update(new_curves)
            save_curves_npz(npz_path, merged)
            print(f"  Merged → {npz_name} ({len(merged)} total curves)")

            # ── Update index record ─────────────────────────────────
            for i, rec in enumerate(index_records):
                if rec.get("npz_file") == npz_name:
                    index_records[i]["has_f2f"] = True
                    has_f2w = rec.get("has_f2w", True)
                    has_f2wo = rec.get("has_f2wo", True)
                    index_records[i]["solver_ok"] = has_f2w and has_f2wo
                    break

            n_done += 1

        except Exception as exc:
            print(f"  FAIL — {exc}")
            n_failed += 1

        finally:
            if project is not None:
                try:
                    project.close(save=False)
                except Exception:
                    pass

    # ── Rewrite index ─────────────────────────────────────────────────
    if n_done > 0:
        os.remove(index_path)
        for rec in index_records:
            save_index_record(index_path, rec)
        print(f"\nIndex rewritten: {index_path}")

    # ── Clean up missing list ─────────────────────────────────────────
    remaining = [e for e in missing if e["eval_idx"] not in {
        m["eval_idx"] for m in missing[:n_done]
    }]
    # Actually, let's rebuild the missing list properly
    completed_idxs = set()
    for i in range(min(n_done, len(missing))):
        # Can't easily track which succeeded; re-derive from updated index
        pass

    # Re-derive remaining missing from updated index
    still_missing = []
    for rec in index_records:
        if not rec.get("has_f2f", False):
            still_missing.append({
                "eval_idx": rec["iter"],
                "params": rec.get("params", {}),
            })

    if still_missing:
        with open(missing_path, "w", encoding="utf-8") as fh:
            for entry in still_missing:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"Still missing F2F: {len(still_missing)} groups → {missing_path}")
    else:
        if os.path.isfile(missing_path):
            os.remove(missing_path)
        print("All F2F gaps filled — missing list removed.")

    # ── Close ─────────────────────────────────────────────────────────
    try:
        conn.close()
        print("CST connection closed.")
    except Exception:
        pass

    print(f"\nDone. {n_done} succeeded, {n_failed} failed.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_fd_curves(
    rec: RecordingResultReader,
    run_id: int,
    s11_tp: str = r"1D Results\S-Parameters\S1,1",
    s21_tp: str = r"1D Results\S-Parameters\S2,1",
    s31_tp: str = r"1D Results\S-Parameters\S3,1",
) -> None:
    """Read S11, S21, S31 from the frequency-domain project."""
    for tp in (s11_tp, s21_tp, s31_tp):
        try:
            rec.get_s_parameter(tp, run_id=run_id)
        except Exception:
            pass


def _load_curves_from_npz(data: dict) -> dict[str, dict]:
    """Reconstruct curves dict from raw .npz arrays (inverse of save_curves_npz)."""
    from cst_optimization.database import _sanitize

    curves: dict[str, dict] = {}
    bases = set()
    for key in data:
        key_str = str(key)
        if "/" in key_str:
            bases.add(key_str.split("/")[0])

    for base in bases:
        xdata_key = f"{base}/xdata"
        if xdata_key not in data:
            continue

        entry: dict = {
            "xdata": np.asarray(data[xdata_key], dtype=float),
        }
        if f"{base}/ydata_real" in data:
            yreal = np.asarray(data[f"{base}/ydata_real"], dtype=float)
            yimag_key = f"{base}/ydata_imag"
            if yimag_key in data:
                yimag = np.asarray(data[yimag_key], dtype=float)
                entry["ydata_real"] = yreal
                entry["ydata_imag"] = yimag
            else:
                entry["ydata_real"] = yreal

        if f"{base}/ref_imp_real" in data:
            entry["ref_imp_real"] = np.asarray(data[f"{base}/ref_imp_real"], dtype=float)
            if f"{base}/ref_imp_imag" in data:
                entry["ref_imp_imag"] = np.asarray(data[f"{base}/ref_imp_imag"], dtype=float)

        # Read metadata
        meta_key = f"{base}/__meta__"
        if meta_key in data:
            for pair in data[meta_key]:
                if pair[0] in ("xlabel", "ylabel", "curve_type"):
                    entry[pair[0]] = str(pair[1])

        # Try to reconstruct the original tree path (best effort)
        curve_type = entry.get("curve_type", "1d")
        entry.setdefault("curve_type", curve_type)
        entry.setdefault("xlabel", "")
        entry.setdefault("ylabel", "")

        curves[f"_{base}"] = entry  # prefix can't be recovered exactly

    return curves


if __name__ == "__main__":
    main()
