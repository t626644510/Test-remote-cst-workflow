# Execution Report

## Phase
P01-fixed-mode-core

## Branch
`phase/S01-P01-fixed-mode-core`

## Summary
Implemented known/fixed-mode support in the Workflow 2 PSO wake-potential fitting core. Added a `KnownMode` dataclass, `compute_known_mode_wake` function, and integrated fixed-mode wake evaluation into `fit_wake_with_pso`. PSO now optimises only unknown modes while known-mode contributions are included in the total wake fit and reconstructed impedance. Backward compatibility is fully preserved: when no known modes are configured, behaviour is identical to the baseline.

## Files Changed

### `workflows/rfgun_hom_antenna/pso_wake_fit.py`
1. **`KnownMode` dataclass** (new, after `ModeFit`): Frozen dataclass with fields `label`, `frequency_hz`, `q`, `r_over_q_ohm`, and `include_in_reconstructed_impedance` (default True). Documented with the R/Q-to-amplitude conversion formula.

2. **`compute_known_mode_wake()` function** (new, after `wake_from_parameters`): Converts known mode R/Q to wake amplitude using the same form-factor convention as the PSO fit path (`A = R/Q * form_factor * 2*pi*f / wake_charge_scale`), then evaluates the resonator wake model on the time grid. Returns zero array for empty known_modes.

3. **`_wake_objective_with_known()` function** (new, after `wake_objective`): Modified sum-of-squares objective that evaluates `known_wake + fitted_unknown_wake` against the target wake.

4. **`WakeFitInput`**: Added `known_modes: tuple[KnownMode, ...] = ()` field.

5. **`WakeFitResult`**: Added `known_modes: tuple[KnownMode, ...] = ()` and `known_mode_wake: np.ndarray | None = None` fields.

6. **`fit_wake_with_pso()`**: Modified to:
   - Compute known-mode wake when `known_modes` is provided.
   - Use `_wake_objective_with_known` so PSO only optimises unknown modes.
   - Report `wake_fit` as the total (known + unknown) fitted wake.
   - Include known-mode contributions in reconstructed impedance when `include_in_reconstructed_impedance` is True.
   - Store known-mode metadata and wake in the result.
   - Preserve all existing behaviour when `known_modes` is empty.

### `tests/workflows/test_workflow2_pso_wake_fit.py`
Updated imports to include `C_LIGHT_M_PER_S`, `KnownMode`, `compute_known_mode_wake`, `_gaussian_form_factor`. Added 6 new tests (see below).

## Tests Added Or Updated

### New tests (6):

1. **`test_known_mode_compute_wake_matches_direct_evaluation`**: Verifies `compute_known_mode_wake` produces identical results to `wake_from_parameters` with manual R/Q-to-amplitude conversion.

2. **`test_known_mode_empty_known_modes_produces_zero_wake`**: Empty `known_modes` tuple produces zero known-mode wake with correct shape.

3. **`test_known_mode_metadata_in_fit_result`**: `fit_wake_with_pso` result contains known-mode metadata (`label`, `frequency_hz`, non-zero `known_mode_wake`).

4. **`test_known_mode_target_fully_explained_by_known_wake`**: Synthetic one-known-mode wake — when the known mode exactly matches the target and fitted amplitude is forced to zero, the total wake equals the known-mode wake with near-zero normalized error.

5. **`test_known_mode_plus_hom_exact_optimizer`**: Synthetic fundamental (R/Q-based) + HOM wake — with fundamental as known mode, exact HOM parameters in the PSO output yield near-zero residual, verifying the known+unknown decomposition works.

6. **`test_known_mode_without_known_falls_back_to_existing_behavior`**: When `known_modes` is not provided, the result has `known_modes == ()` and `known_mode_wake is None`, and the fit behaves identically to the baseline test.

### Existing tests (12, unchanged):
All 12 existing tests continue to pass with no modifications.

## Test Commands

```bash
py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v
```

(pytest via `py` launcher, Python 3.9.13, Windows)

## Test Results

```
collected 18 items

test_detect_impedance_peaks_uses_sampled_grid_only ............. PASSED
test_fit_wake_with_pso_reconstructs_synthetic_mode_with_fixed_optimizer PASSED
test_fit_window_config_uses_tail_only_with_units .............. PASSED
test_fit_peak_range_is_independent_from_scalarization_defaults  PASSED
test_estimate_sigma_z_from_charge_distribution_uses_abs_density PASSED
test_wake_derived_impedance_records_refined_visible_peaks ..... PASSED
test_fit_wake_with_pso_quality_gate_can_fail_on_poor_correlation PASSED
test_longitudinal_default_path_still_uses_cst_impedance_curve  PASSED
test_longitudinal_pso_source_scalarizes_reconstructed_impedance PASSED
test_longitudinal_pso_requires_explicit_wake_tree_path ........ PASSED
test_transverse_pso_requires_offset_wake_tree_path ............ PASSED
test_transverse_pso_uses_reference_offset_wake_difference ..... PASSED
test_known_mode_compute_wake_matches_direct_evaluation ........ PASSED
test_known_mode_empty_known_modes_produces_zero_wake .......... PASSED
test_known_mode_metadata_in_fit_result ....................... PASSED
test_known_mode_target_fully_explained_by_known_wake .......... PASSED
test_known_mode_plus_hom_exact_optimizer ..................... PASSED
test_known_mode_without_known_falls_back_to_existing_behavior . PASSED
```

**18 passed in 0.51s**

## Known Limitations

- The `KnownMode` → wake amplitude conversion uses the same Gaussian form factor (`_gaussian_form_factor`) as the PSO fit path. This assumes the same bunch length (`sigma_z_m`) and charge distribution model. If the actual bunch distribution deviates significantly from Gaussian, the fixed-mode wake amplitude will be incorrect by the form-factor mismatch.
- The implementation uses the "additive" approach (`known_wake + fitted_unknown_wake` compared to target), not the "subtractive" approach (subtracting known-mode wake from target and fitting residual). Both are equivalent for the objective but the additive approach keeps the original target intact in diagnostics.
- Transverse known modes are not explicitly tested but the `compute_known_mode_wake` function passes `direction` through to `wake_from_parameters`, so it should work structurally for transverse mode definitions.
- The `WakeFitInput` `known_modes` field is not yet wired through `build_wake_fit_input_from_config` — that belongs in P02 (config integration). Currently callers must construct `WakeFitInput` directly with `known_modes`.

## Scope Compliance

| Requirement | Status |
|---|---|
| Works only on `phase/*` branch | ✅ `phase/S01-P01-fixed-mode-core` |
| Did not push main | ✅ |
| Did not merge | ✅ |
| Did not modify `stage_plan.md` | ✅ |
| Did not implement Direction 2 | ✅ (full-wake subtraction / residual wake-to-impedance not implemented) |
| Did not modify CST API | ✅ (no `src/cst_optimization/` changes) |
| Did not modify `wakefield_objective.py` | ✅ (no changes needed) |
| Did not replace PSO | ✅ |
| Did not modify scalarization behaviour | ✅ |
| Allowed scope: `pso_wake_fit.py` + test file | ✅ |
| R/Q-to-wake conversion uses existing convention | ✅ (verified against `fit_wake_with_pso` line 1146) |

## Follow-up Notes For Web Phase Reviewer

The implementation is complete for P01 core. P02 (`P02-objective-config-integration`) should wire `known_modes` through `build_wake_fit_input_from_config` and `LongitudinalImpedanceObjective._raw_value_from_pso_wake` so that known modes can be supplied via the YAML `obj_params.pso_fit.known_modes` config. The `KnownMode` dataclass and `WakeFitInput.known_modes` field are already typed for that integration.

The current test suite uses the exact-optimiser bypass (no real PSO execution). A follow-up P03 test could add a live PSO run with one known mode and one HOM to verify the real optimiser converges correctly without touching the known-mode variables.

---

## Follow-up: P01-fixed-mode-core — Codex drift fix

### Problem
In the initial P01 implementation, `fit_wake_with_pso()` selected all visible peaks from the peak source and turned them into optimised `[A, Q]` variables. If the peak source contained the known fundamental mode's peak, that frequency appeared both in `known_modes` (as a fixed contribution) and in `result.modes` (as a fitted mode), violating the requirement that known modes are never optimised by PSO.

### Fix
Three changes were made to `workflows/rfgun_hom_antenna/pso_wake_fit.py`:

1. **`KnownMode.frequency_tolerance_hz`** (new field, default `0.0`): Allows callers to specify a tolerance in Hz for matching known-mode frequencies against detected peaks. A 1 Hz floor is always applied to prevent float-rounding mismatches.

2. **`_filter_known_mode_peaks()`** (new function, after `_mark_selected_peaks`): Splits a sequence of peaks into unknown peaks and known-mode-matched peaks. A peak matches a known mode when `abs(peak.frequency_hz - known.frequency_hz) <= max(known.frequency_tolerance_hz, 1.0)`.

3. **`fit_wake_with_pso()`** modified to:
   - After peak selection, filter out any peaks that match known modes via `_filter_known_mode_peaks`.
   - Mark known-mode-matched peaks in `all_peaks` with `use=False, status="KnownModeFiltered"` for provenance.
   - When zero unknown peaks remain AND known modes exist: skip the PSO optimizer entirely, produce empty `result.modes`, compute `wake_fit` from known-mode wake only, and compute normalised error/correlation against the original target.
   - When zero unknown peaks remain AND no known modes exist: the existing `min_peak_count` error still applies (unchanged behaviour).
   - Existing `wake_objective` path (no known modes) is structurally unchanged.

### Follow-up tests added (4 new, total 22 tests)

All in `tests/workflows/test_workflow2_pso_wake_fit.py`:

1. **`test_known_mode_filter_peaks_matches_by_tolerance`**: Unit test for `_filter_known_mode_peaks` — three peaks, two known modes, verifies only the unmatched peak survives.

2. **`test_known_mode_filter_empty_list`**: Unit test — empty known modes returns all peaks unchanged.

3. **`test_known_mode_only_known_peaks_in_source`**: Integration test — peak source has only a known-mode peak; uses `_raises_optimizer` that raises if called; asserts `result.modes == ()`, `result.known_mode_wake` matches target, and the known-mode peak is marked "KnownModeFiltered" in `all_peaks`.

4. **`test_known_mode_plus_hom_peak_filtering`**: Integration test — peak source contains both known fundamental (500 MHz) and HOM (1.5 GHz) peaks; verifies only the HOM appears in `result.modes`, the fundamental is filtered out with "KnownModeFiltered" status, and the HOM is "Use" in `all_peaks`.

### Test results

```
collected 22 items

... (18 original tests pass) ...
test_known_mode_filter_peaks_matches_by_tolerance ........ PASSED
test_known_mode_filter_empty_list ....................... PASSED
test_known_mode_only_known_peaks_in_source ............. PASSED
test_known_mode_plus_hom_peak_filtering ................ PASSED
```

**22 passed in 0.52s**

### Commit and push

```bash
git add workflows/rfgun_hom_antenna/pso_wake_fit.py tests/workflows/test_workflow2_pso_wake_fit.py .agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md
git commit -m "fix(pso_wake_fit): filter known-mode peaks from PSO variables

- Add KnownMode.frequency_tolerance_hz for configurable frequency matching.
- Add _filter_known_mode_peaks to separate known and unknown peaks.
- Skip PSO optimizer when all peaks are consumed by known modes.
- Mark filtered peaks as KnownModeFiltered in all_peaks diagnostics.
- 4 new tests (22 total), all passing.
"
git push -u origin phase/S01-P01-fixed-mode-core
```
