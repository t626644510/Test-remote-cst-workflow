"""Verify 1D-curve database round-trip and warmup.

Usage::

    python examples/verify_database.py [index.jsonl path]
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import yaml, numpy as np
from cst_optimization.database import (
    load_index, VirtualResultReader, curves_to_warmup,
)
from cst_optimization.factory import _build_objectives


def main(index_path: str = "D:/Results/raw_curves/index.jsonl") -> None:
    if not os.path.isfile(index_path):
        print(f"No index found at {index_path}")
        print("Run workflow_2 first to generate curve data, then re-run this script.")
        sys.exit(0)

    # Load index
    records = load_index(index_path)
    print(f"Index: {len(records)} evaluations")
    if not records:
        return

    # Inspect first .npz
    npz_dir = os.path.dirname(index_path) or "."
    first_npz = os.path.join(npz_dir, records[0].get("npz_file", ""))
    if os.path.isfile(first_npz):
        data = np.load(first_npz, allow_pickle=True)
        keys = sorted(data.keys())
        print(f"\nFirst .npz ({records[0]['npz_file']}): {len(keys)} keys")
        curve_bases = set(k.split("/")[0] for k in keys)
        print(f"Curves recorded: {len(curve_bases)}")
        for base in sorted(curve_bases):
            xdata_key = f"{base}/xdata"
            if xdata_key in data:
                n_pts = len(data[xdata_key])
                curve_type = "?"
                meta_key = f"{base}/__meta__"
                if meta_key in data:
                    for pair in data[meta_key]:
                        if pair[0] == "curve_type":
                            curve_type = str(pair[1])
                print(f"  {base}: {n_pts} points, type={curve_type}")

        # Test VirtualResultReader on first .npz
        print("\n--- VirtualResultReader test ---")
        vreader = VirtualResultReader(first_npz)
        for tp in sorted(vreader._tp_to_base.keys()):
            try:
                xd, yd = vreader.get_1d_result(tp)
                print(f"  {tp}: x=[{xd[0]:.3e}..{xd[-1]:.3e}] ({len(xd)} pts), "
                      f"y range [{float(np.min(np.abs(yd))):.4g}, {float(np.max(np.abs(yd))):.4g}]")
            except Exception as e:
                print(f"  {tp}: FAILED — {e}")
        data.close()

    # Test warmup
    print("\n--- Warmup test ---")
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'default.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    objectives, _, _ = _build_objectives(cfg['workflow_2']['objectives'])
    print(f"Objectives: {[o.name for o in objectives]}")
    for obj in objectives:
        print(f"  {obj.name}: mode={obj.mode}")

    X_w, y_w = curves_to_warmup(index_path, objectives)
    print(f"\nWarmup points: {len(X_w)}")
    if len(X_w) > 0:
        print(f"  y range: [{float(np.min(y_w)):.6f}, {float(np.max(y_w)):.6f}]")
        print(f"  y mean:  {float(np.mean(y_w)):.6f}")
        best = int(np.argmin(y_w))
        print(f"  Best idx: {best}, y={float(y_w[best]):.6f}")

        param_names = list(records[0].get("params", {}).keys())
        print(f"  Best params: {dict(zip(param_names, X_w[best]))}")


if __name__ == "__main__":
    index_path = sys.argv[1] if len(sys.argv) > 1 else "D:/Results/raw_curves/index.jsonl"
    main(index_path)
