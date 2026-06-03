# RW3 — Retry runtime CST wiring + bounded live retry smoke

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `e1c944863ac9aec1f7a68c5802f25cdd3557e92d` |
| Phase label | `RW3 — Retry runtime CST wiring + bounded live retry smoke` |
| Branch | `feature/wf1-retry-runtime-cst-wiring` |
| Live CST explicitly allowed | **Yes** — operator approved RW3 live smoke |
| Live CST run | **Yes** — bounded single-eval retry smoke through root shim |
| Live CST status | **Passed** — synthetic initial failure → retry loop → real CST success → Best F -15392.37 |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/retry_runtime.py` | **Modified** | Added `final_record` field to `RetryRuntimeResult`; set in all exit paths |
| `workflows/rfgun_sao/retry_runtime_cst.py` | **Modified** | `build_record_from_evaluation_result` accepts `penalty_values`; `make_cst_retry_evaluate_once` passes penalty_values through |
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added retry_runtime config resolution with `check_legacy_retry_mutex`; synthetic smoke injection hook (env-var + config gated); retry runtime evaluator path in single_pass workflow |
| `reports/restructure_plan/rw3_retry_runtime_live_smoke_report.md` | **Added** | This report |

---

## Summary of runtime wiring

### 1. `final_record` in `RetryRuntimeResult`

Added `final_record: EvaluationDatabaseRecord | None` field. Set in all exit paths:
- Disabled config: returns `initial_record` as `final_record`.
- Probably-infeasible reject: returns `initial_record`.
- Success/terminal/retry-exhausted: the current (last) record.
- `_make_result()` helper always sets `result.final_record = current`.

### 2. Penalty values in record diagnostics

`build_record_from_evaluation_result` now accepts `penalty_values` and stores them under `"__retry_penalty__"` in `raw_payload.diagnostics`. `make_cst_retry_evaluate_once` passes `EvaluationResult.penalty_values` through, so the evaluator closure can extract them after the retry loop.

### 3. Workflow wiring

In `workflows/rfgun_sao/workflow.py`:
- `check_legacy_retry_mutex(config)` resolves `retry_runtime` config. If legacy `optimization.retry.enabled` is True and retry_runtime requests enable, retry_runtime is disabled with warning.
- If retry_runtime is enabled and legacy retry is disabled:
  - Initial `evaluate_single_pass` runs normally.
  - If SUCCESS → use directly (no retry).
  - If failure → build `EvaluationDatabaseRecord`, run `run_retry_loop_no_cst` with the CST adapter.
  - Optimizer receives `final_record`'s penalty values (or all-ones on exhaustion).
  - Checkpoint records ONLY the final result (never intermediate retry attempts).

### 4. Synthetic smoke injection hook

Opt-in, dual-gated:
- Requires `retry_runtime.smoke_injection: true` in config (local, uncommitted).
- Requires environment variable `WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION=1`.
- On the first evaluation, injects a synthetic `SOLVER_FAILED` without running real CST.
- The retry loop then calls `evaluate_once` which runs the real CST evaluation.
- Hook fires exactly once; subsequent evaluations run normally.
- Completely disabled by default — no risk in production configs.

---

## Retry runtime config used for live smoke

```yaml
optimization:
  retry:
    enabled: false        # legacy retry disabled
retry_runtime:
  enabled: true
  max_tier: 1
  smoke_injection: true   # synthetic failure hook enabled
```

Environment: `WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION=1`

Config was live-only, written to `config.local.yaml` which is gitignored. The config was restored to pre-smoke state after validation.

---

## Live smoke results

```
$ python run_workflow_1.py --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0

[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 5
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best F: [-15392.37487079]
CST cleanup: attempted=True closed=True pid=56344
```

| Metric | Value |
|--------|-------|
| Initial evaluation | Synthetic `SOLVER_FAILED` (injected) |
| Retry loop invoked? | ✅ Yes — `run_retry_loop_no_cst` called |
| Retry `evaluate_once` | ✅ Real CST evaluation (iter -1 in log) |
| Retry CST metrics | ✅ `coupling_beta=2.08, resonant_freq=11.4245, q0=18630.9, ...` |
| Retry loop succeeded? | ✅ Yes — `result.succeeded = True` |
| Final Best F | **-15392.37** (real CST result, not all-ones failure penalty) |
| Retry diagnostics in log | ✅ "Retry runtime smoke: injecting synthetic SOLVER_FAILED for iteration 0" |

### What was live-validated

| Capability | Validated? | Evidence |
|------------|-----------|----------|
| Retry loop invoked via workflow wiring | ✅ Yes | Synthetic failure → `run_retry_loop_no_cst` called |
| Adapter retry attempt ran live CST | ✅ Yes | `evaluate_once` → `adapt_for_retry` → real CST eval → metrics computed |
| `final_record` used by optimizer | ✅ Yes | Best F = -15392.37 (real CST result) |
| Checkpoint records final result only | ✅ Yes | 1 checkpoint entry (not multiple for retries) |
| No orphan DE after cleanup | ✅ Yes | Only `cstd.exe` PID 10184 remained |
| No manual taskkill required | ✅ Yes | Cleanup `attempted=True closed=True` |

### What was NOT validated

| Capability | Status | Reason |
|------------|--------|--------|
| Durable DB | ❌ Not implemented | Separate track |
| Success reuse | ❌ Not implemented | Separate track |
| DB warm-start | ❌ Not implemented | Separate track |
| Failure reuse | ❌ Not implemented | Separate track |
| probably-infeasible skip | ❌ Rejected at runtime | Phase O design |
| Real COM recovery/reconnect | ❌ Not exercised | Tier 2+ recovery not triggered (max_tier=1) |
| Production campaign | ❌ Not attempted | Bounded single-eval only |

---

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short -v
→ 35 passed

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short → 12 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short → 50 passed

Total: 410 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST executed | ✅ Yes — bounded single-eval retry smoke |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed (restored after smoke) |
| Generated artifacts committed | ❌ Not committed |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Rejected at runtime |
| Tier 2+ recovery exercised | ❌ Not exercised (max_tier=1) |
| Real COM recovery exercised | ❌ Not exercised |

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
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/retry_taxonomy.py` | **Not modified** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Modified for smoke, restored | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` | **Not committed** |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` | **Not committed** |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` | **Not committed** |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
RW3 rfgun_sao retry runtime CST wiring + bounded live retry smoke

- Add final_record to RetryRuntimeResult; set in all exit paths
- Store penalty_values in record diagnostics for evaluator extraction
- Wire retry_runtime into single_pass workflow.py with mutex check
- Add synthetic smoke injection hook (env-var + config gated)
- Live CST smoke: synthetic SOLVER_FAILED → retry loop → real CST
  evaluation → Best F -15392.37, no orphan DE, no manual cleanup
- Config.local.yaml restored after smoke; no committed artifacts

No durable DB, no failure reuse, no tier-2 recovery (max_tier=1),
no production campaign.
```
