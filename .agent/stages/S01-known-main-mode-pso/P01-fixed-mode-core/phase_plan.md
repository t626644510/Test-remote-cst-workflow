# Phase Plan: S01-P01-fixed-mode-core

## Status
CODEX_APPROVED

## Parent Stage
S01-known-main-mode-pso

## Stage Branch
`stage/S01-known-main-mode-pso`

## Working Branch
`phase/S01-P01-fixed-mode-core`

## Phase Goal
Add core known/fixed-mode support to Workflow 2 PSO wake-potential fitting so that one or more longitudinal resonator modes with known `frequency_hz`, `q`, and `r_over_q_ohm` can be evaluated as fixed wake contributions while PSO optimizes only the remaining unknown modes.

This phase must preserve existing behavior when no known modes are provided.

## Why This Phase Exists
The current PSO wake fitting treats all modal amplitudes and Q values as unknown fitting variables. For the designed RF gun fundamental accelerating mode, that is scientifically unnecessary because the mode parameters are already known from design data.

P01 isolates the core numerical support before config/objective integration. This keeps the first implementation small, testable, and independent of CST access or workflow-level configuration parsing.

## Non-goals
P01 must not:

- Parse `known_modes` from `obj_params.pso_fit`.
- Modify CST API access or CST project execution.
- Change scalarization semantics in `wakefield_objective.py`.
- Implement Direction 2 full-wake subtraction or residual wake-to-impedance production.
- Promote code into `src/cst_optimization/`.
- Replace PSO with another optimizer.
- Add transverse known-mode support unless already present as a trivial internal generalization and fully covered by small tests.
- Rewrite the existing PSO fitting architecture.

## Allowed Scope
Local execution agent may modify only:

- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`

Conditionally allowed only if strictly required by existing imports or test seams:

- `workflows/rfgun_hom_antenna/wakefield_objective.py`

For P01, `wakefield_objective.py` should preferably remain untouched because objective/config integration belongs to P02.

Agent may create:

- `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md`
- A blocker report under the same phase folder if needed.

## Forbidden Scope
Local execution agent must not modify:

- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/web_phase_planner.md`
- CST API code
- Shared core package under `src/cst_optimization/`
- Workflow config examples unless explicitly needed later by P02/P03
- Any branch other than `phase/*`
- `main`
- `stage/S01-known-main-mode-pso`
- PR, merge, or push behavior

## Acceptance Criteria
P01 is acceptable if all of the following are true:

- A typed or clearly structured known-mode data container exists for fixed longitudinal resonator modes.
- Known mode inputs support at minimum:
  - `label`
  - `frequency_hz`
  - `q`
  - `r_over_q_ohm`
  - optional `include_in_reconstructed_impedance`
- Known-mode wake amplitude is derived using the same convention already used in `pso_wake_fit.py` for converting fitted wake amplitude to `R/Q`, consistent with:

  `A = (R/Q) * form_factor(f, sigma_z) * 2*pi*f / wake_charge_scale`

- Fixed known-mode wake can be evaluated on the same fit grid as the existing PSO wake model.
- PSO unknown parameter vector remains limited to unknown fitted modes; fixed known modes are not optimized.
- The fit comparison includes fixed known-mode wake plus fitted unknown-mode wake, or equivalently fits the residual after subtracting fixed known-mode wake.
- Reconstructed impedance can include fixed known modes when configured.
- Existing behavior is preserved when no known modes are supplied.
- Existing public function signatures are preserved where practical; if changed, changes are minimal and backward compatible.
- Tests cover synthetic known-mode behavior and existing regression behavior.

## Required Tests
Local execution agent must add or update tests in:

- `tests/workflows/test_workflow2_pso_wake_fit.py`

Required test coverage:

- Synthetic one-known-mode case: generate wake from a known mode, provide that mode as fixed, and verify zero fitted unknown modes are sufficient or residual is near zero.
- Synthetic known-mode plus HOM case: generate wake from fixed fundamental plus at least one unknown HOM, provide the fundamental as fixed, and verify PSO/core fitting recovers the HOM behavior within reasonable tolerance.
- Backward compatibility: existing PSO wake tests pass without known modes configured.
- Existing function behavior remains unchanged for default call paths.

Required command:

```powershell
.venv\Scripts\python.exe -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

If the environment does not support the Windows path, the agent may also run the equivalent local Python command and must report the exact command used.

## Risks
- Wake amplitude normalization may be inconsistent with existing `R/Q` conversion.
- Sign convention may make fixed-mode addition/subtraction appear correct in synthetic tests but fail exported CST data later.
- Frequency, Q, and `R/Q` units may be silently misused if docstrings are unclear.
- Reconstructed impedance metadata may blur fixed and fitted modes if both are emitted in a single list without provenance.
- P01 may accidentally drift into P02 by adding config parsing too early.

## Escalation Conditions
Stop and write a blocker report instead of continuing if:

- The existing code does not expose enough information to derive known-mode amplitude using the current `R/Q` convention.
- Implementing P01 requires modifying files outside the allowed scope.
- Existing tests reveal that wake sign, units, or normalization are ambiguous and cannot be resolved from current code.
- Supporting fixed known modes requires changing scalarization behavior.
- The implementation would require CST API changes.
- The agent is tempted to implement Direction 2.
- More than one major architecture option appears viable and choosing one would change the stage scope.
