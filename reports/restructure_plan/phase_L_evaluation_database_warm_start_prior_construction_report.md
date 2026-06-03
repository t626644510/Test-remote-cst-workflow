# Phase L — Evaluation database warm-start / prior construction

## Summary

Implement in-memory warm-start / prior construction helpers:
``classify_record_for_prior``, ``record_to_prior_candidate``,
``build_prior_candidates_from_records``, ``select_prior_candidates``,
and ``derive_stage_observations_from_prior_candidates``.
No durable DB, no optimizer injection, no CST, no JSONL sidecar read.

## Base commit

``797f1b6b973133665baa1a98e732113f11a659e1`` (Phase K accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/evaluation_database_warm_start.py`` | New — prior candidate dataclass, classification, bulk construction, selection, stage-observation derivation |
| ``tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py`` | New — 14 no-CST tests covering all helpers |
| ``workflows/rfgun_sao/evaluation_database_dedup.py`` | Fixed ``find_records_by_parameter_identity`` docstring (removed None pid claim) |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | K → Accepted; added L row |

## Prior construction semantics

| Classification | Becomes prior candidate? | Reason |
|---------------|------------------------|--------|
| SUCCESS + compatible schema + parameter identity + raw payload | Yes (``USABLE_SUCCESS``) | Eligible for warm-start |
| SUCCESS but missing raw payload (if ``require_raw_metrics=True``) | No | ``IGNORED_MISSING_RAW_PAYLOAD`` |
| Failure status | No | ``IGNORED_FAILURE`` (retry taxonomy future) |
| Missing parameter identity | No | ``IGNORED_MISSING_IDENTITY`` |
| Incompatible schema version | No | ``IGNORED_INCOMPATIBLE_SCHEMA`` |
| Unknown / diagnostic-only status | No | ``IGNORED_DIAGNOSTIC_ONLY`` |

### Objective value fallback

``record_to_prior_candidate`` searches for a primary objective value
first in ``objective_values``, then in ``raw_metrics``, picking the first
finite value found.

### Selection / ordering

``select_prior_candidates`` sorts by objective (ascending by default).
Optionally filters by ``max_count`` and ``objective_name``.

### Stage observation derivation

``derive_stage_observations_from_prior_candidates`` converts prior
candidates to ``StageObservation`` objects marked ``COMPLETED`` and
``reused=True``, suitable for stage-runtime warm-start.  Only
candidates with finite objective values are included.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py --tb=short -v
14/14 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short
22/22 passed

$ pytest tests/workflows/test_rfgun_sao_evaluation_database_dedup.py --tb=short
18/18 passed

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

Total: **394 passed** (380 existing + 14 warm-start).

## Explicit statements

- **No CST run.**
- **No durable evaluation database implementation** (no file/db/SQLite read/write).
- **No optimizer/runtime warm-start injection.**
- **No retry/recovery implementation.**
- **No root shim repoint.**
- **Phase C JSONL sidecar is not read for prior construction.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase L | no |

## Commit hashes

- Phase L implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
