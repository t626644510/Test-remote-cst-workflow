# Execution Report

## Phase
P02-objective-config-integration

## Branch
`phase/S01-P02-objective-config-integration`

## Summary
Wired `known_modes` from YAML/config into the Workflow-2 longitudinal PSO fitting path. Added `_known_modes_from_config()` parser in `pso_wake_fit.py` and integrated it into `build_wake_fit_input_from_config()`. The `LongitudinalImpedanceObjective` now automatically passes configured known modes through to `WakeFitInput` with no changes to the objective layer — the config flows through the existing `build_wake_fit_input_from_config` call. Default behaviour (no known_modes) is preserved.

## Files Changed

### `workflows/rfgun_hom_antenna/pso_wake_fit.py`
1. **`_known_modes_from_config(cfg, fitting_direction)`** (new function): Parses `cfg["known_modes"]` — a list of dicts — and returns `tuple[KnownMode, ...]`. Validates required fields (`frequency_hz`, `q`, `r_over_q_ohm`), optional fields (`label`, `direction`, `frequency_tolerance_hz`, `include_in_reconstructed_impedance`), and direction consistency. Returns empty tuple when `known_modes` is absent, `None`, or empty.

2. **`_get_known_required_float()`** (new helper): Extracts and validates a required float from a known-mode config entry, with clear error messages that include the index of the offending entry.

3. **`build_wake_fit_input_from_config()`**: Added `known_modes=_known_modes_from_config(cfg, direction)` to the `WakeFitInput` constructor call.

### `workflows/rfgun_hom_antenna/wakefield_objective.py`
No changes needed. The existing `_raw_value_from_pso_wake` path already passes the full `pso_fit` config dict to `build_wake_fit_input_from_config()`, so the `known_modes` key flows through automatically.

### `tests/workflows/test_workflow2_pso_wake_fit.py`
Added 10 new tests (see below).

## Config Shape Supported

```yaml
pso_fit:
  known_modes:
    - label: fundamental             # recommended
      direction: longitudinal        # optional, must match fitting direction
      frequency_hz: 499.8e6          # required, positive
      q: 36500                       # required, positive (>0.5 for longitudinal)
      r_over_q_ohm: 208.6            # required, finite
      frequency_tolerance_hz: 0.5e6  # optional, non-negative, default 0.0
      include_in_reconstructed_impedance: true  # optional, default true
```

## Validation Behavior

| Condition | Error |
|-----------|-------|
| Missing `frequency_hz` | `pso_fit.known_modes[N].frequency_hz is required but missing.` |
| Missing `q` | `pso_fit.known_modes[N].q is required but missing.` |
| Missing `r_over_q_ohm` | `pso_fit.known_modes[N].r_over_q_ohm is required but missing.` |
| `direction` mismatch (e.g. transverse in longitudinal fit) | `pso_fit.known_modes[N].direction='transverse' does not match fitting direction 'longitudinal'.` |
| `known_modes` not a list | `pso_fit.known_modes must be a list of mode definitions.` |
| Entry not a dict | `pso_fit.known_modes[N] must be a dict, got ...` |
| `frequency_tolerance_hz < 0` | `pso_fit.known_modes[N].frequency_tolerance_hz must be non-negative; got ...` |
| `frequency_hz <= 0` | `pso_fit.known_modes[N].frequency_hz must be positive; got ...` |
| `q <= 0` | `pso_fit.known_modes[N].q must be positive; got ...` |

## Tests Added Or Updated

All new tests (10) are in `tests/workflows/test_workflow2_pso_wake_fit.py`:

### Config parsing tests (6):
1. **`test_known_modes_from_config_parses_full_valid_entry`**: Full config with all fields parses correctly.
2. **`test_known_modes_from_config_default_fields`**: Optional fields get sensible defaults (label="known_0", tolerance=0.0, include=True).
3. **`test_known_modes_from_config_empty_when_absent`**: No `known_modes` in config → `()`.
4. **`test_missing_required_field`** (parametrized ×3): Each of `frequency_hz`, `q`, `r_over_q_ohm` when missing raises `WakeFitError` mentioning `known_modes` and the field name.

### Direction validation tests (2):
5. **`test_transverse_known_mode_in_longitudinal_fit`**: Transverse known mode in longitudinal fit raises error mentioning both directions.
6. **`test_known_mode_direction_matches_fitting_direction`**: Explicit matching direction does not raise.

### Objective integration tests (2):
7. **`test_known_modes_in_config_reaches_fit_input`**: monkeypatches `fit_wake_with_pso` in `wakefield_objective` namespace, verifies that `obj_params.pso_fit.known_modes` results in a populated `WakeFitInput.known_modes` with correct `KnownMode` values.
8. **`test_no_known_modes_in_config_passes_empty`**: Same monkeypatch — when `known_modes` is absent from config, `WakeFitInput.known_modes == ()`.

### Default regression (implicit):
All 22 existing P01 + earlier tests continue to pass unchanged.

## Test Commands

```bash
py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v
```

(pytest via `py` launcher, Python 3.9.13, Windows)

## Test Results

```
collected 32 items

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
test_known_mode_filter_peaks_matches_by_tolerance ............ PASSED
test_known_mode_filter_empty_list ........................... PASSED
test_known_mode_only_known_peaks_in_source .................. PASSED
test_known_mode_plus_hom_peak_filtering ..................... PASSED
test_known_modes_from_config_parses_full_valid_entry ......... PASSED
test_known_modes_from_config_default_fields ................. PASSED
test_known_modes_from_config_empty_when_absent .............. PASSED
TestKnownModesFromConfigRequiredFields::test_missing_required_field[frequency_hz] PASSED
TestKnownModesFromConfigRequiredFields::test_missing_required_field[q] PASSED
TestKnownModesFromConfigRequiredFields::test_missing_required_field[r_over_q_ohm] PASSED
TestKnownModesFromConfigDirectionValidation::test_transverse_known_mode_in_longitudinal_fit PASSED
TestKnownModesFromConfigDirectionValidation::test_known_mode_direction_matches_fitting_direction PASSED
TestLongitudinalObjectiveWithKnownModes::test_known_modes_in_config_reaches_fit_input PASSED
TestLongitudinalObjectiveWithKnownModes::test_no_known_modes_in_config_passes_empty PASSED
```

**32 passed in 0.64s**

## Known Limitations

- Transverse known-mode config parsing is validated against the fitting direction but the `_known_modes_from_config` parser's field semantics (R/Q in ohm) are longitudinal-optimised. Transverse R/Q units (ohm/m) would need separate validation.
- The `wakefield_objective.py` layer was not modified because the config already flows through `build_wake_fit_input_from_config`. This is by design, keeping the objective layer decoupled from config format specifics.
- P03 diagnostics will need to surface configured known modes in result inspection; currently known modes appear in `WakeFitResult.known_modes` but are not yet exposed through objective-level summary methods.

## Scope Compliance

| Requirement | Status |
|---|---|
| Works on `phase/*` branch | ✅ `phase/S01-P02-objective-config-integration` |
| Did not push main | ✅ |
| Did not merge | ✅ |
| Did not modify `stage_plan.md` | ✅ |
| Did not implement Direction 2 | ✅ |
| Did not modify CST API | ✅ (no `src/cst_optimization/` changes) |
| Did not change scalarization semantics | ✅ |
| Only modified allowed scope files | ✅ (`pso_wake_fit.py`, test file, execution report) |
| `wakefield_objective.py` unchanged | ✅ (not needed) |
| No `obj_params.pso_fit.known_modes` parsing in objective | ✅ (parsed in `_known_modes_from_config` in `pso_wake_fit.py`) |

## Follow-up Notes For Web Phase Reviewer

P02 is ready for review. The implementation is minimal: a config parser function in `pso_wake_fit.py` that returns a `tuple[KnownMode]` from the YAML-style dict, wired into the existing `build_wake_fit_input_from_config` entry point. Since the `LongitudinalImpedanceObjective._raw_value_from_pso_wake` already passes `pso_fit` config through to `build_wake_fit_input_from_config`, no objective changes were needed — the `known_modes` key flows through automatically.

The branch has been pushed to remote for inspection.

---

## Follow-up: longitudinal Q validation

### Problem
The `_known_modes_from_config` docstring stated that longitudinal known-mode `q` must be `> 0.5`, but the parser only rejected `q <= 0.0`. A longitudinal known mode with `0 < q <= 0.5` would pass config parsing and fail later in `wake_from_parameters()`.

### Fix
Added parser-level validation in `_known_modes_from_config`: when `fitting_direction` is `"longitudinal"` and `q <= 0.5`, a `WakeFitError` is raised immediately with a message like:

```
pso_fit.known_modes[0].q must be > 0.5 for longitudinal known modes; got 0.5.
```

The existing `q <= 0.0` check is preserved for transverse-like generic rejection.

### Tests
Added `TestKnownModesFromConfigRequiredFields.test_longitudinal_known_mode_q_must_exceed_half`:
- Config with `q = 0.5`, valid other fields, `direction="longitudinal"`.
- Asserts `WakeFitError` raised by `build_wake_fit_input_from_config`.
- Asserts error contains `known_modes`, `.q`, `> 0.5`, and the value `0.5`.

### Test command and result
```
py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v
33 passed in 0.55s
```

### Scope compliance
- Only phase branch: ✅
- No main push: ✅
- No merge: ✅
- No stage_plan modification: ✅
- No `wakefield_objective.py` modification: ✅
- No CST API change: ✅
- No Direction 2: ✅
