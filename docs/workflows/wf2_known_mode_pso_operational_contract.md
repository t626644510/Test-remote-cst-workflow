# WF2 Known-Mode PSO Operational Contract v1.1

Revised: 2026-07-10

## Classification

This module is a longitudinal wake-domain diagnostic and residual-analysis
tool. It is not a unique physical modal inversion and must not be used alone as
a final pass/fail gate.

## Inputs and units

- Known-mode frequency: Hz.
- Known-mode Q: dimensionless and strictly greater than 0.5.
- Known-mode R/Q: ohm, using the convention documented for the dataset.
- Wake distance: meters after CST input-unit conversion.
- Unknown-HOM frequency windows: Hz.

Known modes are fixed inputs. The implementation does not calibrate or mutate
their frequency, Q, or R/Q.

## Default unknown-HOM fit

Detected unknown HOM frequencies remain fixed. PSO variables are packed as:

```text
[A1, Q1, A2, Q2, ...]
```

Peaks matching a configured known mode are filtered before optimisation.

## Optional bounded frequency fit

The option is explicit and disabled by default:

```yaml
obj_params:
  pso_fit:
    frequency_fit:
      enabled: true
      half_width_hz: 500000.0
      overlap_policy: reject
```

When enabled, only unknown longitudinal HOM modes change to:

```text
[f1, A1, Q1, f2, A2, Q2, ...]
```

Each `f` stays inside the symmetric window around its detected peak. Windows
must not overlap. Transverse frequency fitting and automatic overlap resolution
are unsupported and fail closed.

## Required diagnostics

Every successful result records:

- known-mode, unknown-mode, and residual wake;
- normalized wake error and wake correlation;
- initial and fitted unknown-HOM frequencies in Hz;
- per-mode frequency shift and effective frequency window;
- fitted Q and R/Q values with the existing identifiability limitation.

## Acceptance boundary

Useful evidence includes wake-domain residual stability across selected fit
starts and seeds, stable frequency groups, and bounded ensemble behaviour.
Single-seed Q, R/Q, or reconstructed impedance is not decision-grade evidence.

Every scientific report must state:

```text
The fitted HOM parameters are one ensemble-compatible explanation of the wake
tail, not a uniquely identified physical modal decomposition.
```
