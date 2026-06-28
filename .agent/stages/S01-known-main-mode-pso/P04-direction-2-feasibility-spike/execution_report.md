# Execution Report: S01-P04-direction-2-feasibility-spike

## Summary
Executed the P04 no-CST research spike to evaluate Direction 2 feasibility (full-wake fundamental-mode subtraction for HOM recovery). Ran synthetic experiments with a known fundamental (499.8 MHz, Q=36500, R/Q=208.6 ohm) plus two HOMs. Tested exact subtraction, perturbed subtraction (frequency, Q, R/Q), finite wake length effects, and windowing/truncation impacts on wake-to-impedance reconstruction. Produced a quantitative feasibility report with a `CONDITIONAL-GO` recommendation.

## Changed Files
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md` (new)
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md` (this file)

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| feasibility_report.md written | PASS | Report exists in phase folder |
| No production code, tests, CST API, or scalarization modified | PASS | Only report files changed |
| No-CST synthetic wake with fund + multiple HOMs | PASS | 3-mode synthetic: fund + HOM1 + HOM2 |
| Exact subtraction evaluated | PASS | Perfect match (1e-16 float precision) |
| Frequency/Q/RQ perturbation sensitivity quantified | PASS | 3 tables with RMS, correlation, normalized error |
| Finite wake length / windowing effects evaluated | PASS | 6 lengths (0.5-10m), Hann window comparison |
| Wake-to-impedance reconstruction assessed | PASS | Both windowed and unwindowed, peak recovery analyzed |
| Clear recommendation | PASS | CONDITIONAL-GO with explicit conditions |
| CST convention checks listed | PASS | 8-item checklist |
| Regression tests pass | PASS | 38 passed in 0.55s (re-run 2026-06-28) |

## Synthetic Experiment Commands

All experiments were run as inline Python scripts using the PowerShell here-string pattern:
```powershell
@'<python-code>'@ | py -
```

The three complete commands are reproduced verbatim in the `Commands Run` section of `feasibility_report.md`. Each command was re-run and verified to produce output matching the numerical tables in the Evidence sections of the feasibility report.

Command verification results (re-run 2026-06-28):
- **Command 1** (exact subtraction + perturbations): All exact subtraction, frequency, Q, and R/Q table values matched the report within printed precision.
- **Command 2** (decay + freq-vs-length): All envelope and residual RMS values matched.
- **Command 3** (wake length sweep + Hann window): Wake length HOM peak error values, spurious peak counts, and windowing reduction effects matched.

## Test Results

```
py -m pytest tests/workflows/test_workflow2_pso_wake_fit.py
collected 38 items
38 passed in 0.55s (re-run 2026-06-28)
```

All 38 existing regression tests pass. No test files were modified.

## Known Issues
- No CST data was available; all results are from perfectly known synthetic data (model-mismatch error is zero by construction).
- The synthetic wake uses the same resonator model as the analysis code, so model-form errors that would exist with real CST data are absent.

## Scope Deviations
None. Only the two allowed report files were modified. No production code, tests, CST API, `src/cst_optimization/`, scalarization, or stage plan files were touched.

## Commitment
No production code was committed. Only the feasibility report and this execution report were added to version control.

## Commit

Original report commit: `24eb83e76f6969c1fc2208eeebb86a47c3332505`
Follow-up fix commit: `5933d81`

## Push
- Remote: `origin`
- Branch: `phase/S01-P04-direction-2-feasibility-spike`
- Result: pushed (`4ff11f7..5933d81`) to `origin/phase/S01-P04-direction-2-feasibility-spike`

## Ready for Review
YES

## Blockers
None.
