# Phase D2.2 — Hard-exit validation blocked closeout

## Summary

Honest closeout of the D2 hard-exit live validation gap.  Normal cleanup
is validated.  Hard-exit Ctrl+C validation remains blocked because the
current local-agent execution environment lacks an interactive terminal
for manual Ctrl+C and Windows non-interactive signal delivery is
unreliable.  No further automation attempts were made.

## Base commit

``05cf5a2649b13f11c93415b939db0a560ce609cd`` (D2.1 HEAD)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | D2 → Partial; D2.1 → Attempted/blocked; added D2.2; updated status, caveats, next directions |
| ``reports/restructure_plan/phase_D2_2_hard_exit_validation_blocked_closeout.md`` | Created (this file) |

No runtime code was modified.

## Status

| Phase | Status |
|-------|--------|
| D2 | Partial — normal cleanup passed; hard-exit blocked |
| D2.1 | Attempted / blocked |
| D2.2 | Completed / pending review |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed
```

## Live CST

- **No new live CST run in D2.2.**  Prior normal cleanup evidence from
  D2 is reused (``CST cleanup: attempted=True closed=True pid=54584``,
  DE terminated, no visible window).
- **No live hard-exit success claim is made.**
- **No further non-interactive Ctrl+C automation was attempted.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Temp scripts committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by D2.2 | no |

## Commit hashes

- D2.2 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
