# Phase Plan: P05-known-mode-calibration-stability

## Status
DRAFT

## Parent Stage
S01-known-main-mode-pso

## Phase Branch
`phase/S01-P05-known-mode-calibration-stability`

## Phase Goal
Use existing long-wake CST data to evaluate whether Workflow 2 known-mode PSO fitting can produce stable, reproducible scientific outputs when the externally supplied fundamental-mode parameters are treated as uncertain priors rather than perfect constants.

This is a diagnostic / analysis phase. It must not run new CST simulations and must not implement production Direction 2 code.

## Background
P01-P03 implemented Direction 1: known longitudinal modes can be configured through `obj_params.pso_fit.known_modes`, converted into a fixed wake contribution, excluded from the unknown PSO peak list, and reported separately from fitted unknown HOMs.

P04 found Direction 2 is only conditionally feasible. The dominant risk is fundamental-mode mismatch, especially frequency mismatch. A later local replay report using existing long-wake data found that wake-domain tail fitting can be very good while reconstructed `|Z|` can vary substantially with fit start. The same replay also found a likely R/Q convention mismatch: `R/Q = 208.6 ohm` over-predicts the fixed known-mode wake amplitude by about a factor of two, while `R/Q = 104.3 ohm` is more consistent with the CST wake tail.

The current implementation treats all known-mode fields as fixed inputs:

- `frequency_hz` is fixed. `frequency_tolerance_hz` only filters detected peaks near the known mode; it does not fit or update the known frequency.
- `q` is fixed.
- `r_over_q_ohm` is fixed.

This phase tests whether a separate, deterministic known-mode calibration layer is needed before HOM PSO fitting.

## Non-goals
- Do not run new CST solves, smoke runs, geometry rebuilds, or live-CST simulations.
- Do not implement production Direction 2.
- Do not modify CST API or CST result-reading contracts.
- Do not modify `src/cst_optimization/**`.
- Do not modify `workflows/rfgun_hom_antenna/pso_wake_fit.py` or `workflows/rfgun_hom_antenna/wakefield_objective.py` unless explicitly escalated later.
- Do not change scalarization semantics.
- Do not make reconstructed `|Z|` the primary pass/fail target.
- Do not commit local plots, scratch scripts, or large analysis outputs unless explicitly requested.

## Allowed Scope
Files that may be created or updated by the local agent:

- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/known_mode_calibration_stability_report.md`
- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/execution_report.md`

Local-only scratch/output directory, not committed unless requested:

- `analysis_outputs/wf2_known_mode_calibration_stability/`

Read-only code/data inspection is allowed for:

- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `workflows/rfgun_hom_antenna/wakefield_objective.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/known_mode_wake_tail_replay_report.md`
- existing local CST result data under `D:\workflow2\Before_rebuild_backup\`

## Data To Reuse
Use existing data only:

- `D:\workflow2\Before_rebuild_backup\F2W.cst`
- `D:\workflow2\Before_rebuild_backup\F2W`

Primary longitudinal result paths from the replay report:

- `1D Results\Particle Beams\ParticleBeam1\Wake potential\Z`
- `1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z`
- `1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)`

Use available run IDs from the existing result tree. The replay report observed runs `1..20`; at minimum cover the representative runs already studied: `1`, `5`, `10`, and `20`.

## Key Principle
Do not define "best" as a single reconstructed `|Z|` curve closest to CST impedance.

For this phase, reconstructed `|Z|` is a secondary consistency view. The primary scientific target is stable wake-domain explanation and stable calibrated known-mode parameters. A single reconstructed impedance curve can be misleading because wake-tail resonator fits and CST sampled impedance include different finite-window, solver, and post-processing effects.

## Test 1: Deterministic Known-Mode Calibration Sweep
Purpose: determine whether the supplied known fundamental parameters should be calibrated before HOM fitting.

Procedure:

1. For each selected CST run and fit start, construct the target wake tail on the fit grid.
2. Use the eigenmode baseline as the prior:
   - `frequency_hz = 499.8e6`
   - `q = 36500`
   - test both `r_over_q_ohm = 208.6` and `104.3` where useful.
3. Sweep fundamental frequency over a bounded grid around the prior and observed sampled peak, for example:
   - coarse: `499.0 MHz .. 501.0 MHz` in `25 kHz` or `50 kHz` steps;
   - refine around the best region if needed.
4. For each frequency, synthesize the known-mode wake with fixed `Q` and baseline `R/Q`.
5. Compute the best scalar projection:

   ```text
   scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)
   effective_r_over_q = baseline_r_over_q * scale
   ```

6. Record wake-domain residual metrics for the calibrated known-mode-only fit:
   - residual RMS;
   - normalized residual error;
   - wake correlation;
   - fitted scale;
   - effective `R/Q`;
   - best frequency.

Expected output:

- heatmap or table of `best_f`, `effective_r_over_q`, residual RMS, and wake correlation by run and fit start;
- stability range for best frequency and effective R/Q;
- determination of whether `104.3 ohm` should be used as the current module convention baseline.

## Test 2: Q Sensitivity Scan
Purpose: decide whether Q is identifiable from the available wake tail or should remain a fixed prior.

Procedure:

1. Use the best frequency / effective R/Q from Test 1, or a representative calibrated pair.
2. Sweep Q over a bounded prior range, for example:
   - `[10000, 20000, 36500, 60000, 100000]`, or
   - `[0.5 Q0, 0.75 Q0, Q0, 1.25 Q0, 1.5 Q0, 2 Q0]`.
3. For each Q, optionally recompute the scalar R/Q projection and residual metrics.
4. Plot or tabulate residual RMS versus Q.

Expected interpretation:

- If the residual curve is flat, Q is not identifiable and should remain fixed to the eigenmode or a documented prior.
- If the residual curve is sharp and stable across runs / fit starts, Q calibration may be considered in a later phase.

## Test 3: Fit-Start Stability Map
Purpose: stop treating fit start as a single hidden hyperparameter and identify stable start regions.

Procedure:

1. Use the existing start grid unless data quality suggests a smaller sweep:
   - `0`, `0.5`, `1`, `2`, `5`, `10`, `20`, `40 m`.
2. For each run and fit start, run Test 1 calibration.
3. Record:
   - calibrated `best_f`;
   - calibrated `effective_r_over_q`;
   - known-only residual RMS / normalized error / correlation;
   - whether early structure or late truncation appears to dominate.
4. Define acceptable start windows using relative and absolute criteria, for example:
   - residual RMS <= `1.05 * min_residual_rms_for_run`;
   - wake correlation above a configured threshold;
   - `best_f` within a stable band;
   - effective `R/Q` within a stable band.

Expected output:

- per-run acceptable fit-start intervals;
- recommended conservative default start for long-wake longitudinal known-mode use, if one exists;
- clear statement if start choice is run-dependent and cannot be hidden behind one global default.

## Test 4: HOM PSO Ensemble After Known-Mode Calibration
Purpose: distinguish stable wake-tail explanation from non-unique HOM parameter / impedance reconstruction.

Procedure:

1. For each selected run and acceptable fit start, subtract or include the calibrated known fundamental using the current fitter's known-mode pathway.
2. Run HOM PSO multiple times with different deterministic seeds or optimizer settings where supported.
3. Record for each run:
   - wake-domain residual RMS;
   - normalized error;
   - wake correlation;
   - selected peak frequencies;
   - fitted HOM Q and R/Q;
   - reconstructed `|Z|` curve.
4. Summarize ensemble stability:
   - mean / std of wake metrics;
   - mode parameter spread;
   - impedance envelope `mean ± 2 sigma` or percentile bands;
   - CST sampled `|Z|` overlay as a secondary consistency view only.

Expected output:

- whether HOM decomposition is stable under equivalent seeds;
- whether reconstructed impedance is a stable diagnostic envelope;
- whether single-run reconstructed `|Z|` should be forbidden as a pass/fail criterion.

## Metrics And Proposed Gates
Primary metrics:

- known-mode-only residual RMS;
- total wake residual RMS after HOM PSO;
- normalized error;
- wake correlation;
- calibrated `best_f` stability;
- effective `R/Q` stability;
- mode parameter spread across seeds.

Secondary metrics:

- reconstructed `|Z|` envelope width;
- CST sampled `|Z|` overlap with envelope;
- peak-location agreement where the finite wake length makes resolution meaningful.

Do not gate acceptance solely on absolute reconstructed `|Z|` matching CST sampled impedance.

## Required Report Contents
Write:

`.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/known_mode_calibration_stability_report.md`

The report should include:

1. Data sources and run IDs used.
2. Result tree paths and units used.
3. Reproduction notes for the previous R/Q convention finding.
4. Test 1 calibration sweep results.
5. Test 2 Q sensitivity results.
6. Test 3 fit-start stability map.
7. Test 4 HOM PSO ensemble results.
8. Proposed default settings for current long-wake use.
9. Clear recommendation for whether a production known-mode calibration layer is needed.
10. Explicit statement that reconstructed `|Z|` remains diagnostic unless later validated.
11. Data gaps and assumptions.
12. Suggested next phase if productionization is justified.

## Required Validation
If no production code is changed, still run the current regression when practical:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

If the local CST data cannot be opened in the current environment, document the blocker and do not fabricate results.

## Acceptance Criteria
- [ ] Existing CST long-wake data is reused; no new CST solve is run.
- [ ] The four tests above are executed or a clear blocker is documented.
- [ ] The report distinguishes fixed known-mode use from calibrated known-mode analysis.
- [ ] The report states whether `frequency_hz`, `q`, and `r_over_q_ohm` should remain fixed, be calibrated, or be treated as uncertainty intervals.
- [ ] The report provides recommended fit-start policy for current long-wake use.
- [ ] The report treats reconstructed `|Z|` as secondary unless evidence supports a stronger role.
- [ ] No production code or test files are modified.
- [ ] Regression test result is recorded, or the reason for not rerunning is documented.

## Escalation Conditions
Escalate if:

- Existing CST data is unavailable or unreadable.
- The required analysis needs production code changes.
- Calibration results are inconsistent across runs and cannot support any stable workflow recommendation.
- The evidence contradicts the accepted P04 conclusion or implies Direction 1 behavior is scientifically unsafe without immediate changes.
