# Phase E — Workflow3 capability migration design / context cleanup

## Summary

Create the Workflow3 capability migration design document, clean up stale
Phase B caveats in BRANCH_CONTEXT, and add a migration plan subsection to
README.  No runtime code changed.  No live CST run.

## Base commit

``a688058066a1fe7cafefc87df76c163a495be63c``

## Files changed

| File | Change |
|------|--------|
| ``reports/restructure_plan/phase_E_workflow3_capability_migration_design.md`` | New — comprehensive design document (legacy summary, gap matrix, staged search, adaptive bounds, retry/recovery, evaluation database, provenance, budget, phase order) |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | D2.7 → Accepted; Phase D status closed; Phase B caveats replaced with historical note; added Phase E section |
| ``workflows/rfgun_sao/README.md`` | Added "Workflow3 capability gap / migration plan" subsection |
| ``reports/restructure_plan/phase_E_workflow3_capability_migration_design_report.md`` | Created (this file) |

## BRANCH_CONTEXT cleanup

- **Phase B caveats:** removed 6 stale items (``evaluation_records.jsonl not written``, ``JSONL diagnostics sidecar remains future``, ``Second Ctrl+C / _os._exit bypasses cleanup``, ``Ctrl+C hard-exit cleanup hardening remains future``) — replaced with a single historical note referencing Phase C/D.
- **Phase D:** D2.7 → Accepted; status line updated to ``closed through D2.7``.
- **Phase E:** New section with migration constraints and next phase directions.

## Explicit statements

- **No runtime code changed.**
- **No live CST run.**
- **No root shim repoint.**
- **No evaluation database / staged search / adaptive bounds / retry implementation yet.**

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed
```

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase E | no |

## Commit hashes

- Phase E implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
