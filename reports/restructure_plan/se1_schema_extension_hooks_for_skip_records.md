# SE1 — schema extension hooks for failure skip records

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `SE1 — schema extension hooks for failure skip records` |
| Base commit | `bd682845ccd065de6ed0e9e816541e592258c855` (FS4 accepted) |
| Branch | `feature/wf1-failure-skip` |
| Live CST | **No** |
| Real runtime wiring | **No** |
| Production DB migration | **No** |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_database_skip_records.py` | **Added** | Extended status helpers, skip payload model, DB field mapping, schema capability |
| `tests/workflows/test_rfgun_sao_evaluation_database_schema_extension.py` | **Added** | 29 no-CST tests |
| `reports/restructure_plan/se1_schema_extension_hooks_for_skip_records.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | SE1 phase |

---

## Status extension approach

**Option A (adapter-only)** — chosen for SE1.

| Decision | Rationale |
|----------|-----------|
| v1 `EvaluationDatabaseStatus.validate()` not modified | Closed set remains stable; v1 storage, success reuse, and warm-start unaffected |
| Extension statuses defined in separate module | No risk of accidentally validating custom statuses through v1 paths |
| All tests confirm v1 validation rejects skip statuses | Proven isolation |
| Production migration (SE2) required before DB insert | Clear boundary between design and implementation |

---

## Skip statuses defined

| Status | Constant | Reusable? | Warm-start eligible? | Evidence source? |
|--------|----------|-----------|---------------------|-----------------|
| `skipped_failure_reuse` | `SKIPPED_FAILURE_REUSE` | No | No | No |
| `skipped_probably_infeasible` | `SKIPPED_PROBABLY_INFEASIBLE` | No | No | No |
| `success` (v1) | N/A | Yes | Yes | No |

---

## Skip payload model

| Field | Type | Required? | Description |
|-------|------|-----------|-------------|
| `record_kind` | str | Yes | `"skip"` |
| `status` | str | Yes | One of the skip statuses |
| `parameter_key` | str | Yes | Skipped parameter key |
| `skip_policy_version` | int | Yes | Policy version |
| `skip_mode` | str | Yes | `"enforce"` |
| `skip_decision` | str | Yes | `"enforced_skip"` |
| `skip_reason` | str | Yes | Human-readable |
| `source_row_ids` | tuple[int] | Yes | Evidence row IDs |
| `source_run_ids` | tuple[str] | Optional | Evidence run IDs |
| `evidence_count` | int | Yes | Count of evidence rows |
| `evaluator_called` | bool | Yes | Must be `False` |
| `retry_called` | bool | Yes | Must be `False` |
| `budget_consumed` | bool | Yes | Must be `False` |
| `environment_fault_flag` | bool | Yes | Must be `False` |
| `operator_override_id` | str | Optional | Manual override |
| `extra_json` | Mapping | Optional | Extension data |

---

## DB field mapping

| Target field | Source |
|-------------|--------|
| `status` | payload.status |
| `source` | `"failure_skip_enforce"` |
| `diagnostics` | Skip audit fields (record_kind, policy_version, etc.) |
| `error_taxonomy` | failure_taxonomy_version, environment_fault_flag |
| `provenance` | operator_override_id, extra |
| `raw_metrics` | `None` (no fabricated SUCCESS) |
| `objective_values` | `None` (no fabricated SUCCESS) |

---

## Schema capability result (v1)

| Capability | v1 Status |
|------------|-----------|
| `supports_skip_statuses` | **False** — `validate()` rejects custom statuses |
| `supports_skip_audit_fields` | **True** — diagnostics/error_taxonomy fields exist |
| `supports_extra_json` | **True** — provenance field exists |
| `requires_migration_for_skip_rows` | **True** — SE2 required before DB insert |

---

## Synthetic DB insert status

**Deferred** — SE1 does not implement DB insertion.  SE2 (or FS4.1) must:
1. Extend `EvaluationDatabaseStatus._VALID_STATUSES` or replace `validate()`
2. Add skip-audit fields to the DDL if needed
3. Implement `write_failure_skip_synthetic_row()` helper

---

## Success reuse / warm-start compatibility

| Status | Reusable? | Tested? |
|--------|-----------|---------|
| `success` | Yes | v1 tests pass |
| `skipped_failure_reuse` | **No** | SE1 tests confirm `is_reusable_success_status()` returns False |
| `skipped_probably_infeasible` | **No** | SE1 tests confirm |
| v1 validation rejects skip statuses | N/A | Test confirms `ValueError` raised |

No changes to success_reuse or warm-start loaders are required — both check `status == "success"` and would ignore any skip row.

---

## Tests added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestStatusHelpers` | 10 | Success reusable, skip not reusable, recognized, extended, failure evidence source |
| `TestPayloadValidation` | 7 | Valid, missing key, missing source IDs, environment flag warning, evaluator/retry must be false, invalid status |
| `TestDBFieldMapping` | 4 | Status/source mapping, diagnostics mapping, error_taxonomy mapping, no fabricated metrics |
| `TestSchemaCapability` | 4 | v1 requires migration, v1 rejects skip status, v1 accepts success, unknown version conservative |
| `TestGlobalSafety` | 4 | No subprocess, no os.system, no taskkill, no CST import |

**Total: 29 tests**

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_evaluation_database_schema_extension.py --tb=short
-- 29 passed

# Full failure_skip regression (FS2 + FS3 + FS4)
pytest tests/workflows/test_rfgun_sao_failure_skip_candidates.py --tb=short
-- 48 passed
pytest tests/workflows/test_rfgun_sao_failure_skip_dry_run.py --tb=short
-- 23 passed
pytest tests/workflows/test_rfgun_sao_failure_skip_enforce.py --tb=short
-- 18 passed

# Cross-track regression
pytest tests/workflows/test_rfgun_sao_extreme_recovery_safety.py --tb=short
-- 58 passed

# Core imports
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
-- 230 passed, 1 warning
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
-- 12 passed
```

### Safety grep

No `taskkill`/`Stop-Process`/`subprocess`/`os.system` in helper or tests.

### Artifact check

No forbidden artifacts tracked. No generated artifacts committed.

---

## Explicit statements

| Item | Status |
|------|--------|
| Live CST | **No** |
| Real runtime wiring | **No** |
| Production DB migration | **No** |
| Default config changed | **No** |
| Generated artifacts committed | **No** |
| Skip statuses remain non-success | **Yes** |
| Success reuse cannot consume skip rows | **Yes** (verified) |
| Warm-start cannot consume skip rows | **Yes** (verified) |

---

## Recommended next phase

**SE2 — storage migration / synthetic DB insert helper**.  Extend
`EvaluationDatabaseStatus` validation to accept skip statuses, and
implement `write_failure_skip_synthetic_row()` for the durable DB.

Then **FS5 — bounded live exact-key skip smoke** only after explicit
operator approval and adequate DB recording.
