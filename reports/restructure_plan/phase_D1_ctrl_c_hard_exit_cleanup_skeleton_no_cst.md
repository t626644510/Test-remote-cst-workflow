# Phase D1 — Ctrl+C hard-exit cleanup skeleton (no-CST)

## Summary

Add a testable ``_handle_sigint_event`` helper to ``run.py`` that
performs best-effort ``_cleanup_workflow_connection(force=True)`` before
``_os._exit(130)`` on the second Ctrl+C.  The helper is wired into
``main()`` via a closure.  Normal completion and first Ctrl+C behaviour
are unchanged.

## Base commit

``2a0b9e68d2c5c7a954fdc3c5826cc95af5e90f0a``

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added ``_handle_sigint_event`` module-level helper; replaced inline ``_sigint_handler`` with call to helper |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AJ with 5 D1 tests |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added Phase D section with D1 table; updated caveats |
| ``workflows/rfgun_sao/README.md`` | Updated shutdown note to mention D1 best-effort second Ctrl+C cleanup |
| ``reports/restructure_plan/phase_D1_ctrl_c_hard_exit_cleanup_skeleton_no_cst.md`` | Created (this file) |

## Helper design

``_handle_sigint_event(ctrl_c_count, cleanup_func, exit_func, print_func, logger)``

| Event | Action |
|-------|--------|
| First Ctrl+C | Print "Waiting…" message. Do not cleanup or exit. |
| Second+ Ctrl+C | Call ``cleanup_func(force=True)`` (best-effort, exceptions caught). Then ``exit_func(130)``. |

In ``main()``, the helper is called with:
- ``cleanup_func=lambda force: _cleanup_workflow_connection(workflow, force=force)``
- ``exit_func=_os._exit``
- ``logger=_logger``

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "ctrl_c or d1" --tb=short
5/5 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
228/228 passed (full suite)

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
| ``.claude/settings.local.json`` modified by D1 | no |

## Commit hashes

- D1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
