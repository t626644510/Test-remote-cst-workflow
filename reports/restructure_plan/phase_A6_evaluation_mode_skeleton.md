# Phase A6 -- evaluation.mode skeleton

## Summary

Added `evaluation.mode` to the rfgun_sao config schema with a
fail-fast skeleton.  Default mode `single_pass` preserves the
validated single-pass behaviour unchanged.  Mode `two_pass` is
reserved for future implementation and raises `NotImplementedError`
before any CST connection is established.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/config.yaml` | Added `mode: single_pass` | Modified |
| `workflows/rfgun_sao/workflow.py` | Added `_resolve_evaluation_mode()` + fail-fast check | Modified |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 3 mode-related tests | Modified |
| `reports/restructure_plan/phase_A6_evaluation_mode_skeleton.md` | Created | New |

## Behaviour

- Default `single_pass` runs the existing validated path unchanged.
- `two_pass` raises `NotImplementedError` **before** `CSTConnection()`.
- Invalid mode values raise `ValueError`.

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -q
pytest tests/workflows/test_rfgun_sao_imports.py -q
python -m workflows.rfgun_sao.run --help
`

### Real terminal output

**compileall:** exit 0.
**single_pass tests:** 12/12 passed.
**sao tests:** 24/24 passed (3 new: mode default, mode parsing, NotImplementedError).
**--help:** exit 0, flags correct.

New tests:
- `test_config_yaml_has_evaluation_mode` -- config has `mode: single_pass`
- `test_resolve_evaluation_mode_defaults` -- parsing, defaults, invalid mode
- `test_workflow_source_has_two_pass_fail_fast` -- `NotImplementedError` present

## Next recommended phase

**A7:** Add frequency gate and S11 depth gate.
