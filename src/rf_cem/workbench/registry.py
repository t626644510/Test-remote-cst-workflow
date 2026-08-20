"""Deterministic SQLite read model for the local RF-CEM Workbench."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping


WORKBENCH_SCHEMA_VERSION = "rf_cem_workbench.v0"
INDEXER_VERSION = "r5.w5.v0"


class WorkbenchRegistryError(ValueError):
    """Raised when the derived registry cannot be built or read safely."""


@dataclass(frozen=True)
class SourceRecord:
    """One hash-pinned canonical input indexed into the derived registry."""

    source_id: str
    source_kind: str
    display_path: str
    raw_sha256: str
    size_bytes: int
    expected_raw_sha256: str | None = None
    status: str = "indexed"
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityRecord:
    """One typed Workbench catalog entity."""

    entity_kind: str
    entity_id: str
    label: str
    status: str
    source_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationRecord:
    """One deterministic relationship between catalog entities."""

    relation_kind: str
    from_kind: str
    from_id: str
    to_kind: str
    to_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildSummary:
    """Portable summary of a completed registry rebuild."""

    database: Path
    source_count: int
    entity_count: int
    relation_count: int
    input_set_sha256: str


_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    display_path TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    expected_raw_sha256 TEXT,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE entities (
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    source_id TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (entity_kind, entity_id),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
);
CREATE TABLE relations (
    relation_kind TEXT NOT NULL,
    from_kind TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_kind TEXT NOT NULL,
    to_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (relation_kind, from_kind, from_id, to_kind, to_id)
);
CREATE INDEX entities_kind_status_idx ON entities(entity_kind, status);
CREATE INDEX relations_from_idx ON relations(from_kind, from_id);
PRAGMA user_version = 1;
"""


def file_sha256(path: Path) -> str:
    """Return the lowercase raw SHA-256 digest of one file."""
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def canonical_json(value: object) -> str:
    """Return compact deterministic JSON and reject non-finite numbers."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def write_registry(
    database: Path,
    *,
    sources: Iterable[SourceRecord],
    entities: Iterable[EntityRecord],
    relations: Iterable[RelationRecord],
    metadata: Mapping[str, str] | None = None,
) -> BuildSummary:
    """Atomically replace one explicitly named derived Workbench database."""
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    source_rows = sorted(sources, key=lambda row: row.source_id)
    entity_rows = sorted(entities, key=lambda row: (row.entity_kind, row.entity_id))
    relation_rows = sorted(
        relations,
        key=lambda row: (
            row.relation_kind,
            row.from_kind,
            row.from_id,
            row.to_kind,
            row.to_id,
        ),
    )
    _validate_records(source_rows, entity_rows, relation_rows)
    input_set_sha256 = hashlib.sha256(
        canonical_json(
            [
                {
                    "source_id": row.source_id,
                    "raw_sha256": row.raw_sha256,
                    "expected_raw_sha256": row.expected_raw_sha256,
                }
                for row in source_rows
            ]
        ).encode("utf-8")
    ).hexdigest()
    metadata_rows = {
        "schema_version": WORKBENCH_SCHEMA_VERSION,
        "indexer_version": INDEXER_VERSION,
        "source_root": ".",
        "input_set_sha256": input_set_sha256,
        **dict(metadata or {}),
    }

    temporary_handle = tempfile.NamedTemporaryFile(
        prefix=f".{database.name}.", suffix=".tmp", dir=database.parent, delete=False
    )
    temporary_path = Path(temporary_handle.name)
    temporary_handle.close()
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(temporary_path))
        connection.executescript(_SCHEMA_SQL)
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            sorted(metadata_rows.items()),
        )
        connection.executemany(
            """INSERT INTO sources(
                source_id, source_kind, display_path, raw_sha256, size_bytes,
                expected_raw_sha256, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    row.source_id,
                    row.source_kind,
                    row.display_path,
                    row.raw_sha256,
                    row.size_bytes,
                    row.expected_raw_sha256,
                    row.status,
                    canonical_json(dict(row.payload)),
                )
                for row in source_rows
            ],
        )
        connection.executemany(
            """INSERT INTO entities(
                entity_kind, entity_id, label, status, source_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    row.entity_kind,
                    row.entity_id,
                    row.label,
                    row.status,
                    row.source_id,
                    canonical_json(dict(row.payload)),
                )
                for row in entity_rows
            ],
        )
        connection.executemany(
            """INSERT INTO relations(
                relation_kind, from_kind, from_id, to_kind, to_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    row.relation_kind,
                    row.from_kind,
                    row.from_id,
                    row.to_kind,
                    row.to_id,
                    canonical_json(dict(row.payload)),
                )
                for row in relation_rows
            ],
        )
        connection.commit()
        connection.execute("VACUUM")
        connection.close()
        connection = None
        os.replace(temporary_path, database)
    except Exception:
        if connection is not None:
            connection.close()
        temporary_path.unlink(missing_ok=True)
        raise

    return BuildSummary(
        database=database,
        source_count=len(source_rows),
        entity_count=len(entity_rows),
        relation_count=len(relation_rows),
        input_set_sha256=input_set_sha256,
    )


class RegistryReader:
    """Read-only query interface used by the local Workbench server."""

    def __init__(self, database: Path) -> None:
        self.database = database.resolve()
        if not self.database.is_file():
            raise WorkbenchRegistryError(f"Workbench database is missing: {database}")

    def metadata(self) -> dict[str, str]:
        """Return registry metadata."""
        with closing(self._connect()) as connection:
            return {
                str(row["key"]): str(row["value"])
                for row in connection.execute(
                    "SELECT key, value FROM metadata ORDER BY key"
                )
            }

    def list_sources(self) -> list[dict[str, Any]]:
        """Return stored source bindings without opening their files."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT source_id, source_kind, display_path, raw_sha256,
                          size_bytes, expected_raw_sha256, status, payload_json
                   FROM sources ORDER BY source_id"""
            )
            return [_source_row(row) for row in rows]

    def list_entities(self, entity_kind: str | None = None) -> list[dict[str, Any]]:
        """Return all entities or one fixed entity kind."""
        with closing(self._connect()) as connection:
            if entity_kind is None:
                rows = connection.execute(
                    """SELECT entity_kind, entity_id, label, status, source_id,
                              payload_json
                       FROM entities ORDER BY entity_kind, entity_id"""
                )
            else:
                rows = connection.execute(
                    """SELECT entity_kind, entity_id, label, status, source_id,
                              payload_json
                       FROM entities WHERE entity_kind = ? ORDER BY entity_id""",
                    (entity_kind,),
                )
            return [_entity_row(row) for row in rows]

    def entity_counts(self) -> dict[str, int]:
        """Return entity counts grouped by kind."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT entity_kind, COUNT(*) AS count
                   FROM entities GROUP BY entity_kind ORDER BY entity_kind"""
            )
            return {str(row["entity_kind"]): int(row["count"]) for row in rows}

    def list_relations(self) -> list[dict[str, Any]]:
        """Return all entity relationships."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT relation_kind, from_kind, from_id, to_kind, to_id,
                          payload_json
                   FROM relations
                   ORDER BY relation_kind, from_kind, from_id, to_kind, to_id"""
            )
            return [
                {
                    "relation_kind": row["relation_kind"],
                    "from_kind": row["from_kind"],
                    "from_id": row["from_id"],
                    "to_kind": row["to_kind"],
                    "to_id": row["to_id"],
                    "payload": json.loads(row["payload_json"]),
                }
                for row in rows
            ]

    def snapshot(self) -> dict[str, Any]:
        """Return a deterministic portable registry snapshot."""
        return {
            "metadata": self.metadata(),
            "sources": self.list_sources(),
            "entities": self.list_entities(),
            "relations": self.list_relations(),
        }

    def audit_sources(self, source_root: Path) -> list[dict[str, Any]]:
        """Re-hash indexed paths and report fresh, stale, or missing sources."""
        root = source_root.resolve()
        results: list[dict[str, Any]] = []
        for source in self.list_sources():
            relative = _safe_relative_path(str(source["display_path"]))
            candidate = (root / Path(*relative.parts)).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise WorkbenchRegistryError(
                    f"indexed source escapes source root: {relative}"
                ) from exc
            if not candidate.is_file():
                state = "missing"
                actual = None
            else:
                actual = file_sha256(candidate)
                state = "fresh" if actual == source["raw_sha256"] else "stale"
            results.append(
                {
                    "source_id": source["source_id"],
                    "display_path": source["display_path"],
                    "stored_raw_sha256": source["raw_sha256"],
                    "actual_raw_sha256": actual,
                    "status": state,
                }
            )
        return results

    def _connect(self) -> sqlite3.Connection:
        uri = f"{self.database.as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def _validate_records(
    sources: list[SourceRecord],
    entities: list[EntityRecord],
    relations: list[RelationRecord],
) -> None:
    source_ids: set[str] = set()
    for row in sources:
        _non_empty(row.source_id, "source_id")
        _non_empty(row.source_kind, "source_kind")
        _safe_relative_path(row.display_path)
        if row.source_id in source_ids:
            raise WorkbenchRegistryError(f"duplicate source_id: {row.source_id}")
        source_ids.add(row.source_id)
        _sha256(row.raw_sha256, "raw_sha256")
        if row.expected_raw_sha256 is not None:
            _sha256(row.expected_raw_sha256, "expected_raw_sha256")
        if row.size_bytes < 0:
            raise WorkbenchRegistryError("source size_bytes cannot be negative")
        canonical_json(dict(row.payload))

    entity_ids: set[tuple[str, str]] = set()
    for row in entities:
        key = (row.entity_kind, row.entity_id)
        for value, label in (
            (row.entity_kind, "entity_kind"),
            (row.entity_id, "entity_id"),
            (row.label, "label"),
            (row.status, "status"),
        ):
            _non_empty(value, label)
        if key in entity_ids:
            raise WorkbenchRegistryError(f"duplicate entity: {key}")
        entity_ids.add(key)
        if row.source_id is not None and row.source_id not in source_ids:
            raise WorkbenchRegistryError(
                f"entity {key} references unknown source: {row.source_id}"
            )
        canonical_json(dict(row.payload))

    relation_ids: set[tuple[str, str, str, str, str]] = set()
    for row in relations:
        key = (
            row.relation_kind,
            row.from_kind,
            row.from_id,
            row.to_kind,
            row.to_id,
        )
        if key in relation_ids:
            raise WorkbenchRegistryError(f"duplicate relation: {key}")
        relation_ids.add(key)
        if (row.from_kind, row.from_id) not in entity_ids:
            raise WorkbenchRegistryError(f"relation source entity is missing: {key}")
        if (row.to_kind, row.to_id) not in entity_ids:
            raise WorkbenchRegistryError(f"relation target entity is missing: {key}")
        canonical_json(dict(row.payload))


def _source_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source_id": row["source_id"],
        "source_kind": row["source_kind"],
        "display_path": row["display_path"],
        "raw_sha256": row["raw_sha256"],
        "size_bytes": int(row["size_bytes"]),
        "expected_raw_sha256": row["expected_raw_sha256"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"]),
    }


def _entity_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "entity_kind": row["entity_kind"],
        "entity_id": row["entity_id"],
        "label": row["label"],
        "status": row["status"],
        "source_id": row["source_id"],
        "payload": json.loads(row["payload_json"]),
    }


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value.strip() or path.is_absolute() or ".." in path.parts:
        raise WorkbenchRegistryError(f"source path must be safe and relative: {value}")
    return path


def _non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkbenchRegistryError(f"{label} must be a non-empty string")
    return value


def _sha256(value: str, label: str) -> str:
    text = str(value).lower().removeprefix("sha256:")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise WorkbenchRegistryError(f"{label} must be a SHA-256 digest")
    return text


__all__ = [
    "BuildSummary",
    "EntityRecord",
    "INDEXER_VERSION",
    "RegistryReader",
    "RelationRecord",
    "SourceRecord",
    "WORKBENCH_SCHEMA_VERSION",
    "WorkbenchRegistryError",
    "canonical_json",
    "file_sha256",
    "write_registry",
]
