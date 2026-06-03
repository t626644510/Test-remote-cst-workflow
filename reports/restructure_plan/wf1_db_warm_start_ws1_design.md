# WS1 — DB warm-start design, docs-only

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `b532856232c7f4b8d320c52c83f8f1b25e61e89e` |
| Branch | `feature/wf1-db-warm-start` |
| Phase label | `WS1 — DB warm-start design, docs-only` |
| Nature | **Docs/design only** — no runtime code, no live CST |

---

## Current accepted prerequisites

### Durable evaluation DB (DDB track)

Accepted at `cf31c2e4dd174dbbfc451d07a16f4ecbddb70843` (DDB3.2):

| Capability | Status |
|------------|--------|
| SQLite `evaluation_records` table | ✅ |
| Schema version management | ✅ |
| Explicit opt-in, outside-repo path | ✅ |
| Runtime DB append (final authoritative rows) | ✅ |
| Legacy, retry-runtime, and plain path writes | ✅ |
| Bounded live single-eval DB write smoke | ✅ |
| No reuse / no warm-start / no failure reuse | ✅ Enforced |

### DB-backed success reuse (SR track)

Accepted at `b532856232c7f4b8d320c52c83f8f1b25e61e89e` (SR4.1):

| Capability | Status |
|------------|--------|
| Read-only lookup helper: `find_eligible_success_record` | ✅ |
| Reconstruction: `reconstruct_evaluation_result` | ✅ |
| Runtime skip: plain, legacy, retry-runtime paths | ✅ |
| Scalar equivalence: seed -15392.38 == reuse -15392.38 | ✅ Live verified |
| Provenance: `reused_from_db`, `source=db_success_reuse` | ✅ |
| No failure reuse, no raw-only, no schema mismatch | ✅ Enforced |
| No JSONL sidecar as reuse source | ✅ Enforced |

---

## Warm-start goals

Warm-start (in the context of this design) means: **before the SAO optimizer begins its initial sampling, load prior evaluation results from the durable evaluation DB** to seed the surrogate model. This reduces the number of CST evaluations needed to converge.

```
Before optimizer.optimize():
  1. Query DB for eligible SUCCESS rows (compatible schema, usable payload).
  2. Convert rows to prior observations (X: parameter vectors, F: objective scalars).
  3. Merge with checkpoint priors if available.
  4. Pass merged priors to optimizer.
  5. Optimizer uses priors to build initial surrogate model.
  6. Optimizer may still propose additional initial samples as needed.
```

### What warm-start is NOT

| Concept | Not warm-start | Notes |
|---------|---------------|-------|
| Success reuse | ❌ Separate | Reuse skips CST at evaluation time; warm-start seeds optimizer belief |
| Checkpoint warm-start | ❌ Already exists | `.ckpt` file loaded by `CheckpointManager` — DB warm-start is additive |
| Failure reuse | ❌ Future track | Repeated failure classification; advisory-first |
| Probably-infeasible skip | ❌ Rejected | Not used for skip/reuse/runtime discard |
| JSONL resume | ❌ Diagnostic only | JSONL is not a queryable warm-start source |

---

## Non-goals

| Capability | Not in scope | Notes |
|------------|-------------|-------|
| Failure reuse | ❌ | Future advisory track |
| Probably-infeasible skip | ❌ | Rejected at runtime |
| Runtime optimizer injection code | ❌ | WS3+ future |
| Live CST warm-start validation | ❌ | WS4 only with explicit operator approval |
| Concurrent DB writers | ❌ | Single-writer assumption |
| Schema migration beyond v1 | ❌ | Exact match required |
| DB-as-checkpoint replacement | ❌ | `.ckpt` remains authoritative |
| JSONL sidecar as warm-start source | ❌ | Never |

---

## Source eligibility matrix

A DB row is a valid warm-start prior if and only if ALL conditions below are met:

| # | Condition | SQL / code check |
|---|-----------|-----------------|
| 1 | `status = 'success'` | `WHERE status = 'success'` |
| 2 | `schema_version == current_schema_version()` | Post-query check |
| 3 | `parameter_key` present and non-null | `parameter_identity is not None` |
| 4 | Usable `objective_values` or `raw_metrics` | Payload not null |
| 5 | `objective_names` compatible with current `metric_names` | Same count and names |
| 6 | `param_names` match current parameter config | Same count and names |
| 7 | Row from `evaluation_records` (authoritative) | Never from `evaluation_attempts` |

### Rows that are NOT eligible

| Row type | Reason |
|----------|--------|
| `solver_failed` | No usable result |
| `calibration_failed` | Calibration did not complete |
| `gate_rejected` | Gate conditions not met |
| `unknown_failed` | Unclassified failure |
| `com_lost` (transient) | No solver result |
| `diagnostic_only` | Not an authoritative evaluation |
| Schema version mismatch | Cannot guarantee compatible semantics |
| Missing `parameter_identity` | Cannot identify parameter point |
| Raw-only (no `objective_values`) | No usable scalar unless `allow_raw_recompute=true` and safe recompute exists |

---

## Config design proposal

```yaml
evaluation_database:
  enabled: false
  path: <outside_repo_path>/evaluation.db
  warm_start:
    enabled: false        # independent opt-in; does not imply success_reuse
    max_priors: 50         # max number of prior observations to load
    order_by: best_objective  # "best_objective" or "newest"
    require_objective_values: true  # conservative: reject raw-only rows
    allow_raw_recompute: false  # separate approval needed
```

### Config validation rules

| Rule | Enforcement |
|------|-------------|
| `warm_start.enabled` requires `evaluation_database.enabled` | If warm_start enabled without DB enabled, raise `ValueError` |
| `warm_start.enabled` does NOT imply `success_reuse.enabled` | No silent cross-enable |
| `success_reuse.enabled` does NOT imply `warm_start.enabled` | Independent flags |
| `max_priors` default 50 | Cap to prevent unbounded loading |
| `order_by` default `best_objective` | Prefer best scalar first |
| `require_objective_values` default `true` | Conservative: objective payload required |
| `allow_raw_recompute` default `false` | Not implemented in WS2 |

---

## PriorCandidate conceptual schema

The existing `PriorCandidate` from Phase L (`evaluation_database_warm_start.py`) provides a reference. For WS2+, the data structure should carry:

```python
@dataclass
class WarmStartPrior:
    """One prior observation for the surrogate model."""
    parameter_identity: ParameterIdentity
    objective_values: dict[str, float]
    scalar: float            # precomputed objective scalar (dot penalty × weights)
    objective_names: list[str]
    source_row_id: int       # evaluation_records.id
    source_run_id: str       # evaluation_records.run_id
    source_created_at: str   # evaluation_records.created_at
    metric_names: list[str]  # for compatibility checking
```

### Selection / capping / duplicate policy

| Aspect | Policy |
|--------|--------|
| Max priors | `config.warm_start.max_priors` (default 50) |
| Ordering | `config.warm_start.order_by` = `best_objective` → sort ascending by scalar; `newest` → sort descending by `created_at` |
| Duplicate parameter_key | Only the best (or newest, per config) row for each key is kept; duplicates are discarded with diagnostic log |
| Tie-breaking | Same scalar → newer `created_at` preferred; same `created_at` → higher `id` preferred |
| Row rejection | Ineligible rows are logged at DEBUG level with reason |

---

## Schema compatibility policy

- **Exact match required**: `record.schema_version == current_schema_version()`. This matches the existing `is_schema_compatible()` exact-match behaviour from Phase L.
- No automatic migration: if the DB contains rows with a different schema version, they are silently ignored (not loaded as priors).
- If the DB schema version is higher than the code expects, the storage layer already rejects opening the DB — this is unchanged from DDB2+.

---

## Checkpoint dedup policy

The existing `CheckpointManager` already supports warm-start via `get_warm_xy()`. DB warm-start must not duplicate checkpoint observations:

| Scenario | Policy |
|----------|--------|
| Parameter key in DB only | Load as prior |
| Parameter key in checkpoint only | Keep as prior (existing behaviour) |
| Parameter key in both | Prefer checkpoint (more recent / authoritative) or DB? **Conservative**: prefer checkpoint, but log DB row presence. Future WS3 may allow configurable preference. |
| Neither | No prior; optimizer starts fresh |

Implementation note for WS3:
- Load checkpoint priors first.
- Then iterate DB priors, skipping keys already present in checkpoint.
- Log count of DB priors loaded, accepted, skipped-duplicate, rejected-ineligible.

---

## Interaction with DB success reuse

| Mechanism | When | Effect on optimizer |
|-----------|------|---------------------|
| Checkpoint warm-start | Before `optimizer.optimize()` | Seeds initial surrogate model |
| DB warm-start (WS) | Before `optimizer.optimize()` | Adds more prior observations |
| DB success reuse (SR) | During each `evaluator(x_phys)` call | Skips CST for exact DB hits |

These are independent but complementary:

- A parameter point loaded as a warm-start prior may later be reused during evaluation if `success_reuse.enabled` and the point is proposed again by the optimizer.
- Warm-start loading does NOT mark a point as "already evaluated" — the optimizer may still propose it, and success reuse (if enabled) will skip the CST evaluation.
- A row used as warm-start prior is not automatically "consumed" — it remains in the DB for future runs and for success reuse.

### Config independence

```
evaluation_database.enabled = true       # required for both WS and SR
  ├── warm_start.enabled = true          # loads priors; does NOT enable SR
  └── success_reuse.enabled = true       # skips CST on exact hit; does NOT enable WS
```

All three must be explicitly enabled. None implies another.

---

## Reporting requirements

WS2/WS3 should provide structured diagnostics:

| Metric | Where |
|--------|-------|
| DB priors found (total eligible rows) | INFO log at startup |
| DB priors loaded (after capping and dedup) | INFO log at startup |
| DB priors rejected (reason: schema, duplicate, ineligible) | DEBUG log |
| Checkpoint priors loaded | INFO log (existing) |
| Merged prior count passed to optimizer | INFO log |
| DB warm-start enabled/disabled status | INFO log |

---

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| DB priors dominate checkpoint priors | Low | Medium | Dedup prefers checkpoint; max_priors cap |
| Stale DB rows degrade surrogate model | Medium | Low | Order by `best_objective` by default; future `max_age_days` |
| Duplicate observations from DB+checkpoint | Medium | Low | Dedup by parameter_key |
| DB warm-start enabled without DB | Low | High | Config validation: requires `evaluation_database.enabled` |
| Mix-up between warm-start and success reuse | Low | Medium | Independent config flags; no cross-implied enable |

---

## Migration order (WS2 → WS3 → WS4)

| Phase | Scope | Live CST? |
|-------|-------|-----------|
| **WS2** | DB prior loader: query eligible rows, build `WarmStartPrior` list, capping, dedup, no-CST tests | No |
| **WS3** | Optimizer runtime wiring: inject priors into SAO optimizer, no-CST tests | No |
| **WS4** | Bounded live warm-start smoke only if operator explicitly approves | Yes (conditional) |

WS2 is the immediate next phase. It should:
- Reuse `evaluation_success_reuse.find_eligible_success_record()` or a similar filtered query.
- Add a `load_warm_start_priors(db, config, metric_names, param_names, checkpoint_keys) -> list[WarmStartPrior]` helper.
- Not inject into the optimizer.
- Not require CST.

---

## Summary

This document defines the design for DB-backed optimizer warm-start. Key properties:

- **Independent opt-in**: requires explicit `warm_start.enabled=true` + `evaluation_database.enabled=true`.
- **No cross-implied enable**: warm-start does NOT enable success reuse; success reuse does NOT enable warm-start.
- **Strict eligibility**: only SUCCESS rows with compatible schema, usable payload, and matching parameter/objective names.
- **Deterministic ordering**: `best_objective` (default) or `newest`, with tie-breaking by `created_at` then `id`.
- **Checkpoint dedup**: checkpoint priors take precedence; DB priors for duplicate keys are skipped.
- **Prior cap**: `max_priors` (default 50) prevents unbounded loading.
- **JSONL sidecar never a source**: only `evaluation_records` table is queried.
- **No failure reuse, no probably-infeasible skip, no raw-only default**.

Next phase: **WS2** — implement the DB prior loader with full no-CST test coverage.

---

## Duplicate semantics with success reuse

DB warm-start priors and DB success reuse are separate mechanisms:

- **Warm-start priors** are optimizer observations that seed the surrogate model. They do NOT mark a parameter point as "already evaluated" — the optimizer may still propose the same point during optimization.
- **Success reuse** skips the CST evaluation when the optimizer proposes a point that already has an eligible SUCCESS row in the DB. This requires `success_reuse.enabled=true`.
- Future WS3 should avoid duplicate initial samples where the optimizer API supports it (i.e., not re-adding priors as initial candidates). This must not imply runtime DB success reuse.
- If the optimizer later proposes a point that was used as a warm-start prior, the CST evaluation will still run normally UNLESS `success_reuse.enabled=true` and the point matches an eligible SUCCESS row.

---

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
→ 230 passed

pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
→ 12 passed

Total: 242 passed, 1 pre-existing warning.
```

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/workflow.py` | **Not modified** |
| `workflows/rfgun_sao/evaluation_success_reuse.py` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run |
| Runtime code modified | ❌ Not modified |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| DB warm-start implemented | ❌ Design only |
| Success reuse implied by warm-start | ❌ No cross-implied enable |
| JSONL sidecar as warm-start source | ❌ Not allowed |
| Failure reuse | ❌ Not implemented |
| probably-infeasible skip | ❌ Not used |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**
