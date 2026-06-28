# Phase Summary: P03-diagnostics-and-stage-validation

## Status

PHASE_ACCEPTED

## Branch

phase/S01-P03-diagnostics-and-stage-validation

## Commit

f400332

## Summary

P03 made the known/fixed-mode PSO wake fitting feature scientifically reviewable and easier to validate.

The phase added structured diagnostics to `WakeFitResult`, separating fixed known-mode wake, fitted unknown-mode wake, total wake fit, and residual wake.

It also corrected the known-only zero-unknown-mode diagnostic behavior so `objective_value` reports residual sum-of-squares instead of a placeholder value.

## Main Implementation

P03 added three fields to `WakeFitResult`:

* `unknown_mode_wake`
* `residual_wake`
* `diagnostics`

`unknown_mode_wake` contains the pure PSO-fitted unknown-mode wake contribution.

`residual_wake` contains:

`fit_wake - wake_fit`

where `fit_wake` is the target wake and `wake_fit` is the total fitted wake.

`diagnostics` contains structured metrics for reviewing fixed known modes and fitted unknown modes.

## Diagnostics Added

The diagnostics dict includes:

* `known_mode_count`
* `fitted_mode_count`
* `known_mode_labels`
* `target_wake_rms`
* `known_mode_wake_rms`
* `unknown_mode_wake_rms`
* `residual_wake_rms`
* `normalized_error`
* `wake_corr`
* `known_mode_filtered_peak_count`

These fields make it possible to inspect whether the configured known mode was used as fixed data, whether unknown HOMs remain fitted modes, and whether the total fit quality is acceptable.

## Objective Value Behavior

P03 updated `objective_value` so it is computed from the final residual sum-of-squares:

`sum((wake_fit_total - target_wake) ** 2)`

This makes the known-only zero-unknown-mode path meaningful when the known mode does not perfectly explain the target wake.

For exact synthetic cases, the value remains near zero.

## Objective-Level Access

No changes were needed in `wakefield_objective.py`.

The existing `LongitudinalImpedanceObjective.last_fit_result` already carries the enhanced `WakeFitResult`, including known-mode metadata and diagnostics.

## Tests

Reported command:

`py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v`

Reported result:

`36 passed in 0.60s`

P03 added tests for:

* known/unknown/residual wake separation
* diagnostics count and RMS metrics
* known-mode filtered peak count
* known-only imperfect fit residual SSE
* objective-level diagnostics access through `last_fit_result`

## Scope Notes

P03 did not modify:

* `stage_plan.md`
* `wakefield_objective.py`
* CST API
* `src/cst_optimization/`
* scalarization semantics
* Direction 2 logic

P03 did not add live-CST tests. Validation remains no-CST and synthetic, as required.

## Follow-up For P04

P04 should remain a research/review spike, not production coding.

Recommended P04 focus:

* build a no-CST synthetic experiment with known fundamental plus multiple HOMs
* subtract exact and perturbed fundamentals
* quantify sensitivity to frequency, Q, and R/Q mismatch
* evaluate finite wake length and windowing effects on reconstructed impedance
* produce a go/no-go recommendation for Direction 2
* explicitly state required CST convention checks before any production implementation

P04 should not implement full-wake fitting or residual wake-to-impedance production unless the user explicitly promotes it beyond the current spike scope.

## Codex Follow-up

After P03 acceptance, Codex tightened two P02/P03 boundaries on this branch:

* `pso_fit.known_modes` is longitudinal-only for this stage; transverse PSO fitting now rejects the key.
* `frequency_tolerance_hz` must be finite and non-negative.

Codex also added the missing workflow templates and phase documents so future Web/local-agent handoff can use remote `.agent/` files rather than pasted text.

Follow-up validation:

`py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py`

Result:

`38 passed in 0.64s`
