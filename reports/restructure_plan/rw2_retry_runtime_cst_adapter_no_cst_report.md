# RW2 — Retry runtime CST adapter no-CST implementation

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `29a1eb0ae71793cec66ebeccf61ae75e3b6c5ce0` |
| Phase label | `RW2 — Retry runtime CST adapter no-CST implementation` |
| Branch | `feature/wf1-retry-runtime-cst-wiring` |
| Live CST | **No** — pure no-CST implementation |
| Runtime code changed | **Yes** — new `retry_runtime_cst.py` module |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/retry_runtime_cst.py` | **Added** | Adapter module: status mapper, record builder, evaluate_once factory, legacy retry mutex checker |
| `tests/workflows/test_rfgun_sao_retry_runtime_cst.py` | **Added** | 34 no-CST tests covering all scenarios |
| `reports/restructure_plan/rw2_retry_runtime_cst_adapter_no_cst_report.md` | **Added** | This report |

---

## Implementation summary

### Module: `workflows/rfgun_sao/retry_runtime_cst.py`

Four public helpers:

| Function | Description |
|----------|-------------|
| `map_evaluation_status_to_database_status(status)` | Maps legacy `EvaluationStatus` to `EvaluationDatabaseStatus` string for taxonomy consumption |
| `build_record_from_evaluation_result(pid, result, ...)` | Constructs an `EvaluationDatabaseRecord` from an `EvaluationResult`, including metrics, error taxonomy, and retry count |
| `make_cst_retry_evaluate_once(evaluator, ...)` | Factory that returns an `evaluate_once(tier, record)` callback compatible with `run_retry_loop_no_cst()` |
| `check_legacy_retry_mutex(config)` | Detects if legacy `optimization.retry.enabled` conflicts with new `retry_runtime.enabled`; disables new runtime with diagnostic |

### Key design decisions

1. **No-CST at module level**: The module contains zero CST imports. CST objects are injected via the `evaluator` parameter (duck-typed to `Workflow1Evaluator`). Tests use `FakeCstEvaluator`.

2. **Status mapping**:
   - `COM_LOST` → `TRANSIENT_FAILED` (encourages retry; connection loss is transient)
   - `SOLVER_FAILED` → `SOLVER_FAILED` (retry-eligible under default policy)
   - `PHYSICS_INVALID` → `SOLVER_FAILED` (treated as solver failure)
   - `UNKNOWN_ERROR` → `UNKNOWN_FAILED` (retry-eligible when `allow_unknown_retry=True`)

3. **Record builder**: Preserves raw_metrics, objective_values, diagnostics, and error details from the evaluator result. The record's `retry_count` is set to `previous + 1` so the taxonomy sees progress.

4. **Adapter factory**: `make_cst_retry_evaluate_once` wraps `evaluator.adapt_for_retry()`. It extracts parameter identity from the `EvaluationDatabaseRecord` passed to each `evaluate_once` call and converts the result back into a record.

5. **Legacy retry mutex**: `check_legacy_retry_mutex()` reads the config and returns a disabled `RetryRuntimeConfig` if legacy retry is also enabled. A diagnostic message explains the conflict and how to resolve it. No silent double retry.

---

## Test coverage (34 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestMapStatus` | 5 | All EvaluationStatus → database status mappings |
| `TestBuildRecord` | 6 | SUCCESS with metrics, failure with error_taxonomy, COM_LOST→transient, None identity preserved, retry_count passthrough, no-metrics no-crash |
| `TestCstRetryEvaluateOnce` | 7 | SUCCESS no retry, SOLVER_FAILED→retry→SUCCESS, COM_LOST→retry→SUCCESS, max_tier exhaust (not skipped), gate_rejected no retry, unknown_failed retry, recovery callback called |
| `TestCstRetryRecovery` | 2 | Recovery callback called on correct tier, recovery exception captured and bounded |
| `TestProbablyInfeasibleGuard` | 1 | `use_probably_infeasible_for_skip=True` rejected before evaluate_once |
| `TestLegacyRetryMutex` | 6 | No config, no section, retry_runtime disabled, no legacy, mutex triggers, no legacy section, legacy enabled default |
| `TestAdapterTaxonomyIntegration` | 3 | Adapter output classifies correctly via taxonomy, success no retry, max_tier not probably-infeasible |
| `TestSafety` | 4 | No CST imports, no factory, no recovery import, no file I/O |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short -v
→ 34 passed

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
→ 230 passed

pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
→ 12 passed

pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short
→ 83 passed

pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
→ 50 passed

Total: 409 passed, 1 pre-existing warning.
```

No regressions. Existing retry runtime (83), taxonomy (50), and import (242) tests all pass.

---

## Design conformance

| RW1 design element | Implemented? | Notes |
|--------------------|-------------|-------|
| Status mapping | ✅ | `map_evaluation_status_to_database_status()` |
| Record builder | ✅ | `build_record_from_evaluation_result()` |
| Adapter factory | ✅ | `make_cst_retry_evaluate_once()` |
| Fake evaluator | ✅ | `FakeCstEvaluator` in tests |
| Legacy retry mutex | ✅ | `check_legacy_retry_mutex()` |
| No double retry | ✅ | Mutex disables new runtime if legacy enabled |
| "Skipped" → terminal failure | ✅ | All tests use `no_retry_max_tiers_reached` |
| JSONL/checkpoint in adapter | ❌ | Not in scope for RW2; adapter exposes records for future wiring |

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Rejected at runtime |
| Phase O/O1 retry runtime CST wiring | ⏳ Adapter created; live wiring = RW3 |
| Optimizer/runtime warm-start injection | ❌ Not implemented |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/retry_runtime.py` | **Not modified** |
| `workflows/rfgun_sao/retry_taxonomy.py` | **Not modified** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## RW2.1 correction note

This section documents changes made in RW2.1 (docs/code/test no-CST polish).

| Item | What changed |
|------|-------------|
| Nature | Docs/code/test no-CST polish — no runtime code changed, no config changed, no live CST |
| 1. No-retry test semantics | Added `test_initial_success_no_retry`: initial record = SUCCESS, asserts `len(result.attempts) == 0` and `call_count == 0`. Renamed old test to `test_failed_initial_retry_succeeds` |
| 2. Recovery callback ownership | Removed `recovery_callback` parameter from `make_cst_retry_evaluate_once`. Recovery belongs to `run_retry_loop_no_cst()`; adapter only evaluates one attempt. Updated docstring and all call sites |
| 3. Import cleanup | Replaced `__import__("numpy")` with top-level `import numpy as np`. Removed unused `param_dict` variable from `_evaluate_once`. Replaced `__import__` in `check_legacy_retry_mutex` with direct `resolve_retry_runtime_config` import |
| Test count | 35 (was 34) — one new true-initial-SUCCESS test |
| Total validation | 410 passed (35 CST adapter + 375 existing) |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
RW2 rfgun_sao retry runtime CST adapter no-CST implementation

- New retry_runtime_cst.py module: status mapper, record builder,
  evaluate_once adapter factory, legacy retry mutex checker
- Fully no-CST testable via FakeCstEvaluator duck-typing
- 34 no-CST tests covering all retry scenarios, recovery callback,
  mutex, taxonomy integration, and safety
- 409 total tests pass (no regression)
- Legacy retry mutex prevents silent double retry (fail-fast)
- use_probably_infeasible_for_skip still rejected at runtime

No live CST, no default config changes, no durable DB,
no failure reuse.
```
