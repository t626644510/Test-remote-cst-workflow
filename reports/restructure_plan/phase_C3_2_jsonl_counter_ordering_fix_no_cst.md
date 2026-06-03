# Phase C3.2 — JSONL counter ordering fix (no-CST)

## Summary

Fix the two-pass enriched JSONL path where ``_eval_counter`` was
incremented twice per evaluation (once in ``_on_evaluation`` and once
in ``_enrichment_callback``), causing enriched JSONL iterations to start
at 1 and skip every other value.

## Base commit

``426a79477b6e5b4ce0ffd567914697a1fdbc7bd8`` (C3.1 HEAD before fix)

## Counter bug

In C3.1, ``_on_evaluation`` incremented ``_eval_counter`` unconditionally
even when ``use_enriched_jsonl=True``.  The ``_enrichment_callback`` also
incremented ``_eval_counter``.  Result: two evaluations produced iterations
``[1, 3]`` and final counter ``4`` instead of ``[0, 1]`` and ``2``.

## Fix

``_eval_counter`` increment moved inside the ``if not use_enriched_jsonl``
block in ``_on_evaluation``.  When ``use_enriched_jsonl=True``, only
``_enrichment_callback`` increments the counter.  Each evaluation now
increments exactly once, and iteration starts at 0 for both paths.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Moved ``_eval_counter[0] += 1`` into core-only branch |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AI with 4 C3.2 tests (mode gating, counter simulation, enriched callback call count) |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added C3.2 row; updated authoritative behaviour with counter semantics |
| ``reports/restructure_plan/phase_C3_2_jsonl_counter_ordering_fix_no_cst.md`` | Created (this file) |

## Counter semantics

| Mode | JSONL enabled | Counter advanced by | Result |
|------|---------------|---------------------|--------|
| ``single_pass`` | yes | ``_on_evaluation`` after core-only write | iteration 0, 1, 2… |
| ``two_pass`` | yes | ``_enrichment_callback`` after enriched write | iteration 0, 1, 2… |
| any | no | ``_on_evaluation`` (no write, no inc when enriched) | no JSONL |

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "c3 or counter or mode_gating" --tb=short
9/9 passed (targeted — includes C3 + C3.1 + C3.2)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
223/223 passed (full suite)

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
| ``.claude/settings.local.json`` modified by C3.2 | no |

## Commit hashes

- C3.2 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
