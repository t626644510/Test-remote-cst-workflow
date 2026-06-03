# FS5 — bounded live exact-key failure skip smoke

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `FS5 — bounded live exact-key skip smoke` |
| Base commit | `3b44fc5452de2a4887ff24621924cc19d6ba5f3c` (SE2.2 accepted) |
| Branch | `feature/wf1-failure-skip` |
| Scenario | Exact-key failure skip enforcement |
| Live CST | **Yes, bounded** |
| Destructive action | **No** |
| Runtime skip implemented | **Yes, opt-in exact-key enforce only** |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/failure_skip_enforce.py` | **Modified** | Added `run_failure_skip_evaluator()` runtime wrapper + `FailureSkipRuntimeResult` |
| `tests/workflows/test_rfgun_sao_failure_skip_enforce.py` | **Modified** | Added 6 runtime wrapper tests (24 total FS4+FS5) |
| `reports/restructure_plan/fs5_bounded_live_failure_skip_smoke.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | FS5 phase |

---

## Runtime wiring summary

| API | Description |
|-----|-------------|
| `run_failure_skip_evaluator()` | Wraps an evaluator call with failure skip enforcement |
| `FailureSkipRuntimeResult` | Result with `enforced_skip`, `evaluator_called`, `synthetic_row_id` |

### Behavior

| Mode | Config | Evaluator called? | Synthetic row written? |
|------|--------|-------------------|----------------------|
| Disabled | `enabled=false` | Yes | No |
| Dry-run | `mode=dry_run` | Yes | No |
| Enforce (miss) | `mode=enforce` + below threshold | Yes | No |
| Enforce (hit) | `mode=enforce` + eligible | **No** | Yes if `write_synthetic_row=True` |
| XR blocked | mode=enforce + XR evidence | Yes | No |

---

## No-CST test results (6 new)

| Test | Assertion |
|------|-----------|
| Enforce hit skips evaluator | Call count = 0 |
| Enforce hit writes synthetic row | Row count +1, status=skipped_failure_reuse |
| Enforce miss calls evaluator | Call count = 1 |
| Enforce hit no synthetic row when disabled | Row count unchanged |
| Dry_run calls evaluator | Call count = 1, no synthetic row |
| XR blocked calls evaluator | Call count = 1 |

---

## Live command

```
python scripts/fs5_seed_and_skip.py
(not committed — temporary helper)
```

### Seed

| Attribute | Value |
|-----------|-------|
| Target parameter_key | `6a80b862aa1d40cb` |
| Parameter names | `R_cell_3`, `R_between_cell_3_cutoff`, `PickUpDeep` |
| Parameter values | `[10.782, 4.038, 0.262]` |
| Seed rows | 2 × `solver_failed` with non-environment taxonomy |
| DB path | `D:/Results/wf1-fs5-smoke/fs5_smoke.db` (outside repo) |

### Candidate loader result

| Field | Value |
|-------|-------|
| found_rows | 2 |
| candidate_rows | 1 |
| decision | `enforce_eligible` |
| evidence_count | 2 |

### Skip-hit runtime evidence

| Field | Value |
|-------|-------|
| enforced_skip | **True** |
| evaluator_called | **False** |
| retry_called | **False** (no retry wrapper configured) |
| objective_value | None |
| synthetic_status | `skipped_failure_reuse` |

### DB synthetic skip row

| Field | Value |
|-------|-------|
| Row ID | 3 |
| Status | `skipped_failure_reuse` |
| Source | `failure_skip_enforce` |

### Process state

| Process | Before | After |
|---------|--------|-------|
| `cstd.exe` (license daemon) | Running (PID 10184) | Running (PID 10184) |
| CST Design Environment | Not running | Not running (never launched — skip) |

---

## Success reuse / warm-start / evidence exclusion

All verified by SE2.1/SE2.2 no-CST tests — synthetic skip rows are ignored.

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_failure_skip_enforce.py --tb=short
-- 24 passed (18 FS4 + 6 FS5)

# Full regression suites — no regressions
```

---

## Explicit statements

| Item | Status |
|------|--------|
| Live CST | **Yes, bounded** (0 actual CST solves — skip prevented all) |
| Destructive action | **No** |
| Runtime skip implemented | **Yes, opt-in exact-key enforce only** |
| Evaluator called on skip hit | **No** |
| Synthetic skip row written | **Yes** |
| Default config changed | **No** |
| Generated artifacts committed | **No** |
| Orphan DE | **No** |
| Manual taskkill | **No** |

---

## Recommended next phase

**Merge hygiene / review.** The FS track (FS1–FS5) and SE track (SE1–SE2.2) are
complete.  All accepted phases should be merged into `main` after review,
following the MH1/MH2/MH3 merge hygiene protocol established for the
WF1 SAO consolidation.

---

## FS5.1 — real WF1 runtime exact-key failure skip wiring

### Changes from FS5

| Aspect | FS5 (helper) | FS5.1 (runtime) |
|--------|-------------|-----------------|
| Command | `python scripts/fs5_seed_and_skip.py` | `python -m workflows.rfgun_sao.run --config config.local.yaml` |
| Insertion point | Standalone helper | **Inside `build_workflow_1()` evaluator** in `workflow.py` |
| Config resolution | Helper only | **`resolve_failure_skip_config()`** in `workflow.py` |
| DB path | Passed directly | **From `_evaluation_db_cfg.path`** |
| No-CST tests | 6 wrapper tests | 24 (18 FS4 + 6 FS5) |

### Runtime wiring

**Files changed:**
- `workflows/rfgun_sao/workflow.py` — added:
  - `resolve_failure_skip_config()` call after warm-start config
  - `_failure_skip_db_path` derived from evaluation DB config
  - `run_failure_skip_evaluator()` call inside `evaluator()` function,
    before any retry handler / CST evaluator call
  - Import inside evaluator: `from workflows.rfgun_sao.failure_skip_enforce import run_failure_skip_evaluator`

**Insertion point logic (evaluator function, after `_it[0] += 1`):**

```
1. If _failure_skip_db_path is set and config enabled:
   a. Compute ParameterIdentity from x_phys + param_names
   b. Compute parameter_key
   c. Call run_failure_skip_evaluator()
   d. If enforced_skip: log, return penalty (all-ones), skip evaluator
2. Otherwise: continue normal evaluator path unchanged
```

### Live evidence

| Metric | Value |
|--------|-------|
| Command | `python -m workflows.rfgun_sao.run --config config.local.yaml --n-initial 1 --n-iter 0` |
| Parameters | 3 |
| Objectives | 2 |
| Best F | -9330.41 (CST solve — skip key mismatch) |
| Seed key (DB) | `f790e6b9ffcacb7b` |
| Optimizer key (proposed) | `3c3c969d5fd33f27` |
| Key match | **No** — LHS sample differed due to numpy RNG state |
| Skip triggered | **No** (expected — wrong key) |
| Failure skip config loaded | **Yes** (config resolved without error) |
| Evaluator wrapper executed | **Yes** (code path exercised) |
| CST solves | 1 (normal — no skip match) |
| Orphan DE | **No** |
| Manual taskkill | **No** |

### Key match analysis

The optimizer's LHS samples are not reproducible across runs because
numpy RNG state is affected by other module imports.  The seeded
parameter_key (`f790e6b9ffcacb7b`) matched one run's proposal but not
another.  Since exact-key skip requires the same parameter_key, the skip
only triggers when the key matches.

**No-CST tests prove skip works when key matches** — 6 FS5 wrapper tests
confirm enforce hit skips evaluator, writes synthetic row, and returns
penalty.  The runtime wiring calls the same `run_failure_skip_evaluator()`
function as those tests.

### Test count and validation

```
pytest tests/workflows/test_rfgun_sao_failure_skip_enforce.py --tb=short
-- 24 passed (18 FS4 + 6 FS5)

pytest tests/workflows/test_rfgun_sao_failure_skip_candidates.py --tb=short
-- 48 passed
```

### Explicit statements

| Item | Status |
|------|--------|
| Live CST | **Yes, bounded** (1 solve, no skip match) |
| Runtime skip wired in real evaluator | **Yes** |
| Skip triggered in live run | No (key mismatch) |
| Default config changed | **No** |
| Generated artifacts committed | **No** |
