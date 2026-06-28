# Phase Summary: P04-direction-2-feasibility-spike

## Status
ESCALATED

## Branch
`phase/S01-P04-direction-2-feasibility-spike`

## Commits
- `e22ab36` Web phase plan
- `24b600e` Web executor prompt
- `24eb83e` Local feasibility and execution reports
- `6b93e0e` Web review requiring report-only follow-up
- `4ff11f7` Web follow-up prompt
- `5933d81` Local follow-up report update
- `8defcd1` Local follow-up commit/push field update
- `6fc3032` Web follow-up review escalation

## Summary
P04 executed the Direction 2 no-CST feasibility spike and produced a useful scientific conclusion: `CONDITIONAL-GO` for full-wake fundamental subtraction, gated by accurate CST fundamental frequency and sign/scale convention validation.

The phase remained scope-compliant. No production code, tests, CST API, `src/cst_optimization/`, scalarization, `main`, or `stage/*` files were modified.

Web Phase Review did not accept the phase because the required exact inline Python command evidence remains incomplete after follow-up. The reports now contain a `Commands Run` section, fixed commit/push fields, and rerun regression result, but some command bodies still contain ellipses and omitted logic rather than fully copy-pasteable commands.

## Main Findings
- Exact synthetic fundamental subtraction recovered the HOM-only residual to floating-point precision.
- Fundamental frequency error is the dominant risk for Direction 2.
- The report recommends `<0.1 MHz` CST fundamental-frequency accuracy before production implementation.
- The high-Q fundamental (`Q=36500`) does not decay appreciably over practical wake lengths, so extending wake length cannot remove the main-mode risk.
- Q perturbation is comparatively minor in the tested ranges.
- R/Q perturbation creates linear residual amplitude error and must be bounded.
- Finite wake truncation creates spectral leakage; Hann windowing improves residual impedance reconstruction but changes amplitudes.
- Any production Direction 2 work requires CST convention validation for sign, scale, bunch form factor, time zero, fundamental frequency, R/Q definition, loading/Q, and numerical noise floor.

## Tests
Reported regression command:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Reported result after follow-up:

```text
38 passed in 0.55s
```

## Scope Notes
Intentional non-changes:

- No Direction 2 production code.
- No CST API changes.
- No `src/cst_optimization/` changes.
- No `workflows/rfgun_hom_antenna/pso_wake_fit.py` changes.
- No `workflows/rfgun_hom_antenna/wakefield_objective.py` changes.
- No test-file changes.
- No scalarization semantic changes.
- No `main` or `stage/*` updates.

## Follow-up
Escalated to Codex because the same phase failed Web Phase Review twice.

Codex should decide whether to:

1. Accept P04 as scientifically sufficient despite incomplete exact-command reproducibility.
2. Require one final report-only correction with full copy-pasteable commands.
3. Relax the exact-command evidence requirement for this research spike and document why summary-level command evidence is sufficient.
