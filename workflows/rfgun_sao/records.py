# JSONL evaluation-records sidecar for the RF gun SAO workflow.
# Skeleton — no runtime writes enabled by default.

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------


def make_json_safe(value: object, _max_str_len: int = 200) -> object:
    """Convert *value* to a JSON-safe Python object recursively.

    - ``numpy`` scalars → Python scalars.
    - ``numpy.ndarray`` → list.
    - ``NaN`` / ``Infinity`` / ``-Infinity`` → ``None``.
    - Unsupported objects → ``repr(value)[:_max_str_len]``.
    - ``dict`` keys are converted to ``str``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value == float("inf") or value == -float("inf")):
            return None
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, np.ndarray):
        return [make_json_safe(v) for v in value]
    if isinstance(value, (list, tuple)):
        return [make_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    # numpy scalars
    if isinstance(value, np.floating):
        v = float(value)
        if not np.isfinite(v):
            return None
        return v
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    # Fallback
    return repr(value)[:_max_str_len]


# ---------------------------------------------------------------------------
# Record builder
# ---------------------------------------------------------------------------


def build_evaluation_record(
    *,
    iteration: int,
    x_phys: Any,
    objective_names: list[str],
    raw_values: Any,
    penalties: Any,
    solver_ok: bool,
    error: str,
    diagnostics: dict | None = None,
    gate_results: dict | None = None,
    status: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe evaluation record dict.

    Parameters
    ----------
    iteration : int
        Evaluation iteration index.
    x_phys : array-like
        Physical parameter vector.
    objective_names : list[str]
        Objective metric names in order.
    raw_values : array-like
        Raw values aligned with ``objective_names``.
    penalties : array-like
        Penalty values aligned with ``objective_names``.
    solver_ok : bool
        Whether the solver completed without error.
    error : str
        Error message (empty on success).
    diagnostics : dict or None
        Report-only diagnostics (excluded if None or empty).
    gate_results : dict or None
        Gate pass/fail results (excluded if None or empty).
    status : str or None
        Optional status string (e.g. ``"accepted"``, ``"rejected"``).
    metadata : dict or None
        Optional extra metadata (excluded if None or empty).

    Returns
    -------
    dict
        JSON-safe record ready for serialisation.

    Raises
    ------
    ValueError
        If ``objective_names``, ``raw_values``, or ``penalties`` lengths
        differ.
    """
    n_metrics = len(objective_names)
    raw_list = list(raw_values) if hasattr(raw_values, "__len__") else [raw_values]
    pen_list = list(penalties) if hasattr(penalties, "__len__") else [penalties]
    if len(raw_list) != n_metrics or len(pen_list) != n_metrics:
        raise ValueError(
            f"Length mismatch: objective_names={n_metrics}, "
            f"raw_values={len(raw_list)}, penalties={len(pen_list)}",
        )

    record: dict[str, Any] = {
        "schema_version": 1,
        "iteration": int(iteration),
        "solver_ok": bool(solver_ok),
        "error": str(error),
        "objective_names": list(objective_names),
        "raw_values": dict(zip(
            objective_names,
            [make_json_safe(raw_list[i]) for i in range(n_metrics)],
        )),
        "penalties": dict(zip(
            objective_names,
            [make_json_safe(pen_list[i]) for i in range(n_metrics)],
        )),
        "x_phys": make_json_safe(x_phys),
    }
    if status is not None:
        record["status"] = str(status)
    if diagnostics:
        record["diagnostics"] = make_json_safe(diagnostics)
    if gate_results:
        record["gate_results"] = make_json_safe(gate_results)
    if metadata:
        record["metadata"] = make_json_safe(metadata)

    return record


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------


def append_jsonl_record(path: str | Path, record: dict) -> None:
    """Append one JSON-serialised record as a single line to *path*.

    Creates the parent directory if it does not exist.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n"
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line)


def read_jsonl_records(path: str | Path) -> list[dict]:
    """Read all JSONL records from *path*.

    Returns an empty list if the file does not exist.
    """
    target = Path(path)
    if not target.exists():
        return []
    records: list[dict] = []
    with open(target, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------

_DEFAULT_RECORDS_PATH_SUFFIX = "evaluation_records.jsonl"


def resolve_records_config(cfg: dict) -> dict:
    """Resolve the evaluation-records configuration from a YAML config dict.

    Reads ``cfg["logging"]["evaluation_records"]``.

    Returns a dict with keys ``enabled`` (bool) and ``path`` (str or None).
    Default (missing config) → ``{"enabled": False, "path": None}``.
    """
    log_cfg = cfg.get("logging", {})
    records_cfg = log_cfg.get("evaluation_records", None)

    if records_cfg is None:
        return {"enabled": False, "path": None}

    if isinstance(records_cfg, bool):
        if records_cfg:
            log_dir = str(log_cfg.get("output_dir", "D:/Results"))
            default_path = os.path.join(
                log_dir, "workflow1", _DEFAULT_RECORDS_PATH_SUFFIX,
            )
            return {"enabled": True, "path": default_path}
        return {"enabled": False, "path": None}

    if isinstance(records_cfg, dict):
        enabled = bool(records_cfg.get("enabled", False))
        path = records_cfg.get("path", None)
        if path is None and enabled:
            log_dir = str(log_cfg.get("output_dir", "D:/Results"))
            path = os.path.join(
                log_dir, "workflow1", _DEFAULT_RECORDS_PATH_SUFFIX,
            )
        return {"enabled": enabled, "path": str(path) if path else None}

    return {"enabled": False, "path": None}
