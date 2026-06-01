# Phase A23 — Report hash cleanup and evaluation_records policy

## Task

Clean up `HEAD` placeholders in A20/A21/A22 report commit-sections and
establish a clear policy for `evaluation_records.jsonl` in the
`workflows/rfgun_sao` two-pass path.

## Report hash cleanup

### A20 report (`phase_A20_two_pass_checkpoint_persistence_semantics.md`)

| Field | Before (committed) | After (A23 fix) |
|-------|-------------------|-----------------|
| Implementation commit | ``HEAD`` | ``c598ee2`` |
| Report/hash-fill commit | "included in implementation commit" | ``2a8ee2e`` |
| Final pushed HEAD | ``c598ee2`` | ``2a8ee2e`` |

Root cause: the report was committed in the same commit as the implementation,
so the implementation hash was unknown at write time.  The subsequent hash-fill
commit (``2a8ee2e``) updated the file but didn't correct all three fields.

### A21 report (`phase_A21_checkpoint_objective_names_hardening.md`)

| Field | Before (committed) | After (A23 fix) |
|-------|-------------------|-----------------|
| Implementation commit | ``HEAD`` | ``133fef3`` |
| Report/hash-fill commit | "included in implementation commit" | ``1344b00`` |
| Final pushed HEAD | ``133fef3`` | ``1344b00`` |

Same root cause as A20.

### A22 report (`phase_A22_checkpoint_metric_invariant_hardening.md`)

| Field | Before (committed) | After (A23 fix) |
|-------|-------------------|-----------------|
| A22 implementation commit | ``HEAD`` | ``167a6f5`` |
| A22 report/hash-fill commit | "included in A22 implementation commit" | ``e463723`` |
| Final pushed HEAD | ``167a6f5`` | ``e463723`` |

Same root cause.  The A22 report already had a note describing the A20/A21
situation and correctly listed their hashes; only the A22 own fields needed
fixing.

---

## `evaluation_records.jsonl` policy

### Audit result

`workflow.record_path` is set in two places in ``workflow.py``:

- Line 224 (two-pass branch)
- Line 387 (single-pass branch)

Both set it to ``os.path.join(log_dir, "workflow1", "evaluation_records.jsonl")``.

**No code in ``workflows/rfgun_sao/`` reads or writes this path.**  The path
is stored as an attribute on the workflow container for backward compatibility
— the legacy ``cst_optimization.workflows.recovery`` module does use a similar
``record_path`` to write a JSONL sidecar, but the ``rfgun_sao`` explicit
runner (``run.py``) does not.

### Policy decision: **Option A**

The ``.ckpt`` checkpoint (``CheckpointManager``) is the **authoritative
persisted evaluation record** for the ``workflows/rfgun_sao`` explicit runner.

| Question | Answer |
|----------|--------|
| Is ``evaluation_records.jsonl`` currently written by the two-pass path? | **No** |
| Is ``workflow.record_path`` used by any ``rfgun_sao`` code path? | **No** (set but unused) |
| Should a future phase implement a JSONL sidecar? | **Maybe** — not blocked by A23, but not required for current validation. |
| Is the ``.ckpt`` format sufficient for warm-start and crash recovery? | **Yes** (``CheckpointManager.get_warm_xy()`` works). |

No README changes were needed — the existing README does not claim that
``evaluation_records.jsonl`` is written by the two-pass path.

---

## Files changed

| File | Change |
|------|--------|
| ``reports/restructure_plan/phase_A20_two_pass_checkpoint_persistence_semantics.md`` | Fixed commit hashes (removed ``HEAD``, added hash-fill commit) |
| ``reports/restructure_plan/phase_A21_checkpoint_objective_names_hardening.md`` | Fixed commit hashes (removed ``HEAD``, added hash-fill commit) |
| ``reports/restructure_plan/phase_A22_checkpoint_metric_invariant_hardening.md`` | Fixed A22 own commit hashes (removed ``HEAD``, added hash-fill commit) |
| ``reports/restructure_plan/phase_A23_report_hash_cleanup_evaluation_records_policy.md`` | Created (this file) |

No production code was modified.

## Production code changed

**None.** This is a documentation / report-metadata cleanup phase only.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "readme" -v --tb=short
1 passed (README assertion still valid — no README changes)
```

No full test run needed — only report files and static documentation were
modified; no production code, tests, or README were touched.

**Live CST:** Not run. A23 is a documentation-only cleanup.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed to live runtime=cst | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |

## Commit hashes

Following the two-step submission strategy to avoid ``HEAD`` placeholders:

- Implementation/doc cleanup commit: ``f1b45e7`` — ``Phase A23 rfgun_sao report hash cleanup evaluation records policy``
- Report/hash-fill commit: ``(filled after hash-fill)`` — ``A23 report: fill commit hash``
- Final pushed HEAD: ``(filled after hash-fill and push)``

## Caveats / follow-up

- ``evaluation_records.jsonl`` is **not currently written** by the two-pass
  path.  The ``.ckpt`` checkpoint is authoritative.
- Live CST checkpoint evidence with the hardened semantics remains for a
  future phase.
- If a JSONL sidecar writer is desired in the future, it should be a
  separate phase with its own no-CST tests.
