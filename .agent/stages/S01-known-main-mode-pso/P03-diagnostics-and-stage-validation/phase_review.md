# Phase Review: P03-diagnostics-and-stage-validation

## Verdict

PHASE_ACCEPTED

## Phase

P03-diagnostics-and-stage-validation

## Parent Stage

S01-known-main-mode-pso

## Reviewed Branch

phase/S01-P03-diagnostics-and-stage-validation

## Reviewed Commit

f400332

## Review Summary

P03 is accepted.

The phase successfully added result-level diagnostics and no-CST validation for the known/fixed-mode PSO wake fitting feature.

The implementation makes fixed known-mode contributions, fitted unknown-mode contributions, residual wake, and structured quality metrics directly test-accessible through `WakeFitResult`.

No objective-layer changes were required because `LongitudinalImpedanceObjective.last_fit_result` already carries the enhanced `WakeFitResult`.

## What Was Accepted

The accepted implementation includes:

* `WakeFitResult.unknown_mode_wake`
* `WakeFitResult.residual_wake`
* `WakeFitResult.diagnostics`
* common residual-SSE computation for `objective_value`
* structured diagnostics for known/fitted mode counts
* structured diagnostics for known-mode labels
* structured diagnostics for target, known, unknown, and residual wake RMS values
* structured diagnostics for normalized error and wake correlation
* structured diagnostics for known-mode filtered peak count
* no-CST tests for known-mode diagnostics
* no-CST tests for imperfect known-only residual SSE
* no-CST tests for objective-level accessibility through `last_fit_result`

## Acceptance Criteria Check

* [x] Fixed known modes and fitted unknown modes are clearly distinguished.
* [x] `result.modes` remains the fitted unknown-mode list.
* [x] `result.known_modes` remains the fixed known-mode metadata.
* [x] `result.known_mode_wake` exposes fixed known-mode wake contribution.
* [x] `result.unknown_mode_wake` exposes fitted unknown-mode wake contribution.
* [x] `result.residual_wake` exposes target minus total fit.
* [x] `result.wake_fit` remains total fitted wake.
* [x] Diagnostics include known-mode count.
* [x] Diagnostics include fitted-mode count.
* [x] Diagnostics include known-mode labels.
* [x] Diagnostics include target wake RMS.
* [x] Diagnostics include known-mode wake RMS.
* [x] Diagnostics include unknown-mode wake RMS.
* [x] Diagnostics include residual wake RMS.
* [x] Diagnostics include normalized error.
* [x] Diagnostics include wake correlation.
* [x] Diagnostics include known-mode filtered peak count.
* [x] Known-only zero-unknown-mode path reports meaningful residual SSE.
* [x] Objective-level access is available through existing `last_fit_result`.
* [x] Default behavior remains backward compatible.
* [x] No Direction 2 implementation was added.

## Tests Reviewed

Reported command:

`py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v`

Reported result:

`36 passed in 0.60s`

New P03 tests:

* `test_known_mode_result_diagnostics_separate_known_unknown_residual`
* `test_known_only_objective_value_reports_residual_sse`
* `test_longitudinal_objective_exposes_pso_wake_known_mode_diagnostics`

These tests cover:

* known/fitted mode separation
* known wake contribution
* unknown fitted wake contribution
* total wake reconstruction
* residual wake semantics
* diagnostics counts and labels
* diagnostics RMS metrics
* normalized error and wake correlation
* imperfect known-only SSE
* objective-level access to diagnostics

## Scope Compliance

* [x] Worked on `phase/S01-P03-diagnostics-and-stage-validation`.
* [x] Pushed only the phase branch.
* [x] Did not push main.
* [x] Did not merge.
* [x] Did not modify `.agent/stages/S01-known-main-mode-pso/stage_plan.md`.
* [x] Did not modify `workflows/rfgun_hom_antenna/wakefield_objective.py`.
* [x] Did not modify CST API.
* [x] Did not modify `src/cst_optimization/`.
* [x] Did not implement Direction 2.
* [x] Did not replace PSO.
* [x] Did not change scalarization semantics.
* [x] Modified only allowed scope files.

## Review Notes

The diagnostics dict is intentionally flat and test-accessible. This is acceptable for P03 and keeps the implementation lightweight.

The execution report notes that `objective_value` in the normal PSO path is now recomputed from the common residual SSE rather than directly reusing the optimizer-returned value. This is acceptable for P03 because it makes result diagnostics consistent with the final total wake fit.

If future work needs optimizer-native objective values for debugging early termination, that can be added as a separate diagnostic field without changing scalarization.

## Result

P03-diagnostics-and-stage-validation is accepted.

Proceed to P04-direction-2-feasibility-spike, if the stage still requires a documented Direction 2 feasibility conclusion before final stage review.

## Codex Follow-up Review

Codex later resolved the P02/P03 audit follow-up on this branch:

* `known_modes` config is constrained to longitudinal fitting for this stage.
* Transverse PSO fitting rejects `known_modes`, even when per-mode `direction` is omitted.
* `frequency_tolerance_hz` rejects non-finite values.
* Missing workflow docs/templates were added so `.agent/` is a complete source of truth.

Follow-up validation:

`py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py`

Result:

`38 passed in 0.64s`
