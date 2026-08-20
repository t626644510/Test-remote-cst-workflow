"""Authorized, isolated R5 Stage A nominal live-CST capture.

This entry point deliberately does not use ``CSTConnection`` as a context
manager: the shared close path may force-kill CST after a graceful-close
timeout, while Stage A explicitly forbids process termination.  The runner
uses only repository-verified CST wrappers and leaves a non-exiting process
running for manual recovery instead of killing it.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import threading
import time
from typing import Any, Mapping, Sequence

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.solver import SolverRunner

from rf_cem.compiler import load_compile_record
from rf_cem.history_templates import CstHistoryTemplates, load_cst_history_templates
from rf_cem.live_500mhz_diagnostic import _execute_action
from rf_cem.live_500mhz_postprocessing_diagnostic import (
    _TEMPLATE_FILES,
    _attach_postprocessing_templates,
    _evaluate_result_templates,
    _inspect_postprocessing_artifacts,
    _list_result_tree_items,
    _project_dir_for,
)
from rf_cem.physics import R5Bundle, R5CaseArtifacts, load_r5_bundle
from rf_cem.semantic.contracts import file_sha256
from rf_cem.translator import _build_actions, emit_step_import_block


STAGE_A_SCHEMA_VERSION = "r5_live_cst_stage_a.v0"
AUTHORIZATION_SCHEMA_VERSION = "r5_live_cst_authorization.v0"
RF500_INSTANCE_ID = "rf500.2c27faee.b1r3"
NOMINAL_HISTORY_INDICES = (1, 49, 51)
AUTHORIZATION_SCOPE = (
    "One new isolated RF500 nominal eigenmode project bound to the exact R2 STEP; "
    "save replayable results and capture native result-tree, mesh, and field-export evidence."
)
PROHIBITED_ACTIONS = (
    "overwrite_preexisting_output",
    "optimization_campaign",
    "process_kill",
    "lock_or_result_deletion",
    "campaign_cleanup",
    "recovery_launch",
    "unverified_cst_api_or_vba",
    "license_file_import_or_modification",
)


@dataclass(frozen=True)
class StageAConfig:
    """Resolved inputs for one explicitly authorized Stage A execution."""

    repo_root: Path
    r2_bundle: Path
    readiness_bundle: Path
    template_project_dir: Path
    library_path: Path
    output_dir: Path
    authorization_id: str
    action_timeout_s: float = 120.0
    solver_timeout_s: float = 7200.0
    wait_for_ui: bool = False


@dataclass(frozen=True)
class StageAPreflight:
    """Validated Stage A inputs plus the selected nominal setup."""

    report: Mapping[str, Any]
    readiness: R5Bundle
    nominal: R5CaseArtifacts
    compiled_step: Path
    compile_record_path: Path
    r2_manifest_path: Path
    selected_templates: CstHistoryTemplates
    image_version_path: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.live_r5_stage_a",
        description=(
            "Preflight or execute the explicitly authorized, isolated RF500 nominal "
            "R5 Stage A live-CST capture."
        ),
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--r2-bundle", type=Path, required=True)
    parser.add_argument("--readiness-bundle", type=Path, required=True)
    parser.add_argument(
        "--template-project-dir",
        type=Path,
        default=Path(r"D:\ModelData\bare"),
    )
    parser.add_argument(
        "--library-path",
        type=Path,
        default=Path(
            r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--action-timeout-s", type=float, default=120.0)
    parser.add_argument("--solver-timeout-s", type=float, default=7200.0)
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Launch one new CST instance after preflight. Omit for read-only preflight.",
    )
    parser.add_argument(
        "--wait-for-ui",
        action="store_true",
        help="Keep the solved project open until one line is received on stdin.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root.resolve()
    config = StageAConfig(
        repo_root=root,
        r2_bundle=_resolve(root, args.r2_bundle),
        readiness_bundle=_resolve(root, args.readiness_bundle),
        template_project_dir=args.template_project_dir.resolve(),
        library_path=args.library_path.resolve(),
        output_dir=_resolve(root, args.output_dir),
        authorization_id=str(args.authorization_id).strip(),
        action_timeout_s=float(args.action_timeout_s),
        solver_timeout_s=float(args.solver_timeout_s),
        wait_for_ui=bool(args.wait_for_ui),
    )
    preflight = preflight_stage_a(config)
    if not args.execute_live:
        print(json.dumps(preflight.report, ensure_ascii=False, sort_keys=True))
        return 0
    return run_stage_a(config, preflight)


def preflight_stage_a(config: StageAConfig) -> StageAPreflight:
    """Fail closed before creating output or importing ``cst.interface``."""

    if not config.authorization_id:
        raise ValueError("Stage A requires a non-empty authorization id")
    if config.action_timeout_s <= 0 or config.solver_timeout_s <= 0:
        raise ValueError("Stage A timeouts must be positive")
    if config.output_dir.exists():
        raise FileExistsError(f"Stage A output already exists: {config.output_dir}")
    if not config.r2_bundle.is_dir():
        raise FileNotFoundError(f"R2 bundle is missing: {config.r2_bundle}")
    if not config.template_project_dir.is_dir():
        raise FileNotFoundError(
            f"CST template project directory is missing: {config.template_project_dir}"
        )
    if not config.library_path.is_dir():
        raise FileNotFoundError(f"CST library path is missing: {config.library_path}")
    if not (config.library_path / "cst" / "interface").is_dir():
        raise FileNotFoundError("CST interface library is missing below --library-path")

    readiness = load_r5_bundle(config.readiness_bundle, repo_root=config.repo_root)
    nominal = _one_nominal_case(readiness)
    if nominal.physics_case.geometry.instance_id != RF500_INSTANCE_ID:
        raise ValueError("R5 nominal case is not bound to the canonical RF500 instance")

    compile_record_path = (
        config.r2_bundle / "records" / f"{RF500_INSTANCE_ID}.compile_record.v0.json"
    )
    record = load_compile_record(compile_record_path)
    if record.status != "pass" or record.live_cst_status != "not_run":
        raise ValueError("R2 RF500 compile record is not the accepted no-CST baseline")
    case_geometry = nominal.physics_case.geometry
    if (
        case_geometry.compile_record_ref.object_id != record.compile_id
        or case_geometry.compile_record_ref.content_sha256 != record.content_sha256
    ):
        raise ValueError("R5 nominal case does not bind the supplied R2 compile record")

    step_artifacts = [
        item
        for item in record.output_artifacts
        if item.role == "compiled_rf_vacuum_step"
    ]
    if len(step_artifacts) != 1:
        raise ValueError("R2 RF500 compile record requires one compiled STEP artifact")
    step_artifact = step_artifacts[0]
    compiled_step = _inside(config.r2_bundle, Path(step_artifact.path), "compiled STEP")
    if not compiled_step.is_file():
        raise FileNotFoundError(f"R2 compiled STEP is missing: {compiled_step}")
    if (
        compiled_step.stat().st_size != step_artifact.size_bytes
        or file_sha256(compiled_step) != step_artifact.raw_sha256
    ):
        raise ValueError("R2 compiled STEP size/hash mismatch")

    r2_manifest_path = config.r2_bundle / "source_binding_manifest.v0.json"
    r2_manifest = _read_json(r2_manifest_path)
    if (
        r2_manifest.get("bundle_id") != config.r2_bundle.name
        or r2_manifest.get("status") != "pass"
    ):
        raise ValueError("R2 bundle manifest identity/status mismatch")
    manifest_step = _one_manifest_artifact(r2_manifest, step_artifact.path)
    if (
        manifest_step.get("raw_sha256") != step_artifact.raw_sha256
        or manifest_step.get("size_bytes") != step_artifact.size_bytes
    ):
        raise ValueError("R2 manifest and compile-record STEP bindings differ")

    history_path = config.template_project_dir / "Model" / "3D" / "ModelHistory.json"
    templates = load_cst_history_templates(history_path)
    selected = select_nominal_templates(templates)
    controls = nominal_controls(selected)
    required_template_paths = _required_template_paths(config.template_project_dir)
    for path in required_template_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Required CST template artifact is missing: {path}")

    image_version_path = _find_image_version(config.library_path)
    report = {
        "schema_version": STAGE_A_SCHEMA_VERSION,
        "status": "ready_no_cst_preflight",
        "authorization": {
            "authorization_id": config.authorization_id,
            "scope": AUTHORIZATION_SCOPE,
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "output_policy": {
            "path": str(config.output_dir),
            "must_not_exist": True,
            "exists_at_preflight": False,
            "connect_mode": "new",
            "campaign_execution": False,
            "force_close_or_process_kill": False,
        },
        "readiness_bundle": _file_identity(
            config.readiness_bundle / "source_binding_manifest.v0.json"
        ),
        "planned_nominal_case": nominal.physics_case.to_mapping(),
        "r2_manifest": _file_identity(r2_manifest_path),
        "compile_record": _file_identity(compile_record_path),
        "compiled_step": {
            **_file_identity(compiled_step),
            "artifact_role": step_artifact.role,
        },
        "template_sources": [
            _file_identity(path) for path in required_template_paths
        ],
        "history_source_indices": selected.source_history_indices,
        "nominal_controls": controls,
        "cst_installation": {
            "library_path": str(config.library_path),
            "image_version": _image_version_identity(image_version_path),
        },
        "timeouts_s": {
            "history_action": config.action_timeout_s,
            "solver": config.solver_timeout_s,
        },
        "live_cst_started": False,
    }
    return StageAPreflight(
        report=report,
        readiness=readiness,
        nominal=nominal,
        compiled_step=compiled_step,
        compile_record_path=compile_record_path,
        r2_manifest_path=r2_manifest_path,
        selected_templates=selected,
        image_version_path=image_version_path,
    )


def select_nominal_templates(templates: CstHistoryTemplates) -> CstHistoryTemplates:
    """Select only the recorded final order-3/minimum-3 nominal history blocks."""

    indices = templates.source_history_indices.get("solver", [])
    if len(indices) != len(templates.solver_blocks):
        raise ValueError("CST solver history block/index inventory is inconsistent")
    by_index = dict(zip(indices, templates.solver_blocks))
    if len(by_index) != len(indices):
        raise ValueError("CST solver history indices are duplicated")
    missing = [index for index in NOMINAL_HISTORY_INDICES if index not in by_index]
    if missing:
        raise ValueError(f"Recorded nominal solver history blocks are missing: {missing}")
    selected_blocks = tuple(by_index[index] for index in NOMINAL_HISTORY_INDICES)
    selected_indices = dict(templates.source_history_indices)
    selected_indices["solver"] = list(NOMINAL_HISTORY_INDICES)
    return replace(
        templates,
        solver_blocks=selected_blocks,
        source_history_indices=selected_indices,
    )


def nominal_controls(templates: CstHistoryTemplates) -> dict[str, Any]:
    """Extract the exact nominal controls from the selected verified VBA blocks."""

    joined = "\n".join(templates.solver_blocks)
    controls = {
        "solver_type": _quoted_call(joined, "ChangeSolverType"),
        "mesh_type": _quoted_method(joined, "SetMeshType"),
        "number_of_modes": _quoted_method(joined, "SetNumberOfModes"),
        "order_tet": _quoted_method(joined, "SetOrderTet"),
        "accuracy": _quoted_method(joined, "SetAccuracy"),
        "maximum_df": _quoted_method(joined, "AKSMaximumDF"),
        "minimum_passes": _quoted_method(joined, "AKSMinimumPasses"),
        "maximum_passes": _quoted_method(joined, "AKSMaximumPasses"),
        "mesh_increment": _quoted_method(joined, "AKSMeshIncrement"),
        "frequency_range": {"minimum": "498", "maximum": "530", "unit": "MHz"},
        "length_unit": "mm",
        "history_indices": list(NOMINAL_HISTORY_INDICES),
    }
    expected = {
        "solver_type": "HF Eigenmode",
        "mesh_type": "Tetrahedral Mesh",
        "number_of_modes": "1",
        "order_tet": "3",
        "accuracy": "1e-12",
        "maximum_df": "0.001",
        "minimum_passes": "3",
        "maximum_passes": "6",
        "mesh_increment": "5",
    }
    for key, value in expected.items():
        if controls[key] != value:
            raise ValueError(
                f"Recorded nominal CST control {key} changed: {controls[key]!r} != {value!r}"
            )
    return controls


def run_stage_a(config: StageAConfig, preflight: StageAPreflight) -> int:
    """Create, solve, expose for UI capture, and gracefully close one project."""

    prepared = _prepare_output(config, preflight)
    report_path = prepared["report_path"]
    report: dict[str, Any] = {
        **dict(preflight.report),
        "status": "starting_live_cst",
        "phase": "connecting_cst",
        "live_cst_started": True,
        "started_at": _utc_now(),
        "completed_at": None,
        "project_path": str(prepared["project_path"]),
        "action_results": [],
        "solver_result": None,
        "template_attachment": None,
        "template_evaluation": None,
        "result_tree": None,
        "field_artifacts": [],
        "messages": None,
        "graceful_close": None,
    }
    _write_json(report_path, report)

    connection: CSTConnection | None = None
    project: Any = None
    live_error: BaseException | None = None
    try:
        connection = CSTConnection(library_path=str(config.library_path), mode="new")
        connection.connect()
        report["cst_pid"] = connection.pid
        connection.set_quiet_mode(True)
        report["phase"] = "building_nominal_project"
        project = connection.new_mws_project()
        report["initial_project_filename"] = project.filename

        for action in prepared["actions"]:
            result = _execute_action(project, action, config.action_timeout_s)
            report["action_results"].append(result)
            _write_json(report_path, report)
            if not result["success"]:
                raise RuntimeError(f"CST setup action failed: {result['action_id']}")
        report["active_solver"] = project.get_active_solver_name()
        if not project.save(
            path=str(prepared["project_path"]),
            include_results=False,
            allow_overwrite=False,
        ):
            raise RuntimeError("Initial no-overwrite CST project save failed")
        project.close(save=False)
        project = None

        report["phase"] = "attaching_result_templates"
        _write_json(report_path, report)
        attachment = _attach_postprocessing_templates(
            prepared["copied_template_project"],
            _project_dir_for(prepared["project_path"]),
        )
        report["template_attachment"] = attachment
        if attachment.get("status") != "ok":
            raise RuntimeError("Verified 0D template attachment failed")

        project = connection.open_project(str(prepared["project_path"]))
        report["phase"] = "solving_nominal_eigenmode"
        _write_json(report_path, report)
        solver_result = SolverRunner(
            timeout_s=config.solver_timeout_s,
            settle_s=2.0,
        ).run(project)
        report["solver_result"] = {
            "success": solver_result.success,
            "error_type": solver_result.error_type,
            "error_message": solver_result.error_message,
            "elapsed_s": solver_result.elapsed_s,
            "mesh_cells": solver_result.mesh_cells,
        }
        if not solver_result.success:
            raise RuntimeError(
                f"Nominal eigenmode solver failed: {solver_result.error_type}: "
                f"{solver_result.error_message}"
            )

        report["phase"] = "evaluating_result_templates"
        evaluation = _evaluate_result_templates(project, config.action_timeout_s)
        report["template_evaluation"] = evaluation
        if evaluation.get("status") != "ok":
            raise RuntimeError("EvaluateResultTemplates failed")
        if not project.save(include_results=True, allow_overwrite=False):
            raise RuntimeError("Current-project result save failed without overwrite")

        report["messages"] = _safe_messages(project)
        report["postprocessing_artifacts"] = _inspect_postprocessing_artifacts(
            _project_dir_for(prepared["project_path"])
        )
        report["result_tree"] = _list_result_tree_items(prepared["project_path"])
        report["phase"] = "ui_field_capture" if config.wait_for_ui else "finalizing"
        report["status"] = "ui_capture_ready" if config.wait_for_ui else "completed"
        _write_json(report_path, report)

        if config.wait_for_ui:
            print(
                "R5_STAGE_A_UI_READY="
                + json.dumps(
                    {
                        "project_path": str(prepared["project_path"]),
                        "field_output_dir": str(prepared["field_output_dir"]),
                        "report_path": str(report_path),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            sys.stdin.readline()
            if not project.save(include_results=True, allow_overwrite=False):
                raise RuntimeError("Final current-project save failed without overwrite")

        report["field_artifacts"] = _field_inventory(
            prepared["field_output_dir"], config.repo_root
        )
        report["messages"] = _safe_messages(project)
        report["phase"] = "completed"
        report["status"] = "completed"
    except BaseException as exc:
        live_error = exc
        report["failed_phase"] = report.get("phase")
        report["status"] = "failed"
        report["error"] = repr(exc)
        if project is not None:
            report["messages"] = _safe_messages(project)
    finally:
        report["completed_at"] = _utc_now()
        if project is not None:
            try:
                project.close(save=False)
            except Exception as exc:
                report["project_close_error"] = repr(exc)
        if connection is not None:
            report["graceful_close"] = _graceful_close_without_kill(connection)
        _write_json(report_path, report)

    print(json.dumps({"status": report["status"], "report": str(report_path)}))
    return 1 if live_error is not None else 0


def _prepare_output(config: StageAConfig, preflight: StageAPreflight) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=False)
    input_root = config.output_dir / "inputs"
    template_3d = input_root / "template_project" / "Model" / "3D"
    generated = config.output_dir / "generated"
    live = config.output_dir / "live"
    fields = config.output_dir / "fields"
    for path in (input_root, template_3d, generated, live, fields):
        path.mkdir(parents=True, exist_ok=True)

    copied_step = input_root / preflight.compiled_step.name
    shutil.copy2(preflight.compiled_step, copied_step)
    if file_sha256(copied_step) != file_sha256(preflight.compiled_step):
        raise ValueError("Copied R2 STEP hash mismatch")
    shutil.copy2(preflight.compile_record_path, input_root / preflight.compile_record_path.name)
    shutil.copy2(preflight.r2_manifest_path, input_root / preflight.r2_manifest_path.name)
    readiness_manifest = preflight.readiness.path / "source_binding_manifest.v0.json"
    shutil.copy2(readiness_manifest, input_root / "r5_readiness_manifest.v0.json")
    nominal_source = (
        preflight.readiness.path
        / "cases"
        / preflight.nominal.physics_case.physics_case_id
        / "physics_case.v0.json"
    )
    shutil.copy2(nominal_source, input_root / "planned_nominal.physics_case.v0.json")
    shutil.copy2(preflight.image_version_path, input_root / "CST_Image_Version")
    for source in _required_template_paths(config.template_project_dir):
        shutil.copy2(source, template_3d / source.name)

    copied_history = template_3d / "ModelHistory.json"
    selected = select_nominal_templates(load_cst_history_templates(copied_history))
    import_block = emit_step_import_block(copied_step, filename_mode="absolute")
    actions = _build_actions(import_block, selected)
    _write_json(generated / "cst_actions.json", actions)
    _write_json(generated / "stage_a_preflight.v0.json", dict(preflight.report))
    _write_json(
        generated / "authorization.v0.json",
        {
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "authorization_id": config.authorization_id,
            "scope": AUTHORIZATION_SCOPE,
            "prohibited_actions": list(PROHIBITED_ACTIONS),
            "recorded_at": _utc_now(),
        },
    )
    return {
        "actions": actions,
        "copied_template_project": input_root / "template_project",
        "field_output_dir": fields,
        "project_path": live / "rf500_r5_stage_a_nominal.cst",
        "report_path": generated / "stage_a_live_report.v0.json",
    }


def _graceful_close_without_kill(
    connection: CSTConnection,
    *,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Attempt only the native close call; never invoke repository cleanup code."""

    de = connection.design_environment
    pid = connection.pid
    if de is None:
        return {
            "status": "not_connected",
            "pid": pid,
            "force_kill_attempted": False,
            "global_sweep_attempted": False,
        }
    result: dict[str, Any] = {}
    finished = threading.Event()

    def close_native() -> None:
        try:
            de.close()
            result["native_close_returned"] = True
        except BaseException as exc:
            result["native_close_returned"] = False
            result["error"] = repr(exc)
        finally:
            finished.set()

    started = time.perf_counter()
    thread = threading.Thread(target=close_native, daemon=True)
    thread.start()
    finished.wait(timeout_s)
    # Detach so no later code can enter CSTConnection.close() implicitly.
    connection._de = None  # type: ignore[attr-defined]
    return {
        "status": "closed" if finished.is_set() and result.get("native_close_returned") else "left_running",
        "pid": pid,
        "native_close_returned": result.get("native_close_returned", False),
        "timed_out": not finished.is_set(),
        "elapsed_s": time.perf_counter() - started,
        "force_kill_attempted": False,
        "global_sweep_attempted": False,
        **({"error": result["error"]} if "error" in result else {}),
    }


def _one_nominal_case(bundle: R5Bundle) -> R5CaseArtifacts:
    matches = [item for item in bundle.cases if item.physics_case.mesh.level == "nominal"]
    if len(matches) != 1:
        raise ValueError("R5 readiness bundle requires exactly one nominal case")
    nominal = matches[0]
    if (
        nominal.physics_case.case_status != "planned_not_run"
        or nominal.physics_case.authorization_status != "not_requested"
    ):
        raise ValueError("R5 readiness nominal case must remain the immutable no-CST plan")
    return nominal


def _required_template_paths(template_project_dir: Path) -> tuple[Path, ...]:
    source_3d = template_project_dir / "Model" / "3D"
    names = [str(spec["file"]) for spec in _TEMPLATE_FILES.values()]
    names.extend(("Model.rpp", "ModelHistory.json"))
    return tuple(source_3d / name for name in names)


def _find_image_version(library_path: Path) -> Path:
    for parent in (library_path, *library_path.parents):
        candidate = parent / "Image_Version"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("CST Image_Version was not found above --library-path")


def _image_version_identity(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 5:
        raise ValueError(f"CST Image_Version is incomplete: {path}")
    return {
        **_file_identity(path),
        "version": lines[3].strip(),
        "build": lines[2].strip(),
        "release_kind": lines[4].strip(),
        "product_build": f"{lines[3].strip()}.{lines[2].strip()}",
    }


def _one_manifest_artifact(manifest: Mapping[str, Any], relative_path: str) -> Mapping[str, Any]:
    matches = [
        item
        for item in manifest.get("artifacts", [])
        if isinstance(item, Mapping) and item.get("path") == relative_path
    ]
    if len(matches) != 1:
        raise ValueError(f"R2 manifest does not bind exactly one artifact: {relative_path}")
    return matches[0]


def _field_inventory(path: Path, repo_root: Path) -> list[dict[str, Any]]:
    result = []
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        resolved = item.resolve()
        try:
            relative = resolved.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            relative = str(resolved)
        result.append(
            {
                "path": relative,
                "raw_sha256": file_sha256(resolved),
                "size_bytes": resolved.stat().st_size,
                "media_type": "text/plain" if resolved.suffix.lower() in {".txt", ".csv"} else "application/octet-stream",
            }
        )
    return result


def _quoted_call(text: str, name: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s+\"([^\"]+)\"", text)
    if match is None:
        raise ValueError(f"Verified CST call is missing: {name}")
    return match.group(1)


def _quoted_method(text: str, name: str) -> str:
    match = re.search(rf"(?m)^\s*\.{re.escape(name)}\s+\"([^\"]+)\"", text)
    if match is None:
        raise ValueError(f"Verified CST method is missing: {name}")
    return match.group(1)


def _inside(root: Path, relative: Path, label: str) -> Path:
    base = root.resolve()
    path = (base / relative).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its bundle: {relative}") from exc
    return path


def _resolve(root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object: {path}")
    return value


def _file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path.resolve()),
        "raw_sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _safe_messages(project: Any) -> str:
    try:
        return str(project.get_messages())
    except Exception as exc:
        return f"<get_messages failed: {exc}>"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "AUTHORIZATION_SCOPE",
    "NOMINAL_HISTORY_INDICES",
    "PROHIBITED_ACTIONS",
    "STAGE_A_SCHEMA_VERSION",
    "StageAConfig",
    "StageAPreflight",
    "build_parser",
    "main",
    "nominal_controls",
    "preflight_stage_a",
    "run_stage_a",
    "select_nominal_templates",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
