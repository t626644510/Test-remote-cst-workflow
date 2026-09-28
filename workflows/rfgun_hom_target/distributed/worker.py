"""One persistent, node-local worker reusing the verified single-point evaluator."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from ..config import load_config
from ..storage import atomic_json, BudgetExhausted, fingerprint
from .protocol import execution_identity, owner_lock, pack_evidence, read_json, safe_id

LOG = logging.getLogger(__name__)


class PermitClient:
    """A fresh request per solver start; only persisted coordinator grants permit CST."""
    def __init__(self, job: Path, task: dict[str, Any], poll_s: float = 1.):
        self.job, self.task, self.poll_s = job, task, poll_s

    def reserve(self, attempt: str) -> int:
        request_id = uuid4().hex
        request = dict(request_id=request_id, task_id=self.task["id"],
                       contract=self.task["contract"], attempt=attempt)
        atomic_json(self.job / "requests" / f"{request_id}.json", request)
        grant = self.job / "grants" / f"{request_id}.json"
        while not grant.exists():
            time.sleep(self.poll_s)
        response = read_json(grant)
        if any(response.get(k) != request[k] for k in ("request_id", "task_id", "contract")):
            raise ValueError("Budget grant identity mismatch")
        if response.get("denied"):
            raise BudgetExhausted(response["denied"])
        number = response.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("Invalid budget number")
        # An uncertain start is never silently refunded; restarting creates a new request.
        atomic_json(self.job / "claimed" / f"{request_id}.json", response)
        return number


def worker_snapshot(root: Path) -> dict[str, Any]:
    """Small read-only relay snapshot; no CST imports or process manipulation."""
    snapshot = dict(heartbeat=read_json(root / "heartbeat.json") if (root / "heartbeat.json").exists() else None,
                    jobs={})
    for job in sorted((root / "jobs").glob("*")):
        if not job.is_dir() or not (job / "task.json").exists():
            continue
        evaluation = job / "evaluation/evaluation.json"
        progress = read_json(evaluation) if evaluation.exists() else {}
        phase = progress.get("phase", "queued")
        current = Path(progress["current"]) if progress.get("current") else None
        solver_tail = ""
        if current and (current / "solve_started.json").exists() and not (current / "solved.json").exists():
            phase = "solving"
        if current:
            logs = list(current.glob("project/*/Result/Model.log"))
            if logs:
                with logs[0].open("rb") as stream:
                    stream.seek(max(0, logs[0].stat().st_size - 3000))
                    solver_tail = "\n".join(stream.read().decode(errors="replace").splitlines()[-9:])
        snapshot["jobs"][job.name] = dict(
            requests=[read_json(p) for p in sorted((job / "requests").glob("*.json"))],
            outcome=read_json(job / "outcome.json") if (job / "outcome.json").exists() else None,
            phase=phase, solver_tail=solver_tail)
    return snapshot


def execute_task(job: Path, config: Any, contract: str, evaluator_factory: Callable | None = None) -> None:
    """Run a distinct candidate, publish evidence before its immutable completion."""
    from ..runtime import CSTEvaluator
    task = read_json(job / "task.json")
    safe_id(task["id"])
    if task["id"] != job.name or task["contract"] != contract:
        raise ValueError("Task execution contract differs from this worker")
    if (job / "outcome.json").exists():
        return
    from ..geometry import GeometryConstraints
    from dataclasses import asdict
    if set(task["parameters"]) != {p.name for p in config.parameters} or any(
            not p.lower <= task["parameters"][p.name] <= p.upper for p in config.parameters):
        raise ValueError("Task parameters outside configured ranges")
    if not GeometryConstraints(**asdict(config.geometry)).feasible(task["parameters"]):
        raise ValueError("Task violates geometry preflight")
    evaluate = (evaluator_factory or CSTEvaluator)(config, config.paths.template_path)
    try:
        result = evaluate(task["parameters"], job / "evaluation", PermitClient(job, task).reserve)
    except BudgetExhausted as exc:
        result = dict(status="budget_denied", worst=None, error=str(exc))
    except Exception as exc:
        # Do not retry arbitrary exceptions or kill any possibly surviving CST session.
        LOG.exception("Worker task failed: %s", task["id"])
        result = dict(status="worker_failed", worst=None, error=f"{type(exc).__name__}: {exc}")
    sha = pack_evidence(job / "evaluation", job / "evidence.zip")
    atomic_json(job / "outcome.json", dict(id=task["id"], contract=contract,
        parameters=task["parameters"], result=result, evidence_sha256=sha,
        evaluation_dir=str((job / "evaluation").resolve()), completed_at=time.time()))
    LOG.info("%s completed: %s", task["id"], result["status"])


def write_heartbeats(root: Path, info: dict[str, Any], stopped: threading.Event,
                     interval_s: float = 2.) -> None:
    """Keep liveness publication alive after I/O failures; stale data stays stale.

    A persistent filesystem failure still prevents coordinator dispatch. Log
    the first failure and eventual recovery without flooding every poll.
    """
    failed = False
    while not stopped.is_set():
        try:
            atomic_json(root / "heartbeat.json", {**info, "timestamp": time.time()})
        except OSError:
            if not failed:
                LOG.exception("Heartbeat publication failed; retrying without restarting CST")
            failed = True
        else:
            if failed:
                LOG.info("Heartbeat publication recovered")
            failed = False
        stopped.wait(interval_s)


def run_worker(config_path: Path, root: Path) -> int:
    """Stay alive independently of SSH; exactly one evaluator per workstation."""
    config = load_config(config_path, live=True)
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(root / "worker.log", encoding="utf-8"), logging.StreamHandler()])
    with owner_lock(root / "worker.lock"):
        contract = fingerprint(execution_identity(config))
        info: dict[str, Any] = dict(pid=os.getpid(), contract=contract, active=None, status="ready")
        stopped = threading.Event()
        thread = threading.Thread(target=write_heartbeats, args=(root, info, stopped), daemon=True)
        thread.start()
        try:
            while not (root / "STOP").exists():
                tasks = sorted((root / "jobs").glob("*/task.json"))
                for path in tasks:
                    if (root / "STOP").exists():
                        break
                    if (path.parent / "outcome.json").exists():
                        continue
                    info.update(active=path.parent.name, status="evaluating")
                    execute_task(path.parent, config, contract)
                    result = read_json(path.parent / "outcome.json")["result"]
                    info.update(active=None, status="ready")
                    if result["status"] in {"cleanup_failed", "worker_failed", "postprocess_failed"}:
                        info["status"] = "needs_attention"
                        # Preserve pending postprocessing and ambiguous owned sessions.
                        while not (root / "STOP").exists():
                            time.sleep(2.)
                        break
                time.sleep(1.)
        finally:
            stopped.set()
            thread.join(timeout=5.)
            atomic_json(root / "heartbeat.json", {**info, "status": "stopped", "timestamp": time.time()})
    return 0
