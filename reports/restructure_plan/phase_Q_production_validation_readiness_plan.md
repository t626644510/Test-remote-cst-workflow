# Phase Q — Production-scale validation readiness plan

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `0251aee258e4189a8b8381da18f24bf75ffb2325` |
| Phase label | `Phase Q — Production-scale validation readiness plan` |
| Branch | `refactor/wf1-sao-consolidation` |
| Nature | **Docs-only** — no code changes, no live CST |
| Live CST run | **No** — not required for this phase |

---

## Current accepted status (through Phase P3)

### What has live evidence

| Capability | Phase | Evidence |
|------------|-------|----------|
| Role metrics (optimize/threshold/report_only) | B5 | Best F = -17534.24, 5 metrics computed |
| Runner-level CST cleanup | B5.1 | `CST cleanup: attempted=True closed=True pid=<PID>`; live verified |
| Gate runtime rejection | B9 | q0 raw=18630.8 vs threshold → `gate_reject:q0_gate`, Best F=1.0 |
| Single-pass sanity (minimal) | P/P2/P3 | Three runs with `n_initial=1, n_iter=0`, consistent Best F ≈ -15392.38 |
| Cleanup hardening (orphan DE fix) | P3 | Both original and replacement DE properly terminated; no manual `taskkill` needed |

### What does NOT have live evidence

| Capability | Status | Notes |
|------------|--------|-------|
| Phase O/O1 retry runtime CST wiring | ❌ Not wired | `retry_runtime.py` is standalone no-CST; no CST-backed `evaluate_once` exists |
| Durable evaluation DB | ❌ Not implemented | Schema/helpers exist (J–L) but no runtime DB |
| Failure reuse | ❌ Not implemented | Design only |
| Optimizer/runtime warm-start injection | ❌ Not implemented | Checkpoint-based warm-start exists; DB warm-start does not |
| Production-scale SAO run | ❌ Not attempted | Only `n_initial=1, n_iter=0` minimal runs |
| Root shim repoint | ❌ Not done | `run_workflow_1.py` still points to `rfgun_single_pass` |

### Gap summary

The `rfgun_sao` package has extensive **no-CST test coverage** (398 tests) and **minimal live CST sanity** (3 single-evaluation runs). The gap between "minimal live" and "production-scale validation" includes:

- No multi-evaluation run (initial samples + BO iterations)
- No retry/recovery CST integration
- No evaluation database persistence
- No staged search or adaptive bounds in live CST
- No root shim traffic (all runs via `python -m workflows.rfgun_sao.run`)

---

## Proposed validation matrix

### Tier 1: Mandatory sanity (must pass before any production run)

| Scenario | What to validate | Success criteria |
|----------|-----------------|------------------|
| T1.1 Single-pass minimal | `n_initial=1, n_iter=0` | Evaluation completes, Best F finite, cleanup no orphan |
| T1.2 Single-pass small | `n_initial=3, n_iter=2` | Multiple evaluations complete, checkpoint written, cleanup no orphan |
| T1.3 Gate rejection | Known-failing parameter | `gate_reject` logged, Best F=1.0, cleanup no orphan |

### Tier 2: Production-like (only after T1 passes)

| Scenario | What to validate | Success criteria |
|----------|-----------------|------------------|
| T2.1 SAO convergence | `n_initial=10, n_iter=20` | Optimizer converges, Best F lower than single samples |
| T2.2 Repeated-run stability | 3 consecutive runs with same config | Consistent results, no residual CST processes |
| T2.3 Interrupt-and-resume | Ctrl+C during run, restart from checkpoint | Checkpoint loaded, evaluations resume |

### Tier 3: Advanced integration (only after T2, requires separate wiring phases)

| Scenario | What to validate | Notes |
|----------|-----------------|-------|
| T3.1 Retry loop CST | Engineered solver failure + retry | Requires CST-backed `evaluate_once` callback (Phase O/O1 wiring) |
| T3.2 Inter-pass recovery | Calibration failure → recovery → retry | Requires inter-pass recovery wiring |
| T3.3 Evaluation database | Cross-run warm-start from DB | Requires durable DB implementation |
| T3.4 Staged search + adaptive bounds | Multi-stage SAO with adaptive bounds | Requires staged/adaptive runtime wiring (Phases F–I) |
| T3.5 Root shim traffic | `run_workflow_1.py` → `rfgun_sao` | Latest — only after all other T3 criteria pass |

---

## Success criteria

A production-scale validation run is considered **successful** if and only if:

1. **Evaluation completes** — optimizer produces a result, exit code 0.
2. **Metrics finite** — all objective metrics are finite where expected.
3. **Cleanup no orphan** — after workflow completes, no CST Design Environment process remains. Only `cstd.exe` licensing service may be running.
4. **No manual cleanup** — no `taskkill /F` or similar manual intervention needed.
5. **No committed artifacts** — `config.local.yaml`, `.ckpt`, `.jsonl`, `.sqlite`, `.db`, logs, and CST output directories are never staged or committed.
6. **No config default changes** — `workflows/rfgun_sao/config.yaml` retains its default values (single_pass mode, retry disabled, JSONL disabled, DB disabled).

---

## Failure criteria

Any of the following constitutes a **failure**:

| Condition | Severity | Action |
|-----------|----------|--------|
| Orphan DE window remains after cleanup | **Blocker** | Do not proceed; investigate and fix before next run |
| Manual `taskkill` required | **Blocker** | Do not proceed; cleanup hardening regression |
| Retry loop accumulates DE windows | **Blocker** | Retry runtime CST wiring must not proceed |
| Evaluation fails with solver error | **Warning** | Investigate; may be expected transient |
| Checkpoint/log artifacts committed | **Blocker** | Revert commit; add to `.gitignore` if needed |
| Root shim changed prematurely | **Blocker** | Revert immediately; root shim is last |

---

## Artifact policy

| Artifact | Policy | Enforcement |
|----------|--------|------------|
| `config.local.yaml` | Never commit | `.gitignore` (already present) |
| `*.ckpt` files | Never commit | Written to `D:/Results/` (outside repo) |
| `*.jsonl` files | Never commit | Written to `D:/Results/` (outside repo); disabled by default |
| `*.sqlite` / `*.db` | Never commit | Not yet implemented; must be configurable to path outside repo |
| `D:/Results/*` | Never commit | Outside repository boundary |
| CST output dirs | Never commit | `D:/workflow_elgun/PickupDesign_*` (outside repo) |
| Logs | Never commit | Configurable via `logging.output_dir`; must point outside repo |
| Report summaries | Commit only | As markdown in `reports/restructure_plan/` |
| Temporary scripts | Never commit | For live runs, use ad-hoc commands described in report |

Live CST evidence must be summarized in the phase report only (stdout snippets, key metrics, cleanup observations). Raw logs and checkpoints belong outside the repository.

---

## Root shim gating criteria

The root shim (`run_workflow_1.py` → `rfgun_sao`) must NOT be repointed until ALL of the following are met:

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | Production validation accepted | At least T1 + T2.1 (SAO convergence) pass |
| 2 | Cleanup reliability accepted | P3 fix verified across ≥3 consecutive runs with no orphan DE |
| 3 | Default config remains safe | Default `config.yaml` has retry disabled, JSONL disabled, DB disabled, single_pass mode |
| 4 | No regression in `rfgun_single_pass` | All existing single-pass tests still pass |
| 5 | Rollback plan documented | See below |

---

## Rollback plan

If root shim repoint causes issues:

1. **Immediate revert**: `git revert <root-shim-commit>`
2. **Restore previous HEAD**: `git checkout <previous-accepted>`
3. **Manual cleanup checklist**:
   - Verify `run_workflow_1.py` points to `rfgun_single_pass`
   - Run single-pass sanity (T1.1) to confirm
   - No orphan DE windows
   - No CST processes other than `cstd.exe`
   - Check `.gitignore` for correct exclusion patterns
4. **Root cause investigation** in a separate branch

---

## Decision

### Proceed to Phase Q1?

| Factor | Assessment |
|--------|-----------|
| P3 fix validated | ✅ Yes — minimal single-pass cleanup works |
| No-CST test coverage | ✅ 398 tests |
| Production-scale run ready? | ⚠️ **Not yet** — T1.2 (multi-evaluation) and T2.1 (SAO convergence) are the minimum next steps |
| Retry runtime CST wiring ready? | ❌ No — Phase O/O1 `retry_runtime.py` is still no-CST only |
| Root shim repoint ready? | ❌ No — must be last |

**Recommended next step**: Phase Q1 — minimal multi-evaluation live validation (`n_initial=3, n_iter=2`) to verify SAO convergence and repeated-run cleanup stability. Only if operator explicitly requests it.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run in Phase Q | ❌ Not run (docs-only phase) |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Root shim repoint | ❌ Not done |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Retry runtime wired to CST runner | ❌ Not wired |
| Production-scale validation run | ❌ Not attempted |

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
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** This is a documentation-only change (no code modified).
Expected HEAD: `0251aee258e4189a8b8381da18f24bf75ffb2325` if no code changes accompany this report.

---

## Commit message proposal

```
Phase Q rfgun_sao production-scale validation readiness plan

- Docs-only readiness plan covering validation matrix (T1/T2/T3),
  success/failure criteria, artifact policy, root shim gating, and
  rollback plan
- No code changes, no live CST, no default config changes
- BRANCH_CONTEXT.md updated

No durable DB, no failure reuse, no retry runtime CST wiring,
no root shim repoint.
```
