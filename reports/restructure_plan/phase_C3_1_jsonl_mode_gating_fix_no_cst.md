# Phase C3.1 — JSONL mode gating fix (no-CST)

## Summary

Fix C3's single_pass regression where JSONL core-only writes were
suppressed when JSONL was enabled.  A new ``_should_use_enriched_jsonl``
helper now gates the enriched callback correctly: two_pass + enabled →
use enriched callback; single_pass + enabled → use core-only fallback.
Counter is incremented exactly once per evaluation.

## Base commit

``2e8ffed93b207b88f29d6c8c1b6d5efdad32d33a`` (C3 HEAD before fix)

## C3 regression

C3 used ``records_cfg.get("enabled")`` as the condition to skip core-only
writes in ``_on_evaluation``, which also suppressed writes for single_pass
mode.  C3.1 replaces this with an explicit mode check.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added ``_should_use_enriched_jsonl(cfg, records_cfg) → bool`` helper; fixed ``_on_evaluation`` to skip core-only write only when enriched callback will be used; fixed duplicate counter issue |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Renamed C3 test to ``test_c3_jsonl_sidecar_diagnostics_included``; added Section AH with 5 mode gating tests |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | C3 → Needs C3.1 fix; added C3.1 row; updated authoritative behaviour to describe both paths |
| ``reports/restructure_plan/phase_C3_1_jsonl_mode_gating_fix_no_cst.md`` | Created (this file) |

## Mode gating logic

| Mode | JSONL config | Callback | Behaviour |
|------|-------------|----------|-----------|
| ``single_pass`` | disabled | None | No JSONL written |
| ``single_pass`` | enabled | None | Core-only JSONL via ``_on_evaluation`` |
| ``two_pass`` | disabled | None | No JSONL written |
| ``two_pass`` | enabled | ``_enrichment_callback`` | Enriched JSONL (diagnostics + gate_results); core-only write skipped |

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "c3 or mode_gating" --tb=short
12/12 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
219/219 passed (full suite)

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
| ``.claude/settings.local.json`` modified by C3.1 | no |

## Commit hashes

- C3.1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
