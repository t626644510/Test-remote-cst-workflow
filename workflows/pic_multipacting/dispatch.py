"""Local work-conserving queue: an idle CPU group receives the next case."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from .model import tasks
from .run import plot_summary, summarize, utc, write_json


def validate_groups(groups: list[list[int]]) -> None:
    """Require nonempty, disjoint logical CPU groups."""
    if not groups or any(not g for g in groups):
        raise ValueError("At least one nonempty CPU group is required")
    flat = [n for g in groups for n in g]
    if len(flat) != len(set(flat)) or any(n < 0 for n in flat):
        raise ValueError("CPU groups must be nonnegative and nonoverlapping")


def pending_keys(root: Path, selected: set[str], limit: int | None) -> list[str]:
    """Deduplicate across all workers, including failed records; no automatic retries."""
    records = list((root / "cases").glob("*/result.json"))
    records += list((root / "workers").glob("*/cases/*/result.json"))
    finished = {p.parent.name for p in records}
    keys = [t.key for t in tasks() if (not selected or t.key in selected) and t.key not in finished]
    return keys if limit is None else keys[:limit]


def dispatch(config: dict[str, Any], selected: set[str], limit: int | None) -> None:
    """Dispatch one case per idle group; STOP drains active cases before exiting.

    A worker process/CST session is renewed each case, reusing its prepared
    template. This small startup cost avoids a persistent IPC/job-server layer.
    """
    root = Path(config["output"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "RUNNING.json"
    with lock.open("x", encoding="utf-8") as f:
        json.dump(dict(pid=os.getpid(), started=utc(), mode="parallel_queue"), f)
    slots, streams = [], []
    started = time.time()
    state: dict[str, Any] = dict(pid=os.getpid(), started=utc(), status="starting", workers=[])
    codes: list[int] = []
    try:
        groups = config["cpu_groups"]
        validate_groups(groups)
        saved = root / "dispatch_config.json"
        if saved.exists():
            previous = json.loads(saved.read_text(encoding="utf-8"))
            if any(previous.get(k) != config.get(k) for k in
                   ("template", "field_project", "receivers", "cpu_groups")):
                raise ValueError("Parallel resume configuration changed")
        if list((root / "workers").glob("*/RUNNING.json")):
            raise RuntimeError("A worker lock remains; inspect that worker before resuming")
        queue = pending_keys(root, selected, limit)
        write_json(saved, config)
        entry = Path(__file__).resolve().parents[2] / "run_workflow_8.py"
        for i, group in enumerate(groups, 1):
            directory = root / "workers" / f"worker{i}"
            directory.mkdir(parents=True, exist_ok=True)
            cfg = root / f"worker{i}.local.json"
            worker_config = dict(config, output=str(directory), cpu_affinity=group, plot_on_exit=False)
            worker_config.pop("cpu_groups", None)
            write_json(cfg, worker_config)
            stdout = (root / f"worker{i}.stdout.log").open("a", encoding="utf-8")
            stderr = (root / f"worker{i}.stderr.log").open("a", encoding="utf-8")
            streams.extend([stdout, stderr])
            info = dict(worker=i, output=str(directory), affinity=group, assigned=0, task=None)
            state["workers"].append(info)
            slots.append(dict(info=info, config=cfg, stdout=stdout, stderr=stderr, process=None))
        failed = False
        while queue or any(s["process"] is not None for s in slots):
            changed = False
            stopping = failed or (root / "STOP").exists()
            for slot in slots:
                info, proc = slot["info"], slot["process"]
                if proc is not None and proc.poll() is not None:
                    code = proc.returncode
                    record = Path(info["output"]) / "cases" / info["task"] / "result.json"
                    if code == 0 and not record.exists():
                        code = 1
                        state["error"] = f"Worker exited without case record: {info['task']}"
                    codes.append(code)
                    failed |= code != 0
                    stopping |= failed
                    slot["process"] = None
                    info.update(task=None, returncode=code)
                    summarize(root)
                    changed = True
                if (not stopping and not (root / "STOP").exists() and queue
                        and slot["process"] is None):
                    key = queue.pop(0)
                    proc = subprocess.Popen(
                        [sys.executable, str(entry), "--config", str(slot["config"]),
                         "--resume", "--cases", key], cwd=str(entry.parent),
                        stdout=slot["stdout"], stderr=slot["stderr"],
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    slot["process"] = proc
                    info.update(pid=proc.pid, task=key, assigned=info["assigned"] + 1)
                    changed = True
            if stopping or (root / "STOP").exists():
                for slot in slots:
                    (Path(slot["info"]["output"]) / "STOP").touch()
                if not any(s["process"] is not None for s in slots):
                    break
            if changed:
                state.update(status="draining" if stopping else "running",
                             remaining=len(queue), updated=utc())
                write_json(root / "state.json", state)
            if queue or any(s["process"] is not None for s in slots):
                time.sleep(3)
        state.update(status="stopped_error" if failed else
                     ("paused" if (root / "STOP").exists() else "complete"),
                     returncodes=codes, remaining=len(queue), wall_s=time.time()-started)
    except BaseException as exc:
        for slot in slots:
            if slot["process"] is not None:
                (Path(slot["info"]["output"]) / "STOP").touch()
                slot["process"].wait()
        state.update(status="paused" if isinstance(exc, KeyboardInterrupt) else "stopped_error",
                     error=str(exc))
        raise
    finally:
        for stream in streams:
            stream.close()
        state["updated"] = utc()
        write_json(root / "state.json", state)
        summarize(root)
        if (root / "workers").exists():
            plot_summary(root)
        lock.unlink()
