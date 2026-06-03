# Phase A13.1 — CST runner adapter hardening

## Task

No-CST hardening for the opt-in CST two-pass runner adapters (A13) before
live CST smoke.

Fixes:
1. **Solver error field** — changed ``getattr(solver_result, 'error', ...)``
   to ``getattr(solver_result, 'error_message', None) or 'unknown'`` to
   match the actual ``SolverResult`` API.
2. **Calibration runner unit tests** — 5 focused no-CST tests using fake
   CST objects (``FakeProject``, ``FakeConnection``, ``FakeSolverRunner``,
   ``FakeResultReader``) and monkeypatch.
3. **Measurement runner delegation test** — 1 test verifying
   ``make_cst_measurement_runner`` correctly delegates to
   ``Workflow1Evaluator.evaluate_single_pass`` with ``f_data`` merged.

## Summary

Only ``two_pass_cst.py`` and the test file were modified.  ``workflow.py``
and ``README.md`` are untouched.

### two_pass_cst.py
- Changed line 82: ``solver_result.error`` → ``solver_result.error_message``

### tests
New section K with 6 tests (total 66 → 72):

| Test | What it verifies |
|------|-----------------|
| ``test_cst_calibration_runner_success_hpbw`` | HPBW success path: ``success=True``, ``f_data`` set, ``close()`` called |
| ``test_cst_calibration_runner_solver_failure_uses_error_message`` | ``error_message`` field propagated into ``CalibrationResult.error`` |
| ``test_cst_calibration_runner_com_failure_classified`` | ``error_type="com"`` returns COM-lost message |
| ``test_cst_calibration_runner_parameter_update_failure`` | ``update_parameters`` returning ``False`` returns failure |
| ``test_cst_calibration_runner_hpbw_fallback_to_dip_min`` | HPBW raises → fallback to dip-min, method == ``"cst_s11_dip_min"`` |
| ``test_cst_measurement_runner_delegates_to_workflow1_evaluator`` | ``f_data`` merged, iteration forwarded, ``EvaluationResult`` populated from evaluator output |

## Files changed

| File | Action |
|---|---|
| ``workflows/rfgun_sao/two_pass_cst.py`` | Fixed ``solver_result.error`` → ``solver_result.error_message`` |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added section K with 6 tests + fake helpers |
| ``reports/restructure_plan/phase_A13_1_cst_runner_hardening.md`` | Created (this file) |

## Behavioural changes

**None for production defaults.**
- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged** (no CST,
  penalty 1.0, ``workflow._conn = None``).
- ``runtime=cst`` remains **opt-in only**.
- Calibration solver failure error message now correctly reads
  ``solver_result.error_message`` instead of the non-existent
  ``solver_result.error`` field.
- Retry, inter-pass recovery, metric roles, staged search still
  **not implemented**.

**Protected areas confirmed unchanged:**

| Area | Status |
|---|---|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
# … 72/72 passed (66 existing + 6 new)

$ git diff --name-only
workflows/rfgun_sao/two_pass_cst.py
tests/workflows/test_rfgun_sao_imports.py
reports/restructure_plan/phase_A13_1_cst_runner_hardening.md
```

**Live CST smoke:** not run.  A13.1 is no-CST hardening only.

## Notes / caveats

- A13.1 uses fake CST objects only; no real CST was invoked.
- Real CST smoke remains for A13.2 or manual validation.
- ``make_cst_calibration_runner`` is still minimal S11 HPBW / dip-min
  fallback; no mode-tracking or multi-resonance logic.
- Retry integration and inter-pass recovery remain future work.

## Commits

```
309754a
```
