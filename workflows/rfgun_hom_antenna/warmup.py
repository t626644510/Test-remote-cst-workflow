"""Workflow 2 warm-start bundle construction and loading.

The bundle keeps raw CST curves as the source of truth while adding enough
metadata to distinguish measured objective values from penalties assigned to
intentionally skipped conditional phases.  Scalar penalties are dimensionless
and use the same normalised objective weights as the live Workflow 2 evaluator.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml

from cst_optimization.database import VirtualResultReader, load_index


@dataclass(frozen=True)
class Workflow2WarmupData:
    """Warm-start observations reconstructed from a Workflow 2 curve index."""

    X: np.ndarray
    scalar_penalties: np.ndarray
    penalty_matrix: np.ndarray
    measurement_mask: np.ndarray
    f2w_ran: np.ndarray
    records: list[dict[str, Any]]
    parameter_names: list[str]
    objective_names: list[str]

    @property
    def n_scalar(self) -> int:
        """Number of finite scalar observations."""
        return len(self.scalar_penalties)

    @property
    def n_full_measurements(self) -> int:
        """Number of rows where every objective was physically measured."""
        if not len(self.measurement_mask):
            return 0
        return int(np.count_nonzero(np.all(self.measurement_mask, axis=1)))

    def measured_count(self, objective_name: str) -> int:
        """Return measured-row count for one objective."""
        index = self.objective_names.index(objective_name)
        return int(np.count_nonzero(self.measurement_mask[:, index]))


@dataclass(frozen=True)
class _EvaluatedRecord:
    record: dict[str, Any]
    npz_path: Path
    params: np.ndarray
    raw_values: np.ndarray
    penalties: np.ndarray
    measurement_mask: np.ndarray
    scalar_penalty: float
    f2w_ran: bool
    source_index: Path


def _normalise_weights(
    weights: Sequence[float] | np.ndarray | None,
    n_objectives: int,
) -> np.ndarray:
    if weights is None:
        resolved = np.ones(n_objectives, dtype=float)
    else:
        resolved = np.asarray(weights, dtype=float).ravel()
    if len(resolved) != n_objectives:
        raise ValueError(
            f"Expected {n_objectives} objective weights, got {len(resolved)}"
        )
    if not np.all(np.isfinite(resolved)) or np.any(resolved < 0):
        raise ValueError("Objective weights must be finite and non-negative")
    total = float(np.sum(resolved))
    if total <= 0:
        raise ValueError("Objective weights must have a positive sum")
    return resolved / total


def _eligible_evaluation(record: dict[str, Any]) -> bool:
    if record.get("record_type", "evaluation") != "evaluation":
        return False
    if bool(record.get("smoke_only", False)):
        return False
    if record.get("evaluation_ok") is False:
        return False
    if record.get("solver_ok") is False:
        return False
    return bool(record.get("npz_file")) and isinstance(record.get("params"), dict)


def _record_attempt(record: dict[str, Any]) -> int:
    try:
        return int(record.get("attempt", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _latest_eligible_records(
    index_path: Path,
    parameter_names: Sequence[str],
) -> list[dict[str, Any]]:
    """Select the latest successful evaluation for each exact parameter row."""
    selected: dict[bytes, dict[str, Any]] = {}
    order: list[bytes] = []
    for record in load_index(str(index_path)):
        if not _eligible_evaluation(record):
            continue
        try:
            params = np.asarray(
                [float(record["params"][name]) for name in parameter_names],
                dtype=np.float64,
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not np.all(np.isfinite(params)):
            continue
        key = params.tobytes()
        previous = selected.get(key)
        if previous is None:
            order.append(key)
        if previous is None or _record_attempt(record) >= _record_attempt(previous):
            selected[key] = record
    return [selected[key] for key in order]


def _stored_mapping(
    record: dict[str, Any],
    field: str,
) -> dict[str, Any]:
    value = record.get(field, {})
    return value if isinstance(value, dict) else {}


def _evaluate_record(
    index_path: Path,
    record: dict[str, Any],
    objectives: Sequence[Any],
    weights: np.ndarray,
    parameter_names: Sequence[str],
) -> _EvaluatedRecord | None:
    npz_path = index_path.parent / str(record["npz_file"])
    if not npz_path.is_file():
        return None

    params = np.asarray(
        [float(record["params"][name]) for name in parameter_names],
        dtype=float,
    )
    objective_names = [obj.name for obj in objectives]
    raw_values = np.full(len(objectives), np.nan, dtype=float)
    penalties = np.full(len(objectives), np.nan, dtype=float)
    measured = np.zeros(len(objectives), dtype=bool)

    stored_mask = _stored_mapping(record, "measurement_mask")
    stored_penalties = _stored_mapping(record, "penalty_values")
    if not stored_penalties:
        stored_penalties = _stored_mapping(record, "penalties")
    skipped_phases = set(record.get("skipped_phases", []))

    reader = VirtualResultReader(str(npz_path))
    try:
        for index, objective in enumerate(objectives):
            saved_factory = getattr(objective, "_reader_factory", None)
            has_ref_factory = hasattr(objective, "_ref_reader_factory")
            saved_ref_factory = (
                getattr(objective, "_ref_reader_factory", None)
                if has_ref_factory
                else None
            )
            objective._reader_factory = lambda current=reader: current
            if has_ref_factory:
                objective._ref_reader_factory = lambda current=reader: current
            try:
                raw = float(objective.raw_value())
                if np.isfinite(raw):
                    raw_values[index] = raw
                    measured[index] = True
                    penalties[index] = float(objective.mode.compute(raw))
            except Exception:
                pass
            finally:
                objective._reader_factory = saved_factory
                if has_ref_factory:
                    objective._ref_reader_factory = saved_ref_factory
    finally:
        reader.close()

    # A total-bundle mask is authoritative for distinguishing real
    # measurements from intentionally assigned skip penalties.
    if stored_mask:
        measured = np.asarray(
            [bool(stored_mask.get(name, False)) for name in objective_names],
            dtype=bool,
        )
        raw_values[~measured] = np.nan

    for index, name in enumerate(objective_names):
        if measured[index]:
            continue
        stored = stored_penalties.get(name, np.nan)
        try:
            stored_value = float(stored)
        except (TypeError, ValueError):
            stored_value = np.nan
        if not np.isfinite(stored_value):
            skipped_owner = {
                "z_longitudinal": "wakefield",
                "z_transverse": "wakefield_offset",
            }.get(name)
            if skipped_owner in skipped_phases:
                stored_value = 1.0
        if np.isfinite(stored_value):
            penalties[index] = stored_value

    if not np.all(np.isfinite(penalties)):
        return None

    phases = set(record.get("phase_manifest", []))
    f2w_ran = bool(record.get("has_f2w", False) or "wakefield" in phases)
    return _EvaluatedRecord(
        record=record,
        npz_path=npz_path,
        params=params,
        raw_values=raw_values,
        penalties=penalties,
        measurement_mask=measured,
        scalar_penalty=float(np.dot(penalties, weights)),
        f2w_ran=f2w_ran,
        source_index=index_path,
    )


def load_workflow2_warmup(
    index_path: str | Path,
    objectives: Sequence[Any],
    *,
    weights: Sequence[float] | np.ndarray | None = None,
    parameter_names: Sequence[str] | None = None,
) -> Workflow2WarmupData:
    """Load scalar and per-objective priors from a Workflow 2 curve index."""
    resolved_path = Path(index_path)
    raw_records = load_index(str(resolved_path))
    if not raw_records:
        return Workflow2WarmupData(
            X=np.empty((0, 0)),
            scalar_penalties=np.empty((0,)),
            penalty_matrix=np.empty((0, len(objectives))),
            measurement_mask=np.empty((0, len(objectives)), dtype=bool),
            f2w_ran=np.empty((0,), dtype=bool),
            records=[],
            parameter_names=list(parameter_names or []),
            objective_names=[obj.name for obj in objectives],
        )

    if parameter_names is None:
        first_params = next(
            (
                record.get("params", {})
                for record in raw_records
                if isinstance(record.get("params"), dict)
            ),
            {},
        )
        parameter_names = list(first_params)
    parameter_names = list(parameter_names)
    resolved_weights = _normalise_weights(weights, len(objectives))

    evaluated: list[_EvaluatedRecord] = []
    for record in _latest_eligible_records(resolved_path, parameter_names):
        item = _evaluate_record(
            resolved_path,
            record,
            objectives,
            resolved_weights,
            parameter_names,
        )
        if item is not None:
            evaluated.append(item)

    if not evaluated:
        return Workflow2WarmupData(
            X=np.empty((0, len(parameter_names))),
            scalar_penalties=np.empty((0,)),
            penalty_matrix=np.empty((0, len(objectives))),
            measurement_mask=np.empty((0, len(objectives)), dtype=bool),
            f2w_ran=np.empty((0,), dtype=bool),
            records=[],
            parameter_names=parameter_names,
            objective_names=[obj.name for obj in objectives],
        )

    return Workflow2WarmupData(
        X=np.vstack([item.params for item in evaluated]),
        scalar_penalties=np.asarray(
            [item.scalar_penalty for item in evaluated],
            dtype=float,
        ),
        penalty_matrix=np.vstack([item.penalties for item in evaluated]),
        measurement_mask=np.vstack(
            [item.measurement_mask for item in evaluated]
        ),
        f2w_ran=np.asarray([item.f2w_ran for item in evaluated], dtype=bool),
        records=[item.record for item in evaluated],
        parameter_names=parameter_names,
        objective_names=[obj.name for obj in objectives],
    )


def build_total_warmup_bundle(
    cleaned_index: str | Path,
    recovery_index: str | Path,
    output_dir: str | Path,
    objectives: Sequence[Any],
    *,
    weights: Sequence[float] | np.ndarray | None = None,
    parameter_names: Sequence[str],
    overwrite: bool = False,
) -> Workflow2WarmupData:
    """Merge cleaned and recovered WF2 curves into one immutable bundle."""
    cleaned_path = Path(cleaned_index)
    recovery_path = Path(recovery_index)
    target = Path(output_dir)
    resolved_weights = _normalise_weights(weights, len(objectives))
    parameter_names = list(parameter_names)

    candidates: list[_EvaluatedRecord] = []
    for index_path in (cleaned_path, recovery_path):
        for record in _latest_eligible_records(index_path, parameter_names):
            item = _evaluate_record(
                index_path,
                record,
                objectives,
                resolved_weights,
                parameter_names,
            )
            if item is not None:
                candidates.append(item)

    # Prefer the row with the most measured objectives.  For equal coverage,
    # later sources/attempts win while preserving first-seen output order.
    chosen: dict[bytes, _EvaluatedRecord] = {}
    order: list[bytes] = []
    for item in candidates:
        key = np.asarray(item.params, dtype=np.float64).tobytes()
        previous = chosen.get(key)
        if previous is None:
            order.append(key)
            chosen[key] = item
            continue
        previous_rank = (
            int(np.count_nonzero(previous.measurement_mask)),
            _record_attempt(previous.record),
        )
        current_rank = (
            int(np.count_nonzero(item.measurement_mask)),
            _record_attempt(item.record),
        )
        if current_rank >= previous_rank:
            chosen[key] = item
    selected = [chosen[key] for key in order]

    if target.exists():
        if not overwrite:
            raise FileExistsError(
                f"Warm-up bundle already exists: {target}. "
                "Pass overwrite=True to replace it."
            )
        shutil.rmtree(target)
    target.mkdir(parents=True)

    objective_names = [obj.name for obj in objectives]
    output_records: list[dict[str, Any]] = []
    for bundle_index, item in enumerate(selected):
        output_name = f"eval_total_{bundle_index:04d}.npz"
        shutil.copy2(item.npz_path, target / output_name)
        source_record = item.record
        output_record = {
            "schema_version": 1,
            "bundle_type": "wf2_total_warmup",
            "record_type": "evaluation",
            "iter": bundle_index,
            "params": {
                name: float(value)
                for name, value in zip(parameter_names, item.params)
            },
            "npz_file": output_name,
            "raw_values": {
                name: (
                    float(item.raw_values[index])
                    if item.measurement_mask[index]
                    else None
                )
                for index, name in enumerate(objective_names)
            },
            "penalty_values": {
                name: float(item.penalties[index])
                for index, name in enumerate(objective_names)
            },
            "measurement_mask": {
                name: bool(item.measurement_mask[index])
                for index, name in enumerate(objective_names)
            },
            "scalar_penalty": float(item.scalar_penalty),
            "objective_weights": {
                name: float(resolved_weights[index])
                for index, name in enumerate(objective_names)
            },
            "f2w_ran": bool(item.f2w_ran),
            "has_f2f": bool(source_record.get("has_f2f", True)),
            "has_f2w": bool(item.f2w_ran),
            "has_f2wo": bool(
                source_record.get(
                    "has_f2wo",
                    item.measurement_mask[
                        objective_names.index("z_transverse")
                    ]
                    if "z_transverse" in objective_names
                    else False,
                )
            ),
            "skipped_phases": list(source_record.get("skipped_phases", [])),
            "solver_ok": True,
            "evaluation_ok": True,
            "smoke_only": False,
            "source_index": str(item.source_index),
            "source_npz": item.npz_path.name,
            "source_iter": source_record.get("source_iter", source_record.get("iter")),
            "source_output_iter": source_record.get("iter"),
            "source_attempt": _record_attempt(source_record),
        }
        output_records.append(output_record)

    index_path = target / "index.total.jsonl"
    with index_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in output_records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False))
            handle.write("\n")

    full_count = sum(
        all(record["measurement_mask"].values())
        for record in output_records
    )
    report_lines = [
        "# Workflow 2 total warm-up bundle audit",
        "",
        f"- Scalar-valid unique parameter rows: {len(output_records)}",
        f"- Full four-objective measurements: {full_count}",
        f"- Intentional partial/pre-filter rows: {len(output_records) - full_count}",
        f"- Cleaned source: `{cleaned_path}`",
        f"- Recovery source: `{recovery_path}`",
        "",
        "| bundle iter | source iter | measured objectives | scalar penalty | source file |",
        "|---:|---:|---|---:|---|",
    ]
    for record in output_records:
        measured_names = [
            name
            for name, present in record["measurement_mask"].items()
            if present
        ]
        report_lines.append(
            f"| {record['iter']} | {record['source_iter']} | "
            f"{', '.join(measured_names)} | "
            f"{record['scalar_penalty']:.9f} | {record['source_npz']} |"
        )
    (target / "AUDIT.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    return load_workflow2_warmup(
        index_path,
        objectives,
        weights=resolved_weights,
        parameter_names=parameter_names,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a consolidated Workflow 2 warm-start bundle",
    )
    parser.add_argument("--results-dir", default="Results")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.yaml")),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    # Registration imports are intentionally local so importing this module
    # remains lightweight for tests.
    from cst_optimization.factory import _build_objectives, _resolve_named_weights
    from workflows.rfgun_hom_antenna import antenna_objective  # noqa: F401
    from workflows.rfgun_hom_antenna import wakefield_objective  # noqa: F401

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    workflow_config = config.get("workflow_2", config)
    objectives, _, _ = _build_objectives(workflow_config["objectives"])
    objective_names = [obj.name for obj in objectives]
    weights = _resolve_named_weights(
        workflow_config.get("optimization", {}).get("objective_weights"),
        objective_names,
    )
    parameter_names = [
        entry["name"] for entry in workflow_config["parameters"]
    ]
    results_dir = Path(args.results_dir)
    data = build_total_warmup_bundle(
        results_dir / "wf2_warmup_cleaned" / "index.cleaned.jsonl",
        results_dir / "raw_curves" / "index.jsonl",
        results_dir / "wf2_warmup_total",
        objectives,
        weights=weights,
        parameter_names=parameter_names,
        overwrite=args.overwrite,
    )
    print(
        f"Built {data.n_scalar} scalar priors "
        f"({data.n_full_measurements} full measurements)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
