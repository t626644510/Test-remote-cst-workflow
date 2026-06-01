# Phase A12.1 — Two-pass runtime skeleton polish

## Task

Quality fix for A12's injectable two-pass runtime evaluator skeleton.
No live CST changes, no behaviour change in production code paths.

Fixes:
1. **`_extract_raw_array` helper** — raw metric extraction now correctly
   falls back `objective_values` → `raw_metrics` → `np.nan`, with
   non-finite guarding.
2. **Failed measurement path** — now preserves available raw metrics
   (via `_extract_raw_array`) instead of unconditional `np.nan` full
   array, so checkpoint receives whatever partial data exists.
3. **S11 gate reject test** — runtime-level test confirms S11DepthGate
   rejection prevents measurement and reports the correct reason.

## Summary

Only `two_pass.py` and the test file were modified. `workflow.py` and
`README.md` are untouched.

### two_pass.py

- Added `_extract_raw_array(result, metric_names) → np.ndarray` helper
  that tries `objective_values` first, falls back to `raw_metrics`, then
  `np.nan`. Non-finite or unconvertible values become `np.nan`.
- Both the success path and the failed-measurement path now use this
  helper instead of inline construction. The failed path previously
  unconditionally filled `raw_arr` with `np.nan`; now it preserves
  whatever partial raw data the measurement returned.

### test file

- Extended `_FakeMeasurementRunner` with a sentinel-based
  `objective_values` parameter (backward compatible: default = same
  as `raw_values`) and an explicit `error` string parameter.
- Added 3 new tests in section I (total: 58 → 61).

| Test | What it verifies |
|------|-----------------|
| `test_two_pass_runtime_raw_array_falls_back_to_raw_metrics` | `objective_values=None` → `raw_metrics` is used for checkpoint `raw_arr` |
| `test_two_pass_runtime_failed_measurement_preserves_raw_metrics_for_checkpoint` | `SOLVER_FAILED` → penalty `1.0`, but `raw_arr` still contains `raw_metrics` data; `solver_ok=False`, error propagated |
| `test_two_pass_runtime_s11_gate_rejects_before_measurement` | `S11DepthGate` rejection → `val=1.0`, `meas_runner.call_count=0`, `solver_ok=False`, reason contains `"s11_depth_gate_reject"` |

## Files changed

| File | Action |
|---|---|
| `workflows/rfgun_sao/two_pass.py` | Added `_extract_raw_array` helper; both measurement paths use it |
| `tests/workflows/test_rfgun_sao_imports.py` | Extended `_FakeMeasurementRunner`; added 3 new tests |
| `reports/restructure_plan/phase_A12_1_two_pass_runtime_polish.md` | Created (this file) |

## Behavioural changes

**None for production behaviour.**
- `single_pass` path: **unchanged**.
- Default `two_pass` placeholder path: **unchanged** (calibration failure
  → reject → penalty 1.0, no measurement call, no CST connection).
- The `_extract_raw_array` helper only affects the *measurement accepted*
  path, which never fires with default placeholder runners.

**Improved robustness in non-default paths:**
- When a custom measurement runner returns `EvaluationResult` with
  `objective_values=None` but `raw_metrics` populated, checkpoint now
  receives the raw data instead of `np.nan`.
- Non-finite values are sanitized to `np.nan` regardless of source.

**Protected areas confirmed unchanged:**

| Area | Status |
|---|---|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `config.local.yaml` | **Not modified / not committed** |

**two_pass placeholder invariant:**
- `workflow._conn` remains `None`
- Default evaluator returns penalty `1.0`
- No CST connection created
- Still not physically meaningful

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
# … 61/61 passed (58 existing + 3 new)

$ git diff --name-only
workflows/rfgun_sao/two_pass.py
tests/workflows/test_rfgun_sao_imports.py
reports/restructure_plan/phase_A12_1_two_pass_runtime_polish.md
```

## Notes / caveats

- A12.1 only improves no-CST runtime skeleton quality.
- Real CST calibration/measurement remains **A13 or later**.
- `make_two_pass_placeholder_evaluator` is unchanged.
- `workflow.py` and `README.md` were not modified.
- `_FakeMeasurementRunner` now supports `objective_values=None` and a
  configurable `error` string, extending its test expressiveness without
  breaking existing call sites.

## Commits

```
89c97eb
```
