# Phase J — Evaluation database design/schema

## Summary

Design the evaluation database schema and helpers:
``ParameterIdentity`` with deterministic keys, ``RawEvaluationPayload``,
``EvaluationDatabaseRecord``, JSON round-trip, schema versioning, DDL
string (design-only, not executed).  No durable storage, no dedup, no
warm-start, no CST.

## Base commit

``22c1229cabf56a151e2c1722b771d49b791ab78d`` (Phase I1 accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/evaluation_database_schema.py`` | New — schema module with ``ParameterIdentity``, ``RawEvaluationPayload``, ``EvaluationDatabaseRecord``, ``ReuseEligibility``, JSON round-trip, DDL string |
| ``tests/workflows/test_rfgun_sao_evaluation_database_schema.py`` | New — 22 no-CST tests covering schema version, status, parameter identity, validation, JSON round-trip, DDL |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | I/I1 → Accepted; added J; updated next directions |

## Schema components

| Component | Description |
|-----------|-------------|
| ``current_schema_version`` | Returns `1` |
| ``is_schema_compatible`` | Exact-match version check |
| ``EvaluationDatabaseStatus`` | ``SUCCESS``, ``GATE_REJECTED``, ``CALIBRATION_FAILED``, ``SOLVER_FAILED``, ``TRANSIENT_FAILED``, ``UNKNOWN_FAILED`` |
| ``ParameterIdentity`` | Ordered param names/values with ``parameter_key()`` (SHA-256 hex digest, first 16 chars) and optional ``precision`` for rounding |
| ``RawEvaluationPayload`` | Raw metrics, objective values, gate results, diagnostics, artifact references (string-only) |
| ``EvaluationDatabaseRecord`` | Full record with schema version, identity, status, payload, objective names, source, provenance, retry count, error taxonomy |
| ``ReuseEligibility`` | Design-only categories: ``ELIGIBLE_SUCCESS_RAW_REDERIVE``, ``INELIGIBLE_FAILURE_RETRY_POLICY_MISSING``, ``DIAGNOSTIC_ONLY`` |
| ``record_to_json_dict`` / ``record_from_json_dict`` | JSON round-trip (no file I/O) |
| ``schema_ddl_sqlite`` | DDL string (not executed) |

## Key design decisions

### Parameter identity

``ParameterIdentity.parameter_key()`` returns a deterministic 16-character
SHA-256 digest based on ``name=value`` pairs.  Precision rounding is
optional; when set, values are rounded before hashing.  This key is the
primary dedup mechanism for future Phase K+.

### JSONL sidecar independence

The Phase C diagnostic JSONL sidecar is **not referenced** by the
evaluation database schema.  ``record_to_json_dict`` / ``record_from_json_dict``
are self-contained and do not read from or write to the JSONL sidecar.

### Reuse eligibility design-only

``ReuseEligibility`` defines categories for future use but is **not**
implemented as runtime logic.  No records are automatically classified
as eligible or ineligible.

### Failure reuse deferred

Failure records (``CALIBRATION_FAILED``, ``SOLVER_FAILED``, etc.) round-trip
correctly but are not marked as reusable for warm-start.  Real failure
reuse requires the error taxonomy and retry threshold design in Phase M+.

### DDL design-only

``schema_ddl_sqlite()`` returns a DDL string for review only.  It is
not executed, and no file or database writes occur in Phase J.

## Validation

```
$ python -m compileall workflows/rfgun_sao/evaluation_database_schema.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short -v
22/22 passed

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short
32/32 passed

$ pytest tests/workflows/test_rfgun_sao_adaptive_bounds.py --tb=short
33/33 passed

$ pytest tests/workflows/test_rfgun_sao_stage_adaptive_policy.py --tb=short
18/18 passed

$ pytest tests/workflows/test_rfgun_sao_stage_runtime.py --tb=short
17/17 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

Total: **362 passed** (340 existing + 22 new schema tests).

## Explicit statements

- **No CST run.**
- **No durable evaluation database implementation** (no file/db writes, no SQLite connections).
- **No dedup/skip implementation.**
- **No warm-start/prior construction implementation.**
- **No retry/recovery implementation.**
- **No root shim repoint.**
- **JSONL diagnostic sidecar is not used as recovery/warm-start source.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase J | no |

## Commit hashes

- Phase J implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
