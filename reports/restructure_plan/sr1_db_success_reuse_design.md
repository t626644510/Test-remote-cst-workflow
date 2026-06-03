# SR1 — DB-backed success reuse design and lookup policy

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `cf31c2e4dd174dbbfc451d07a16f4ecbddb70843` |
| Branch | `feature/wf1-db-success-reuse` |
| Phase label | `SR1 — Success reuse design and lookup policy` |
| Nature | **Docs/design only** — no runtime code, no live CST |

---

## Current DDB accepted state

The durable evaluation DB (DDB3.2) provides:

| Capability | Status |
|------------|--------|
| SQLite storage for final authoritative records | ✅ Accepted |
| Config: `evaluation_database.enabled/path/schema_version/create_if_missing` | ✅ Accepted |
| Schema: `schema_version` table, `evaluation_records` with parameter_key indexing | ✅ Accepted |
| Insert: `insert_final_record()` — final optimizer-used records only | ✅ Accepted |
| Query: `query_by_parameter_key()` — diagnostic/inspection only | ✅ Accepted |
| No query or behavior depends on DB for lookup | ✅ Enforced |
| Legacy retry path writes DB records | ✅ DDB3.2 |
| Runtime `repo_root` path protection | ✅ DDB3.1 |
| `objective_values` payload in DB rows | ✅ DDB3.1 |
| Row-count: exactly one DB row per evaluator call | ✅ DDB3.1 live evidence |

### What DDB does NOT do

- DB is never queried before evaluation to skip CST.
- DB is never used for warm-start, failure reuse, or probably-infeasible classification.
- JSONL sidecar is not a reuse source.

---

## What success reuse means in WF1

Success reuse means: **before invoking the CST solver**, check whether this exact parameter point has already been evaluated successfully in a previous run. If the DB contains a compatible SUCCESS record for the same parameter identity, reconstruct the evaluation result from the stored row and return it to the optimizer without running CST.

```
Before evaluation:
  1. Build ParameterIdentity from (param_names, x_phys)
  2. Compute parameter_key = identity.parameter_key()
  3. If success_reuse enabled AND DB enabled:
       query DB: SELECT * FROM evaluation_records
                 WHERE parameter_key = ? AND status = 'success'
                 ORDER BY created_at DESC LIMIT 1
  4. If eligible row found → reconstruct EvaluationResult → return to optimizer
  5. If no eligible row → proceed with normal CST evaluation
```

### What success reuse is NOT

| Capability | Not reuse | Notes |
|------------|-----------|-------|
| Warm-start | ❌ | Separate track (WS1) — DB priors for surrogate model |
| Failure reuse | ❌ | Separate track — requires repeated failure, thresholds |
| Probably-infeasible skip | ❌ | Rejected at runtime |
| JSONL resume | ❌ | JSONL is diagnostic-only; not a queryable source |
| Production campaign | ❌ | Bounded scope |

---

## Required eligibility conditions

A DB record is reusable if and only if ALL of the following hold:

| # | Condition | Enforcement |
|---|-----------|-------------|
| 1 | `evaluation_database.enabled = true` | Config check |
| 2 | `success_reuse.enabled = true` | Separate config; must be explicitly enabled |
| 3 | Record `status == 'success'` | SQL `WHERE status = 'success'` |
| 4 | `parameter_key` matches current `ParameterIdentity.parameter_key()` | SQL `WHERE parameter_key = ?` |
| 5 | Schema compatible (`schema_version == current_schema_version()`) | Post-query check; exact v1 match for SR2 |
| 6 | Usable payload: `raw_metrics` or `objective_values` not null | Post-query check |
| 7 | `objective_names` compatible with current `metric_names` (same count, same names) | Post-query check |
| 8 | Parameter names/count match current config | `param_names` parsed and compared |
| 9 | Row is from `evaluation_records` (authoritative final) | Never from `evaluation_attempts` |
| 10 | Row is not `gate_rejected`, `diagnostic_only`, `CALIBRATION_FAILED`, or unknown | SQL `WHERE status = 'success'` eliminates these |

### Conditions that do NOT block reuse

- Provenance mismatch (different git commit, host, config fingerprint) — provenance is diagnostic.
- Different `run_id` — cross-run reuse is the primary use case.
- Different `source` — any source producing a valid SUCCESS record is eligible.

---

## Tie-breaking when multiple eligible rows exist

| Policy | Rule |
|--------|------|
| Ordering | `ORDER BY created_at DESC, id DESC` |
| Selected | First row (newest by creation time, then highest ID) |
| Logging | Log selected row `id`, `run_id`, `source`, `created_at` at INFO level |
| Diagnostics | Store reuse provenance in returned result (see below) |

---

## Payload reconstruction policy

From a selected DB row, reconstruct an `EvaluationResult`:

| DB column | → `EvaluationResult` field | Required? |
|-----------|---------------------------|-----------|
| `status` | `status` | Always `SUCCESS` for reuse |
| `raw_metrics` (JSON) | `raw_metrics` | Yes if `require_objective_values=false` |
| `objective_values` (JSON) | `objective_values` | Yes if `require_objective_values=true` |
| — | `penalty_values` | Reconstructed from `raw_metrics` via `compute_role_penalties()` if possible; otherwise from stored `__retry_penalty__` in diagnostics |
| — | `f0_ghz` | From `raw_metrics.get("resonant_freq", NaN)` |
| `diagnostics` (JSON) | `diagnostics` | Preserved from DB, with `reused_from_db=true` added |
| `run_id` / `id` | `diagnostics["reuse_source"]` | `{db_row_id, run_id, created_at}` |

### Policy when `objective_values` is missing

If `require_objective_values=true` (default) and the row lacks `objective_values`, the row is **not reusable**. The evaluation proceeds with CST.

### Policy when `raw_metrics` is missing

If the row has neither `raw_metrics` nor `objective_values`, it is **not reusable** regardless of setting.

---

## Checkpoint / accounting semantics

| Aspect | Rule |
|--------|------|
| Checkpoint | Checkpoint records the reused result as one optimizer evaluation. The callback is called with the reconstructed `raw_arr`, `penalties_arr`, `solver_ok=True`, `error=""`. |
| CST solve budget | A DB-reused evaluation **does not consume CST solve budget** (no solver runs). This is transparent to the optimizer. |
| Distinguishability | The `diagnostics` dict in the reused result includes `reused_from_db=true`, `source_run_id`, `source_row_id`. The checkpoint and DB write should also reflect reuse provenance. |
| DB write | The reused result is written as a new evaluation_records row (same logic as normal evaluation), so future queries see it. |

---

## Runtime insertion point proposal

Success reuse must be checked **before** any CST solve is launched. Three insertion points:

### Plain single_pass path

```
Before:  raw, pen, ok, status, err = wf1_evaluator.evaluate_single_pass(...)
After:   if success_reuse enabled:
             pid = ParameterIdentity(param_names, x_phys)
             result = lookup_success_reuse(pid)
             if result:
                 return penalty_from_result(result)
         raw, pen, ... = evaluate_single_pass(...)
```

### Retry runtime path

```
Before:  raw, pen, ok, status, err = wf1_evaluator.evaluate_single_pass(...)
         (or synthetic smoke injection)
After:   if success_reuse enabled:
             check DB before the initial CST evaluation
             if reusable row found → skip entire retry runtime path
             treat as SUCCESS, return penalty
```

### Legacy retry path

```
Before:  result, tier = retry_handler.execute(...)
After:   if success_reuse enabled:
             check DB before retry_handler.execute
             if reusable row found → return penalty directly
             skip retry_handler entirely
```

### Key invariant

If reuse succeeds:
- `retry_handler.execute` is never called (legacy path).
- `evaluate_single_pass` is never called (plain path).
- `run_retry_loop_no_cst` is never called (retry runtime path).
- Checkpoint receives the reconstructed result.
- DB records the reused evaluation with `source` indicating reuse.

---

## Config proposal

```yaml
success_reuse:
  enabled: false                  # master switch; disabled by default
  require_objective_values: true  # if true, only rows with objective_values are reusable
  allow_raw_recompute: false      # if true, recompute penalties from raw_metrics
  max_age_days: null              # optional: reject rows older than N days
  log_decisions: true             # log each reuse decision at INFO level
```

### Config validation

| Rule | Enforcement |
|------|-------------|
| `success_reuse.enabled` requires `evaluation_database.enabled` | If `success_reuse.enabled=true` and `evaluation_database.enabled=false`, reject or warn |
| `require_objective_values` defaults `true` | Conservative — only rows with explicit objective payload are considered |
| `allow_raw_recompute` defaults `false` | No automatic penalty recomputation from raw metrics |
| `max_age_days` null = no age filter | Optional time-based rejection |
| `log_decisions` defaults `true` | Audit trail for reuse decisions |

---

## Safety policy

| Invariant | Enforcement |
|-----------|-------------|
| Default disabled | `success_reuse.enabled=false` in committed config |
| DB enabled alone ≠ reuse enabled | Both must be true |
| No failure reuse | Only `status == 'success'` rows are eligible |
| No schema-incompatible reuse | Exact schema version match |
| No probably-infeasible skip | Rejected at runtime |
| No JSONL sidecar reuse | Only `evaluation_records` table is queried |
| Ambiguous eligibility → run CST | If `require_objective_values` fails, run CST normally |
| No reuse from `evaluation_attempts` | Query only `evaluation_records` |

---

## Proposed no-CST implementation phases

### SR2 — Lookup helper + fake DB tests (no workflow runtime skip)

Implement:
- `find_eligible_success_record(db, parameter_identity, metric_names, config) -> EvaluationDatabaseRecord | None`
- `reconstruct_evaluation_result(db_row, metric_names, metric_specs, objectives_by_name) -> EvaluationResult | None`

Tests:
- exact same parameter_key SUCCESS returns reusable row
- different parameter_key no match
- failure rows ignored
- gate_rejected ignored
- schema mismatch ignored/rejected
- missing parameter identity ignored
- missing objective/raw payload ignored
- multiple SUCCESS rows deterministic newest/highest id
- diagnostic attempt rows ignored
- DB disabled no-op
- success_reuse disabled no-op
- `require_objective_values=true` rejects rows without objective_values

### SR3 — Runtime opt-in success reuse (no-CST + no live CST)

Wire the lookup helper into the three insertion points (plain, retry-runtime, legacy). Tests:
- plain path reuse skips fake CST evaluator
- retry_runtime path reuse skips retry loop
- legacy retry path reuse skips retry_handler
- checkpoint called exactly once with reused result
- DB write for reused result includes `source` = "reuse"
- no failure reuse (failure rows never trigger lookup)
- success_reuse disabled → normal CST evaluation path

### SR4 — Bounded live reuse smoke (operator approval only)

- Explicit approval required.
- Use outside-repo local DB.
- First run: live CST writes success row.
- Second run: same parameter point with `success_reuse.enabled=true`.
- Verify CST solve is not launched for the reused candidate.
- Verify final scalar/metrics match DB row.
- Verify checkpoint called once.
- Verify DB row written with reuse provenance.
- Verify no orphan DE / no manual taskkill.

---

## Proposed tests for SR2

| # | Test | Validates |
|---|------|-----------|
| 1 | Same parameter_key SUCCESS returns row | Core reuse path |
| 2 | Different parameter_key → no match | Correct identity matching |
| 3 | Failure rows ignored | No failure reuse |
| 4 | Gate_rejected ignored | No gate reuse |
| 5 | Schema mismatch rejected | Schema safety |
| 6 | Missing parameter identity ignored | Edge case |
| 7 | Missing raw_metrics → rejected (require_obj=true) | Payload validation |
| 8 | Missing objective_values → rejected (require_obj=true) | Payload validation |
| 9 | Multiple SUCCESS → newest selected | Tie-breaking |
| 10 | Diagnostic attempt rows ignored | Only authoritative rows |
| 11 | DB disabled → no-op | Config gating |
| 12 | success_reuse disabled → no-op | Config gating |
| 13 | `allow_raw_recompute=false` + no objective_values → rejected | Safe default |
| 14 | `require_objective_values=false` + raw_metrics present → accepted | Lenient mode |

---

## Proposed tests for SR3

| # | Test | Validates |
|---|------|-----------|
| 1 | Plain path reuse skips fake CST evaluator | Insertion point |
| 2 | Retry runtime path reuse skips retry loop | Insertion point |
| 3 | Legacy retry path reuse skips retry_handler | Insertion point |
| 4 | Checkpoint called once with reused result | Accounting |
| 5 | DB write includes `source="reuse"` | Audit trail |
| 6 | No failure reuse (failure in DB, CST runs) | Safety |
| 7 | `success_reuse.disabled` → normal CST path | Default |

---

## Summary

This document defines the design for DB-backed success reuse in WF1. Key properties:

- **Separate opt-in**: requires both `evaluation_database.enabled=true` and `success_reuse.enabled=true`.
- **Strict eligibility**: only SUCCESS rows with matching parameter_key, compatible schema, and usable payload.
- **No failure reuse**: failure, gate_rejected, diagnostic-only rows are never reused.
- **Deterministic tie-breaking**: newest `created_at`, then highest `id`.
- **Conservative default**: `require_objective_values=true`, `allow_raw_recompute=false`.
- **Three insertion points**: plain, retry-runtime, legacy — all check before CST solve.
- **Checkpoint and DB recording**: reused results are checkpointed and stored with provenance.

Next phase: **SR2** — implement the lookup helper with full no-CST test coverage.
