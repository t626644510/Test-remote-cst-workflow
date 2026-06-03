# Phase L1 — Warm-start/prior semantics hardening

## Summary

Harden evaluation database warm-start/prior construction semantics:
``record_to_prior_candidate`` now enforces the same eligibility checks
as ``classify_record_for_prior``; diagnostic-only classification is made
reachable; 9 new no-CST tests cover the blocking issues.  No durable DB,
no JSONL sidecar read, no CST.

## Base commit

``797f1b6b973133665baa1a98e732113f11a659e1`` (Phase K accepted HEAD)

## Previous Phase L HEAD

``e41335290813b1a57ebaee99dd4e9f8223d63d56`` (blocking issues fixed by L1)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/evaluation_database_warm_start.py`` | ``record_to_prior_candidate`` now calls ``classify_record_for_prior``; added ``_is_diagnostic_only`` detection; added ``current_schema``/``require_raw_metrics`` params; bulk builder passes both to converter |
| ``tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py`` | Added 9 L1 tests: incompatible schema rejection, payload requirements, objective-values-only, provenance, diagnostic-only (status + error_taxonomy), UNKNOWN_FAILED not diagnostic, JSONL sidecar not referenced |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | L → Needs L1 hardening; added L1; updated Phase E constraints; cleaned next directions to M/N/O+ |

## Blocking issues fixed

| Issue | Fix |
|-------|-----|
| ``record_to_prior_candidate`` bypassed eligibility checks | Now calls ``classify_record_for_prior`` internally; returns ``None`` for ineligible records |
| ``diagnostic_only`` status was unreachable | Added ``_is_diagnostic_only`` detection (checks status string and error_taxonomy category) before generic failure classification |
| ``build_prior_candidates_from_records`` could create candidates with different eligibility than ``classify_record_for_prior`` | Now passes ``current_schema`` and ``require_raw_metrics`` to both classify and convert |
| Missing test: direct helper rejects incompatible schema | Added ``test_rejects_incompatible_schema`` |
| Missing test: objective-values-only SUCCESS is usable | Added ``test_objective_values_only_is_usable`` |
| Missing test: diagnostic-only classification | Added ``test_diagnostic_only_ignored`` and ``test_diagnostic_only_via_error_taxonomy`` |
| Missing test: JSONL sidecar not referenced | Added ``test_warm_start_does_not_reference_jsonl`` (static source inspection) |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py --tb=short -v
23/23 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short
22/22 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_dedup.py --tb=short
18/18 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

## Explicit statements

- **No CST run.** No durable DB. No JSONL sidecar read/reference.
- **No optimizer/runtime warm-start injection.**
- **No retry/failure reuse.**
- **No root shim repoint.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase L1 | no |

## Commit hashes

- Phase L1 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
