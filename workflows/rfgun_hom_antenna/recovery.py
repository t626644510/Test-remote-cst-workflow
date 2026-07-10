"""Workflow 2 phase-snapshot replay and crash-recovery helpers.

This module intentionally stays inside the Workflow 2 package.  The shared
``cst_optimization.database`` module records and replays generic CST curves;
the phase ordering, objective ownership, and legacy-index repair rules below
are specific to the dual-project HOM workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from cst_optimization.database import VirtualResultReader, load_index


WF2_INDEX_SCHEMA_VERSION = 3


def parameter_hash(
    parameter_names: Sequence[str],
    values: Sequence[float],
) -> str:
    """Return a stable hash for a physical-space Workflow 2 parameter vector."""
    payload = [
        [str(name), float(value)]
        for name, value in zip(parameter_names, values)
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def parameter_hash_from_mapping(
    parameter_names: Sequence[str],
    params: Mapping[str, Any],
) -> str:
    """Hash *params* in the configured parameter order."""
    return parameter_hash(
        parameter_names,
        [float(params[name]) for name in parameter_names],
    )


def record_parameter_hash(
    record: Mapping[str, Any],
    parameter_names: Sequence[str],
) -> str:
    """Read or derive a parameter hash from a schema-v2/v3 index record."""
    stored = str(record.get("params_hash", "") or "")
    if stored:
        return stored
    params = record.get("params", {})
    if not isinstance(params, Mapping):
        return ""
    try:
        return parameter_hash_from_mapping(parameter_names, params)
    except (KeyError, TypeError, ValueError):
        return ""


@dataclass
class SnapshotReplay:
    """Result of replaying objective functions from one cumulative NPZ."""

    raw_values: np.ndarray
    penalties: np.ndarray
    objective_manifest: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def postprocess_ok(self) -> bool:
        """Whether every attempted objective produced a finite raw value."""
        return not self.errors


def replay_snapshot(
    npz_path: str | os.PathLike[str],
    objectives: Sequence[Any],
    obj_project_map: Sequence[str],
    ref_project_map: Sequence[str],
    available_phases: Iterable[str],
) -> SnapshotReplay:
    """Replay objectives whose owning projects are present in a snapshot.

    A cumulative Workflow 2 snapshot contains curves from more than one CST
    project.  The same ``VirtualResultReader`` can therefore serve both the
    primary and reference reader factories for the transverse objective.
    """
    available = set(available_phases)
    raw_values = np.full(len(objectives), np.nan, dtype=float)
    penalties = np.full(len(objectives), np.nan, dtype=float)
    manifest: list[str] = []
    errors: list[str] = []
    reader = VirtualResultReader(str(npz_path))
    try:
        for idx, obj in enumerate(objectives):
            project_label = obj_project_map[idx]
            if project_label not in available:
                continue
            ref_label = (
                ref_project_map[idx]
                if idx < len(ref_project_map)
                else ""
            )
            if ref_label and ref_label not in available:
                errors.append(
                    f"{obj.name}: reference phase '{ref_label}' unavailable"
                )
                continue

            saved_reader = getattr(obj, "_reader_factory", None)
            saved_ref = getattr(obj, "_ref_reader_factory", None)
            obj._reader_factory = lambda vr=reader: vr
            if hasattr(obj, "_ref_reader_factory") and ref_label:
                obj._ref_reader_factory = lambda vr=reader: vr
            try:
                raw = float(obj.raw_value())
                penalty = float(obj.mode.compute(raw))
                if not np.isfinite(raw) or not np.isfinite(penalty):
                    raise ValueError(
                        f"non-finite replay value raw={raw}, penalty={penalty}"
                    )
                raw_values[idx] = raw
                penalties[idx] = penalty
                manifest.append(str(obj.name))
            except Exception as exc:
                errors.append(f"{obj.name}: {exc}")
            finally:
                obj._reader_factory = saved_reader
                if hasattr(obj, "_ref_reader_factory"):
                    obj._ref_reader_factory = saved_ref
    finally:
        reader.close()

    return SnapshotReplay(
        raw_values=raw_values,
        penalties=penalties,
        objective_manifest=manifest,
        errors=errors,
    )


def infer_recoverable_phases(
    replay: SnapshotReplay,
    objectives: Sequence[Any],
    obj_project_map: Sequence[str],
    phase_order: Sequence[str],
) -> list[str]:
    """Infer durable phases from the objectives actually replayable."""
    replayed = set(replay.objective_manifest)
    recovered: list[str] = []
    for phase in phase_order:
        required = {
            str(obj.name)
            for obj, project_label in zip(objectives, obj_project_map)
            if project_label == phase
        }
        if required and required.issubset(replayed):
            recovered.append(phase)
    return recovered


@dataclass
class RecoverySeed:
    """Cumulative snapshot assembled from compatible historical records."""

    npz_path: str = ""
    source_iter: int | None = None
    recovered_phases: list[str] = field(default_factory=list)
    objective_manifest: list[str] = field(default_factory=list)
    replay_values: dict[str, float] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)
    replay_errors: list[str] = field(default_factory=list)


def build_recovery_seed(
    *,
    index_path: str | os.PathLike[str],
    curves_dir: str | os.PathLike[str],
    parameter_names: Sequence[str],
    parameter_values: Sequence[float],
    objectives: Sequence[Any],
    obj_project_map: Sequence[str],
    ref_project_map: Sequence[str],
    phase_order: Sequence[str],
    output_iteration: int,
    output_attempt: int = 0,
    smoke_only: bool = False,
    include_smoke_sources: bool = False,
) -> RecoverySeed:
    """Merge all compatible historical NPZ files into a replayable seed.

    Only files referenced by index rows with the exact physical-parameter hash
    are considered.  This prevents overwritten filenames or unrelated retries
    from being combined merely because their iteration numbers look similar.
    """
    index_file = Path(index_path)
    curves_path = Path(curves_dir)
    target_hash = parameter_hash(parameter_names, parameter_values)
    matching: list[dict[str, Any]] = []
    for record in load_index(str(index_file)):
        if record.get("smoke_only") and not include_smoke_sources:
            continue
        if record_parameter_hash(record, parameter_names) == target_hash:
            matching.append(record)

    matching.sort(
        key=lambda record: (
            str(record.get("timestamp", "")),
            int(record.get("attempt", 0) or 0),
        )
    )
    source_files: list[str] = []
    source_iter: int | None = None
    payload: dict[str, np.ndarray] = {}
    for record in matching:
        npz_name = str(record.get("npz_file", "") or "")
        if not npz_name:
            continue
        npz_file = curves_path / npz_name
        if not npz_file.is_file():
            continue
        resolved = str(npz_file.resolve())
        if resolved in source_files:
            continue
        try:
            with np.load(npz_file, allow_pickle=True) as data:
                payload.update({key: data[key] for key in data.files})
        except Exception:
            continue
        source_files.append(resolved)
        if source_iter is None:
            raw_source = record.get("source_iter", record.get("iter"))
            if isinstance(raw_source, int):
                source_iter = raw_source

    if not payload:
        return RecoverySeed(source_iter=source_iter)

    seed_name = (
        f"eval_{output_iteration:04d}_a{output_attempt:03d}_seed.npz"
    )
    seed_path = curves_path / seed_name
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    payload["__wf2__/schema_version"] = np.array(
        [WF2_INDEX_SCHEMA_VERSION],
        dtype=np.int64,
    )
    payload["__wf2__/params_hash"] = np.array([target_hash])
    payload["__wf2__/smoke_only"] = np.array([bool(smoke_only)])
    np.savez_compressed(seed_path, **payload)

    provisional = list(phase_order)
    replay = replay_snapshot(
        seed_path,
        objectives,
        obj_project_map,
        ref_project_map,
        provisional,
    )
    phases = infer_recoverable_phases(
        replay,
        objectives,
        obj_project_map,
        phase_order,
    )
    replay_values = {
        str(obj.name): float(replay.raw_values[idx])
        for idx, obj in enumerate(objectives)
        if np.isfinite(replay.raw_values[idx])
    }

    return RecoverySeed(
        npz_path=str(seed_path),
        source_iter=source_iter,
        recovered_phases=phases,
        objective_manifest=replay.objective_manifest,
        replay_values=replay_values,
        source_files=source_files,
        replay_errors=replay.errors,
    )


def write_recovery_report(
    output_path: str | os.PathLike[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Write a concise, auditable Markdown report before recovery starts."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Workflow 2 recovery analysis",
        "",
        (
            "| checkpoint | source iter | output iter | recoverable phases | "
            "replayed objectives | source files |"
        ),
        "|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        source_files = "<br>".join(
            Path(str(item)).name for item in row.get("source_files", [])
        ) or "-"
        phases = ", ".join(row.get("recovered_phases", [])) or "none"
        replay_values = row.get("replay_values", {})
        objectives = "<br>".join(
            f"{name}={float(value):.8g}"
            for name, value in replay_values.items()
        ) or "-"
        source_iter = row.get("source_iter")
        lines.append(
            (
                "| {checkpoint} | {source} | {output} | {phases} | "
                "{objectives} | {files} |"
            ).format(
                checkpoint=row.get("checkpoint_index", ""),
                source=source_iter if source_iter is not None else "-",
                output=row.get("output_iteration", ""),
                phases=phases,
                objectives=objectives,
                files=source_files,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def infer_checkpoint_source_iterations(
    checkpoint_values: Sequence[Sequence[float]],
    index_records: Sequence[Mapping[str, Any]],
    parameter_names: Sequence[str],
) -> dict[int, int | None]:
    """Map checkpoint rows to historical iteration IDs by parameter hash.

    Schema-v2 runs did not store the iteration in ``EvalRecord``.  Exact
    parameter matches remain authoritative.  If a checkpoint row has no NPZ
    or index row (for example, a phase-1 solver failure), a consistent
    checkpoint-order offset derived from the exact matches is used only to
    label ``source_iter``; it is never used to select or merge curve files.
    """
    by_hash: dict[str, int] = {}
    for record in index_records:
        params_hash = record_parameter_hash(record, parameter_names)
        raw_source = record.get("source_iter", record.get("iter"))
        if params_hash and isinstance(raw_source, int):
            by_hash[params_hash] = raw_source

    result: dict[int, int | None] = {}
    offsets: list[int] = []
    for idx, values in enumerate(checkpoint_values):
        source = by_hash.get(parameter_hash(parameter_names, values))
        result[idx] = source
        if source is not None:
            offsets.append(source - idx)

    if offsets and len(set(offsets)) == 1:
        offset = offsets[0]
        known = {value for value in result.values() if value is not None}
        for idx, source in list(result.items()):
            candidate = idx + offset
            if source is None and candidate not in known:
                result[idx] = candidate
                known.add(candidate)
    return result
