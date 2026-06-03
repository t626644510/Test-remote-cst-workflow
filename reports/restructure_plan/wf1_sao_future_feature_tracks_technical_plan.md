# WF1 SAO future feature tracks — technical plan

## Current accepted base

| Field | Value |
|-------|-------|
| Base commit | `c82e809991ac4e15c28fb52dba037d55160b23f6` |
| Branch | `refactor/wf1-sao-consolidation` |
| Completed consolidation | Phases O–V (retry runtime skeleton → root shim repoint → production campaign → closeout) |
| Root shim | `run_workflow_1.py` → `workflows.rfgun_sao.run` |

## Current completed state

- **Root shim repointed** at Phase S (commit `76ac3bf`).
- **Root shim live sanity** (S1): single-eval through `run_workflow_1.py`, Best F -15392.37, no orphan DE.
- **Bounded production campaign** (T): 9 evals through `run_workflow_1.py`, Best F -18002.12, no orphan DE.
- **Cleanup stable** since P3: 31 live evaluations, zero orphan DE, zero manual cleanup.
- **No-CST test suite**: 399 tests passing.
- **Default config unchanged**: single_pass mode, JSONL disabled, retry disabled, DB disabled.

## Guiding principles

1. **Separate branches**: Each track below must be developed on its own branch (branched from `main` or the consolidation branch after merge). No mixing tracks in a single phase.
2. **Default config must remain safe**: All new features must be opt-in, disabled by default.
3. **JSONL diagnostic sidecar remains diagnostic-only**: Must not be promoted to recovery/warm-start source.
4. **Probably-infeasible is advisory**: Must not become a runtime skip without separate acceptance and live validation.
5. **Live CST only when explicitly requested**: No automatic live CST in future phases without operator approval.
6. **No-CST first**: Each track should start with no-CST helpers and tests before any live CST integration.
7. **Rollback path**: Every track must document a rollback path before merge.

---

## Track A: Retry runtime CST wiring

### Purpose
Wire the Phase O/O1 `retry_runtime.py` no-CST callback skeleton into the live CST pipeline. Create a CST-backed `evaluate_once` callback that connects retry eligibility classification to actual CST reconnection and re-evaluation.

### What exists now
- `workflows/rfgun_sao/retry_runtime.py`: `RetryRuntimeConfig`, `RetryAttemptRecord`, `RetryRuntimeResult`, `run_retry_loop_no_cst()` — all no-CST.
- `workflows/rfgun_sao/retry_taxonomy.py`: `classify_failure_record()`, `classify_retry_eligibility()`, `RetryPolicy`.
- Legacy `EvaluationRetryHandler` (unrelated — handles CST retries at a different level).
- P3 cleanup hardening (`retry_handler.close_all()`) ensures replacement DEs are terminated.

### Implementation stages

1. **Design**: Define how `run_retry_loop_no_cst` maps to CST lifecycle:
   - `evaluate_once` callback wraps a CST evaluation (open project, solve, extract metrics).
   - On retry-eligible failure: close connection, call recovery callback, reconnect, re-evaluate.
   - Inter-pass recovery: between calibration and measurement in two-pass mode.
2. **No-CST adapter skeleton**: `make_cst_retry_evaluate_once(connection, project_path, solver, ...) -> Callable`
   - Testable with fake connection.
3. **Wiring**: Connect `RetryRuntimeConfig` to config loading; integrate into workflow evaluator.
4. **Live tests**: Minimal single-eval with engineered failure to exercise retry path.
5. **Rollback**: `git revert` commit; restore legacy retry path.

### Required test coverage
- No-CST: retry loop with fake CST evaluation (injectable `evaluate_once` already exists).
- No-CST: retry eligibility classification with taxonomy helpers.
- Live CST: single retry on calibration failure.
- Live CST: max-tier reached results in no orphan DE accumulation.

### Live test criteria
- Single-eval with deliberate solver failure → retry → re-evaluate → success.
- Max-tier exhausted → evaluation skipped, workflow continues, no orphan DE.
- Cleanup after retry: no orphan DE windows.

### Non-goals
- Full production-scale retry campaign.
- Durable DB-backed retry tracking.
- Failure reuse / permanent skip.

---

## Track B: Durable evaluation DB

### Purpose
Implement a persistent evaluation database (SQLite) that stores `EvaluationDatabaseRecord` instances, replacing the in-memory-only schema from Phases J–L.

### What exists now
- `workflows/rfgun_sao/evaluation_database_schema.py`: `ParameterIdentity`, `EvaluationDatabaseRecord`, `RawEvaluationPayload`, `record_to_json_dict`, `record_from_json_dict`, `schema_ddl_sqlite()`.
- `workflows/rfgun_sao/evaluation_database_dedup.py`: `InMemoryEvaluationRecordIndex`, `classify_record_for_dedup`, `decide_dedup_for_parameter`.
- `workflows/rfgun_sao/evaluation_database_warm_start.py`: `PriorCandidate`, `PriorConstructionReport`, `classify_record_for_prior`, `build_prior_candidates_from_records`, `select_prior_candidates`, `derive_stage_observations_from_prior_candidates`.

### Schema / migration requirements
- Use SQLite via standard library (`sqlite3`).
- Schema defined by `schema_ddl_sqlite()`.
- Migration: `schema_version` integer for forward-compat; incompatible versions return empty/error.
- DB file path: configurable via config, default outside repo (e.g. `D:/Results/`), never committed.

### Explicit opt-in config
```yaml
evaluation_database:
  enabled: false
  path: D:/Results/workflow1/evaluation.db
```

### Artifact path policy
- DB file must be configurable.
- Default path must be outside repository.
- Explicit error if path inside repo detected.

### Implementation stages
1. **SQLite adapter**: `append_record`, `lookup_by_parameter_key`, `lookup_by_status`, `close`.
2. **Opt-in wiring**: Integrate into workflow lifecycle (open at start, close at end).
3. **Dedup integration**: Replace `InMemoryEvaluationRecordIndex` with DB-backed lookup.
4. **Config validation**: Reject paths inside repo, require explicit enable.
5. **Tests**: No-CST tests with temporary SQLite files (cleaned up in teardown).

### Non-goals
- Network DB (PostgreSQL, etc.).
- Automatic migration beyond schema version check.
- DB as checkpoint replacement (checkpoint remains authoritative for optimizer state).

---

## Track C: DB-backed success reuse / dedup

### Purpose
Use the durable evaluation DB to skip re-evaluation of parameters that already have a SUCCESS result with compatible schema and identical parameter identity.

### Rules
- **Only SUCCESS** records are eligible for reuse. Failures are never reused.
- **Compatible schema**: `record.schema_version == current_schema_version()`.
- **Same parameter identity**: exact `parameter_key()` match.
- **Usable payload**: must have `raw_metrics` or `objective_values` depending on context.
- **No diagnostic-only**, no gate-rejected, no failure.
- **No provenance restriction**: provenance is preserved in the record but not blocking.

### Safety criteria
- Reuse is opt-in (requires both durable DB enabled and reuse enabled).
- Reuse never skips evaluation for parameter with existing incomplete/failed result.
- Reuse never promotes stale data from incompatible schema version.
- Reuse never pulls diagnostic-only records.

### Implementation stages
1. **DB query**: `find_success_by_parameter_key(key, schema_version)`.
2. **Reuse decision**: Integrate with `decide_dedup_for_parameter`.
3. **Runtime integration**: Before evaluation, check DB; if reusable record exists, return cached result.
4. **Tests**: No-CST with temporary DB; verify SUCCESS reused, failure not reused, incompatible skipped.

---

## Track D: DB warm-start / optimizer runtime warm-start

### Purpose
Use the durable evaluation DB to construct prior candidates for the SAO optimizer's initial surrogate model, extending the existing checkpoint-based warm-start.

### What exists now
- `evaluation_database_warm_start.py`: `classify_record_for_prior`, `build_prior_candidates_from_records`, `select_prior_candidates`, `derive_stage_observations_from_prior_candidates`.
- Phase L1 semantics: compatible SUCCESS + identity + raw/objective payload → usable; objective-values-only allowed; diagnostic-only ignored; provenance preserved but not blocking.

### Implementation
- Query DB for eligible records.
- Construct `PriorCandidate` list.
- Feed into optimizer's `prior_data` parameter.
- Keep checkpoint-based warm-start as fallback when DB disabled.

### Opt-in only
```yaml
warm_start:
  database:
    enabled: false
    max_candidates: 50
```

### Implementation stages
1. **DB query**: `find_prior_candidates(schema_version, max_count)`.
2. **Candidate construction**: Reuse Phase L helpers on DB results.
3. **Runtime integration**: Merge DB priors with checkpoint priors.
4. **Tests**: DB with prior candidates; verify ordering by objective; verify max_count respected.

---

## Track E: Failure reuse

### Purpose
After sufficient repeated failures of the same parameter with the same failure class, classify the parameter as probably-infeasible to avoid re-evaluating it in future runs.

### Constraints
- **Last track**: must not start until Tracks A–D are stable.
- **Single failure never skip**: only repeated, stable, same-identity, same-class failures.
- **Transient never permanent**: `TRANSIENT_FAILED` does not contribute to permanent classification.
- **Gate rejection separate**: gate rejection has its own policy (not solver failure).
- **Must require**: durable DB, stable identity, schema compatibility, repeated stable pattern, explicit thresholds.
- **Start advisory-only**: classification recorded but not acted upon.
- **Live validation required** before any runtime skip behavior is enabled.

### Current taxonomy support
- `should_escalate_to_probably_infeasible()` exists in `retry_taxonomy.py` (Phase N1).
- Returns False under default policy.
- Requires `enable_permanent_infeasible=True` and `permanent_failure_threshold` set.

### Implementation stages
1. **DB query**: `find_failure_history_by_parameter_key(key, schema_version, min_count)`.
2. **Advisory classification**: Use `should_escalate_to_probably_infeasible` to classify; log diagnostic only.
3. **Skip enablement**: After live validation, allow opt-in skip via config.
4. **Thresholds**: Configurable `permanent_failure_threshold` (default 5+).
5. **Tests**: DB with repeated failures; verify advisory classification; verify skip not activated by default.

---

## Suggested ordering

| Order | Track | Branch name | Dependencies |
|-------|-------|-------------|--------------|
| 1 | Retry runtime CST wiring | `feature/wf1-retry-runtime-cst-wiring` | None |
| 2 | Durable evaluation DB | `feature/wf1-durable-evaluation-db` | None |
| 3 | DB-backed success reuse / dedup | `feature/wf1-db-success-reuse` | Track B |
| 4 | DB warm-start / optimizer runtime warm-start | `feature/wf1-db-warm-start` | Track B, Phase L semantics |
| 5 | Failure reuse | `feature/wf1-failure-reuse` | Tracks B, C |

Tracks 1 and 2 are independent and can proceed in parallel. Tracks 3–5 depend on Track B.

---

## Acceptance criteria per track

| Track | Must pass | Live CST required? |
|-------|-----------|-------------------|
| A | Retry eligibility correctly classifies; retry loop terminates; no orphan DE accumulation | Yes — engineered failure |
| B | Append, lookup, schema-version guard; path outside repo; opt-in disabled by default | No |
| C | SUCCESS reused; failure never reused; incompatible skipped | No |
| D | Prior candidates correctly ordered; objective-values-only allowed; max_count respected; checkpoint fallback | No |
| E | Advisory classification only under default config; skip requires explicit enable + threshold + live validation | Yes — before skip enabled |

---

## Risks and rollback notes

| Risk | Mitigation |
|------|-----------|
| DB file committed to repo | Reject paths inside repo; fail-early validation |
| DB schema drift | Schema version check; incompatible → empty result |
| Retry accumulates orphan DEs | P3 cleanup hardening already handles this; verify in live tests |
| Failure reuse skips legitimate evaluations | Advisory-only first; explicit opt-in; thresholds; live validation |
| Warm-start with stale data | Schema compatibility; identity match; provenance traceable |

Each track's rollback: `git revert <track-merge-commit>`, verify default config unchanged, run no-CST tests.

---

## Final note

This document is a **technical planning reference** for future branches. No implementation work should be committed to the current consolidation branch after Phase V acceptance. All future work begins on fresh branches.
