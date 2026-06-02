# Phase P — Live CST smoke for retry/recovery

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `c1d73471ea78f9674de7fa37bca5361ce0ae8813` |
| Phase label | `Phase P — Live CST smoke for retry/recovery, explicitly requested only` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST explicitly allowed | **Yes** — operator confirmed in session |
| Live CST smoke executed | **Yes** — minimal `single_pass` with `n_initial=1, n_iter=0` |
| Live CST status | **Partial** — evaluation succeeded but cleanup revealed orphan DE issue |

---

## Preflight result

| Check | Result | Notes |
|-------|--------|-------|
| Branch | ✅ `refactor/wf1-sao-consolidation` | |
| Accepted base HEAD | ✅ `c1d73471ea78f9674de7fa37bca5361ce0ae8813` | O/O1 accepted |
| Operator explicitly permits live CST | ✅ Yes | Confirmed via AskUserQuestion |
| `config.local.yaml` exists | ✅ Yes | Valid CST library & project paths |
| CST project file `PickupDesign_2026.cst` | ✅ Yes | `D:/workflow_elgun/PickupDesign_2026.cst` |
| CST Python libraries | ✅ Yes | `D:/CST2026/CST Studio Suite 2026/AMD64/python_cst_libraries` — importable |
| `cstd.exe` licensing service | ✅ Yes | PID 10184, no window |
| Orphan DE windows before smoke | ✅ None | No prior DE windows |
| CST DE can be created | ✅ Yes | Verified with `cst.interface.DesignEnvironment()` |

All preflight checks passed. Proceeded with minimal live smoke.

---

## Exact command run

```powershell
cd c:\Users\lau\cst_ver3
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

Config used: `workflows/rfgun_sao/config.local.yaml` (CST paths, single_pass mode, 13 parameters, 5 objectives).
Overrides: `--n-initial 1 --n-iter 0` (1 total evaluation).

---

## Smoke result

### Evaluation output

```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 5
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best X: [10.78035626  4.03836673  ...]
Best F: [-15392.37577983]
CST cleanup: attempted=True closed=True pid=none
Log: D:/Results\workflow1\workflow_1_runtime.log
```

### Metrics computed

| Metric | Value |
|--------|-------|
| `coupling_beta` | 2.08375 |
| `field_flatness` | 0.035853 |
| `max_modified_poynting` | 4.09367e+12 |
| `peak_e_field` | 76963.9 V/m |
| `pulsed_heating` | 24.8087 |
| `q0` | 18630.9 |
| `resonant_freq` | 11.4245 GHz |

Best F: `-15392.38` (consistent with previous live smokes: B5 got -17534.24, B9 got 1.0 with gate rejection).

### Cleanup observations

1. Runtime log shows `DesignEnvironment.close() hung (PID=56996) — abandoning COM thread`.
   This is a **known behaviour** documented in B5.1. The COM thread is abandoned gracefully.
2. The `cst_optimization.core.retry` module triggered a "Proactive graceful reset" and
   connected a new DE (PID 30808) for cleanup.
3. **Orphan DE window left open**: PID 30808 (`CST DESIGN ENVIRONMENT_AMD64`) remained
   after the run completed. Manual `taskkill /PID 30808 /F` was required.
4. `cstd.exe` licensing service (PID 10184) remained running normally after cleanup.

### Cleanup gap

The final cleanup message `attempted=True closed=True pid=none` indicates the workflow
connection was marked closed, but the underlying DE process (PID 30808) was not
terminated. This is a **pre-existing cleanup reliability gap** (not introduced by
Phase O/O1) that would affect retry/recovery if integration requires restarting CST.

### Retry runtime status

The Phase O/O1 `retry_runtime.py` was **not exercised** during this smoke:
- No `RetryRuntimeConfig` was created or used.
- No `run_retry_loop_no_cst()` was called.
- No `_normalize_retry_record()` was triggered.
- All retry-related log entries came from the legacy `cst_optimization.core.retry` module.
- The new retry runtime is not yet wired into the CST runner (`run.py`).

This confirms that retry/recovery CST integration is entirely future work.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST was explicitly allowed | ✅ Yes |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Root shim repoint | ❌ Not done |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |

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
| `workflows/rfgun_sao/retry_runtime.py` | **Not modified** |
| `workflows/rfgun_sao/retry_taxonomy.py` | **Not modified** |
| Root shim | **Not repointed** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` | **Not committed** (outside repo) |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` | **Not committed** (outside repo) |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` (cleaned up) | **Not committed** (outside repo) |
| Temporary scripts | **Not created** | N/A |

---

## Key findings

1. **CST environment is ready** for future retry/recovery integration:
   - Libraries importable ✅
   - Licensing service running ✅
   - Project file accessible ✅
   - Single evaluation completes ✅

2. **Cleanup reliability gap**: The `DesignEnvironment.close()` hang and orphan DE
   window are pre-existing issues (documented in B5.1). Any retry/recovery mechanism
   that restarts or reconnects CST must handle this gracefully, possibly by tracking
   PID and force-killing on cleanup failure.

3. **Retry runtime not wired**: The Phase O/O1 `retry_runtime.py` is a standalone
   no-CST module. Wiring it into the CST pipeline would require:
   - Creating a CST-backed `evaluate_once` callback
   - Integrating `RetryRuntimeConfig` into the configuration system
   - Handling the CST reconnect/cleanup lifecycle within retry loops

4. **Legacy retry still active**: The existing `cst_optimization.core.retry` module
   (legacy, not O/O1) triggered a reconnect during cleanup. Its interaction with
   the new retry runtime would need careful design in future phases.

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** This report is a documentation-only change
(no code modified). Expected HEAD: `c1d73471ea78f9674de7fa37bca5361ce0ae8813`
if no code changes are committed alongside this report.
