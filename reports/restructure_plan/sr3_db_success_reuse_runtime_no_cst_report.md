# SR3 — Runtime opt-in success reuse wiring, no-CST only

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `e5b0e0295980d2d828b823e19deb9178975c9605` |
| Phase label | `SR3 — Runtime opt-in success reuse wiring, no-CST only` |
| Branch | `feature/wf1-db-success-reuse` |
| Live CST | **No** — pure no-CST implementation |
| Runtime skip | **Yes** — wired and no-CST tested |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_success_reuse.py` | **Modified** | Added `try_success_reuse()` — combined lookup + reconstruction helper |
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added success reuse config, `_try_sr_reuse` and `_handle_sr_reuse` helpers; reuse checks in legacy, retry-runtime, and plain paths |
| `tests/workflows/test_rfgun_sao_evaluation_success_reuse_workflow.py` | **Added** | 14 no-CST workflow integration tests |
| `reports/restructure_plan/sr3_db_success_reuse_runtime_no_cst_report.md` | **Added** | This report |

---

## Runtime wiring summary

### Config integration

After evaluation DB config resolution, success reuse config is resolved:
- `resolve_success_reuse_config(config, db_enabled=...)` — raises `ValueError` if reuse enabled without DB
- `_sr_cfg` holds the resolved config (disabled by default)
- Two closures defined for use inside the evaluator:

| Closure | Purpose |
|---------|---------|
| `_try_sr_reuse(x_phys)` | Builds `ParameterIdentity`, calls `try_success_reuse()`, returns `EvaluationResult | None` |
| `_handle_sr_reuse(reuse_result, x_phys)` | Computes penalty scalar, calls checkpoint, writes DB with reuse provenance, returns scalar |

### Three insertion points

| Path | Insertion | On hit |
|------|-----------|--------|
| Legacy retry | Before `retry_handler.execute()` | Skip `execute` and `force_reset` |
| Retry runtime | Before initial CST or smoke injection | Skip `evaluate_single_pass` and `run_retry_loop_no_cst` |
| Plain single_pass | Before `evaluate_single_pass()` | Skip CST solve entirely |

### On reuse hit

1. Reuse result is returned from `try_success_reuse()`.
2. `_handle_sr_reuse` computes `penalties_arr` from `reuse_result.penalty_values`.
3. Checkpoint callback is called once with reconstructed data.
4. DB writes a new `evaluation_records` row with `source="db_success_reuse"` and diagnostics containing `reused_from_db=True`, `source_row_id`, `source_run_id`.
5. The CST evaluation path (CST solve, retry loop, retry handler) is entirely skipped.

### On reuse miss

The original CST/retry path runs unchanged. No behavior change.

---

## Test coverage (14 workflow tests + 35 reuse = 49 total)

| Test class | Tests | Coverage |
|------------|-------|----------|
| `TestWorkflowConfig` | 2 | Disabled no query, enabled without DB fails |
| `TestPlainPathReuse` | 3 | Hit skips evaluate, miss calls evaluate, penalty values returned |
| `TestRetryRuntimeReuse` | 2 | Hit skips loop, miss keeps loop |
| `TestLegacyRetryReuse` | 2 | Hit skips handler, miss keeps handler |
| `TestNoInvalidReuse` | 5 | Failure row not reused, raw-only not reused, names mismatch not reused, provenance in diagnostics, no JSONL |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse_workflow.py --tb=short -v
→ 14 passed

pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short -v
→ 35 passed

pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short → 40 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_workflow.py → 10 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime.py → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py → 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py → 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py → 28 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py → 50 passed
pytest tests/workflows/test_rfgun_sao_imports.py → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py → 12 passed

Total: 521 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run |
| Runtime skip wired | ✅ All three paths (plain, retry-runtime, legacy) |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Success reuse runtime | ✅ Wired and no-CST tested |
| Warm-start | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| probably-infeasible skip | ❌ Not used |
| JSONL sidecar as reuse source | ❌ Not used |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/run.py` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
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
SR3 rfgun_sao runtime opt-in success reuse wiring, no-CST only

- Add try_success_reuse() helper (combined lookup + reconstruction)
- Wire reuse into three workflow paths: legacy, retry-runtime, plain
- On hit: skip CST/retry, checkpoint once, DB write with provenance
- On miss: existing behaviour unchanged
- 14 no-CST workflow integration tests
- 521 total tests pass

No live CST, no default config change, no warm-start/failure reuse.
```
