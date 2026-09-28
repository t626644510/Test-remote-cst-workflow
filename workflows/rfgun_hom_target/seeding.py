"""Explicit baseline migration after changing only the mode acceptance policy.

No CST session is opened. The previous campaign is locked against concurrent
writers, its template and saved solve verified, and raw fields recomputed.
Old native projects and campaign records are never rewritten.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterator

from .postprocess import PostprocessConfig, analyze_bundle
from .runtime import metadata, postprocess_config, read_baseline, verify_solved
from .search import objective
from .session_recovery import ensure_sessions_inactive
from .storage import atomic_json, digest, project_manifest


@contextmanager
def archive_lock(root: Path) -> Iterator[None]:
    """Acquire the existing campaign lock without changing its bytes or DB."""
    with (root / "campaign.lock").open("r+b") as stream:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_seed_config(current: Any, previous: dict[str, Any], solve_count: int) -> None:
    """Only mode-policy changes qualify; preserve sampling and remaining budget."""
    now = current.as_dict()
    for section in ("solver", "geometry", "parameters", "results"):
        if now[section] != previous[section]:
            raise ValueError(f"Seed {section} differs from current configuration")
    old_physics = {k: v for k, v in previous["physics"].items() if k != "mode_policy"}
    new_physics = {k: v for k, v in now["physics"].items() if k != "mode_policy"}
    if old_physics != new_physics:
        raise ValueError("Seed numerical physics settings differ")
    if current.search.max_solves > previous["search"]["max_solves"] - solve_count:
        raise ValueError("Seed import must retain the previous remaining solve budget")


def import_baseline(config: Any, store: Any, template: Path, source_root: Path) -> None:
    """Import exactly one completed baseline under a new, explicit policy.

    Score convention remains peak/beta=1/circuit, in ohm/m. All raw fields are
    recomputed, never merely relabelled valid. This consumes no solver budget.
    """
    root = source_root.resolve()
    if root == store.root.resolve() or store.state["records"] or store.state["pending"] or store.state["solve_count"]:
        raise ValueError("Seed requires a fresh, separate destination campaign")
    with archive_lock(root):
        state, old_config, old_template = (_json(root / name) for name in
            ("state.json", "config.resolved.json", "template.json"))
        if state["pending"] or len(state["records"]) != 1 or state["status"] not in {"baseline_failed", "baseline_complete", "target_reached"}:
            raise ValueError("Seed campaign must be stopped with exactly one completed baseline")
        validate_seed_config(config, old_config, state["solve_count"])
        if project_manifest(Path(old_template["project"])) != old_template["manifest"] or project_manifest(template) != old_template["manifest"]:
            raise ValueError("Seed template fingerprint differs")
        record = state["records"][0]
        if record["source"] != "baseline" or record["status"] not in {"valid", "quality_failed"}:
            raise ValueError("Seed must have a solved baseline with complete field evidence")
        evaluation = Path(record["attempt_dir"]).resolve()
        if root not in evaluation.parents:
            raise ValueError("Seed evaluation is outside its campaign")
        ensure_sessions_inactive(evaluation)
        saved = _json(evaluation / "evaluation.json")
        attempt = Path(saved["current"]).resolve()
        project = Path(saved["project"]).resolve()
        if evaluation not in attempt.parents or attempt not in project.parents:
            raise ValueError("Seed project/attempt paths are inconsistent")
        verify_solved(project, attempt)
        parameters = read_baseline(template, config)
        if parameters != record["parameters"] or read_baseline(project, config) != parameters:
            raise ValueError("Seed geometry differs from baseline")
        bundles = sorted(attempt.glob("postprocess_*/analysis.json"))
        if not bundles:
            raise ValueError("Seed has no completed raw field bundle")
        bundle = bundles[-1].parent
        raw_config = _json(bundle / "field_config.json")
        expected = asdict(postprocess_config(config, metadata(template)))
        actual = asdict(PostprocessConfig.from_mapping({k: v for k, v in raw_config.items() if k in expected}))
        for key in expected:
            if key not in {"mode_policy", "conductivity_layers"} and actual[key] != expected[key]:
                raise ValueError(f"Seed field contract differs: {key}")
        if raw_config.get("band_mhz") != [config.physics.frequency_min_mhz, config.physics.frequency_max_mhz]:
            raise ValueError("Seed objective frequency band differs")
        before = {str(p.relative_to(bundle)): digest(p) for p in bundle.rglob("*") if p.is_file()}
        original = json.loads(json.dumps(analyze_bundle(bundle).to_dict()))
        if original["modes"] != record["modes"]["modes"] or original["native_modes"] != record["modes"]["native_modes"]:
            raise ValueError("Seed raw evidence does not reproduce recorded metrics")
        processed = analyze_bundle(bundle, mode_policy=config.physics.mode_policy)
        if not processed.quality_ok:
            raise ValueError("Seed still fails numerical field/energy quality checks")
        after = {str(p.relative_to(bundle)): digest(p) for p in bundle.rglob("*") if p.is_file()}
        if after != before:
            raise ValueError("Seed fields changed during import")
        provenance = dict(source_campaign=str(root), source_contract=state["contract"],
            source_state_sha256=digest(root / "state.json"), source_bundle=str(bundle),
            source_bundle_manifest=before, saved_solve_sha256=digest(attempt / "solved.json"),
            previous_mode_policy=old_config["physics"].get("mode_policy", "strict_all"),
            mode_policy=config.physics.mode_policy, previous_solve_count=state["solve_count"],
            new_remaining_budget=config.search.max_solves)
        destination = store.root / "evaluations/evaluation_0000"
        copied = destination / "attempt_imported/postprocess_000"
        shutil.copytree(bundle, copied)
        raw_config["mode_policy"] = config.physics.mode_policy
        atomic_json(copied / "field_config.json", raw_config)
        data = processed.to_dict()
        atomic_json(copied / "analysis.json", data)
        atomic_json(store.root / "seed_provenance.json", provenance)
        worst = float(processed.worst_impedance_ohm_per_m)
        imported = dict(id="evaluation_0000", parameters=parameters, source="baseline_archive",
            status="valid", worst=worst, objective=objective(worst, config.physics.threshold_ohm_per_m),
            project=str(project), attempt_dir=str(destination), modes=data, seed_provenance=provenance,
            coverage_policy=record.get("coverage_policy"), coverage_basis=record.get("coverage_basis"),
            coverage_verified=record.get("coverage_verified", False))
        store.state["seed_provenance"] = provenance
        store.finish(imported)
