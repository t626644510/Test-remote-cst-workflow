# Phase B10.1 — Phase B docs polish

## Summary

Polish three documentation gaps found in B10 review:
1. Stale direction-validation sentence in README metric roles section.
2. Stale "Live gate rejection checkpoint evidence" in future work (B9 already validated live).
3. Missing B9 row in BRANCH_CONTEXT live evidence table.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/README.md`` | Fixed direction sentence: "validated for threshold and gate roles"; removed stale "Live gate rejection checkpoint evidence" from future work |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added B9 to live evidence table; removed gate role from next directions |
| ``reports/restructure_plan/phase_B10_1_phase_b_docs_polish.md`` | Created (this file) |

## Documentation fixes

| Issue | Fix |
|-------|-----|
| "Direction validated only for threshold role (B3)" | "Direction validated for threshold and gate roles; optimize/report_only do not use direction for scalar behaviour (B3, B7)" |
| "Live gate rejection checkpoint evidence" in future work | Removed — B9 already validated gate rejection live |
| B9 missing from BRANCH_CONTEXT live evidence | Added row with q0 raw, threshold, gate_reject error, cleanup evidence |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
184/184 passed
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
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by B10.1 | no |

## Commit hashes

- B10.1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- Phase B documentation is now consistent with accepted B9/B10 status.
- Next directions: JSONL diagnostics sidecar, Ctrl+C hardening, or a new topic.
