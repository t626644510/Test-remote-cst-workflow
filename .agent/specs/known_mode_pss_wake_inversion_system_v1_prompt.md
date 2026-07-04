You are the local execution agent for validating the Known-mode PSO Wake
Inversion System Spec v1.0.

## Objective

Validate the system behavior described in the specification using existing
Workflow 2 CST long-wake data only.

You are NOT allowed to:

- run new CST simulations
- modify production code
- modify CST API
- modify PSO implementation
- change scalarization logic
- commit local plots, scratch scripts, CST files, or large generated outputs
  unless a phase prompt explicitly allows them

---

## Required Inputs

Use existing dataset:

```text
D:\workflow2\Before_rebuild_backup\F2W.cst
```

Primary result paths:

- `1D Results\Particle Beams\ParticleBeam1\Wake potential\Z`
- `1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z`
- `1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)`

Runs:

- `1`, `5`, `10`, `20` minimum
- optionally `1..20`

Use longitudinal data only.

---

## Tasks

### Task 1: Calibration Layer Validation

For each run and fit start:

- sweep fundamental frequency around `499.8 MHz +/- 0.5 MHz`
- keep the known-mode Q fixed to the prior unless Task 2 justifies otherwise
- compute projection-based effective `R/Q`:

```text
scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)
RQ_cal = RQ_prior * scale
```

Measure:

- residual RMS
- normalized residual error
- wake correlation
- `f_cal` stability within each run over selected stable starts
- `RQ_cal` stability within each run over selected stable starts

Output:

- per-run `f_cal` distribution
- per-run `RQ_cal` distribution
- global run-to-run distribution as descriptive evidence only

Do not fail the system merely because different CST runs prefer different
calibrated fundamental frequencies. A run-to-run offset is expected evidence
for the calibration layer; instability is defined within selected stable
starts for the same run, or by clearly inconsistent calibrated values that
cannot support a stable workflow policy.

---

### Task 2: Q Identifiability Test

Sweep Q:

```text
10000, 20000, 36500, 60000, 100000
```

Measure:

- residual RMS sensitivity
- normalized residual sensitivity
- whether the best Q is stable across runs and selected starts

Decision:

- `Q fixed` if the residual curve is flat, inconsistent, or dominated by
  residual structure
- `Q calibratable` only if the optimum is sharp, stable, and physically
  interpretable across runs and selected starts

---

### Task 3: PSO HOM Ensemble Stability

For selected calibrated baselines and stable fit starts:

- run PSO with multiple deterministic seeds
- collect:
  - HOM frequencies
  - HOM Q values
  - HOM amplitudes or derived `R/Q`
  - wake residual RMS
  - normalized residual error
  - wake correlation
  - bound-hit indicators for HOM Q and amplitude

Compute:

- variance across seeds
- mode clustering stability
- residual metric spread
- whether multiple seeds produce physically divergent HOM decompositions

The peak-frequency list may be fixed by peak detection. In that case, mode
stability should focus on fitted amplitude, Q, derived `R/Q`, bound hits, and
wake-domain residuals.

---

### Task 4: Envelope Validation

Compute, when practical:

- `Z_mean(f)`
- `Z_std(f)`
- percentile envelope such as P10/P90 or P05/P95

Check:

- whether CST sampled impedance lies within or near the ensemble envelope

This check is secondary only. It may produce warnings and diagnostic comments,
but it must not override wake-domain and ensemble-stability evidence unless a
future phase validates equivalence between the CST sampled impedance and the
reconstructed resonator-sum impedance.

---

## Required Outputs

Generate report:

```text
.agent/specs/known_mode_pss_wake_inversion_system_v1_validation_report.md
```

Must include:

- calibration stability tables
- Q sensitivity tables
- ensemble variance tables
- reconstructed-impedance envelope summary as secondary evidence
- pass/fail evaluation of the system spec
- any local scratch/plot paths used for review

Plots are optional. If generated, keep them in a local scratch/output directory
and do not commit them unless the active phase explicitly allows plot files.

---

## Final Decision Criteria

PASS if:

- selected-start `f_cal` variation within each run is less than or equal to
  `0.1 MHz`, or the report justifies a slightly wider grid-resolution-limited
  band without changing the workflow recommendation
- selected-start `RQ_cal` variation within each run is less than `10%`
- Q is weakly identifiable and kept as a fixed prior, or a stable Q calibration
  is demonstrated
- calibrated HOM PSO wake residuals are stable across seeds for selected starts
- no seed-dependent physics divergence is observed in wake-domain metrics

FAIL if:

- calibrated known-mode parameters are unstable even within selected stable
  starts for the same run
- no defensible fit-start policy can be identified
- HOM PSO ensemble behavior is seed-dependent in wake-domain residuals or mode
  decomposition to the point that no stable scientific output can be reported

Do not FAIL solely because:

- reconstructed impedance `|Z|` is outside the envelope;
- different CST runs prefer different calibrated frequencies within the
  bounded frequency-search window;
- very early or very late exploratory fit starts fail stability gates.

---

## Important Rule

Reconstructed impedance `|Z|` MUST NOT be used as the primary decision metric.
Only wake-domain calibration quality, selected-start stability, and HOM
ensemble stability are primary.
