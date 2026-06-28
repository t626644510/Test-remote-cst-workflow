# Codex Audit: P02/P03

## Verdict
RESOLVED_AFTER_FOLLOWUP

## Scope Reviewed
- P02 branch: `phase/S01-P02-objective-config-integration`
- P02 commits: `779c9bf`, `297d346`
- P03 branch: `phase/S01-P03-diagnostics-and-stage-validation`
- P03 commit: `f400332`

## Validation Run By Codex

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Result:

```text
36 passed
```

Follow-up validation after Codex fixes:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Result:

```text
38 passed
```

## Accepted Technical Work
- P02 wires `pso_fit.known_modes` into `WakeFitInput.known_modes`.
- P02 validates required known-mode fields and longitudinal `q > 0.5`.
- P01 follow-up behavior is present: known-mode-matched peaks are filtered from unknown PSO variables.
- P03 separates fixed known-mode wake, fitted unknown-mode wake, total fit, and residual wake in `WakeFitResult`.
- P03 exposes structured diagnostics and fixes the zero-unknown-mode `objective_value` to final residual SSE.
- No CST API, shared core, scalarization, or Direction 2 production code was modified.

## Findings

### P1: P02/P03 phase workflow files are incomplete
The repository does not contain `phase_plan.md` or `executor_prompt.md` for P02 or P03. This violates the multi-agent workflow rule that every phase must have:

- `phase_plan.md`
- `executor_prompt.md`
- `execution_report.md`
- `phase_review.md`
- `phase_summary.md`

Only the execution reports are committed on the P03 branch. The P02/P03 phase reviews and summaries exist locally but are currently untracked, so remote reviewers may not see them.

### P2: `known_modes` can be implicitly enabled for transverse fitting
`_known_modes_from_config()` is wired into the generic `build_wake_fit_input_from_config()` path. If a transverse PSO fit receives `known_modes` entries without an explicit `direction`, the parser defaults those entries to the current fitting direction and accepts them as transverse known modes.

This is broader than the stage's initial longitudinal-main-mode objective. It may be acceptable as a trivial generalization, but it should be explicitly documented or tightened before stage acceptance.

Codex probe result:

```text
trans rejects longitudinal known mode: WakeFitError ...
trans implicit known count 1 KnownMode(...)
```

Recommended follow-up: either require explicit `direction: longitudinal` for known modes in this stage, or document/test that omitted `direction` intentionally means "current fitting direction" and that transverse known modes are accepted but not validated for scientific use yet.

### P3: `frequency_tolerance_hz` should reject non-finite values
`frequency_tolerance_hz` is converted with `float(...)` and checked only for `< 0.0`. Non-finite values such as `nan` can pass validation and then make known-mode peak filtering silently fail or behave unexpectedly.

Recommended follow-up: require `np.isfinite(tolerance)` and add a small parser test.

## Process Recommendation
Before proceeding to P04 or final stage review:

1. Commit/push the missing `.agent` review and summary files, or regenerate committed P02/P03 phase documentation.
2. Resolve the transverse implicit-known-mode boundary as either intentional documented behavior or a validation error.
3. Add finite validation for `frequency_tolerance_hz`.

P02/P03 code is close, but stage workflow evidence is not complete yet.

## Follow-up Resolution
Codex resolved the findings in the current P03 branch:

1. Added missing workflow document templates and phase documents:
   - `phase_review.md` and `phase_summary.md` templates under `.agent/skills/multi-agent-git-dev/templates/`.
   - `executor_prompt.md` for P01.
   - `phase_plan.md` and `executor_prompt.md` for P02 and P03.
2. Updated the multi-agent workflow rules:
   - Web Phase Planner writes `.agent/` workflow documents through remote Git.
   - Local Execution Agent must fetch and fast-forward pull the assigned `phase/*` branch before reading `executor_prompt.md`.
   - Execution reports should use the shared template instead of restating long report formats in every prompt.
3. Tightened known-mode config semantics:
   - `pso_fit.known_modes` config is longitudinal-only for this stage.
   - Transverse PSO fitting now rejects `known_modes`, including entries with omitted `direction`.
4. Tightened `frequency_tolerance_hz` validation:
   - Non-finite values such as `NaN` are rejected during config parsing.

The technical and workflow follow-up checks now pass locally. The updated branch should be pushed so Web Phase Planner can review the remote source of truth.
