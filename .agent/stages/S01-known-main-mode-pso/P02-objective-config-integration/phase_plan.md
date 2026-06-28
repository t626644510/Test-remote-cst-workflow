# Phase Plan: S01-P02-objective-config-integration

## Status
CODEX_APPROVED

## Parent Stage
S01-known-main-mode-pso

## Working Branch
`phase/S01-P02-objective-config-integration`

## Phase Goal
Wire configured `obj_params.pso_fit.known_modes` into Workflow-2 longitudinal PSO wake fitting.

## Why This Phase Exists
P01 added array-level known-mode support. P02 makes that support usable from workflow configuration while keeping objective scalarization and CST access unchanged.

## Non-goals
- Do not modify CST API.
- Do not modify `src/cst_optimization/`.
- Do not change scalarization semantics.
- Do not implement Direction 2.
- Do not add transverse known-mode production support.

## Allowed Scope
- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`
- `.agent/stages/S01-known-main-mode-pso/P02-objective-config-integration/execution_report.md`

`workflows/rfgun_hom_antenna/wakefield_objective.py` may be touched only if config cannot flow through the existing builder path.

## Forbidden Scope
- CST API code
- `src/cst_optimization/`
- Direction 2 code
- Stage-level plans
- Main or stage branch pushes

## Acceptance Criteria
- [x] `known_modes` is parsed from `pso_fit` config.
- [x] Parsed known modes reach `WakeFitInput.known_modes`.
- [x] Missing `frequency_hz`, `q`, or `r_over_q_ohm` fails clearly.
- [x] Longitudinal `q <= 0.5` fails clearly during config parsing.
- [x] `frequency_tolerance_hz` is finite and non-negative.
- [x] `known_modes` config is limited to longitudinal fitting for this stage.
- [x] No-known-mode default behavior is unchanged.
- [x] Existing pso_wake and cst_impedance regression tests pass.

## Required Tests
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

## Risks
- Config parser may accidentally broaden support into transverse physics before validation.
- Unit naming for `r_over_q_ohm` must remain explicit.

## Escalation Conditions
Escalate if config wiring requires CST API changes, scalarization changes, or transverse known-mode semantics.
