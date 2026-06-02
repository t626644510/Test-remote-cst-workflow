# Phase D1.2 — BRANCH_CONTEXT cleanup

## Summary

Remove the stray D1 row from the Phase C table in BRANCH_CONTEXT.md.
Phase C now correctly lists only C1–C3.5.  D1 and D1.1 marked Accepted;
D1.2 added.  No runtime code was changed.

## Base commit

``d6fd98d77fb224d26d3ab6c9ff282022f880086b`` (D1.1 HEAD before fix)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Removed D1 row from Phase C table; D1.1 → Accepted; added D1.2 row; updated Phase D status |
| ``reports/restructure_plan/phase_D1_2_branch_context_cleanup.md`` | Created (this file) |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

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
| ``.claude/settings.local.json`` modified by D1.2 | no |

## Commit hashes

- D1.2 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
