# Phase B5.1 — CST shutdown detection and cleanup hardening

## Summary

Add best-effort CST connection cleanup to the explicit runner
(``run.py``) so that live runs do not leave a CST Design Environment
window open.  A ``_cleanup_workflow_connection`` helper handles normal
and force-close paths, and a ``finally`` block ensures cleanup runs
after every ``opt.optimize()`` call (success, interrupt, or exception).

**Correction to B5 shutdown evidence:** B5 role-metrics validation
remains accepted, but B5's shutdown evidence was stale/inaccurate
because a CST window remained open after the B5 report was uploaded.
B5.1 is the concrete fix for this.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added ``_cleanup_workflow_connection()`` helper; wired into ``main()`` via ``finally`` block after ``opt.optimize()`` |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AA with 7 B5.1 tests |
| ``reports/restructure_plan/phase_B5_1_cst_shutdown_cleanup.md`` | Created (this file) |

## Production code changed

**``run.py`` only.** 25 lines added (helper + finally block).  No change
to evaluator, workflow builder, checkpoint, or ``src/cst_optimization/``.

## Helper: ``_cleanup_workflow_connection(workflow, *, force=False) -> dict``

| Scenario | ``attempted`` | ``closed`` | ``error`` |
|----------|--------------|------------|-----------|
| ``workflow`` is ``None`` | ``False`` | ``False`` | ``""`` |
| No ``_conn`` attribute | ``False`` | ``False`` | ``""`` |
| ``_conn`` is ``None`` | ``False`` | ``False`` | ``""`` |
| ``conn.close()`` succeeds | ``True`` | ``True`` | ``""`` |
| ``conn.close()`` raises | ``True`` | ``False`` | ``"message"`` |
| ``conn.pid`` raises | ``True`` | ``True`` (if close works) | ``""`` |
| ``force=True`` | ``True`` | passes ``force=True`` to ``close()`` | — |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "cleanup_workflow" -v --tb=short
7/7 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
158/158 passed (full suite — all existing + 7 new)
```

## Live CST cleanup verification

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml
    --n-initial 1 --n-iter 0
```

**Optimisation result:** Best F = -17534.24 (successful measurement) ✅

**Cleanup output:**
```
CST cleanup: attempted=True closed=True pid=50700
```

**CST process state:**

| Before run | After run | Notes |
|------------|-----------|-------|
| Licensing ``cstd`` PID 10184 (no window) | Same PID 10184 (no window) | Normal licensing service — should not be killed |
| — | DE PID 50700 started during run | Successfully terminated by ``close()`` |
| — | DE PID 50700 not found after cleanup | ✅ Confirmed via ``Get-Process -Id 50700`` |

**CST window closed: yes.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by B5.1 | no |

## Commit hashes

- B5.1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- The ``connection.py`` warning ``DesignEnvironment.close() hung — abandoning COM thread``
  may still appear in the log, but the DE process was confirmed terminated after cleanup.
- Background ``cstd`` licensing service (no window) remains after cleanup — this is
  normal CST installation behavior and must not be confused with an open DE window.
- Live runs after B5.1 will report ``CST cleanup: attempted=True closed=True pid=<PID>``.
- Suggested next phase: README milestone update for Phase B, or gate role implementation.
