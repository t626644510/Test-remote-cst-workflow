# Phase A5.1 -- objective_weights validation fix

## Summary

Fixed two issues with the A5 objective_weights implementation:

1. `_resolve_named_weights()` no longer replaces zero weights with 1.0
   (weight `0.0` is now allowed, weight `inf` is rejected).
2. `_build_sao()` CompositeObjective path now reuses
   `_resolve_named_weights()` instead of duplicating dict-to-list logic.

## Bug fixed

| Issue | Before | After |
|---|---|---|
| `weight=0` | Clamped to 1.0 | Allowed (0.0 stays) |
| `weight=inf` | Ignored (passed to `np.where`) | Rejected (`ValueError`) |
| CompositeObjective weights | Separate dict-to-list logic | Reuses `_resolve_named_weights()` |

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/workflow.py` | `_resolve_named_weights()` validation + `_build_sao()` | Modified |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 3 weight-validation tests | Modified |
| `reports/restructure_plan/phase_A5_1_objective_weights_fix.md` | Created | New |

## Behaviour

- `{a: 0.0, b: 2.0}` → `[0.0, 1.0]` (normalized, zero preserved).
- `{a: 0.0, b: 0.0}` → `ValueError` (sum non-positive).
- `{a: inf}` → `ValueError` (non-finite).
- `_build_sao()` CompositeObjective now uses the same weight resolution
  as the SAO scalar evaluator wrapper (single code path).

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -q
pytest tests/workflows/test_rfgun_sao_imports.py -q
python -m workflows.rfgun_sao.run --help
`

### Real terminal output

**compileall:** exit 0.
**single_pass:** 12/12 passed.
**sao:** 21/21 passed (3 new: weight zero, all-zero, inf).
**--help:** exit 0, flags correct.

New tests:
- `test_weight_0_is_allowed` -- `{a: 0, b: 2}` → `[0.0, 1.0]`
- `test_all_zero_weights_raise_error` -- `{a: 0, b: 0}` → ValueError
- `test_inf_weights_raise_error` -- `{a: inf}` → ValueError

## Next recommended phase

**A6:** Add optional two-pass skeleton (`evaluation.mode: single_pass / two_pass`).
