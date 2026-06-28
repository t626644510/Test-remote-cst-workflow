# Phase Summary: P01-fixed-mode-core

## Status

PHASE_ACCEPTED

## Branch

phase/S01-P01-fixed-mode-core

## Commit

b3f7b83

## Summary

P01 added core support for fixed known resonator modes in Workflow 2 PSO wake-potential fitting.

Known longitudinal modes can now be represented as fixed data instead of optimized PSO variables. The fitter evaluates known-mode wake contributions on the fit grid, filters matching known-mode peaks out of the PSO variable list, and optimizes only remaining unknown modes.

## Main Implementation

The phase introduced:

* `KnownMode`
* `KnownMode.frequency_tolerance_hz`
* `compute_known_mode_wake()`
* `_wake_objective_with_known()`
* `_filter_known_mode_peaks()`
* `WakeFitInput.known_modes`
* `WakeFitResult.known_modes`
* `WakeFitResult.known_mode_wake`

## Behavior Added

When known modes are supplied:

* known-mode wake is computed from `R/Q`, Q, frequency, bunch form factor, and wake charge scale;
* known-mode wake is added to fitted unknown-mode wake for target comparison;
* peaks matching known modes are removed from the PSO-selected unknown peak list;
* filtered peaks are marked as `KnownModeFiltered`;
* PSO is skipped entirely when all selected peaks are known modes;
* result modes contain only fitted unknown modes;
* reconstructed impedance includes known modes when `include_in_reconstructed_impedance` is true.

When no known modes are supplied:

* existing behavior is preserved.

## Tests

Reported command:

`py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v`

Reported result:

`22 passed in 0.52s`

Test coverage includes:

* known-mode wake formula equivalence,
* empty known-mode wake,
* result metadata,
* one-known-mode synthetic wake,
* known-mode plus HOM synthetic wake,
* backward compatibility without known modes,
* known-mode peak filtering by tolerance,
* empty known-mode filtering behavior,
* known-only peak source with optimizer skipped,
* known fundamental plus HOM peak source where only the HOM remains fitted.

## Scope Notes

P01 did not wire YAML config into Workflow 2 objective logic. That remains P02 scope.

P01 did not modify:

* `stage_plan.md`
* `wakefield_objective.py`
* CST API
* `src/cst_optimization/`
* scalarization semantics
* Direction 2 logic

## Follow-up For P02

P02 should wire `obj_params.pso_fit.known_modes` into Workflow-2 longitudinal PSO fitting.

Expected P02 focus:

* parse known modes from config,
* validate required fields,
* reject unsupported directions clearly,
* pass parsed known modes into `WakeFitInput`,
* add no-CST objective integration tests,
* preserve default `cst_impedance` and existing `pso_wake` behavior.
