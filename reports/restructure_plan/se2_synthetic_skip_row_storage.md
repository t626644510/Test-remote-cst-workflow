# SE2 — synthetic skip row storage support / temp DB insert helper

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `SE2 — synthetic skip row storage support / temp DB insert helper` |
| Base commit | `b73ca3457b060c869710839ede83234b8bf43777` (SE1.1 accepted) |
| Branch | `feature/wf1-failure-skip` |
| Live CST | **No** |
| Real runtime wiring | **No** |
| Production DB migration | **No** |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_database_schema.py` | **Modified** | Extended `_VALID_STATUSES` to include skip statuses |
| `workflows/rfgun_sao/evaluation_database_skip_records.py` | **Modified** | Updated schema capability (`supports_skip_statuses=True`, `requires_migration=False` for v1) |
| `workflows/rfgun_sao/evaluation_database_skip_storage.py` | **Added** | Synthetic skip row writer + decision-to-payload bridge |
| `workflows/rfgun_sao/failure_skip_candidates.py` | **Modified** | `classify_failure_skip_evidence` excludes skip statuses; loader excludes skip rows from evidence |
| `tests/workflows/test_rfgun_sao_evaluation_database_skip_storage.py` | **Added** | 25 tests (status, write, read-back, decision bridge, exclusion, safety) |
| `tests/workflows/test_rfgun_sao_evaluation_database_schema_extension.py` | **Modified** | Updated capability tests for SE2 changes |
| `reports/restructure_plan/se2_synthetic_skip_row_storage.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | SE2 phase |

---

## Implementation approach

**Option A (status validation extension)** — chosen for SE2.

| Decision | Rationale |
|----------|-----------|
| Extended `EvaluationDatabaseStatus._VALID_STATUSES` | Minimal change, backward-compatible |
| No DDL changes needed | v1 schema already has `status` as TEXT column |
| All existing loaders check `== "success"` | Skip rows safely ignored without code changes |
| Schema capability updated | v1: `supports_skip_statuses=True`, `requires_migration=False` |

---

## Schema capability result (v1 after SE2)

| Capability | Status |
|------------|--------|
| `supports_skip_statuses` | **True** — validation accepts `skipped_failure_reuse`, `skipped_probably_infeasible` |
| `requires_migration_for_skip_rows` | **False** — no DDL migration required |
| `supports_skip_audit_fields` | **True** |
| `supports_extra_json` | **True** |

---

## Synthetic row writer API

| API | Description |
|-----|-------------|
| `write_failure_skip_synthetic_row()` | Validates payload, writes one row to evaluation_records. Returns row ID. |
| `build_skip_payload_from_enforce_decision()` | Builds a validated payload from an FS4 enforce decision. |

### DB fields written

| Field | Value |
|-------|-------|
| `status` | `skipped_failure_reuse` or `skipped_probably_infeasible` |
| `source` | `failure_skip_enforce` |
| `diagnostics` | Full audit: record_kind, policy_version, mode, decision, reason, source_row_ids, evidence_count, evaluator/retry/budget flags |
| `error_taxonomy` | failure_taxonomy_version, environment_fault_flag |
| `provenance` | operator_override_id, extra |
| `raw_metrics` | `None` (no fabricated SUCCESS) |
| `objective_values` | `None` (no fabricated SUCCESS) |

---

## Success reuse / warm-start / evidence exclusion

| Loader | Skip row consumed? | Reason |
|--------|-------------------|--------|
| Success reuse | **No** | Only accepts `status == "success"` |
| Warm-start prior loader | **No** | Only accepts `status == "success"` |
| Failure skip candidate loader | **No** | Explicitly excluded in classifier + loader loop |

---

## Tests added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestStatusValidation` | 4 | Skip statuses validate, v1 success validates, invalid rejected, capability updated |
| `TestSyntheticRowWrite` | 6 | Valid payload writes, invalid raises, zero rows on error, status/source, diagnostics, no fabricated metrics |
| `TestReadBack` | 5 | Row readable, is_skip_status, not reusable, not warm-start eligible, not evidence source |
| `TestDecisionToPayload` | 3 | Enforce builds valid payload, non-enforce raises, no source rows raises |
| `TestExclusion` | 3 | Candidate loader ignores skip row, success reuse ignores, mixed skip+success rows |
| `TestGlobalSafety` | 4 | No subprocess, no os.system, no taskkill, no CST import |

**Total: 25 tests**

---

## Validation

All regressions pass: 600 total tests across 13 suites.

---

## Explicit statements

| Item | Status |
|------|--------|
| Live CST | **No** |
| Real runtime wiring | **No** |
| Production DB migration | **No** |
| Default config changed | **No** |
| Generated artifacts committed | **No** |
| Skip statuses accepted by v1 validation | **Yes** |
| Success reuse cannot consume skip rows | **Yes** |
| Warm-start cannot consume skip rows | **Yes** |
| Candidate loader excludes skip rows | **Yes** |

---

## Recommended next phase

**FS5 — bounded live exact-key skip smoke** only with explicit operator approval.
SE2 has made synthetic skip row storage viable without DDL migration.
