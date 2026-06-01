# Phase A13 — Minimal opt-in CST two-pass runners

## Task

Implement real CST two-pass calibration/measurement runner adapters for
the injectable two-pass runtime evaluator (A12).  All CST runners are
**opt-in** via ``evaluation.two_pass.runtime: cst``.  The default
``placeholder`` runtime is unchanged: no CST connection, penalty 1.0,
``workflow._conn = None``.

This is **not** a complete legacy Workflow 3 port.  Retry integration,
inter-pass recovery, metric roles, adaptive bounds, and staged search
remain future work.

## Summary

### new file: ``two_pass_cst.py``

- ``make_cst_calibration_runner(connection, project_path, solver_runner,
  calibration_guess_ghz)`` — returns a runner that:
  1. Opens the CST project
  2. Sets ``f_data = calibration_guess_ghz``
  3. Runs the frequency-domain solver
  4. Reads S11 via ``ResultReader``
  5. Extracts ``f0_ghz`` via ``half_power_bandwidth``, falls back to
     dip-minimum if HPBW fails
  6. Returns ``CalibrationResult(success, f0_ghz, s11_min_db, method)``
  Handles COM loss, solver failures, parameter update failures.

- ``make_cst_measurement_runner(wf1_evaluator, metric_names)`` — returns
  a runner that:
  1. Merges ``f_data`` from the ``MeasurementPlan`` into the param dict
  2. Delegates to ``wf1_evaluator.evaluate_single_pass`` to reuse all
     single-pass post-processing (frequency, Q0, beta, E-field, etc.)
  3. Converts the 5-tuple return to ``EvaluationResult``
  No physics logic is duplicated.

### modified: ``workflow.py``

- New helper ``_resolve_two_pass_runtime(config)`` reads
  ``evaluation.two_pass.runtime`` (default ``"placeholder"``,
  accepts ``"placeholder"`` or ``"cst"``).
- The two-pass branch now switches on runtime:
  - ``placeholder`` → existing behaviour (placeholder runners, no CST)
  - ``cst`` → creates ``CSTConnection``, ``SolverRunner``,
    ``Workflow1Evaluator``, then CST runner adapters; sets
    ``workflow._conn = conn``
- ``inter_pass_recovery`` is detected and logged as a warning but
  otherwise ignored.
- ``single_pass`` is unchanged.

### modified: ``README.md``

Updated implemented / not-implemented lists; added A13 items and
notes about ``config.local.yaml`` and opt-in config key.

### tests

5 new tests in section J (total 61 → 66):
- Runtime resolver defaults, accepts, rejects
- ``two_pass_cst`` module import + no-recovery check
- CST runtime branch with monkeypatched fake connection/evaluators
  (verifies wiring without real CST)

Also fixed ``_FakeMeasurementRunner`` sentinel bug (default
``objective_values`` now correctly equals ``raw_values``).

## Files changed

| File | Action |
|---|---|
| ``workflows/rfgun_sao/two_pass_cst.py`` | **Created** — CST calibration/measurement runner factories |
| ``workflows/rfgun_sao/workflow.py`` | Added ``_resolve_two_pass_runtime``; restructured two_pass branch for opt-in CST |
| ``workflows/rfgun_sao/README.md`` | Updated implemented/not-implemented lists, notes on opt-in config |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added section J (5 tests); fixed ``_FakeMeasurementRunner`` sentinel |
| ``reports/restructure_plan/phase_A13_minimal_cst_two_pass_runners.md`` | Created (this file) |

## Behavioural changes

**None for production defaults.**
- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged** (no CST,
  penalty 1.0, ``workflow._conn = None``).
- ``runtime=cst`` is **opt-in only** via ``evaluation.two_pass.runtime: cst``.
- Actual CST connection is only created for ``runtime=cst``.
- Retry integration, inter-pass recovery, metric roles, staged search
  are **not implemented** (intentionally out of scope).

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
# … 66/66 passed (61 existing + 5 new)

$ git diff --name-only
workflows/rfgun_sao/README.md
workflows/rfgun_sao/two_pass_cst.py
workflows/rfgun_sao/two_pass.py          # unchanged in A13
workflows/rfgun_sao/workflow.py
tests/workflows/test_rfgun_sao_imports.py
reports/restructure_plan/phase_A13_minimal_cst_two_pass_runners.md
```

**Live CST smoke:** not run.  A13 code path is opt-in and no-CST tests
passed.

## Local config note

``runtime=cst`` requires a local ``workflows/rfgun_sao/config.local.yaml``
with valid ``cst.library_path`` and ``project.cst_path``.  This file must
**not** be committed.

## Notes / caveats

- A13 uses ``Workflow1Evaluator`` for measurement post-processing to
  avoid duplicating physics code.
- Calibration runner is minimal S11-based f0 detection (HPBW + dip-min
  fallback).  No mode-tracking or multi-resonance logic.
- Retry integration remains future work.
- Inter-pass recovery remains future work (detected and logged as
  warning if enabled).
- Production validation beyond minimal smoke remains future work.

## Commits

```
<!-- filled after commit -->
```
