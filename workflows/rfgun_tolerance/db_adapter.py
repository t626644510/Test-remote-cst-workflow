"""Read-only adapter from evaluation DB rows to TAM2-compatible records — TAM5.

No CST, no JSONL, no Excel.  Read-only from the caller perspective.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def records_from_evaluation_db_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert DB rows from ``get_all_records()`` to TAM2-compatible records.

    Parameters
    ----------
    rows : list of dict
        Rows from ``SQLiteEvaluationDatabase.get_all_records()``.

    Returns
    -------
    list of dict
        Records compatible with ``build_tolerance_dataset_from_records()``.
    """
    records: list[dict[str, Any]] = []
    for row in rows:
        rec: dict[str, Any] = {}

        # Status
        raw_status = row.get("status", "unknown_failed")
        if hasattr(raw_status, "value"):
            rec["status"] = str(raw_status.value)
        else:
            rec["status"] = str(raw_status)

        # Parameter identity
        pn = row.get("param_names")
        pv = row.get("param_values")
        pk = row.get("parameter_key")
        pid: dict[str, Any] | None = None
        if pn is not None and pv is not None:
            pid = {
                "param_names": list(pn) if not isinstance(pn, str) else pn,
                "values": [float(v) for v in pv] if not isinstance(pv, str) else pv,
                "parameter_key": str(pk) if pk else "",
            }
        if pid:
            rec["parameter_identity"] = pid

        # Raw metrics and objective values (already decoded by get_all_records)
        raw_m = row.get("raw_metrics")
        if isinstance(raw_m, dict):
            rec["raw_metrics"] = dict(raw_m)
        obj_v = row.get("objective_values")
        if isinstance(obj_v, dict):
            rec["objective_values"] = dict(obj_v)

        # Only include rows that have at least parameter or metric data
        if pid or raw_m or obj_v:
            records.append(rec)

    return records


def load_records_from_sqlite_db(path: str | Path) -> list[dict[str, Any]]:
    """Load DB rows from a SQLite evaluation database.

    Parameters
    ----------
    path : str or Path
        Path to a SQLite evaluation database file.

    Returns
    -------
    list of dict
        Records compatible with ``build_tolerance_dataset_from_records()``.
    """
    from cst_optimization.evaluation.evaluation_database_storage import (
        EvaluationDatabaseConfig,
        SQLiteEvaluationDatabase,
    )

    cfg = EvaluationDatabaseConfig(
        enabled=True,
        path=str(path),
        create_if_missing=False,
    )
    with SQLiteEvaluationDatabase(cfg) as db:
        rows = db.get_all_records()
    return records_from_evaluation_db_rows(rows)
