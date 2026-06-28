# Stage Plan: S01-known-main-mode-pso

## Status
DRAFT

## Stage Branch
`stage/S01-known-main-mode-pso`

## Stage Goal
Improve Workflow 2 PSO wake-potential fitting by allowing the dominant, already-designed fundamental accelerating mode to be supplied as fixed resonator data instead of fitted as an unknown mode.

The first implementation target is direction 1: keep the existing long-range wake-potential fitting approach, but let users predefine known main-mode parameters so PSO optimizes only the remaining unknown modes.

Direction 2 is evaluated in this stage plan, but should not be implemented until the direction-1 path is accepted and the listed validation conditions are satisfied.

## Scientific Context
Existing PSO wake fitting assumes high-Q modal parameters are unknown except for fixed resonant frequencies detected from an impedance source or derived from wake data. For the RF gun fundamental mode, that assumption is unnecessarily weak: the main mode is a designed mode with known parameters.

Reference example for the fundamental mode:

- Frequency: `499.8 MHz +/- 0.5 MHz`.
- Unloaded Q: `Q0 = 36500`, dimensionless.
- `R/Q = 208.6 ohm`.
- Shunt impedance assumption: `R = Q0 * (R/Q) ~= 7.61 Mohm`.

Units and assumptions must be explicit in implementation docstrings and comments. The known-mode wake amplitude should be derived from the same formula already used by `pso_wake_fit.py` when converting fitted wake amplitude to `R/Q`:

`A = (R/Q) * form_factor(f, sigma_z) * 2*pi*f / wake_charge_scale`

where `f` is in Hz, `sigma_z` is in meters, `R/Q` is in ohm for longitudinal impedance, and `wake_charge_scale` preserves the existing V/pC convention.

## Current Baseline
The current working tree already contains PSO wake fitting work:

- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `workflows/rfgun_hom_antenna/wakefield_objective.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`

This stage treats those files as the active baseline. Do not revert or rewrite the existing PSO fitting architecture unless a phase review escalates an explicit architecture conflict.

Important current behavior:

- Frequencies are fixed from visible impedance peaks or wake-derived refined peaks.
- PSO currently optimizes `[A1, Q1, A2, Q2, ...]`.
- Fitted `A` is converted to `R/Q`, then to reconstructed impedance.
- Fit windows already support long-range tail fitting with explicit distance/time units.

## Direction 1: Fixed Known Main Mode
### Intended Behavior
Users can pass one or more known resonator modes through `obj_params.pso_fit`, initially for longitudinal fitting. A known mode with frequency, Q, and `R/Q` is not optimized by PSO.

For long-range fitting, the PSO objective should compare:

`known_mode_wake + fitted_unknown_mode_wake`

against the measured CST wake potential over the configured fit window.

Equivalently, implementation may subtract the known-mode wake from the target wake and fit the residual, as long as the final diagnostics still report the full reconstructed wake and include clear fixed-mode metadata.

### Expected Config Shape
The phase planner may refine names, but the stage-level contract should stay close to:

```yaml
pso_fit:
  known_modes:
    - label: fundamental
      direction: longitudinal
      frequency_hz: 499.8e6
      q: 36500
      r_over_q_ohm: 208.6
      frequency_tolerance_hz: 0.5e6
      include_in_reconstructed_impedance: true
```

The implementation should also allow `wake_amplitude` only if it is clearly documented as being in the same wake unit as the input wake curve. The primary path should be `R/Q` based, because that matches the known RF design data.

### Scope Boundaries
Allowed implementation scope for direction 1:

- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `workflows/rfgun_hom_antenna/wakefield_objective.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`
- Workflow-2 config examples or comments if needed.

Forbidden in direction 1 unless escalated:

- CST API changes.
- Shared-core promotion into `src/cst_optimization/`.
- Replacing PSO with another optimizer.
- Reworking wakefield objective scalarization semantics.
- Implementing direction 2 subtraction/full-wake production.

## Direction 2: Full Wake After Main-Mode Removal
### Assessment
The idea is physically plausible but not ready to treat as guaranteed.

If the dominant fundamental wake can be accurately synthesized from known `f`, `Q0`, `R/Q`, bunch form factor, and the same wake convention used by CST, then subtracting it from the computed full wake should leave a HOM residual. With a sufficiently long wake length, HOMs with lower Q should decay, and wake-to-impedance reconstruction may become more accurate across a wider frequency band than the current long-range-only fit.

However, several conditions must be validated before implementation:

- The CST wake potential normalization, sign convention, time origin, and bunch charge/form-factor convention must match the model used in `wake_from_parameters`.
- The known-mode frequency must be accurate enough. A small error near `499.8 MHz` can leave a long-lived sinusoidal residual because `Q0 = 36500` implies slow decay.
- `Q0` must be the correct Q for the wakefield simulation boundary/material setup. If the simulation includes external loading or numerical loss, using unloaded Q may over-subtract or under-subtract.
- `R/Q = 208.6 ohm` must correspond to the same longitudinal voltage definition used by the wake potential.
- The wake length must be long enough for relevant HOM residuals to decay below numerical/noise tolerance. This is not automatic for trapped or high-Q HOMs.
- Early short-range wake contains broadband and numerical components that are not well represented by a small resonator set; subtracting the fundamental does not make early-time data automatically modal.
- Direct wake-to-impedance conversion of a finite, truncated residual can introduce windowing/ringing artifacts unless the truncation and residual tail are controlled.

### Direction 2 Recommendation
Do not implement direction 2 in the first coding phase. Treat it as an experimental follow-up after direction 1 has:

- Fixed-mode synthesis verified against synthetic wake data.
- Residual wake diagnostics available.
- A no-CST comparison showing that subtracting a known main mode recovers known HOM modes.
- A live-CST or exported-data validation case confirming sign, scale, and phase conventions for the fundamental mode.

If those checks pass, direction 2 can become a later stage or a late phase in this stage.

## Phase Breakdown
### P01-fixed-mode-core
Goal: Add typed known-mode support to the PSO fitting core without touching CST access.

Expected work:

- Add a fixed/known mode data container.
- Convert known `R/Q`, Q, and frequency to wake amplitude using existing form-factor conventions.
- Support evaluating fixed known-mode wake on the fit grid.
- Modify the PSO objective path so fixed modes are included in the fitted wake or subtracted from the target residual.
- Reconstruct impedance as fixed modes plus fitted unknown modes when configured.
- Preserve existing behavior when no known modes are configured.

Required tests:

- Synthetic one-known-mode wake requires zero fitted modes or leaves near-zero residual.
- Synthetic known-mode plus HOM case recovers the HOM when the main mode is fixed.
- Existing PSO tests still pass.

### P02-objective-config-integration
Goal: Wire known modes from `obj_params.pso_fit` into Workflow-2 longitudinal PSO fitting.

Expected work:

- Parse `known_modes` from config with explicit units and validation.
- Reject unsupported directions or incomplete known-mode definitions with clear errors.
- Ensure scalarization behavior remains unchanged.
- Keep transverse known-mode support out of scope unless P01 already made it trivial and tests remain small.

Required tests:

- `LongitudinalImpedanceObjective` passes configured known modes into the fit input.
- Missing `frequency_hz`, `q`, or `r_over_q_ohm` fails clearly.
- No-CST regression tests for the default `cst_impedance` path and current `pso_wake` path still pass.

### P03-diagnostics-and-stage-validation
Goal: Make the feature reviewable for scientific use and workflow testing.

Expected work:

- Add result metadata that identifies fixed modes separately from fitted modes.
- Report fixed-mode contribution, residual fit quality, normalized error, and correlation in existing result structures or test-accessible fields.
- Add or update documentation/config comments only where useful.
- Run targeted no-CST validation.

Required tests:

- `.venv\Scripts\python.exe -m pytest tests\workflows\test_workflow2_pso_wake_fit.py`

Optional validation if exported CST data is available:

- Compare synthesized fundamental wake against CST wake near the configured `499.8 MHz` mode.
- Check whether subtracting the known mode leaves a physically plausible HOM residual.

### P04-direction-2-feasibility-spike
Goal: Decide whether full-wake fitting or residual wake-to-impedance reconstruction should become an implementation stage.

This is a research/review phase, not production coding, unless the user explicitly promotes it.

Expected work:

- Build a no-CST synthetic experiment with known fundamental plus multiple HOMs.
- Subtract the exact or slightly perturbed fundamental and quantify residual sensitivity.
- Evaluate finite wake length/windowing effects on reconstructed impedance.
- Produce a short feasibility report under the phase folder.

Acceptance:

- Clear go/no-go recommendation for direction 2.
- Explicit conditions for required wake length, tolerance, and CST convention checks.

## Stage Acceptance Criteria
- Direction 1 is implemented through accepted phases and preserves existing default behavior.
- Known fundamental mode parameters can be configured without making them PSO variables.
- The reconstructed impedance can include the fixed fundamental contribution when requested.
- Fit diagnostics distinguish fixed known modes from fitted unknown modes.
- Targeted no-CST tests pass.
- Any live-CST validation remains clearly separated from no-CST validation.
- Direction 2 has a documented feasibility conclusion before implementation scope expands.

## Risks
- A sign or normalization mismatch between the resonator formula and CST wake potential can make fixed-mode subtraction misleading.
- Using unloaded `Q0` may be wrong if the wake simulation reflects loaded Q or numerical damping.
- Known fundamental frequency uncertainty can dominate the residual over long wakes.
- Allowing known modes into the same result list as fitted modes may blur scientific provenance unless metadata is explicit.
- Direction 2 can silently become a broader signal-processing project; keep it gated behind feasibility evidence.

## Escalation Conditions
Escalate to Codex or the user if:

- The exact CST wake potential convention cannot be confirmed from existing code, tests, user-provided docs, or exported data.
- Direction 1 requires changes outside the allowed files.
- Known-mode subtraction improves synthetic tests but fails a CST/exported validation case by sign, scale, or phase.
- Direction 2 requires assumptions about HOM decay that cannot be validated with available wake length or data.
- A phase fails review twice.

## Next Role Handoff
Web Phase Planner should create `P01-fixed-mode-core/phase_plan.md` and `executor_prompt.md` first. The first local execution agent should implement only the array-level PSO core support, with no CST API or objective integration changes.
