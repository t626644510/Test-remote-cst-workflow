# Phase Review: P04-direction-2-feasibility-spike

## Verdict
PHASE_ACCEPTED

## Branch And Commits
- Branch: `phase/S01-P04-direction-2-feasibility-spike`
- Commits reviewed:
  - `e22ab36` Web phase plan
  - `24b600e` Web executor prompt
  - `24eb83e` initial local feasibility and execution reports
  - `6b93e0e` Web review requiring report-only follow-up
  - `4ff11f7` Web follow-up prompt
  - `5933d81` local follow-up report update
  - `8defcd1` local follow-up commit/push field update
  - `6fc3032` Web escalation review
  - `272c1f7` Web escalation summary
  - `8330632` Codex-authorized final report-only reproducibility fix

## Review Summary
P04 is accepted after the Codex-authorized final report-only fix.

Codex required one final report-only correction and did not relax the evidence standard. The final local commit `8330632` replaced abbreviated command evidence with complete, copy-pasteable PowerShell here-string commands in `feasibility_report.md` and updated `execution_report.md` with verification evidence.

The phase remains a no-CST research spike. No production code, tests, CST API, shared core, wakefield objective, scalarization, main, or stage branch changes were observed.

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| Feasibility report exists | PASS | `feasibility_report.md` is present in the P04 phase folder. |
| Execution report exists | PASS | `execution_report.md` is present in the P04 phase folder. |
| Scope stayed report-only | PASS | Diff from P03 shows only P04 `.agent` workflow/report files. |
| Synthetic wake includes fundamental plus HOMs | PASS | Mode table includes fundamental, HOM1, and HOM2. |
| Exact subtraction evaluated | PASS | Report records floating-point-level exact subtraction. |
| Frequency/Q/RQ sensitivity quantified | PASS | Report includes frequency, Q, and R/Q perturbation tables. |
| Finite wake/windowing evaluated | PASS | Report covers wake length, truncation leakage, Hann windowing, and reconstruction behavior. |
| Wake-to-impedance reconstruction assessed | PASS | Report assesses unwindowed and windowed residual reconstruction. |
| Recommendation given | PASS | Recommendation is `CONDITIONAL-GO`. |
| CST preconditions listed | PASS | Report includes the required CST convention checklist. |
| Regression passes | PASS | Execution report records `38 passed in 0.55s`. |
| Complete command evidence recorded | PASS | Final report contains three complete here-string commands and no omitted loop bodies in the command evidence. |

## Scope Compliance
PASS.

Compared with `phase/S01-P03-diagnostics-and-stage-validation`, the P04 branch changes are limited to P04 `.agent` files, including phase docs, Codex decision/prompt, reports, reviews, and summary.

## Tests Reviewed
Reported command:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Reported result:

```text
38 passed in 0.55s
```

The execution report also states the three synthetic experiment commands were re-run and verified to reproduce the numerical tables.

## Scientific Findings Accepted
- Exact synthetic fundamental subtraction recovers the HOM-only residual to floating-point precision.
- Fundamental frequency error is the dominant risk; the report recommends `<0.1 MHz` accuracy before production Direction 2 work.
- Q perturbation is comparatively small over the tested wake lengths because `Q=36500` decays very slowly.
- R/Q perturbation creates linear residual amplitude error and must be bounded.
- The high-Q fundamental does not decay appreciably over practical wake lengths, so extending wake length cannot solve main-mode subtraction error.
- Finite wake truncation creates spectral leakage; Hann windowing improves residual impedance reconstruction but changes amplitudes.
- Any production Direction 2 implementation must be gated by CST sign, scale, bunch form factor, time-zero, fundamental frequency, R/Q definition, loading/Q, and numerical noise-floor checks.

## Review Notes
The execution report's commit/push section still names `5933d81` as the follow-up fix commit, but Web Phase Review independently verified the final Codex-authorized commit `8330632` and the branch diff. This is not blocking because Codex's final completion standard focused on command completeness, rerun verification, and report-only scope.

## Findings Or Follow-up
None for P04.

Future work must not implement Direction 2 until the CST convention checklist is satisfied with exported or live CST data.

## Result
P04-direction-2-feasibility-spike is accepted.

Next allowed step: return to Codex for stage-level review / stage acceptance decision.
