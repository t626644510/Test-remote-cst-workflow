# Phase A22 — Checkpoint metric invariant hardening

## Task

Harden ``_checkpoint_metric_names_from_wf_ref()`` and
``_record_checkpoint_evaluation()`` against remaining metric invariant gaps
found in A21 review:
1. ``objective_names`` of type ``str`` would be split into characters.
2. Duplicate metric names could produce unstable dict keys.
3. Invalid / empty metric members were not rejected.
4. Penalties array length was not checked against metric names.

## A21 review findings

| Gap | Before A22 | After A22 |
|-----|-----------|-----------|
| String `objective_names` | Accepted; `"abc"` → `["a", "b", "c"]` | Rejected with `None` |
| Duplicate names | Accepted silently | Rejected with `None` |
| Invalid member (empty str, None) | Accepted | Rejected with `None` |
| Penalties length check | Not checked | Hard `mark_failed` with `"checkpoint_metric_length_mismatch"` |

## Production code changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Updated `_checkpoint_metric_names_from_wf_ref` with validation rules; updated length check in `_record_checkpoint_evaluation` to also check penalties length |

### `_checkpoint_metric_names_from_wf_ref` rules (added)

- Rejects `str` / `bytes` types (would be misinterpreted as character sequences).
- Rejects empty list.
- Rejects any element that is not a non-empty `str`.
- Rejects duplicates (`len(set(...)) != len(...)`).

### `_record_checkpoint_evaluation` length check (expanded)

Before: `if len(metric_names) != len(raw_values)`

After: `if len(metric_names) != len(raw_values) or len(metric_names) != len(penalties)`

## Test matrix (Section T — 5 tests)

| Test | Input | Expected |
|------|-------|----------|
| `test_checkpoint_metric_names_string_rejected` | `objective_names="abc"` (str) | `status!=completed`, error `checkpoint_objective_names_unavailable` |
| `test_checkpoint_metric_names_duplicate_rejected` | `["a", "a"]` | `status!=completed`, error `checkpoint_objective_names_unavailable` |
| `test_checkpoint_metric_names_invalid_member_rejected` | `["a", ""]` | `status!=completed`, error `checkpoint_objective_names_unavailable` |
| `test_checkpoint_metric_names_penalties_mismatch` | 2 names, 2 raw, 1 penalty | `status!=completed`, error `checkpoint_metric_length_mismatch` |
| `test_checkpoint_metric_names_valid_regression` | `["a", "b"]`, matching lengths | `status==completed`, `solver_ok=True`, raw/pen dicts correct |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
107/107 passed
```

- 102 existing + 5 new Section T tests.
- All A19/A20/A21/A22 checkpoint tests pass.

**Live CST:** Not run. A22 is a no-CST hardening verified by unit tests.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |

## Commit hashes

- Implementation commit: **133fef3** — `Phase A21 rfgun_sao checkpoint objective names hardening`
- Report/hash-fill commit: **1344b00** — `A21 report: fill commit hash`
- A22 implementation commit: ``HEAD`` — ``Phase A22 rfgun_sao checkpoint metric invariant hardening``
- A22 report/hash-fill commit: included in A22 implementation commit (same hash)
- Final pushed HEAD: ``<filled after push>``

**Note on A20/A21 report hashes:** The A20 report (``c598ee2``) and A21 report
(``133fef3``) contained ``HEAD`` in their implementation commit fields at
commit time.  Subsequent hash-fill commits (``2a8ee2e`` for A20, ``1344b00``
for A21) updated those fields.  A22 avoids this by including the report in the
same commit as the implementation.

## Caveats / follow-up

- ``evaluation_records.jsonl`` is **still not written** by the two-pass path.
- Live CST checkpoint evidence with the hardened semantics remains for a
  future phase.
- Metric invariant hardening is now comprehensive for the checkpoint path.
