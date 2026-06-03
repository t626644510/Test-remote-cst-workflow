# Phase C3.4 — README JSONL policy cleanup

## Summary

Fix two stale ``evaluation_records.jsonl is not written`` statements in
README.md that contradicted the C2–C3.2 opt-in JSONL runtime writing.
Replaced with ``JSONL sidecar is opt-in only — see JSONL section``.
No runtime code was changed.

## Base commit

``492d78d64c7698cf25b872119efafe95e0d9f3f7`` (C3.3 HEAD before fix)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/README.md`` | Two stale ``not written`` statements replaced with ``opt-in only`` wording |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | C3.3 → Needs C3.4 README cleanup; added C3.4 row |
| ``reports/restructure_plan/phase_C3_4_readme_jsonl_policy_cleanup.md`` | Created (this file) |

## Stale wording fixed

| Location (before) | Location (after) |
|-------------------|------------------|
| Checkpoint persistence section: ``evaluation_records.jsonl`` is **not** currently written (A23 policy) | ``evaluation_records.jsonl`` is opt-in only — see JSONL sidecar section. |
| Metric roles section: ``evaluation_records.jsonl`` is **not** written; ``.ckpt`` is authoritative (A23) | ``.ckpt`` is authoritative; JSONL sidecar is opt-in only (see JSONL section) |

Both A23 historical references remain accurate for the time of A23 but no
longer describe current behaviour after C2–C3.2.

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "readme or jsonl or c3 or counter or mode_gating" --tb=short
30/30 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
223/223 passed

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
| ``.claude/settings.local.json`` modified by C3.4 | no |

## Commit hashes

- C3.4 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
