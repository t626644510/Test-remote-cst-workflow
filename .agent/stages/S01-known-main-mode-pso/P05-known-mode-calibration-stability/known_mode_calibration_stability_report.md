# Known-Mode Calibration Stability Report

## Scope

This phase replays existing Workflow 2 long-wake CST results to test whether
the fixed fundamental mode should be deterministically calibrated before HOM
PSO fitting. No CST solve, smoke run, geometry rebuild, live-CST simulation,
production-code change, CST API change, scalarization change, or test-code
change was performed.

Current implementation behavior remains fixed-input only:

- `KnownMode.frequency_hz` is fixed by the caller.
- `KnownMode.q` is fixed by the caller.
- `KnownMode.r_over_q_ohm` is fixed by the caller.
- `frequency_tolerance_hz` only filters detected peaks near a known mode. It
  does not fit, calibrate, or update the known-mode frequency.

The analysis in this report is diagnostic evidence for a possible future
calibration layer. It is not a production implementation.

## Data Source

Existing local CST data:

- `D:\workflow2\Before_rebuild_backup\F2W.cst`
- `D:\workflow2\Before_rebuild_backup\F2W`

Longitudinal `ParticleBeam1` paths used:

- `1D Results\Particle Beams\ParticleBeam1\Wake potential\Z`
- `1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z`
- `1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)`

Available and used run IDs:

```text
1, 2, 3, ..., 20
```

Representative runs retained for detailed tables:

```text
1, 5, 10, 20
```

Observed units:

| Result | CST label | Analysis unit |
|---|---|---|
| Wake axis | `s / mm` | m |
| Wake value | `Wl(s) / V/pC` | V/pC |
| Impedance axis | `Frequency / MHz` | Hz |
| Impedance value | `Z / Ohm` | Ohm |
| Charge axis | `Distance / mm` | m |
| Charge value | `C/m` | C/m |

The bunch RMS length estimated from the charge distribution is
`sigma_z_m = 0.07 m` for all used runs.

Local-only outputs were written under:

```text
analysis_outputs/wf2_known_mode_calibration_stability/
```

They were intentionally not added to git.

## Method

Primary evidence is wake-domain stability:

- known-mode-only residual RMS;
- total wake residual RMS after HOM PSO;
- normalized residual error;
- wake correlation;
- calibrated fundamental frequency stability;
- effective `R/Q` stability.

Reconstructed `|Z|` is treated only as a secondary consistency diagnostic.
It is not used as the pass/fail definition for the best result.

Baseline prior values:

| Parameter | Value |
|---|---:|
| Fundamental frequency | `499.8e6 Hz` |
| Fundamental Q | `36500` |
| R/Q convention 1 | `208.6 ohm` |
| R/Q convention 2 | `104.3 ohm` |

Frequency sweep:

```text
499.0 MHz .. 501.0 MHz, 25 kHz step
```

Fit-start sweep:

```text
0, 0.5, 1, 2, 5, 10, 20, 40 m
```

For each frequency, the known wake was projected onto the CST wake tail:

```text
scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)
effective_r_over_q = baseline_r_over_q * scale
```

## R/Q Convention Recheck

The fixed-prior recheck at `fit_start = 1 m`, `f = 499.8 MHz`, `Q = 36500`
reproduces the factor-of-two amplitude finding.

| Run | R/Q (ohm) | Target RMS (V/pC) | Known RMS (V/pC) | Residual RMS (V/pC) | Norm. error | Corr. |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 208.6 | 0.17004 | 0.35138 | 0.18169 | 1.14175 | 0.99891 |
| 1 | 104.3 | 0.17004 | 0.17569 | 0.00984 | 0.00335 | 0.99891 |
| 5 | 208.6 | 0.17004 | 0.35138 | 0.19375 | 1.29832 | 0.96102 |
| 5 | 104.3 | 0.17004 | 0.17569 | 0.04859 | 0.08164 | 0.96102 |
| 10 | 208.6 | 0.17099 | 0.35137 | 0.18722 | 1.19875 | 0.97909 |
| 10 | 104.3 | 0.17099 | 0.17569 | 0.03575 | 0.04371 | 0.97909 |
| 20 | 208.6 | 0.17049 | 0.35137 | 0.18212 | 1.14109 | 0.99623 |
| 20 | 104.3 | 0.17049 | 0.17569 | 0.01590 | 0.00870 | 0.99623 |

The `208.6 ohm` convention over-predicts the wake amplitude by approximately
2x in this implementation's wake convention. The `104.3 ohm` convention is
the correct current baseline for these data.

After scalar projection at `fit_start = 1 m`, both conventions converge to the
same effective `R/Q` because the scale absorbs the convention:

| Run | Baseline R/Q | Projection scale | Effective R/Q (ohm) | Best frequency (MHz) |
|---:|---:|---:|---:|---:|
| 1 | 208.6 | 0.48340 | 100.838 | 499.800 |
| 1 | 104.3 | 0.96680 | 100.838 | 499.800 |
| 5 | 208.6 | 0.48332 | 100.821 | 500.025 |
| 5 | 104.3 | 0.96665 | 100.821 | 500.025 |
| 10 | 208.6 | 0.48356 | 100.870 | 499.950 |
| 10 | 104.3 | 0.96711 | 100.870 | 499.950 |
| 20 | 208.6 | 0.48371 | 100.901 | 499.775 |
| 20 | 104.3 | 0.96741 | 100.901 | 499.775 |

## Test 1: Deterministic Calibration Sweep

Across all 20 runs and all 8 fit starts, using `104.3 ohm` as the projection
baseline:

| Quantity | Min | Mean | Max | Std. dev. |
|---|---:|---:|---:|---:|
| Best frequency (MHz) | 499.775 | 499.885 | 500.125 | 0.085 |
| Effective R/Q (ohm) | 99.544 | 100.574 | 100.935 | 0.357 |
| Known-only residual RMS (V/pC) | 0.00219 | 0.01099 | 0.03900 | 0.00819 |
| Known-only normalized error | 0.00017 | 0.00638 | 0.05027 | 0.01007 |
| Wake correlation | 0.97454 | 0.99679 | 0.99991 | 0.00509 |

Mean behavior by fit start:

| Start (m) | Mean best f (MHz) | f range (MHz) | Mean eff. R/Q (ohm) | R/Q range (ohm) | Mean residual RMS | Mean corr. |
|---:|---:|---|---:|---|---:|---:|
| 0 | 499.885 | 499.775-500.125 | 100.744 | 100.593-100.829 | 0.01608 | 0.99482 |
| 0.5 | 499.885 | 499.775-500.125 | 100.809 | 100.658-100.895 | 0.01519 | 0.99524 |
| 1 | 499.885 | 499.775-500.125 | 100.848 | 100.704-100.935 | 0.01439 | 0.99559 |
| 2 | 499.885 | 499.775-500.125 | 100.833 | 100.686-100.925 | 0.01288 | 0.99618 |
| 5 | 499.885 | 499.775-500.125 | 100.731 | 100.556-100.838 | 0.01046 | 0.99709 |
| 10 | 499.885 | 499.775-500.125 | 100.563 | 100.385-100.643 | 0.00820 | 0.99788 |
| 20 | 499.885 | 499.775-500.125 | 100.307 | 100.110-100.415 | 0.00613 | 0.99853 |
| 40 | 499.885 | 499.775-500.125 | 99.756 | 99.544-99.857 | 0.00456 | 0.99899 |

Interpretation:

- Best frequency is stable per run and lies within `499.775-500.125 MHz`.
- Effective `R/Q` is stable near `100.6 ohm`, slightly below `104.3 ohm`.
- Later starts reduce known-only residual because more HOM / early structure is
  excluded, not because late starts are necessarily better for HOM recovery.
- A deterministic calibration layer would catch both R/Q convention mismatch
  and run-level frequency offset before HOM PSO spends degrees of freedom on
  fundamental residual.

Representative run ranges over practical starts `1-20 m`:

| Run | Best f range (MHz) | Eff. R/Q range (ohm) | Residual RMS range (V/pC) |
|---:|---|---|---|
| 1 | 499.800-499.800 | 100.290-100.838 | 0.00283-0.00793 |
| 5 | 500.025-500.025 | 100.273-100.821 | 0.00296-0.00848 |
| 10 | 499.950-499.950 | 100.345-100.870 | 0.00730-0.01923 |
| 20 | 499.775-499.775 | 100.365-100.901 | 0.00361-0.01345 |

## Test 2: Q Sensitivity

Q grid:

```text
10000, 20000, 36500, 60000, 100000
```

For each representative run and start, frequency was fixed to the Test 1 best
frequency and `R/Q` was re-projected. The best grid value was often
`Q = 10000`, but the residual curve was very flat.

| Run | Start (m) | Best Q on grid | Residual RMS span over Q grid |
|---:|---:|---:|---:|
| 1 | 1 | 10000 | 0.000587 |
| 1 | 2 | 10000 | 0.000797 |
| 5 | 1 | 10000 | 0.000544 |
| 5 | 2 | 10000 | 0.000705 |
| 10 | 1 | 10000 | 0.000235 |
| 10 | 2 | 10000 | 0.000250 |
| 20 | 1 | 10000 | 0.000335 |
| 20 | 2 | 10000 | 0.000379 |

Interpretation:

- Q is weakly identifiable from these wake tails.
- Letting Q float in a deterministic calibration layer would risk fitting
  residual structure rather than measuring a robust physical Q.
- Keep `Q = 36500` as a fixed documented prior for the current long-wake
  known-mode path.

## Test 3: Fit-Start Stability

The known-only residual minimum is generally at `40 m`, but this is not an
appropriate default for HOM PSO because it discards useful HOM content. The
more relevant question is whether parameters are stable over practical starts.

Practical starts `1-20 m` show:

- per-run frequency is stable to the 25 kHz sweep step;
- effective `R/Q` stays within about `0.55 ohm` for the representative runs;
- residuals fall as the start moves later because non-fundamental content is
  progressively excluded.

Recommended current fit-start policy:

- Use `2 m` as a conservative fixed default for long-wake longitudinal
  known-mode HOM PSO.
- Also inspect `1 m` during analysis when early HOM content matters.
- Use `5-10 m` as a secondary stability check, not as the only production
  default.
- Do not hide start choice behind a single "best residual" selected from very
  late starts.

This makes `1 m` defensible and `2 m` slightly more conservative. The current
data do not support a universal late-tail default such as `40 m` for HOM PSO.

## Test 4: HOM PSO Ensemble After Calibration

The ensemble used calibrated known frequency and effective `R/Q` from Test 1,
fixed `Q = 36500`, HOM peak search from `550 MHz` to `1.45 GHz`, eight selected
unknown modes, and deterministic seeds:

```text
711, 733, 769, 797
```

Starts tested:

```text
1 m, 2 m
```

Wake-domain ensemble summary:

| Run | Start (m) | N | Residual RMS mean | Residual RMS std. | Min-max RMS | Mean norm. error | Mean corr. |
|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | 1 | 4 | 0.00416 | 0.00038 | 0.00381-0.00480 | 0.00060 | 0.99970 |
| 1 | 2 | 4 | 0.00397 | 0.00044 | 0.00369-0.00473 | 0.00055 | 0.99972 |
| 5 | 1 | 4 | 0.00439 | 0.00033 | 0.00398-0.00480 | 0.00067 | 0.99967 |
| 5 | 2 | 4 | 0.00415 | 0.00022 | 0.00387-0.00439 | 0.00060 | 0.99970 |
| 10 | 1 | 4 | 0.01300 | 0.00520 | 0.00414-0.01674 | 0.00670 | 0.99664 |
| 10 | 2 | 4 | 0.00858 | 0.00430 | 0.00429-0.01453 | 0.00316 | 0.99842 |
| 20 | 1 | 4 | 0.00668 | 0.00204 | 0.00450-0.00997 | 0.00168 | 0.99916 |
| 20 | 2 | 4 | 0.00697 | 0.00240 | 0.00424-0.01084 | 0.00187 | 0.99906 |

Mode and reconstructed impedance stability:

- Selected peak frequencies are fixed by the visible peak list and are stable
  for a given run/start.
- Fitted HOM Q and R/Q are not unique. Several ensembles hit broad ranges,
  including Q near the lower bound and, for some modes, the upper bound.
- Reconstructed impedance ratios over the HOM band had large high-percentile
  spreads. Mean P90 reconstructed/CST `|Z|` ratios ranged from about `14.7` to
  `30.0` across the representative groups.

Secondary impedance-envelope summary:

| Run | Start (m) | Mean P90 reconstructed/CST `|Z|` ratio |
|---:|---:|---:|
| 1 | 1 | 21.23 |
| 1 | 2 | 28.79 |
| 5 | 1 | 30.01 |
| 5 | 2 | 14.66 |
| 10 | 1 | 18.15 |
| 10 | 2 | 18.37 |
| 20 | 1 | 19.98 |
| 20 | 2 | 29.12 |

Interpretation:

- Calibrated known-mode subtraction makes wake-domain HOM PSO residuals small
  and repeatable for runs 1 and 5.
- Runs 10 and 20 still have seed-dependent HOM decompositions, even when wake
  metrics remain acceptable.
- Single-run reconstructed `|Z|` must not be used as an authoritative pass/fail
  result. Use ensemble envelopes and wake-domain gates instead.

## Recommendation

A production known-mode calibration layer is recommended for long-wake
longitudinal Workflow 2 use, but it should be deterministic and bounded:

1. Keep the existing known-mode implementation fixed by default.
2. Add a future optional pre-PSO calibration step that estimates:
   - frequency over a bounded prior window;
   - scalar effective `R/Q` by projection.
3. Keep Q fixed to the eigenmode/design prior unless later evidence shows a
   stable, physically meaningful Q estimate.
4. Record calibrated values separately from user-supplied priors so scientific
   provenance stays clear.
5. Keep reconstructed `|Z|` as an ensemble diagnostic, not a scalar acceptance
   target.

Recommended current long-wake defaults before productionizing calibration:

| Setting | Recommendation |
|---|---|
| Known frequency prior | `499.8e6 Hz` |
| Known Q | `36500`, fixed |
| Known R/Q input convention | `104.3 ohm` |
| Expected calibrated effective R/Q | about `100.6 ohm` for this data |
| `frequency_tolerance_hz` | `1e6` to `2e6` for peak filtering |
| Unknown HOM peak minimum | `>= 550e6 Hz` |
| Primary HOM PSO start | `2 m` |
| Secondary review starts | `1 m`, `5 m`, optionally `10 m` |
| Primary gates | wake residual RMS, normalized error, wake correlation |
| Secondary gates | reconstructed `|Z|` ensemble envelope |

## Data Gaps And Assumptions

- The analysis used CST result-tree replay only; no new CST data were produced.
- The sweep resolution was `25 kHz`; sub-grid frequency optimization was not
  attempted.
- HOM PSO used a local deterministic log-space PSO helper because the local
  environment did not require `pymoo` for this report-only replay.
- The reconstructed impedance envelope was summarized numerically; local
  scratch CSV files contain the detailed ensemble rows.
- Only longitudinal `ParticleBeam1` data were evaluated. Transverse known modes
  remain unsupported by the production module.

## Suggested Next Phase

If accepted, the next implementation phase should be small and optional:

- add a diagnostic/pre-fit calibration helper for longitudinal known modes;
- keep it outside CST access and outside scalarization;
- expose prior values, calibrated values, residual metrics, and fit-start
  evidence in diagnostics;
- add synthetic no-CST tests for frequency and scalar `R/Q` projection;
- leave Q fixed unless a later dedicated study justifies calibrating it.
