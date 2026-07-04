# Execution Report: S01-P05-known-mode-calibration-stability

## Summary

Ran a report-only diagnostic replay on existing long-wake Workflow 2 CST data
to evaluate whether the fixed known fundamental mode needs deterministic
calibration before HOM PSO fitting.

No production code, tests, CST API, `src/cst_optimization/**`, scalarization
logic, live-CST solve, smoke run, or geometry rebuild was changed or run.

## Changed Files

- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/known_mode_calibration_stability_report.md`
- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/execution_report.md`

## Local-Only Scratch Outputs

Generated but not committed:

- `analysis_outputs/wf2_known_mode_calibration_stability/run_calibration_stability.py`
- `analysis_outputs/wf2_known_mode_calibration_stability/summary.json`
- `analysis_outputs/wf2_known_mode_calibration_stability/calibration_sweep.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/q_sensitivity.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/rq_convention_recheck.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/fixed_prior_rq_recheck.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/hom_pso_ensemble.csv`

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| Existing CST long-wake data is reused; no new CST solve is run. | PASS | Read `D:\workflow2\Before_rebuild_backup\F2W.cst` result trees only. |
| Runs `1`, `5`, `10`, and `20` are covered. | PASS | Representative tables include runs `1`, `5`, `10`, `20`. |
| All available runs `1..20` are summarized if practical. | PASS | Calibration sweep covers all 20 runs and 8 fit starts. |
| Test 1 deterministic calibration sweep is executed. | PASS | Report includes frequency/RQ sweep tables and all-run statistics. |
| Test 2 Q sensitivity scan is executed. | PASS | Report includes Q grid results for representative runs and starts. |
| Test 3 fit-start stability map is executed. | PASS | Report includes starts `0`, `0.5`, `1`, `2`, `5`, `10`, `20`, `40 m`. |
| Test 4 HOM PSO ensemble is executed. | PASS | Report includes calibrated HOM PSO ensemble over starts `1 m` and `2 m` with four seeds. |
| Report distinguishes fixed known-mode production behavior from diagnostic calibration. | PASS | Report explicitly states current known fields remain fixed and `frequency_tolerance_hz` only filters peaks. |
| Report treats reconstructed `|Z|` as secondary. | PASS | Report uses wake-domain gates as primary and impedance ratios as secondary envelope diagnostics. |
| No production code or test files are modified. | PASS | Only two allowed report files are staged for commit. |
| Regression test result is recorded. | PASS | `py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py` passed. |

## Commands Run

Branch synchronization:

```powershell
git status --short --branch
git fetch origin
git pull --ff-only origin phase/S01-P05-known-mode-calibration-stability
```

Diagnostic replay:

```powershell
py analysis_outputs\wf2_known_mode_calibration_stability\run_calibration_stability.py
```

Regression:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

## Test Results

Diagnostic replay completed successfully.

Summary:

- Data source: `D:\workflow2\Before_rebuild_backup\F2W.cst`
- Run IDs used: `1..20`
- Representative runs: `1`, `5`, `10`, `20`
- Fit starts: `0`, `0.5`, `1`, `2`, `5`, `10`, `20`, `40 m`
- Frequency sweep: `499.0 MHz` to `501.0 MHz`, `25 kHz` step
- Q grid: `10000`, `20000`, `36500`, `60000`, `100000`
- HOM PSO ensemble: starts `1 m` and `2 m`, four deterministic seeds

Regression result:

```text
38 passed in 0.72s
```

## Main Findings

- The previous factor-of-two R/Q convention finding was reproduced:
  `R/Q = 208.6 ohm` over-predicts the known fundamental wake amplitude by
  about 2x in the current implementation convention.
- `R/Q = 104.3 ohm` is the correct current baseline convention, but the
  deterministic scalar projection across these data prefers effective
  `R/Q` near `100.6 ohm`.
- Best calibrated frequency across all runs/starts lies in
  `499.775 MHz` to `500.125 MHz`.
- Q is weakly identifiable and should remain fixed to the prior
  `Q = 36500`.
- A deterministic frequency plus scalar `R/Q` calibration layer is recommended
  for future long-wake longitudinal known-mode use.
- `2 m` is the recommended conservative current HOM PSO start; `1 m` remains
  useful for review, and `5-10 m` can be used as secondary stability checks.
- Single-run reconstructed `|Z|` should remain non-authoritative; use ensemble
  envelopes as secondary diagnostics.

## Known Issues

- No production calibration helper was implemented in this phase by design.
- HOM PSO ensemble used a local scratch log-space PSO helper to avoid adding
  dependencies or modifying production code.
- Full reconstructed impedance curves were not committed; only report tables
  and local scratch summaries were produced.

## Scope Deviations

None in committed files.

Local-only scratch files were created under the allowed directory:

```text
analysis_outputs/wf2_known_mode_calibration_stability/
```

They are intentionally untracked and not committed.

## Commit

Commit containing this report: to be created by the local execution agent.

## Push

- Remote: `origin`
- Branch: `phase/S01-P05-known-mode-calibration-stability`
- Result: pending at report-write time

## Ready for Review

YES after the two allowed report files are committed and pushed.

## Blockers

None.
