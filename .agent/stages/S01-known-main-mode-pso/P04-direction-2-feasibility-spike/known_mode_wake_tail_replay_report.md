# Known-Mode Wake-Tail Replay Report

## Scope

This report summarizes the read-only replay tests performed on the existing
long-wake Workflow 2 CST results:

- `D:\workflow2\Before_rebuild_backup\F2W.cst`
- `D:\workflow2\Before_rebuild_backup\F2W`
- `D:\workflow2\Before_rebuild_backup\F2W_offset.cst`
- `D:\workflow2\Before_rebuild_backup\F2W_offset`

Only longitudinal `ParticleBeam1` data from `F2W.cst` was used. No smoke run,
live CST solve, geometry rebuild, or CST API change was performed.

The objective was to evaluate the current known-mode PSO wake fitting behavior
using an externally supplied fundamental mode:

```yaml
frequency_hz: 499.8e6
q: 36500
r_over_q_ohm: 208.6  # first convention tested
```

and then retest after switching to the alternate R/Q convention:

```yaml
r_over_q_ohm: 104.3
```

## Result Tree Inventory

`F2W.cst` exposes the expected longitudinal wakefield result tree:

- `1D Results\Particle Beams\ParticleBeam1\Wake potential\Z`
- `1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z`
- `1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)`

Available run IDs for the longitudinal wake and impedance curves:

```text
1, 2, 3, ..., 20
```

Observed units:

- Wake potential axis: `s / mm`
- Wake potential value: `Wl(s) / V/pC`
- Wake length: approximately `100000 mm = 100 m`
- Wake impedance axis: `Frequency / MHz`
- Wake impedance span: approximately `0 to 1462.735 MHz`
- Estimated bunch RMS length from charge distribution: `sigma_z_m = 0.07 m`

`F2W_offset.cst` contains `ParticleBeam2` offset-beam results. It was not used
in this longitudinal-only replay.

## How The Factor-of-Two R/Q Issue Was Found

The current known-mode implementation computes a fixed wake contribution from
frequency, Q, R/Q, and bunch form factor. For the supplied `R/Q = 208.6 ohm`,
the computed fixed fundamental wake was compared directly with the CST wake
tail on the same fit grid.

For run 1 with fit start at `1 m`:

```text
target_wake_rms ~= 0.170 V/pC
known_mode_wake_rms with R/Q=208.6 ~= 0.351 V/pC
```

The wake phase and frequency matched well, but the amplitude was about twice
the CST wake amplitude.

A scalar projection was then computed:

```text
scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)
```

Across representative runs and fit starts, the best scale was mostly
`0.46 - 0.48`, implying:

```text
effective R/Q ~= 96 - 101 ohm
```

This is consistent with the alternate R/Q convention and motivated retesting
with `R/Q = 104.3 ohm`.

## Fundamental Frequency Tolerance

The sampled CST impedance peak near the supplied fundamental frequency was
stable across all 20 longitudinal runs:

```text
local sampled peak: 500.255334 MHz
delta from 499.8 MHz: +455.334 kHz
```

For production-style HOM fitting with:

```yaml
peak_settings:
  freq_min_hz: 550e6
```

the fundamental is outside the unknown-HOM peak search range, so
`frequency_tolerance_hz = 1e6` or `2e6` is sufficient for diagnostics.

If peak search starts below the fundamental, a much larger tolerance can be
needed to filter the sampled cluster around 500 MHz. That mode is not
recommended for the current Workflow 2 HOM-only use.

## R/Q = 104.3 Baseline Cases

The four representative replay cases used `R/Q = 104.3 ohm`, HOM peak search
from `550 MHz`, eight selected unknown modes, and fit end at the wake tail.

| run | fit start | residual RMS (V/pC) | normalized error | wake corr | unknown RMS (V/pC) |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 m | 0.00722 | 0.00180 | 0.99969 | 0.00666 |
| 5 | 1 m | 0.04794 | 0.07950 | 0.96216 | 0.00792 |
| 10 | 1 m | 0.03045 | 0.03172 | 0.98520 | 0.01871 |
| 20 | 10 m | 0.00976 | 0.00331 | 0.99903 | 0.00422 |

Interpretation:

- Run 1 and run 20 show excellent wake-domain agreement.
- Run 5 and run 10 retain nontrivial residual structure after subtracting the
  known fundamental, likely reflecting additional HOM content, run-dependent
  structure, or mismatch not removed by changing the fit start.
- The `R/Q = 104.3 ohm` convention is strongly preferred over `208.6 ohm` for
  this implementation's wake amplitude convention.

## Fit-Start Sweep

Fit starts tested:

```text
0, 0.5, 1, 2, 5, 10, 20, 40 m
```

Best wake-domain residual RMS by run:

| run | best fit start | residual RMS (V/pC) | normalized error | wake corr |
|---:|---:|---:|---:|---:|
| 1 | 10 m | 0.00692 | 0.00167 | 0.99986 |
| 5 | 0 m | 0.04783 | 0.07910 | 0.96234 |
| 10 | 0.5 m | 0.03048 | 0.03176 | 0.98516 |
| 20 | 5 m | 0.00961 | 0.00320 | 0.99903 |

Fit-start behavior:

- Run 1 is robust from about `2 m` to `10 m`; very late starts reduce unknown
  HOM RMS but do not materially improve residual RMS.
- Run 5 degrades as the fit start is moved later. This suggests the residual
  is not merely an early transient.
- Run 10 is best around `0.5 m` to `1 m`; `0 m` is affected by early structure,
  while very late starts degrade the result.
- Run 20 is best around `1 m` to `10 m`, with `5 m` slightly best in one sweep
  and `2 m` slightly best in the impedance replay sweep. Differences are small.

## Reconstructed Impedance Observations

The reconstructed `|Z|` was also plotted for the same fit-start sweep. These
plots compare CST sampled `|Z|` with PSO reconstructed `|Z|` over:

- full HOM band, linear scale;
- full HOM band, log10 scale;
- zoom around `740 - 820 MHz`;
- zoom around `1250 - 1360 MHz`.

Main observation:

Wake-domain residual quality and reconstructed impedance agreement are not
equivalent. A fit start with excellent wake residual can still produce a
reconstructed `|Z|` curve that differs substantially from CST sampled
impedance, especially in peak width and amplitude.

This is expected from the current model constraints:

- PSO frequencies are fixed to visible sampled peaks.
- PSO optimizes wake-domain amplitude and Q.
- R/Q is derived from fitted wake amplitude and bunch form factor.
- CST sampled impedance includes finite-window and solver/postprocess effects
  not necessarily reproduced by the wake-tail resonator sum.

Therefore, for this stage:

- use `known_mode_wake`, `unknown_mode_wake`, `residual_wake`, `wake_corr`, and
  `residual_wake_rms` as primary diagnostics;
- treat reconstructed `|Z|` as a secondary diagnostic, not as a direct
  replacement for CST sampled impedance.

## Local Artifacts

Local plots and replay scripts were generated under:

```text
analysis_outputs/wf2_known_mode_rq1043/
```

Important local files:

- `summary_rq104p3.png`
- `run01_start1p0m_rq104p3.png`
- `run05_start1p0m_rq104p3.png`
- `run10_start1p0m_rq104p3.png`
- `run20_start10p0m_rq104p3.png`
- `start_sweep/all_runs_start_sweep_summary.png`
- `start_sweep/run01_start_sweep.png`
- `start_sweep/run05_start_sweep.png`
- `start_sweep/run10_start_sweep.png`
- `start_sweep/run20_start_sweep.png`
- `impedance_start_sweep/run01_impedance_by_start.png`
- `impedance_start_sweep/run05_impedance_by_start.png`
- `impedance_start_sweep/run10_impedance_by_start.png`
- `impedance_start_sweep/run20_impedance_by_start.png`

These local artifacts were intentionally not added to git because repository
hygiene rules exclude local outputs and scratch analysis scripts.

## Recommendations For GPT-5.5 Pro Discussion

Suggested questions for the next design discussion:

1. Should Workflow 2 standardize known-mode R/Q input on the `104.3 ohm`
   convention for this wake fitting implementation?
2. Should config documentation explicitly name the R/Q convention expected by
   `KnownMode.r_over_q_ohm`?
3. Should the fitter expose an optional diagnostic-only scalar projection
   (`effective_known_r_over_q`) to catch convention mismatches early?
4. Should production validation gate known-mode use on wake-domain residual
   metrics rather than reconstructed `|Z|` agreement?
5. Should the recommended default fit start for long-wake longitudinal known
   mode fitting be run-dependent, or should Workflow 2 use a conservative
   fixed start such as `1 m` or `2 m`?

Current evidence supports:

- use `R/Q = 104.3 ohm` for this module's known fundamental mode input;
- keep `peak_settings.freq_min_hz >= 550e6` for unknown HOM fitting;
- use `frequency_tolerance_hz` around `1e6 - 2e6` for this CST data;
- prefer wake-domain diagnostics for acceptance;
- keep reconstructed impedance plots as review aids, not as pass/fail metrics.
