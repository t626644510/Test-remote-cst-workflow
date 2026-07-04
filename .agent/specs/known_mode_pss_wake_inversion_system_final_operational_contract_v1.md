# Known-mode PSO Wake Inversion System — Final Operational Contract v1.0

## 0. Purpose
This document defines the **final operational contract** for the Workflow 2 known-mode PSO wake inversion system.

It converts prior research phases (P01–P05) into a **decision-grade system specification**.

---

## 1. System Classification

This system is:

> A calibrated inverse modeling system for wake-field decomposition using known-mode subtraction + PSO HOM inversion + ensemble uncertainty quantification.

It is NOT:
- a curve-fitting tool
- a single-run optimizer
- an impedance-matching engine

---

## 2. Core System Pipeline

### Stage 1 — Deterministic Calibration (REQUIRED)

Input:
- CST wake tail
- eigenmode prior (f0, Q0, R/Q0)

Output:
- f_calibrated
- RQ_calibrated

Rule:
```
f and R/Q are NOT PSO variables
They are calibrated via bounded deterministic projection
```

Acceptance condition:
- frequency stability across runs
- projection residual minimization

---

### Stage 2 — HOM PSO Inversion (CONDITIONAL)

Input:
- residual_wake = wake - known_mode_calibrated

Optimization variables:
- HOM amplitudes A_i
- HOM Q_i (weakly constrained)

Fixed:
- HOM frequencies (from peak detection)
- known-mode parameters (calibrated)

Rule:
```
PSO operates ONLY in HOM subspace
Never reabsorbs fundamental mismatch
```

---

### Stage 3 — Ensemble Uncertainty Layer (MANDATORY)

Execution:
- multiple PSO seeds
- multiple initialization states

Outputs:
- Z_mean(f)
- Z_std(f)
- mode clustering statistics
- wake residual distribution

Rule:
```
Single-run solutions are NOT valid scientific outputs
Only ensemble statistics are valid
```

---

### Stage 4 — Envelope Validation Gate (FINAL DECISION LAYER)

Decision is based ONLY on wake-domain + ensemble stability.

### PASS criteria:
```
|f_cal std| < 0.1 MHz
|RQ_cal std| < 10%
wake_corr > 0.995
ensemble_variance bounded
no seed-dependent divergence
```

### FAIL criteria:
```
calibration drift unbounded
wake residual unstable
ensemble divergence across seeds
fundamental absorbed into HOM modes
```

---

## 3. Key System Invariants

### 3.1 Frequency Invariant
- frequency is a CALIBRATION parameter
- NOT a PSO optimization variable

### 3.2 Q Invariant
- Q is weakly identifiable
- default: FIXED PRIOR unless proven otherwise

### 3.3 R/Q Invariant
- R/Q is convention-sensitive
- must be corrected via projection calibration

---

## 4. Observability Principle

### Primary observable:
```
wake-domain residual stability
```

### Secondary observable:
```
reconstructed impedance envelope
```

### Forbidden as primary metric:
```
|Z(ω)| matching CST as optimization target
```

---

## 5. Identifiability Statement

This system is:

> PARTIALLY IDENTIFIABLE IN WAKE DOMAIN ONLY

and NOT uniquely identifiable in frequency-domain decomposition.

---

## 6. Failure Modes

- fundamental leakage into HOM PSO space
- seed-dependent mode decomposition
- impedance overfitting
- fit-start instability
- calibration drift

---

## 7. Final System Interpretation

This system is a:

> constrained inverse solver with deterministic calibration + stochastic HOM inversion + ensemble validation

NOT a curve fitting pipeline.

---

## 8. Operational Rule

A result is scientifically valid ONLY IF:

- calibration layer is stable
- PSO ensemble is stable
- wake residual is stable

Impedance agreement is optional and non-decisional.
