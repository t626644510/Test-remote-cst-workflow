# Phase B6 — Phase B milestone README / branch-context update

## Summary

Update ``workflows/rfgun_sao/README.md`` and ``BRANCH_CONTEXT.md`` to
document the completed Phase B metric roles milestone (B1–B5.1).  No
runtime behaviour was changed; no live CST was run.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/README.md`` | Updated test count (107/107 → 158/158); added B5 live smoke to live CST table; added B1–B5.1 to no-CST/policy/hardening table; added "Metric roles" section to implemented capabilities; removed "Metric roles" from future work; updated live CST shutdown note to reflect B5.1 automatic cleanup |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Complete rewrite — consolidated core rules, documented Phase A and Phase B status with completion tables, authoritative behaviour, live evidence, known caveats, and next possible directions |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Updated ``test_rfgun_sao_readme_status_current_after_a25`` → ``_after_b6``; changed ``107/107`` → ``158/158``; added B1–B5.1 assertions |
| ``reports/restructure_plan/phase_B6_metric_roles_milestone_readme.md`` | Created (this file) |

## Documentation updates

### README metric role semantics now documented

- **optimize** — in objective_names, checkpoint arrays, penalty via mode.compute.
- **threshold** — in objective_names, checkpoint arrays, penalty via threshold formula.
- **report_only** — excluded from objective_names/checkpoint, surfaced as
  ``EvaluationResult.diagnostics``, logged in two-pass path, ``report_as`` alias.
- ``evaluation_records.jsonl`` not written; ``.ckpt`` authoritative.

### BRANCH_CONTEXT.md consolidated

- Core rules expanded (7 rules, including config.local.yaml and licensing service).
- Phase A summary (closed through A25.1).
- Phase B completion table with 7 phases, authoritative behaviour, live evidence,
  known caveats, and next directions.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
158/158 passed
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
| ``.claude/settings.local.json`` modified by B6 | no |

## Commit hashes

- B6 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- Phase B metric roles **milestone can be closed** after B6 documentation.
- Next possible directions: gate role skeleton, JSONL diagnostics sidecar,
  Ctrl+C hard-exit cleanup hardening, or additional live CST regression smoke.
