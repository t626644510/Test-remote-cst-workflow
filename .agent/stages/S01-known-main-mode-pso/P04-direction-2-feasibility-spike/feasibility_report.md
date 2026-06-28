# Feasibility Report: Direction 2 — Full-Wake Main-Mode Subtraction

## Scope Statement
This report was produced during phase `P04-direction-2-feasibility-spike`, a no-CST research spike. No production code, tests, CST API, `src/cst_optimization/`, wakefield objective, or scalarization semantics were modified.

## Synthetic Experiment Design

### Mode Table

| Mode | Label | Frequency (GHz) | Q | R/Q (ohm) | A (V/pC) | Source |
|------|-------|----------------|----|-----------|----------|--------|
| 0 | fundamental | 0.4998 | 36500 | 208.6 | 0.6548 | Known (will be subtracted) |
| 1 | HOM1 | 1.500 | 1000 | 50.0 | 0.4691 | Unknown (target for recovery) |
| 2 | HOM2 | 2.200 | 500 | 30.0 | 0.4107 | Unknown (target for recovery) |

Wake parameters: `sigma_z = 3 mm`, `wake_charge_scale = 1e12` (V/pC), Gaussian bunch form factor.

## Experiment 1: Exact Subtraction

**Procedure**: Generate full wake = fund + HOM1 + HOM2. Subtract exact known fundamental. Compare residual to HOM-only truth.

**Result**: Maximum difference = `1.1e-16` (floating-point precision). **Mathematically perfect.**

## Experiment 2: Perturbation Sensitivity

### Frequency Perturbation (df)

| Offset (MHz) | Residual vs HOM Diff RMS | Correlation | Normalized Error |
|-------------|--------------------------|-------------|------------------|
| +0.1 | 0.0028 | 0.999976 | 4.8e-5 |
| +0.5 | 0.0142 | 0.999400 | 1.2e-3 |
| +1.0 | 0.0284 | 0.997601 | 4.8e-3 |
| +5.0 | 0.1418 | 0.944710 | 0.120 |

**Interpretation**: Frequency errors produce a sinusoidal beat residual at the fundamental frequency. Even 0.1 MHz (0.02% relative) produces a measurable residual. The error grows approximately linearly with offset and accumulates wake length.

### Q Perturbation (dQ)

| Offset | Diff RMS | Correlation | Normalized Error |
|--------|----------|-------------|------------------|
| +500 | 2.6e-6 | 1.000000 | 3.9e-11 |
| +1000 | 5.1e-6 | 1.000000 | 1.5e-10 |
| +5000 | 2.3e-5 | 1.000000 | 3.1e-09 |
| +10000 | 4.1e-5 | 1.000000 | 9.9e-09 |

**Interpretation**: Q = 36500 is so high that the mode rings essentially undamped over any practical wake length. Small Q errors are negligible because the damping term `exp(-π f t / Q)` is close to 1 regardless.

### R/Q Perturbation (dR/Q)

| Offset (ohm) | Diff RMS | Correlation | Normalized Error |
|-------------|----------|-------------|------------------|
| +5 | 0.0110 | 0.999636 | 7.3e-4 |
| +10 | 0.0221 | 0.998547 | 2.9e-3 |
| +20 | 0.0442 | 0.994227 | 1.2e-2 |
| +50 | 0.1105 | 0.965483 | 7.3e-2 |

**Interpretation**: R/Q errors scale the fundamental amplitude linearly. A 10-ohm error (5% relative) creates a ~0.3% normalized residual, which may be acceptable for some applications. 50-ohm error (24%) is clearly problematic.

## Experiment 3: Fundamental Mode Decay

| Wake Length (m) | Envelope Decay at End |
|----------------|----------------------|
| 0.5 | 0.99993 (99.99%) |
| 5.0 | 0.99928 (99.93%) |
| 50.0 | 0.99285 (99.29%) |
| 100.0 | 0.98575 (98.58%) |
| 500.0 | 0.931 |

**Critical finding**: With Q = 36500 at 499.8 MHz, the fundamental mode NEVER decays appreciably within any practical CST wake length (typically <10 m). At 10 m, the envelope is still at 99.86% of its starting amplitude. This means:

1. The subtraction residual from a frequency error persists undiminished across the entire wake window.
2. Frequency error residual does not decay — it grows with length as the phase accumulates.
3. **The fundamental cannot be "rung out" by extending the wake window.**

## Experiment 4: Frequency Error vs Wake Length

| Freq Error (MHz) | Length 1m | Length 5m | Length 10m | Length 50m |
|-----------------|-----------|-----------|------------|------------|
| +0.1 | 5.3e-4 | 2.8e-3 | 5.6e-3 | 2.8e-2 |
| +0.5 | 2.7e-3 | 1.4e-2 | 2.8e-2 | 1.4e-1 |
| +1.0 | 5.3e-3 | 2.8e-2 | 5.6e-2 | 2.7e-1 |

The residual RMS **increases** with wake length because the frequency error creates a beat that accumulates phase. This is fundamentally different from a simple amplitude error — the perturbation produces a growing discrepancy.

## Experiment 5: Wake-to-Impedance Reconstruction from Truncated Residual

### Without window
- Residual wake at 2.0 m length produces hundreds of spurious impedance peaks due to spectral leakage from the abrupt truncation.
- The true HOM peaks at 1.5 and 2.2 GHz are visible among many artifacts.
- Baseline noise obscures weak/moderate HOM peaks.

### With Hann window
- Spurious peaks are dramatically reduced.
- True HOM peaks remain clearly visible.
- Peak amplitudes are reduced by the window (expected).
- Both 1.5 GHz and 2.2 GHz peaks are recovered within ~1-5 MHz of true frequencies.

### Key observation
The finite wake length sets the frequency resolution as `Δf ≈ 1 / T_wake`. For a 2 m wake (~6.7 ns): `Δf ≈ 150 MHz`. This means:
- Two closely-spaced HOMs (<150 MHz apart) cannot be resolved from a 2 m wake.
- HOM frequency recovery accuracy is fundamentally limited by wake length.
- A 2 m wake is marginal for the 1.5 and 2.2 GHz peaks (700 MHz apart — easily resolved).
- But if the HOMs were at 1.8 and 1.9 GHz, they would be unresolvable.

## Conditions Required Before Production Direction 2 Implementation

The following CST convention checks are **mandatory** before any production Direction 2 code:

1. **Wake sign convention**: Confirm CST wake potential sign matches the model's sign. A sign flip would make subtraction additive.
2. **Wake amplitude scale**: Confirm CST wake units (V/pC vs V/C) match the convention used in `wake_from_parameters`.
3. **Bunch form factor**: Confirm CST's actual bunch distribution matches the Gaussian assumption used for form-factor computation.
4. **Time zero / distance zero**: Confirm the CST wake time origin alignment with the model.
5. **Fundamental frequency accuracy**: Determine whether the CST-observed fundamental frequency matches the design frequency within <0.1 MHz. If not, Direction 2 frequency sensitivity will likely dominate the residual.
6. **R/Q definition**: Confirm the CST definition of R/Q (or shunt impedance) matches the longitudinal voltage convention used in the model.
7. **External loading effect**: Determine whether the wake simulation reflects loaded Q or unloaded Q. If loaded Q differs significantly from Q0, the decay rate changes.
8. **Numerical noise floor**: Characterize the CST wake potential's numerical noise level to distinguish meaningful residual from truncation/windowing artifacts.

## Recommendation

### CONDITIONAL-GO

**Condition**: If and only if the CST fundamental frequency can be determined to within **<0.1 MHz** and the sign/scale conventions match.

**Supporting evidence**:
- R/Q and Q perturbations are manageable (Q is robust; R/Q at 5-10% is acceptable).
- Frequency perturbation is the critical risk. A 0.5 MHz error creates a residual that is ~1.5% of the HOM signal, growing with wake length.
- Wake-to-impedance reconstruction from the residual is feasible with windowing, but frequency resolution is bounded by wake length.
- The high Q fundamental never decays, so frequency accuracy is the only lever for clean subtraction.

**If frequency accuracy cannot be guaranteed <0.1 MHz**: **NO-GO** — the frequency error residual will mask HOM content and degrade impedance reconstruction.

**If frequency accuracy is confirmed**: Direction 2 can proceed as a controlled experiment with:
- Hann windowing of the residual before impedance reconstruction.
- Explicit reporting of the known-mode residual level alongside HOM recovery metrics.
- A CST-exported validation case as the first implementation milestone.

## Assumptions

- The Gaussian bunch form factor is a reasonable approximation for the CST bunch distribution.
- The wake potential is computed for a single bunch with the specified bunch length.
- The three-mode synthetic model captures the dominant physical effects relevant to feasibility.
- The `_wake_to_impedance_linear` function produces the same frequency-domain results as a CST impedance calculation for the same wake input.

## Limitations

- No CST data was used; all conclusions are from synthetic data with perfectly known modes.
- Real CST wakes include numerical noise, discretisation effects, and possibly non-modal broadband components not modelled here.
- Only longitudinal wakes were tested; transverse subtraction would introduce additional sign and polarisation complications.
- The synthetic wake uses the same form-factor and resonator model as the analysis code — this eliminates model-mismatch errors that would exist with real CST data.
