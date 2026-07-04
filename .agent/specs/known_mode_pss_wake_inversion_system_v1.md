# Known-mode PSO Wake Inversion System Spec v1.0

## 0. Purpose

This document defines the formal system specification for the Workflow 2
known-mode PSO wake inversion pipeline.

It unifies:

- deterministic known-mode calibration
- PSO-based HOM fitting
- uncertainty / ensemble analysis
- CST-consistency validation

This is a SYSTEM SPECIFICATION, not an implementation plan.

---

## 1. System Overview

We define the inverse problem.

### Forward Model (Conceptual)

A wakefield system generates:

```text
wake(t) = sum(known_modes) + sum(HOM_modes) + noise
```

### Inverse Problem Goal

Given CST wake data, recover:

- calibrated fundamental mode
- HOM resonator set
- uncertainty bounds

The recovered system is valid only if wake-domain calibration and ensemble
stability are demonstrated. Reconstructed impedance overlays are secondary
diagnostics.

---

## 2. Core Insight From P05

P05 empirical results show:

- known-mode frequency can have a systematic offset at the `0.1 MHz` scale;
- `R/Q` has a convention mismatch, with the factor-of-two ambiguity resolved
  by projection for the current wake convention;
- Q is weakly identifiable from the long wake tail;
- reconstructed impedance is not a stable objective by itself.

Therefore:

> The system is partially identifiable only after deterministic calibration.

Run-to-run calibrated frequency offsets are not automatically failures. They
are expected evidence that the calibration layer is measuring the effective
fundamental in each CST run.

---

## 3. System Decomposition

### 3.1 Deterministic Calibration Layer

Input:

- CST wake tail
- eigenmode prior `(f0, Q0, R/Q0)`
- selected fit-start policy

Output:

- `f_calibrated`
- `RQ_calibrated`
- wake-domain residual metrics
- calibration stability diagnostics

Definition:

For each candidate frequency in a bounded search window, synthesize the known
fundamental wake with Q fixed to the prior and compute:

```text
scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)
RQ_calibrated = RQ_prior * scale
residual = target_wake - scale * known_wake
```

Then choose:

```text
f_calibrated = argmin residual_rms
```

over the bounded frequency grid. The calibrated `R/Q` is the scalar projection
at `f_calibrated`.

Q remains fixed unless a dedicated Q-identifiability test demonstrates a
sharp, stable, physically interpretable optimum across runs and selected
starts.

---

### 3.2 PSO Layer: HOM Inversion

After calibration:

```text
wake_residual = wake - known_mode_calibrated
```

Optimization variables:

- HOM amplitude `A_i`
- HOM quality factor `Q_i`

Fixed quantities:

- HOM frequencies from peak detection or a validated peak source
- calibrated known-mode frequency
- calibrated known-mode `R/Q`
- known-mode Q prior

The PSO layer must not absorb the calibrated fundamental into the unknown HOM
mode list.

---

### 3.3 Ensemble Layer: Uncertainty Quantification

Run PSO over:

- multiple deterministic seeds
- selected stable fit starts
- optionally multiple equivalent optimizer settings

Output:

- wake residual metric distribution
- HOM mode clustering statistics
- HOM amplitude / Q / derived `R/Q` spread
- bound-hit statistics
- optional reconstructed impedance `Z_mean(f)` and `Z_std(f)`

If peak frequencies are fixed by peak detection, frequency clustering is
expected to be stable by construction. In that case, ensemble stability is
judged primarily by wake residuals, fitted HOM amplitudes, HOM Q values,
derived `R/Q`, and bound-hit behavior.

---

### 3.4 Envelope Validator: Secondary Diagnostic

The reconstructed impedance envelope is a consistency diagnostic:

```text
Z_mean(f), Z_std(f), and optional percentile bands
```

It can flag suspicious cases for review, but it is not the primary acceptance
gate unless a later phase validates that the CST sampled impedance and the
reconstructed resonator-sum impedance are equivalent for this workflow.

Primary acceptance remains:

```text
PASS if:
  calibration_stable == true
  AND wake_residual_stable == true
  AND ensemble_wake_variance_bounded == true
```

Reject otherwise.

---

## 4. Key System Properties

### 4.1 Identifiability Constraints

- Q is weakly identifiable; treat it as a prior by default.
- Frequency can be biased relative to the eigenmode prior; calibrate it within
  a bounded window.
- `R/Q` is convention-sensitive; use projection-based correction and report the
  calibrated effective value separately from the user-supplied prior.
- Fit-start choice is part of the inverse problem. Stability should be assessed
  over selected starts, not hidden behind one late-tail optimum.

---

### 4.2 Non-objective Quantities

The following MUST NOT be used as primary optimization targets:

- reconstructed impedance `|Z(omega)|` matching CST sampled impedance

They are only:

- diagnostic overlays
- consistency checks
- warnings for human review

---

## 5. Stability Conditions

System stability is evaluated on selected stable fit starts, not on every
exploratory start. Very early starts can contain broadband/short-range
structure; very late starts can discard HOM information.

### 5.1 Calibration Stability

For each run:

```text
selected-start f_cal variation <= 0.1 MHz
selected-start RQ_cal variation < 10%
```

Across runs:

- report the global `f_cal` distribution descriptively;
- do not fail solely because different CST runs prefer different calibrated
  frequencies within the bounded search window;
- fail only if the distribution is inconsistent with a defensible calibration
  and fit-start policy.

### 5.2 Q Stability

Q is considered fixed if:

- residual RMS changes only weakly over the Q sweep; or
- the best Q is inconsistent across runs/starts; or
- Q changes appear to fit residual structure rather than a stable physical
  damping rate.

Q may be considered calibratable only if:

- the residual curve has a sharp optimum;
- the optimum is stable across runs and selected starts;
- the inferred Q is physically interpretable for the CST setup.

### 5.3 HOM Ensemble Stability

For calibrated HOM PSO, require:

- wake residual RMS and normalized error to remain bounded across seeds;
- wake correlation to remain high for selected starts;
- no seed-dependent bifurcation in physically meaningful HOM mode groups;
- bound hits to be reported and treated as instability evidence when frequent.

The exact numerical ensemble thresholds must be specified by the validation
phase before declaring a strict production PASS. Until then, ensemble results
can support a conditional PASS, warning, or FAIL based on the reported spread.

---

## 6. Failure Modes

- mode mixing, where the fundamental is absorbed into HOMs;
- PSO seed bifurcation in wake-domain residuals or HOM parameters;
- impedance overfitting;
- start-dependent solutions without a defensible selected-start interval;
- Q calibration that follows residual structure rather than physical damping;
- treating single-run reconstructed impedance as authoritative.

---

## 7. Final System Interpretation

This system is NOT:

- a curve fitting tool;
- an impedance optimizer;
- a single-seed PSO result generator.

It IS:

- a constrained inverse problem solver with calibration layer and ensemble
  uncertainty quantification.

---

## 8. Recommendation

Production usage requires:

1. deterministic frequency and scalar `R/Q` calibration;
2. fixed-Q prior unless Q identifiability is proven;
3. selected-start stability policy;
4. PSO HOM ensemble stability;
5. reconstructed-impedance envelope review as a secondary diagnostic.

Production usage must not rely on:

- single-run impedance matching;
- a hidden best fit start chosen only by minimum residual;
- Q fitting without identifiability evidence.
