# Phase A21 — Checkpoint objective_names hardening

## Task

Harden ``_record_checkpoint_evaluation`` in ``run.py`` against missing or
malformed ``objective_names`` on the ``wf_ref`` container.  The helper now
explicitly validates metric names before attempting to use them, preventing
uncaught ``AttributeError`` / ``TypeError`` when ``wf_ref[0]`` lacks
``.objective_names`` or the names are empty / non-iterable.

## A20 review finding

``_record_checkpoint_evaluation`` checked only ``bool(wf_ref)``.  If
``wf_ref[0]`` had no ``.objective_names`` attribute, the line
``metric_names = wf_ref[0].objective_names`` would raise ``AttributeError``
with no fallback.  The same gap applied to ``objective_names=[]`` or a
non-iterable value.

## Production code changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added ``_checkpoint_metric_names_from_wf_ref()`` helper.  Updated ``_record_checkpoint_evaluation`` to use it.  Added length-mismatch guard. |

### Helper: ``_checkpoint_metric_names_from_wf_ref(wf_ref)``

Returns ``list[str]`` when metric names are available; ``None`` otherwise.
Never raises for the following cases:
- ``wf_ref`` is empty.
- ``wf_ref[0]`` lacks ``objective_names``.
- ``objective_names`` is ``None``, empty, or not iterable.

### Updated decision rules in ``_record_checkpoint_evaluation``

| Condition | Action | Error fallback |
|-----------|--------|----------------|
| ``solver_ok=True``, all finite, **valid metric_names**, lengths match | ``mark_completed`` | — |
| Length mismatch between names and raw | ``mark_failed`` | ``"checkpoint_metric_length_mismatch"`` |
| No names (from helper returning None) | ``mark_failed`` | ``"checkpoint_objective_names_unavailable"`` |
| ``not solver_ok`` | ``mark_failed`` | preserves passed error, or ``"checkpoint_solver_failed"`` |
| Raw has NaN | ``mark_failed`` | preserves passed error, or ``"non_finite_raw_values"`` |
| Catch-all | ``mark_failed`` | ``"checkpoint_record_failed"`` |

## Test matrix (Section S — 4 tests)

| Test | Inputs | Assertions |
|------|--------|------------|
| ``test_checkpoint_metric_names_object_no_names`` | ``wf_ref=[object()]``, ``solver_ok=True``, finite raw | ``status!=completed``, error contains ``checkpoint_objective_names_unavailable``, no exception |
| ``test_checkpoint_metric_names_empty_list`` | ``wf_ref=[Fake([])]``, ``solver_ok=True``, finite raw | ``status!=completed``, error contains ``checkpoint_objective_names_unavailable`` |
| ``test_checkpoint_metric_names_length_mismatch`` | 2 names but 1 raw element, ``solver_ok=True``, finite | ``status!=completed``, error contains ``checkpoint_metric_length_mismatch`` |
| ``test_checkpoint_metric_names_valid_still_completes`` | Valid ``["m1", "m2"]``, ``solver_ok=True``, finite | ``status==completed``, raw=/pen dicts correct |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
102/102 passed
```

- 98 existing + 4 new Section S tests.
- All A19/A20/A21 checkpoint tests pass.

**Live CST:** Not run. A21 is a no-CST hardening verified by unit tests.

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
- Live CST checkpoint evidence with the updated semantics remains for a
  future phase.
- Length mismatch now raises a hard ``mark_failed`` (rather than silently
  truncating via ``zip``), which matches the expected invariant.

## Commits

- Implementation commit: ``HEAD`` — ``Phase A21 rfgun_sao checkpoint objective names hardening``
- Report/hash-fill commit: included in implementation commit
- Final pushed HEAD: ``133fef3``
