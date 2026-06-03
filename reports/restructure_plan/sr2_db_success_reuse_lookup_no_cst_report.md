# SR2 — DB-backed success reuse lookup helper, no-CST only

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `ffa6a4bdd17eda515a4911d074f272a4ef56a861` |
| Phase label | `SR2 — DB-backed success reuse lookup helper, no-CST only` |
| Branch | `feature/wf1-db-success-reuse` |
| Live CST | **No** — pure no-CST implementation |
| Runtime skip | **Not wired** — lookup helper only |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_success_reuse.py` | **Added** | Config resolver, lookup helper, reconstruction helper |
| `tests/workflows/test_rfgun_sao_evaluation_success_reuse.py` | **Added** | 30 no-CST tests |
| `reports/restructure_plan/sr2_db_success_reuse_lookup_no_cst_report.md` | **Added** | This report |

---

## Implementation summary

### Module: `evaluation_success_reuse.py`

| Component | Description |
|-----------|-------------|
| `SuccessReuseConfig` | Dataclass: `enabled`, `require_objective_values`, `allow_raw_recompute`, `max_age_days`, `log_decisions` |
| `resolve_success_reuse_config(config, db_enabled=False)` | Requires DB enabled; raises `ValueError` if reuse enabled without DB |
| `find_eligible_success_record(db, pid, metric_names, config, ...)` | Read-only lookup; returns selected DB row dict or `None` |
| `reconstruct_evaluation_result(row, metric_names, ...)` | Builds `EvaluationResult` from DB row with reuse provenance |

### Lookup eligibility (12 checks)

| Check | Rejects? |
|-------|----------|
| `config.enabled` is False | None returned |
| `parameter_identity` is None | None returned |
| `status != 'success'` (solver_failed, gate_rejected, unknown_failed, diagnostic_only) | Skipped |
| `schema_version != current_schema_version()` | Skipped |
| `param_names` mismatch (count or names) | Skipped |
| `objective_names` mismatch vs `metric_names` | Skipped |
| Missing `objective_values` when `require_objective_values=True` | Skipped |
| No payload at all when `require_objective_values=False` | Skipped |
| `allow_raw_recompute=False` + no `objective_values` | Skipped |

### Tie-breaking

`ORDER BY created_at DESC, id DESC` — newest creation time, then highest ID. Deterministic. Selected row is logged at INFO level.

### Reconstruction

- `EvaluationResult(SUCCESS)` from DB row.
- `raw_metrics`, `objective_values`, `penalty_values` from row (with JSON parsing).
- `penalty_values` priority: `__retry_penalty__` in diagnostics → `objective_values` fallback.
- Diagnostics enriched with: `reused_from_db=True`, `source_row_id`, `source_run_id`, `source_created_at`.

---

## Test coverage (30 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestResolveConfig` | 6 | Config disabled/enabled, DB requirement, defaults |
| `TestLookupDisabled` | 2 | Disabled returns None, no DB query |
| `TestLookupEligibility` | 13 | Exact match, different key, failure/gate/unknown ignored, schema mismatch, missing identity, missing objective_values, raw-only accepted with require_obj=false, param/objective names mismatch, diagnostic_only ignored |
| `TestLookupTieBreaking` | 2 | Newest created_at, highest id when same time |
| `TestReconstruction` | 5 | Basic reconstruction, penalty from diagnostics, penalty fallback, SUCCESS status, reuse provenance, f0_ghz |
| `TestSafety` | 2 | No CST import, no JSONL reference |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short -v
→ 30 passed

# Full regression
pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py → 40 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_workflow.py → 10 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime.py → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py → 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py → 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py → 28 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py → 50 passed
pytest tests/workflows/test_rfgun_sao_imports.py → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py → 12 passed

Total: 502 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run |
| Runtime skip wired | ❌ Not wired |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| DB-backed success reuse implemented | ⏳ Lookup helper only; runtime skip = SR3 |
| Warm-start | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| probably-infeasible skip | ❌ Not used |
| JSONL sidecar as reuse source | ❌ Not used |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_sao/workflow.py` | **Not modified** |
| `workflows/rfgun_sao/run.py` | **Not modified** |
| `workflows/rfgun_single_pass/` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
SR2 rfgun_sao DB-backed success reuse lookup helper, no-CST only

- New evaluation_success_reuse.py: config resolver, lookup helper,
  reconstruction helper
- Eligibility: SUCCESS rows only, matching parameter_key, compatible
  schema, usable payload, matching objective/param names
- Tie-breaking: newest created_at, then highest id (deterministic)
- Reconstruction: EvaluationResult from DB row with reuse provenance
- 30 no-CST tests covering config, lookup, tie-breaking, reconstruction,
  safety
- 502 total tests pass

No runtime skip, no live CST, no default config change.
```
