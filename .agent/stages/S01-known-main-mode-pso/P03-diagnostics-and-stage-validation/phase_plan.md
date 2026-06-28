# Phase Plan: S01-P03-diagnostics-and-stage-validation

## Status
CODEX_APPROVED

## Parent Stage
S01-known-main-mode-pso

## Working Branch
`phase/S01-P03-diagnostics-and-stage-validation`

## Phase Goal
Expose diagnostics that distinguish fixed known modes from fitted unknown modes and make no-CST validation reviewable.

## Why This Phase Exists
P01/P02 make known modes usable. P03 ensures downstream reviewers can inspect fixed-mode contribution, fitted-mode contribution, residual wake, and fit quality without ambiguity.

## Non-goals
- Do not modify CST API.
- Do not modify `src/cst_optimization/`.
- Do not change scalarization semantics.
- Do not implement Direction 2.
- Do not add live-CST validation.

## Allowed Scope
- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`
- `.agent/stages/S01-known-main-mode-pso/P03-diagnostics-and-stage-validation/execution_report.md`

`workflows/rfgun_hom_antenna/wakefield_objective.py` may be touched only if objective-level access cannot be achieved through existing `last_fit_result`.

## Forbidden Scope
- CST API code
- `src/cst_optimization/`
- Direction 2 production code
- Scalarization logic
- Stage-level plans

## Acceptance Criteria
- [x] `WakeFitResult` separates fixed known-mode wake, fitted unknown-mode wake, total fit, and residual wake.
- [x] Diagnostics include known/fitted mode counts, known labels, wake RMS values, normalized error, correlation, and filtered peak count.
- [x] Known-only zero-unknown-mode path reports actual residual SSE.
- [x] Objective-level access remains available through `LongitudinalImpedanceObjective.last_fit_result`.
- [x] Targeted no-CST tests pass.

## Required Tests
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

## Risks
- Result metadata could blur fitted and fixed provenance.
- Diagnostics should remain lightweight and test-accessible.

## Escalation Conditions
Escalate if diagnostics require objective scalarization changes, CST API changes, or Direction 2 implementation.
