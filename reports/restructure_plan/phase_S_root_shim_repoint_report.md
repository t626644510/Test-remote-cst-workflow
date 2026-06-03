# Phase S — Root shim repoint

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `98f8b87487cd6f934ef8c813d0ef3b1383452c7f` |
| Phase label | `Phase S — Root shim repoint, explicitly approved only` |
| Branch | `refactor/wf1-sao-consolidation` |
| Operator explicitly approved root shim repoint | **Yes** — confirmed in session |
| Root shim repointed | **Yes** — `run_workflow_1.py` now imports `workflows.rfgun_sao.run` |
| Live CST run | **No** — not separately approved; not required for import-only change |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `run_workflow_1.py` | **Modified** | Import changed from `workflows.rfgun_single_pass.run` → `workflows.rfgun_sao.run` |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | Phase R accepted; Phase S row added |
| `reports/restructure_plan/phase_S_root_shim_repoint_report.md` | **Added** | This report |

---

## Source change

**Before:**
```python
from workflows.rfgun_single_pass.run import main
```

**After:**
```python
from workflows.rfgun_sao.run import main
```

Docstring updated to reflect the new target module. No other changes to `run_workflow_1.py`.

---

## CLI compatibility validation

```
$ python run_workflow_1.py --help
usage: run_workflow_1.py [-h] [--config CONFIG] [--seed SEED]
                         [--n-iter N_ITER] [--n-initial N_INITIAL]

Workflow 1 SAO optimisation

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG       Path to Workflow 1 YAML config (default:
                        .../workflows/rfgun_sao/config.yaml)
  --seed SEED           Override optimizer seed from config
  --n-iter N_ITER       Override n_iterations from config
  --n-initial N_INITIAL Override n_initial_samples from config
```

All 4 flags preserved (`--config`, `--seed`, `--n-iter`, `--n-initial`). Default config path correctly points to `workflows/rfgun_sao/config.yaml`.

---

## Validation results

| Check | Command | Result |
|-------|---------|--------|
| Static import | `Select-String "rfgun_single_pass"` | ✅ Not found |
| Import target | `Select-String "^from workflows"` | ✅ `from workflows.rfgun_sao.run import main` |
| CLI help | `python run_workflow_1.py --help` | ✅ All flags preserved |
| Compile | `python -m compileall run_workflow_1.py workflows/rfgun_sao` | ✅ OK |
| rfgun_sao imports | `pytest test_rfgun_sao_imports.py` | ✅ 230 passed |
| rfgun_single_pass imports | `pytest test_rfgun_single_pass_imports.py` | ✅ 12 passed |
| Cleanup diagnostics | `pytest test_rfgun_sao_cst_cleanup_diagnostics.py` | ✅ 24 passed |
| Retry runtime | `pytest test_rfgun_sao_retry_runtime.py` | ✅ 83 passed |
| Retry taxonomy | `pytest test_rfgun_sao_retry_taxonomy.py` | ✅ 50 passed |
| **Total** | | **399 passed** |

---

## Live CST

No live CST was run in Phase S. The operator approved the import repoint but did not separately approve live CST validation after the repoint.

The `rfgun_sao` runner has independent live evidence from earlier phases:
- P3: cleanup hardening (1 run, single-eval, no orphan DE) ✅
- Q1: multi-eval stability (5 evals, Best F -18002.12, no orphan DE) ✅
- Q2: repeated-run stability (3 runs, 15 evals, zero orphan DE across full sequence) ✅

---

## Rollback plan

If the repoint causes issues, revert with:

```powershell
git revert <commit-SHA>
# Verify:
grep -n "rfgun_single_pass" run_workflow_1.py
# Should show: from workflows.rfgun_single_pass.run import main

# Run tests:
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```

No rollback was performed — the repoint passed all validation.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Operator explicitly approved root shim repoint | ✅ Yes |
| Root shim repointed | ✅ Yes — `run_workflow_1.py` → `workflows.rfgun_sao.run` |
| Live CST run in Phase S | ❌ Not run |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Retry runtime CST wiring | ❌ Not wired |
| Optimizer/runtime warm-start injection | ❌ Not implemented |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/retry_runtime.py` | **Not modified** |
| `workflows/rfgun_sao/cst_cleanup_diagnostics.py` | **Not modified** |
| Root shim repointed | ✅ Done — minimal import-only change |
| `workflows/rfgun_single_pass/run.py` | **Untouched** — still exists and importable |

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

**To be confirmed by reviewer.**

---

## Commit message proposal

```
Phase S rfgun_sao root shim repoint

- run_workflow_1.py: import changed from rfgun_single_pass.run to rfgun_sao.run
- CLI compatibility verified (--config, --seed, --n-iter, --n-initial preserved)
- 399 tests pass; all rfgun_single_pass import tests still pass
- Rollback plan documented: git revert <SHA>
- No live CST, no default config change, no durable DB, no retry runtime wiring

Root shim repointed with explicit operator approval.
```
