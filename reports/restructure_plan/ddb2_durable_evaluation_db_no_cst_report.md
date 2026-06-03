# DDB2 — Durable evaluation DB no-CST SQLite storage implementation

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `ae726b36f657685a076e33d4cebbeafe2fb09113` |
| Phase label | `DDB2 — Durable evaluation DB no-CST SQLite storage implementation` |
| Branch | `feature/wf1-durable-evaluation-db` |
| Live CST | **No** — pure no-CST implementation |
| Runtime workflow integration | **Not wired** — storage layer only |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_database_schema.py` | **Modified** | Updated `schema_ddl_sqlite()` with `schema_version` table, `run_id` column, `IF NOT EXISTS` on indexes |
| `workflows/rfgun_sao/evaluation_database_storage.py` | **Added** | Config resolver + `SQLiteEvaluationDatabase` class |
| `tests/workflows/test_rfgun_sao_evaluation_database_storage.py` | **Added** | 29 no-CST storage tests |
| `reports/restructure_plan/ddb2_durable_evaluation_db_no_cst_report.md` | **Added** | This report |

---

## Implementation summary

### Module: `evaluation_database_storage.py`

Two public components:

#### `resolve_evaluation_database_config(config, repo_root=None) -> EvaluationDatabaseConfig`

| Scenario | Result |
|----------|--------|
| `config` is `None` or no `evaluation_database` section | `enabled=False`, no validation |
| `enabled=false` | `enabled=False`, path not read or validated |
| `enabled=true` with missing/empty `path` | `ValueError` raised |
| `enabled=true` with path inside repo | `ValueError` raised |
| `enabled=true` with valid path outside repo | `EvaluationDatabaseConfig(enabled=True, path=resolved, ...)` |

#### `SQLiteEvaluationDatabase`

| Method | Behaviour |
|--------|-----------|
| `open()` | Creates DB file if missing + `create_if_missing=True`; initializes schema; verifies version compatibility |
| `close()` | Closes `sqlite3.Connection` |
| `initialize_schema()` | Runs `schema_ddl_sqlite()` DDL, inserts version row |
| `insert_final_record(record, run_id=None)` | Inserts one authoritative final record; rejects missing `parameter_identity`; returns row ID |
| `query_by_parameter_key(key)` | Returns all rows matching key, newest first (inspection only, no reuse/warm-start) |
| `count_records()` | Count of all records |
| Context manager | `__enter__`/`__exit__` support |

### Schema version handling

| Scenario | Behaviour |
|----------|-----------|
| New DB + `create_if_missing=True` | Create schema, insert version row |
| Existing DB, version == expected | Open OK |
| Existing DB, version > expected | `ValueError`: newer than expected |
| Existing DB, version < expected | `ValueError`: older than expected, no migration |
| Missing `schema_version` table | `ValueError`: cannot determine compatibility |
| Empty file + `create_if_missing=True` | Initialize schema |

### DDL update

`evaluation_database_schema.py` `schema_ddl_sqlite()` updated:
- Added `schema_version` table (created first).
- Added `run_id TEXT` column to `evaluation_records`.
- Changed `CREATE INDEX` → `CREATE INDEX IF NOT EXISTS`.
- Comment updated from "Not executed" to reflect actual usage.

---

## Test coverage (29 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestResolveConfig` | 9 | none/missing/disabled/enabled, missing path, empty path, inside repo, outside repo, disabled no validation |
| `TestSchemaLifecycle` | 3 | create schema, version row, context manager |
| `TestSchemaVersionHandling` | 4 | version > rejects, version < rejects, missing version table rejects, empty file initializes |
| `TestInsertAndQuery` | 5 | insert SUCCESS, insert SOLVER_FAILED, read-back fields, query by key, duplicate appends |
| `TestInsertValidation` | 2 | missing identity rejects, diagnostics not in records |
| `TestDisabledConfig` | 3 | disabled config, no path validation, cannot instantiate with disabled |
| `TestNoReuseSemantics` | 1 | no reuse/warm-start query at startup |
| `TestSafety` | 2 | no CST imports, no raw `open()` in code |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short -v
→ 29 passed

# Full regression (472 existing tests)
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short → 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py --tb=short → 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py --tb=short → 28 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short → 50 passed
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short → 12 passed

Total: 501 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run |
| Runtime workflow integration | ❌ Not wired |
| Success reuse | ❌ Not implemented |
| DB warm-start | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| probably-infeasible skip | ❌ Not used |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/workflow.py` | **Not modified** |
| `workflows/rfgun_sao/run.py` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| `make_cst_retry_evaluate_once` | **Not modified** |
| `run_retry_loop_no_cst` | **Not modified** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | Temporary test files | **Not committed** |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
DDB2 rfgun_sao durable evaluation DB no-CST SQLite storage implementation

- New evaluation_database_storage.py: config resolver + SQLiteEvaluationDatabase
  with open/close/insert/query/count/context-manager support
- Schema DDL updated: schema_version table, run_id column, IF NOT EXISTS indexes
- Config: disabled by default; path required when enabled; inside-repo rejected
- Schema version: exact match required; >rejects, <rejects, missing rejects
- Insert: final authoritative records only; missing parameter_identity rejected
- 29 no-CST tests: config, schema, insert, query, version, safety
- 501 total tests pass (29 new + 472 existing)

No live CST, no runtime workflow integration, no reuse/warm-start/failure reuse,
no default config change.
```
