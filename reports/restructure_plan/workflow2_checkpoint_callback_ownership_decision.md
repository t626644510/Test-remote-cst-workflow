# W2-6C: Checkpoint Callback Ownership Decision Record

**STATUS: Historical analysis.  Superseded by W2-6E.**

W2-6C analysed the R4 double-trigger and proposed four options.
W2-6E implemented Option C: evaluator-only callback ownership.
``DualProjectOrchestrator`` no longer fires ``checkpoint_callback``.
Workflow2 evaluator wrappers fire exactly one callback per logical evaluation.

See the decision options below for the historical rationale; W2-6E
implementation is current.

## Current Behaviour (as of W2-6E)

### Callback Origin

The root ``run_workflow_2.py::_on_evaluation`` (lines 181–206) is a
persistence callback with side effects:

```python
def _on_evaluation(x_phys, raw_values, penalties, solver_ok, error):
    idx = ckpt.add_pending(x_phys)       # ← creates new EvalRecord
    if all_finite:
        ckpt.mark_completed(idx, ...)     # ← finalizes that record
    elif phases_done:
        ckpt.mark_phase_done(idx, ...)
    else:
        ckpt.mark_failed(idx, error)
    ckpt.save()                           # ← persists to disk
```

### Two Call Sites (historical — orchestrator call removed in W2-6E)

| Call site | File | Trigger |
|-----------|------|---------|
| Orchestrator | `orchestrator.py:567` | End of `DualProjectOrchestrator.execute()` |
| SAO evaluator (retry) | `workflow.py:325–326` | After `retry_handler.execute()` returns |
| SAO evaluator (non-retry) | `workflow.py:346–352` | After `orchestrator.execute()` returns |

Because the evaluator calls `orch.execute()` internally, the orchestrator
fires the callback first, then the evaluator fires it again with the same
or derived data.

### Root Callback Side Effects (historical — single call as of W2-6E)

Each invocation of `_on_evaluation` calls `ckpt.add_pending(x_phys)`,
which **appends a new `EvalRecord`** to `ckpt.records`.  When the callback
fires twice for one logical evaluation:

1. **First call** (orchestrator): appends record A, then calls
   `ckpt.mark_completed(A_idx, ...)` or `mark_failed(A_idx, ...)`,
   then `ckpt.save()`. A is finalized.
2. **Second call** (evaluator): appends record B with the **same** x vector,
   then calls `ckpt.mark_completed(B_idx, ...)` or `mark_failed(B_idx, ...)`,
   then `ckpt.save()`. B is finalized.

Result: **two completed records exist for one evaluation**.  The first
record was finalized, then a duplicate was appended and finalized.  The
checkpoint file grows faster than expected and the warm-start GP may
receive duplicate training points.

### W2-1 Characterisation Confirmation (historical — updated in W2-6E)

`TestCheckpointCallbackCount` (3 tests) previously confirmed
`callback.call_count == 2` for both retry and non-retry paths.
As of W2-6E, these tests assert `call_count == 1`.

---

## Why This Matters

- **Persistence side effects**: the callback writes to disk on every call.
  Double-trigger doubles disk I/O and record count.
- **Incorrect warm-start**: `CheckpointManager.get_warm_xy()` returns ALL
  completed records.  Duplicate records mean duplicate training points
  for the GP surrogate model, which can bias acquisition.
- **Crash recovery risk**: `partial_records` and `pending_count` are
  inflated by orphaned pending records.
- **Future pipeline clarity**: as workflow2 gains more automation (scheduled
  re-runs, crash recovery), a clean record lineage is important.

---

## Decision Options

### Option A: Preserve + Document (Recommended for W2-6C)

Leave the current double-trigger behaviour unchanged.  Document that the
callback is not idempotent and that duplicate records are expected.

**Pros**:
- Zero behaviour change risk.
- W2-1 tests pass as-is.
- W2-6C can be purely documentary.

**Cons**:
- Duplicate checkpoint records accumulate silently.
- GP warm-start may degrade over many evaluations.
- A future fix becomes harder as history grows.

**Validation**: no-CST test duplication exists (added in W2-6C).

### Option B: Orchestrator Exclusively Owns the Callback

Remove the callback call from the SAO evaluator wrapper.
Only the orchestrator fires the callback.

**Pros**:
- Eliminates the root cause of double-trigger.
- Simple change (remove ~10 lines).
- Orchestrator has access to full execution state.

**Cons**:
- If the orchestrator's `execute()` is refactored or called without the
  evaluator wrapper, callbacks may be missed.
- Retry handler paths must still route through orchestrator.

**Required validation** (future phase):
- Update W2-1 P0.3 tests to expect call_count == 1.
- Verify retry path callback still fires (orchestrator inside
  `_evaluate_for_retry`).
- Verify crash-resume partial evaluation path.

### Option C: Evaluator Exclusively Owns the Callback

Remove the callback from the orchestrator.  Only the evaluator wrapper
fires it.

**Pros**:
- The evaluator is the single logical entry point for each optimisation
  iteration — it should own the callback contract.
- Orchestrator already propagates state via `last_raw_values`,
  `last_penalties`, `last_solver_ok`.

**Cons**:
- If anyone calls `orch.execute()` directly (without the evaluator
  wrapper), no callback fires.
- SAEA path uses `orchestrator.execute` directly: the evaluator IS the
  orchestrator's execute method.  This path would need explicit callback
  wiring.

**Required validation** (future phase):
- Update W2-1 P0.3 tests to expect call_count == 1.
- Verify SAEA path callback (evaluator = orchestrator.execute).
- Verify crash recovery partial evaluation path.

### Option D: Make Root Callback Idempotent

Keep both call sites but guard `_on_evaluation` against duplicate records
for the same (x_phys, iteration) key.

**Pros**:
- Least invasive — no changes to orchestrator or evaluator.
- Root callback becomes safe to call multiple times.

**Cons**:
- Adds complexity to the callback (must track seen keys).
- Duplicate record accumulation still happens until the guard is triggered;
  the second call still appends before the guard can reject it unless a
  pre-check is added.

**Required validation** (future phase):
- Add unit test for the idempotency guard with exact duplicate and
  near-duplicate (same x, different iteration) inputs.
- Verify checkpoint record count after a full evaluation cycle.

---

## Recommendation (historical — implemented by W2-6E)

**Option C: Evaluator Exclusively Owns the Callback** was the recommended
approach.  W2-6E implemented it:
- `DualProjectOrchestrator` no longer fires `checkpoint_callback`.
- Evaluator wrappers (SAO retry, SAO non-retry, SAEA) fire exactly one
  callback per logical evaluation.
- The SAEA path was given an explicit wrapper (W2-6E).
- Only the evaluator owns callback firing.

1. The evaluator wrapper is the single logical entry point for each SAO
   iteration.  Making it the callback owner aligns responsibility with
   the contract.
2. The orchestrator already exposes `last_*` state properties — removing
   its callback call loses no data.
3. The SAEA path (`evaluator = orchestrator.execute`) would need explicit
   callback wiring, which is a small, testable change.
4. The root `_on_evaluation` callback is explicitly designed for the
   evaluator's lifecycle — it references `orch.last_completed_labels`
   which is set by the orchestrator.

**W2-6E implemented Option C** (supersedes the above list).  See
``reports/restructure_plan/workflow2_current_context.md`` for the
implementation note.

---

## Tests Added in W2-6C (renamed in W2-6E)

| Original name (W2-6C) | Current name (W2-6E) | Current assertion |
|------|---------|---------|
| `test_non_retry_path_root_like_callback_creates_two_records` | `test_non_retry_path_root_like_callback_creates_one_record` | 1 record per evaluation |
| `test_retry_path_root_like_callback_creates_two_records` | `test_retry_path_root_like_callback_creates_one_record` | 1 record per evaluation |
| `test_both_calls_use_same_x_vector` | `test_same_x_vector_one_call` | 1 invocation, same x vector |

Additional tests added in W2-6E:
- `test_saea_evaluator_fires_callback_once` — SAEA path fires callback once
- `test_saea_evaluator_receives_arrays` — SAEA callback receives numpy arrays
- `test_partial_raw_nan_still_fires_callback_once` — NaN raw still fires once
- `test_non_retry_failure_passes_solver_ok_false` — failure semantics preserved
- `test_non_retry_success_passes_solver_ok_true` — success semantics preserved

## Appendix: Validation Commands

```powershell
python -m pytest tests/workflows/test_workflow2_characterization.py -q
python -m pytest tests/workflows/test_workflow2_scheduler_shim.py -q
```
