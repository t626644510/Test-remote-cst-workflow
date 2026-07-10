"""Live-CST diagnostic that attaches known 0D eigenmode postprocessing templates."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Sequence

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.results import ResultReader
from cst_optimization.core.solver import SolverRunner

from .live_500mhz_diagnostic import _run_live_diagnostic


_TEMPLATE_FILES = {
    "frequency_mhz": {
        "file": "Frequency (Mode 1).r0d",
        "source_name": r"3D\Frequency (Mode 1)",
        "tree_path": r"Tables\0D Results\Frequency (Mode 1)",
        "unit": "MHz",
    },
    "r_over_q_ohm": {
        "file": "R over Q (Mode 1).r0d",
        "source_name": r"3D\R over Q (Mode 1)",
        "tree_path": r"Tables\0D Results\R over Q (Mode 1)",
        "unit": "Ohm",
    },
    "q_factor": {
        "file": "Q-Factor (Perturbation) (Mode 1).r0d",
        "source_name": r"3D\Q-Factor (Perturbation) (Mode 1)",
        "tree_path": r"Tables\0D Results\Q-Factor (Perturbation) (Mode 1)",
        "unit": "dimensionless",
    },
}

_MODEL_RPP_RECORD_LINE_COUNT = 11


def main(argv: Sequence[str] | None = None) -> int:
    """Create a CST project, attach verified template artifacts, and save it."""
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.live_500mhz_postprocessing_diagnostic",
        description="Create a parametric 500 MHz CST project with known 0D postprocessing templates attached.",
    )
    parser.add_argument("--package-dir", type=Path, required=True, help="Path to a parametric geometry package.")
    parser.add_argument(
        "--template-project-dir",
        type=Path,
        default=Path(r"D:\ModelData\bare"),
        help="Unpacked CST project directory containing Model/3D/*.r0d template artifacts.",
    )
    parser.add_argument(
        "--library-path",
        default=r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries",
        help="CST python_cst_libraries path.",
    )
    parser.add_argument("--project-path", type=Path, default=None, help="Optional output .cst path.")
    parser.add_argument("--connect-mode", choices=("new", "any", "any_or_new"), default="new")
    parser.add_argument("--timeout-s", type=float, default=120.0, help="Per-history-block timeout.")
    parser.add_argument("--run-solver", action="store_true", help="Run the configured eigenmode solver after template registration.")
    parser.add_argument(
        "--evaluate-templates",
        action="store_true",
        help="Call CST's documented EvaluateResultTemplates command after opening the registered project.",
    )
    parser.add_argument("--solver-timeout-s", type=float, default=7200.0, help="Solver timeout when --run-solver is set.")
    args = parser.parse_args(argv)

    actions_path = args.package_dir / "translator" / "rf_cem_artifacts" / "generated" / "cst_actions.json"
    if not actions_path.exists():
        raise FileNotFoundError(f"parametric CST actions not found: {actions_path}")
    actions = json.loads(actions_path.read_text(encoding="utf-8"))

    live_dir = args.package_dir / "live_postprocessing"
    live_dir.mkdir(parents=True, exist_ok=True)
    project_path = (args.project_path or (live_dir / "rf_cem_500mhz_parametric_postprocessing.cst")).resolve()

    setup_report = _run_live_diagnostic(
        library_path=args.library_path,
        connect_mode=args.connect_mode,
        project_path=project_path,
        actions=actions,
        timeout_s=args.timeout_s,
        run_solver=False,
    )

    project_dir = _project_dir_for(project_path)
    attach_report = _attach_postprocessing_templates(args.template_project_dir, project_dir)
    reopen_report = _reopen_and_save_project(args.library_path, args.connect_mode, project_path)
    solver_postprocess_report = _run_solver_and_postprocess(
        args.library_path,
        args.connect_mode,
        project_path,
        run_solver=args.run_solver,
        evaluate_templates=args.evaluate_templates,
        solver_timeout_s=args.solver_timeout_s,
        timeout_s=args.timeout_s,
    )
    final_artifacts = _inspect_postprocessing_artifacts(project_dir)
    tree_report = _list_result_tree_items(project_path)

    report = {
        "schema_version": "live_cst_postprocessing_template_diagnostic.v0",
        "status": "ok"
        if setup_report.get("status") == "ok"
        and attach_report["status"] == "ok"
        and reopen_report["status"] == "ok"
        and solver_postprocess_report["status"] in {"ok", "skipped"}
        and final_artifacts["status"] == "ok"
        else "failed",
        "parametric_package": str(args.package_dir),
        "project_path": str(project_path),
        "project_dir": str(project_dir),
        "template_project_dir": str(args.template_project_dir),
        "setup_report": setup_report,
        "attach_report": attach_report,
        "reopen_report": reopen_report,
        "solver_postprocess_report": solver_postprocess_report,
        "final_artifacts": final_artifacts,
        "result_tree_probe": tree_report,
    }
    report_path = live_dir / "live_postprocessing_diagnostic_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote live CST postprocessing diagnostic report to {report_path}")
    print(f"Saved CST project with postprocessing templates to {project_path}")
    return 0 if report["status"] == "ok" else 1


def _project_dir_for(project_path: Path) -> Path:
    return project_path.with_suffix("")


def _attach_postprocessing_templates(template_project_dir: Path, project_dir: Path) -> dict:
    started = time.time()
    source_3d = template_project_dir / "Model" / "3D"
    target_3d = project_dir / "Model" / "3D"
    target_model = project_dir / "Model"
    copied: list[dict] = []
    missing: list[str] = []

    target_3d.mkdir(parents=True, exist_ok=True)
    for metric_id, spec in _TEMPLATE_FILES.items():
        source = source_3d / str(spec["file"])
        target = target_3d / str(spec["file"])
        if not source.exists():
            missing.append(str(source))
            continue
        shutil.copy2(source, target)
        copied.append(
            {
                "metric_id": metric_id,
                "source": str(source),
                "target": str(target),
                "source_name": spec["source_name"],
                "tree_path": spec["tree_path"],
                "unit": spec["unit"],
            }
        )

    if not missing:
        pc_report = _merge_pc_output_variables(target_model / "PC_integration.json")
        rpp_report = _install_model_rpp(template_project_dir, project_dir)
    else:
        pc_report = {"status": "skipped_missing_templates"}
        rpp_report = {"status": "skipped_missing_templates"}

    return {
        "status": "ok"
        if not missing and len(copied) == len(_TEMPLATE_FILES) and rpp_report["status"] == "ok"
        else "failed",
        "elapsed_s": time.time() - started,
        "copied_templates": copied,
        "missing_templates": missing,
        "pc_integration": pc_report,
        "model_rpp": rpp_report,
        "note": (
            "Template artifacts are copied from an existing CST project as read-only evidence. "
            "Model/3D/Model.rpp registers those artifacts with CST's Template Based Post-Processing UI/framework."
        ),
    }


def _merge_pc_output_variables(path: Path) -> dict:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "execution": {
                "classname": "SMAPowerByEmagHPCFrameReduced",
                "libname": "SMAPowerByEmagUI",
            },
            "inputVariables": [],
            "outputVariables": [],
        }

    outputs = {
        str(item.get("name")): item
        for item in payload.get("outputVariables", [])
        if isinstance(item, dict) and item.get("name")
    }
    added = []
    for spec in _TEMPLATE_FILES.values():
        name = str(spec["source_name"])
        if name not in outputs:
            outputs[name] = {"len": 1, "name": name, "type": "float"}
            added.append(name)
    payload["outputVariables"] = [outputs[name] for name in sorted(outputs)]
    path.write_text(json.dumps(payload, indent=3, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "ok", "path": str(path), "added_output_variables": added}


def _install_model_rpp(template_project_dir: Path, project_dir: Path) -> dict:
    source = template_project_dir / "Model" / "3D" / "Model.rpp"
    target = project_dir / "Model" / "3D" / "Model.rpp"
    wanted_names = {Path(str(spec["file"])).stem for spec in _TEMPLATE_FILES.values()}

    if source.exists():
        selected = _select_model_rpp_records(source, wanted_names)
        if selected["status"] == "ok":
            target.write_text(selected["text"], encoding="utf-8")
            return {
                "status": "ok",
                "source": str(source),
                "target": str(target),
                "registered_templates": selected["registered_templates"],
                "source_policy": "filtered_source_model_rpp",
            }
        return selected

    text = _fallback_model_rpp_text()
    target.write_text(text, encoding="utf-8")
    return {
        "status": "ok",
        "source": "",
        "target": str(target),
        "registered_templates": sorted(wanted_names),
        "source_policy": "built_from_verified_500mhz_template_metadata",
        "warning": "Source Model.rpp was missing; used the minimal 500 MHz template registry format verified in live CST.",
    }


def _select_model_rpp_records(path: Path, wanted_names: set[str]) -> dict:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if len(lines) < 5:
        return {"status": "failed", "error": f"Model.rpp is too short: {path}"}
    try:
        record_line_count = int(lines[0].strip())
        record_count = int(lines[3].strip())
    except ValueError as exc:
        return {"status": "failed", "error": f"Cannot parse Model.rpp header: {exc}"}
    if record_line_count != _MODEL_RPP_RECORD_LINE_COUNT:
        return {
            "status": "failed",
            "error": f"Unsupported Model.rpp record size {record_line_count}; expected {_MODEL_RPP_RECORD_LINE_COUNT}",
        }

    cursor = 4
    selected_records: list[list[str]] = []
    selected_names: list[str] = []
    for _ in range(record_count):
        record = lines[cursor : cursor + record_line_count]
        cursor += record_line_count
        if len(record) != record_line_count:
            return {"status": "failed", "error": f"Truncated Model.rpp record in {path}"}
        result_name = record[0].strip()
        if result_name in wanted_names:
            selected_records.append(record)
            selected_names.append(result_name)

    missing = sorted(wanted_names.difference(selected_names))
    if missing:
        return {"status": "failed", "error": f"Model.rpp missing required template records: {missing}"}

    output_lines = [lines[0], lines[1], lines[2], str(len(selected_records))]
    for record in selected_records:
        output_lines.extend(record)
    output_lines.append(lines[cursor].strip() if cursor < len(lines) else "0")
    return {
        "status": "ok",
        "text": "\n".join(output_lines) + "\n",
        "registered_templates": selected_names,
    }


def _fallback_model_rpp_text() -> str:
    records = [
        ("Frequency (Mode 1)", "P"),
        ("R over Q (Mode 1)", "P"),
        ("Q-Factor (Perturbation) (Mode 1)", "1"),
    ]
    lines = ["11", "0", "0", str(len(records))]
    for result_name, flag in records:
        lines.extend(
            [
                result_name,
                "3D Eigenmode Result",
                "1",
                "0D",
                "2D and 3D Field Results",
                flag,
                "ED10",
                "3D Eigenmode Result^+MWS+PS+DS.rtp",
                "VBA",
                "1",
                result_name,
            ]
        )
    lines.append("0")
    return "\n".join(lines) + "\n"


def _reopen_and_save_project(library_path: str, connect_mode: str, project_path: Path) -> dict:
    started = time.time()
    try:
        with CSTConnection(library_path=library_path, mode=connect_mode) as conn:
            conn.set_quiet_mode(True)
            project = conn.open_project(str(project_path))
            try:
                active_solver = project.get_active_solver_name()
                try:
                    messages = str(project.get_messages())
                except Exception as exc:
                    messages = f"<get_messages failed: {exc}>"
                saved = project.save(path=str(project_path), include_results=False, allow_overwrite=True)
            finally:
                project.close(save=False)
        return {
            "status": "ok" if saved else "failed",
            "elapsed_s": time.time() - started,
            "active_solver": active_solver,
            "project_saved_after_reopen": saved,
            "messages": messages,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "elapsed_s": time.time() - started,
            "error": repr(exc),
        }


def _run_solver_and_postprocess(
    library_path: str,
    connect_mode: str,
    project_path: Path,
    *,
    run_solver: bool,
    evaluate_templates: bool,
    solver_timeout_s: float,
    timeout_s: float,
) -> dict:
    if not run_solver and not evaluate_templates:
        return {"status": "skipped", "note": "Use --run-solver and/or --evaluate-templates for live-CST result validation."}

    started = time.time()
    solver_result = None
    evaluate_report = {"status": "skipped"}
    try:
        with CSTConnection(library_path=library_path, mode=connect_mode) as conn:
            conn.set_quiet_mode(True)
            project = conn.open_project(str(project_path))
            try:
                if run_solver:
                    solver = SolverRunner(timeout_s=solver_timeout_s)
                    solver_result = solver.run(project)
                if evaluate_templates:
                    evaluate_report = _evaluate_result_templates(project, timeout_s)
                saved = project.save(path=str(project_path), include_results=True, allow_overwrite=True)
            finally:
                project.close(save=False)
    except Exception as exc:
        return {
            "status": "failed",
            "elapsed_s": time.time() - started,
            "error": repr(exc),
            "solver_result": _solver_result_dict(solver_result),
            "evaluate_templates": evaluate_report,
        }

    solver_ok = solver_result is None or bool(getattr(solver_result, "success", False))
    evaluate_ok = evaluate_report["status"] in {"ok", "skipped"}
    return {
        "status": "ok" if saved and solver_ok and evaluate_ok else "failed",
        "elapsed_s": time.time() - started,
        "project_saved_with_results": saved,
        "solver_result": _solver_result_dict(solver_result),
        "evaluate_templates": evaluate_report,
    }


def _evaluate_result_templates(project: object, timeout_s: float) -> dict:
    try:
        project.execute_vba("EvaluateResultTemplates", header="Evaluate result templates", timeout=timeout_s)
        return {"status": "ok", "command": "EvaluateResultTemplates"}
    except Exception as exc:
        return {"status": "failed", "command": "EvaluateResultTemplates", "error": repr(exc)}


def _solver_result_dict(result: object | None) -> dict | None:
    if result is None:
        return None
    return {
        "success": bool(getattr(result, "success", False)),
        "error_type": getattr(result, "error_type", None),
        "error_message": getattr(result, "error_message", None),
        "elapsed_s": getattr(result, "elapsed_s", 0.0),
        "mesh_cells": getattr(result, "mesh_cells", None),
    }


def _inspect_postprocessing_artifacts(project_dir: Path) -> dict:
    model_3d = project_dir / "Model" / "3D"
    missing = []
    present = []
    for metric_id, spec in _TEMPLATE_FILES.items():
        path = model_3d / str(spec["file"])
        if path.exists():
            present.append({"metric_id": metric_id, "path": str(path), "bytes": path.stat().st_size})
        else:
            missing.append(str(path))

    pc_path = project_dir / "Model" / "PC_integration.json"
    rpp_path = model_3d / "Model.rpp"
    output_variables = []
    if pc_path.exists():
        try:
            payload = json.loads(pc_path.read_text(encoding="utf-8"))
            output_variables = [
                str(item.get("name"))
                for item in payload.get("outputVariables", [])
                if isinstance(item, dict) and item.get("name")
            ]
        except Exception:
            output_variables = ["<unreadable PC_integration.json>"]
    return {
        "status": "ok" if not missing else "failed",
        "present_template_files": present,
        "missing_template_files": missing,
        "model_rpp_path": str(rpp_path),
        "model_rpp_exists": rpp_path.exists(),
        "pc_integration_path": str(pc_path),
        "pc_output_variables_after_reopen_save": output_variables,
        "pc_note": "CST may rewrite PC_integration.json on save; template-file presence is the primary validation in this diagnostic.",
    }


def _list_result_tree_items(project_path: Path) -> dict:
    try:
        reader = ResultReader(str(project_path), allow_interactive=True)
        items = reader.list_tree_items("0D/1D")
        matched = {
            metric_id: spec["tree_path"]
            for metric_id, spec in _TEMPLATE_FILES.items()
            if spec["tree_path"] in items
        }
        scalar_readback = {}
        for metric_id, tree_path in matched.items():
            try:
                scalar = reader.get_scalar(tree_path)
                scalar_readback[metric_id] = {
                    "status": "ok",
                    "tree_path": tree_path,
                    "value": scalar.value,
                    "unit": _TEMPLATE_FILES[metric_id]["unit"],
                }
            except Exception as exc:
                scalar_readback[metric_id] = {
                    "status": "failed",
                    "tree_path": tree_path,
                    "error": repr(exc),
                }
        return {
            "status": "ok",
            "matched_metric_tree_paths": matched,
            "scalar_readback": scalar_readback,
            "item_count": len(items),
            "sample_items": items[:50],
        }
    except Exception as exc:
        return {
            "status": "not_available",
            "error": repr(exc),
            "note": "Result tree items may be unavailable before a solver/postprocessing run.",
        }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
