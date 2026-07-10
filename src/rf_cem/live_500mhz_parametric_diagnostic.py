"""Live-CST diagnostic runner for generated parametric 500 MHz geometry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .live_500mhz_diagnostic import _run_live_diagnostic


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.live_500mhz_parametric_diagnostic",
        description="Run live-CST import/setup diagnostics for a parametric geometry package.",
    )
    parser.add_argument("--package-dir", type=Path, required=True, help="Path to runs/parametric_geometry_500mhz.")
    parser.add_argument(
        "--library-path",
        default=r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries",
        help="CST python_cst_libraries path.",
    )
    parser.add_argument("--project-path", type=Path, default=None, help="Optional output .cst path.")
    parser.add_argument("--connect-mode", choices=("new", "any", "any_or_new"), default="new")
    parser.add_argument("--timeout-s", type=float, default=120.0, help="Per-history-block timeout.")
    parser.add_argument("--run-solver", action="store_true", help="Run the configured eigenmode solver after setup.")
    parser.add_argument("--solver-timeout-s", type=float, default=7200.0, help="Solver timeout when --run-solver is set.")
    args = parser.parse_args(argv)

    actions_path = args.package_dir / "translator" / "rf_cem_artifacts" / "generated" / "cst_actions.json"
    if not actions_path.exists():
        raise FileNotFoundError(f"parametric CST actions not found: {actions_path}")
    actions = json.loads(actions_path.read_text(encoding="utf-8"))
    live_dir = args.package_dir / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    project_path = args.project_path or (live_dir / "rf_cem_500mhz_parametric_diagnostic.cst")
    report = _run_live_diagnostic(
        library_path=args.library_path,
        connect_mode=args.connect_mode,
        project_path=project_path,
        actions=actions,
        timeout_s=args.timeout_s,
        run_solver=args.run_solver,
        solver_timeout_s=args.solver_timeout_s,
    )
    report["schema_version"] = "live_cst_parametric_diagnostic.v0"
    report["parametric_package"] = str(args.package_dir)
    report["actions"] = str(actions_path)
    report_path = live_dir / "live_parametric_diagnostic_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote live CST parametric diagnostic report to {report_path}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
