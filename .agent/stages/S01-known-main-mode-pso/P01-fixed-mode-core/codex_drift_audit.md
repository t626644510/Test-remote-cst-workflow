# Codex Drift Audit: P01-fixed-mode-core

## Verdict
NEEDS_FOLLOWUP

## Context
Web Phase Reviewer marked P01 as `PHASE_ACCEPTED`, but remote branch visibility was unavailable. Codex reviewed the actual local branch and working-tree diff on `phase/S01-P01-fixed-mode-core`.

## Evidence Reviewed
- Branch: `phase/S01-P01-fixed-mode-core`
- Changed implementation files:
  - `workflows/rfgun_hom_antenna/pso_wake_fit.py`
  - `tests/workflows/test_workflow2_pso_wake_fit.py`
- Workflow files present:
  - `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/phase_plan.md`
  - `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md`
  - `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/blocker_report.md`
- Test command run by Codex:
  - `py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py`
- Test result:
  - `18 passed`

## Finding
P01 does not fully enforce the phase requirement that fixed known modes are not optimized by PSO.

The implementation adds `KnownMode` and adds known-mode wake to the fitted wake, but `fit_wake_with_pso()` still selects all visible peaks from the peak source and turns them into optimized `[A, Q]` variables. If the peak source still contains the known fundamental mode, that known frequency appears both in `known_modes` and in `result.modes`.

Relevant code:
- `workflows/rfgun_hom_antenna/pso_wake_fit.py`: peak selection remains `selected = _select_peaks_for_pso(...)`, then `fr_hz = [peak.frequency_hz for peak in selected]`.
- The known-mode wake is added later, after peak selection, without filtering known-mode peaks out of the fitted unknown-mode list.

Codex probe result:

```text
selected_peaks [1000000000.0]
fitted_modes [(1000000000.0, 0.0, 30.0)]
known_modes [(1000000000.0, 30.0, 20.0)]
```

This means a known mode can still consume a PSO variable slot whenever it remains visible in the peak source. The existing tests avoid this in the HOM case by making the peak-source frequency range exclude the fixed fundamental; the one-known-mode test uses a zero-amplitude fitted duplicate, so it does not catch the missing filter.

## Scope Assessment
The implementation stayed within P01 file scope and did not touch CST API, `wakefield_objective.py`, `src/cst_optimization/`, scalarization, or Direction 2.

## Required Follow-up
Before P02 proceeds, P01 should add core behavior and tests for one of these explicit policies:

1. Filter selected peaks that match known modes within an explicit tolerance, so known modes cannot become fitted unknown modes.
2. Add an explicit core-level mechanism for callers to provide only unknown-mode peaks, and document/test that P01 relies on that contract.

Codex recommends option 1 because it better matches the stage goal and reduces the risk of P02 accidentally optimizing the fixed fundamental when `known_modes` is wired from config.

## Process Notes
The working tree is not clean; P01 changes are not committed locally. The execution workflow expected a commit and execution report. This should be corrected before the phase is considered durable.

The old `blocker_report.md` records the initial missing phase branch state. It is now stale because the current branch is `phase/S01-P01-fixed-mode-core`; keep it only if the phase summary explains the blocker was resolved.
