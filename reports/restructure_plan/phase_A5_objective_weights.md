# Phase A5 -- objective_weights support

## Summary

Added optional `optimization.objective_weights` support to the
`workflows/rfgun_sao/workflow.py` builder.  Default behaviour
(no `objective_weights`) remains equal weights, unchanged from the
validated WF1 baseline.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/run.py` | Fixed stale path comment | Modified |
| `workflows/rfgun_sao/workflow.py` | Enhanced `_resolve_named_weights()` with validation | Modified |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 4 weight-related tests | Modified |
| `reports/restructure_plan/phase_A5_objective_weights.md` | Created | New |

## Behaviour

- `objective_weights: null` → equal weights (1/N each), unchanged.
- `objective_weights: {}` (empty dict) → equal weights.
- `objective_weights: {resonant_freq: 5.0, ...}` → named dict,
  missing objectives default to 1.0.  Unknown keys produce a warning.
- Validation: NaN, negative, or non-positive sum raise `ValueError`.
- The `_build_sao()` CompositeObjective path also reads the same dict.

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
**sao:** 18/18 passed (4 new weight tests).
**--help:** exit 0, correct flags.

New tests:
- `test_default_weights_equal` — `_resolve_named_weights(None, ...)` returns [1/3, 1/3, 1/3]
- `test_named_weights_by_objective_order` — dict weights preserve objective_names order
- `test_invalid_weights_raise_error` — NaN or negative → ValueError
- `test_workflow_source_has_objective_weights` — source contains `objective_weights`

## Next recommended phase

**A6:** Add optional two-pass skeleton (`evaluation.mode: single_pass / two_pass`).
