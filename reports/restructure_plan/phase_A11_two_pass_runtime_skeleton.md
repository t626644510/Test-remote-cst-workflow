# Phase A11 -- Two-pass runtime skeleton

## Summary

Replaced the `NotImplementedError` for `evaluation.mode=two_pass`
with a working runtime skeleton.  Two-pass mode now builds parameters,
objectives, a placeholder evaluator (no CST), and the SAO optimizer,
then returns a workflow that can be invoked without CST.  Single-pass
behaviour is unchanged.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/two_pass.py` | Added `make_two_pass_placeholder_evaluator()` | Modified |
| `workflows/rfgun_sao/workflow.py` | Replaced NotImplementedError with two_pass path | Modified |
| `tests/workflows/test_rfgun_sao_imports.py` | Added two_pass placeholder tests | Modified |
| `workflows/rfgun_sao/README.md` | Updated status | Modified |
| `reports/restructure_plan/phase_A11_two_pass_runtime_skeleton.md` | Created | New |

## Behaviour impact

- **single_pass**: Unchanged (identical path).
- **two_pass**: No longer raises `NotImplementedError`.  Builds workflow
  without CST connection and returns a placeholder evaluator that always
  returns penalty 1.0.  Not physically meaningful yet.

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -q
pytest tests/workflows/test_rfgun_sao_imports.py -q
python -m workflows.rfgun_sao.run --help
`

### Real terminal output

**compileall:** exit 0 (workflow.py recompiled).
**single_pass:** 12/12 passed.
**sao:** 53/53 passed (2 new: two_pass build, no CST connection).
**--help:** exit 0.

## Next recommended phase

**A12:** Begin actual two-pass CST implementation with calibration/measurement evaluator.
