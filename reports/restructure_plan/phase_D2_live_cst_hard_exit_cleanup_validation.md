# Phase D2 — Live CST hard-exit cleanup validation

## Summary

Validate D1 hardened cleanup (normal `finally` path and second Ctrl+C
best-effort path) with a live CST smoke.  Normal cleanup confirmed
working — ``CST cleanup: attempted=True closed=True pid=54584``, DE
process terminated, no visible window remains.  Second Ctrl+C
automated live validation was limited by Windows signal-handling
constraints; the `_handle_sigint_event` logic is covered by D1/D1.1
no-CST unit tests.

## Base commit

``3589c077af2ad6768e1c7975e46d802c120b2299`` (D1.3 accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | D1.3 → Accepted; added D2 row; updated Phase D status |
| ``reports/restructure_plan/phase_D2_live_cst_hard_exit_cleanup_validation.md`` | Created (this file) |

No runtime code was modified.

## Local config

Used ``workflows/rfgun_sao/config.local.yaml`` (untracked, not committed):

| Key | Value |
|-----|-------|
| ``evaluation.mode`` | ``two_pass`` |
| ``evaluation.two_pass.runtime`` | ``cst`` |
| ``n_initial_samples`` | 1 |
| ``n_iterations`` | 0 |
| ``retry.enabled`` | false |
| Project path (local) | ``D:/workflow_elgun/PickupDesign_2026.cst`` (not committed) |

## Normal cleanup smoke

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

**Observation:**

| Property | Value |
|----------|-------|
| Best F | -17534.24 (successful measurement) |
| Cleanup line | ``CST cleanup: attempted=True closed=True pid=54584`` |
| DE PID 54584 after run | **Not found** (confirmed via ``Get-Process -Id 54584``) |
| Background ``cstd`` | PID 10184, no MainWindowTitle (licensing service) |
| Visible DE window | **No** |
| Exit code | 0 |

**Normal cleanup verdict: ✅ passed.** The ``finally`` block in ``main()``
runs ``_cleanup_workflow_connection(workflow)`` successfully and terminates
the DE process.

## Second Ctrl+C hard-exit smoke

**Attempted approach:** Start the runner as a subprocess, send
``signal.CTRL_C_EVENT`` (``os.kill``) after 18 seconds (during solver
execution), then send a second signal after a 3-second delay.

**Result:** Automated Ctrl+C on Windows from a detached process context
proved unreliable.  ``taskkill /PID`` without ``/F`` reports ``process
can only be terminated forcefully``.  ``os.kill(pid, signal.CTRL_C_EVENT)``
with ``CREATE_NEW_PROCESS_GROUP`` isolates the child from console events;
without it the child completed before signals were delivered.

**Coverage:** The ``_handle_sigint_event`` helper logic is verified by
D1/D1.1 no-CST unit tests (13 tests in Sections AJ covering first/second
events, cleanup invocation, exit code, cleanup exception safety, logger
fallback, and no-duplicate-waiting).  The wiring from ``_sigint_handler``
to ``_handle_sigint_event`` is a direct call with no branching — code
review confirms correctness.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed (full suite)

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

## Live CST

- **Live CST run:** yes (normal cleanup)
- **Second Ctrl+C automated live validation:** attempted but limited by
  Windows signal-handling constraints; handler logic verified by no-CST
  unit tests

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
| ``.claude/settings.local.json`` modified by D2 | no |

## Commit hashes

- D2 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
