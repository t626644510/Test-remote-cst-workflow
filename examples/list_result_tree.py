"""Print result tree paths from a CST project file.

Usage:
    .venv\\Scripts\\python examples\\list_result_tree.py
    .venv\\Scripts\\python examples\\list_result_tree.py "D:/path/to/project.cst"
"""

import sys
import os as _os

_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

# ── Resolve CST library path BEFORE any cst import ─────────────────────
import yaml

_config_path = _os.path.join(_PROJECT_ROOT, "config", "default.yaml")
cfg = yaml.safe_load(open(_config_path, encoding="utf-8"))
_lib = cfg["cst"]["library_path"]

# Try env var as fallback
_lib_env = _os.environ.get("CST_LIBRARY_PATH", "")
if not _os.path.isdir(_lib) and _lib_env and _os.path.isdir(_lib_env):
    _lib = _lib_env

print(f"CST library path: {_lib}")
if not _os.path.isdir(_lib):
    print(f"ERROR: Path does not exist — check cst.library_path in config/default.yaml")
    print(f"  config path: {_config_path}")
    print(f"  library_path: {_lib}")
    # Try a few common locations as last resort
    _guesses = [
        r"D:/CST2026/CST Studio Suite 2026/AMD64/python_cst_libraries",
        r"C:/Program Files/Dassault Systemes/CST Studio Suite 2026/AMD64/python_cst_libraries",
        r"D:/Program Files/CST Studio Suite 2026/AMD64/python_cst_libraries",
    ]
    for g in _guesses:
        if _os.path.isdir(g):
            _lib = g
            print(f"  Found at: {_lib}")
            break
    else:
        sys.exit(1)

if _lib not in sys.path:
    sys.path.insert(0, _lib)

# Also add src/ for convenience
_SRC_DIR = _os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import cst.results


def list_tree(project_path: str) -> None:
    print(f"Project: {project_path}\n")
    pf = cst.results.ProjectFile(project_path, allow_interactive=True)

    # ── 3D results ───────────────────────────────────────────────────
    mod_3d = pf.get_3d()
    if mod_3d is not None:
        print("=" * 72)
        print("  3D Results")
        print("=" * 72)
        _print_module(mod_3d)

    # ── Schematic results ────────────────────────────────────────────
    try:
        mod_sch = pf.get_schematic()
        if mod_sch is not None:
            print("\n" + "=" * 72)
            print("  Schematic Results")
            print("=" * 72)
            _print_module(mod_sch)
    except Exception:
        pass

    # ── Sub-projects ─────────────────────────────────────────────────
    try:
        sub_names = pf.list_subprojects()
        if sub_names:
            print("\n" + "=" * 72)
            print(f"  Sub-projects ({len(sub_names)})")
            print("=" * 72)
            for sn in sub_names:
                print(f"\n  [{sn}]")
                sub = pf.load_subproject(sn)
                mod = sub.get_3d()
                if mod is not None:
                    _print_module(mod, indent="    ")
    except Exception:
        pass

    pf.close()


def _print_module(mod, indent: str = "") -> None:
    """Print tree items, run IDs, and parameter combinations."""

    # ── Tree items ───────────────────────────────────────────────────
    try:
        items = mod.get_tree_items()
    except Exception:
        items = []
    if items:
        print(f"\n{indent}Tree items ({len(items)}):")
        for it in items:
            print(f"{indent}  {it}")
    else:
        print(f"\n{indent}(no tree items accessible)")

    # ── Run IDs ──────────────────────────────────────────────────────
    try:
        run_ids = mod.get_all_run_ids()
    except Exception:
        try:
            run_ids = mod.get_run_ids()
        except Exception:
            run_ids = []
    if run_ids:
        print(f"\n{indent}Runs ({len(run_ids)}): {list(run_ids)}")
        last_run = run_ids[-1]
        try:
            param_combo = mod.get_parameter_combination(last_run)
            if param_combo:
                print(f"{indent}Parameters (run {last_run}):")
                for k, v in param_combo.items():
                    print(f"{indent}  {k} = {v}")
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="List CST result tree paths")
    parser.add_argument("project", nargs="?", default="",
                        help="Path to .cst file (default: from config)")
    args = parser.parse_args()

    if args.project:
        cst_path = args.project
    else:
        cst_path = cfg.get("tolerance", {}).get("project_path", "")
        if not cst_path:
            w3_cfg = yaml.safe_load(
                open(_os.path.join(_PROJECT_ROOT, "config", "workflow_3.yaml"),
                     encoding="utf-8"))
            cst_path = w3_cfg.get("project", {}).get("cst_path", "")

    if not cst_path or not _os.path.exists(cst_path):
        print(f"Project not found: {cst_path}")
        print("Usage: python examples\\list_result_tree.py <path_to.cst>")
        sys.exit(1)

    list_tree(cst_path)
