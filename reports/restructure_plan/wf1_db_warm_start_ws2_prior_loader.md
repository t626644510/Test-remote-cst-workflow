# WS2 -- DB prior loader / no-CST helper

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `e510ec3e7ab54424f627155a3a326996d04fbc4c` |
| Phase label | `WS2 -- DB prior loader / no-CST helper` |
| Branch | `feature/wf1-db-warm-start` |
| Live CST | **No** -- pure no-CST implementation |
| Optimizer wiring | **Not wired** -- prior loader only |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_database_warm_start.py` | **Modified** | Added `DbWarmStartConfig`, `DbWarmStartPrior`, `DbWarmStartLoadReport`, `resolve_db_warm_start_config()`, `load_warm_start_priors()`, helper utilities |
| `tests/workflows/test_rfgun_sao_db_warm_start_ws2.py` | **Added** | 29 no-CST tests |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | WS1 accepted, WS2 added |
| `reports/restructure_plan/wf1_db_warm_start_ws2_prior_loader.md` | **Added** | This report |

---

## Implementation summary

### Module: `evaluation_database_warm_start.py` (extended)

New WS2-specific dataclasses and functions added alongside the existing Phase L helpers.

#### `DbWarmStartConfig`

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `False` | Master switch |
| `max_priors` | `50` | Maximum prior observations |
| `order_by` | `"best_objective"` | `"best_objective"` or `"newest"` |
| `require_objective_values` | `True` | Reject rows without objective payload |
| `allow_raw_recompute` | `False` | Not implemented in WS2 |

#### `DbWarmStartPrior`

One prior observation with full objective values dict and computed scalar.

#### `DbWarmStartLoadReport`

Structured report with counts for: `found_rows`, `eligible_rows`, `accepted_priors`, `rejected_rows`, `skipped_duplicates`, `skipped_checkpoint_duplicates`, `capped`, `rejection_reasons`. Accepted priors stored in `diagnostics["priors"]`.

### Config resolver: `resolve_db_warm_start_config(config, db_enabled=False)`

| Scenario | Result |
|----------|--------|
| No `evaluation_database.warm_start` section | `enabled=False` |
| `warm_start.enabled=True` without DB | `ValueError` |
| `warm_start.enabled=True` with DB enabled | Resolved config |
| Invalid `order_by` | `ValueError` |
| Negative `max_priors` | `ValueError` |
| `evaluation_database.enabled` alone | Does NOT enable warm-start |
| `success_reuse.enabled` alone | Does NOT enable warm-start |

### Prior loader: `load_warm_start_priors(rows, config, ...) -> DbWarmStartLoadReport`

Accepts a list of DB row dicts (pre-fetched), applies eligibility checks, dedup, capping, and checkpoint dedup.

### Eligibility matrix

| Condition | Eligible? |
|-----------|-----------|
| `status == 'success'` | ✅ |
| Schema compatible | ✅ |
| Parameter key present | ✅ |
| Parameter names match | ✅ |
| Objective names match | ✅ |
| Objective values present (when `require_objective_values=True`) | ✅ |
| Failure/COM/gate/diagnostic | ❌ Rejected |
| Schema incompatible | ❌ Rejected |
| Missing parameter key/identity | ❌ Rejected |
| Objective/parameter names mismatch | ❌ Rejected |
| Raw-only (no objective_values) | ❌ Rejected (default) |

### Duplicate / capping policy

| Aspect | Policy |
|--------|--------|
| Duplicate parameter_key | First occurrence kept; subsequent skipped (counted in `skipped_duplicates`) |
| `order_by="best_objective"` | Sort by ascending scalar, then newest `created_at`, then highest `id` |
| `order_by="newest"` | Sort by descending `created_at`, then highest `id` |
| `max_priors` cap | Capped after ordering; `capped=True` in report |
| Checkpoint dedup | Optional `checkpoint_parameter_keys` set; matching keys skipped and counted |

### Scalar computation

The scalar for ordering is derived from `__retry_penalty__` in diagnostics (if present) or from the sum of `objective_values`. This matches the SR approach for consistency.

---

## Test coverage (29 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestResolveConfig` | 12 | None/missing/disabled config, DB required, invalid order_by, negative max_priors, zero max_priors, custom values, no cross-implied enable |
| `TestLoadPriors` | 15 | Empty rows, SUCCESS row, failure/gate/schema/param/objective rejection, missing key, missing objective_values, empty objective_values, duplicate dedup, capping, checkpoint dedup, ordering (newest, best_objective) |
| `TestSafety` | 2 | No CST imports, no JSONL reference |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_db_warm_start_ws2.py --tb=short -v
-- 29 passed

# Full regression (507 existing tests)
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short -- 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short -- 12 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short -- 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short -- 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py --tb=short -- 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py --tb=short -- 28 passed
pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short -- 35 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short -- 40 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_workflow.py --tb=short -- 10 passed

Total: 536 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | **No** |
| Optimizer runtime wiring | **Not implemented** |
| Evaluator runtime wiring | **Not implemented** |
| Default config changed | **Not changed** |
| `config.local.yaml` committed | **Not committed** |
| Generated artifacts committed | **Not committed** |
| DB warm-start prior loader | **Implemented and tested** |
| JSONL sidecar as warm-start source | **Not used** (verified) |
| Failure rows as priors | **Rejected** |
| probably-infeasible skip | **Not used** |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `workflows/rfgun_sao/workflow.py` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |

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
feat(wf1): add DB warm-start prior loader WS2

- DbWarmStartConfig: enabled/max_priors/order_by/require_objective_values
- DbWarmStartPrior: full objective values dict + scalar + provenance
- DbWarmStartLoadReport: structured rejection counts
- resolve_db_warm_start_config: no cross-implied enable
- load_warm_start_priors: eligibility, dedup, capping, checkpoint dedup
- 29 no-CST tests: config, eligibility, rejection, ordering, safety
- 536 total tests pass

No optimizer wiring, no evaluator wiring, no live CST.
```
