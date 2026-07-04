# S01 Known-Mode PSO Wake Fitting Closure Report

## Status

This document is the canonical closure record for stage
`S01-known-main-mode-pso`.

Use this report as the single current handoff document. Earlier phase reports,
reviews, feasibility notes, validation reports, and operational-contract drafts
remain historical evidence, but they should not be used as independent decision
documents without this closure context.

Closure branch:

```text
codex/S01-known-mode-pso-closure
```

Historical phase branches:

```text
phase/S01-P01-fixed-mode-core
phase/S01-P02-objective-config-integration
phase/S01-P03-diagnostics-and-stage-validation
phase/S01-P04-direction-2-feasibility-spike
phase/S01-P05-known-mode-calibration-stability
```

## Executive Conclusion

The known-mode PSO work produced a useful production capability, but it did not
produce a unique, decision-grade HOM inversion method.

The accepted production capability is Direction 1:

- longitudinal known modes can be supplied to Workflow 2 PSO wake fitting;
- known modes are fixed inputs and are not optimized by PSO;
- PSO fits only remaining unknown HOM peaks;
- result diagnostics separate known-mode wake, unknown-mode wake, total fit,
  residual wake, normalized error, and wake correlation.

The rejected or deferred capability is using a single PSO fit, or a single
reconstructed impedance curve, as a physics acceptance criterion.

The practical conclusion is:

```text
Known-mode PSO fitting is a wake-domain diagnostic and residual-analysis tool.
It is not, by itself, a unique HOM parameter inversion or final pass/fail gate.
```

## Production Capability That Exists

Implemented and tested behavior:

1. `KnownMode` represents fixed known resonator data:
   - `frequency_hz`
   - `q`
   - `r_over_q_ohm`
   - `frequency_tolerance_hz`
   - `include_in_reconstructed_impedance`
2. Known-mode wake is synthesized from the same amplitude convention used by
   fitted modes:

   ```text
   A = (R/Q) * form_factor(f, sigma_z) * 2*pi*f / wake_charge_scale
   ```

3. Known-mode wake is included in the total wake comparison.
4. Peaks matching known modes are filtered out of the unknown HOM PSO list.
5. PSO optimizes only unknown HOM amplitudes and Q values.
6. Reconstructed impedance can include known-mode contributions when requested.
7. `WakeFitResult` exposes:
   - `known_mode_wake`
   - `unknown_mode_wake`
   - `residual_wake`
   - `diagnostics`
8. Config integration exists through:

   ```yaml
   obj_params:
     pso_fit:
       known_modes:
         - label: fundamental
           frequency_hz: ...
           q: ...
           r_over_q_ohm: ...
   ```

9. Known modes are longitudinal-only in this stage. Transverse known modes are
   intentionally unsupported.

Targeted no-CST regression reached:

```text
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
38 passed
```

## Current Non-Capabilities

The current production implementation does not:

- calibrate known-mode frequency;
- calibrate known-mode `R/Q`;
- calibrate known-mode Q;
- fit known-mode parameters with PSO;
- implement Direction 2 full-wake residual-to-impedance production logic;
- change CST result reading APIs;
- change Workflow 2 scalarization semantics;
- support transverse known modes.

`frequency_tolerance_hz` only filters detected peaks near a known mode. It does
not update the known-mode frequency.

## Empirical Findings From Existing Long-Wake CST Data

Data used:

```text
D:\workflow2\Before_rebuild_backup\F2W.cst
D:\workflow2\Before_rebuild_backup\F2W
```

Longitudinal result paths:

```text
1D Results\Particle Beams\ParticleBeam1\Wake potential\Z
1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z
1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)
```

Runs inspected:

```text
1..20, with detailed focus on 1, 5, 10, 20
```

Observed units:

- wake axis: `s / mm`, converted to m
- wake value: `Wl(s) / V/pC`
- impedance axis: `Frequency / MHz`, converted to Hz
- impedance value: `Z / Ohm`
- estimated bunch RMS length: `sigma_z_m = 0.07 m`

### R/Q Convention

The input `R/Q = 208.6 ohm` overpredicts the fixed fundamental wake amplitude
by about a factor of two in the current implementation convention.

The current longitudinal wake-fitting convention is closer to:

```text
R/Q input convention: about 104.3 ohm to 104.6 ohm
effective projected R/Q: about 100.6 ohm for this CST data
```

This does not mean the external design value is wrong. It means the numerical
definition used by this wake-fitting path matches the half-convention.

### Fundamental Frequency

Deterministic sweeps over the existing long-wake data found stable effective
fundamental frequencies by run, roughly:

| Run | Effective frequency |
|---:|---:|
| 1 | `499.80-499.81 MHz` |
| 5 | `500.025-500.03 MHz` |
| 10 | `499.94-499.95 MHz` |
| 20 | `499.77-499.775 MHz` |

This supports deterministic calibration as a diagnostic or future optional
pre-fit step. It also means blindly fixing every run to exactly `499.8 MHz`
can leave residual structure for PSO to absorb.

### Q Identifiability

The fundamental `Q = 36500` is weakly identifiable from these wake tails.

Q sweeps over:

```text
10000, 20000, 36500, 60000, 100000
```

changed residuals only weakly and often preferred lower Q values in ways that
look like residual-structure absorption rather than a robust physical damping
measurement.

Closure decision:

```text
Keep known-mode Q fixed to the prior, e.g. 36500.
Do not calibrate Q from this wake-tail method without new evidence.
```

### Fit Start

Very late starts can minimize known-only residual by discarding HOM content.
That is not the same as producing a better HOM inversion.

Current practical policy:

- use `2 m` as the conservative long-wake longitudinal start;
- inspect `1 m` as a companion start when early HOM content matters;
- use `5 m` to `10 m` as secondary stability checks;
- do not select `40 m` merely because known-only residual is smallest.

## Bounded Calibration Experiment

A local scratch experiment tested the user's proposed bounded calibration:

```text
frequency: 499.8 MHz +/- 0.5 MHz
frequency step: 10 kHz
Q: fixed 36500
R/Q prior: 104.6 ohm
R/Q bound: 104.6 +/- 5 ohm
runs: 1, 5, 10, 20
fit starts: 1 m, 2 m, 5 m
seeds: 4 per run/start
```

Result:

- `R/Q` never hit the bound.
- Projected `R/Q` naturally landed around `100.7-100.9 ohm`.
- Per-run fundamental frequency was stable.
- Wake-domain residuals improved, especially for run 10 at `1 m`.
- HOM Q values still frequently hit bounds and remained non-unique.

Interpretation:

```text
Bounded calibration improves wake-domain stability.
It does not make the HOM parameter decomposition unique.
```

The scratch scripts and plots are local-only under:

```text
analysis_outputs/wf2_known_mode_bounded_calibration/
```

They are intentionally not committed.

## Why The Current Method Is Not A Final Decision Gate

Even with known fundamental pre-input and bounded calibration, the HOM PSO
problem remains partially identifiable.

Reasons:

1. Multiple HOM amplitude/Q combinations can explain the same wake tail.
2. Fitted HOM Q values often hit lower or upper bounds.
3. Reconstructed impedance can vary strongly while wake residual remains good.
4. CST sampled impedance and resonator-sum reconstructed impedance are not yet
   validated as equivalent post-processing products.
5. Fit-start choice affects what residual structure is visible to PSO.
6. The fundamental high-Q mode does not decay away over practical wake length,
   so small frequency errors can persist across the full tail.

Therefore:

```text
Accept wake-domain residual stability as useful evidence.
Do not accept single-run HOM Q/RQ or single reconstructed |Z| as decisive.
```

## Canonical Acceptance Levels

Highest confidence:

- calibrated or fixed fundamental contribution;
- wake-domain residual RMS;
- normalized wake residual error;
- wake correlation;
- stability of these metrics across selected starts and seeds.

Medium confidence:

- repeated HOM frequency groups from fixed peak detection;
- ensemble-level unknown-mode contribution;
- qualitative residual structure after known-mode subtraction.

Low confidence:

- single-seed HOM Q;
- single-seed HOM `R/Q`;
- single reconstructed `|Z|` curve;
- absolute agreement between reconstructed `|Z|` and CST sampled impedance.

## Recommended Use Going Forward

Current production use should be limited to:

1. Configure known longitudinal fundamental mode.
2. Use `R/Q` convention near `104.3-104.6 ohm`, not `208.6 ohm`, for this wake
   fitting path.
3. Keep Q fixed to `36500`.
4. Use unknown HOM peak search above the fundamental, e.g. `freq_min_hz >=
   550e6`.
5. Inspect `known_mode_wake`, `unknown_mode_wake`, `residual_wake`, and
   diagnostics.
6. Treat PSO output as diagnostic evidence, not a final scalar pass/fail.

If future production work continues, the smallest defensible next step is an
optional diagnostic calibration layer:

- bounded frequency sweep around the known prior;
- scalar bounded `R/Q` projection;
- fixed Q;
- selected-start stability report;
- HOM PSO ensemble report;
- no scalarization change;
- no CST API change.

This should be implemented only as optional diagnostic or pre-fit calibration,
not as an implicit hidden mutation of user-supplied known-mode values.

## Branch Closure

Use this branch as the single closure branch:

```text
codex/S01-known-mode-pso-closure
```

Historical branches remain preserved as evidence:

| Branch | Closure role |
|---|---|
| `phase/S01-P01-fixed-mode-core` | production core support |
| `phase/S01-P02-objective-config-integration` | config wiring |
| `phase/S01-P03-diagnostics-and-stage-validation` | diagnostics and no-CST validation |
| `phase/S01-P04-direction-2-feasibility-spike` | Direction 2 feasibility evidence |
| `phase/S01-P05-known-mode-calibration-stability` | CST replay, calibration stability, spec validation |

The branch closure decision is:

```text
Do not continue proliferating phase branches for this line of work unless a new
stage is explicitly opened with a narrower objective.
```

## Final Limitation Statement

The known-mode PSO wake fitting module is production-usable for Workflow 2 as a
longitudinal wake-domain diagnostic with fixed known modes.

It is not production-usable as a unique HOM inversion system or standalone
acceptance gate.

Any report or workflow using this module should state:

```text
The fitted HOM parameters are one ensemble-compatible explanation of the wake
tail, not a uniquely identified physical modal decomposition.
```

