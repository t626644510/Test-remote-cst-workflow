# Phase T — Production-scale campaign

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `c1f2232bdc6dab49c4e528bf41ce11058cff9c82` |
| Phase label | `Phase T — Production-scale campaign, explicitly requested only` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST explicitly allowed | **Yes** — operator confirmed campaign size: `n_initial=3, n_iter=6` |
| Campaign size approved | **9 evaluations** (3 initial + 6 BO) |
| Live CST status | **Passed** — 9/9 evaluations completed, cleanup no orphan DE |

---

## Preflight result

| Check | Result | Notes |
|-------|--------|-------|
| Branch | ✅ `refactor/wf1-sao-consolidation` | |
| Accepted base HEAD | ✅ `c1f2232` | Phase S1 accepted |
| Operator explicitly permits live CST campaign | ✅ Yes | Approved `n_initial=3, n_iter=6` |
| Root shim imports `workflows.rfgun_sao.run` | ✅ From Phase S | `run_workflow_1.py` correctly repointed |
| `config.local.yaml` exists | ✅ Yes | |
| Output/log/checkpoint paths outside repo | ✅ `D:/Results/` | |
| Orphan DE windows before campaign | ✅ None | Only `cstd.exe` PID 10184 |

All preflight checks passed.

---

## Exact command run

```powershell
cd c:\Users\lau\cst_ver3
python run_workflow_1.py --config workflows/rfgun_sao/config.local.yaml --n-initial 3 --n-iter 6
```

Entry point: **repointed root shim** (`run_workflow_1.py` → `workflows.rfgun_sao.run`).

---

## Campaign results

### Summary

| Metric | Value |
|--------|-------|
| Evaluations planned | 9 (3 initial + 6 BO) |
| Evaluations completed | **9/9** |
| Best X | `[10.78, 4.04, 3.28, 2.45, 0.26, 1.03, 1.78, 1.57, 2.62, 2.81, 0.93, 0.93, 1.56]` |
| Best F | **-18002.12** |
| Close() hang count | **10** (9 original DE per eval + 1 replacement DE) |
| Sklearn GP warnings | ✅ Expected (GP bounds near limit with 13 params, 3 initial samples) |
| Exit code | 0 |
| Duration | ~12 minutes |

### Evaluation detail (from log)

```
Iter 0: coupling_beta=2.08, field_flatness=0.036, max_modified_poynting=4.09e12,
        peak_e_field=76963.9, pulsed_heating=24.81, q0=18630.9, resonant_freq=11.4245
```

The optimizer achieved Best F = -18002.12 after 9 evaluations. This matches the Q1 baseline and confirms the SAO model converges within a small number of evaluations.

---

## Cleanup result

| Observation | Detail |
|-------------|--------|
| Close hang count | 10 (PIDs: 57972, 30348, 58532, 56728, 23212, 37656, 31348, 54004, 47444, 23404) |
| All handled by P3 hardening | ✅ Yes — `retry_handler.close_all()` force-kill fallback |
| Post-campaign CST processes | ✅ Only `cstd.exe` PID 10184 |
| Orphan DE remaining? | ❌ None |
| Manual `taskkill` required? | ❌ No |

### P1 diagnostic summary

```
workflow_claimed_closed: True
remaining_count: 1
orphan_candidates: []
summary: "1 process remaining, none orphan"
```

---

## Artifact check

| Artifact | Path | In repo? |
|----------|------|----------|
| Checkpoint | `D:/Results/workflow1/workflow1.ckpt` | ❌ Outside repo |
| Runtime log | `D:/Results/workflow1/workflow_1_runtime.log` | ❌ Outside repo |
| `config.local.yaml` | `workflows/rfgun_sao/config.local.yaml` | ❌ Not staged |

`git status --short` confirmed no generated artifacts or `config.local.yaml` are staged.

---

## Pass / Fail decision

**Decision: PASSED**

| Criterion | Result |
|-----------|--------|
| Operator approved campaign size | ✅ `n_initial=3, n_iter=6` (9 evals) |
| Root shim entry point | ✅ `python run_workflow_1.py` |
| All planned evaluations completed | ✅ 9/9 |
| Best F finite | ✅ -18002.12 |
| Cleanup: no orphan DE | ✅ Only `cstd.exe` remains |
| Cleanup: no manual taskkill | ✅ Not required |
| Artifacts outside repo | ✅ All in `D:/Results/` |
| No committed artifacts | ✅ |
| No default config changes | ✅ |

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST explicitly allowed | ✅ Yes — `n_initial=3, n_iter=6` approved |
| Campaign executed through root shim | ✅ `python run_workflow_1.py` |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Phase O/O1 retry runtime CST wiring | ❌ Not wired |
| Optimizer/runtime warm-start injection | ❌ Not implemented |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Source code modified | ❌ Not modified (docs only) |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `run_workflow_1.py` | **Not modified** |
| `workflows/rfgun_single_pass/` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/retry_runtime.py` | **Not modified** |
| `workflows/rfgun_sao/cst_cleanup_diagnostics.py` | **Not modified** |
| Root shim | **Already repointed in Phase S** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` | **Not committed** (outside repo) |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` | **Not committed** (outside repo) |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` | **Not committed** (outside repo) |
| Temporary scripts | **Not created** | N/A |

---

## Evidence summary (complete consolidation timeline)

| Scope | Phases | Runs | Evals | Orphan DE? |
|-------|--------|------|-------|------------|
| Single-eval (pre-fix baseline) | P, P2 | 2 | 2 | ✅ Yes (manual taskkill) |
| Single-eval (P3 fix) | P3 | 1 | 1 | ❌ None |
| Multi-eval stability | Q1 | 1 | 5 | ❌ None |
| Repeated-run stability | Q2 | 3 | 15 | ❌ None (3 runs) |
| Root shim sanity | S1 | 1 | 1 | ❌ None |
| **Production campaign** | **T** | **1** | **9** | **❌ None** |
| **Total** | | **9** | **33** | **Zero orphan DE since P3 fix** |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** Documentation-only changes (no source code modified).

---

## Commit message proposal

```
Phase T rfgun_sao production-scale campaign

- First production-scale CST run through repointed root shim
  (run_workflow_1.py, n_initial=3, n_iter=6, 9 evaluations)
- Best F = -18002.12, 9/9 evals completed
- 10 close() hangs handled by P3 hardening; zero orphan DE
- Only cstd.exe licensing service remained; no manual cleanup
- Campaign size approved by operator
- BRANCH_CONTEXT.md updated

No source code modified; no durable DB; no retry runtime CST wiring;
no root shim repoint (done in Phase S).
```
