"""Minimal serial CST PIC scan with durable 1D exports and offline SEY analysis."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .model import Task, active_source_macro, analyze, logical_grid, tasks


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: Any) -> None:
    """Replace a small metadata file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def export_curves(reader: Any, directory: Path) -> dict[str, dict[str, Any]]:
    """Export original MP-related 1D samples, labels and tree paths, losslessly."""
    prefixes = (
        "1D Results\\Collision Information\\", "1D Results\\Emission Information\\",
        "1D Results\\Solver Statistics [PIC]\\", "1D Results\\Energy\\",
        "1D Results\\Power\\Wave-Particle",
    )
    curves, arrays, metadata = {}, {}, {}
    for path in reader.list_tree_items():
        if not path.startswith(prefixes):
            continue
        item = reader.get_result_item(path, 0)
        x, y = np.asarray(item.get_xdata()), np.asarray(item.get_ydata())
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError(f"Nonfinite result: {path}")
        key = f"c{len(curves):03d}"
        arrays[key + "_x"], arrays[key + "_y"] = x, y
        metadata[path] = dict(key=key, xlabel=item.xlabel, ylabel=item.ylabel, run_id=0)
        curves[path] = dict(x=x, y=y, xlabel=item.xlabel, ylabel=item.ylabel)
    if not curves:
        raise ValueError("No MP 1D curves were produced")
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(directory / "raw_1d.npz", **arrays)
    write_json(directory / "curves.json", metadata)
    # Ensure data can be read before removing the transient CST project.
    loaded = load_curves(directory)
    for path in curves:
        if not (np.array_equal(curves[path]["x"], loaded[path]["x"]) and
                np.array_equal(curves[path]["y"], loaded[path]["y"])):
            raise ValueError(f"Export round-trip failed: {path}")
    return curves


def load_curves(directory: Path) -> dict[str, dict[str, Any]]:
    meta = json.loads((directory / "curves.json").read_text(encoding="utf-8"))
    with np.load(directory / "raw_1d.npz", allow_pickle=False) as data:
        return {path: dict(x=data[m["key"] + "_x"].copy(), y=data[m["key"] + "_y"].copy(),
                           xlabel=m["xlabel"], ylabel=m["ylabel"]) for path, m in meta.items()}


def verify_run(curves: dict[str, dict[str, Any]], task: Task) -> float:
    """Check exclusive primary emission and actual time coverage, not SEE source names."""
    primary = "1D Results\\Emission Information\\Current\\[Sources]\\"
    emitted = [p[len(primary):] for p, c in curves.items()
               if p.startswith(primary) and np.any(c["y"] != 0)]
    if emitted != [task.source]:
        raise ValueError(f"Wrong active primary sources: {emitted}, expected {task.source}")
    p = curves.get("1D Results\\Solver Statistics [PIC]\\Particle vs. Time")
    if p is None or len(p["x"]) < 2 or not np.all(np.diff(p["x"]) > 0):
        raise ValueError("Missing or invalid particle-vs-time record")
    return float(p["x"][-1])


def snapshot_config(config: dict[str, Any], root: Path) -> dict[str, Any]:
    """Freeze template history, emission faces and scan grid once per scan."""
    template = Path(config["template"])
    history_path = template.with_suffix("") / "Model/3D/ModelHistory.json"
    history = json.loads(history_path.read_text(encoding="utf-8"))["history"]
    sources = {}
    position_names = set()
    for block in history:
        if block.get("hidden"):
            continue
        code = "\n".join(block.get("code", []))
        deleted = re.search(r'ParticleSource.Delete "([^"]+)"', code)
        if deleted:
            sources.pop(deleted[1], None)
        if "With ParticleSource" in code:
            name = re.search(r'\.Name "([^"]+)"', code)[1]
            sources[name] = dict(faces=re.findall(r'\.AddFace "([^"]+)", "([^"]+)"', code), code=code)
        if "With PSMonitor" in code:
            position_names.add(re.search(r'\.Name "([^"]+)"', code)[1])
        deleted = re.search(r'(?:PICPositionMonitor|PSMonitor).Delete "([^"]+)"', code)
        if deleted:
            position_names.discard(deleted[1])
    if set(sources) != {f"particle{i}" for i in range(1, 22)}:
        raise ValueError("Template must contain exactly particle1..particle21")
    frozen = dict(config, template_sha256=digest(template),
                  field_sha256=digest(Path(config["field_project"])),
                  sources=sources, position_monitors=sorted(position_names))
    write_json(root / "config.json", frozen)
    write_json(root / "template_history.json", history)
    write_json(root / "grid.json", logical_grid())
    return frozen


def prepare_template(conn: Any, config: dict[str, Any], root: Path) -> Path:
    """Open only a copy. Remove old results and fix external-field absolute linkage."""
    target = root / "template/prepared.cst"
    if target.exists() and (root / "template/ready.json").exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    copy = root / "template/input.cst"
    shutil.copy2(config["template"], copy)
    project = conn.open_project(str(copy))
    try:
        project.project.schematic.execute_vba_code("Sub Main\nDeleteResults\nEnd Sub", timeout=120)
        field = str(Path(config["field_project"]).resolve()).replace('"', '""')
        macro = "\n".join([
            "With PredefinedField", '.ResetExternalSettings', '.FieldType "External"',
            '.UseLocalCopyOnly "False"', '.UpdateLocalCopies "False"', '.ExternalFieldMur "1.0"',
            f'.SetExternalField "True", "{field}", "0.618*factor1", "phase", "0", "False"',
            '.SetExternalFieldDescription "0", "<mesh:tet><sourcename:Eigenmode Tet 1>"',
            '.SetExternalFieldSpaceShift "0", "0.0", "0.0", "0.0"',
            '.SetExternalFieldTimeSignal "0", "[Constant]"',
            '.SetExternalFieldTimeShift "0", "0.0"', '.Create', 'End With',
            'PICSolver.SimulationTime "20"',
        ])
        for name in config["position_monitors"]:
            macro += f'\nPICPositionMonitor.Delete "{name}"'
        # The original has Material and all solid monitors; add boundary-loss diagnostics.
        macro += '\n'.join([
            "", "With ParticleMonitorOnSolid", ".Reset", '.Name "[Background]:Boundary"',
            '.EnableCollisionInfo "True"', '.EnableCurrent "True"', '.EnablePower "True"',
            '.EnableEnergyHistogram "True"', '.EnergyBinSize "5"',
            '.EnergyMin "0"', '.EnergyMax "3000"', '.Create', "End With",
        ])
        project.execute_vba(macro, "WF8 output and field configuration", timeout=120)
        if not project.save(str(target), include_results=False, allow_overwrite=True):
            raise RuntimeError("Cannot save prepared template")
        write_json(root / "template/ready.json", dict(prepared_sha256=digest(target), created=utc()))
    finally:
        project.project.close()
    return target


def remove_case_work(root: Path, working: Path) -> None:
    """Delete only the closed WF8 scratch directory; never the template or input project."""
    expected = (root / "working").resolve()
    if working.resolve() != expected or expected.parent != root.resolve():
        raise ValueError("Refusing cleanup outside this scan's working directory")
    shutil.rmtree(expected)


def summarize(root: Path) -> None:
    """Rebuild compact CSV from durable per-case records and SEY results."""
    rows = []
    paths = list((root / "cases").glob("*/result.json"))
    paths += list((root / "workers").glob("*/cases/*/result.json"))
    for path in sorted(paths):
        d = json.loads(path.read_text(encoding="utf-8"))
        row = {k: d.get(k) for k in ["key", "source", "factor1", "phase", "voltage_kV",
                                    "status", "end_ns", "prepare_s", "solve_s", "export_s", "total_s", "error"]}
        row["data_directory"] = str(path.parent)
        analysis_path = path.parent / "sey.json"
        if analysis_path.exists():
            a = json.loads(analysis_path.read_text(encoding="utf-8"))
            row["analysis_issues"] = json.dumps(a["issues"], ensure_ascii=False)
            for v in a["rows"]:
                if v["start_ns"] == 5 and v["requested_end_ns"] == 20:
                    row["SEY_5_20_" + v["surface"]] = v["sey"]
        rows.append(row)
    if rows:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with (root / "summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            w.writerows(rows)


def plot_summary(root: Path) -> None:
    """Plot the combined 5–20 ns SEY grid; blanks remain missing or undefined."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(7, 3, figsize=(12, 20), constrained_layout=True)
    for source_id, ax in enumerate(axes.flat, 1):
        values = np.full((6, 8), np.nan)
        paths = list((root / "cases").glob(f"s{source_id:02d}_*/sey.json"))
        paths += list((root / "workers").glob(f"*/cases/s{source_id:02d}_*/sey.json"))
        for path in paths:
            task = json.loads((path.parent / "task.json").read_text(encoding="utf-8"))
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data["rows"]:
                if (row["surface"] == "combined_paired_receivers" and row["start_ns"] == 5
                        and row["requested_end_ns"] == 20 and row["window_complete"]):
                    if row["sey"] is not None:
                        i, j = round(task["factor1"] * 5), task["phase"] // 45
                        values[i, j] = row["sey"]
                        if i == 0:
                            values[0, :] = row["sey"]
        im = ax.imshow(values, origin="lower", aspect="auto", vmin=0, vmax=2, cmap="coolwarm")
        ax.set(title=f"particle{source_id}", xlabel="RF phase (deg)", ylabel="factor1")
        ax.set_xticks(range(8), range(0, 360, 45), fontsize=7)
        ax.set_yticks(range(6), ["0*", ".2", ".4", ".6", ".8", "1"])
    fig.colorbar(im, ax=axes, label="Paired-receiver SEY, 5–20 ns (not a safety verdict)", shrink=.6)
    fig.suptitle("WF8 PIC screen — *zero-field phase cells reference one run per source")
    fig.savefig(root / "sey_grid.png", dpi=140)
    plt.close(fig)


def run(config: dict[str, Any], root: Path, selected: set[str], limit: int | None) -> None:
    """Serial task loop, explicit failures, no retry tree or remote machinery."""
    from cst_optimization.core.connection import CSTConnection
    from cst_optimization.core.results import ResultReader
    from cst_optimization.core.solver import SolverRunner

    root.mkdir(parents=True, exist_ok=True)
    lock = root / "RUNNING.json"
    # Exclusive creation intentionally refuses duplicate dispatchers.
    with lock.open("x", encoding="utf-8") as f:
        json.dump(dict(pid=os.getpid(), started=utc()), f)
    conn = None
    sampler = None
    session_identity = None
    state: dict[str, Any] = dict(pid=os.getpid(), status="preparing", updated=utc())
    try:
        if (root / "config.json").exists():
            saved = json.loads((root / "config.json").read_text(encoding="utf-8"))
            for k in ("template", "field_project", "receivers"):
                if config[k] != saved[k]:
                    raise ValueError(f"Resume configuration changed: {k}")
            config = saved
        else:
            config = snapshot_config(config, root)
        if config.get("cpu_affinity"):
            import psutil
            psutil.Process().cpu_affinity(config["cpu_affinity"])
            state["cpu_affinity"] = config["cpu_affinity"]
        write_json(root / "state.json", state)
        pending = [t for t in tasks() if (not selected or t.key in selected)
                   and not (root / "cases" / t.key / "result.json").exists()]
        if limit is not None:
            pending = pending[:limit]
        if not pending or (root / "STOP").exists():
            state["status"] = "paused" if (root / "STOP").exists() else "selection_complete"
            return
        conn = CSTConnection(config["cst_library"], mode="new")
        conn.connect()
        import psutil
        if not conn.pid:
            raise RuntimeError("Private CST session PID unavailable")
        session_identity = (conn.pid, psutil.Process(conn.pid).create_time())
        conn.set_quiet_mode(True)
        state["cst_pid"] = conn.pid
        state["cst_created"] = session_identity[1]
        if conn.pid and (config.get("sample_hardware", False) or config.get("cpu_affinity")):
            from .hardware import Sampler
            output = root / "hardware.jsonl" if config.get("sample_hardware", False) else None
            sampler = Sampler(conn.pid, output, config.get("cpu_affinity"))
            sampler.start()
        prepared = prepare_template(conn, config, root)
        solver = SolverRunner(timeout_s=float(config.get("timeout_s", 7200)), settle_s=0.5)
        for task in pending:
            if (root / "STOP").exists():
                state["status"] = "paused"
                break
            working = root / "working"
            if working.exists():
                raise RuntimeError("Unfinished working directory exists; preserve it for inspection")
            working.mkdir()
            case = root / "cases" / task.key
            case.mkdir(parents=True, exist_ok=True)
            project_file = working / "case.cst"
            shutil.copy2(prepared, project_file)
            start = time.perf_counter()
            record = dict(task.record(), started=utc(), status="running")
            write_json(case / "task.json", record)
            state.update(status="preparing_case", task=task.record(), updated=utc())
            write_json(root / "state.json", state)
            project = conn.open_project(str(project_file))
            result = None
            export_ok = False
            try:
                project.execute_vba(
                    f'StoreParameter "factor1", "{task.factor1:.1f}"\n'
                    f'StoreParameter "phase", "{task.phase}"',
                    "WF8 RF parameters", timeout=120)
                project.rebuild()
                if config.get("cpu_affinity"):
                    # Official Solver.MaximumNumberOfThreads: cap transient solver
                    # threads to this worker's logical CPUs, avoiding oversubscription.
                    project.execute_vba(
                        f'Solver.MaximumNumberOfThreads "{len(config["cpu_affinity"])}"',
                        "WF8 assigned CPU threads", timeout=120)
                project.execute_vba(active_source_macro(task.source), "WF8 single source", timeout=120)
                record["prepare_s"] = time.perf_counter() - start
                state.update(status="solving", updated=utc())
                write_json(root / "state.json", state)
                print(f"{utc()} START {task.key}", flush=True)
                result = solver.run(project)
                record["solve_s"] = result.elapsed_s
                record["solver_success"] = result.success
                if not result.success:
                    record.update(status="failed", error=result.error_message)
                    if result.error_type in ("timeout", "com"):
                        raise RuntimeError(f"Stop scan after {result.error_type}: {result.error_message}")
                else:
                    state.update(status="exporting", updated=utc())
                    write_json(root / "state.json", state)
                stamp = time.perf_counter()
                if not project.save(include_results=True):
                    raise RuntimeError("Cannot save current run for 1D export")
                reader = ResultReader(str(project_file), allow_interactive=True)
                try:
                    curves = export_curves(reader, case)
                except ValueError as exc:
                    if not result.success and str(exc) == "No MP 1D curves were produced":
                        curves = {}
                    else:
                        raise
                export_ok = True
                if result.success:
                    end = verify_run(curves, task)
                    record["end_ns"] = end
                    record["status"] = "complete" if end >= 19.98 else "incomplete"
                write_json(case / "sey.json", analyze(curves, config["receivers"]))
                record["export_s"] = time.perf_counter() - stamp
                record["curve_count"] = len(curves)
            except Exception as exc:
                record.update(status="failed", error=str(exc))
                # Unknown/export/timeout failures stop; never overwrite sole raw evidence.
                raise
            finally:
                try:
                    write_json(case / "messages.json", dict(messages=str(project.get_messages())))
                except Exception:
                    pass
                # Small text logs preserve phase timings; large CST result files are discarded.
                for name in ("Model.log", "MCalc.log", "PP-MCalc.log"):
                    source_log = project_file.with_suffix("") / "Result" / name
                    if source_log.exists():
                        (case / "logs").mkdir(exist_ok=True)
                        shutil.copy2(source_log, case / "logs" / name)
                record.update(finished=utc(), total_s=time.perf_counter() - start)
                write_json(case / "result.json", record)
                project.project.close()
            summarize(root)
            if export_ok:
                remove_case_work(root, working)
            print(f"{utc()} {record['status'].upper()} {task.key} {record['total_s']:.1f}s", flush=True)
        else:
            state["status"] = "selection_complete" if selected or limit else "complete"
    except Exception as exc:
        state.update(status="stopped_error", error=str(exc))
        raise
    finally:
        # Never use connection.close(): its legacy fallback can sweep globally.
        cleanup_error = None
        if sampler is not None:
            sampler.close()
        if conn is not None and session_identity is not None:
            try:
                from .hardware import close_owned_session
                state["close_result"] = close_owned_session(conn, *session_identity)
            except Exception as exc:
                state.update(status="stopped_error", close_error=str(exc))
                cleanup_error = exc
        summarize(root)
        if config.get("plot_on_exit", True) and (root / "cases").exists():
            plot_summary(root)
        state["updated"] = utc()
        write_json(root / "state.json", state)
        lock.unlink()
        if cleanup_error is not None:
            raise RuntimeError("WF8 private CST session could not be closed") from cleanup_error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--cases", nargs="*", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true", help="Completed/failed records are always skipped")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    root = Path(config["output"]).resolve()
    unknown = set(args.cases) - {t.key for t in tasks()}
    if unknown:
        parser.error(f"Unknown task keys: {unknown}")
    if args.dry_run:
        print(json.dumps(dict(actual_runs=len(tasks()), logical_combinations=len(logical_grid()),
                              output=str(root), selected=args.cases, first=tasks()[0].record()), indent=2))
    elif args.analyze_only:
        cases = list((root / "cases").glob("*")) + list((root / "workers").glob("*/cases/*"))
        for case in cases:
            if (case / "raw_1d.npz").exists():
                write_json(case / "sey.json", analyze(load_curves(case), config["receivers"]))
        summarize(root)
    else:
        if config.get("cpu_groups"):
            from .dispatch import dispatch
            dispatch(config, set(args.cases), args.limit)
        else:
            run(config, root, set(args.cases), args.limit)
