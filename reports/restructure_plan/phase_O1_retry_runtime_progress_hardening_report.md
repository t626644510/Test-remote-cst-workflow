# Phase O1 — Retry runtime no-CST progress hardening

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `9dcbadf48115dada9d494ec217a22554c330c038` |
| Previous Phase O HEAD (reviewed, not accepted) | `8901383b8694e7e3a01ea16e0cf0547c5dd9478d` |
| Phase label | `Phase O1 — Retry runtime no-CST progress hardening` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST | **No** |
| Durable DB | **No** |
| Failure reuse | **No** |
| JSONL sidecar read | **No** |
| Root shim repoint | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/retry_runtime.py` | **Modified** | Added `_normalize_retry_record()` helper, internal `attempts_consumed` progress guard, updated `retry_count_consumed` semantics |
| `tests/workflows/test_rfgun_sao_retry_runtime.py` | **Modified** | Added 23 new tests (5 `TestNormalizeRetryRecord`, 4 `TestRetryLoopProgressSameFailure`, 2 `TestRetryLoopProgressLowerRetryCount`, 4 `TestRetryLoopProgressTerminalAfterRetry`, 2 `TestRetryLoopProgressSuccess`, 2 `TestRetryLoopProgressRecovery`, 3 `TestO1Safety`, 1 `test_probably_infeasible_still_rejected_before_evaluate`) |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | Phase O status changed to "Needs O1 retry progress hardening"; Phase O1 row added; next directions updated |
| `reports/restructure_plan/phase_O1_retry_runtime_progress_hardening_report.md` | **Added** | This report |

---

## Summary of changes

### Blocking issue addressed

The retry loop in `run_retry_loop_no_cst()` had **no progress guard**. If the injectable `evaluate_once()` callback returned a retryable failed record without advancing `retry_count`, the loop would classify the same record identically each iteration and retry infinitely at the same tier.

**O1 fix** provides two independent termination guarantees:

1. **Record normalisation** (`_normalize_retry_record`): After each `evaluate_once()` call, if the returned record is not SUCCESS and its `retry_count` has not advanced past the previous record's `retry_count`, a shallow copy is created with `retry_count = previous + 1`. This ensures `classify_retry_eligibility()` sees monotonic progress and eventually returns `NO_RETRY_MAX_TIERS_REACHED`.

2. **Internal attempts counter** (`attempts_consumed`): An independent counter (`attempts_consumed`) tracks the number of `evaluate_once()` calls. Before each retry, the loop checks `attempts_consumed >= config.max_tier` and stops if so, providing a defence-in-depth bound even if normalisation were bypassed.

### Implementation details

#### `_normalize_retry_record()` helper

```python
def _normalize_retry_record(
    record: EvaluationDatabaseRecord,
    previous_retry_count: int,
) -> tuple[EvaluationDatabaseRecord, dict[str, Any]]:
```

- **SUCCESS passthrough**: Records with `status == SUCCESS` are returned as-is (the classifier handles them).
- **Already advanced**: If `record.retry_count > previous_retry_count`, no change needed.
- **Same/lower retry_count**: A shallow copy is created with `retry_count = previous_retry_count + 1`. A diagnostic dict (`retry_count_advanced=True`, `retry_count_before`, `retry_count_after`) is returned alongside the record.
- Preserves all other fields: `parameter_identity`, `status`, `raw_payload`, `objective_names`, `source`, `provenance`, `schema_version`, `error_taxonomy`.

#### Loop control flow with progress guard

```
run_retry_loop_no_cst():
  ...
  attempts_consumed = 0

  while True:
    eligibility = classify_retry_eligibility(current, ...)

    if SUCCESS → stop
    if terminal (gate_rejected, diagnostic_only, ...) → stop
    if RETRY_ELIGIBLE:
      if attempts_consumed >= config.max_tier:   # ← O1 internal guard
        stop with diagnostic "internal_max_tier_guard_fired"

      prev_retry = current.retry_count            # ← O1: capture baseline
      next_record = evaluate_once(tier, current)  # or exception handler
      attempts_consumed += 1                      # ← O1: internal counter

      current, norm_diag = _normalize_retry_record(next_record, prev_retry)
                                                   # ← O1: ensure progress
      if norm_diag:
        attempt_record.diagnostics.update(norm_diag)
        result.diagnostics["progress_guard_activations"].append(...)
      continue
```

#### `retry_count_consumed` semantics

Updated to `max(current.retry_count, attempts_consumed)`:
- `current.retry_count` reflects the final record's retry count (may have been normalised).
- `attempts_consumed` reflects the total number of `evaluate_once()` calls made.
- The max of the two is a conservative measure of retry progress.

---

## Retry progress semantics

### Guaranteed termination

The loop now terminates within `max_tier` retry attempts for any `evaluate_once()` return value:

| Scenario | Behaviour |
|----------|-----------|
| `evaluate_once` correctly increments `retry_count` | Works as before; normalisation is a no-op |
| `evaluate_once` returns same `retry_count` repeatedly | Normalisation advances by 1 each time; stops at `max_tier` |
| `evaluate_once` returns **lower** `retry_count` | Normalisation advances to `previous + 1`; stops at `max_tier` |
| `evaluate_once` raises exception | Exception handler creates record with `retry_count = prev + 1`; normalisation is no-op |
| Recovery callback exception + same failure | Recovery exception captured in attempt record; normalisation still advances; loop terminates |
| `evaluate_once` returns SUCCESS with unchanged `retry_count` | SUCCESS passthrough; loop stops immediately |
| `evaluate_once` returns terminal status (gate_rejected, diagnostic_only, etc.) | Classifier handles before retry_count matters; loop stops |

### Progress guard diagnostics

When normalisation activates, the following diagnostics are recorded:

- `attempt_record.diagnostics["retry_count_advanced"] = True`
- `attempt_record.diagnostics["retry_count_before"] = <original value>`
- `attempt_record.diagnostics["retry_count_after"] = <normalised value>`
- `result.diagnostics["progress_guard_activations"]` — list of all activations with attempt index and details

---

## Validation commands and results

All commands run from repository root (`c:\Users\lau\cst_ver3`):

```powershell
# 1. Compile check
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
```
→ Compiles OK.

```powershell
# 2. Retry runtime tests (Phase O + O1)
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short -v
```
→ **83 passed** (60 Phase O + 23 Phase O1).

```powershell
# 3. Retry taxonomy tests
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
```
→ **50 passed**.

```powershell
# 4. Warm-start tests
pytest tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py --tb=short
```
→ **23 passed**.

```powershell
# 5. Dedup tests
pytest tests/workflows/test_rfgun_sao_evaluation_database_dedup.py --tb=short
```
→ **9 passed**.

```powershell
# 6. Schema tests
pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short
```
→ **7 passed**.

```powershell
# 7. rfgun_sao imports
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```
→ **192 passed**.

```powershell
# 8. rfgun_single_pass imports
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
```
→ **9 passed**.

**Total: 354 passed, 1 pre-existing warning.**

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/retry_taxonomy.py` | **Not modified** |
| Root shim | **Not repointed** |

---

## Feature completion checklist

| Feature | Status | Notes |
|---------|--------|-------|
| Live CST | **No** | Pure no-CST skeleton |
| Runtime CST retry | **No** | No CST-backed evaluation |
| Runtime CST recovery | **No** | Callback-only skeleton |
| Durable DB append/lookup | **No** | No file I/O |
| Failure reuse | **No** | Not implemented |
| JSONL sidecar read/reference | **No** | Verified by safety tests |
| Optimizer/runtime warm-start injection | **No** | Not implemented |
| Inter-pass recovery (real CST) | **No** | Callback-only skeleton |
| Post-eval recovery (real CST) | **No** | Callback-only skeleton |
| probably-infeasible as skip | **No** | Rejected at runtime |
| Internal progress guard | **Yes** | `attempts_consumed` counter + `_normalize_retry_record` |
| Progress guard diagnostics | **Yes** | `progress_guard_activations` list in result |

---

## Artifacts check

| Artifact type | Present in commit | Verification |
|---------------|-------------------|--------------|
| `config.local.yaml` | **No** | Not committed |
| `*.jsonl` | **No** | Not generated |
| `*.ckpt` | **No** | Not generated |
| `*.sqlite` / `*.db` | **No** | Not generated |
| Logs | **No** | Not generated |
| CST output dirs | **No** | Not generated |
| Temporary scripts | **No** | Not committed |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** Expected to be the commit that includes the changes listed in the Files changed section above.

---

## Commit message proposal

```
Phase O1 rfgun_sao retry runtime no-CST progress hardening

- _normalize_retry_record: ensures retry_count advances after each
  evaluate_once call, preventing infinite loops on same-failure records
- Internal attempts_consumed guard: independent max_tier bound for
  defence-in-depth loop termination
- retry_count_consumed semantics: max(final.retry_count, attempts_consumed)
- Progress guard diagnostics: progress_guard_activations list tracks each
  normalisation event
- 23 new tests: normalize_retry_record unit tests, same/lower retry_count
  termination, terminal-after-retry, success-no-advance, recovery+same
  failure, safety checks
- BRANCH_CONTEXT.md updated

No live CST, no durable DB, no failure reuse, no JSONL reference,
no root shim repoint, no config default changes.
Phase O/O1 not marked accepted; pending reviewer decision.
```
