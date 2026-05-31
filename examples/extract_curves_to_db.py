"""Extract all parametric-run 1D curves from the three workflow-2 CST projects,
group them by parameter set, and save merged groups to the curves database.

Usage::

    python examples/extract_curves_to_db.py

Reads from:
    - F2F.cst       (frequency-domain S-parameters)
    - F2W.cst       (wakefield impedance, reference beam)
    - F2W_offset.cst (wakefield impedance, offset beam)

Outputs:
    - D:/Results/raw_curves/eval_NNNN.npz   (merged 1D curves per param group)
    - D:/Results/raw_curves/index.jsonl      (per-group metadata)
    - D:/Results/raw_curves/missing_f2f_params.jsonl  (groups needing F2F re-run)
"""

from __future__ import annotations

import json
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_project_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import yaml
import numpy as np

from cst_optimization.core.results import ResultReader
from cst_optimization.database import (
    RecordingResultReader,
    save_curves_npz,
    save_index_record,
)

# Rounding precision for parameter matching
_PARAM_ROUND = 6


def main() -> None:
    # ── Load config ───────────────────────────────────────────────────
    with open("config/default.yaml", "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    wf2 = cfg["workflow_2"]
    projects = wf2["projects"]
    param_names = [p["name"] for p in wf2["parameters"]]

    # ── S-parameter tree paths from config ────────────────────────────
    rp = wf2.get("result_paths", {})
    s11_tp = rp.get("s11", r"1D Results\S-Parameters\S1,1")
    s21_tp = rp.get("s21", r"1D Results\S-Parameters\S2,1")
    s31_tp = rp.get("s31", r"1D Results\S-Parameters\S3,1")

    cst_lib = cfg.get("cst", {}).get(
        "library_path", r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries"
    )

    # Ensure CST Python libs are importable (no DE connection needed)
    from cst_optimization.core import init_cst_path
    init_cst_path(cst_lib)

    # ── Collect runs from all three projects ──────────────────────────
    # project_data[label] = {param_key: {"params": dict, "curves": dict}}
    project_data: dict[str, dict[str, dict]] = {}

    for label, proj_cfg in projects.items():
        cst_path = proj_cfg["cst_path"]
        if not os.path.isfile(cst_path):
            print(f"[{label}] SKIP — file not found: {cst_path}")
            continue

        print(f"\n[{label}] {cst_path}")
        reader = ResultReader(cst_path, allow_interactive=True)
        run_ids = reader.get_all_run_ids()
        print(f"  Found {len(run_ids)} runs: {run_ids}")

        label_data: dict[str, dict] = {}
        skipped_no_params = 0

        for run_id in run_ids:
            params = reader.get_parameter_combination(run_id)
            if not params:
                skipped_no_params += 1
                continue

            # Only keep parameters that are in the workflow 2 config
            filtered = {}
            for pn in param_names:
                v = params.get(pn)
                if v is not None:
                    filtered[pn] = float(v)

            if not filtered:
                skipped_no_params += 1
                continue

            # Round for matching
            key = _make_key(filtered)

            # Read curves
            rec = RecordingResultReader(reader)
            if label == "frequency_domain":
                _read_fd_curves(rec, run_id, s11_tp, s21_tp, s31_tp)
            elif label == "wakefield":
                _read_wake_curves(rec, run_id, ["ParticleBeam1"])
            elif label == "wakefield_offset":
                _read_wake_curves(rec, run_id, ["ParticleBeam2"])

            label_data[key] = {
                "params": filtered,
                "curves": rec.recorded_curves.copy(),
                "run_id": run_id,
            }

        if skipped_no_params:
            print(f"  Skipped {skipped_no_params} runs (no parameter data)")
        print(f"  Unique param sets: {len(label_data)}")
        project_data[label] = label_data

    # ── Merge groups across projects ──────────────────────────────────
    # Collect all unique param keys
    all_keys: set[str] = set()
    for ld in project_data.values():
        all_keys.update(ld.keys())
    all_keys_sorted = sorted(all_keys)

    print(f"\n--- Merging across projects ---")
    print(f"Total unique param sets: {len(all_keys_sorted)}")

    # Database output
    db_dir = cfg.get("logging", {}).get("output_dir", "D:/Results") + "/raw_curves"
    os.makedirs(db_dir, exist_ok=True)
    # Clear old index
    index_path = os.path.join(db_dir, "index.jsonl")
    if os.path.isfile(index_path):
        os.remove(index_path)

    # Clear old .npz files
    for old_npz in os.listdir(db_dir):
        if old_npz.startswith("eval_") and old_npz.endswith(".npz"):
            os.remove(os.path.join(db_dir, old_npz))

    complete = 0
    missing_f2f: list[dict] = []
    missing_f2w: list[dict] = []
    missing_f2wo: list[dict] = []
    eval_idx = 0

    for key in all_keys_sorted:
        # Gather params from the first project that has this key
        params = None
        curves_merged: dict[str, dict] = {}
        has_f2f = False
        has_f2w = False
        has_f2wo = False

        for label in ["frequency_domain", "wakefield", "wakefield_offset"]:
            ld = project_data.get(label, {})
            if key in ld:
                entry = ld[key]
                if params is None:
                    params = entry["params"]
                curves_merged.update(entry["curves"])
                if label == "frequency_domain":
                    has_f2f = True
                elif label == "wakefield":
                    has_f2w = True
                elif label == "wakefield_offset":
                    has_f2wo = True

        if params is None or not curves_merged:
            continue

        # Save merged .npz
        npz_name = f"eval_{eval_idx:04d}.npz"
        npz_path = os.path.join(db_dir, npz_name)
        save_curves_npz(npz_path, curves_merged)

        save_index_record(index_path, {
            "iter": eval_idx,
            "params": params,
            "npz_file": npz_name,
            "solver_ok": has_f2f and has_f2w and has_f2wo,
            "error": "",
            "has_f2f": has_f2f,
            "has_f2w": has_f2w,
            "has_f2wo": has_f2wo,
        })

        if has_f2f and has_f2w and has_f2wo:
            complete += 1
        if not has_f2f:
            missing_f2f.append({"eval_idx": eval_idx, "params": params})
        if not has_f2w:
            missing_f2w.append({"eval_idx": eval_idx, "params": params})
        if not has_f2wo:
            missing_f2wo.append({"eval_idx": eval_idx, "params": params})

        eval_idx += 1

    # ── Save missing-F2F list for re-computation ──────────────────────
    if missing_f2f:
        missing_path = os.path.join(db_dir, "missing_f2f_params.jsonl")
        with open(missing_path, "w", encoding="utf-8") as fh:
            for entry in missing_f2f:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Total eval groups:  {eval_idx}")
    print(f"Complete (3/3):    {complete}")
    print(f"Missing F2F:       {len(missing_f2f)}  ← need re-run (fast, freq-domain)")
    print(f"Missing F2W:       {len(missing_f2w)}")
    print(f"Missing F2W_offset:{len(missing_f2wo)}")
    print(f"\nDatabase: {db_dir}/")
    if missing_f2f:
        print(f"Re-run list: {missing_path}")
        print(f"\nParams needing F2F re-computation:")
        for entry in missing_f2f:
            short = ", ".join(f"{k}={v:.4f}" for k, v in sorted(entry["params"].items()))
            print(f"  eval_{entry['eval_idx']:04d}: {short}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_key(params: dict[str, float]) -> str:
    """Stable string key from rounded parameter values."""
    parts = []
    for name in sorted(params.keys()):
        parts.append(f"{name}={params[name]:.{_PARAM_ROUND}f}")
    return ";".join(parts)


def _read_fd_curves(
    rec: RecordingResultReader,
    run_id: int,
    s11_tp: str = r"1D Results\S-Parameters\S1,1",
    s21_tp: str = r"1D Results\S-Parameters\S2,1",
    s31_tp: str = r"1D Results\S-Parameters\S3,1",
) -> None:
    for tp in (s11_tp, s21_tp, s31_tp):
        try:
            rec.get_s_parameter(tp, run_id=run_id)
        except Exception:
            pass


def _read_wake_curves(
    rec: RecordingResultReader, run_id: int, beam_names: list[str],
) -> None:
    for beam_name in beam_names:
        for direction in ["Z", "X", "Y"]:
            tp = (
                f"1D Results\\Particle Beams\\{beam_name}"
                f"\\Wake impedance\\{direction}"
            )
            try:
                rec.get_1d_result(tp, run_id=run_id)
            except Exception:
                pass


if __name__ == "__main__":
    main()
