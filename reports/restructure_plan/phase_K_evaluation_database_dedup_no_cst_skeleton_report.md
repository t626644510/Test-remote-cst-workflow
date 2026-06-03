# Phase K — Evaluation database dedup no-CST skeleton

## Summary

Implement in-memory dedup helpers for the evaluation database:
``InMemoryEvaluationRecordIndex``, ``classify_record_for_dedup``,
``decide_dedup_for_parameter``, and the full dedup decision taxonomy.
No durable I/O, no SQLite, no file writes, no CST, no warm-start.

## Base commit

``a22ecba13210ba2ba2effd99ff5af5fb668a5882`` (Phase J accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/evaluation_database_dedup.py`` | New — dedup decision taxonomy, in-memory index, record classification, dedup query |
| ``tests/workflows/test_rfgun_sao_evaluation_database_dedup.py`` | New — 18 no-CST tests covering classification, indexing, lookup, decision, provenance, failure reuse |
| ``workflows/rfgun_sao/evaluation_database_schema.py`` | Updated ``RawEvaluationPayload.diagnostics`` docstring to remove sidecar reference |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | J → Accepted; added K row |

## Dedup semantics

| Scenario | Decision |
|----------|----------|
| Parameter key match → success record(s) found | ``USE_EXISTING_SUCCESS`` |
| No matching parameter key | ``EVALUATE_NEW`` |
| Match found but only failure records | ``IGNORE_FAILURE_RETRY_POLICY_MISSING`` |
| No parameter identity on record or query | ``IGNORE_MISSING_PARAMETER_IDENTITY`` |
| Incompatible schema version | ``IGNORE_INCOMPATIBLE_SCHEMA`` |
| ``allow_failure_reuse=True`` (Phase K) | Still returns ``IGNORE_FAILURE_RETRY_POLICY_MISSING`` (not implemented) |
| Provenance mismatch | Does **not** block dedup; recorded in diagnostics only |
| Multiple success records for same key | Prefers the first (deterministic iteration order) |

## Validation

```
$ python -m compileall workflows/rfgun_sao/evaluation_database_dedup.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_dedup.py --tb=short -v
18/18 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short
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

Total: **380 passed** (340 existing + 22 schema + 18 dedup).

## Explicit statements

- **No CST run.**
- **No durable evaluation database implementation** (no file/db/SQLite read/write).
- **No warm-start/prior construction implementation.**
- **No retry/recovery implementation.**
- **No root shim repoint.**
- **Phase C JSONL sidecar is not referenced or read by dedup helpers.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase K | no |

## Commit hashes

- Phase K implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
