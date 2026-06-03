# Phase B4.1 — Report-only diagnostics preservation hardening

## Summary

Harden report-only diagnostics preservation across two weak points identified
in B4 review: stale diagnostics surviving failed evaluations, and the
two-pass CST measurement runner dropping diagnostics from the returned
``EvaluationResult``.

## Stale diagnostics reset

**Problem:** ``_last_diagnostics`` was only set on successful evaluations.
A previous success could leave stale diagnostics that would be returned by
``adapt_for_retry`` after a subsequent failure.

**Fix:** Reset ``self._last_diagnostics = {}`` at the **start** of every
``evaluate_single_pass`` call, before any CST work begins.  Added a public
``last_diagnostics()`` accessor returning a copy of the diagnostics dict.

## Two-pass CST diagnostics preservation

**Problem:** ``make_cst_measurement_runner`` in ``two_pass_cst.py`` called
``evaluate_single_pass`` but did not preserve ``_last_diagnostics`` in the
returned ``EvaluationResult``.

**Fix:** After ``evaluate_single_pass``, read diagnostics via
``last_diagnostics()`` accessor (or fallback safely if the accessor doesn't
exist) and include them in the returned ``EvaluationResult(diagnostics=...)``.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/evaluator.py`` | Added ``self._last_diagnostics = {}`` reset at start of ``evaluate_single_pass``; added ``last_diagnostics()`` public accessor |
| ``workflows/rfgun_sao/two_pass_cst.py`` | Preserve diagnostics from evaluator in ``EvaluationResult`` returned by measurement runner |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section Y with 5 B4.1 tests |
| ``reports/restructure_plan/phase_B4_1_report_only_diagnostics_preservation.md`` | Created (this file) |

## Production code changed

- **evaluator.py**: 5 lines (reset + accessor).
- **two_pass_cst.py**: 5 lines (diagnostics extraction + preservation).

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "b4_1 or diagnostics or measurement_runner" -v --tb=short
11/11 passed (targeted — includes 5 new B4.1 + 6 existing report_only/measurement tests)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
147/147 passed (full suite)
```

## Live CST

- **Live CST run:** no
- **CST window closed:** N/A — no CST launched

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by B4.1 | no |

## Commit hashes

- B4.1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- Report-only diagnostics are now properly reset and preserved across all
  known code paths.
- Live CST validation of report-only diagnostics remains future work.
- JSONL sidecar for persisting diagnostics remains future work.
- Suggested next phase: Live CST smoke with metric roles (threshold penalty
  + report_only diagnostics), or README milestone update.
