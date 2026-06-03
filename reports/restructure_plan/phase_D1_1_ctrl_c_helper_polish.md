# Phase D1.1 — Ctrl+C helper polish

## Summary

Polish the ``_handle_sigint_event`` helper: add ``return`` after
``exit_func(130)`` to prevent fall-through to waiting message; add
``print_func`` fallback when ``logger is None``; add no-duplicate-waiting
and cleanup-failure-fallback tests; clean up BRANCH_CONTEXT table
structure (Phase C table no longer references D1).

## Base commit

``14b3eb6ffaf3458be8c65f20feb9e64f560b7569`` (D1 accepted HEAD)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added ``return`` after ``exit_func(130)``; added ``print_func`` fallback for cleanup failure when logger is None |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added no-duplicate-waiting assertion to second-event test; added cleanup-failure fallback test; hardened cleanup raises test |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | D1 → Accepted; added D1.1; Phase C status line cleaned (closed through C3.5, no D1 reference) |
| ``reports/restructure_plan/phase_D1_1_ctrl_c_helper_polish.md`` | Created (this file) |

## Validation

```
$ python -m compileall workflows/rfgun_sao
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "ctrl_c or sigint or cleanup or d1" --tb=short
13/13 passed (targeted — includes 8 D1 + 5 D1.1)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed (full suite)

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
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
| Generated JSONL/ckpt/logs committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by D1.1 | no |

## Commit hashes

- D1.1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
