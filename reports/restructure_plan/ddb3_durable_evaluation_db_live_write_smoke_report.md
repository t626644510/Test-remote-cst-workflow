# DDB3 — Bounded live single-eval durable DB write smoke

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `e09596872b49e7578cc873d5db4ed78cccd043b9` |
| Phase label | `DDB3 — Bounded live single-eval durable DB write smoke` |
| Branch | `feature/wf1-durable-evaluation-db` |
| Live CST explicitly allowed | **Yes** — operator approved |
| Live CST run | **Yes** — bounded single-eval through root shim |
| Live CST status | **Passed** — evaluation completed, DB row written, no orphan DE |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added evaluation DB config resolution, `_write_eval_db()` helper, DB writes at final return points for retry-runtime and plain paths, DB stored on workflow |
| `workflows/rfgun_sao/run.py` | **Modified** | Added evaluation DB close in `_cleanup_workflow_connection` |
| `reports/restructure_plan/ddb3_durable_evaluation_db_live_write_smoke_report.md` | **Added** | This report |

---

## Runtime integration summary

### Config resolution

- `resolve_evaluation_database_config(config)` evaluates `evaluation_database.*` section.
- When disabled or absent → no DB created, no file touched, no behavior change.
- When enabled → `SQLiteEvaluationDatabase` opened, stored on `workflow._evaluation_db`.

### Write points

| Evaluator path | DB write source |
|----------------|-----------------|
| Retry runtime initial success | `EvaluationDatabaseRecord` built from initial `evaluate_single_pass` result |
| Retry runtime retry success | `retry_result.final_record` (pre-built by retry loop) |
| Plain single_pass | `EvaluationDatabaseRecord` built from `evaluate_single_pass` result |

### Non-fatal write

- All DB writes are wrapped in `try/except` with `_logger.warning`.
- DB write failure does not alter optimizer result, checkpoint, or cleanup behavior.
- Checkpoint remains authoritative.

### Cleanup

- `_cleanup_workflow_connection` in `run.py` calls `edb.close()` for `workflow._evaluation_db`.

---

## Live smoke config (local only, not committed)

```yaml
retry_runtime:
  enabled: false
evaluation_database:
  enabled: true
  path: D:/Results/workflow1/evaluation_ddb3_smoke.db
  create_if_missing: true
```

Legacy retry disabled, retry_runtime disabled, evaluation DB enabled.

---

## Live smoke results

### Command

```powershell
python run_workflow_1.py --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

### Evaluation

```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 5
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best F: [-76961.84]
CST cleanup: attempted=True closed=True pid=14684
```

### DB verification (post-run)

| Field | Record 1 | Record 2 |
|-------|----------|----------|
| `id` | 1 | 2 |
| `status` | `success` | `success` |
| `retry_count` | 0 | 0 |
| `run_id` | `17b4eab7` | `17b4eab7` |
| `parameter_key` | `0db7dda1c179b411` | `fc1a17281332fcbe` |
| `raw_metrics` | Present | Present |
| `objective_values` | Present | Present |

Both records were written with `status=success`, same `run_id`. The optimizer ran 2 evaluations (expected behavior with `n_initial=1` may produce multiple initial candidates).

### Log evidence

```
INFO  Evaluation DB enabled: path=D:\Results\workflow1\evaluation_ddb3_smoke.db run_id=17b4eab7
DEBUG Evaluation DB: written (id=1, status=success, key=0db7dda1)
DEBUG Evaluation DB: written (id=2, status=success, key=fc1a1728)
INFO  Workflow 1 completed. Best: OptimizationResult(...)
DEBUG Evaluation DB closed
```

### Cleanup

| Check | Result |
|-------|--------|
| Pre-run CST processes | Only `cstd.exe` PID 10184 |
| Post-run CST processes | Only `cstd.exe` PID 10184 |
| Orphan DE remaining? | ❌ None |
| Manual `taskkill` required? | ❌ No |
| Evaluation DB file | ✅ At `D:/Results/workflow1/evaluation_ddb3_smoke.db` (outside repo) |
| DB closed properly | ✅ `DEBUG Evaluation DB closed` |

---

## What was live-validated

| Capability | Validated? | Evidence |
|------------|-----------|----------|
| Real CST evaluation completed | ✅ | Best F finite, metrics computed |
| Final authoritative DB row written | ✅ | 2 records with status=success in DB |
| DB write did not affect optimizer | ✅ | Evaluation completed normally |
| DB closed in cleanup | ✅ | `DEBUG Evaluation DB closed` |
| No orphan DE | ✅ | Only `cstd.exe` remains |
| No manual cleanup | ✅ | Not required |

## What was NOT validated

| Capability | Status | Reason |
|------------|--------|--------|
| DB-backed success reuse | ❌ | Separate track |
| DB warm-start | ❌ | Separate track |
| Failure reuse | ❌ | Separate track |
| probably-infeasible skip | ❌ | Rejected at runtime |
| Production campaign | ❌ | Bounded single-eval only |
| Concurrent DB writers | ❌ | Single-writer assumption |
| Schema migrations beyond v1 | ❌ | Exact match required |

---

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short -v
→ 40 passed

# Full regression
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py → 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py → 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py → 28 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py → 50 passed
pytest tests/workflows/test_rfgun_sao_imports.py → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py → 12 passed

Total: 512 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST executed | ✅ Yes — bounded single-eval through root shim |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed (restored after smoke) |
| Generated artifacts committed | ❌ Not committed |
| Durable DB | ✅ Implemented and live-validated |
| Success reuse | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| probably-infeasible skip | ❌ Not used |
| DB file committed | ❌ Outside repo |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/retry_taxonomy.py` | **Not modified** |
| `workflows/rfgun_sao/retry_runtime.py` | **Not modified** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Modified for smoke, restored | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` | **Not committed** |
| `*.sqlite` / `*.db` | `D:/Results/workflow1/evaluation_ddb3_smoke.db` | **Not committed** (outside repo) |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` | **Not committed** |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` | **Not committed** |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
DDB3 rfgun_sao bounded live single-eval durable DB write smoke

- Wire evaluation DB into workflow.py: config resolution, final-record
  writes for retry-runtime and plain paths, non-fatal on failure
- DB cleanup in run.py: _cleanup_workflow_connection closes DB
- Live CST: single-eval completed, 2 DB records written with
  status=success, same run_id, no orphan DE
- 512 total tests pass

No success reuse, no warm-start, no failure reuse, no default config change.
```
