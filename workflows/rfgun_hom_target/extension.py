"""Replay completed distributed evidence into a separately budgeted extension.

No CST session is opened. New geometry/search limits may differ; the template,
solver and physical sampling contract must match. Impedance units are ohm/m.
"""
from dataclasses import asdict
import copy
import json
from pathlib import Path
import shutil
from typing import Any

from .geometry import GeometryConstraints
from .postprocess import PostprocessConfig, analyze_bundle
from .runtime import metadata, postprocess_config
from .search import objective
from .seeding import archive_lock
from .storage import atomic_json, digest, fingerprint, project_manifest


def import_completed(config: Any, store: Any, template: Path, source: Path) -> None:
    """Import a stopped distributed campaign, with zero *new* consumed solves.

Only replayed admissible observations train the GP. All historical coordinates
remain available for deduplication. Old records, budgets and field files are
preserved; a changed model must start without this import.
    """
    source = source.resolve()
    if source == store.root.resolve() or store.state["records"] or store.state["solve_count"] or store.state["pending"]:
        raise ValueError("Extension import requires a fresh separate campaign")
    with archive_lock(source):
        def read(name: str) -> Any:
            return json.loads((source / name).read_text(encoding="utf-8"))
        state, previous, identity = read("state.json"), read("config.resolved.json"), read("execution_identity.json")
        state_hash = digest(source / "state.json")
        if state["status"] not in {"budget_exhausted", "candidate_limit", "target_reached", "no_feasible_candidates"}:
            raise ValueError("Extension source is not a finished campaign")
        if state.get("pending") or any(j["state"] != "finished" for j in state.get("jobs", {}).values()):
            raise ValueError("Extension source still has in-flight work")
        if fingerprint(identity) != state["contract"] or identity["settings"] != {k:v for k,v in previous.items() if k != "paths"}:
            raise ValueError("Historical execution identity does not match its configuration")
        if project_manifest(template) != identity["template"]:
            raise ValueError("Extension template differs from the solved model")
        now = config.as_dict()
        for key in ("solver", "results"):
            if now[key] != previous[key]:
                raise ValueError("Extension numerical settings differ: " + key)
        if {k:v for k,v in now["physics"].items() if k != "mode_policy"} != {k:v for k,v in previous["physics"].items() if k != "mode_policy"}:
            raise ValueError("Extension field/physics settings differ")
        coordinate_contract = lambda items: [(p["name"],p["unit"],p["cst_name"]) for p in items]
        if coordinate_contract(now["parameters"]) != coordinate_contract(previous["parameters"]):
            raise ValueError("Extension parameter mapping differs")
        geometry = GeometryConstraints(**asdict(config.geometry))
        expected = asdict(postprocess_config(config, metadata(template)))
        staged, proofs = [], []
        for index, old in enumerate(state["records"]):
            record = copy.deepcopy(old)
            record.update(id=f"history_{index:04d}", source="history_archive", history_import=True,
                          historical_id=old["id"], historical_status=old["status"])
            p = record["parameters"]
            admissible = geometry.feasible(p) and all(c.lower <= p[c.name] <= c.upper for c in config.parameters)
            if not admissible or old["status"] not in {"valid", "quality_failed"}:
                record.update(status="history_excluded", objective=None, worst=None)
                staged.append(record)
                continue
            bundles = list(Path(old["attempt_dir"]).glob("attempt_*/postprocess_*/field_config.json"))
            if len(bundles) != 1:
                raise ValueError(f"Ambiguous/missing field evidence: {old['id']}")
            bundle = bundles[0].parent
            raw = json.loads(bundles[0].read_text(encoding="utf-8"))
            actual = asdict(PostprocessConfig.from_mapping({k:v for k,v in raw.items() if k in expected}))
            for key in expected:
                if key not in {"mode_policy", "conductivity_layers"} and actual[key] != expected[key]:
                    raise ValueError("Historical field contract differs: " + key)
            if raw.get("band_mhz") != [config.physics.frequency_min_mhz, config.physics.frequency_max_mhz]:
                raise ValueError("Historical field band differs")
            hashes = {str(p.relative_to(bundle)):digest(p) for p in bundle.rglob("*") if p.is_file()}
            replay = analyze_bundle(bundle, mode_policy=config.physics.mode_policy)
            data = json.loads(json.dumps(replay.to_dict()))
            if data["modes"] != old["modes"]["modes"] or data["native_modes"] != old["modes"]["native_modes"]:
                raise ValueError("Historical raw data does not reproduce recorded modes")
            if not replay.quality_ok:
                raise ValueError("Admissible historical fields fail extraction quality")
            worst = float(replay.worst_impedance_ohm_per_m)
            destination = store.root / "evaluations" / record["id"] / "attempt_imported" / "postprocess_000"
            shutil.copytree(bundle, destination)
            if hashes != {str(p.relative_to(destination)):digest(p) for p in destination.rglob("*") if p.is_file()}:
                raise ValueError("Historical field copy changed")
            atomic_json(destination / "analysis.json", data)
            atomic_json(destination / "field_config.json", {**raw, "mode_policy":config.physics.mode_policy})
            record.update(status="valid", modes=data, worst=worst,
                          objective=objective(worst, config.physics.threshold_ohm_per_m),
                          attempt_dir=str(destination.parent.parent))
            staged.append(record)
            proofs.append(dict(id=record["id"], historical_id=old["id"], bundle=str(bundle), hashes=hashes))
        if not staged or staged[0]["status"] != "valid":
            raise ValueError("Extension requires an admissible replayed baseline")
        if digest(source / "state.json") != state_hash:
            raise ValueError("Historical source changed during replay")
        provenance = dict(source_campaign=str(source), source_contract=state["contract"],
                          source_state_sha256=state_hash, previous_solves=state["solve_count"],
                          additional_max_solves=config.search.max_solves, replayed=proofs)
        atomic_json(store.root / "history_state.snapshot.json", state)
        atomic_json(store.root / "extension_provenance.json", provenance)
        store.state.update(records=staged, extension_provenance=provenance,
                           radius=config.search.initial_radius, improvements=0, no_improvement=0,
                           rng_state=None, status="ready")
        store.save()
        store.sync_mirrors()
