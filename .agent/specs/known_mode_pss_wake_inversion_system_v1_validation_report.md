# Known-mode PSO Wake Inversion System Spec v1.0 Validation Report

## Executive Conclusion

The spec validates as `PASS WITH WARNINGS` under the revised wake-domain-first
criteria.

Production direction is scientifically reasonable if the system keeps a
deterministic calibration layer for fundamental frequency and scalar effective
`R/Q`, keeps known-mode Q fixed to the prior, and treats HOM PSO as an ensemble
inversion rather than a single-run modal measurement.

The main warning is not the wake fit. The wake-domain metrics are stable enough
for selected starts. The warning is interpretability: individual HOM Q/RQ
values and reconstructed impedance envelopes remain seed- and model-sensitive,
so they should be reported with uncertainty and must not become primary
pass/fail targets.

## Scope

This report validates the Known-mode PSO Wake Inversion System Spec v1.0 using
existing Workflow 2 long-wake CST data only.

No new CST simulation, smoke run, geometry rebuild, production-code change,
CST API change, PSO implementation change, or scalarization change was
performed.

## Inputs

Dataset:

```text
D:\workflow2\Before_rebuild_backup\F2W.cst
```

Result paths:

- `1D Results\Particle Beams\ParticleBeam1\Wake potential\Z`
- `1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z`
- `1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)`

Runs:

- detailed validation: `1`, `5`, `10`, `20`
- calibration sweep source: all available runs `1..20`

Units:

- wake axis: `s / mm`, converted to m
- wake value: `Wl(s) / V/pC`
- impedance axis: `Frequency / MHz`, converted to Hz
- impedance value: `Z / Ohm`
- charge distribution: `Distance / mm`, `C/m`

Local scratch outputs used:

```text
analysis_outputs/wf2_known_mode_calibration_stability/
```

No scratch scripts, plots, CSV files, or CST outputs were committed.

## Validation Method

The validation reused the P05 diagnostic replay outputs and added one local
secondary impedance-envelope summary. The calibration sweep used:

- frequency prior: `499.8 MHz`
- frequency sweep: `499.0 MHz` to `501.0 MHz`
- frequency step: `25 kHz`
- Q prior: `36500`
- R/Q baseline convention: `104.3 ohm`
- selected fit starts for final gates: `1 m` and `2 m`

The known-mode scalar projection was:

```text
scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)
RQ_cal = RQ_prior * scale
```

The reconstructed impedance envelope was computed from existing ensemble mode
parameters, without rerunning PSO.

## Task 1: Calibration Layer Validation

Selected-start calibration stability for runs `1`, `5`, `10`, and `20`:

| Run | f_cal range (MHz) | f variation (MHz) | RQ_cal range (ohm) | RQ variation | Mean residual RMS | Mean corr. |
|---:|---|---:|---|---:|---:|---:|
| 1 | 499.800-499.800 | 0.000 | 100.817-100.838 | 0.02% | 0.00690 | 0.99916 |
| 5 | 500.025-500.025 | 0.000 | 100.801-100.821 | 0.02% | 0.00751 | 0.99901 |
| 10 | 499.950-499.950 | 0.000 | 100.859-100.870 | 0.01% | 0.01867 | 0.99401 |
| 20 | 499.775-499.775 | 0.000 | 100.889-100.901 | 0.01% | 0.01267 | 0.99722 |

Across all runs `1..20` and selected starts `1 m` and `2 m`:

- `f_cal` range: `499.775 MHz` to `500.125 MHz`
- `RQ_cal` range: `100.686 ohm` to `100.935 ohm`

Interpretation:

- Per-run selected-start `f_cal` variation passes the `<= 0.1 MHz` gate.
- Per-run selected-start `RQ_cal` variation is far below the `10%` gate.
- Run-to-run frequency offsets are real and should be treated as evidence for
  deterministic calibration, not as a failure.
- Run 10 has lower known-only correlation at selected starts because residual
  HOM or non-fundamental structure remains, but its calibration parameters are
  stable.

Task 1 result: PASS.

## Task 2: Q Identifiability Test

Q grid:

```text
10000, 20000, 36500, 60000, 100000
```

Residual sensitivity:

| Run | Start (m) | Best Q on grid | Residual RMS range | Absolute span | Relative span |
|---:|---:|---:|---|---:|---:|
| 1 | 1 | 10000 | 0.00750-0.00809 | 0.000587 | 7.47% |
| 1 | 2 | 10000 | 0.00528-0.00608 | 0.000797 | 13.81% |
| 5 | 1 | 10000 | 0.00809-0.00863 | 0.000544 | 6.47% |
| 5 | 2 | 10000 | 0.00603-0.00674 | 0.000705 | 10.90% |
| 10 | 1 | 10000 | 0.01906-0.01930 | 0.000235 | 1.22% |
| 10 | 2 | 10000 | 0.01794-0.01819 | 0.000250 | 1.38% |
| 20 | 1 | 10000 | 0.01321-0.01354 | 0.000335 | 2.49% |
| 20 | 2 | 10000 | 0.01162-0.01200 | 0.000379 | 3.20% |

Interpretation:

- The grid often prefers `Q = 10000`, but the absolute residual change is
  small.
- The apparent preference is not enough to justify replacing the physical
  prior `Q = 36500`.
- Q changes likely absorb residual structure rather than identifying a stable
  damping rate.

Task 2 result: PASS with decision `Q fixed`.

## Task 3: PSO HOM Ensemble Stability

The HOM ensemble used calibrated known-mode baselines, selected starts `1 m`
and `2 m`, four deterministic seeds per run/start, and the existing HOM peak
selection path.

Wake-domain ensemble summary:

| Run | Start (m) | Seeds | RMS mean | RMS std. | Mean norm. error | Mean corr. | HOM Q range | Q bound hits |
|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 1 | 1 | 4 | 0.00416 | 0.00038 | 0.00060 | 0.99970 | 1.0-57.8 | 19/32 |
| 1 | 2 | 4 | 0.00397 | 0.00044 | 0.00055 | 0.99972 | 1.0-29.5 | 23/32 |
| 5 | 1 | 4 | 0.00439 | 0.00033 | 0.00067 | 0.99967 | 1.0-484.3 | 14/32 |
| 5 | 2 | 4 | 0.00415 | 0.00022 | 0.00060 | 0.99970 | 1.0-100000.0 | 17/32 |
| 10 | 1 | 4 | 0.01300 | 0.00520 | 0.00670 | 0.99664 | 1.0-90654.1 | 16/32 |
| 10 | 2 | 4 | 0.00858 | 0.00430 | 0.00316 | 0.99842 | 1.0-100000.0 | 15/32 |
| 20 | 1 | 4 | 0.00668 | 0.00204 | 0.00168 | 0.99916 | 1.0-100000.0 | 23/32 |
| 20 | 2 | 4 | 0.00697 | 0.00240 | 0.00187 | 0.99906 | 1.0-100000.0 | 21/32 |

Interpretation:

- Wake-domain residuals are bounded and correlations remain high for selected
  starts.
- Runs 1 and 5 are stable in both residual level and seed spread.
- Runs 10 and 20 show larger seed spread, but still retain high wake
  correlations and acceptable normalized errors.
- HOM Q and derived mode parameters are not unique. Frequent bound hits mean
  individual fitted HOM Q/RQ values should not be treated as authoritative
  physical measurements.

Task 3 result: PASS for wake-domain inversion, WARNING for HOM parameter
uniqueness.

## Task 4: Envelope Validation

The reconstructed impedance envelope is secondary only. The table below reports
how often CST sampled impedance falls inside the ensemble envelope over the
`550 MHz` to `1.45 GHz` HOM band.

| Run | Start (m) | CST inside P10/P90 | CST inside P05/P95 | Median mean/CST | P90 mean/CST | Median std/mean |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 9.3% | 12.0% | 7.21 | 21.17 | 0.45 |
| 1 | 2 | 1.1% | 2.4% | 10.58 | 28.66 | 0.35 |
| 5 | 1 | 5.5% | 5.7% | 10.29 | 30.06 | 0.55 |
| 5 | 2 | 27.5% | 36.6% | 5.73 | 13.87 | 0.77 |
| 10 | 1 | 20.2% | 23.1% | 4.82 | 17.80 | 0.74 |
| 10 | 2 | 9.9% | 12.0% | 6.77 | 18.23 | 0.42 |
| 20 | 1 | 6.5% | 12.7% | 6.55 | 19.70 | 0.49 |
| 20 | 2 | 6.7% | 7.8% | 8.03 | 27.30 | 0.37 |

Interpretation:

- The reconstructed impedance envelope does not tightly contain CST sampled
  impedance.
- This is consistent with P05: wake-tail resonator fitting and CST sampled
  impedance are not interchangeable pass/fail metrics.
- The envelope is useful as a warning and review diagnostic, not as a primary
  system gate.

Task 4 result: SECONDARY WARNING, not a primary FAIL.

## Pass/Fail Evaluation

| Criterion | Result | Evidence |
|---|---|---|
| Selected-start `f_cal` variation within each run `<= 0.1 MHz` | PASS | Representative runs have `0.000 MHz` variation at starts `1 m` and `2 m`. |
| Selected-start `RQ_cal` variation within each run `< 10%` | PASS | Representative runs are `0.01%` to `0.02%`. |
| Q weakly identifiable or consistent prior | PASS | Q residual spans are small; decision is `Q fixed`. |
| Calibrated HOM PSO wake residuals stable across seeds | PASS with warning | Wake correlations remain high; runs 10 and 20 have larger residual spread. |
| No seed-dependent physics divergence | PASS with warning | Wake-domain metrics do not bifurcate, but HOM Q/RQ parameters are non-unique. |
| Reconstructed impedance used only as secondary | PASS | Envelope mismatch is reported as warning only. |

Final decision:

```text
PASS WITH WARNINGS
```

The system spec is reasonable under its primary wake-domain criteria. The
warnings are important:

- individual HOM Q/RQ values are not stable enough to publish as unique modal
  physics without additional clustering or constraints;
- reconstructed impedance envelope mismatch should remain secondary;
- strict production PASS thresholds for ensemble variance still need to be
  formalized before this becomes an automated gate.

## Recommended Current Policy

- Use deterministic calibration for frequency and scalar effective `R/Q`.
- Keep known-mode Q fixed to `36500`.
- Use `R/Q = 104.3 ohm` as the current input convention baseline.
- Treat calibrated effective `R/Q` near `100.6 ohm` as expected for this data.
- Use `2 m` as the conservative selected start and `1 m` as a companion review
  start.
- Use reconstructed impedance only for secondary envelope review.
- Report HOM ensemble wake metrics as primary; report individual HOM Q/RQ
  parameters with uncertainty warnings.

## Local Artifacts

Used or generated local-only artifacts:

- `analysis_outputs/wf2_known_mode_calibration_stability/calibration_sweep.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/q_sensitivity.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/hom_pso_ensemble.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/impedance_envelope_summary.csv`
- `analysis_outputs/wf2_known_mode_calibration_stability/summary.json`

No plots were generated for this validation report.
