# Phase A8 -- Calibration primitives

## Summary

Added `workflows/rfgun_sao/calibration.py` with pure Python
dataclasses and helpers for the upcoming two-pass calibration:
`CalibrationResult`, `MeasurementPlan`, `make_measurement_plan`,
and `s11_min_db_from_magnitude`.  No runtime behaviour change.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/calibration.py` | Created (CalibrationResult, MeasurementPlan, helpers) | New |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 6 tests (5 calibration + 1 A7 missing MultiDip test) | Modified |
| `workflows/rfgun_sao/README.md` | Updated structure and test count | Modified |
| `reports/restructure_plan/phase_A8_calibration_primitives.md` | Created | New |

## Behaviour impact

**None.**  Calibration primitives are not integrated into the evaluator
or builder yet.

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
**sao:** 39/39 passed (6 new: 5 calibration + 1 MultiDip single-dip).
**--help:** exit 0.

## Next recommended phase

**A9:** Integrate gates and calibration into `build_workflow_1()`
when `evaluation.mode: two_pass`.
