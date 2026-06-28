# Phase Review: P01-fixed-mode-core

## Verdict

PHASE_ACCEPTED

## Phase

P01-fixed-mode-core

## Parent Stage

S01-known-main-mode-pso

## Reviewed Branch

phase/S01-P01-fixed-mode-core

## Reviewed Commit

b3f7b83

## Review Summary

P01 is accepted after Codex follow-up.

The remote phase branch is now visible and was reviewed against the stage baseline branch `codex/wf2-major-refactor-worktree`.

The phase branch is one commit ahead of the stage baseline. The diff is limited to:

* `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md`
* `workflows/rfgun_hom_antenna/pso_wake_fit.py`
* `tests/workflows/test_workflow2_pso_wake_fit.py`

No stage plan, objective integration, CST API, shared core, main branch, or merge changes were observed.

## What Was Accepted

P01 adds core known/fixed-mode support to Workflow 2 PSO wake-potential fitting.

The accepted implementation includes:

* `KnownMode` typed container.
* `KnownMode.frequency_tolerance_hz` for configurable matching between known modes and detected peaks.
* `compute_known_mode_wake()` for converting known `R/Q`, frequency, and Q into fixed wake contribution.
* `_wake_objective_with_known()` for comparing known wake plus unknown fitted wake against the target wake.
* `_filter_known_mode_peaks()` for removing known-mode-matched peaks from the PSO variable list.
* zero-unknown-mode path that skips the optimizer when all selected peaks are known modes.
* `KnownModeFiltered` diagnostic status for filtered peaks.
* `WakeFitInput.known_modes`.
* `WakeFitResult.known_modes` and `WakeFitResult.known_mode_wake`.
* reconstructed impedance inclusion for known modes when configured.
* backward-compatible behavior when no known modes are supplied.

## Codex Follow-up Resolution

The Codex follow-up identified that the initial implementation could allow a known fundamental mode peak to appear both as a fixed known mode and as an optimized PSO variable.

The follow-up fixed this by:

* adding frequency-tolerance-based matching,
* filtering known-mode peaks out of selected PSO peaks,
* marking filtered peaks as `KnownModeFiltered`,
* skipping optimizer execution when no unknown peaks remain,
* adding tests that fail if the optimizer is called in the known-only case.

This resolves the core P01 drift concern.

## Acceptance Criteria Check

* [x] Fixed/known mode data container exists.
* [x] Known mode supports label, frequency, Q, R/Q, reconstructed impedance inclusion control, and matching tolerance.
* [x] Known-mode wake amplitude is derived from the same `R/Q` convention used by the PSO fit path.
* [x] Fixed known-mode wake can be evaluated on the fit grid.
* [x] PSO optimizes only unknown modes.
* [x] Known-mode matched peaks are filtered out before PSO variable construction.
* [x] Zero-unknown-mode case skips optimizer execution.
* [x] Fit comparison uses known-mode wake plus fitted unknown-mode wake.
* [x] Reconstructed impedance can include fixed known-mode contributions.
* [x] Default behavior without known modes is preserved.
* [x] Synthetic one-known-mode test coverage exists.
* [x] Synthetic known-mode plus HOM test coverage exists.
* [x] Peak filtering and diagnostics test coverage exists.
* [x] Existing tests still pass.

## Tests Reviewed

Reported test command:

`py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v`

Reported result:

`22 passed in 0.52s`

The execution report records the initial 18 passing tests plus 4 Codex follow-up tests.

## Scope Compliance

* [x] Worked on `phase/S01-P01-fixed-mode-core`.
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
* [x] Did not parse YAML config for `known_modes`; that remains P02 scope.

## Review Notes

One minor diagnostic note remains for later phases:

In the zero-unknown-mode path, `objective_value` is currently set to `0.0`, while actual fit quality is represented by `normalized_error` and `wake_corr`. This does not block P01 acceptance, but P03 diagnostics may consider clarifying or recomputing objective semantics for known-only fits.

## Result

P01-fixed-mode-core is accepted.

Proceed to P02-objective-config-integration.
