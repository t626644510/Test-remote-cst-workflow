"""Explicit worker, coordinator and file-relay entrypoints; no implicit CST run."""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import sys
import zipfile
from uuid import uuid4

from ..storage import atomic_json, digest, fingerprint
from .protocol import execution_identity, Node, owner_lock, publish_json, read_json, safe_id


def recover_postprocess(root: Path, task_id: str) -> dict:
    """Requeue only saved postprocessing; requires a stopped, unowned worker."""
    from ..session_recovery import ensure_sessions_inactive
    from ..runtime import verify_solved
    job = root / "jobs" / safe_id(task_id)
    with owner_lock(root / "worker.lock"):
        outcome = read_json(job / "outcome.json")
        journal = read_json(job / "evaluation/evaluation.json")
        if outcome["result"]["status"] != "postprocess_failed" or journal["phase"] != "postprocess_pending":
            raise ValueError("Only saved postprocessing failure can be requeued")
        ensure_sessions_inactive(job / "evaluation")
        verify_solved(Path(journal["project"]), Path(journal["current"]))
        (job / "outcome.json").rename(job / ("outcome.failed-" + uuid4().hex + ".json"))
        if (root / "STOP").exists():
            (root / "STOP").unlink()
    return dict(requeued=task_id, phase="postprocess_pending", new_solve_required=False)


def archive_native(root: Path, task_id: str) -> dict:
    """Package a completed owned native project, never the user's original project."""
    from ..runtime import verify_solved
    from ..session_recovery import ensure_sessions_inactive
    job = root / "jobs" / safe_id(task_id)
    outcome = read_json(job / "outcome.json")
    project = Path(outcome["result"]["project"]).resolve()
    if job.resolve() not in project.parents:
        raise ValueError("Native project outside its owned task")
    ensure_sessions_inactive(job / "evaluation")
    journal = read_json(job / "evaluation/evaluation.json")
    verify_solved(project, Path(journal["current"]))
    target = job / "native.zip"
    if not target.exists():
        with zipfile.ZipFile(target.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as archive:
            for path in [project, *project.with_suffix("").rglob("*")]:
                if path.is_file() and path.suffix.lower() not in {".lock", ".lok"}:
                    archive.write(path, path.relative_to(project.parent).as_posix())
        os.replace(target.with_suffix(".tmp"), target)
    return dict(task_id=task_id, project=project.name, sha256=digest(target))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="WF5 asynchronous distinct-candidate campaign")
    sub = parser.add_subparsers(dest="command", required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--config", type=Path, required=True)
    worker.add_argument("--root", type=Path, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--root", type=Path, required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("--root", type=Path, required=True)
    publish.add_argument("--relative", required=True)
    publish.add_argument("--payload", required=True)
    archive = sub.add_parser("archive-native")
    archive.add_argument("--root", type=Path, required=True)
    archive.add_argument("--task-id", required=True)
    recover = sub.add_parser("recover-postprocess")
    recover.add_argument("--root", type=Path, required=True)
    recover.add_argument("--task-id", required=True)
    coordinator = sub.add_parser("coordinator")
    coordinator.add_argument("--config", type=Path, required=True)
    coordinator.add_argument("--cluster", type=Path, required=True)
    coordinator.add_argument("--resume", action="store_true")
    coordinator.add_argument("--import-serial", type=Path)
    coordinator.add_argument("--original-identity", type=Path)
    coordinator.add_argument("--prior-solves", type=int, default=0)
    coordinator.add_argument("--import-only", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "worker":
        from .worker import run_worker
        return run_worker(args.config, args.root)
    if args.command == "inspect":
        from .worker import worker_snapshot
        print(json.dumps(worker_snapshot(args.root), allow_nan=False))
        return 0
    if args.command == "publish":
        target = (args.root / args.relative).resolve()
        if args.root.resolve() not in target.parents:
            raise ValueError("Message outside worker root")
        publish_json(target, json.loads(base64.b64decode(args.payload)))
        print('{"published":true}')
        return 0
    if args.command == "archive-native":
        print(json.dumps(archive_native(args.root, args.task_id)))
        return 0
    if args.command == "recover-postprocess":
        print(json.dumps(recover_postprocess(args.root, args.task_id)))
        return 0
    from ..config import load_config
    from ..storage import CampaignStore
    from .coordinator import Coordinator
    from .migration import import_serial
    config = load_config(args.config, live=True)
    nodes = [Node.from_dict(row) for row in read_json(args.cluster)["nodes"]]
    identity = execution_identity(config)
    contract = fingerprint(identity)
    store = CampaignStore(config.paths.output_dir, contract, config.search.max_solves, resume=args.resume)
    try:
        cluster_identity = [asdict(node) for node in nodes]
        if args.resume:
            if read_json(store.root / "cluster.resolved.json") != cluster_identity:
                raise ValueError("Worker endpoints changed; refusing duplicate task delivery")
        else:
            atomic_json(store.root / "cluster.resolved.json", cluster_identity)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
            handlers=[logging.StreamHandler(), logging.FileHandler(store.root / "campaign.log", encoding="utf-8")])
        if not args.resume:
            atomic_json(store.root / "execution_identity.json", identity)
            atomic_json(store.root / "config.resolved.json", config.as_dict())
        if args.import_serial:
            if args.resume or not args.original_identity:
                raise ValueError("Import requires a fresh campaign and verified original identity")
            import_serial(config, store, args.import_serial, args.original_identity, args.prior_solves)
        if args.import_only:
            print(json.dumps(dict(imported=len(store.state["records"]), solve_count=store.state["solve_count"])))
            return 0
        if not store.state["records"] or store.state["records"][0]["status"] != "valid":
            raise ValueError("Async campaign needs a verified valid baseline import")
        result = Coordinator(config, store, nodes).run()
        print(json.dumps(dict(status=result["status"], solve_count=result["solve_count"])))
        return 0
    finally:
        store.close()
