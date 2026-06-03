# SR4 — Bounded live success reuse smoke

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `2d10c55eee4542478936789d64dd7fe0b9d573c2` |
| Phase label | `SR4 — Bounded live success reuse smoke` |
| Branch | `feature/wf1-db-success-reuse` |
| Live CST explicitly allowed | **Yes** — operator approved |
| Runtime code changed | **No** — no modifications needed for live smoke |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `reports/restructure_plan/sr4_db_success_reuse_live_smoke_report.md` | **Added** | This report |

No runtime code changed. No source file modified.

---

## Live smoke design

**Two-step process** with a fresh outside-repo SQLite DB:

1. **Seed run**: CST evaluation (`success_reuse.enabled=false`) → writes one SUCCESS row.
2. **Reuse run**: Same config but `success_reuse.enabled=true` → reuses the seed row.

### DB path

`D:/Results/workflow1/evaluation_sr4_smoke.db` — outside repo, not committed.

---

## Local config summary

### Seed run config

```yaml
optimization:
  retry:
    enabled: false
retry_runtime:
  enabled: false
evaluation_database:
  enabled: true
  path: D:/Results/workflow1/evaluation_sr4_smoke.db
  create_if_missing: true
success_reuse:
  enabled: false
```

### Reuse run config

```yaml
# Same as seed, except:
success_reuse:
  enabled: true
  require_objective_values: true
```

### Command (both runs)

```powershell
python run_workflow_1.py --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

---

## Seed run results

### Evaluation

```
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best F: [-15392.38103863]
CST cleanup: attempted=True closed=True pid=32368
```

### DB row (seed)

| Field | Value |
|-------|-------|
| `id` | 1 |
| `source` | `retry_runtime_cst` |
| `status` | `success` |
| `parameter_key` | `c325dffff9315d57` |
| `param_values` | `[10.78, 4.04, 3.28, 2.44, 0.26, 1.03, ...]` |
| `run_id` | `70f6f4c4` |
| `has_obj` | ✅ Yes |

### Post-seed cleanup

| Check | Result |
|-------|--------|
| CST Design Environment remaining? | ❌ None |
| Only `cstd.exe` licensing service? | ✅ Yes |
| Manual `taskkill` required? | ❌ No |

---

## Reuse run results

### Evaluation

```
[Workflow 1] Planned: 1 initial + 0 BO = 1
Done. Best F: [8.18734438e+11]
CST cleanup: attempted=True closed=True pid=48836
```

**No "You are working in interactive mode"** — the CST solve was skipped for the reused candidate. The CST connection was opened during workflow construction (required by the current builder) but no CST evaluation/solve was executed.

### Reuse hit evidence (from log)

```
INFO  Success reuse: found eligible row (id=1, run_id=70f6f4c4, created_at=2026-06-03 12:34:28, key=c325dfff)
INFO  Success reuse: hit (key=c325dfff, row_id=1, run_id=70f6f4c4)
DEBUG Evaluation DB: written (id=2, status=success, key=c325dfff)
DEBUG Checkpoint saved (1 records)
```

### DB row comparison

| Field | Seed (id=1) | Reuse (id=2) | Match? |
|-------|------------|--------------|--------|
| `source` | `retry_runtime_cst` | `db_success_reuse` | Different (expected) |
| `status` | `success` | `success` | ✅ |
| `parameter_key` | `c325dffff9315d57` | `c325dffff9315d57` | ✅ **Exact match** |
| `param_values` | Same 13-parameter vector | Same 13-parameter vector | ✅ |
| `run_id` | `70f6f4c4` | `06cc1333` | Different (expected) |

### Post-reuse cleanup

| Check | Result |
|-------|--------|
| CST Design Environment remaining? | ❌ None |
| Only `cstd.exe` licensing service? | ✅ Yes |
| Manual `taskkill` required? | ❌ No |

---

## Best F comparison

| Run | Best F | Notes |
|-----|--------|-------|
| Seed | **-15392.38** | Real CST evaluation with full penalty computation |
| Reuse | **8.187e+11** | Reconstructed from DB row using objective_values → penalty_values fallback |

The Best F differs because the reuse path does not have access to the metric specs (`MetricRole`, objective `mode`, `sigma`, `threshold`) needed to recompute the actual penalty values. The reconstruction uses `objective_values` as `penalty_values` placeholders, which produces a raw metric value (11.424 GHz) instead of the computed tolerance penalty.

**This is a known limitation documented in the SR1 design**: penalty recomputation requires `allow_raw_recompute=true` and a safe recompute helper. The reuse **did fire correctly** and the CST solve was skipped, but the penalty values are placeholders. This is acceptable for SR4 — the purpose was to validate the lookup/skip/provenance path, not the penalty reconstruction.

---

## What was live-validated

| Capability | Validated? | Evidence |
|------------|-----------|----------|
| DB SUCCESS row written by real CST | ✅ | Seed row id=1, source=retry_runtime_cst |
| Same parameter_key reused on second run | ✅ | Both rows have key `c325dffff9315d57` |
| Reuse lookup hit logged | ✅ | `Success reuse: found eligible row` and `hit` |
| CST solve skipped on reuse run | ✅ | No "You are working in interactive mode" |
| Reuse row source=`db_success_reuse` | ✅ | Row id=2 has reuse provenance |
| Checkpoint called once per run | ✅ | 1 checkpoint per run |
| DB closed in cleanup | ✅ | `Evaluation DB closed` |
| No orphan DE | ✅ | Only `cstd.exe` after both runs |
| No manual cleanup | ✅ | Not required |

## What was NOT validated

| Capability | Status | Reason |
|------------|--------|--------|
| Full penalty reconstruction from DB | ❌ | Requires `allow_raw_recompute` and metric specs access |
| Warm-start | ❌ | Separate track |
| Failure reuse | ❌ | Separate track |
| probably-infeasible skip | ❌ | Rejected at runtime |
| Production campaign | ❌ | Bounded single-eval only |
| Multi-point dedup | ❌ | Single parameter point only |
| Concurrent DB writers | ❌ | Single-writer assumption |
| Schema migrations beyond v1 | ❌ | Exact match required |

---

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short -v
→ 35 passed

pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse_workflow.py --tb=short -v
→ 10 passed

pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short → 35 passed
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short → 12 passed

Total: 405 passed (all existing tests), 1 pre-existing warning.
```

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/workflow.py` | **Not modified** |
| `workflows/rfgun_sao/evaluation_success_reuse.py` | **Not modified** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Modified for smoke, restored | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` | **Not committed** |
| `*.sqlite` / `*.db` | `D:/Results/workflow1/evaluation_sr4_smoke.db` | **Not committed** (outside repo) |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` | **Not committed** |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` | **Not committed** |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
SR4 rfgun_sao bounded live success reuse smoke

- Two-step live smoke with fresh outside-repo SQLite DB:
  1. Seed run: real CST evaluation, writes SUCCESS row (id=1)
  2. Reuse run: success_reuse enabled, reuses same parameter_key
     (id=2, key match confirmed)
- Reuse lookup hit logged; CST solve skipped (no "interactive mode" msg)
- DB provenance: source=db_success_reuse, reused_from_db=true
- Best F differs due to placeholder penalty (objective_values fallback)
  — reconstruction without metric specs is known limitation
- No orphan DE, no manual cleanup, no committed artifacts

No runtime code changed, no default config change.
```
