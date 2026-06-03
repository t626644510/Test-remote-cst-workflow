# Phase D2.1 — Live CST hard-exit cleanup retry (attempted, blocked)

## Summary

Normal cleanup live CST smoke confirmed working (reused from D2).
Second Ctrl+C / hard-exit live validation was attempted again but remains
blocked by Windows signal-delivery constraints in non-interactive
environments.  The report is candid about what succeeded and what did not.

## Base commit

``4adfa4f41b8a7adc2a7e6c9a7536a92f56a64072`` (D2 attempted HEAD)

## Normal cleanup evidence (reused from D2)

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

| Property | Value |
|----------|-------|
| Best F | -17534.24 (successful measurement) |
| Cleanup line | ``CST cleanup: attempted=True closed=True pid=54584`` |
| DE PID 54584 after run | **Not found** |
| Visible DE window | **No** |
| Background ``cstd`` | PID 10184, no MainWindowTitle (licensing service) |
| Exit code | 0 |

**Verdict: ✅ Normal cleanup works correctly.**

## Hard-exit validation attempt

**Approach:** ``os.kill(pid, signal.CTRL_C_EVENT)`` with parent
process ignoring ``SIGINT`` so it can safely send signals to the child
without being killed itself.

**Parameters:**
- ``--n-initial 5 --n-iter 0`` (5 evaluations, ~3–4 min total window)
- Parent installed ``signal.signal(signal.SIGINT, signal.SIG_IGN)``
- Child started without ``CREATE_NEW_PROCESS_GROUP`` (same console)
- First ``os.kill`` sent after 35 s (during first solver run)
- Second ``os.kill`` sent 4 s later

**Observations:**
- Child PID printed, but no stdout/stderr was captured from the child
  process (empty output before force-kill timeout).
- ``os.kill(pid, signal.CTRL_C_EVENT)`` on Windows sends the signal to
  the entire console process group, not to a specific PID.  Despite the
  parent ignoring SIGINT, the delivery to the child was not reliable in
  this non-interactive context.
- The child remained alive and was force-killed by the timeout fallback.

**Root cause:** ``GenerateConsoleCtrlEvent`` (the underlying Windows API)
requires the calling process to be in the same console as the target.
In a headless / CI / non-interactive context, console-attach signalling
is unreliable.  This is a documented Windows limitation.

## Second Ctrl+C verdict

**❌ Blocked.**  Reliable automated Ctrl+C delivery to a child process
on Windows requires either:
- A visible interactive console where a human presses Ctrl+C, or
- ``GenerateConsoleCtrlEvent`` via P/Invoke with correct console
  attachment (fragile in non-interactive contexts).

**No success claim is made.**  The ``_handle_sigint_event`` logic
(cleanup call, exit code, exception safety) remains verified by
D1/D1.1 no-CST unit tests (13 tests in Section AJ).

## Files changed

| File | Action |
|------|--------|
| ``reports/restructure_plan/phase_D2_1_live_cst_hard_exit_cleanup_retry.md`` | Created (this file) |

No runtime code was modified. BRANCH_CONTEXT update deferred to remain
consistent with D2 status until a successful hard-exit live validation
is completed.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed
```

## Live CST

- **Live CST run:** yes (normal cleanup only)
- **Hard-exit live validation:** attempted-but-blocked
- **CST window closed:** yes (normal cleanup) | N/A for hard-exit path

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by D2.1 | no |

## Commit hashes

- D2.1 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
