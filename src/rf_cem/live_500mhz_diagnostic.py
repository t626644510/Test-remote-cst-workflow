"""Live-CST diagnostic runner for the 500 MHz CSTTranslator v0 artifacts."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Sequence

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.solver import SolverRunner

from .build_500mhz_baseline import write_artifacts
from .design_package import BaselineDesignPackage, BaselinePaths
from .history_templates import load_cst_history_templates
from .translator import translate_baseline
from .udsg_builder import build_baseline_udsg


def main(argv: Sequence[str] | None = None) -> int:
    """Create a disposable CST project and execute generated VBA blocks."""
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.live_500mhz_diagnostic",
        description="Run a live-CST import/setup diagnostic for the 500 MHz baseline without starting the solver.",
    )
    parser.add_argument("--appendix", type=Path, required=True, help="Path to Appendix/500MHz_baseline.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated artifacts and report.")
    parser.add_argument(
        "--library-path",
        default=r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries",
        help="CST python_cst_libraries path.",
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Optional output .cst path. Defaults under output-dir/live/.",
    )
    parser.add_argument("--connect-mode", choices=("new", "any", "any_or_new"), default="new")
    parser.add_argument("--timeout-s", type=float, default=120.0, help="Per-history-block timeout.")
    args = parser.parse_args(argv)

    paths = BaselinePaths.from_appendix(args.appendix)
    paths.validate()
    templates = load_cst_history_templates(paths.model_history_json)
    udsg, review_diff = build_baseline_udsg(paths, BaselineDesignPackage(), templates.recipe)
    artifacts = translate_baseline(udsg, templates, paths.step_file, filename_mode="absolute")
    write_artifacts(args.output_dir, udsg, review_diff, artifacts)

    live_dir = args.output_dir / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    project_path = args.project_path or (live_dir / "rf_cem_500mhz_diagnostic.cst")
    report_path = live_dir / "live_diagnostic_report.json"

    report = _run_live_diagnostic(
        library_path=args.library_path,
        connect_mode=args.connect_mode,
        project_path=project_path,
        actions=artifacts.actions,
        timeout_s=args.timeout_s,
        run_solver=False,
    )
    report["generated_artifacts"] = {
        "udsg": str(args.output_dir / "semantic" / "udsg.v0.json"),
        "actions": str(args.output_dir / "generated" / "cst_actions.json"),
        "script": str(args.output_dir / "generated" / "cst_script.bas"),
        "translator_report": str(args.output_dir / "generated" / "translator_report.json"),
    }
    _write_json(report_path, report)
    print(f"Wrote live CST diagnostic report to {report_path}")
    return 0 if report["status"] == "ok" else 1


def _run_live_diagnostic(
    *,
    library_path: str,
    connect_mode: str,
    project_path: Path,
    actions: list[dict],
    timeout_s: float,
    run_solver: bool = False,
    solver_timeout_s: float | None = None,
) -> dict:
    started_at = time.time()
    action_results = []
    project_saved = False
    messages = None
    active_solver = ""
    filename = ""
    pid = None
    solver_result = None

    try:
        with CSTConnection(library_path=library_path, mode=connect_mode) as conn:
            pid = conn.pid
            conn.set_quiet_mode(True)
            project = conn.new_mws_project()
            try:
                filename = project.filename
                for action in actions:
                    result = _execute_action(project, action, timeout_s)
                    action_results.append(result)
                    if not result["success"]:
                        break
                active_solver = project.get_active_solver_name()
                if run_solver:
                    solver = SolverRunner(timeout_s=solver_timeout_s or timeout_s)
                    solver_result = solver.run(project)
                try:
                    messages = project.get_messages()
                except Exception as exc:
                    messages = f"<get_messages failed: {exc}>"
                project_saved = project.save(
                    path=str(project_path),
                    include_results=False,
                    allow_overwrite=True,
                )
            finally:
                project.close(save=False)
    except Exception as exc:
        action_results.append(
            {
                "action_id": "<connection_or_project>",
                "caption": "connect/new/save CST project",
                "success": False,
                "error": repr(exc),
            }
        )

    failures = [item for item in action_results if not item.get("success")]
    return {
        "schema_version": "live_cst_diagnostic.v0",
        "status": "ok" if not failures and project_saved else "failed",
        "started_at_unix": started_at,
        "elapsed_s": time.time() - started_at,
        "cst_pid": pid,
        "initial_project_filename": filename,
        "saved_project": str(project_path),
        "project_saved": project_saved,
        "active_solver": active_solver,
        "action_results": action_results,
        "solver_result": _solver_result_dict(solver_result),
        "messages": str(messages),
    }


def _execute_action(project: object, action: dict, timeout_s: float) -> dict:
    action_id = str(action.get("action_id"))
    caption = str(action.get("caption") or action_id)
    try:
        project.execute_vba(str(action.get("vba", "")), header=caption, timeout=timeout_s)
        return {
            "action_id": action_id,
            "caption": caption,
            "success": True,
            "error": "",
        }
    except Exception as exc:
        return {
            "action_id": action_id,
            "caption": caption,
            "success": False,
            "error": repr(exc),
        }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _solver_result_dict(result: object | None) -> dict | None:
    if result is None:
        return None
    return {
        "success": bool(getattr(result, "success", False)),
        "error_type": getattr(result, "error_type", None),
        "error_message": getattr(result, "error_message", None),
        "elapsed_s": getattr(result, "elapsed_s", 0.0),
        "mesh_cells": getattr(result, "mesh_cells", None),
        "frequency_mhz": None,
        "frequency_note": "frequency extraction is not implemented in this MVP; confirm manually or add a verified CST result parser later",
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
