# Durable evaluation DB storage — no-CST SQLite adapter.
# Stores authoritative final evaluation records only.
# No failure reuse.  Success reuse and warm-start are implemented by
# higher-level helpers (SR, WS tracks) with explicit opt-in config.
# Explicit opt-in only; disabled by default.
#
# Phase DDB2 — no-CST SQLite storage implementation.

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cst_optimization.evaluation.schema import (
    EvaluationDatabaseRecord,
    current_schema_version,
    record_to_json_dict,
    schema_ddl_sqlite,
    validate_evaluation_record,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class EvaluationDatabaseConfig:
    """Resolved configuration for the evaluation database.

    Parameters
    ----------
    enabled : bool
        Whether the database is active.
    path : str or None
        Filesystem path to the SQLite DB file.  ``None`` when disabled.
    schema_version : int
        Expected schema version.
    create_if_missing : bool
        Whether to auto-create schema when the DB file does not exist.
    """
    enabled: bool = False
    path: str | None = None
    schema_version: int = 1
    create_if_missing: bool = True


def resolve_evaluation_database_config(
    config: dict | None,
    repo_root: str | None = None,
) -> EvaluationDatabaseConfig:
    """Resolve the evaluation database configuration from a workflow config dict.

    Parameters
    ----------
    config : dict or None
        Full workflow configuration dict.  ``None`` returns disabled config.
    repo_root : str or None
        Absolute path to the repository root for inside-repo detection.
        If ``None``, the check is skipped.

    Returns
    -------
    EvaluationDatabaseConfig
        Resolved config.  ``enabled=False`` when the section is absent or
        explicitly disabled.

    Raises
    ------
    ValueError
        If ``enabled=True`` but *path* is missing, empty, or points inside
        the repository root.
    """
    if config is None:
        return EvaluationDatabaseConfig()

    raw = config.get("evaluation_database", None)
    if raw is None:
        return EvaluationDatabaseConfig()

    enabled = bool(raw.get("enabled", False))
    if not enabled:
        return EvaluationDatabaseConfig()

    path = raw.get("path", None)
    if not path or not str(path).strip():
        raise ValueError(
            "evaluation_database.path is required when "
            "evaluation_database.enabled=True",
        )

    resolved = os.path.abspath(os.path.expanduser(str(path).strip()))

    if repo_root is not None:
        repo_abs = os.path.abspath(repo_root)
        try:
            # Check if resolved path is inside the repo root
            Path(resolved).relative_to(Path(repo_abs))
            raise ValueError(
                f"evaluation_database.path ({resolved}) is inside the repository "
                f"root ({repo_abs}).  The DB file must be outside the repo.",
            )
        except ValueError as exc:
            if "inside the repository" in str(exc):
                raise
            # Not relative → path is outside repo, which is correct
            pass

    return EvaluationDatabaseConfig(
        enabled=True,
        path=resolved,
        schema_version=int(raw.get("schema_version", current_schema_version())),
        create_if_missing=bool(raw.get("create_if_missing", True)),
    )


# ---------------------------------------------------------------------------
# SQLite storage
# ---------------------------------------------------------------------------


class SQLiteEvaluationDatabase:
    """SQLite-backed evaluation record storage.

    Stores authoritative final evaluation records only (no retry attempts).
    No failure reuse.  Warm-start and success reuse are implemented by
    higher-level helpers (WS, SR tracks) with explicit opt-in config.

    Parameters
    ----------
    config : EvaluationDatabaseConfig
        Resolved config.  Must have ``enabled=True`` and a valid ``path``.
    """

    def __init__(self, config: EvaluationDatabaseConfig) -> None:
        if not config.enabled:
            raise ValueError("Cannot instantiate with disabled config")
        if not config.path:
            raise ValueError("Cannot instantiate without path")
        self._config = config
        self._conn: sqlite3.Connection | None = None
        self._run_id: str | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> SQLiteEvaluationDatabase:
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open or create the SQLite database and verify schema compatibility."""
        if self._conn is not None:
            return

        path = self._config.path
        db_exists = os.path.isfile(path) and os.path.getsize(path) > 0

        # Handle create_if_missing=False with missing or empty DB file
        if not db_exists and not self._config.create_if_missing:
            raise ValueError(
                f"Evaluation DB file does not exist at {path} and "
                "create_if_missing=False",
            )

        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row

        try:
            if not db_exists and self._config.create_if_missing:
                self._initialize_schema()
            elif db_exists:
                self._verify_schema()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def set_run_id(self, run_id: str) -> None:
        """Set a run identifier for subsequent inserts."""
        self._run_id = run_id

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _initialize_schema(self) -> None:
        """Create the schema and insert the version row."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("Not connected")

        cursor = conn.cursor()
        cursor.executescript(schema_ddl_sqlite())
        cursor.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (self._config.schema_version,),
        )
        conn.commit()
        _logger.info(
            "Evaluation DB schema created (version=%d) at %s",
            self._config.schema_version, self._config.path,
        )

    def _verify_schema(self) -> None:
        """Verify the existing DB schema is compatible."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("Not connected")

        cursor = conn.cursor()

        # Check if schema_version table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'",
        )
        if cursor.fetchone() is None:
            raise ValueError(
                f"Existing DB at {self._config.path} has no schema_version table. "
                "Cannot determine compatibility.",
            )

        cursor.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        db_version = int(row[0]) if row and row[0] is not None else 0
        expected = self._config.schema_version

        if db_version > expected:
            raise ValueError(
                f"Evaluation DB schema version {db_version} is newer than "
                f"expected {expected}.  Upgrade the code or recreate the DB.",
            )
        if db_version < expected:
            raise ValueError(
                f"Evaluation DB schema version {db_version} is older than "
                f"expected {expected} and no migration is available.  "
                "Recreate the DB or add a migration.",
            )

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert_final_record(
        self,
        record: EvaluationDatabaseRecord,
        run_id: str | None = None,
    ) -> int:
        """Insert one authoritative final evaluation record.

        Parameters
        ----------
        record : EvaluationDatabaseRecord
            The final record to store.  Must have a non-``None``
            ``parameter_identity``.
        run_id : str or None
            Run identifier.  Falls back to ``self._run_id`` if not provided.

        Returns
        -------
        int
            The row ID of the inserted record.

        Raises
        ------
        ValueError
            If *record* is missing ``parameter_identity``.
        RuntimeError
            If the database is not open.
        """
        # Validate the record before insert
        try:
            validate_evaluation_record(record)
        except ValueError as exc:
            raise ValueError(f"Invalid evaluation record: {exc}") from exc

        if record.parameter_identity is None:
            raise ValueError(
                "Cannot insert evaluation record without parameter_identity",
            )

        # Validate record schema version matches DB schema version
        if record.schema_version != self._config.schema_version:
            raise ValueError(
                f"Record schema version {record.schema_version} does not match "
                f"evaluation DB schema version {self._config.schema_version}",
            )

        conn = self._conn
        if conn is None:
            raise RuntimeError("Database is not open")

        pid = record.parameter_identity
        effective_run_id = run_id or self._run_id

        cursor = conn.execute(
            """
            INSERT INTO evaluation_records (
                schema_version, parameter_key, param_names, param_values,
                param_precision, status, raw_metrics, objective_values,
                objective_names, gate_results, diagnostics, artifact_refs,
                source, provenance, retry_count, error_taxonomy, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.schema_version,
                pid.parameter_key(),
                json.dumps(pid.param_names),
                json.dumps(pid.values),
                pid.precision,
                str(record.status),
                self._json_or_none(
                    record.raw_payload.raw_metrics if record.raw_payload else None,
                ),
                self._json_or_none(
                    record.raw_payload.objective_values if record.raw_payload else None,
                ),
                self._json_or_none(record.objective_names),
                self._json_or_none(
                    record.raw_payload.gate_results if record.raw_payload else None,
                ),
                self._json_or_none(
                    record.raw_payload.diagnostics if record.raw_payload else None,
                ),
                self._json_or_none(
                    record.raw_payload.artifact_refs if record.raw_payload else None,
                ),
                record.source,
                self._json_or_none(record.provenance),
                record.retry_count,
                self._json_or_none(record.error_taxonomy),
                effective_run_id,
            ),
        )
        conn.commit()
        return cursor.lastrowid or -1

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_by_parameter_key(
        self,
        parameter_key: str,
    ) -> list[dict[str, Any]]:
        """Return all records matching a parameter key, newest first.

        This is a **diagnostic / inspection-only** query.  No workflow
        behaviour depends on it.  No success reuse or warm-start semantics.

        Returns
        -------
        list[dict]
            Row data as dicts (JSON fields decoded).
        """
        conn = self._conn
        if conn is None:
            raise RuntimeError("Database is not open")

        cursor = conn.execute(
            "SELECT * FROM evaluation_records WHERE parameter_key = ? "
            "ORDER BY created_at DESC",
            (parameter_key,),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def count_records(self) -> int:
        """Return total number of records in the database."""
        conn = self._conn
        if conn is None:
            return 0
        cursor = conn.execute("SELECT COUNT(*) FROM evaluation_records")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def get_all_records(self) -> list[dict[str, Any]]:
        """Return all records, newest first.

        Each row is a dict with JSON columns decoded.
        """
        conn = self._conn
        if conn is None:
            return []
        cursor = conn.execute(
            "SELECT * FROM evaluation_records ORDER BY created_at DESC",
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _json_or_none(value: object) -> str | None:
        """Serialize *value* to JSON string, or return ``None``."""
        if value is None:
            return None
        return json.dumps(value)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a ``sqlite3.Row`` to a plain dict, decoding JSON columns."""
        data = dict(row)
        json_cols = {
            "param_names", "param_values", "raw_metrics", "objective_values",
            "objective_names", "gate_results", "diagnostics", "artifact_refs",
            "provenance", "error_taxonomy",
        }
        for col in json_cols:
            val = data.get(col)
            if val is not None and isinstance(val, str):
                try:
                    data[col] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        return data
