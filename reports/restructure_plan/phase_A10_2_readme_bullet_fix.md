# Phase A10.2 -- README bullet fix

## Summary

Fixed a single line in README where A9 and A10 bullets were merged
on one line.  No test or logic changes.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/README.md` | Split A9/A10 bullet | Modified |
| `reports/restructure_plan/phase_A10_2_readme_bullet_fix.md` | Created | New |

## Behaviour impact

None.

## Tests run

`powershell
python -m compileall src workflows ...
pytest tests/workflows/test_rfgun_single_pass_imports.py -q
pytest tests/workflows/test_rfgun_sao_imports.py -q
python -m workflows.rfgun_sao.run --help
`

**compileall:** exit 0.  **single_pass:** 12/12.  **sao:** 51/51.  **--help:** exit 0.

## Next recommended phase

**A11:** Integrate two_pass.py into `build_workflow_1()`.
