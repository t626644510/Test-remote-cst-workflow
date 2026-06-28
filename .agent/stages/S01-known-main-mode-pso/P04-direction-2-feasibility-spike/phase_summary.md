# Phase Summary: P04-direction-2-feasibility-spike

## Status
PHASE_ACCEPTED

## Branch
`phase/S01-P04-direction-2-feasibility-spike`

## Commits
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
- `c4b45ba` Web acceptance review

## Summary
P04 executed the Direction 2 no-CST feasibility spike and is accepted after Codex-authorized final report cleanup.

The final report provides complete, copy-pasteable PowerShell here-string commands for all three synthetic experiment groups and records that they were re-run and verified against the numerical tables. The phase remained report-only and did not modify production code, tests, CST API, shared core, wakefield objective, scalarization, main, or stage branches.

The accepted scientific conclusion is `CONDITIONAL-GO` for Direction 2: full-wake fundamental subtraction is feasible only if the CST fundamental frequency can be determined to within `<0.1 MHz` and CST sign/scale conventions match the resonator model.

## Main Findings
- Exact synthetic fundamental subtraction recovered the HOM-only residual to floating-point precision.
- Fundamental frequency error is the dominant risk for Direction 2.
- The high-Q fundamental (`Q=36500`) does not decay appreciably over practical wake lengths.
- Q perturbation is comparatively minor in the tested ranges.
- R/Q perturbation creates linear residual amplitude error and must be bounded.
- Finite wake truncation creates spectral leakage; Hann windowing improves residual impedance reconstruction but changes amplitudes.
- Any production Direction 2 work requires CST convention validation for sign, scale, bunch form factor, time zero, fundamental frequency, R/Q definition, loading/Q, and numerical noise floor.

## Tests
Reported regression command:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Reported result:

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
P04 is complete and accepted.

Next step: return to Codex for stage-level review / stage acceptance decision. Direction 2 should not be implemented until the accepted CST convention checklist is satisfied with exported or live CST data.
