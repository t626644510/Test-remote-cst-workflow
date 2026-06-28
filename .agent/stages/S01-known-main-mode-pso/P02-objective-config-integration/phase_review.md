# Phase Review: P02-objective-config-integration

## Verdict

PHASE_ACCEPTED

## Phase

P02-objective-config-integration

## Parent Stage

S01-known-main-mode-pso

## Reviewed Branch

phase/S01-P02-objective-config-integration

## Reviewed Commits

* 779c9bf
* 297d346

## Review Summary

P02 is accepted after follow-up.

The implementation wires `obj_params.pso_fit.known_modes` into Workflow-2 longitudinal PSO wake fitting by parsing known modes in `pso_wake_fit.py` and passing them into `WakeFitInput.known_modes`.

No changes to `wakefield_objective.py` were needed because the existing objective path already passes the full `pso_fit` config into `build_wake_fit_input_from_config()`.

The follow-up resolved the only review blocker: longitudinal known-mode `q <= 0.5` is now rejected during config parsing rather than later during wake evaluation.

## What Was Accepted

The accepted implementation includes:

* `_known_modes_from_config(cfg, fitting_direction)`
* `_get_known_required_float()`
* config parsing for `known_modes`
* validation for required known-mode fields
* validation for direction mismatch
* validation for negative frequency tolerance
* validation for positive frequency
* validation for positive Q
* longitudinal-specific validation requiring `q > 0.5`
* validation for finite `r_over_q_ohm`
* default empty tuple behavior when `known_modes` is absent
* wiring into `build_wake_fit_input_from_config()`
* objective integration through the existing `LongitudinalImpedanceObjective` pso_wake config flow
* tests proving configured known modes reach `WakeFitInput`

## Config Shape Accepted

Supported shape:

pso_fit:
known_modes:
- label: fundamental
direction: longitudinal
frequency_hz: 499.8e6
q: 36500
r_over_q_ohm: 208.6
frequency_tolerance_hz: 0.5e6
include_in_reconstructed_impedance: true

Required fields:

* `frequency_hz`
* `q`
* `r_over_q_ohm`

Optional fields:

* `label`
* `direction`
* `frequency_tolerance_hz`
* `include_in_reconstructed_impedance`

## Acceptance Criteria Check

* [x] `known_modes` is parsed from pso_fit config.
* [x] Parsed known modes are passed into `WakeFitInput.known_modes`.
* [x] `LongitudinalImpedanceObjective` pso_wake path can pass configured known modes into the PSO fit input.
* [x] Missing `frequency_hz` fails clearly.
* [x] Missing `q` fails clearly.
* [x] Missing `r_over_q_ohm` fails clearly.
* [x] Direction mismatch fails clearly.
* [x] Longitudinal `q <= 0.5` fails clearly at config parsing.
* [x] Absent `known_modes` preserves default behavior with `known_modes == ()`.
* [x] Existing `cst_impedance` and `pso_wake` regression tests continue to pass.
* [x] Scalarization behavior is unchanged.
* [x] Direction 2 is not implemented.

## Tests Reviewed

Reported command:

`py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py -v`

Reported result:

`33 passed in 0.55s`

Test coverage includes:

* full known-mode config parsing
* optional field defaults
* absent known_modes default behavior
* missing required fields
* direction mismatch
* matching direction acceptance
* objective-level pso_wake pass-through
* no-known-mode objective pass-through
* longitudinal known-mode Q boundary validation
* all previous P01 and baseline tests

## Scope Compliance

* [x] Worked on `phase/S01-P02-objective-config-integration`.
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

P02 intentionally keeps config parsing in `pso_wake_fit.py` rather than embedding YAML/config semantics into `wakefield_objective.py`.

This is acceptable and preferable for this phase because the objective layer already passes `pso_fit` config into `build_wake_fit_input_from_config()`.

P03 should focus on diagnostics and reviewability, especially exposing fixed-mode metadata and residual quality in result structures or test-accessible fields.

## Result

P02-objective-config-integration is accepted.

Proceed to P03-diagnostics-and-stage-validation.

## Codex Follow-up Note

Codex later tightened the accepted P02 config boundary on the P03 branch:

* `pso_fit.known_modes` config is longitudinal-only for this stage.
* Transverse PSO fitting rejects `known_modes`, even when the per-mode `direction` field is omitted.
* `frequency_tolerance_hz` must be finite and non-negative.

Follow-up validation reported on the P03 branch:

`py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py`

Result: `38 passed`.
