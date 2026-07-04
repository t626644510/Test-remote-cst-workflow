# Known-mode PSO Wake Inversion System Spec v1.0

## 0. Purpose
This document defines the formal system specification for the Workflow 2 known-mode PSO wake inversion pipeline.

It unifies:
- deterministic known-mode calibration
- PSO-based HOM fitting
- uncertainty / ensemble analysis
- CST-consistency validation

This is a SYSTEM SPECIFICATION, not an implementation plan.

---

## 1. System Overview

We define the inverse problem:

### Forward model (conceptual)
A wakefield system generates:

```
wake(t) = Σ known_modes + Σ HOM_modes + noise
```

### Inverse problem goal
Given CST wake data:

```
recover:
- calibrated fundamental mode
- HOM resonator set
- uncertainty bounds
```

---

## 2. Core Insight (P05 result)

From P05 empirical results:

- known-mode frequency has systematic bias (~0.1 MHz scale)
- R/Q has convention mismatch (~factor ~2 resolved via projection)
- Q is not identifiable from wake tail
- reconstructed impedance is NOT a stable objective

Therefore:

> The system is partially identifiable only after calibration.

---

## 3. System Decomposition

### 3.1 Deterministic Calibration Layer

Input:
- CST wake tail
- eigenmode prior (f0, Q0, R/Q0)

Output:
- f_calibrated
- RQ_calibrated

Definition:
```
(f_cal, RQ_cal) = argmin residual(wake_tail)
```
subject to bounded frequency search.

---

### 3.2 PSO Layer (HOM inversion)

After calibration:

Input:
- wake_residual = wake - known_mode_calibrated

Optimization:
- amplitude A_i
- quality factor Q_i (HOM only)

Fixed:
- frequencies from peak detection
- known-mode parameters

---

### 3.3 Ensemble Layer (uncertainty quantification)

Run PSO over:
- multiple seeds
- multiple initializations

Output:
- Z_mean(f)
- Z_std(f)
- mode clustering statistics

---

### 3.4 Envelope Validator (system gate)

Define acceptance:

```
PASS if:
  wake_residual_stable == true
  AND calibration_stable == true
  AND ensemble_variance < threshold
```

Reject otherwise.

---

## 4. Key System Properties

### 4.1 Identifiability constraints
- Q is weakly identifiable → treated as prior
- frequency is weakly biased → must be calibrated
- R/Q is convention-sensitive → projection-based correction required

---

### 4.2 Non-objective quantities
The following MUST NOT be used as primary optimization targets:
- reconstructed impedance |Z(ω)| matching CST

They are only:
- diagnostic overlays
- consistency checks

---

## 5. Stability Conditions

System is considered stable if:

```
|f_cal variation| < 0.1 MHz
|RQ_cal variation| < 10%
wake_corr > 0.995
```

across:
- fit starts
- runs
- PSO seeds

---

## 6. Failure Modes

- mode mixing (fundamental absorbed into HOM)
- PSO seed bifurcation
- impedance overfitting
- start-dependent solutions

---

## 7. Final System Interpretation

This system is NOT:
- a curve fitting tool
- an impedance optimizer

It IS:
- a constrained inverse problem solver with calibration layer + ensemble uncertainty quantification

---

## 8. Recommendation

Production usage requires:

1. deterministic calibration layer
2. PSO HOM ensemble stability
3. envelope-based validation

NOT single-run impedance matching.
