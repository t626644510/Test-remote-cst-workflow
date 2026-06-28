# Phase Review: P04-direction-2-feasibility-spike

## Verdict
ESCALATE_TO_CODEX

## Branch And Commits
- Branch: `phase/S01-P04-direction-2-feasibility-spike`
- Commits reviewed:
  - `e22ab36` Web phase plan
  - `24b600e` Web executor prompt
  - `24eb83e` Local feasibility and execution reports
  - `6b93e0e` Web review requiring report-only follow-up
  - `4ff11f7` Web follow-up prompt
  - `5933d81` Local follow-up report update
  - `8defcd1` Local follow-up commit/push field update

## Review Summary
P04 remains scientifically useful and appears scope-compliant, but it cannot be marked `PHASE_ACCEPTED` by Web Phase Review because the required reproducibility evidence is still incomplete after follow-up.

The follow-up fixed the execution-report commit, push, and regression-test evidence. The report now records:

- Original report commit: `24eb83e76f6969c1fc2208eeebb86a47c3332505`.
- Follow-up fix commit: `5933d81`.
- Push result: `4ff11f7..5933d81` pushed to `origin/phase/S01-P04-direction-2-feasibility-spike`.
- Regression rerun: `38 passed in 0.55s`.

However, the follow-up did not fully satisfy the requested exact inline-command evidence. The `feasibility_report.md` `Commands Run` section still contains abbreviated command bodies with ellipses and comments such as:

- `# ... same pattern for Q and R/Q perturbations ...`
- `# ... generate true and perturbed fundamental, compute residual RMS ...`
- `# ... generate full wake + residual at multiple lengths ...`
- `# ... apply Hann window, compute impedance, detect peaks ...`

The `execution_report.md` also summarizes commands with `...` and points to the feasibility report for the full command body, but that full body is not actually present for all experiments.

Because this is the second review failure for the same phase, Web Phase Review should not issue another follow-up prompt. Per the workflow escalation rule, this phase is escalated to Codex for judgment on whether to accept the spike despite incomplete command reproducibility, relax the exact-command requirement, or require one final report-only correction.

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `feasibility_report.md` is written in the P04 phase folder | PASS | Report exists and contains the Direction 2 feasibility analysis. |
| `execution_report.md` is written using the shared report structure | PASS | Commit, push, blocker, and test fields are now filled. |
| Phase remains a research spike and does not modify production code/tests/CST/scalarization | PASS | Compared against P03 branch; changes are limited to P04 `.agent` files. |
| No-CST synthetic wake with known fundamental plus multiple HOMs | PASS | Synthetic table includes fundamental plus HOM1 and HOM2. |
| Exact fundamental subtraction evaluated against HOM-only truth | PASS | Exact subtraction residual reaches floating-point precision. |
| Frequency, Q, and R/Q perturbation sensitivity quantified | PASS | Report includes separate quantitative tables for frequency, Q, and R/Q perturbations. |
| Finite wake length and windowing/truncation effects evaluated | PASS | Report discusses finite wake length, spectral leakage, and Hann window behavior. |
| Wake-to-impedance reconstruction behavior assessed | PASS | Report compares unwindowed and Hann-windowed residual reconstruction. |
| Clear `GO`, `NO-GO`, or `CONDITIONAL-GO` recommendation | PASS | Recommendation is `CONDITIONAL-GO`. |
| Concrete conditions before production Direction 2 implementation | PASS | Report includes an 8-item CST convention checklist. |
| Required regression command passes or blocker documented | PASS | Execution report records `38 passed in 0.55s`. |
| Exact inline Python synthetic experiment commands recorded | FAIL | Feasibility/execution reports still use abbreviated command bodies with `...` and omitted loops/logic. |

## Scope Compliance
PASS.

Reviewed diff from `phase/S01-P03-diagnostics-and-stage-validation` to `phase/S01-P04-direction-2-feasibility-spike` shows only P04 `.agent` files were added or updated:

- `phase_plan.md`
- `executor_prompt.md`
- `codex_phase_plan_review.md`
- `feasibility_report.md`
- `execution_report.md`
- `phase_review.md`
- `followup_prompt.md`

No production code, tests, CST API, `src/cst_optimization/`, scalarization, `main`, or `stage/*` changes were observed.

## Tests Reviewed
Reported command:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Reported result:

```text
38 passed in 0.55s
```

## Scientific Findings Reviewed
The scientific result is adequate for a research spike, pending Codex judgment on reproducibility evidence:

- Exact synthetic fundamental subtraction recovers HOM-only wake to floating-point precision.
- Fundamental frequency error is the dominant risk; the report recommends `<0.1 MHz` accuracy before production Direction 2 work.
- Q perturbation is comparatively negligible for the tested wake lengths because Q=36500 decays extremely slowly.
- R/Q perturbation creates linear amplitude residuals and is manageable only within bounded error.
- The fundamental does not decay appreciably over practical wake lengths, so extending wake length cannot solve fundamental subtraction error.
- Finite wake truncation creates spectral leakage; Hann windowing improves residual impedance reconstruction but reduces peak amplitudes.
- The report correctly gates production Direction 2 behind CST sign/scale/phase/frequency/Q/RQ/noise validation.

## Findings Or Follow-up
No further Web-generated follow-up prompt is issued because this is the second review failure for the same phase.

Codex should decide one of:

1. Accept P04 as scientifically sufficient despite incomplete exact-command reproduction.
2. Require one final report-only correction with full copy-pasteable inline commands or a committed artifact-free command transcript.
3. Relax the exact-command evidence requirement for this research spike and document why summary-level command evidence is sufficient.

## Result
Escalated to Codex. P04 is not marked `PHASE_ACCEPTED` by Web Phase Review.
