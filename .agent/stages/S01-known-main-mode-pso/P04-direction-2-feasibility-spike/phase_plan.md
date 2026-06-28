# Phase Plan: P04-direction-2-feasibility-spike

## Status
DRAFT

## Parent Stage
S01-known-main-mode-pso

## Phase Branch
`phase/S01-P04-direction-2-feasibility-spike`

## Phase Goal
Evaluate whether Direction 2 — subtracting a known fundamental mode from full wake data and using the residual for HOM recovery / wake-to-impedance reconstruction — is feasible enough to become a later implementation stage.

This phase is a no-CST research spike. It must produce a quantitative feasibility report, not production code.

## Why This Phase Exists
The parent stage already implements and validates Direction 1: fixed known longitudinal main-mode support inside the existing long-range PSO wake fitting path.

The stage plan requires a documented Direction 2 feasibility conclusion before implementation scope expands. Direction 2 is physically plausible, but sensitive to fundamental-mode sign, scale, phase, frequency, Q, R/Q, finite wake length, and windowing assumptions. P04 tests those risks using synthetic no-CST data before any production design is approved.

## Non-goals
- Do not implement Direction 2 production code.
- Do not add a new production workflow, CST result path, objective type, or optimizer path.
- Do not modify the CST API or any CST access layer.
- Do not modify `src/cst_optimization/`.
- Do not modify `workflows/rfgun_hom_antenna/pso_wake_fit.py` or `workflows/rfgun_hom_antenna/wakefield_objective.py`.
- Do not modify `tests/workflows/test_workflow2_pso_wake_fit.py`; run it only as regression validation.
- Do not change wakefield objective scalarization semantics.
- Do not change accepted P01/P02/P03 behavior.
- Do not merge or push `main`, `stage/*`, tags, or unrelated branches.

## Allowed Scope
Files that may be modified:

- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md`

Allowed execution-only activity:

- Inspect existing no-CST wake fitting utilities and tests.
- Run the required regression test command.
- Run inline Python synthetic experiments without committing implementation code or persistent scripts.
- Use existing no-CST utilities from `workflows/rfgun_hom_antenna/pso_wake_fit.py`, such as known-mode wake synthesis, wake-to-impedance reconstruction, and peak detection, if useful.

## Forbidden Scope
Do not modify:

- `main`
- `stage/*`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/skills/**`
- `src/cst_optimization/**`
- CST API / CST connector / CST file-reading code
- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `workflows/rfgun_hom_antenna/wakefield_objective.py`
- `tests/**`
- Any scalarization, objective aggregation, optimizer, or production reconstruction semantics

If any production code change appears necessary to complete the feasibility assessment, stop and write a blocker in the execution report.

## Synthetic Experiment Requirements
The feasibility report must include a no-CST synthetic experiment with:

1. A known longitudinal fundamental mode close to the stage reference:
   - `frequency_hz = 499.8e6`
   - `q = 36500`
   - `r_over_q_ohm = 208.6`
2. Multiple synthetic HOMs with distinct frequencies, Q values, and R/Q values.
3. A full synthetic wake equal to fundamental + HOM contributions using the existing wake convention where possible.
4. Exact-fundamental subtraction:
   - subtract the exact synthetic fundamental from the full wake;
   - quantify whether the residual matches the known HOM-only wake.
5. Perturbed-fundamental subtraction:
   - vary fundamental frequency, Q, and R/Q by small controlled offsets;
   - quantify residual sensitivity relative to the HOM-only residual.
6. Finite wake length / windowing evaluation:
   - test multiple wake lengths or truncation windows;
   - evaluate how reconstruction artifacts, peak recovery, or ringing change;
   - include at least one comparison with and without a simple taper/window if practical in an inline experiment.
7. Wake-to-impedance reconstruction check:
   - reconstruct impedance from the synthetic residual when practical;
   - compare recovered peak locations / relative strengths to the known HOM truth;
   - explicitly discuss cases where finite grid resolution or finite wake length hides or distorts peaks.

## Feasibility Report Requirements
Write the report to:

`.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`

The report must include:

- Scope statement confirming this was no-CST and non-production.
- Synthetic mode table for the fundamental and HOMs.
- Commands run, including any inline Python synthetic experiment commands.
- Metrics used, for example residual RMS, normalized residual error, correlation with HOM-only truth, recovered peak frequency error, and residual fundamental leakage.
- Exact-subtraction results.
- Frequency/Q/RQ perturbation sensitivity results.
- Finite wake length / windowing results.
- Interpretation of whether Direction 2 is scientifically stable enough to pursue.
- Clear `GO`, `NO-GO`, or `CONDITIONAL-GO` recommendation.
- Required conditions before any production Direction 2 implementation, including CST sign/scale/phase convention checks and live-CST or exported-data validation.
- Explicit list of assumptions and limitations.

## Acceptance Criteria
- [ ] `feasibility_report.md` is written in the P04 phase folder.
- [ ] `execution_report.md` is written using `.agent/skills/multi-agent-git-dev/templates/execution_report.md`.
- [ ] The phase remains a research spike and does not modify production code, tests, CST API, `src/cst_optimization/`, scalarization semantics, `main`, or `stage/*`.
- [ ] The report uses a no-CST synthetic wake with one known fundamental plus multiple HOMs.
- [ ] Exact fundamental subtraction is evaluated against the known HOM-only truth.
- [ ] Frequency, Q, and R/Q perturbation sensitivity are quantified.
- [ ] Finite wake length and windowing/truncation effects are evaluated.
- [ ] Wake-to-impedance reconstruction behavior is assessed or, if not possible, the blocker is explained quantitatively.
- [ ] The report gives a clear `GO`, `NO-GO`, or `CONDITIONAL-GO` recommendation for Direction 2.
- [ ] The report states concrete conditions required before production Direction 2 implementation.
- [ ] The required regression command passes or any failure is documented as a blocker.

## Required Tests
Run this regression command exactly and record the result:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

If additional inline Python synthetic experiments are run, record the exact commands and conclusions in both `feasibility_report.md` and `execution_report.md`.

## Risks
- Exact synthetic subtraction may look good while realistic CST convention mismatch still fails.
- The high-Q fundamental can leave a long-lived residual from very small frequency, Q, or R/Q errors.
- Finite wake length can create spectral leakage or ringing that looks like HOM structure.
- Coarse wake-to-impedance grids may miss narrow HOM peaks even when residual wake is correct.
- A research spike can accidentally become implementation work; keep output limited to reports.

## Escalation Conditions
Escalate if:

- The required synthetic experiment cannot be performed without modifying production code.
- Existing utilities expose inconsistent sign, scale, or phase conventions that cannot be resolved from code/tests.
- The required regression test cannot run in the local environment.
- Direction 2 feasibility depends on assumptions that require live CST/exported CST data unavailable in this phase.
- The local agent needs to modify files outside the allowed P04 report files.
