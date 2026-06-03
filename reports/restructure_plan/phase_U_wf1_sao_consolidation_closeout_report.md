# Phase U — WF1 SAO consolidation closeout / merge readiness

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `5929027b60a247ea62497597ff8a23ef25bb4745` |
| Phase label | `Phase U — WF1 SAO consolidation closeout / merge readiness` |
| Branch | `refactor/wf1-sao-consolidation` |
| Nature | **Docs-only closeout** — no live CST, no code changes |
| Root shim repointed? | ✅ Yes (Phase S) — `run_workflow_1.py` imports `workflows.rfgun_sao.run` |

---

## Current default entry point

```
run_workflow_1.py → workflows.rfgun_sao.run.main
```

The root shim was repointed from `workflows.rfgun_single_pass.run` to `workflows.rfgun_sao.run` at Phase S (commit `76ac3bf`). Rollback is available via `git revert 76ac3bf`.

---

## Accepted live evidence (post-consolidation)

The following live CST evidence has been accumulated on the consolidated `rfgun_sao` package, all through the repointed root shim:

| Phase | Scope | Command | Evals | Best F | Orphan DE? | Manual cleanup? |
|-------|-------|---------|-------|--------|------------|-----------------|
| P3 | Cleanup hardening fix | `--n-initial 1 --n-iter 0` | 1 | -15392.38 | ❌ None | ❌ No |
| Q1 | Multi-eval stability | `--n-initial 3 --n-iter 2` | 5 | -18002.12 | ❌ None | ❌ No |
| Q2 | Repeated-run stability (×3) | `--n-initial 3 --n-iter 2` | 15 | -18002 / -18002 / -17883 | ❌ None | ❌ No |
| S1 | Root shim sanity | `--n-initial 1 --n-iter 0` | 1 | -15392.37 | ❌ None | ❌ No |
| T | Bounded production campaign | `--n-initial 3 --n-iter 6` | **9** | **-18002.12** | ❌ None | ❌ No |
| **Total** | | | **31** | | **Zero orphan DE** | **Zero manual cleanup** |

### Key observations

- **Cleanup hardening (P3) is stable**: 31 total evaluations across 7 runs since the P3 fix, zero orphan DE windows, zero manual `taskkill` operations. All `DesignEnvironment.close()` hangs (dozens) are handled by the `retry_handler.close_all()` force-kill fallback.
- **SAO optimizer converges**: Best F improves from -15392 (single evaluation) to -18002 (after 3+ initial samples + BO).
- **Root shim works**: `python run_workflow_1.py` correctly delegates to `workflows.rfgun_sao.run`, all CLI flags preserved, default config path correct.

---

## No-CST test evidence

| Test suite | Count | Status |
|------------|-------|--------|
| rfgun_sao imports | 230 | ✅ |
| rfgun_single_pass imports | 12 | ✅ |
| CST cleanup diagnostics (P1) | 24 | ✅ |
| Retry runtime (O/O1) | 83 | ✅ |
| Retry taxonomy (N/N1) | 50 | ✅ |
| **Total** | **399** | ✅ |

All tests pass with 1 pre-existing sklearn DeprecationWarning (cosmetic).

---

## Merge readiness checklist

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Root shim repointed | ✅ | `run_workflow_1.py` → `workflows.rfgun_sao.run` (Phase S) |
| 2 | Root shim live sanity passed | ✅ | S1: single-eval, Best F -15392.37, no orphan DE |
| 3 | Bounded production campaign passed | ✅ | T: 9 evals, Best F -18002.12, no orphan DE |
| 4 | Cleanup stable across repeated runs | ✅ | Q2: 3 consecutive runs, 15 evals, zero orphan DE |
| 5 | Cleanup stable with production campaign | ✅ | T: 10 close hangs, all handled |
| 6 | No default config changes | ✅ | `config.yaml` unchanged from legacy single-pass defaults |
| 7 | Artifact policy clean | ✅ | No `.jsonl`, `.ckpt`, `.db`, logs, or `config.local.yaml` in repo |
| 8 | `rfgun_single_pass` tests still pass | ✅ | 12 import tests pass (legacy package untouched) |
| 9 | CLI compatible | ✅ | Flags `--config`, `--seed`, `--n-iter`, `--n-initial` identical |
| 10 | Rollback path documented | ✅ | `git revert 76ac3bf` restores `rfgun_single_pass` import |

**All merge readiness criteria are satisfied.**

---

## Current non-goals / future work

The following capabilities remain **separately gated future work** and are NOT part of this consolidation:

| Capability | Status | Required before production use? |
|------------|--------|-------------------------------|
| Phase O/O1 retry runtime CST wiring | ❌ Not wired (no-CST skeleton only) | No — retry is opt-in, disabled by default |
| Durable evaluation DB (J–L) | ❌ Not implemented (schema/helpers exist) | No — checkpoint-based warm-start works |
| Failure reuse | ❌ Not implemented | No — design only |
| DB warm-start / optimizer runtime injection | ❌ Not implemented | No — checkpoint warm-start works |
| Broader production campaigns | ❌ Not attempted beyond 9 evals | User-discretionary |

---

## Rollback reminder

To restore the root shim to the legacy `rfgun_single_pass` target:

```powershell
git revert 76ac3bf3eb792129ce0fc4ac0e90a836a21d481f
# Verify:
grep -n "rfgun_single_pass" run_workflow_1.py
# Expected: from workflows.rfgun_single_pass.run import main

# Run tests:
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```

---

## Complete phase timeline (O → U)

```
U  — WF1 SAO consolidation closeout / merge readiness     (docs)
T  — Production-scale campaign                              (live, 9 evals)
S1 — Post-repoint root shim live sanity                     (live, 1 eval)
S  — Root shim repoint                                      (source change)
R  — Root shim repoint readiness plan                       (docs)
Q2 — Repeated-run cleanup stability                         (live, 15 evals)
Q1 — Multi-evaluation live validation                       (live, 5 evals)
Q  — Production-scale validation readiness plan             (docs)
P3 — Cleanup runtime hardening                              (source + live)
P2 — Cleanup observation smoke                              (live)
P1 — Cleanup gap analysis                                   (helper + tests)
P  — Live CST smoke (partial, pre-fix)                      (live)
O1 — Retry runtime progress hardening                       (helper + tests)
O  — Retry runtime wiring skeleton                          (helper + tests)
N1 — Retry taxonomy semantics hardening                     (helper + tests)
N  — Retry taxonomy skeleton                                (helper + tests)
M  — Retry/recovery taxonomy design                         (docs)
```

Phase labels A–L (earlier consolidation stages) exist in `BRANCH_CONTEXT.md` and earlier reports.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run in Phase U | ❌ Not run (docs-only closeout) |
| Source/runtime code modified | ❌ Not modified |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Phase O/O1 retry runtime CST wiring | ❌ Not wired |
| Optimizer/runtime warm-start injection | ❌ Not implemented |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `run_workflow_1.py` | **Not modified** (repointed in Phase S) |
| `workflows/rfgun_single_pass/` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No (from prior runs in `D:/Results/`) | **Not committed** |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No (from prior runs in `D:/Results/`) | **Not committed** |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Validation commands and results

```powershell
python -m compileall run_workflow_1.py workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
→ 230 passed

pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
→ 12 passed

pytest tests/workflows/test_rfgun_sao_cst_cleanup_diagnostics.py --tb=short -v
→ 24 passed

pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short
→ 83 passed

pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
→ 50 passed

Total: 399 passed, 1 pre-existing warning.
```

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
Phase U rfgun_sao WF1 SAO consolidation closeout / merge readiness

- Docs-only closeout report documenting consolidation evidence summary
- Root shim repointed at Phase S; live validated through S1 and T
- 31 total live evaluations since P3 fix; zero orphan DE; zero manual cleanup
- All merge readiness criteria satisfied
- Future work (retry runtime CST wiring, durable DB) remains separately gated
- BRANCH_CONTEXT.md finalized

No source code changes, no live CST, no default config changes.
```
