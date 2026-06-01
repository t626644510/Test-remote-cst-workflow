# Phase A25.1 — README validation taxonomy cleanup

## Summary

Restructure the ``Validated so far`` section in ``workflows/rfgun_sao/README.md``
to clearly separate live CST smokes from no-CST / policy / hardening milestones.
No production code was changed; no live CST was run.

## Reason for correction

A25 placed all A19–A24.1 phases under the heading ``Live CST two-pass (opt-in
runtime=cst)``, making no-CST audits and doc/policy phases appear as live CST
validations.  The note *"Each live smoke used a valid local CST project..."*
did not apply to A16–A23 or A24.1.

## README changes

| Change | Before | After |
|--------|--------|-------|
| Table heading | ``Live CST two-pass (opt-in runtime=cst)`` — single table | Split into **Live CST smokes** (4 rows) and **No-CST / policy / hardening milestones** (8 rows) |
| Table columns | Phase / Validation / Result | Phase / Type / Validation / Result |
| Type column | Implicit from heading | Explicit: ``Live CST``, ``no-CST regression``, ``no-CST audit``, ``no-CST fix``, ``no-CST hardening``, ``policy / docs``, ``shutdown correction`` |
| Live smoke scope note | Below combined table | Below **Live CST smokes** table only — no longer applies to no-CST / policy phases |
| A24.1 classification | Implicitly a live smoke | Explicit ``shutdown correction`` — not a new live smoke |
| A24 result | Listed as partial in combined table | Clear: ``status=completed`` line moved to live CST table |
| Checkpoint milestone content | Present | Preserved unchanged |

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/README.md`` | Split validation table, added ``Type`` column, scoped live-smoke note |
| ``reports/restructure_plan/phase_A25_1_readme_validation_taxonomy_cleanup.md`` | Created (this file) |

## Production code changed

**None.**

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "readme" -v --tb=short
2/2 passed
```

All existing README assertions (``107/107``, A19–A24.1, ``.ckpt``,
``evaluation_records.jsonl``, ``runtime=cst``, etc.) remain satisfied by the
restructured text.

## Live CST

- **Live CST run:** no
- **CST window closed:** N/A — no CST launched

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

- A25.1 correction commit: actual hash reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- **README milestone can be accepted** after taxonomy cleanup.
- **Checkpoint milestone is closed** (A19–A24.1 + A25 + A25.1).
- Next phase options: JSONL sidecar implementation, live gate rejection
  checkpoint evidence, metric roles, inter-pass recovery, or another topic.
