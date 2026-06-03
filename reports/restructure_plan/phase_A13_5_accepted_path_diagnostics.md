# Phase A13.5 — Accepted-path calibration diagnostics

## Task

Add an ``INFO``-level log line to the accepted calibration path of the
two-pass runtime evaluator so that successful calibrations are visible in
the runtime log alongside the existing rejection diagnostics (A13.3).

This is an **observability polish** — no workflow logic, scoring, or
checkpoint behaviour is changed.

## Summary

- Added accepted-path ``_logger.info`` in ``make_two_pass_runtime_evaluator``
  recording ``reason``, ``cal_success``, ``f0_ghz``, ``s11_min_db``,
  ``cal_method``, and compact ``meta``.
- Extended ``_FakeCalibrationRunner`` test helper with ``method`` and ``meta``
  parameters.
- Added 1 no-CST test (``test_two_pass_runtime_logs_accepted_calibration_details``)
  verifying the log message with ``caplog``.
- **no-CST tests:** 77/77 passed.
- **Live CST rerun:** not performed — A13.4 already established full minimal
  pass; A13.5 is no-CST observability only.

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/two_pass.py`` | Added accepted-path ``_logger.info`` before measurement pass |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Extended ``_FakeCalibrationRunner`` with ``method``/``meta``; added Section M test |
| ``reports/restructure_plan/phase_A13_5_accepted_path_diagnostics.md`` | Created (this file) |

## Behavioural changes

**None.** No production behaviour is altered.

- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged**.
- ``runtime=cst`` remains **opt-in only**.
- No change to scalar, penalty, or checkpoint behaviour.
- No retry, inter-pass recovery, metric roles, staged search implemented.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
77/77 passed
```

### New test

| Test | What it verifies |
|------|-----------------|
| ``test_two_pass_runtime_logs_accepted_calibration_details`` | ``caplog`` captures ``Two-pass accepted`` with ``f0_ghz=11.4245``, ``s11_min_db=-20.0``, ``cal_method=cst_s11_hpbw``, and meta fields ``s11_points``/``hpbw_ok``; measurement called once; scalar finite and not 1.0 |

### Live CST rerun

Not run. A13.4 already demonstrated a full minimal pass (Best F = -15185.95,
all 7 metrics computed). A13.5 is a no-CST code change verified by the
``caplog`` unit test.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** |
| CST project/result artifacts | **Not committed** |

## Notes / caveats

- A13.5 improves observability only.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search, enabled gates) remains future work.

## Commits

- Implementation/fix commit: ``HEAD`` — ``A13.5 log accepted two-pass calibration diagnostics``
- Report commit: included in implementation commit (same hash)
- Final pushed HEAD: ``<filled after push>``
