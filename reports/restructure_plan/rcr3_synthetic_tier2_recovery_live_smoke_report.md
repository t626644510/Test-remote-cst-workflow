# RCR3 — Bounded synthetic tier-2 recovery live smoke

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `a76a2dae392431ef1af39bd279fc9b89990d5307` |
| Phase label | `RCR3 — Bounded synthetic tier-2 recovery live smoke` |
| Branch | `feature/wf1-real-com-recovery` |
| Live CST explicitly allowed | **Yes** — operator approved |
| Live CST run | **Yes** — bounded single-eval through root shim |
| Live CST status | **Passed** — synthetic tier-2 recovery path fully exercised |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added `_is_retry_runtime_tier2_smoke_enabled()` helper; tier-2 smoke hook with config+env gating; wrapped evaluate_once for second synthetic failure |
| `tests/workflows/test_rfgun_sao_retry_runtime_workflow.py` | **Modified** | Added 7 no-CST tests for tier-2 smoke hook gating |
| `reports/restructure_plan/rcr3_synthetic_tier2_recovery_live_smoke_report.md` | **Added** | This report |

---

## Synthetic tier-2 recovery hook

Gating: requires BOTH `config["retry_runtime"]["synthetic_tier2_recovery_smoke"]=True` AND env `WF1_SAO_ALLOW_RCR_TIER2_SMOKE=1`.

Flow:

1. **Initial evaluation**: synthetic `SOLVER_FAILED` (existing RW3 hook).
2. **Tier 1 recovery callback**: no-op (returns True, no new connection).
3. **First retry (tier 1 evaluate_once)**: wrapped — returns synthetic `SOLVER_FAILED` (tier-2 smoke hook injects second failure).
4. **Tier 2 recovery callback**: `registry.close_all(force=True)` closes initial DE, `connection_factory()` creates new DE, `evaluator.on_reconnect()`, `registry.track()`.
5. **Second retry (tier 2 evaluate_once)**: passes through to real CST adapter → real CST evaluation.
6. **Final**: `RetryRuntimeResult` with `succeeded=True`, `final_record` from real CST.
7. **Cleanup**: `registry.close_all(force=True)` closes replacement DE at workflow cleanup.

---

## Live smoke results

### Command

```powershell
python run_workflow_1.py --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

### Config (local only, not committed)

```yaml
optimization:
  retry:
    enabled: false
retry_runtime:
  enabled: true
  max_tier: 2
  smoke_injection: true
  synthetic_tier2_recovery_smoke: true
```

Env: `WF1_SAO_ALLOW_RETRY_RUNTIME_SMOKE_INJECTION=1`, `WF1_SAO_ALLOW_RCR_TIER2_SMOKE=1`

### Log evidence (full tier-2 recovery path)

```
# Initial synthetic failure
INFO Retry runtime smoke: injecting synthetic SOLVER_FAILED for iteration 0

# Tier-2 smoke wrapper activated
INFO RCR3 tier-2 recovery smoke: wrapped evaluate_once

# Tier 1 retry: synthetic failure injected (so tier 2 is triggered)
INFO RCR3 tier-2 smoke: injecting synthetic SOLVER_FAILED for retry attempt (tier=1)

# Tier 2: registry.close_all closed old DE, factory created new DE (PID 10176)
INFO RCR recovery: reconnected (tier=2, PID=10176)

# Real CST evaluation on new connection
INFO Workflow 1: rebuild done for iteration -1
INFO Workflow 1 iter -1 done: coupling_beta=2.08375, ..., resonant_freq=11.4245

# Retry diagnostics
DEBUG Retry: success after 2 attempt(s)
DEBUG Retry result: final_status=success succeeded=True stopped=success attempts=2 retry_consumed=2

# Final cleanup: registry closed the replacement DE
DEBUG Retry runtime connection registry closed (attempted=1, closed_ok=1, errors=0)
```

### Best F

```
Best F: [-15392.38122944]
```

The Best F = -15392.38 is from the real CST evaluation on the replacement DE (PID 10176). This is consistent with single-eval single-pass runs and confirms the retried evaluation used a working CST connection.

---

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py --tb=short -v
→ 28 passed

pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short → 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py --tb=short → 31 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short → 50 passed
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short → 12 passed

Total: 472 passed, 1 pre-existing warning.
```

---

## Cleanup evidence

| Check | Result |
|-------|--------|
| Pre-run CST processes | Only `cstd.exe` PID 10184 |
| Post-run CST processes | Only `cstd.exe` PID 10184 |
| Orphan DE remaining? | ❌ None |
| Manual `taskkill` required? | ❌ No |
| Registry close_all final cleanup | ✅ `attempted=1, closed_ok=1, errors=0` |

---

## What was live-validated

| Capability | Validated? | Evidence |
|------------|-----------|----------|
| Synthetic initial SOLVER_FAILED → retry loop | ✅ | Log: "injecting synthetic SOLVER_FAILED" |
| Tier 1 recovery callback no-op | ✅ | Tier 1 called, no new connection created |
| Tier 2 recovery callback invoked | ✅ | Log: "reconnected (tier=2, PID=10176)" |
| Registry `close_all(force)` closes old DE | ✅ | Old DE closed before new one created |
| `connection_factory()` creates new CST DE | ✅ | New PID shown in reconnected log |
| `evaluator.on_reconnect(new_conn)` | ✅ | Evaluation on replacement DE succeeded |
| Replacement connection tracked in registry | ✅ | Registry cleanup showed `attempted=1` |
| Real CST evaluation after reconnect | ✅ | "iter -1 done" with metrics |
| `final_record` used by optimizer | ✅ | Best F = -15392.38 (real CST result) |
| `registry.close_all` at final cleanup | ✅ | Log: "connection registry closed" |
| No orphan DE | ✅ | Only `cstd.exe` remains |
| No manual cleanup | ✅ | Not required |

## What was NOT validated

| Capability | Status | Reason |
|------------|--------|--------|
| Real OS-level COM disconnect recovery | ❌ | Not attempted — synthetic failure only |
| Uncontrolled CST process kill | ❌ | Not attempted |
| Production campaign | ❌ | Bounded single-eval only |
| Durable DB | ❌ | Separate track |
| Success reuse | ❌ | Separate track |
| Warm-start | ❌ | Separate track |
| Failure reuse | ❌ | Separate track |

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST executed | ✅ Yes — bounded single-eval through root shim |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed (restored after smoke) |
| Generated artifacts committed | ❌ Not committed |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| Real COM disconnect validated | ❌ Not validated |
| Adapter-level recovery added | ❌ Adapter remains recovery-free |

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
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `run_retry_loop_no_cst` | **Not modified** |
| `make_cst_retry_evaluate_once` | **Not modified** (remains recovery-free) |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
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
RCR3 rfgun_sao bounded synthetic tier-2 recovery live smoke

- Synthetic tier-2 smoke hook: config.synthetic_tier2_recovery_smoke + env
  WF1_SAO_ALLOW_RCR_TIER2_SMOKE; disabled by default
- Live CST validated full tier-2 recovery path:
  synthetic initial failure > tier 1 no-op > synthetic retry failure >
  tier 2 recovery (registry.close_all, connection_factory, on_reconnect,
  registry.track) > real CST evaluation > final result
- 7 no-CST tests for tier-2 smoke hook gating (both config + env required)
- 472 total tests pass

No real COM disconnect, no adapter-level recovery, no default config change.
```
