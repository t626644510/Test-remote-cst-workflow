# Phase C3.3 — JSONL docs/status polish

## Summary

Close Phase C JSONL documentation and BRANCH_CONTEXT status: mark C3–C3.2
as Accepted, add C3.3, update authoritative behaviour, caveats, and next
directions, and add JSONL semantics subsection to README.  No runtime
behaviour changed.

## Base commit

``c911f2c79dfec138b08456be3c3684f76baf1a49`` (C3.2 accepted HEAD)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | C3–C3.2 → Accepted; added C3.3; added counter/authorship details to authoritative behaviour; cleaned up caveats and next directions |
| ``workflows/rfgun_sao/README.md`` | Added "JSONL evaluation records sidecar (C1–C3)" to implemented capabilities; updated future work entry |
| ``reports/restructure_plan/phase_C3_3_jsonl_docs_acceptance_polish.md`` | Created (this file) |

## Documentation updates

### BRANCH_CONTEXT

| Phase | Before | After |
|-------|--------|-------|
| C3 | Needs C3.1 fix | Accepted |
| C3.1 | Needs C3.2 counter fix | Accepted |
| C3.2 | Completed / pending review | Accepted |
| C3.3 | — | Completed / pending review |

Authoritative behaviour now includes per-path counter semantics.
Caveats updated to reflect completed enrichment and non-recovery status.
Next directions cleaned up (enrichment no longer listed as future).

### README

New subsection under implemented capabilities covers all C1–C3.2 JSONL
semantics: disabled by default, opt-in only, single_pass core-only,
two_pass enriched diagnostics/gate_results, non-fatal failures,
``.ckpt`` authoritative.

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
| ``.claude/settings.local.json`` modified by C3.3 | no |

## Commit hashes

- C3.3 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
