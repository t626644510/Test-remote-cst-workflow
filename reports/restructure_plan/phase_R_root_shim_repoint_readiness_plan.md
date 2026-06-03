# Phase R — Root shim repoint readiness / rollback plan

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `e2f3b796f4cc288675c42efcd63febcb2876b825` |
| Phase label | `Phase R — Root shim repoint readiness / rollback plan` |
| Branch | `refactor/wf1-sao-consolidation` |
| Nature | **Docs-only** — no code changes, no live CST, no root shim repoint |
| Root shim repointed? | **No** — still points to `workflows.rfgun_single_pass.run` |

---

## Current accepted evidence (through Phase Q2)

### Live CST evidence

| Capability | Phase | Evidence summary |
|------------|-------|-----------------|
| Role metrics (optimize/threshold/report_only) | B5 | Best F = -17534.24, 5/7 metrics computed |
| Runner-level CST cleanup | B5.1 | `attempted=True closed=True pid=<PID>` |
| Gate runtime rejection | B9 | q0=18630.8 vs threshold → `gate_reject`, Best F=1.0 |
| Cleanup hardening (orphan DE fix) | P3 | Original + replacement DE terminated; no manual `taskkill` |
| Multi-eval stability | Q1 | 5 evaluations, Best F -18002.12, no orphan DE |
| Repeated-run stability | Q2 | 3 consecutive runs (15 total evals), 18 close hangs handled, **zero orphan DE accumulation** |

### No-CST evidence

- **398+ no-CST tests** covering import integrity, retry taxonomy, retry runtime, evaluation database schema/dedup/warm-start, stage search, adaptive bounds, cleanup diagnostics
- All tests pass (399 as of Q2)

---

## Capabilities still not implemented

| Capability | Status | Impact on root shim repoint |
|------------|--------|----------------------------|
| Phase O/O1 retry runtime CST wiring | ❌ Not wired | Low — retry runtime is opt-in, disabled by default |
| Durable evaluation DB (J–L) | ❌ Not implemented | Low — schema/helpers exist but runtime not wired |
| Failure reuse | ❌ Not implemented | Low — future feature |
| DB warm-start / optimizer runtime injection | ❌ Not implemented | Low — checkpoint warm-start already works |
| Full production-scale campaign | ❌ Not attempted | Medium — root shim repoint is safe as long as default config is unchanged |

**Key insight**: None of the unimplemented capabilities are blockers for root shim repoint. The root shim delegates to a default `single_pass` configuration identical to the current `rfgun_single_pass` behaviour. All unimplemented features are opt-in, disabled by default, and only activate through explicit config changes.

---

## Root shim current state

`run_workflow_1.py` (3 lines of logic):

```python
from workflows.rfgun_single_pass.run import main

if __name__ == "__main__":
    main()
```

The CLI interface (`--config`, `--seed`, `--n-initial`, `--n-iter`) is identical between `workflows.rfgun_single_pass.run` and `workflows.rfgun_sao.run` — both use the same argument parser (both accept `--config`, `--seed`, `--n-iter`, `--n-initial`). The config loading path (`config.yaml`) and default config are also structurally identical.

---

## Repoint readiness criteria

All criteria below **must** be satisfied before root shim repoint is considered:

| # | Criterion | Current status | Met? |
|---|-----------|----------------|------|
| 1 | Phase Q2 accepted | ✅ Accepted at `e2f3b79` | ✅ |
| 2 | Cleanup stable across repeated runs | ✅ 3 runs, 15 evals, zero orphan DE | ✅ |
| 3 | No orphan DE after any live run since P3 fix | ✅ P3/Q1/Q2 = 5 runs total | ✅ |
| 4 | Default `config.yaml` unchanged | ✅ No modifications to default config | ✅ |
| 5 | `rfgun_single_pass` import tests pass | ✅ 12 tests pass | ✅ |
| 6 | `rfgun_sao` import tests pass | ✅ 230 tests pass | ✅ |
| 7 | Artifact policy documented and enforced | ✅ Q readiness plan specifies | ✅ |
| 8 | Rollback plan documented | ✅ This document | ✅ |
| 9 | Operator explicitly approves repoint | ❌ Pending — must be obtained before Phase S | ⏳ |

**All technical readiness criteria are met.** The remaining requirement is explicit operator approval, which belongs in Phase S.

---

## Proposed root shim repoint design (for future Phase S)

### Target change

In `run_workflow_1.py`:

```python
# Before:
from workflows.rfgun_single_pass.run import main

# After:
from workflows.rfgun_sao.run import main
```

### CLI compatibility

Both runners accept the same flags:

| Flag | `rfgun_single_pass.run` | `rfgun_sao.run` |
|------|------------------------|-----------------|
| `--config` | ✅ Default: `config.yaml` | ✅ Default: `config.yaml` (co-located) |
| `--seed` | ✅ Override optimization seed | ✅ Override optimization seed |
| `--n-initial` | ✅ Override n_initial_samples | ✅ Override n_initial_samples |
| `--n-iter` | ✅ Override n_iterations | ✅ Override n_iterations |

**No CLI incompatibility** — the shim can be replaced without changing user-facing behaviour.

### Behavioural equivalence (with default config)

| Aspect | `rfgun_single_pass` | `rfgun_sao` (single_pass mode) |
|--------|---------------------|-------------------------------|
| Evaluation mode | Single-pass SAO | Single-pass SAO |
| Parameters | From config | From config |
| Objectives | From config | From config |
| Checkpoint | `CheckpointManager` | `CheckpointManager` |
| Cleanup | `_cleanup_workflow_connection` | `_cleanup_workflow_connection` (+ P3 fix) |
| JSONL records | Disabled by default | Disabled by default |
| Retry | Legacy `EvaluationRetryHandler` | Legacy `EvaluationRetryHandler` |
| P3 cleanup hardening | Not present | ✅ Present |
| Phase O/O1 retry runtime | Not present | Not wired (opt-in only) |
| Default config | `config.yaml` | `config.yaml` (identical structure) |

The `rfgun_sao` runner **adds the P3 cleanup hardening** (`retry_handler.close_all()` during cleanup) which is a strict improvement. All existing single-pass behaviour is preserved.

### No default live CST surprise

The repoint does NOT change default behaviour:
- JSONL remains disabled
- Retry runtime remains disabled
- DB remains disabled
- Staged search remains disabled
- Adaptive bounds remain disabled
- Two-pass mode remains disabled (default is single_pass)

Users who run `python run_workflow_1.py` with an existing `config.yaml` will see identical results, with the added benefit of improved cleanup reliability.

---

## Rollback plan

If root shim repoint causes issues:

### Step 1: Immediate revert

```powershell
git revert <root-shim-repoint-commit>
```

### Step 2: Verify restored state

```powershell
# Confirm run_workflow_1.py targets single_pass
grep -n "rfgun_single_pass" run_workflow_1.py

# Run import tests
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short

# Run SAO import tests
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```

### Step 3: Manual cleanup check (if live CST was involved in the test run)

```powershell
# Check for orphan DE processes
Get-Process -Name "CST DESIGN ENVIRONMENT*" -ErrorAction SilentlyContinue
# If found, force-kill:
# taskkill /F /PID <orphan-pid>
```

### Step 4: Root cause investigation

- If repoint caused a regression, create a bugfix branch
- If the rollback was due to an environment issue (missing CST libs, config drift), document and fix in R1
- If the repoint was premature, update readiness criteria in this document

---

## Preflight checklist for future Phase S

Before any root shim repoint commit:

- [ ] Operator explicitly approves root shim repoint
- [ ] No orphan DE windows present before starting (only `cstd.exe`)
- [ ] `config.local.yaml` exists locally but is not staged/committed
- [ ] Default `config.yaml` is unchanged from accepted HEAD
- [ ] Accepted HEAD recorded: `e2f3b796f4cc288675c42efcd63febcb2876b825`
- [ ] `rfgun_single_pass` import tests pass (12)
- [ ] `rfgun_sao` import tests pass (230)
- [ ] Cleanup diagnostics tests pass (24)
- [ ] Retry runtime tests pass (83)
- [ ] Retry taxonomy tests pass (50)
- [ ] Artifact policy understood: no `.jsonl`, `.ckpt`, `.sqlite`, `.db`, logs, CST dirs, `config.local.yaml` committed
- [ ] Rollback plan is accessible (this document)

---

## Blockers that would prevent Phase S

| Blocking condition | Detection | Action |
|--------------------|-----------|--------|
| Orphan DE after live run | Post-run process check | Fix cleanup before repoint |
| Default config drift | `git diff config.yaml` | Revert config changes |
| Committed artifact found in history | `git status --short` review | Remove artifact from history |
| CLI incompatibility discovered | Review test output | Fix or document in R1 |
| Unclear rollback path | Review this document | Update before Phase S |

Currently, **no blockers** are present.

---

## Recommendation

**Proceed to Phase S (root shim repoint) when operator explicitly approves.**

All technical readiness criteria are satisfied:
- ✅ Cleanup stable across repeated runs (Q2: 3 runs, 15 evals, zero orphan DE)
- ✅ Default config unchanged
- ✅ Rollback plan documented
- ✅ Test suite passes (399 tests)
- ✅ CLI compatibility verified

The remaining step is operator approval for the actual repoint commit. A Phase R1 readiness hardening is only needed if this review identifies gaps not captured above.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Root shim repointed in Phase R | ❌ **Not repointed** — docs-only |
| Live CST run in Phase R | ❌ Not run (docs-only) |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Retry runtime CST wiring | ❌ Not wired |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |

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

---

## Commit message proposal

```
Phase R rfgun_sao root shim repoint readiness / rollback plan

- Docs-only readiness plan covering current evidence, repoint design,
  readiness criteria, rollback steps, preflight checklist, and blockers
- All technical readiness criteria satisfied: cleanup stable (Q2: 3 runs,
  zero orphan DE), default config unchanged, 399 tests pass
- Root shim NOT repointed; root shim import unchanged
- Recommendation: proceed to Phase S when operator explicitly approves

No code changes, no live CST, no durable DB, no retry runtime CST wiring,
no root shim repoint.
```
