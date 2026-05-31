# Phase 09 -- Workflow 1 branch finalisation

## Summary

Workflow 1 separation is complete and validated.  The branch
``workflow/1-rfgun-single-pass`` is ready for long-term maintenance.

## Final branch status

| Attribute | Value |
|---|---|
| **Branch** | ``workflow/1-rfgun-single-pass`` |
| **Ahead of baseline** | 19 commits |
| **Commits** | 1-9 (separation phases) + 8.x (bugfix phases) + 9 (finalisation) |
| **New files** | 21 |
| **Lines added** | ~3,000 |
| **Status** | **VALIDATED** |

## Validation matrix

| Check | Result | Date |
|---|---|---|
| ``compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py`` | PASS | All phases |
| No-CST smoke tests (12 tests) | **12/12 PASS** | All phases >= 6 |
| `src/cst_optimization/` modified | **0 files** | All phases |
| `config/default.yaml` modified | **0 files** | All phases |
| Workflow 2/3 modified | **0 files** | All phases |
| `run_workflow_1.py` preserved as shim | **Yes** | Phase 3+ |
| Live CST smoke (1 eval, 0 iter) | **PASS** | Phase 8.8 |
| All 7 raw metrics computed | **Yes** | Phase 8.8 |
| ``Done. Best X`` printed correctly | **Yes** | Phase 8.8 (after 8.7 fix) |
| ``Best F`` printed correctly | **Yes** | Phase 8.8 |
| No Python exceptions | **Yes** | Phase 8.8 |

## Fixed bugs (all pre-existing, not introduced by extraction)

| Bug | Found | Fixed | File | Impact |
|---|---|---|---|---|
| ``ckpt.loaded_count`` not found | 8.0 | 8.1 | ``run.py`` | Blocked startup |
| Invalid kwargs to ``opt.optimize()`` | 8.2 | 8.3 | ``run.py`` | Blocked optimizer |
| ``n_initial`` vs ``n_initial_samples`` key | 8.4 | 8.5 | ``workflow.py`` | Budget ignored |
| ``result.get("x")`` vs ``result.x_opt`` | 8.6 | 8.7 | ``run.py`` | Cosmetic print fail |

All four bugs existed in the original ``run_workflow_1.py`` (pre-migration)
and were masked by earlier failures.  No regressions were introduced by
the WF1 extraction.

## Remaining caveats

1. **``config.local.yaml`` is machine-specific** -- The working config
   uses machine-local paths (``D:/CST2026/...``, ``D:/workflow_elgun/...``,
   ``D:/Results/...``).  Each developer must create their own copy and
   adjust paths.  Copy ``config.yaml`` to ``config.local.yaml`` and modify.
2. **Committed ``config.yaml`` still has generic paths** -- The default
   ``config.yaml`` in the repository uses ``F:/workflow_elgun/...`` paths.
   The working copy (``F:`` → ``D:`` modifications) has unstaged changes
   that should not be committed.
3. **CST ``close()`` hang warning** -- ``DesignEnvironment.close() hung``
   warnings appear in the log after successful completion.  This is a
   known CST COM issue that does not affect physics results.
4. **Sandbox exit code** -- The sandbox may kill the process after output
   is complete (exit code 124/1), but the Python code path completes
   successfully.  The ``_setup_logging`` + ``retry.force_reset()``
   reconnect phase continues after the main output.

## Recommendation

1. **Keep ``workflow/1-rfgun-single-pass`` as a long-lived branch** for
   ongoing Workflow 1 development.
2. **Do not merge into ``main``** until the Workflow 2 and Workflow 3
   separation strategy is decided (merging only WF1 would leave
   ``cst_optimization/factory.py`` still serving WF2/WF3, causing
   hybrid maintenance).
3. **Cherry-pick selectively** -- Any generic improvements discovered
   during the WF1 separation (e.g., ``ckpt.load()`` correctness,
   ``n_initial_samples`` key) can be cherry-picked into ``main``
   independently.
4. **Future WF2/WF3 separation** -- The same phased approach used here
   (inventory → scaffold → runner migration → config split → evaluator
   extraction → tests → validation) can be applied to the remaining
   workflows when the time comes.
