# Execution Report

## Phase
P03-diagnostics-and-stage-validation

## Branch
`phase/S01-P03-diagnostics-and-stage-validation`

## Summary
Added comprehensive diagnostics to `WakeFitResult` for distinguishing fixed known modes from fitted unknown modes. New fields (`unknown_mode_wake`, `residual_wake`, `diagnostics`) provide test-accessible separation of wake contributions and quality metrics. The `objective_value` in the zero-unknown-mode path now reports the actual residual sum-of-squares instead of `0.0`. The `LongitudinalImpedanceObjective` already exposes `last_fit_result` which carries all new fields downstream. Three new tests verify diagnostics semantics, imperfect known-only residual reporting, and objective-level accessibility.

## Files Changed

### `workflows/rfgun_hom_antenna/pso_wake_fit.py`
1. **`WakeFitResult`**: Added three new fields:
   - `unknown_mode_wake: np.ndarray | None = None` — fitted unknown-mode wake contribution (None when no known modes, for backward compat)
   - `residual_wake: np.ndarray | None = None` — target minus total fitted wake
   - `diagnostics: dict[str, Any] = field(default_factory=dict)` — structured quality metrics

2. **`fit_wake_with_pso()`**: 
   - Computes `unknown_mode_wake`, `residual_wake`, and populates `diagnostics` after the normal/fitted-mode construction.
   - Diagnostics include: `known_mode_count`, `fitted_mode_count`, `known_mode_labels`, `target_wake_rms`, `known_mode_wake_rms`, `unknown_mode_wake_rms`, `residual_wake_rms`, `normalized_error`, `wake_corr`, `known_mode_filtered_peak_count`.
   - `objective_value` is now always computed as the residual sum-of-squares (SSE) from the common section, replacing the previous `0.0` placeholder in the zero-unknown-mode path.

### `workflows/rfgun_hom_antenna/wakefield_objective.py`
No changes needed. `LongitudinalImpedanceObjective` already has `last_fit_result: WakeFitResult | None` which carries all new fields to downstream consumers.

### `tests/workflows/test_workflow2_pso_wake_fit.py`
Added 3 new tests (36 total).

## Diagnostics Added

Each `WakeFitResult` now includes a `diagnostics` dict with:

| Key | Type | Description |
|-----|------|-------------|
| `known_mode_count` | int | Number of configured known modes |
| `fitted_mode_count` | int | Number of fitted unknown modes (`len(result.modes)`) |
| `known_mode_labels` | list[str] | Labels of all known modes |
| `target_wake_rms` | float | RMS of the target wake curve |
| `known_mode_wake_rms` | float | RMS of the known-mode wake (0 if no known modes) |
| `unknown_mode_wake_rms` | float | RMS of the unknown fitted wake |
| `residual_wake_rms` | float | RMS of `target - total_fit` |
| `normalized_error` | float | Existing normalized error |
| `wake_corr` | float | Existing wake correlation |
| `known_mode_filtered_peak_count` | int | Number of peaks that were filtered out because they matched a known mode |

## Objective-Level Accessibility

`LongitudinalImpedanceObjective.last_fit_result` was already wired in P02 and now carries the enhanced `WakeFitResult`. No new objective fields were needed.

## Tests Added Or Updated

### New tests (3):

1. **`test_known_mode_result_diagnostics_separate_known_unknown_residual`**: Fundamental (known) + HOM (fitted) synthetic wake. Asserts:
   - `known_modes` length 1, `modes` length 1
   - `known_mode_wake` and `unknown_mode_wake` both non-zero with correct shape
   - `wake_fit == known_mode_wake + unknown_mode_wake`
   - `residual_wake == target - total_fit`
   - All diagnostics fields populated correctly; near-zero residual for exact match.

2. **`test_known_only_objective_value_reports_residual_sse`**: Known-only fit with intentionally mismatched Q. Asserts:
   - Zero fitted modes (optimizer never called via `_raises_optimizer`)
   - Non-zero residual (imperfect match)
   - `objective_value == sum(residual_wake ** 2)` (SSE, not 0.0)
   - `normalized_error > 0`

3. **`test_longitudinal_objective_exposes_pso_wake_known_mode_diagnostics`**: monkeypatches `fit_wake_with_pso` in `wakefield_objective` namespace, calls `LongitudinalImpedanceObjective.raw_value()` with configured known modes. Asserts:
   - `obj.last_fit_result.known_modes` non-empty with correct label
   - `obj.last_fit_result.unknown_mode_wake` and `residual_wake` are present
   - `diagnostics` contains known_mode_count and known_mode_labels

## Test Commands

```bash
py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v
```

(pytest via `py` launcher, Python 3.9.13, Windows)

## Test Results

```
collected 36 items

... (33 existing tests pass) ...
test_known_mode_result_diagnostics_separate_known_unknown_residual .... PASSED
test_known_only_objective_value_reports_residual_sse ............... PASSED
test_longitudinal_objective_exposes_pso_wake_known_mode_diagnostics . PASSED
```

**36 passed in 0.60s**

## Known Limitations

- The `diagnostics` dict is a flat dict and could be extended with more statistical or frequency-domain metrics in future phases if needed.
- Transverse diagnostics follow the same structural pattern (since `WakeFitResult` is direction-agnostic) but are not explicitly tested for transverse use cases.
- The `objective_value` in the normal PSO path is now computed from the common section (SSE) rather than returned directly from the optimizer. For well-converged fits these are equivalent; for early-termination or constrained optimizers there may be sub-percent differences.

## Scope Compliance

| Requirement | Status |
|---|---|
| Works on `phase/*` branch | ✅ `phase/S01-P03-diagnostics-and-stage-validation` |
| Did not push main | ✅ |
| Did not merge | ✅ |
| Did not modify `stage_plan.md` | ✅ |
| Did not implement Direction 2 | ✅ |
| Did not modify CST API | ✅ (no `src/cst_optimization/` changes) |
| Did not change scalarization semantics | ✅ |
| Only modified allowed scope files | ✅ (`pso_wake_fit.py`, test file, execution report) |
| `wakefield_objective.py` unchanged | ✅ (not needed) |

## Follow-up Notes For Web Phase Reviewer

P03 is ready for review. The diagnostics added are:
- **`unknown_mode_wake`**: the pure PSO-fitted wake (no known modes), useful for inspecting what the PSO actually produced.
- **`residual_wake`**: what the optimizer minimized, useful for understanding fit quality across the time domain.
- **`diagnostics` dict**: structured metrics for programmatic testing and potential reporting.

The zero-unknown-mode `objective_value` fix (from `0.0` to actual SSE) addresses the P01 review note. The existing `last_fit_result` on `LongitudinalImpedanceObjective` carries all new fields without any objective-layer changes.

The branch has been pushed to remote for inspection.
