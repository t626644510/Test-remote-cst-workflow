# Phase Review: P04-direction-2-feasibility-spike

## Verdict
NEEDS_FOLLOWUP

## Branch And Commits
- Branch: `phase/S01-P04-direction-2-feasibility-spike`
- Commits reviewed:
  - `e22ab36` Web phase plan
  - `24b600e` Web executor prompt
  - `24eb83e` Local feasibility and execution reports

## Review Summary
P04 is technically close and the feasibility report contains the core scientific evidence requested by the phase plan.

The phase stayed within `.agent` workflow/report files and did not modify production code. The report gives a clear `CONDITIONAL-GO` recommendation for Direction 2, supported by no-CST synthetic experiments covering exact subtraction, frequency/Q/RQ perturbation sensitivity, finite wake length, windowing, and wake-to-impedance reconstruction behavior.

However, the phase cannot be accepted yet because two required evidence fields are incomplete:

1. The phase plan and executor prompt required exact inline Python synthetic experiment commands to be recorded. The execution report currently uses abbreviated placeholders such as `py -c "..."`, and the feasibility report does not include an exact commands section.
2. The execution report's commit and push fields are stale placeholders (`<will be filled after commit>` and `to be pushed after commit`) even though commit `24eb83e` was pushed.

These are documentation/evidence issues only. No production follow-up is requested.

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `feasibility_report.md` is written in the P04 phase folder | PASS | Report exists and contains the Direction 2 feasibility analysis. |
| `execution_report.md` is written using the shared report structure | PARTIAL | Report exists, but commit/push fields are stale placeholders. |
| Phase remains a research spike and does not modify production code/tests/CST/scalarization | PASS | Compared against P03 branch; changes are limited to P04 `.agent` files. |
| No-CST synthetic wake with known fundamental plus multiple HOMs | PASS | Synthetic table includes fundamental plus HOM1 and HOM2. |
| Exact fundamental subtraction evaluated against HOM-only truth | PASS | Exact subtraction residual reaches floating-point precision. |
| Frequency, Q, and R/Q perturbation sensitivity quantified | PASS | Report includes separate quantitative tables for frequency, Q, and R/Q perturbations. |
| Finite wake length and windowing/truncation effects evaluated | PASS | Report discusses finite wake length, spectral leakage, and Hann window behavior. |
| Wake-to-impedance reconstruction behavior assessed | PASS | Report compares unwindowed and Hann-windowed residual reconstruction. |
| Clear `GO`, `NO-GO`, or `CONDITIONAL-GO` recommendation | PASS | Recommendation is `CONDITIONAL-GO`. |
| Concrete conditions before production Direction 2 implementation | PASS | Report includes an 8-item CST convention checklist. |
| Required regression command passes or blocker documented | PASS | Execution report records `38 passed in 0.53s`. |
| Exact inline Python synthetic experiment commands recorded | FAIL | Execution report uses abbreviated `py -c "..."` placeholders; feasibility report lacks an exact command section. |

## Scope Compliance
PASS.

Reviewed diff from `phase/S01-P03-diagnostics-and-stage-validation` to `phase/S01-P04-direction-2-feasibility-spike` shows only P04 `.agent` files were added:

- `phase_plan.md`
- `executor_prompt.md`
- `codex_phase_plan_review.md`
- `feasibility_report.md`
- `execution_report.md`

No production code, tests, CST API, `src/cst_optimization/`, scalarization, `main`, or `stage/*` changes were observed.

## Tests Reviewed
Reported command:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Reported result:

```text
38 passed in 0.53s
```

## Scientific Findings Reviewed
Accepted as sufficient for a research-spike result, pending evidence cleanup:

- Exact synthetic fundamental subtraction recovers HOM-only wake to floating-point precision.
- Fundamental frequency error is the dominant risk; the report recommends `<0.1 MHz` accuracy before production Direction 2 work.
- Q perturbation is comparatively negligible for the tested wake lengths because Q=36500 decays extremely slowly.
- R/Q perturbation creates linear amplitude residuals and is manageable only within bounded error.
- The fundamental does not decay appreciably over practical wake lengths, so extending wake length cannot solve fundamental subtraction error.
- Finite wake truncation creates spectral leakage; Hann windowing improves residual impedance reconstruction but reduces peak amplitudes.
- The report correctly gates production Direction 2 behind CST sign/scale/phase/frequency/Q/RQ/noise validation.

## Findings Or Follow-up
Required follow-up:

1. Update `feasibility_report.md` with a `Commands Run` section that records the exact inline Python commands used for:
   - exact and perturbed subtraction,
   - finite wake length / windowing / reconstruction,
   - fundamental decay and frequency-error-vs-length checks.
2. Update `execution_report.md` so the command evidence is exact rather than abbreviated.
3. Replace the execution report commit placeholder with `24eb83e76f6969c1fc2208eeebb86a47c3332505` or the follow-up commit hash, as appropriate.
4. Replace the push placeholder with the actual pushed result for `origin phase/S01-P04-direction-2-feasibility-spike`.
5. Do not modify production code or tests.

## Result
P04 is not accepted yet. Proceed with a report-only follow-up on the same branch.
