# Phase P2 — CST cleanup observation live smoke / hardening decision

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `07d913359122ba20a439ff560342f3188436d540` |
| Phase label | `Phase P2 — CST cleanup observation live smoke / hardening decision` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST explicitly allowed | **Yes** — operator confirmed in session |
| Live CST smoke executed | **Yes** — minimal `single_pass`, `n_initial=1, n_iter=0` |
| Live CST status | **Completed** — evaluation succeeded; orphan DE pattern confirmed reproducible |

---

## Preflight result

| Check | Result | Notes |
|-------|--------|-------|
| Branch | ✅ `refactor/wf1-sao-consolidation` | |
| Accepted base HEAD | ✅ `07d9133` | P1 accepted |
| Operator explicitly permits live CST | ✅ Yes | Confirmed via AskUserQuestion |
| `config.local.yaml` exists | ✅ Yes | Valid CST library & project paths |
| CST project file accessible | ✅ Yes | `D:/workflow_elgun/PickupDesign_2026.cst` |
| CST Python libraries importable | ✅ Yes | Verified in Phase P |
| `cstd.exe` licensing service | ✅ Yes | PID 10184, no window |
| Orphan DE windows before smoke | ✅ None | Only `cstd.exe` PID 10184 present |

All preflight checks passed.

---

## Exact command run

```powershell
cd c:\Users\lau\cst_ver3
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

Config: `config.local.yaml` (single_pass, 13 parameters, 5 objectives).
Overrides: `--n-initial 1 --n-iter 0` (1 total evaluation).

---

## Evaluation result

```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 5
Done. Best X: [10.78035626  4.03836673  ...]
Best F: [-15392.37379935]
CST cleanup: attempted=True closed=True pid=none
```

Best F consistent with Phase P (-15392.38 vs -15392.37). Evaluation completed normally.

---

## Cleanup observation

### Runtime log sequence

1. `DesignEnvironment.close() hung (PID=50324) — abandoning COM thread` — **same hang pattern as Phase P**.
2. `Proactive graceful reset requested` — legacy `cst_optimization.core.retry` triggered reconnect.
3. `Connected to new CST DE, PID=36496` — new DE opened for cleanup.
4. `CST cleanup: attempted=True closed=True pid=None` — workflow cleanup claimed success.
5. **Orphan DE window PID 36496 remained** with visible title "CST Studio Suite 2026".

### Post-smoke process classification (using P1 helper)

```
PID=10184  cstd.exe                                  cls=licensing_service   kill=False  licensing service must remain running
PID=36496  CST DESIGN ENVIRONMENT_AMD64.exe          cls=design_environment  kill=True   DE window still present after workflow cleanup
```

### `summarize_cleanup_observation()` output

```
workflow_claimed_closed: True
workflow_pid: 50324
remaining_count: 2
orphan_candidates: [{'pid': 36496, 'process_name': 'CST DESIGN ENVIRONMENT_AMD64.exe',
                     'has_window_title': True,
                     'reason': 'DE window still present after workflow cleanup'}]
summary: "1/2 processes identified as orphan DE candidate"
```

The P1 diagnostic helper correctly classified both processes and identified the orphan.

### Manual cleanup

Manual `taskkill /PID 36496 /F` was required to terminate the orphan DE. After cleanup,
only `cstd.exe` PID 10184 (licensing service) remained — normal state.

---

## Cleanup gap assessment

| Aspect | Phase P | Phase P2 | Verdict |
|--------|---------|----------|---------|
| Evaluation | Completed (Best F = -15392.38) | Completed (Best F = -15392.37) | ✅ Consistent |
| `close()` hang | PID 56996 | PID 50324 | ✅ Reproducible in two independent runs |
| Orphan DE PID | 30808 | 36496 | ✅ Pattern confirmed: legacy retry creates new DE that is not fully terminated |
| Window title | "CST Studio Suite 2026" | "CST Studio Suite 2026" | ✅ Consistent |
| Manual cleanup required | `taskkill /PID 30808 /F` | `taskkill /PID 36496 /F` | ✅ Required in both runs |
| P1 helper accuracy | N/A (P1 didn't exist) | Correctly classified both processes | ✅ P1 helper validated |

**Cleanup reliability gap is confirmed open and reproducible.** The orphan DE pattern
is deterministic — not a transient glitch.

---

## Decision

### Cleanup runtime hardening recommended before retry runtime CST wiring

The evidence from two independent live CST runs shows:

1. **`DesignEnvironment.close()` always hangs** in this environment. The COM thread
   abandonment is the entry point to the orphan chain.

2. **The legacy retry proactive reset is the proximate cause** of the orphan DE.
   It opens a new DE to perform cleanup, but does not fully terminate the OS process.
   The DE remains visible and requires manual force-kill.

3. **Any retry/recovery mechanism that restarts CST** will accumulate orphan DE
   windows unless the cleanup lifecycle is hardened first. With `max_tier=3`,
   running the retry loop through 3 CST-backed evaluations could leave up to 3
   orphan DE windows per parameter point.

4. **The P1 diagnostic helper is validated** and can be used by future hardening
   phases to classify processes and detect orphans without importing CST libraries.

**Recommended next step**: Phase P3 — cleanup runtime hardening in
`src/cst_optimization/`, only with explicit operator approval. The fix should
ensure that `DesignEnvironment.close()` either:
- Does not hang (timeout with force-termination of the OS process), or
- The legacy retry proactive reset fully terminates the replacement DE after
  cleanup, or
- A post-cleanup watchdog force-kills any remaining DE process by PID.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST explicitly allowed | ✅ Yes |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Root shim repoint | ❌ Not done |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Retry runtime wired to CST runner | ❌ Not wired |
| Cleanup reliability gap | ⚠️ **Confirmed open and reproducible** |
| Runtime cleanup code modified | ❌ Not modified (`src/cst_optimization/` unchanged) |
| P1 diagnostic helper validated | ✅ Yes — live smoke confirmed correct classification |

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
| `workflows/rfgun_sao/cst_cleanup_diagnostics.py` | **Not modified** |
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

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
```
→ Compiles OK.

```powershell
pytest tests/workflows/test_rfgun_sao_cst_cleanup_diagnostics.py --tb=short -v
```
→ **24 passed** (P1 helper).

```powershell
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short
```
→ **83 passed**.

```powershell
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
```
→ **50 passed**.

```powershell
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```
→ **229 passed** (1 pre-existing warning).

```powershell
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
```
→ **12 passed**.

**Total: 398 passed, 1 pre-existing warning.**

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** This is a documentation-only change (no code modified).
Expected HEAD: `07d913359122ba20a439ff560342f3188436d540` if no code changes accompany
this report.

---

## Commit message proposal

```
Phase P2 rfgun_sao CST cleanup observation live smoke / hardening decision

- Two-phase live CST (Phase P + P2) confirms identical orphan DE pattern:
  close() hang → legacy retry reset → orphan DE window requires manual kill
- P1 diagnostic helper validated: correctly classifies cstd vs DE, detects orphan
- Cleanup gap confirmed open and reproducible; runtime hardening recommended
  before retry runtime CST wiring
- BRANCH_CONTEXT.md updated

No code changes, no runtime cleanup modification, no live CST wiring.
No durable DB, no failure reuse, no retry runtime wiring, no root shim repoint.
```
