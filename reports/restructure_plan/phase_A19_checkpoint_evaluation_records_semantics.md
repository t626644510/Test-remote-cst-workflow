# Phase A19 — Checkpoint / evaluation-records semantics audit

## Task

Audit the two-pass evaluation checkpoint and evaluation-records semantics in
``workflows/rfgun_sao`` via no-CST targeted regression tests.  Build a
semantic matrix covering all evaluation paths; fill any gaps.

This is a **no-CST audit** — no production code changes, no live smoke.

## Semantic matrix

| Path | Checkpoint `solver_ok` | Checkpoint `error` | Penalties | Raw values | Callee | Notes |
|------|------------------------|---------------------|-----------|------------|--------|-------|
| **Placeholder** (default two_pass) | `False` | `"calibration_failed: placeholder_calibration_runner"` | All 1.0 | All NaN | `mark_failed` | `run.py` creates pending → failed record |
| **Calibration failed** | `False` | `"calibration_failed: <detail>"` or `"calibration_failed"` | All 1.0 | All NaN (or f0 if finite) | `mark_failed` | reason appended with error detail via `_decision_error_message` |
| **Frequency gate reject** | `False` | `"frequency_gate_reject"` | All 1.0 | All NaN (or f0 if finite) | `mark_failed` | Gate rejects; measurement not called |
| **S11 depth gate reject** | `False` | `"s11_depth_gate_reject"` | All 1.0 | All NaN (or f0 if finite) | `mark_failed` | Same pattern as freq gate |
| **Measurement success** | `True` | `""` | From runner | From runner | `mark_completed` | All metrics finite, scalar = dot(pen, weights) |
| **Measurement failure** | `False` | `result.error` | All 1.0 | From runner (fallback chain) | `mark_failed` or ambiguous | If all raw NaN → `mark_failed`; if partial finite raw with no `_wf_ref` → stuck pending (edge case) |
| **Multi-dip diagnostic** | N/A (runtime doesn't pass S11 arrays) | N/A | N/A | N/A | N/A | A17 status: diagnostic-only; no live plumbing |

### Production code changed

**None.** All existing semantics were correct and consistent. Only new no-CST
regression tests were added to formally lock the observed behaviour.

## Files changed

| File | Action |
|------|--------|
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section Q with 6 checkpoint semantics tests |
| ``reports/restructure_plan/phase_A19_checkpoint_evaluation_records_semantics.md`` | Created (this file) |

No production code was modified.

## New tests (Section Q)

| Test | What it asserts |
|------|-----------------|
| ``test_two_pass_checkpoint_placeholder_runtime_semantics`` | Through ``build_workflow_1`` with ``two_pass`` mode, verifies: ``_conn is None``, checkpoint captures ``calibration_failed: placeholder_calibration_runner``, ``solver_ok=False``, penalties all 1.0, raw all NaN, scalar=1.0 |
| ``test_two_pass_checkpoint_frequency_gate_reject_semantics`` | Full checkpoint capture: ``solver_ok=False``, ``error="frequency_gate_reject"``, penalties all 1.0, raw contains f0=11.5, scalar=1.0 |
| ``test_two_pass_checkpoint_s11_depth_gate_reject_semantics`` | Full checkpoint capture: ``solver_ok=False``, ``error="s11_depth_gate_reject"``, penalties all 1.0, raw contains f0=11.424, scalar=1.0 |
| ``test_two_pass_checkpoint_measurement_success_full_semantics`` | Multi-metric (f1, f2): ``solver_ok=True``, ``error=""``, penalties=[0.15, 0.35], raw=[11.424, 0.5], scalar from weighted dot product |
| ``test_two_pass_checkpoint_measurement_failure_no_penalties`` | ``penalty_values=None`` + ``SOLVER_FAILED``: ``solver_ok=False``, ``error="solver timed out"``, penalties all 1.0, raw falls back to ``raw_metrics`` |
| ``test_extract_raw_array_both_none`` | ``_extract_raw_array`` returns all NaN when both ``objective_values`` and ``raw_metrics`` are ``None`` |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
93/93 passed
```

**Live CST:** Not run. A19 is a no-CST audit; live smoke reports are
provided by A13.4/A14/A15.

## Measurement failure status

**A19 does NOT fully lock the measurement-failure evaluation-records path.**
The current semantics are:

1. The runtime evaluator correctly sets ``solver_ok=False``, all-1 penalties,
   and passes ``result.error`` to the checkpoint callback.
2. The ``run.py`` checkpoint callback uses ``all_finite(raw_values)`` to
   decide ``mark_completed`` vs ``mark_failed``.  If a measurement returns
   partial finite raw values, the record may be marked completed despite
   ``solver_ok=False`` — an inconsistency noted but not addressed in A19.
3. ``evaluation_records.jsonl`` is not written by the two-pass path; only
   the ``.ckpt`` checkpoint is used.  The ``workflow.record_path`` attribute
   is set but not consumed by any two-pass code path.

**Recommendation for future phase (A20/A21):** Either align the checkpoint
callback to always use ``solver_ok`` (not ``all_finite``) for the
``mark_completed`` / ``mark_failed`` decision, or implement a dedicated
two-pass checkpoint handler that records the rejection reason alongside
each record.  Also evaluate whether ``evaluation_records.jsonl`` should be
written by the two-pass path or if the ``.ckpt`` format is sufficient.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed to live runtime=cst | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |

## Commits

- Implementation commit: ``HEAD`` — ``Phase A19 rfgun_sao checkpoint evaluation records audit``
- Report/hash-fill commit: included in implementation commit
- Final pushed HEAD: ``<filled after push>``

## Caveats / follow-up

- **Measurement failure locking is incomplete.** The ``run.py`` checkpoint
  callback uses ``all_finite(raw)`` rather than ``solver_ok`` to decide
  ``mark_completed`` vs ``mark_failed``.  This can produce inconsistent
  records when a measurement returns partial finite data but reports failure.
  A future phase should align the checkpoint handler for the two-pass path.
- **``evaluation_records.jsonl`` is not written** by the two-pass path.
  Only the ``.ckpt`` checkpoint is persisted.  The ``workflow.record_path``
  attribute exists but is unused in the two-pass code path.
- **No live CST checkpoint evidence** was collected in this phase.
  A future live smoke with explicit checkpoint/record inspection would
  close the gap.
