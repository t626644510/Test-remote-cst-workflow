# Phase A16 — Mixed gate precedence and checkpoint semantics

## Task

Add no-CST regression tests to explicitly verify mixed gate precedence rules
and checkpoint semantics of the two-pass runtime evaluator:

1. Calibration failure has highest precedence over all gates.
2. Frequency gate is checked before S11 depth gate.
3. S11 depth gate applies after frequency gate accepts.
4. Multi-dip detector is diagnostic-only (does not reject).
5. Rejection scalar = ``dot(ones, normalized weights)`` = 1.0.

This is a **no-CST regression** task — no live smoke, no new production code.

## Summary

- Added 5 focused no-CST tests in a new Section N.
- **no-CST tests:** 82/82 passed (77 existing + 5 new).
- **No code changes needed** — all gate precedence and checkpoint semantics
  were already correct.

## Files changed

| File | Action |
|------|--------|
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section N with 5 tests |
| ``reports/restructure_plan/phase_A16_mixed_gate_precedence.md`` | Created (this file) |

No production code was modified.

## Behavioural changes

**None.** No production code was modified.

- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged**.
- ``runtime=cst`` remains **opt-in only**.
- No retry, inter-pass recovery, metric roles, staged search implemented.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
82/82 passed
```

**Live CST:** Not run. A16 is a no-CST gate precedence regression suite;
A14/A15 already validated individual gates with live CST.

## Gate semantics captured

The 5 new tests formally capture the following semantics:

| # | Test | What it asserts |
|---|------|-----------------|
| 1 | ``test_two_pass_gate_precedence_calibration_failure_before_gates`` | ``calibration_failed`` with detailed error in checkpoint, measurement not called, even when both gates would also reject |
| 2 | ``test_two_pass_gate_precedence_frequency_before_s11`` | ``frequency_gate_reject`` exclusively — ``s11_depth_gate_reject`` does not appear in error string, measurement not called |
| 3 | ``test_two_pass_gate_precedence_s11_after_frequency_accepts`` | ``s11_depth_gate_reject`` after frequency gate accepts, measurement not called |
| 4 | ``test_two_pass_multidip_diagnostic_does_not_reject_runtime`` | Direct decision call: ``accepted=True``, ``diagnostics["multi_dip_detected"]=True``. Runtime evaluator: measurement called, scalar from fake penalties |
| 5 | ``test_two_pass_rejection_scalar_all_ones_with_normalized_weights`` | ``val == 1.0`` for ``weights=[0.2, 0.3, 0.5]``, ``penalties=[1,1,1]``, checkpoint ``ok=False`` |

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** |
| CST project/result artifacts | **Not committed** |

## Notes / caveats

- This does not validate mixed gates with live CST.
- Multi-dip live validation remains future work.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search) remains future work.

## Commits

- Implementation/fix commit: ``HEAD`` — ``A16 add mixed gate precedence regression tests``
- Report commit: included in implementation commit (same hash)
- Final pushed HEAD: ``<filled after push>``
