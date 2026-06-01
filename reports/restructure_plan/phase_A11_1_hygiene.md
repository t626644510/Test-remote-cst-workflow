# Phase A11.1 — Hygiene & readability for rfgun_sao two-pass placeholder

## Task

Hygiene-only cleanup for `workflows/rfgun_sao/` after A11 two-pass runtime
placeholder was merged.  No behaviour changes, no CST interaction, no config
changes.

**Scope:**
1. README.md — remove duplicate A11 bullet, clarify placeholder-only status.
2. workflow.py — drop unused local variables from two-pass branch.
3. test_rfgun_sao_imports.py — deduplicate import, add spacing, extract
   `_minimal_two_pass_cfg()` helper, keep test count stable.

## Summary

All three target files were cleaned without altering runtime behaviour.
Single-pass path is untouched; two-pass placeholder still returns penalty 1.0,
creates no CST connection, and leaves `workflow._conn = None`.

## Files changed

| File | Action |
|---|---|
| `workflows/rfgun_sao/README.md` | Consolidated duplicate A11 bullets into one; clarified placeholder-only status |
| `workflows/rfgun_sao/workflow.py` | Removed two unused local variables (`param_names`, `weights`) from two-pass branch |
| `tests/workflows/test_rfgun_sao_imports.py` | Deduplicated `import numpy as np`; added blank lines between test functions; extracted `_minimal_two_pass_cfg()` helper |
| `reports/restructure_plan/phase_A11_1_hygiene.md` | Created (this file) |

## Behavioural changes

**None.** All changes are cosmetic / readability:
- README text deduplication only.
- Two unused variables in `workflow.py` (two-pass branch) removed; builder
  output (`workflow`, `optimizer`, `placeholder_eval`) is identical.
- Test file: same 53 tests, same intent, same coverage.

**Protected areas confirmed unchanged:**

| Area | Status |
|---|---|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `config.local.yaml` | **Not modified / not committed** |

**two_pass placeholder invariant:** `workflow._conn is None` still holds;
no CST connection is created.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
# … 53/53 passed (see result below)

$ git diff --name-only
workflows/rfgun_sao/README.md
workflows/rfgun_sao/workflow.py
tests/workflows/test_rfgun_sao_imports.py
reports/restructure_plan/phase_A11_1_hygiene.md
```

## Notes / caveats

- two_pass placeholder evaluator still returns constant penalty 1.0; actual
  CST calibration / measurement execution is not implemented and remains
  **not physically meaningful**.
- `_minimal_two_pass_cfg()` helper is defined at module level in the test
  file; it is **not** importable from the production package — it is a test
  helper only.
- No new tests were added; the same 53 tests pass as before.

## Commit hash

```
21a76b9
```
