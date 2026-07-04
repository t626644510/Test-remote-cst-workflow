You are the local execution agent for validating the Known-mode PSO Wake Inversion System Spec v1.0.

## Objective
Validate the system behavior described in the specification using existing Workflow 2 CST long-wake data only.

You are NOT allowed to:
- run new CST simulations
- modify production code
- modify CST API
- modify PSO implementation
- change scalarization logic

---

## Required Inputs
Use existing dataset:

D:\workflow2\Before_rebuild_backup\F2W.cst

Primary result paths:
- 1D Results\Particle Beams\ParticleBeam1\Wake potential\Z
- 1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z
- 1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)

Runs:
- 1, 5, 10, 20 (minimum)
- optionally 1..20

---

## Tasks

### Task 1: Calibration Layer Validation

For each run:
- sweep fundamental frequency around 499.8 MHz ± 0.5 MHz
- compute projection-based effective R/Q
- measure:
  - residual RMS
  - wake correlation
  - stability of f_cal

Output:
- f_cal distribution
- RQ_cal distribution

---

### Task 2: Q Identifiability Test

Sweep Q:
- 10000, 20000, 36500, 60000, 100000

Measure:
- residual RMS sensitivity

Decision:
- Q fixed OR Q calibratable

---

### Task 3: PSO HOM Ensemble Stability

For selected calibrated baseline:
- run PSO with multiple seeds
- collect:
  - HOM frequencies
  - HOM Q values
  - HOM amplitudes
  - wake residual RMS

Compute:
- variance across seeds
- mode clustering stability

---

### Task 4: Envelope Validation

Compute:
- Z_mean(f)
- Z_std(f)

Check:
- CST impedance lies within envelope (secondary only)

---

## Required Outputs
Generate report:

.agent/specs/known_mode_pss_wake_inversion_system_v1_validation_report.md

Must include:
- calibration stability plots
- Q sensitivity curves
- ensemble variance tables
- envelope plots
- pass/fail evaluation of system spec

---

## Final Decision Criteria
PASS if:
- f_cal stable (<0.1 MHz variation)
- RQ_cal stable (<10%)
- Q weakly identifiable or consistent prior
- ensemble variance bounded
- no seed-dependent physics divergence

FAIL otherwise

---

## Important Rule
Reconstructed impedance |Z| MUST NOT be used as primary decision metric.
Only wake-domain and ensemble stability matter.
