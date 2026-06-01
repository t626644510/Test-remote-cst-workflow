# Phase A24.1 — CST shutdown cleanup and A24 report correction

## Summary

Correct the A24 report's inaccurate CST shutdown claim and close the
lingering CST Design Environment process that remained after the A24
live checkpoint evidence smoke.  No new live CST simulation was run.

## Reason for correction

A24 report stated: *"CST window closed: yes — the Python script exited,
releasing the COM reference. CST Design Environment was not left running."*

This was **incorrect**.  After the A24 evidence script exited, a ``cstd``
process (PID 38892) remained running with an active Design Environment
window.  The COM reference release does not always terminate the DE
process; the ``cstd`` background licensing service also auto-restarts,
which confused the original verification.

## CST shutdown cleanup

| Step | Detail |
|------|--------|
| **Before cleanup** | ``cstd`` PID 38892 running (active DE window). Also a child ``cstd`` process (PID 8352 parent). |
| **Cleanup method** | ``taskkill /PID 38892 /F /T`` — force-terminated the DE process tree. |
| **After cleanup** | A new ``cstd`` PID 22628 appears (auto-restarted licensing service). It has **no main window title** — verified via ``MainWindowTitle`` property. This is normal CST licensing daemon behavior. |
| **CST window closed after A24.1 cleanup** | **yes** — no visible DE window remains. |
| **Background service remaining** | ``cstd`` PID 22628 (no window, licensing only) — expected. |

## A24 report corrections

| Field in A24 report | Before (original) | After (A24.1 fix) |
|---------------------|-------------------|-------------------|
| ``CST window closed`` | ``yes`` (incorrect) | ``yes after A24.1 cleanup`` with reference to correction report |
| ``Evidence of shutdown`` | Claimed COM release closed DE | Described actual ``taskkill`` method and verified no-window state |
| ``Implementation/report commit`` | ``HEAD`` | ``786b7b1`` |
| ``Final pushed HEAD`` | "reported in final execution message" | ``786b7b1`` (superseded by A24.1) |

**A24 checkpoint evidence unchanged:** yes — the evidence script output
(``status=completed``, ``solver_ok=True``, ``error=''``, 7 metrics) is
unaffected by the shutdown correction.

## Files changed

| File | Action |
|------|--------|
| ``reports/restructure_plan/phase_A24_live_cst_checkpoint_evidence.md`` | Corrected shutdown section and commit hashes |
| ``reports/restructure_plan/phase_A24_1_cst_shutdown_correction.md`` | Created (this file) |

## Production code changed

**None.**

## Validation

- **No pytest run.** Report-only correction; no production code, tests, or
  README were modified.
- **Shutdown verification:** Used ``Get-Process`` to enumerate ``cstd``
  processes before and after cleanup.  Checked ``MainWindowTitle`` to
  distinguish DE windows from background licensing services.  The DE
  process (PID 38892) was confirmed terminated; the remaining ``cstd``
  (PID 22628) has no window title.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |

## Commit hashes

- A24 original report commit: ``786b7b1`` — ``Phase A24 rfgun_sao live CST checkpoint evidence``
- A24.1 correction commit: ``c1e8b7c`` — ``Phase A24.1 CST shutdown correction``
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: ``c1e8b7c``

## Caveats / follow-up

- A24 can now be **accepted** after the shutdown correction.  The checkpoint
  evidence itself (``status=completed``, ``solver_ok=True``, all 7 metrics)
  is unaffected and sufficient to validate A20–A22 hardened semantics.
- The ``cstd`` licensing background service auto-restarts after being killed;
  this is normal CST installation behaviour and does not indicate an open
  Design Environment.
- **Next phase suggestion:** README milestone update reflecting the
  completed A19–A24 checkpoint audit, hardening, live evidence, and
  shutdown correction cycle.
