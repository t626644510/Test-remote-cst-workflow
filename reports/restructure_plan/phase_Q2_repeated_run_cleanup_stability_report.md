# Phase Q2 — Repeated-run cleanup stability validation

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `9b154a1e05e9a8f7df1ec50475aadb30e835616a` |
| Phase label | `Phase Q2 — Repeated-run cleanup stability validation` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST explicitly allowed | **Yes** — operator confirmed 3 consecutive runs |
| Repeated runs executed | **3** consecutive `n_initial=3, n_iter=2` runs |
| Live CST status | **Passed** — all 3 runs clean, no orphan DE accumulation |

---

## Preflight result

| Check | Result | Notes |
|-------|--------|-------|
| Branch | ✅ `refactor/wf1-sao-consolidation` | |
| Accepted base HEAD | ✅ `9b154a1` | Phase Q1 accepted |
| Operator explicitly permits repeated live CST | ✅ Yes — 3 runs approved | |
| `config.local.yaml` exists | ✅ Yes | Valid CST paths |
| CST project file accessible | ✅ Yes | `D:/workflow_elgun/PickupDesign_2026.cst` |
| `cstd.exe` licensing service | ✅ Yes | PID 10184, no window |
| Orphan DE windows before smoke | ✅ None | Only `cstd.exe` PID 10184 present |

All preflight checks passed.

---

## Command executed (3 times)

```powershell
cd c:\Users\lau\cst_ver3
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 3 --n-iter 2
```

Expected per run: 3 initial samples + 2 Bayesian optimization iterations = **5 evaluations**.

---

## Per-run results

| Metric | Run 1 | Run 2 | Run 3 |
|--------|-------|-------|-------|
| Planned | 5 (3+2) | 5 (3+2) | 5 (3+2) |
| Completed | ✅ 5 | ✅ 5 | ✅ 5 |
| Best F | **-18002.12** | **-18002.12** | **-17882.53** |
| Close hang count | 6 | 6 | 6 |
| Cleanup `attempted` | ✅ True | ✅ True | ✅ True |
| Cleanup `closed` | ✅ True | ✅ True | ✅ True |
| Orphan DE remaining? | ❌ None | ❌ None | ❌ None |
| Manual `taskkill` needed? | ❌ No | ❌ No | ❌ No |
| Only `cstd.exe` remains? | ✅ Yes | ✅ Yes | ✅ Yes |
| Artifacts outside repo? | ✅ Yes | ✅ Yes | ✅ Yes |

### Notes on Best F variation

Runs 1 and 2 returned identical Best F (-18002.12), while Run 3 returned -17882.53. This ~0.7% variation is expected from the SAO optimizer's stochastic acquisition function (EI with noise) and different initial sample positions. All three values are consistent with the -18002 baseline established in Phase Q1.

### Close hang pattern

All 3 runs exhibited 6 `DesignEnvironment.close() hung` warnings. With 5 evaluations per run, the breakdown is:
- 5 hangs from original DE processes (one per evaluation)
- 1 hang from a replacement DE created by `force_reset()` during post-eval cleanup

All 18 total close hangs (3 runs × 6) were handled by the P3 cleanup hardening (`retry_handler.close_all()` + `CSTConnection.close()` force-kill fallback).

---

## Post-run process classification

After each run, the P1 diagnostic helper confirmed:

```
  workflow_claimed_closed: True
  remaining_count: 1
  orphan_candidates: []
  summary: "1 process remaining, none orphan"
```

Only `cstd.exe` PID 10184 (licensing service) was present after every run. No orphan DE windows accumulated across the 3-run sequence.

---

## Pass / Fail decision

**Decision: PASSED**

| Criterion | Result |
|-----------|--------|
| All 3 consecutive runs completed | ✅ Yes |
| All 15 evaluations completed | ✅ Yes (5 per run) |
| Run-to-run cleanup: no orphan DE accumulation | ✅ Only `cstd.exe` remains after each run |
| Manual taskkill needed after any run? | ❌ No — none required |
| Checkpoint/logs outside repo | ✅ `D:/Results/` |
| No committed artifacts | ✅ None |
| No config default changes | ✅ Not changed |

---

## Cleanup stability assessment

**Cleanup reliability is stable across repeated runs.** The P3 hardening (`retry_handler.close_all()`) correctly terminates all DE connections regardless of run count:

- No orphan DE accumulation after 3 consecutive runs
- No manual intervention needed
- `cstd.exe` licensing service unaffected throughout
- Each run's 6 close hangs fully handled via force-kill fallback
- Checkpoint cleared between runs (fresh start for each)

This meets the cleanup stability requirement for Phase R (root shim repoint readiness) planning.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST explicitly allowed | ✅ Yes — 3 runs approved |
| Repeated runs executed | ✅ 3 consecutive runs |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Root shim repoint | ❌ Not done |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Retry runtime wired to CST runner | ❌ Not wired |
| Full production-scale validation | ❌ Not attempted |
| Cleanup stability sufficient for Phase R | ✅ Yes |

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
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` (3×) | **Not committed** (outside repo) |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` (3×) | **Not committed** (outside repo) |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` | **Not committed** (outside repo) |
| Temporary scripts | **Not created** | N/A |

---

## Key findings

1. **P3 cleanup hardening is stable across repeated runs**. 3 consecutive runs × 5 evaluations × 6 close hangs = 18 total hangs, all handled. Zero orphan DE accumulation.

2. **No manual intervention needed** across the entire 3-run sequence. This is a significant improvement over the pre-P3 state where every live run required manual `taskkill`.

3. **SAO results are consistent**. Best F values (-18002, -18002, -17883) are tightly clustered, confirming repeatable optimizer behaviour.

4. **Cleanup reliability meets Phase R readiness criteria**. The cleanup stability demonstrated across 3 repeated runs is sufficient to proceed with root shim repoint readiness planning.

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** This is a documentation-only change (no code modified).

---

## Commit message proposal

```
Phase Q2 rfgun_sao repeated-run cleanup stability validation

- 3 consecutive runs (n_initial=3, n_iter=2, 5 evals each = 15 total)
- All runs clean: Best F -18002.12 / -18002.12 / -17882.53
- 18 total close() hangs handled by P3 fix; zero orphan DE accumulation
- No manual taskkill required across entire 3-run sequence
- Cleanup stability confirmed sufficient for Phase R readiness
- BRANCH_CONTEXT.md updated

No code changes, no durable DB, no retry runtime CST wiring,
no root shim repoint.
```
