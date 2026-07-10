# RF-CEM Parametric Geometry Status

Last updated: 2026-07-07

## Current Architecture Position

The current RF-CEM parametric geometry work sits between reviewed geometry semantics and CSTTranslator:

```text
reviewed_feature_labels.yaml
  -> expert_prior.v0.yaml
  -> parametric_geometry.v0.json
  -> generated_vacuum.step
  -> CSTTranslator eigenmode setup
```

This matches the original RF-CEM architecture direction:

- Feature graph / assembly graph: records what each solid/face means.
- Expert prior / grammar: records how domain knowledge turns features into parameters.
- Parametric geometry: records the run truth source.
- Solver interface: imports generated geometry and applies verified CST templates.

## Completed

- 500 MHz no-CST parametric geometry pipeline.
- CadQuery/OCP worker isolation for STEP generation and mesh payload.
- `generated_vacuum.step` export.
- `parametric_geometry.v0.json` truth source.
- Geometry validation report.
- CSTTranslator payload using generated STEP.
- Audit HTML rendering generated STEP, parameters, features, rules, risks, and Translator impact.
- External expert prior interface with built-in, case, and CLI override precedence.
- Resolved prior output beside each run.
- Real curve-based nose/blend recovery for the 500 MHz baseline:
  - `iris_torus_exact` uses torus-derived arcs and the expert nose rule: 10 mm semicircle, reversed 10 mm quarter arc, then tangent return to the conductive wall.
  - `expanded_smooth_nose` uses local smooth NURBS-like nose controls while retaining blend/equator evidence.
- Configurable curve selection through `expert_prior.v0.yaml`:
  - `grammar.variant_policy.enabled_variants`
  - `grammar.variant_policy.default_selected_variant`
  - `grammar.variant_policy.curve_selection`
  - `grammar.variant_policy.curve_parameters`
- `free_equator_smooth` is the current working baseline. It replaces the conventional constant-radius equator cylinder with a configurable local equator crown curve.
- Manual equator perturbation variants are generated for visual inspection:
  - `manual_equator_inset_3mm`
  - `manual_equator_bulge_3mm`
  - `manual_equator_wide_soft`
- Curve controls are promoted into `derived_parameters` in `parametric_geometry.v0.json`, including arc centers/radii/angles, NURBS control points, and normalized shared controls such as `shared_equator_crown_delta_r_mm`.
- `variant_index.json` and `audit/variant_comparison.html` summarize the generated variants and selected working baseline.
- RF-CEM 500 MHz no-CST parameter scan adapter exists under `workflows/rf_cem_500mhz_parametric_opt`.
- Baseline-difference validation severity is configurable through `validation.baseline_difference_policy`; the current optimization phase treats bbox/volume/surface differences as warnings rather than hard blockers.
- CST postprocessing/result-template evidence has been traced outside `ModelHistory.json`; the verified registration path is `Model/3D/Model.rpp + Model/3D/*.r0d`. See `docs/rf_cem_cst_postprocessing_template_notes.md`.
- Live-CST has validated result-template registration, automatic template evaluation after solver run, and `ResultReader` scalar readback for:
  - `Tables\0D Results\Frequency (Mode 1)`
  - `Tables\0D Results\R over Q (Mode 1)`
  - `Tables\0D Results\Q-Factor (Perturbation) (Mode 1)`
- The currently successful 500 MHz eigenmode automation path uses `Tetrahedral` mesh / `Solver_HF_TET_E`, not HEX.
- CSTTranslator now separates material/boundary semantics into two layers:
  - Global background material is set to the history-verified `Copper (annealed)` lossy metal, conductivity `5.8e7 S/m`, representing the conducting cavity wall outside the vacuum model.
  - After STEP import, the imported RF vacuum body is assigned to CST `Vacuum` material through the verified `Solid.ChangeMaterial` history command.
- Live-CST has validated copper background + vacuum solid + Tetrahedral eigenmode readback:
  - Frequency: `505.583944055 MHz`
  - R over Q: `428.086330643 Ohm`
  - Q-Factor (Perturbation): `45867.1264209`

## Not Yet Done

- CAD-native NURBS export is still not guaranteed for every smooth variant. Some smooth profiles intentionally fall back to dense sampled profiles and record that fallback in validation.
- Equator free-curve physical bounds and optimization ranges are still provisional.
- Live-CST parameter scan over derived curve controls.
- Multi-cell grammar.
- Non-axisymmetric geometry generation.
- Face-level CST boundary assignment.
- HOM, coupler, wakefield, cooling, thermal, structural, multipacting, optimizer.
- Batch live-CST evaluator for optimizer samples. Single-point live-CST diagnostics work, but parameter-scan execution is not yet productionized.
- Systematic live-CST comparison for `free_equator_smooth` and manual perturbation variants.

## Current Working Baseline

The current working baseline is:

```text
runs/parametric_geometry_500mhz/variants/free_equator_smooth
```

The top-level compatibility package under `runs/parametric_geometry_500mhz/geometry`, `metadata`, `translator`, and `audit` is copied from `free_equator_smooth`.

Current variant roles:

| Variant | Role | Validation intent |
|---|---|---|
| `iris_torus_exact` | Evidence-exact reference. | Should closely reproduce the original 500 MHz STEP nose/blend geometry. |
| `expanded_smooth_nose` | Smooth nose reference. | Keeps a smoother nose while preserving the conventional equator. |
| `free_equator_smooth` | Current working baseline. | Uses smooth nose plus configurable equator crown. |
| `manual_equator_inset_3mm` | Manual visual perturbation. | Demonstrates equator inward crown effect; baseline-difference thresholds are warning-only in exploratory mode. |
| `manual_equator_bulge_3mm` | Manual visual perturbation. | Demonstrates equator outward crown effect; baseline-difference thresholds are warning-only in exploratory mode. |
| `manual_equator_wide_soft` | Manual visual perturbation. | Demonstrates wider, softer equator inward crown; baseline-difference thresholds are warning-only in exploratory mode. |

## Semantic Risk Register

| Risk | Control |
|---|---|
| Expert natural language is translated into the wrong YAML field. | Use `docs/rf_cem_expert_prior_schema.md`, schema validation, resolved prior output, and audit HTML. |
| Feature labels conflict with expert prior mappings. | Required mappings fail clearly; provenance and confidence are recorded. |
| Prior configuration becomes too free-form. | v0 only supports declared extraction methods and segment templates; no eval or arbitrary formulas. |
| Geometry looks plausible but is physically wrong. | Geometry validation and live-CST eigenmode validation remain required. |
| Prior unexpectedly changes CST setup. | v0 prior only changes generated STEP and metadata. CST boundary/solver templates remain historical-template driven. |
| Baseline-difference thresholds accidentally block novel cavity shapes. | `validation.baseline_difference_policy` now makes bbox/volume/surface differences warning-only for exploratory optimization; BRep/profile topology remain hard gates. |
| Dense sampled fallback may hide the difference between mathematical NURBS intent and exported STEP representation. | Record `source_kernel_curve_generation_mode`, fallbacks, and derived curve controls in validation and audit artifacts. |
| CST postprocessing templates are absent from `ModelHistory.json`. | Use unpacked CST project evidence: `Model/3D/*.r0d`, `Model/PC_integration.json`, `Result/Postprocessing.log`, and explicit result tree paths. |
| Copying `.r0d` files alone does not register GUI/result-template steps. | Write `Model/3D/Model.rpp` records together with the `.r0d` files. |
| `QFactor.Calculate` can emit the misleading message `HEX mesh is invalid`. | First check template registration, imported-body material, stale result state, and solver completion. The validated path remains Tetrahedral; do not auto-switch to HEX without an explicit mesh policy. |
| Vacuum STEP import with default/air background shifts the physical model away from the intended conducting cavity. | Treat global conducting background as part of the boundary/material policy. The current default is the history-verified `Copper (annealed)`. |

## Human Confirmation Items

- Final frequency tolerance for generated-vs-baseline eigenmode comparison.
- Nose/blend local geometric tolerance.
- Equator free-curve allowable range and physical constraints.
- Which manual equator perturbations should become optimization seeds.
- Which mode-shape comparison evidence is acceptable.
- Whether future priors should support asymmetric left/right segment templates as a required case.
- Final hard-gate policy for exploratory geometry beyond BRep/profile validity.
- Frequency/R over Q/Q-factor objective weights, constraints, and failed-sample handling for optimizer runs.
- Whether solver mesh policy should be externalized into expert prior / workflow config. Current default remains the historical-template Tetrahedral eigenmode setup.
- Whether background material should become configurable among `Copper (annealed)`, OFHC copper, and PEC. The current MVP default is `Copper (annealed)` because it has history-tree and live-CST evidence.

## Maintenance Rule

Update this document when any of the following changes:

- `expert_prior.v0.yaml` schema shape.
- Feature-to-parameter mapping semantics.
- Curve selection policy or curve parameter semantics.
- `derived_parameters` contract.
- Generated design package contract.
- CSTTranslator consumption contract.
- Scope boundary, especially if face-level boundaries or additional solvers are introduced.
