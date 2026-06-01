# Phase A18 — rfgun_sao milestone summary

## Task

Consolidate the ``workflows/rfgun_sao/README.md`` with the validated status
from A13–A17, add a static README assertion test, and produce a milestone
summary report.

This is a **documentation / milestone consolidation** task — no new features,
no production code changes, no live smoke.

## Summary

- **README rewritten** with clear sections: Status, Default behavior,
  Validated so far, Implemented capabilities, Not implemented yet / future
  work, Running, Local CST config.
- **Test count updated** from stale ``66/66`` to current ``86/86``.
- **Live smoke results** from A13.4/A14/A15 captured in a validation table.
- **Static README assertion test** added (Section P) — asserts key
  substrings: ``86/86``, ``A13.4``, ``A14``, ``A15``, ``A16``, ``A17``,
  ``runtime=cst``, ``config.local.yaml``, ``run_workflow_1.py``,
  ``multi-dip``, ``future``.
- **no-CST tests:** 87/87 passed (86 existing + 1 new).
- **No production code changed.**

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/README.md`` | Complete rewrite with milestone structure |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section P — static README assertion |
| ``reports/restructure_plan/phase_A18_rfgun_sao_milestone_summary.md`` | Created (this file) |

No production code was modified.

## Behavioural changes

**None.** No production code was modified.

- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged**.
- ``runtime=cst`` remains **opt-in only**.
- ``run_workflow_1.py`` **unchanged** — still points to ``rfgun_single_pass``.
- No retry, inter-pass recovery, metric roles, staged search implemented.

## Validation status captured

| Area | Status |
|------|--------|
| no-CST tests | ``86/86`` (as of A17; ``87/87`` after A18 README test) |
| A13.4 — Full minimal live pass | Calibration success, measurement reached, Best F = -15185.95 |
| A14 — Frequency gate live smoke | ``frequency_gate_reject``, measurement skipped, Best F = 1.0 |
| A15 — S11 depth gate live smoke | ``s11_depth_gate_reject``, measurement skipped, Best F = 1.0 |
| A16 — Mixed gate precedence | Regression locked: cal failure > frequency > S11 depth |
| A17 — Multi-dip diagnostic status | Diagnostic-only, no live plumbing, compact S11 summaries only |

## Validation run

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
87/87 passed
```

**Live CST:** Not run. A18 is a documentation consolidation task; live smoke
reports are provided by A13.4/A14/A15.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** |
| CST project/result artifacts | **Not committed** |

## Notes / caveats

- This is **not** production validation.
- Future work remains: retry integration, inter-pass recovery, metric roles,
  adaptive bounds, staged search, live multi-dip plumbing, production-scale
  validation.
- Default root entry ``run_workflow_1.py`` still points to
  ``rfgun_single_pass`` and is intentionally not repointed.

## Commits

- Implementation/fix commit: ``HEAD`` — ``A18 consolidate rfgun_sao milestone README``
- Report commit: included in implementation commit (same hash)
- Final pushed HEAD: ``<filled after push>``
