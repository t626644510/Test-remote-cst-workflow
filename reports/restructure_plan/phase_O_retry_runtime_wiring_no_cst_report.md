# Phase O — Retry / inter-pass recovery runtime wiring no-CST skeleton

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `9dcbadf48115dada9d494ec217a22554c330c038` |
| Phase label | `Phase O — Retry / inter-pass recovery runtime wiring no-CST skeleton` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST | **No** |
| Durable DB | **No** |
| Failure reuse | **No** |
| JSONL sidecar read | **No** |
| Root shim repoint | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/retry_runtime.py` | **Unchanged** (already existed as untracked skeleton) | Retry runtime config, dataclasses, no-CST retry loop, inter-pass/post-eval recovery skeletons |
| `tests/workflows/test_rfgun_sao_retry_runtime.py` | **Added** | 50+ tests covering config, retry loop, recovery callbacks, safety |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | Phase N/N1 marked Accepted; Phase O row added; Phase O caveats added; next directions updated |
| `reports/restructure_plan/phase_O_retry_runtime_wiring_no_cst_report.md` | **Added** | This report |

---

## Summary of changes

### 1. Retry runtime skeleton (`retry_runtime.py`)

The module was already present as an untracked skeleton. It provides:

- **`RetryRuntimeConfig`** — dataclass with `enabled=False` by default, `max_tier`, `allow_unknown_retry`, `allow_gate_retry`, `inter_pass_recovery_enabled`, `post_eval_recovery_enabled`, `use_probably_infeasible_for_skip`.
- **`RetryAttemptRecord`** — dataclass tracking one retry attempt (index, tier, status before/after, recovery status, error, diagnostics).
- **`RetryRuntimeResult`** — dataclass for the final result (final_status, attempts list, retry_count_consumed, succeeded, stopped_reason, diagnostics).
- **`resolve_retry_runtime_config()`** — resolves config from `dict | None`; accepts nested `{"retry": {...}}` or flat shape; defaults to disabled.
- **`should_use_retry_runtime()`** — returns `config.enabled`.
- **`run_retry_loop_no_cst()`** — no-CST retry loop with injectable `evaluate_once` callback; uses `classify_retry_eligibility()` for retry decisions; handles all terminal states (success, gate_rejected, diagnostic_only, incompatible_schema, missing_identity, max_tiers_reached); captures recovery callback results; captures `evaluate_once` exceptions as failure records; rejects `use_probably_infeasible_for_skip=True` with diagnostic.
- **`run_inter_pass_recovery_no_cst()`** — callback-only inter-pass recovery skeleton; returns `skipped_disabled` when disabled or no callback; captures callback exceptions.
- **`run_post_eval_recovery_no_cst()`** — same pattern for post-evaluation recovery.

### 2. No-CST tests

`tests/workflows/test_rfgun_sao_retry_runtime.py` provides comprehensive coverage.

### 3. Documentation updates

`BRANCH_CONTEXT.md` updated with Phase O completion and caveats.

---

## Retry runtime skeleton semantics

### Config resolution

The config resolver `resolve_retry_runtime_config()` accepts:
- `None` / `{}` → returns `RetryRuntimeConfig()` with `enabled=False`.
- `{"retry": {"enabled": True}}` (nested) or `{"enabled": True}` (flat).
- When `enabled=False`, other fields are **not** parsed (defaults apply).
- Defaults: `max_tier=3`, `allow_unknown_retry=True`, `allow_gate_retry=False`, all recovery disabled.

### Retry loop control flow

```
run_retry_loop_no_cst(initial_record, evaluate_once, config, recovery_callback, current_schema):
  1. If config disabled → return immediately (no retry).
  2. If use_probably_infeasible_for_skip → return with diagnostic error.
  3. Loop:
     a. classify_retry_eligibility(current_record) using config-derived RetryPolicy.
     b. SUCCESS → stop (succeeded=True).
     c. Terminal states (gate_rejected, diagnostic_only, incompatible_schema,
        missing_identity, max_tiers_reached) → stop (succeeded=False).
     d. RETRY_ELIGIBLE → call recovery_callback (if any), then evaluate_once.
     e. evaluate_once exception → captured as UNKNOWN_FAILED with incremented
        retry_count; loop continues (may hit max_tier).
```

### Recovery callback semantics

- Called before each retry attempt when provided.
- Signature: `recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool`.
- Return `True` → `recovery_label="recovery_success"`; `False` → `"recovery_failed"`.
- Exception → captured as `"recovery_exception:<msg>"`, loop continues.
- Recovery failure is **non-fatal** — the loop proceeds to evaluate_once regardless.

### Probably-infeasible guard

- `config.use_probably_infeasible_for_skip=True` causes immediate return with
  `stopped_reason="probably_infeasible_skip_not_supported"` and diagnostic error.
- **Not used for runtime skip or dedup.** Only stored in config; runtime rejects it.

---

## Inter-pass / post-eval recovery semantics

Both use the same callback-only pattern:

- `run_inter_pass_recovery_no_cst(calibration_record, callback, *, enabled)`
- `run_post_eval_recovery_no_cst(callback, *, enabled)`

When disabled or no callback available:
- Returns `{"status": "skipped_disabled", "recovered": False}`.

When enabled with callback:
- Calls callback; returns `{"status": "completed", "recovered": <result>}`.
- Callback exception → `{"status": "callback_exception", "recovered": False, "error": "..."}`.

No real CST cleanup/recovery is invoked. These are pure wiring skeletons.

---

## Explicit statement: probably-infeasible is not used for skip/reuse/runtime control

Per Phase O boundaries:

- `should_escalate_to_probably_infeasible()` from `retry_taxonomy` is **never called** by `retry_runtime.py`.
- `use_probably_infeasible_for_skip` config field exists but is **rejected** at runtime.
- The retry loop does **not** skip or permanently discard records based on probably-infeasible classification.
- All retry decisions go through `classify_retry_eligibility()` which may return `NO_RETRY_MAX_TIERS_REACHED` but never sets `probably_infeasible=True` under default policy (already guaranteed by taxonomy).

---

## Validation commands and results

Run from repository root (`c:\Users\lau\cst_ver3`):

```powershell
# 1. Compile check
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
```

```powershell
# 2. New retry runtime tests
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short -v
```

```powershell
# 3. Existing retry taxonomy tests must pass
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
```

```powershell
# 4. Existing warm-start tests must pass
pytest tests/workflows/test_rfgun_sao_evaluation_database_warm_start.py --tb=short
```

```powershell
# 5. Existing dedup tests must pass
pytest tests/workflows/test_rfgun_sao_evaluation_database_dedup.py --tb=short
```

```powershell
# 6. Existing schema tests must pass
pytest tests/workflows/test_rfgun_sao_evaluation_database_schema.py --tb=short
```

```powershell
# 7. rfgun_sao imports
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```

```powershell
# 8. rfgun_single_pass imports (must remain untouched)
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
```

**Results:** (to be filled after running)

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** (retry disabled by default) |
| Root shim | **Not repointed** |

---

## Feature completion checklist

| Feature | Status | Notes |
|---------|--------|-------|
| Live CST | **No** | Pure no-CST skeleton |
| Runtime CST retry | **No** | No CST-backed evaluation |
| Runtime CST recovery | **No** | Callback-only skeleton |
| Durable DB append/lookup | **No** | No file I/O |
| Failure reuse | **No** | Not implemented |
| JSONL sidecar read/reference | **No** | Verified by safety tests |
| Optimizer/runtime warm-start injection | **No** | Not implemented |
| Inter-pass recovery (real CST) | **No** | Callback-only skeleton |
| Post-eval recovery (real CST) | **No** | Callback-only skeleton |
| probably-infeasible as skip | **No** | Rejected at runtime |

---

## Artifacts check

| Artifact type | Present in commit | Verification |
|---------------|-------------------|--------------|
| `config.local.yaml` | **No** | Not committed |
| `*.jsonl` | **No** | Not generated |
| `*.ckpt` | **No** | Not generated |
| `*.sqlite` / `*.db` | **No** | Not generated |
| Logs | **No** | Not generated |
| CST output dirs | **No** | Not generated |
| Temporary scripts | **No** | Not committed |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** Expected to be the commit that includes:
- `tests/workflows/test_rfgun_sao_retry_runtime.py` (added)
- `workflows/rfgun_sao/BRANCH_CONTEXT.md` (updated)
- `reports/restructure_plan/phase_O_retry_runtime_wiring_no_cst_report.md` (added)
- `workflows/rfgun_sao/retry_runtime.py` (untracked → tracked)

---

## Commit message proposal

```
Phase O retry runtime wiring no-CST skeleton

- No-CST retry loop with injectable evaluate_once callback
- Config resolution: RetryRuntimeConfig, disabled by default
- RetryAttemptRecord / RetryRuntimeResult dataclasses
- Inter-pass/post-eval recovery callback-only skeletons
- use_probably_infeasible_for_skip rejected with diagnostic (Phase O not supported)
- 50+ no-CST tests: config, retry loop, recovery, safety
- BRANCH_CONTEXT.md updated (N/N1 accepted, O caveats, next directions)
- Phase O report

No live CST, no durable DB, no failure reuse, no JSONL reference,
no root shim repoint, no config default changes.
```
