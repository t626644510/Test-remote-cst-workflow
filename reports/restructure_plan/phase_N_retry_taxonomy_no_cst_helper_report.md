# Phase N — Retry taxonomy no-CST helper skeleton

## Summary

Implement retry taxonomy no-CST helpers: ``RetryFailureClass``,
``RetryEligibilityAction``, ``RetryPolicy``, ``RetryClassification``,
``classify_failure_record``, ``classify_retry_eligibility``,
``suggest_next_retry_tier``, ``should_escalate_to_probably_infeasible``,
and ``summarize_retry_classifications``.  No runtime retry, no durable
DB, no failure reuse, no CST.

## Base commit

``2193838d4e50517e92341da66b751d1c3a6b8275`` (Phase M accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/retry_taxonomy.py`` | New — retry taxonomy module with full enum, dataclass, and helper function set |
| ``tests/workflows/test_rfgun_sao_retry_taxonomy.py`` | New — 33 no-CST tests covering all classification and eligibility paths |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | M → Accepted; added N; next directions to N1/O |

## Retry taxonomy

| Component | Description |
|-----------|-------------|
| ``RetryFailureClass`` | 10 categories: SUCCESS, GATE_REJECTED, CALIBRATION_FAILED, SOLVER_FAILED, TRANSIENT_FAILED, UNKNOWN_FAILED, DIAGNOSTIC_ONLY, INCOMPATIBLE_SCHEMA, MISSING_PARAMETER_IDENTITY, UNSUPPORTED_STATUS |
| ``RetryEligibilityAction`` | 8 actions: NO_RETRY_SUCCESS, RETRY_ELIGIBLE, NO_RETRY_GATE_REJECTED, NO_RETRY_DIAGNOSTIC_ONLY, NO_RETRY_INCOMPATIBLE_SCHEMA, NO_RETRY_MISSING_IDENTITY, NO_RETRY_MAX_TIERS_REACHED, DEFER_PERMANENT_CLASSIFICATION |
| ``RetryPolicy`` | Safe defaults: max_tier=3, allow_unknown_retry=True, allow_gate_retry=False, enable_permanent_infeasible=False |
| ``RetryClassification`` | Result with failure_class, action, next_tier, reason, probably_infeasible (default False), should_count_failure, diagnostics |

### Eligibility rules

| Status | Default action | Tier | Permanent? |
|--------|---------------|------|-----------|
| SUCCESS | NO_RETRY_SUCCESS | 0 | N/A |
| GATE_REJECTED | NO_RETRY_GATE_REJECTED | 0 | No |
| DIAGNOSTIC_ONLY | NO_RETRY_DIAGNOSTIC_ONLY | 0 | No |
| INCOMPATIBLE_SCHEMA | NO_RETRY_INCOMPATIBLE_SCHEMA | 0 | No |
| MISSING IDENTITY | NO_RETRY_MISSING_IDENTITY | 0 | No |
| CALIBRATION/SOLVER/TRANSIENT/UNKNOWN (retries < max) | RETRY_ELIGIBLE | retry_count+1 | No |
| Retries ≥ max_tier | NO_RETRY_MAX_TIERS_REACHED | 0 | **False** (not permanent) |
| ``should_escalate_to_probably_infeasible`` | — | — | Only when explicitly enabled + threshold met |

### Probably-infeasible guard

``should_escalate_to_probably_infeasible`` returns ``False`` under
default policy.  When enabled, requires at least ``permanent_failure_threshold``
non-transient, non-gate failures.  Not used for runtime skip in Phase N.

## Validation

```
$ python -m compileall workflows/rfgun_sao/retry_taxonomy.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short -v
33/33 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short
22/22 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_dedup.py --tb=short
18/18 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py --tb=short
23/23 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

Total: **337 passed**.

## Explicit statements

- **No CST run.**
- **No runtime retry/recovery implemented.**
- **No durable DB.**
- **No failure reuse.**
- **No JSONL sidecar read/reference.**
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
| ``.claude/settings.local.json`` modified by Phase N | no |

## Commit hashes

- Phase N implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
