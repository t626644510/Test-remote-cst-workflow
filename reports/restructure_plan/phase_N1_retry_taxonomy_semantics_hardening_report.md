# Phase N1 — Retry taxonomy semantics hardening

## Summary

Harden the ``should_escalate_to_probably_infeasible`` guard with strict
parameter identity, failure class, and threshold requirements.  Add 17
regression tests covering all escalation-blocking scenarios.  No runtime
retry, no durable DB, no failure reuse, no CST.

## Base commit

``2193838d4e50517e92341da66b751d1c3a6b8275`` (Phase M accepted HEAD)

## Previous Phase N HEAD

``4e179e07db13ffc469f967a846566c7357c2cd05`` (blocking issues fixed by N1)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/retry_taxonomy.py`` | Added ``_record_parameter_key``, ``_is_stable_permanent_candidate_class``; rewrote ``should_escalate_to_probably_infeasible`` with identity/class/threshold checks |
| ``tests/workflows/test_rfgun_sao_retry_taxonomy.py`` | Added 17 N1 tests covering threshold-met positive, default false, mixed identities, mixed classes, transient/gate/success/diagnostic-only/missing/incompatible blocking, JSONL non-reference |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | N → Needs N1 hardening; added N1 row |

## Blocking issue fixed

**Problem:** ``should_escalate_to_probably_infeasible`` only excluded
transient/gate/success.  Mixed identities, diagnostic-only, missing
identity, incompatible schema, and unsupported status could all
contribute to escalation.

**Fix:** All records must now satisfy:
1. Compatible schema
2. Non-missing ``parameter_identity``
3. **Same** ``parameter_key`` across all records
4. Classification as ``CALIBRATION_FAILED``, ``SOLVER_FAILED``, or
   ``UNKNOWN_FAILED`` (only if ``allow_unknown_retry=True``)
5. Excluded classes: ``TRANSIENT_FAILED``, ``GATE_REJECTED``,
   ``SUCCESS``, ``DIAGNOSTIC_ONLY`` (status or error_taxonomy),
   ``INCOMPATIBLE_SCHEMA``, ``MISSING_PARAMETER_IDENTITY``,
   ``UNSUPPORTED_STATUS``

Additionally:
- ``permanent_failure_threshold`` is clamped to ``max(threshold, 2)``,
  so a single failure can never escalate.
- Default policy (``enable_permanent_infeasible=False``) continues to
  return ``False`` unconditionally.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short -v
50/50 passed (33 N + 17 N1)

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

Total: **354 passed**.

## Explicit statements

- **No CST run.**
- **No runtime retry/recovery.**
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
| ``.claude/settings.local.json`` modified by Phase N1 | no |

## Commit hashes

- Phase N1 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
