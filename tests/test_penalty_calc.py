"""Read existing wakefield CST results from disk and compute SAO penalties.

Does NOT open CST Studio Suite — uses only ``cst.results`` (disk-based reads).

Usage::

    python tests/test_penalty_calc.py
"""

import os
import sys

# ── Path setup ──────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_project_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# ── CST library setup ───────────────────────────────────────────────────
# Read library path from config
import yaml

with open(os.path.join(_project_root, "config", "default.yaml"), "r") as fh:
    _cfg = yaml.safe_load(fh)

_cst_lib = _cfg.get("cst", {}).get(
    "library_path", r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries"
)
from cst_optimization.core import init_cst_path

init_cst_path(_cst_lib)

# ── Imports ─────────────────────────────────────────────────────────────
import numpy as np

from cst_optimization.core.results import ResultReader
from cst_optimization.physics.wakefield import (
    ParticleBeam,
    read_beam_impedance,
    compute_transverse_impedance,
    scalarize,
    aggregate_over_beams,
    WakeImpedanceData,
)
from cst_optimization.objectives.registry import get_objective, get_mode
# Force decorator registration
from cst_optimization.objectives import wakefield  # noqa: F401
from cst_optimization.objectives import antenna    # noqa: F401
from cst_optimization.objectives import modes      # noqa: F401

# ── Config ──────────────────────────────────────────────────────────────
wf2_cfg = _cfg["workflow_2"]
obj_cfgs = wf2_cfg["objectives"]
projects_cfg = wf2_cfg["projects"]

F2F_PATH = projects_cfg["frequency_domain"]["cst_path"]
F2W_PATH = projects_cfg["wakefield"]["cst_path"]
F2WO_PATH = projects_cfg["wakefield_offset"]["cst_path"]

print("=" * 70)
print("CST Result Penalty Calculator")
print(f"  F2F:  {F2F_PATH}")
print(f"  F2W:  {F2W_PATH}")
print(f"  F2WO: {F2WO_PATH}")
print("=" * 70)

# ── Open result readers (disk only, no DesignEnvironment) ───────────────
reader_f2f = ResultReader(F2F_PATH, allow_interactive=False)
reader_f2w = ResultReader(F2W_PATH, allow_interactive=False)
reader_f2wo = ResultReader(F2WO_PATH, allow_interactive=False)

print("\nResult files opened successfully.")
print(f"  F2F tree items: {reader_f2f.list_tree_items('0D/1D')[:5]}...")
print(f"  F2W tree items: {reader_f2w.list_tree_items('0D/1D')[:5]}...")
print(f"  F2WO tree items: {reader_f2wo.list_tree_items('0D/1D')[:5]}...")

# ── Read wakefield data ─────────────────────────────────────────────────
print("\n" + "-" * 70)
print("Reading wakefield impedance data...")

# ParticleBeam1 from F2W.cst (reference beam)
beam1 = ParticleBeam(name="ParticleBeam1", offset_x_mm=0.0, offset_y_mm=0.0, is_reference=True)
wake1 = read_beam_impedance(reader_f2w, beam1)

# ParticleBeam2 from F2Woffset.cst (offset beam)
beam2 = ParticleBeam(name="ParticleBeam2", offset_x_mm=2.0, offset_y_mm=0.0, is_reference=False)
wake2 = read_beam_impedance(reader_f2wo, beam2)

print(f"  ParticleBeam1 (F2W):")
if wake1.z_long is not None:
    zl1 = wake1.z_long
    print(f"    Z_long: {len(zl1.frequencies)} pts, "
          f"{zl1.frequencies[0]/1e6:.1f}-{zl1.frequencies[-1]/1e6:.1f} MHz, "
          f"peak |Z|={np.max(np.abs(zl1.impedance)):.1f} ohm")
else:
    print(f"    Z_long: MISSING")
if wake1.z_x is not None:
    print(f"    Z_x:    {len(wake1.z_x.frequencies)} pts, peak |Z|={np.max(np.abs(wake1.z_x.impedance)):.1f} ohm")
else:
    print(f"    Z_x:    MISSING")
if wake1.z_y is not None:
    print(f"    Z_y:    {len(wake1.z_y.frequencies)} pts, peak |Z|={np.max(np.abs(wake1.z_y.impedance)):.1f} ohm")
else:
    print(f"    Z_y:    MISSING")

print(f"  ParticleBeam2 (F2Woffset):")
if wake2.z_long is not None:
    zl2 = wake2.z_long
    print(f"    Z_long: {len(zl2.frequencies)} pts, "
          f"{zl2.frequencies[0]/1e6:.1f}-{zl2.frequencies[-1]/1e6:.1f} MHz, "
          f"peak |Z|={np.max(np.abs(zl2.impedance)):.1f} ohm")
else:
    print(f"    Z_long: MISSING")
if wake2.z_x is not None:
    print(f"    Z_x:    {len(wake2.z_x.frequencies)} pts, peak |Z|={np.max(np.abs(wake2.z_x.impedance)):.1f} ohm")
else:
    print(f"    Z_x:    MISSING")
if wake2.z_y is not None:
    print(f"    Z_y:    {len(wake2.z_y.frequencies)} pts, peak |Z|={np.max(np.abs(wake2.z_y.impedance)):.1f} ohm")
else:
    print(f"    Z_y:    MISSING")

# ── Build objectives from config ────────────────────────────────────────
print("\n" + "-" * 70)
print("Building objectives from config...")

objectives = {}
raw_values = {}
penalties = {}

for entry in obj_cfgs:
    name = entry["name"]
    if not entry.get("enabled", True):
        continue

    obj_cls = get_objective(name)
    mode_name = entry.get("mode", "minimize")
    mode_cls = get_mode(mode_name)
    mode_params = entry.get("mode_params", {})
    mode = mode_cls(**mode_params) if mode_params else mode_cls()
    obj_params = dict(entry.get("obj_params", {}))
    proj_label = obj_params.pop("project", "")
    ref_proj = obj_params.pop("ref_project", "")

    # Map project label → reader factory
    if proj_label == "frequency_domain":
        rf = lambda r=reader_f2f: r
    elif proj_label == "wakefield_offset":
        rf = lambda r=reader_f2wo: r
    else:
        rf = lambda r=reader_f2w: r

    # Build ref_reader_factory if ref_project is set
    ref_rf = None
    if ref_proj == "wakefield":
        ref_rf = lambda r=reader_f2w: r
    elif ref_proj == "frequency_domain":
        ref_rf = lambda r=reader_f2f: r

    kwargs = {"reader_factory": rf, "mode": mode, **obj_params}
    if ref_rf is not None:
        kwargs["ref_reader_factory"] = ref_rf

    obj = obj_cls(**kwargs)
    objectives[name] = obj
    print(f"  {name}: project={proj_label}", end="")
    if ref_proj:
        print(f", ref_project={ref_proj}", end="")
    print()

# ── Compute raw values ──────────────────────────────────────────────────
print("\n" + "-" * 70)
print("Computing raw values...")

for name, obj in objectives.items():
    try:
        raw = obj.raw_value()
        raw_values[name] = raw
        print(f"  {name}: raw = {raw:.6g}")
    except Exception as exc:
        raw_values[name] = np.nan
        print(f"  {name}: ERROR — {exc}")

# ── Compute transverse impedance (detailed) ─────────────────────────────
print("\n" + "-" * 70)
print("Transverse impedance detail:")

try:
    z_trans = compute_transverse_impedance(wake1, wake2)
    print(f"  Frequencies: {len(z_trans.frequencies)} pts, "
          f"{z_trans.frequencies[0]/1e6:.1f}-{z_trans.frequencies[-1]/1e6:.1f} MHz")
    print(f"  Z_trans peak: {np.max(z_trans.impedance):.1f} ohm/m")
    print(f"  Z_trans mean: {np.mean(z_trans.impedance):.1f} ohm/m")

    # Show where Z_trans exceeds threshold
    zt_cfg = None
    for e in obj_cfgs:
        if e["name"] == "z_transverse":
            zt_cfg = e
            break
    if zt_cfg:
        threshold = float(zt_cfg["obj_params"]["z_threshold_ohm_per_m"])
        freq_min = float(zt_cfg.get("obj_params", {}).get("freq_min_hz", 0) or 0)
        above = z_trans.impedance > threshold
        if np.any(above):
            n_above = np.sum(above)
            peak_above = np.max(z_trans.impedance[above])
            print(f"  *** {n_above} frequency points EXCEED threshold {threshold:.0f} ohm/m ***")
            print(f"  *** Peak exceedance: {peak_above:.1f} ohm/m ***")
        else:
            print(f"  All points below threshold {threshold:.0f} ohm/m")
except Exception as exc:
    print(f"  ERROR computing transverse impedance: {exc}")

# ── Compute penalties ───────────────────────────────────────────────────
print("\n" + "-" * 70)
print("Penalty computation:")

total_penalty = 0.0
n_obj = 0
for name, obj in objectives.items():
    raw = raw_values[name]
    if np.isfinite(raw):
        penalty = obj.mode.compute(float(raw))
        penalties[name] = penalty
        total_penalty += penalty
        n_obj += 1
        print(f"  obj_{name}: raw={raw:.6g} → penalty={penalty:.6f}")
    else:
        penalties[name] = 1.0
        total_penalty += 1.0
        n_obj += 1
        print(f"  obj_{name}: raw=N/A → penalty=1.000000 (default)")

# ── SAO weighted scalar ─────────────────────────────────────────────────
print("\n" + "=" * 70)
if n_obj > 0:
    avg_penalty = total_penalty / n_obj
else:
    avg_penalty = 1.0
print(f"SAO weighted scalar (equal weights, {n_obj} objectives): {avg_penalty:.6f}")
print(f"Total penalty sum: {total_penalty:.6f}")
print("=" * 70)
