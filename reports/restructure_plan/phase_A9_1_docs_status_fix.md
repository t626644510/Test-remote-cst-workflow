# Phase A9.1 -- Docs/status fix

## Summary

Updated `README.md` to reflect the actual A9 implementation status,
noting what is implemented (objective_weights, gates, calibration,
two-pass config helpers) and what is not (actual two-pass, gate
integration, metric roles).  Test metadata corrected to 45/45.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/README.md` | Rewritten with accurate status table | Modified |
| `reports/restructure_plan/phase_A9_1_docs_status_fix.md` | Created | New |

## Behaviour impact

None.

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -q
pytest tests/workflows/test_rfgun_sao_imports.py -q
python -m workflows.rfgun_sao.run --help
`

### Real terminal output

**compileall:** exit 0.
**single_pass:** 12/12.
**sao:** 45/45.
**--help:** exit 0.

## Next recommended phase

**A10:** Integrate gates into `evaluation.mode: two_pass` two-pass path.
