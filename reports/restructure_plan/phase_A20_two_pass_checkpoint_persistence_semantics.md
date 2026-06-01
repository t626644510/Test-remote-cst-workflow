# Phase A20 — Two-pass checkpoint persistence semantics fix

## Task

Fix the two-pass checkpoint persistence semantics discovered in A19: the
``_on_evaluation`` callback in ``run.py`` used ``all_finite(raw_values)``
as the primary decision for ``mark_completed`` vs ``mark_failed``, which
could mark a record as completed even when ``solver_ok=False``.

Extract the logic into a module-level testable helper
``_record_checkpoint_evaluation`` and base the decision on ``solver_ok``
first, then ``all_finite``, then ``wf_ref`` availability.

## A19 issue

Old ``_on_evaluation`` logic (removed):

```python
if all_finite and _wf_ref:
    mark_completed(...)           # mark_completed even if solver_ok=False
elif not all_finite:
    mark_failed(idx, error=error)  # fine, but what if all_finite=True and no _wf_ref?
ckpt.save()                        # ambiguous: record stays "pending" with no error
```

Three problems:
1. ``solver_ok=False`` + ``all_finite=True`` + ``_wf_ref`` populated → record
   incorrectly marked ``completed``.
2. ``all_finite=True`` + no ``_wf_ref`` → record stays ``pending`` with no
   error (ambiguous).
3. No fallback error string when error is empty.

## Production code changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added module-level ``_record_checkpoint_evaluation()`` helper. ``_on_evaluation`` inside ``main()`` delegates to it. |

### Helper: ``_record_checkpoint_evaluation``

**Signature:**
```python
def _record_checkpoint_evaluation(
    ckpt: CheckpointManager,
    wf_ref: list,
    x_phys: np.ndarray,
    raw_values: np.ndarray,
    penalties: np.ndarray,
    solver_ok: bool,
    error: str,
) -> None:
```

**Decision rules:**
1. ``solver_ok=True`` **and** all raw values finite **and** ``wf_ref``
   populated → ``mark_completed(solver_ok=True)``.
2. Otherwise → ``mark_failed(error=...)`` with stable fallback:
   - Preserves passed *error* if non-empty.
   - If empty: ``"checkpoint_solver_failed"`` (if ``not solver_ok``),
     ``"non_finite_raw_values"`` (if NaN), or
     ``"checkpoint_objective_names_unavailable"`` (if no wf_ref).

## Test matrix (Section R — 5 tests)

| Test | Inputs | Assertions |
|------|--------|------------|
| ``test_checkpoint_persistence_completed_success`` | ``solver_ok=True``, finite raw, wf_ref with names | ``status=completed``, ``solver_ok=True``, ``error=""``, raw/pen dicts correct |
| ``test_checkpoint_persistence_failure_finite_raw`` | ``solver_ok=False``, finite raw, error="solver timed out" | ``status!=completed``, ``solver_ok=False``, error contains "solver timed out" |
| ``test_checkpoint_persistence_rejection_nan_raw`` | ``solver_ok=False``, NaN raw, error="calibration_failed: ..." | ``status!=completed``, error contains "calibration_failed", "placeholder_calibration_runner" |
| ``test_checkpoint_persistence_solver_ok_nan_raw`` | ``solver_ok=True``, NaN raw, error="" | ``status!=completed``, fallback error "non_finite_raw_values" in record |
| ``test_checkpoint_persistence_no_wf_ref`` | ``solver_ok=True``, finite raw, empty ``wf_ref=[]`` | ``status!=completed``, fallback error "checkpoint_objective_names_unavailable" |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
98/98 passed
```

- 93 existing + 5 new Section R tests.
- All checkpoint semantics tests (A19 Section Q + A20 Section R) pass.

**Live CST:** Not run. A20 is a no-CST production fix verified by unit tests.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed to live runtime=cst | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |

## Caveats / follow-up

- ``evaluation_records.jsonl`` is **still not written** by the two-pass path.
  Only the ``.ckpt`` checkpoint is persisted.  The ``workflow.record_path``
  attribute on the two-pass container is set but unused.
- **Live CST checkpoint evidence** has not been collected with the new
  semantics.  A future live CST smoke could verify the completed record
  after a full run.
- ``CheckpointManager`` itself was not modified.  Its ``mark_failed``
  semantics (``status="pending"`` for retryable failures, ``solver_ok``
  unchanged) remain as defined in ``src/cst_optimization``.

## Commits

- Implementation commit: ``HEAD`` — ``Phase A20 rfgun_sao checkpoint persistence semantics``
- Report/hash-fill commit: included in implementation commit
- Final pushed HEAD: ``<filled after push>``
