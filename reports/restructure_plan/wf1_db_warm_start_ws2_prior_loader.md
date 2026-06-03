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

Duplicate parameter_key is resolved **per key before final capping**, not first-occurrence:

| Aspect | Policy |
|--------|--------|
| `order_by="best_objective"` | Keep lowest scalar, tie-break newer `created_at`, then higher row `id` |
| `order_by="newest"` | Keep newest `created_at`, tie-break higher row `id` |
| `skipped_duplicates` | Counts discarded same-key rows during per-key dedup |
| `max_priors=0` | Means **no priors accepted** (not unlimited). Loader returns empty report. |
| `config.enabled=False` | Means no priors loaded regardless of rows. |
| `max_priors` cap | Applied after ordering; `capped=True` in report |
| Checkpoint dedup | Optional `checkpoint_parameter_keys` set; matching keys skipped and counted |
| `allow_raw_recompute=True` | Raises `ValueError` in WS2 (raw recompute not implemented) |

### Scalar computation

The scalar for ordering is derived from `__retry_penalty__` in diagnostics (if present) or from the sum of `objective_values`. This matches the SR approach for consistency.

---

## Test coverage (45 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestResolveConfig` | 12 | None/missing/disabled config, DB required, invalid order_by, negative/zero max_priors, custom values, no cross-implied enable, allow_raw_recompute rejection |
| `TestLoadPriors` | 15 | Empty rows, SUCCESS row, failure/gate/schema/param/objective rejection, missing key, missing objective_values, empty objective_values, duplicate dedup, capping, checkpoint dedup, ordering (newest, best_objective) |
| `TestDisabledConfig` | 1 | Disabled config returns empty report |
| `TestMaxPriorsZero` | 2 | Resolver accepts 0; loader returns no priors |
| `TestDuplicateHardening` | 4 | Worse-first best-wins, same scalar newer wins, same timestamp higher id wins, newest mode keeps newest |
| `TestParamIdentityHardening` | 4 | Missing values, wrong length, non-numeric, key mismatch |
| `TestObjectiveHardening` | 4 | Missing keys, non-numeric values, NaN, inf |
| `TestAllowRawRecompute` | 1 | `allow_raw_recompute=True` raises ValueError |
| `TestSafety` | 2 | No CST imports, no JSONL reference |

### WS2.1 hardening additions (16 tests)

| Area | Tests | What it validates |
|------|-------|-------------------|
| Disabled config | 1 | Empty report when `config.enabled=False` |
| `max_priors=0` | 2 | Resolver accepts; loader returns empty |
| Duplicate tie-break | 4 | Per-key best selection with correct scalar/created_at/id ordering |
| Param identity | 4 | Missing/wrong-length/non-numeric param_values, key mismatch |
| Objective payload | 4 | Missing keys, non-numeric values, NaN, inf rejection |
| `allow_raw_recompute` | 1 | Raises `ValueError` in WS2 |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_db_warm_start_ws2.py --tb=short -v
-- 45 passed

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

Total: 552 passed, 1 pre-existing warning.
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
