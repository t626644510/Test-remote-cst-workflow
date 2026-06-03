# DDB1 — Durable evaluation DB design

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `365075223ccffce3b2a97beb8dbe0e53a136193e` |
| Branch | `feature/wf1-durable-evaluation-db` |
| Phase label | `DDB1 — Durable evaluation DB design` |
| Nature | **Docs/design only** — no runtime code, no live CST |

---

## Current record / storage state

| Mechanism | Purpose | Is durable? | Is queryable? | Is authoritative? |
|-----------|---------|-------------|---------------|-------------------|
| `.ckpt` (CheckpointManager) | Optimizer warm-start state | Yes (file) | No (binary format) | Yes — optimizer checkpoint |
| `evaluation_records.jsonl` (JSONL sidecar) | Diagnostic record stream | Yes (file) | Limited (append-only) | No — diagnostic only |
| `EvaluationDatabaseRecord` (in-memory) | Taxonomy input / retry loop classification | No (in-memory) | No | No — generated per eval |
| `InMemoryEvaluationRecordIndex` | Dedup for current run | No (in-memory) | Within current run only | No — ephemeral |

### Why JSONL sidecar is not the durable DB

The JSONL sidecar (Phase C) was explicitly designed as a **diagnostic-only stream**:

- It is **append-only**: no indexing, no queries, no update.
- It is **disabled by default** and must not be promoted to a recovery/warm-start source (design constraint from Phase C).
- It lacks a schema version guarantee for cross-run compatibility.
- It stores raw dicts, not structured records with typed fields.
- It was never designed for programmatic read-back — only for external analysis.

A durable evaluation DB must be **queryable**, **schema-versioned**, **opt-in**, and **independent of the JSONL sidecar**.

---

## Proposed DB technology: SQLite

| Requirement | SQLite suitability |
|-------------|-------------------|
| Local file, no server | ✅ Standard library (`sqlite3`) |
| Single-writer, single-process | ✅ Default mode |
| Atomic inserts per row | ✅ Implicit transactions |
| Schema versioning | ✅ Application-managed version table |
| No network dependency | ✅ Local file only |
| Cross-platform | ✅ Built into Python stdlib |

No other DB engine is considered for this track. PostgreSQL, DuckDB, or cloud DB are separate future tracks.

---

## Config shape

```yaml
evaluation_database:
  enabled: false              # master switch; no DB created when false
  path: D:/Results/workflow1/evaluation.db  # must point outside repo
  schema_version: 1           # explicit version pin
  write_mode: final_only      # "final_only" or "all_attempts"
  create_if_missing: true     # auto-create schema on startup
```

### Config validation rules

| Rule | Enforcement |
|------|-------------|
| `path` must be outside repo | If path is inside repo directory, reject with error |
| `enabled` defaults to `false` | No DB interaction when disabled or absent |
| `schema_version` mismatch | Reject open if existing DB has incompatible version |
| `write_mode` default `final_only` | Only the optimizer-used final result is stored; retry attempts are not stored unless `all_attempts` is set |

---

## Schema proposal

### Main table: `evaluation_records`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `schema_version` | INTEGER NOT NULL | Matches `current_schema_version()` |
| `parameter_key` | TEXT NOT NULL | `ParameterIdentity.parameter_key()` (SHA-256 prefix) |
| `param_names` | TEXT | JSON array of ordered names |
| `param_values` | TEXT | JSON array of ordered values |
| `param_precision` | INTEGER | Optional rounding precision |
| `status` | TEXT NOT NULL | `EvaluationDatabaseStatus` value |
| `raw_metrics` | TEXT | JSON dict |
| `objective_values` | TEXT | JSON dict |
| `objective_names` | TEXT | JSON array |
| `gate_results` | TEXT | JSON dict or null |
| `diagnostics` | TEXT | JSON dict or null |
| `source` | TEXT | e.g. `"rfgun_sao.run"` |
| `provenance` | TEXT | JSON dict (git commit, config fingerprint, etc.) |
| `retry_count` | INTEGER NOT NULL DEFAULT 0 |
| `error_taxonomy` | TEXT | JSON dict or null |
| `created_at` | TEXT NOT NULL | ISO-8601 datetime |
| `run_id` | TEXT | Unique run identifier (UUID) for cross-run grouping |

### Version table: `schema_version`

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Indexes

```sql
CREATE INDEX idx_parameter_key ON evaluation_records(parameter_key);
CREATE INDEX idx_status ON evaluation_records(status);
CREATE INDEX idx_run_id ON evaluation_records(run_id);
CREATE INDEX idx_created_at ON evaluation_records(created_at);
```

### DDL provenance

The existing `schema_ddl_sqlite()` in `evaluation_database_schema.py` provides a reference DDL. The DDB2 implementation should either reuse or replace this with an `executescript`-compatible string.

---

## Migration policy

| Principle | Rule |
|-----------|------|
| Forward-only | New columns/indexes added; existing rows not migrated in-place |
| Version table | `schema_version` table records applied version history |
| Incompatible reject | If existing DB's max schema version > code's expected version, reject open with error |
| Compatible probe | `is_schema_compatible(record_version, current_version)` already exists in schema module |
| Rollback | No automatic downgrade; incompatible DB must be manually removed or re-created |

On open:
1. If DB file does not exist and `create_if_missing` is true: create schema, insert version row.
2. If DB file exists: check `schema_version` table. If max version > expected, reject.
3. If max version <= expected: proceed (forward-compatible within same major version).

---

## Write semantics

### `final_only` (default)

- Each evaluation produces exactly one DB row: the **final result used by the optimizer**.
- Intermediate retry attempts are **not written** to the DB.
- The checkpoint callback determines which evaluation is "final" — the retry loop's `final_record`.
- This matches the RW3 checkpoint semantics: checkpoint and DB both record the optimizer-used result.

### `all_attempts` (opt-in)

- Every `evaluate_once` result (including retry attempts) is written to the DB.
- Each row carries the `retry_count` field to distinguish attempts.
- `parameter_key` + `retry_count` uniquely identify an attempt within a run.
- Useful for diagnostics and failure analysis but generates more rows.

### Atomicity

- Each insert is a single `INSERT` statement (auto-commit or explicit transaction).
- A DB write failure must not crash the optimizer — logged warning only.
- The checkpoint file remains the authoritative optimizer state.

---

## Path policy

| Rule | Enforcement |
|------|-------------|
| DB path must be configurable | Via `evaluation_database.path` in config |
| Default path must be outside repo | Default `D:/Results/workflow1/evaluation.db` |
| Path inside repo is rejected | Startup validation: if resolved path starts with repo root, raise `ValueError` |
| `config.local.yaml` overrides only | Default config.yaml has `enabled: false`; path is irrelevant when disabled |
| DB files `.db` / `.sqlite` in `.gitignore` | Already covered by existing `.gitignore` patterns |

---

## Transaction / concurrency policy

| Assumption | Rationale |
|------------|-----------|
| Single-writer | Only one workflow process writes to the DB at a time |
| No concurrent readers | No concurrent workflow processes; external tools may read at any time |
| Atomic insert | Each `INSERT` is wrapped in an implicit or explicit transaction |
| WAL mode optional | May be enabled for concurrent-read performance; not required for correctness |
| Write failure = warning | If `sqlite3` raises on insert, log warning and continue; optimizer state not affected |

---

## Test strategy for DDB2

### Test file

`tests/workflows/test_rfgun_sao_evaluation_database_storage.py`

### Test scenarios (no-CST)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | Create schema from scratch | `sqlite3.connect(temp_db)`, execute DDL, verify tables exist |
| 2 | Insert SUCCESS record | Build `EvaluationDatabaseRecord`, insert as JSON, read back, verify fields |
| 3 | Insert SOLVER_FAILED record | Same as above with failure status |
| 4 | Query by parameter_key | Insert two records with different keys, query by key, verify correct record returned |
| 5 | Schema version mismatch rejection | Create DB with version 2, try to open with expected version 1 → reject |
| 6 | Disabled config = no DB | `enabled: false` → no file created, no query attempted |
| 7 | Path outside repo validation | Path inside repo → `ValueError` |
| 8 | `final_only` vs `all_attempts` | `final_only`: only final record stored; `all_attempts`: retry records also stored |
| 9 | Double insert idempotent | Same parameter_key inserted twice → both rows retained (append); no silent dedup |
| 10 | Provenance stored and readable | Provenance dict round-trips through JSON serialization |

### Test infrastructure

- Temporary SQLite file via `tempfile.NamedTemporaryFile(suffix=".db")` or `pytest` tmp_path.
- Cleanup: test teardown removes temp file.
- No fixture that depends on real CST or workflow.

---

## Explicit non-goals for DDB1–DDB3

| Capability | Not in scope | Notes |
|------------|-------------|-------|
| Success reuse / dedup | ❌ | Separate track (SR1) after DDB accepted |
| Warm-start from DB | ❌ | Separate track (WS1) after DDB accepted |
| Failure reuse | ❌ | Separate track; depends on SR + WS |
| probably-infeasible skip | ❌ | Rejected at runtime |
| DB-backed retry state persistence | ❌ | Future; retry runtime currently in-memory |
| Network DB (PostgreSQL, etc.) | ❌ | Not considered |
| JSONL sidecar replacement | ❌ | JSONL remains diagnostic-only independent stream |
| Checkpoint replacement | ❌ | `.ckpt` remains authoritative optimizer state |
| Live CST | ❌ | No live CST until DDB3 |

---

## Proposed next phases

| Phase | Scope | Live CST? |
|-------|-------|-----------|
| **DDB2** | No-CST SQLite storage implementation: schema creation, insert SUCCESS/FAILURE, query by key, version mismatch, path validation, write mode support | No |
| **DDB3** | Optional live single-eval DB write smoke: run CST, verify DB row written, no orphan DE | Only if operator explicitly approves |
| SR1 | Success reuse design (after DDB accepted) | No |
| WS1 | Warm-start design using DB priors (after DDB accepted) | No |

---

## Summary

This document defines the design for a durable evaluation database using SQLite. The DB is an **explicit opt-in** storage layer that records final evaluation results (and optionally retry attempts) for future query, analysis, and eventual reuse/warm-start tracks. It is independent of the JSONL diagnostic sidecar and does not replace the checkpoint as the authoritative optimizer state.

Key properties:
- SQLite, local file, no server.
- `enabled: false` by default; no DB created or queried when disabled.
- Path must be outside repo; path inside repo is rejected.
- Schema versioning with forward-only migration and incompatible reject.
- `final_only` write mode by default (only optimizer-used result); `all_attempts` optional.
- Write failure is non-fatal (logged warning).
- No success reuse, no warm-start, no failure reuse — those are separate future tracks.

Next actionable phase: **DDB2** — implement the SQLite storage adapter with full no-CST test coverage.
