"""Audited import of a stopped serial campaign, preserving all expensive calls."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..postprocess import analyze_bundle
from ..runtime import verify_solved
from ..search import objective
from ..seeding import archive_lock
from ..session_recovery import ensure_sessions_inactive
from ..storage import atomic_json, digest, fingerprint, project_manifest
from .protocol import read_json


def import_serial(config: Any, store: Any, source: Path, original_identity: Path, prior_solves: int) -> None:
    """Explicit new schema, same numerical contract, no new CST solver invocation."""
    if store.state["records"] or store.state["solve_count"] or store.state.get("import_provenance"):
        raise ValueError("Serial import requires a fresh destination")
    if prior_solves < 0:
        raise ValueError("Negative prior budget")
    with archive_lock(source):
        old = read_json(source / "state.json")
        old_config = read_json(source / "config.resolved.json")
        original = read_json(original_identity)
        if fingerprint(original) != old["contract"] or original["config"] != old_config:
            raise ValueError("Original serial code/configuration identity not verified")
        current = config.as_dict()
        for key in ("parameters", "geometry", "solver", "physics", "results"):
            if current[key] != old_config[key]:
                raise ValueError("Cannot migrate changed numerical settings: " + key)
        if current["search"]["max_solves"] != old_config["search"]["max_solves"] + prior_solves:
            raise ValueError("Migration must preserve remaining global budget")
        if {k:v for k,v in current["search"].items() if k!='max_solves'} != {k:v for k,v in old_config["search"].items() if k!='max_solves'}:
            raise ValueError("Search settings changed during import")
        if project_manifest(config.paths.template_path) != original["template"]:
            raise ValueError("Migrated template differs")
        records = copy.deepcopy(old["records"])
        for evaluation in (source / "evaluations").glob("evaluation_*"):
            ensure_sessions_inactive(evaluation)
        pending = old.get("pending")
        if pending:
            journal = read_json(Path(pending["attempt_dir"]) / "evaluation.json")
            if journal.get("phase") == "complete":
                verify_solved(Path(journal["project"]), Path(journal["current"]))
                result = journal["result"]
            elif journal.get("phase") == "failed":
                result = dict(status=journal["category"], error=journal["error"], worst=None)
            elif journal.get("phase") == "invalid":
                verify_solved(Path(journal["project"]), Path(journal["current"]))
                result = dict(status="quality_failed", worst=None, error=journal.get("error", ""),
                    project=journal["project"], modes=read_json(Path(journal["current"]) / "latest_analysis.json"))
            else:
                raise ValueError("Serial task still in flight; no new evaluation may start")
            record = {**pending, **result}
            record["objective"] = objective(record["worst"], config.physics.threshold_ohm_per_m) if record["status"] == "valid" else None
            records.append(record)
        for record in records:
            if record["status"] == "valid":
                bundles = sorted(Path(record["attempt_dir"]).glob("attempt_*/postprocess_*/field_config.json"))
                if not bundles:
                    raise ValueError("Imported valid record missing raw fields")
                replay = analyze_bundle(bundles[-1].parent)
                data = json.loads(json.dumps(replay.to_dict()))
                if not replay.quality_ok or data["modes"] != record["modes"]["modes"] or replay.worst_impedance_ohm_per_m != record["worst"]:
                    raise ValueError("Imported raw fields do not reproduce the valid record")
        for key in ("rng_state", "radius", "improvements", "no_improvement"):
            store.state[key] = copy.deepcopy(old[key])
        store.state["records"] = records
        store.state["solve_count"] = prior_solves + old["solve_count"]
        store.state["reservations"] = [dict(number=i+1, source="pre_serial_campaign") for i in range(prior_solves)]
        store.state["reservations"] += [{**r, "number":r["number"]+prior_solves,
            "source_campaign":str(source)} for r in old["reservations"]]
        provenance = dict(source_campaign=str(source), source_state_sha256=digest(source / "state.json"),
            source_contract=old["contract"], original_identity=original,
            imported_solves=old["solve_count"], earlier_solves=prior_solves,
            global_max_solves=config.search.max_solves, pending_recovered=bool(pending))
        store.state.update(pending=None, status="ready_async", import_provenance=provenance)
        atomic_json(store.root / "serial_state.before.json", old)
        atomic_json(store.root / "import_provenance.json", provenance)
        store.save()
        store.sync_mirrors()
