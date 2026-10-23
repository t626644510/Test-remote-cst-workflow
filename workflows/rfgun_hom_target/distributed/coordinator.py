"""Single-writer asynchronous ask/tell, immutable solve permits and raw-field replay."""
from __future__ import annotations

from dataclasses import asdict
import json
import logging
import math
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

from ..postprocess import analyze_bundle
from ..runtime import metadata, postprocess_config, read_baseline
from ..search import Campaign, CandidatePlanner, objective
from ..physics import match_mode_signatures
from ..storage import atomic_json, BudgetExhausted, digest
from .protocol import Node, read_json, safe_id, unpack_evidence
from .transport import Transport

LOG = logging.getLogger(__name__)


def equivalent_metrics(a: Any, b: Any) -> bool:
    """Allow floating roundoff across CPUs, never percent-level scientific drift."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent_metrics(a[k], b[k]) for k in a)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(equivalent_metrics(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-12)
    return type(a) is type(b) and a == b


class AsyncPlanner(CandidatePlanner):
    """Reuse the existing GP/EI; exclude in-flight points and prefer spatial diversity."""
    def ask_async(self, baseline: dict[str, float], pending: list[dict[str, Any]]) -> tuple[dict[str, float], str]:
        original = self.state["records"]
        # Non-valid placeholders participate in key deduplication, never GP fitting.
        self.state["records"] = original + [dict(parameters=p["parameters"], status="pending") for p in pending]
        choices = []
        try:
            for _ in range(5 if pending else 1):
                parameters, source = self.ask(baseline)
                unit = self.space.normalize(np.array([parameters[n] for n in self.space.names]))
                separation = min((np.linalg.norm(unit - self.space.normalize(
                    np.array([p["parameters"][n] for n in self.space.names]))) for p in pending), default=math.inf)
                choices.append((float(separation), parameters, source))
                if separation >= .05:  # Euclidean distance in six normalized coordinates.
                    break
            _, parameters, source = max(choices, key=lambda item: item[0])
            return parameters, source
        finally:
            self.state["records"] = original


def issue_permit(store: Any, request: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Exactly-once journal reservation; retries return the same immutable reply."""
    safe_id(request["request_id"])
    if request.get("task_id") != job["id"] or request.get("contract") != store.state["contract"]:
        raise ValueError("Budget request identity mismatch")
    permits = store.state.setdefault("permits", {})
    key = job["id"] + ":" + request["request_id"]
    if key in permits:
        return permits[key]
    response = {k: request[k] for k in ("task_id", "request_id", "contract")}
    if store.state.get("target_reached"):
        response["denied"] = "Target already reached"
    elif store.state["solve_count"] >= store.max_solves:
        response["denied"] = "Global solve budget exhausted"
    else:
        # Reservation and reply share ONE atomic JSON commit. A lost reply is replayable.
        number = store.state["solve_count"] + 1
        store.state["solve_count"] = number
        store.state["reservations"].append(dict(number=number, attempt=request["attempt"],
            task_id=job["id"], node=job["node"], request_id=request["request_id"]))
        response["number"] = number
    permits[key] = response
    store.save()
    return response


def validate_return(config: Any, task: dict[str, Any], outcome: dict[str, Any], evidence: Path) -> dict[str, Any]:
    """Never trust a low worker score without replay of the same field convention.

    Frequencies are Hz in raw fields; impedance is peak/beta=1/circuit ohm/m.
    """
    if any(outcome.get(k) != task[k] for k in ("id", "contract", "parameters")):
        raise ValueError("Worker result identity mismatch")
    result = outcome["result"]
    if result.get("modes"):
        bundles = sorted(evidence.glob("attempt_*/postprocess_*/field_config.json"))
        if not bundles:
            raise ValueError("Mode metrics returned without raw evidence")
        expected = asdict(postprocess_config(config, metadata(config.paths.template_path)))
        raw_settings = read_json(bundles[-1])
        expected = json.loads(json.dumps(expected))
        for key, value in expected.items():
            if key == "conductivity_layers" and not value:
                continue  # Automatically read template materials are preserved in the bundle.
            if raw_settings.get(key) != value:
                raise ValueError("Worker field convention differs: " + key)
        if raw_settings.get("band_mhz") != [config.physics.frequency_min_mhz, config.physics.frequency_max_mhz]:
            raise ValueError("Worker frequency window differs")
        replay = analyze_bundle(bundles[-1].parent)
        recomputed = json.loads(json.dumps(replay.to_dict()))
        if not equivalent_metrics(recomputed["modes"], result["modes"]["modes"]) or recomputed["native_modes"] != result["modes"]["native_modes"]:
            raise ValueError("Worker metrics do not reproduce from raw fields")
        if result["status"] == "valid":
            if not replay.quality_ok or not math.isclose(replay.worst_impedance_ohm_per_m, result["worst"], rel_tol=1e-8):
                raise ValueError("Worker validity/score differs from local replay")
            result = {**result, "modes": recomputed, "worst": float(replay.worst_impedance_ohm_per_m)}
    elif result["status"] == "valid":
        raise ValueError("Valid worker result requires numerical field evidence")
    return result


class Coordinator:
    """At most one distinct candidate per worker; completed results enter a single GP."""
    def __init__(self, config: Any, store: Any, nodes: list[Node], *, planner: Any = None):
        if not nodes or len({node.name for node in nodes}) != len(nodes):
            raise ValueError("Need uniquely named workers")
        self.config, self.store = config, store
        self.nodes = {n.name: Transport(n) for n in nodes}
        self.planner = planner if planner is not None else AsyncPlanner(config, store.state)
        self.baseline = read_baseline(config.paths.template_path, config)
        store.state.setdefault("jobs", {})
        store.state.setdefault("permits", {})
        store.state.setdefault("next_job", 0)
        store.state.setdefault("node_status", {})
        if any(r["status"] == "valid" and r["worst"] <= config.physics.threshold_ohm_per_m for r in store.state["records"]):
            store.state["target_reached"] = True

    def active(self) -> list[dict[str, Any]]:
        return [j for j in self.store.state["jobs"].values() if j["state"] != "finished"]

    def accept(self, job: dict[str, Any], outcome: dict[str, Any]) -> None:
        transport = self.nodes[job["node"]]
        destination = self.store.root / "evaluations" / job["id"]
        artifact = destination / "evidence.zip"
        if not artifact.exists() or digest(artifact) != outcome["evidence_sha256"]:
            transport.fetch("jobs/" + job["id"] + "/evidence.zip", artifact)
        evidence = destination / "raw"
        unpack_evidence(artifact, evidence, outcome["evidence_sha256"])
        result = validate_return(self.config, job["task"], outcome, evidence)
        if result["status"] in {"worker_failed", "cleanup_failed", "postprocess_failed"}:
            job.update(state="needs_attention", error=result.get("error", result["status"]),
                       failed_outcome_sha256=outcome["evidence_sha256"])
            self.store.save()
            return
        record = dict(id=job["id"], parameters=job["parameters"], source=job["source"],
            attempt_dir=str(evidence), node=job["node"], **result)
        record["native_project"] = record.get("project")
        record["native_node"] = job["node"]
        record["objective"] = objective(record["worst"], self.config.physics.threshold_ohm_per_m) if record["status"] == "valid" else None
        valid = [r for r in self.store.state["records"] if r["status"] == "valid"]
        previous_best = min((r["objective"] for r in valid), default=math.inf)
        if record.get("modes") and self.store.state["records"]:
            record["mode_matches"] = [m.to_dict() for m in match_mode_signatures(
                Campaign._signatures(self.store.state["records"][0]), Campaign._signatures(record),
                frequency_gate_hz=(self.config.physics.frequency_max_mhz-self.config.physics.frequency_min_mhz)*1e6)]
        self.planner.observe(record, previous_best)
        job.update(state="finished", completed_at=outcome["completed_at"])
        self.store.finish(record)
        LOG.info("%s returned from %s: %s; worst=%s ohm/m", job["id"], job["node"], record["status"], record.get("worst"))
        if record["status"] == "valid" and record["worst"] <= self.config.physics.threshold_ohm_per_m:
            self.store.state["target_reached"] = True
            self.store.save()

    def tick(self) -> None:
        state = self.store.state
        ready = []
        # Ingest every available result before issuing new solve permissions.
        snapshots = {}
        for name, transport in self.nodes.items():
            try:
                snapshot = transport.inspect()
                heartbeat = snapshot.get("heartbeat") or {}
                if heartbeat.get("contract") != state["contract"]:
                    raise ValueError("Worker code/template/settings fingerprint differs")
                snapshots[name] = snapshot
                state["node_status"][name] = {**heartbeat, "last_contact": time.time()}
                for job in list(self.active()):
                    remote = snapshot["jobs"].get(job["id"], {})
                    if job["node"] == name and job["state"] == "needs_attention" and job["id"] in snapshot["jobs"]:
                        outcome = remote.get("outcome")
                        if not outcome or outcome.get("evidence_sha256") != job.get("failed_outcome_sha256"):
                            job["state"] = "recovering_postprocess"
                    if job["node"] == name and remote.get("outcome") and job["state"] != "needs_attention":
                        self.accept(job, remote["outcome"])
                if heartbeat.get("status") == "ready" and time.time()-heartbeat.get("timestamp", 0) < 30.:
                    ready.append(name)
            except (OSError, ValueError, ConnectionError, TimeoutError, subprocess.TimeoutExpired) as exc:
                state["node_status"][name] = dict(status="unavailable", error=str(exc)[-500:], timestamp=time.time())
                LOG.warning("%s unavailable; tasks and budgets retained: %s", name, str(exc)[-200:])
        for name, snapshot in snapshots.items():
            for job in self.active():
                if job["node"] != name or job["state"] == "needs_attention":
                    continue
                try:
                    if job["id"] not in snapshot["jobs"]:
                        self.nodes[name].publish(f"jobs/{job['id']}/task.json", job["task"])
                    for request in snapshot["jobs"].get(job["id"], {}).get("requests", []):
                        if request["request_id"] in job.get("delivered_grants", []):
                            continue
                        response = issue_permit(self.store, request, job)
                        self.nodes[name].publish(f"jobs/{job['id']}/grants/{request['request_id']}.json", response)
                        job.setdefault("delivered_grants", []).append(request["request_id"])
                    job["phase"] = snapshot["jobs"].get(job["id"], {}).get("phase", "queued")
                    job["solver_tail"] = snapshot["jobs"].get(job["id"], {}).get("solver_tail", "")
                except (OSError, ValueError, ConnectionError, TimeoutError, subprocess.TimeoutExpired) as exc:
                    LOG.warning("Delivery pending for %s: %s", job["id"], str(exc)[-200:])
        for name in ready:
            if state.get("target_reached") or (self.store.root / "PAUSE").exists():
                break
            if any(j["node"] == name for j in self.active()):
                continue
            if hasattr(self.planner, "can_dispatch") and not self.planner.can_dispatch():
                continue
            unreserved = sum(not any(v.get("task_id") == j["id"] and "number" in v for v in state["permits"].values()) for j in self.active())
            if state["solve_count"] + unreserved >= self.store.max_solves:
                break
            if len(state["records"]) + len(self.active()) >= self.config.search.max_candidate_attempts:
                break
            parameters, source = self.planner.ask_async(self.baseline, self.active())
            number = state["next_job"]
            identity = f"async_{number:04d}"
            state["next_job"] += 1
            task = dict(id=identity, parameters=parameters, contract=state["contract"])
            state["jobs"][identity] = dict(id=identity, parameters=parameters, source=source,
                node=name, state="dispatched", task=task, dispatched_at=time.time())
            self.store.save()  # Dispatch identity survives a failed network send.
            try:
                self.nodes[name].publish(f"jobs/{identity}/task.json", task)
            except (OSError, ConnectionError, TimeoutError, subprocess.TimeoutExpired) as exc:
                LOG.warning("Task %s persisted; delivery will retry: %s", identity, exc)
            LOG.info("Dispatched DISTINCT %s to %s: %s", identity, name, parameters)
        state["status"] = "target_reached_draining" if state.get("target_reached") else "running_async"
        state["updated_at"] = time.time()
        self.store.save()
        Campaign(self.config, self.store, None).report()

    def run(self, poll_s: float = 3.) -> dict[str, Any]:
        self.store.sync_mirrors()
        while True:
            self.tick()
            state = self.store.state
            if not self.active():
                if state.get("target_reached"):
                    state["status"] = "target_reached"
                    break
                if state["solve_count"] >= self.store.max_solves:
                    state["status"] = "budget_exhausted"
                    break
                if hasattr(self.planner, "complete") and self.planner.complete():
                    state["status"] = "search_plan_complete"
                    break
                if (self.store.root / "PAUSE").exists():
                    state["status"] = "paused"
                    break
                if len(state["records"]) >= self.config.search.max_candidate_attempts:
                    state["status"] = "candidate_limit"
                    break
            elif all(j["state"] == "needs_attention" for j in self.active()):
                state["status"] = "needs_attention"
                break
            time.sleep(poll_s)
        for transport in self.nodes.values():
            try:
                transport.stop_when_idle()
            except (OSError, ConnectionError, TimeoutError, subprocess.TimeoutExpired):
                LOG.warning("Worker stop delivery pending")
        self.store.save()
        report = Campaign(self.config, self.store, None).report()
        best = report.get("best")
        if best and best.get("native_node") and self.nodes[best["native_node"]].node.ssh_host:
            transport = self.nodes[best["native_node"]]
            native = transport.archive_native(best["id"])
            archive = self.store.root / "best_native.zip"
            transport.fetch(f"jobs/{best['id']}/native.zip", archive)
            unpack_evidence(archive, self.store.root / "best_native", native["sha256"])
            atomic_json(self.store.root / "best_native.json", native)
            best["project"] = str(self.store.root / "best_native" / native["project"])
            self.store.save()
            report = Campaign(self.config, self.store, None).report()
        return report
