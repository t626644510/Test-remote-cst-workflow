# Phase A13.2 — Live CST smoke for opt-in two-pass runtime

## Task

Minimal live CST smoke test for the opt-in ``evaluation.two_pass.runtime: cst``
path added in A13.  No code changes were needed — the adapter handled a failed
calibration gracefully.

## Summary

- **no-CST tests:** 72/72 passed (baseline before smoke)
- **Live CST smoke:** passed with caveats
  - CST connection: **created** (PID=26448)
  - Calibration runner: **invoked** (S11 read attempted)
  - Calibration result: **failed** (``success=False``, ``f0=nan``)
  - Gate decision: ``calibration_failed`` → measurement skipped
  - Evaluator returned: **1.0** (graceful placeholder)
  - No unhandled exceptions
- **Code changes:** none — only report added

## Files changed

| File | Action |
|---|---|
| ``reports/restructure_plan/phase_A13_2_live_cst_smoke.md`` | Created (this file) |

No production code was modified in A13.2.

## Local config

Used ``workflows/rfgun_sao/config.local.yaml`` (gitignored, not committed):

- ``evaluation.mode: two_pass``
- ``evaluation.two_pass.runtime: cst``
- ``optimization.n_initial_samples: 1``, ``n_iterations: 0``
- ``retry.enabled: false``

All other fields identical to ``config.yaml``.

## Validation

### 1. no-CST pytest

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
72/72 passed
```

### 2. Live CST smoke

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

**Exit code:** 0

**Key log lines (from runtime log):**
```
20:32:59 [INFO] workflows.rfgun_sao.workflow: Workflow 1 (two_pass CST): connected to CST DE, PID=26448
20:32:59 [INFO] workflow_1: Start: 1 initial + 0 iterations
20:32:59 [WARNING] workflows.rfgun_sao.calibration: Calibration failed (success=False, f0=nan), falling back to 11.424000 GHz
20:32:59 [DEBUG] cst_optimization.checkpoint: Checkpoint saved (1 records)
20:32:59 [INFO] workflow_1: Workflow 1 completed. Best F: [1.]
```

**Stdout summary:**
```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 7
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best X: [...]
Best F: [1.]
```

**Key observations:**
1. CST connection established ✅
2. Two-pass CST branch entered (not placeholder) ✅
3. Calibration runner attempted S11 analysis ✅
4. Calibration failed (solver or S11 analysis issue — exact error not surfaced in log) ✅ (graceful)
5. Decision gate correctly identified ``calibration_failed`` ✅
6. Measurement path correctly skipped ✅
7. Checkpoint recorded ✅
8. Evaluator returned scalar 1.0 (no crash) ✅
9. **Calibration sensitivity needs tuning** — HPBW and dip-min fallback both failed to identify a valid ``f0_ghz``. Possible causes: solver didn't run, S11 sweep had no dip, or error during ``ResultReader.get_s_parameter()``.

## Behavioural changes

**None.** No production code was modified.
- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged**.
- ``runtime=cst`` remains **opt-in only**.
- Retry, inter-pass recovery, metric roles, staged search still **not implemented**.

## Protected areas

| Area | Status |
|---|---|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** |
| CST project/result artifacts | **Not committed** |

## Notes / caveats

- The A13 runner adapter has **minimal live smoke coverage** — the calibration
  path exercised correctly but failed to find a resonance.
- **Calibration failure** is likely due to:
  (a) the solver returning an error that surfaced as ``error_message`` (not
  visible in current logging), or
  (b) ``ResultReader.get_s_parameter()`` or ``half_power_bandwidth()``
  returning non-finite results.
- The calibration error string is stored in ``CalibrationResult.error`` but
  **not logged** by the current ``evaluate_two_pass_decision`` /
  ``make_measurement_plan`` path.  A future improvement could log the
  detailed error to aid debugging.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search) remains future work.

## Commits

- Implementation/fix commit: **none**
- Report commit: ``<!-- filled after commit -->`` — A13.2 report live CST smoke
- Final pushed HEAD: ``<!-- filled after push -->``
