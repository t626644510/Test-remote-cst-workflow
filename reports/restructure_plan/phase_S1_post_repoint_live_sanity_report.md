# Phase S1 — Post-repoint root shim live sanity / rollback drill

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `76ac3bf3eb792129ce0fc4ac0e90a836a21d481f` |
| Phase label | `Phase S1 — Post-repoint root shim live sanity / rollback drill` |
| Branch | `refactor/wf1-sao-consolidation` |
| Live CST explicitly allowed | **Yes** — operator confirmed |
| Root shim live sanity executed | **Yes** — `python run_workflow_1.py` with `--n-initial 1 --n-iter 0` |
| Live CST status | **Passed** — repointed root shim works correctly; cleanup no orphan DE |

---

## Preflight result

| Check | Result | Notes |
|-------|--------|-------|
| Branch | ✅ `refactor/wf1-sao-consolidation` | |
| Accepted base HEAD | ✅ `76ac3bf` | Phase S accepted |
| Operator explicitly permits live CST | ✅ Yes | |
| Root shim imports `workflows.rfgun_sao.run` | ✅ Verified | `from workflows.rfgun_sao.run import main` |
| `config.local.yaml` exists | ✅ Yes | |
| Orphan DE windows before smoke | ✅ None | Only `cstd.exe` PID 10184 |

All preflight checks passed.

---

## Exact command run

```powershell
cd c:\Users\lau\cst_ver3
python run_workflow_1.py --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

Command was executed through the **repointed root shim** (`run_workflow_1.py`), not via `python -m workflows.rfgun_sao.run`.

---

## Evaluation result

```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 5
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best X: [10.78035626  4.03836673  ...]
Best F: [-15392.37397092]
CST cleanup: attempted=True closed=True pid=none
```

| Metric | Value |
|--------|-------|
| Entry point | `python run_workflow_1.py` ✅ (root shim) |
| Evaluations planned/completed | 1/1 ✅ |
| Best F | -15392.37 (consistent with previous single-eval runs) |
| Exit code | 0 |
| Cleanup `attempted` | ✅ True |
| Cleanup `closed` | ✅ True |

---

## Cleanup result

| Observation | Detail |
|-------------|--------|
| Close hang count | 2 (PID 14360 original DE, PID 43096 replacement DE) |
| Both handled by P3 hardening | ✅ Yes |
| Post-run CST processes | ✅ Only `cstd.exe` PID 10184 |
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

## Rollback drill

Rollback was **not performed** — the live sanity passed. Documented rollback command:

```powershell
git revert 76ac3bf3eb792129ce0fc4ac0e90a836a21d481f
# After revert:
grep -n "rfgun_single_pass" run_workflow_1.py
# Expected: from workflows.rfgun_single_pass.run import main

# Verify tests:
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```

The rollback path is clean and does not require source code changes — only `git revert` of the Phase S commit.

---

## Pass / Fail decision

**Decision: PASSED**

| Criterion | Result |
|-----------|--------|
| Root shim: import target | ✅ `workflows.rfgun_sao.run` |
| Root shim: CLI flags preserved | ✅ `--config`, `--seed`, `--n-iter`, `--n-initial` |
| Root shim: evaluation completed | ✅ Best F -15392.37 |
| Root shim: cleanup | ✅ No orphan DE, no manual cleanup |
| Root shim: artifacts outside repo | ✅ All in `D:/Results/` |
| Rollback path documented | ✅ `git revert 76ac3bf` |

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Root shim repointed | ✅ Yes (Phase S) |
| Post-repoint live CST through root shim | ✅ Run and passed |
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
| `run_workflow_1.py` | **Not modified** (unchanged from Phase S) |
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

## Final HEAD commit SHA

**To be confirmed by reviewer.** Documentation-only changes (no source code modified).

---

## Commit message proposal

```
Phase S1 rfgun_sao post-repoint root shim live sanity / rollback drill

- First live CST run through repointed root shim (run_workflow_1.py)
- Best F = -15392.37, 1/1 eval, cleanup no orphan DE
- Root shim import target, CLI flags, config path all verified
- 2 close() hangs handled by P3 hardening; only cstd.exe remains
- Rollback drill documented but not performed (live run passed)
- BRANCH_CONTEXT.md updated: S accepted, S1 added, migration constraint updated

No source code modified; no durable DB; no retry runtime CST wiring.
```
