# WS3 -- optimizer warm-start runtime wiring, no-CST

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `bc85a38529d11d0307b7f0e009677ae8f692f868` |
| Phase label | `WS3 -- optimizer warm-start runtime wiring / no-CST` |
| Branch | `feature/wf1-db-warm-start` |
| Live CST | **No** -- pure no-CST implementation |
| Optimizer wiring | **Implemented** -- DB priors merged into optimizer warm-start |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_database_storage.py` | **Modified** | Added `get_all_records()` method returning all rows, newest first |
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added WS3 warm-start config resolution, `get_all_records()` + `load_warm_start_priors()` call, stored report on `workflow._db_warm_start_report` |
| `workflows/rfgun_sao/run.py` | **Modified** | After checkpoint warm-start loading, merges DB warm-start priors into `prior_data` (X, F arrays) |
| `tests/workflows/test_rfgun_sao_db_warm_start_ws3.py` | **Added** | 16 no-CST WS3 optimizer wiring tests |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | WS3 status |
| `reports/restructure_plan/wf1_db_warm_start_ws3_optimizer_wiring.md` | **Added** | This report |

---

## Runtime wiring summary

### Config semantics (unchanged from WS2)

Warm-start requires all three:
1. `evaluation_database.enabled: true` (with outside-repo path)
2. `evaluation_database.warm_start.enabled: true`

Cross-implied enable remains prevented:
- DB enabled alone does NOT enable warm-start
- `success_reuse.enabled` alone does NOT enable warm-start
- Warm-start enabled does NOT enable success reuse

### Data flow

```
build_workflow_1(config, ...)
  |
  +-- Resolve evaluation_database config (DDB)
  +-- Open SQLiteEvaluationDatabase if enabled
  +-- Resolve success_reuse config (SR)
  +-- Resolve warm_start config (WS3)
  |     if ws_cfg.enabled and _evaluation_db is not None:
  |       rows = _evaluation_db.get_all_records()
  |       ws_report = load_warm_start_priors(rows, ws_cfg, ...)
  |       workflow._db_warm_start_report = ws_report
  +-- Build optimizer, evaluator, workflow container
  +-- Return (workflow, optimizer, evaluator)

run_workflow_1.py / run.py main()
  |
  +-- ckpt.load() -> warm_xy (checkpoint priors)
  +-- workflow._db_warm_start_report -> DB warm-start priors
  +-- Merge: convert DbWarmStartPrior -> (X, F) arrays
  |     ws_x = [[p.v1, p.v2, ...], ...]
  |     ws_f = [p.scalar, ...]
  +-- Merge with checkpoint priors (vstack, concatenate)
  +-- prior_data = (merged_X, merged_F)
  +-- opt.optimize(evaluator=ev, prior_data=prior_data)
```

### DB row source

- `get_all_records()` queries `SELECT * FROM evaluation_records ORDER BY created_at DESC`
- All rows are returned as dicts with JSON columns decoded
- Rows are passed to WS2's `load_warm_start_priors()` which applies eligibility checks
- Only compatible SUCCESS final authoritative rows become priors
- Failure, gate, diagnostic, malformed rows are rejected with specific reasons
- JSONL sidecar is never read

### Optimizer injection

- DB priors are converted to `(X, F)` format matching the optimizer's `prior_data` parameter
- `X` is a 2D array of parameter vectors, `F` is a 1D array of objective scalars
- Checkpoint priors are loaded first, then DB priors are appended
- DB priors do NOT consume CST solve budget
- DB priors do NOT call evaluator or retry runtime

### Warm-start vs success reuse independence

| Config combination | Behavior |
|-------------------|----------|
| WS enabled, SR disabled | Optimizer receives DB priors. Future evaluation proposals run CST normally (no skip). |
| SR enabled, WS disabled | Optimizer does NOT receive DB priors. Future exact DB hits skip CST. |
| Both enabled | Optimizer receives DB priors AND future exact DB hits skip CST. No double-count. |

---

## Test coverage (16 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestWS3Config` | 5 | Default disabled, DB alone, SR alone, WS without DB raises, WS needs explicit enable |
| `TestPriorLoading` | 6 | Loads SUCCESS rows, converts to X/F arrays, no evaluator call, counts in report, rejection counts, duplicate counts |
| `TestWSandSRIndependence` | 2 | WS without SR does not skip eval, SR without WS does not load priors |
| `TestMalformedRows` | 1 | Malformed param_values rejected |
| `TestSafety` | 2 | No JSONL, no CST imports |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_db_warm_start_ws3.py --tb=short -v
-- 16 passed

pytest tests/workflows/test_rfgun_sao_db_warm_start_ws2.py --tb=short
-- 45 passed

# Full regression (552 existing)
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short -- 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short -- 12 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short -- 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short -- 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py --tb=short -- 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py --tb=short -- 28 passed
pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short -- 35 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short -- 40 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_workflow.py --tb=short -- 10 passed

Total: 568 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | **No** |
| Default config changed | **Not changed** |
| `config.local.yaml` committed | **Not committed** |
| Generated artifacts committed | **Not committed** |
| DB warm-start prior loader | **Wired into optimizer initialization** |
| DB priors consume CST solve budget | **No** (priors are observations, not evaluations) |
| DB priors call evaluator | **No** |
| DB priors invoke retry runtime | **No** |
| JSONL sidecar as warm-start source | **Not used** |
| Failure rows as priors | **Rejected** |
| probably-infeasible skip | **Not used** |
| Warm-start implies success reuse | **No** (independent configs) |
| Success reuse implies warm-start | **No** (independent configs) |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | Temporary test files | **Not committed** |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
feat(wf1): wire DB warm-start optimizer priors WS3

- Add get_all_records() to SQLiteEvaluationDatabase
- Resolve warm-start config in workflow.py; load eligible rows from DB
  via WS2 load_warm_start_priors(); store report on workflow
- Merge DB priors with checkpoint priors in run.py before optimizer call
  (convert DbWarmStartPrior -> (X, F) arrays; vstack if checkpoint exists)
- DB priors do not call evaluator or consume CST solve budget
- DB priors do not enable success reuse (independent semantics)
- 16 no-CST tests: config, prior loading, X/F conversion, rejection, safety
- 568 total tests pass

No live CST, no default config change, no failure reuse.
```
