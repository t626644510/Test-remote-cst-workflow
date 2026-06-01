# Phase A17 — Multi-dip diagnostic status

## Task

Clarify the multi-dip detection status via no-CST regression tests and
README documentation: MultiDipDetector is a pure utility that can flag
diagnostics when S11 arrays are explicitly supplied, but the runtime CST
path stores only compact S11 summaries and does not plumb full arrays for
live multi-dip analysis.

This is a **no-CST regression + documentation clarification**, not a live
validation or new feature implementation.

## Summary

- Added 4 focused no-CST tests in Section O documenting:
  - Multi-dip detector flags diagnostics but decision remains accepted.
  - Runtime evaluator with multi-dip detector proceeds without S11 arrays.
  - CST calibration meta stores compact summaries, not full arrays.
  - README documents multi-dip diagnostic-only / future-work status.
- Updated ``README.md`` with explicit multi-dip status notes.
- **no-CST tests:** 86/86 passed (82 existing + 4 new).
- **No production code changes** — tests and documentation only.

## Files changed

| File | Action |
|------|--------|
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section O with 4 tests |
| ``workflows/rfgun_sao/README.md`` | Updated Implemented / Not implemented / Notes with multi-dip status |
| ``reports/restructure_plan/phase_A17_multidip_diagnostic_status.md`` | Created (this file) |

No production code was modified.

## Behavioural changes

**None.** No production code was modified.

- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged**.
- ``runtime=cst`` remains **opt-in only**.
- Multi-dip remains **diagnostic-only** (does not reject, does not affect
  penalty/scalar).
- No retry, inter-pass recovery, metric roles, staged search implemented.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
86/86 passed
```

**Live CST:** Not run. A17 is a no-CST status/documentation task;
A13.4/A14/A15 already covered live smoke paths.

## Multi-dip status captured

The 4 new tests and README updates formally capture these facts:

| # | What it asserts |
|---|-----------------|
| 1 | ``MultiDipDetector`` detects close dips; ``evaluate_two_pass_decision`` returns ``accepted=True`` with ``diagnostics["multi_dip_detected"]=True`` when S11 arrays are **explicitly supplied** |
| 2 | Runtime evaluator with ``multi_dip_detector`` enabled proceeds to measurement even without S11 arrays — does not reject, does not get stuck |
| 3 | CST calibration meta stores compact summary fields (``s11_points``, ``s11_freq_min_ghz``, ``s11_freq_max_ghz``, ``s11_min_db``) — NOT full frequency/magnitude arrays |
| 4 | README states multi-dip is diagnostic-only, live plumbing is future work, runtime stores compact summaries |

Key design decisions enforced:
- ``"frequencies_ghz"``, ``"s11_magnitude"``, ``"s_complex"`` are **not** stored in ``CalibrationResult.meta``.
- No ``np.ndarray`` or ``list`` values appear in meta.
- Multi-dip detection does **not** reject candidates in any path.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** |
| CST project/result artifacts | **Not committed** |

## Notes / caveats

- This intentionally avoids storing full S11 arrays in
  ``CalibrationResult.meta`` to prevent bloat and accidental leaks.
- Future live multi-dip plumbing should derive dip features from the
  calibration solve and pass compact dip descriptors (dip count, dip
  frequencies, dip depths) rather than raw arrays.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search) remains future work.

## Commits

- Implementation/fix commit: ``HEAD`` — ``A17 document multi-dip diagnostic status``
- Report commit: included in implementation commit (same hash)
- Final pushed HEAD: ``<filled after push>``
