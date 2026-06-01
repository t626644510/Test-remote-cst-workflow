# Phase A25 — rfgun_sao README milestone update after checkpoint audit and live evidence

## Summary

Update ``workflows/rfgun_sao/README.md`` and the static README assertion test
to reflect the A19–A24.1 checkpoint audit / hardening / live evidence cycle.
No production code was changed; no live CST was run.

## README changes

| Section | Change |
|---------|--------|
| no-CST test count | ``86/86 as of A17`` → ``107/107 as of A22``; added checkpoint hardening to test suite description |
| Live CST validation table | Added rows for A19 (audit), A20 (persistence fix), A21 (names hardening), A22 (invariant hardening), A23 (policy), A24 (live evidence), A24.1 (shutdown correction) |
| Implemented capabilities | Added "Checkpoint persistence" section: ``_record_checkpoint_evaluation`` helper, completed-record semantics, metric name validation, ``.ckpt`` authoritative, live evidence reference |
| Not implemented yet / future work | Added ``evaluation_records.jsonl`` sidecar writer, live gate rejection checkpoint evidence |
| Local CST config | Added "Live CST shutdown note" explaining that Python exit may not close the DE process; references A24.1 report |
| Overclaim avoidance | No change needed — existing text already qualifies ``rfgun_sao`` as experimental and ``runtime=cst`` as opt-in |

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/README.md`` | Updated no-CST count, live table, implemented capabilities, future work, shutdown note |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Updated ``test_rfgun_sao_readme_status_current_after_a18`` → ``...after_a25``; added assertions for A19–A24.1, ``.ckpt``, ``evaluation_records.jsonl`` |
| ``reports/restructure_plan/phase_A25_rfgun_sao_checkpoint_milestone_readme.md`` | Created (this file) |

## Production code changed

**None.**

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "readme" -v --tb=short
2/2 passed  (multi-dip + updated status assertion)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
107/107 passed
```

## Live CST

- **Live CST run:** no
- **CST window closed:** N/A — no CST launched

## A24.1 metadata caveat

A24.1 report's own final HEAD field was updated in hash-fill commit
``22b79d4``, which supersedes the correction commit ``c1e8b7c``.  No
further hash-only commits are needed for A24.1.

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

- Implementation/doc commit: ``(filled after commit)`` — ``Phase A25 rfgun_sao checkpoint milestone README``
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- The **checkpoint milestone can be considered closed** after A25:
  audit (A19), fix (A20), hardening (A21, A22), policy (A23), live
  evidence (A24), shutdown correction (A24.1), and README documentation
  (A25) are complete.
- **Next phase suggestion:** Choose next consolidation topic — JSONL
  sidecar implementation, live gate rejection checkpoint evidence, or
  another area (metric roles, inter-pass recovery, etc.).
