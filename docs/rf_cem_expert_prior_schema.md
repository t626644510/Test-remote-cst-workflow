# RF-CEM Expert Prior Schema v0

This document explains how domain-expert knowledge should enter the RF-CEM parametric geometry pipeline.

## Layer Separation

`reviewed_feature_labels.yaml` answers: what is this geometry?

Examples:

- this solid is `RFVacuumVolume`
- these faces are `BeamPipeLeft`
- these faces are `EquatorRegion`
- these faces are `NoseCone`

`expert_prior.v0.yaml` answers: how should the system interpret and model those features?

Examples:

- use beam-pipe cylindrical faces to define beam-pipe radius and length
- use equator faces to define the maximum cavity radius
- use nose and blend features as local spline fallback regions
- allow left/right asymmetry in the first single-cell grammar
- choose whether nose/equator regions use exact arcs, local smooth NURBS-like controls, or experimental crown curves
- define manual curve perturbation variants for visual inspection before optimization

`parametric_geometry.v0.json` records: what did this run actually use?

It is the run truth source. STEP files are export artifacts.

## File Locations

Built-in default prior:

```text
src/rf_cem/parametric_geometry/priors/axisymmetric_single_cell.v0.yaml
```

Case-level prior:

```text
Appendix/500MHz_baseline/expert_prior.v0.yaml
```

Optional CLI override:

```powershell
python -m rf_cem.build_500mhz_parametric_geometry --expert-prior path\to\expert_prior.v0.yaml
```

Precedence:

```text
CLI explicit prior > case prior > built-in prior > emergency fallback
```

Every run writes the merged prior to:

```text
metadata/resolved_expert_prior.v0.yaml
metadata/resolved_expert_prior.v0.json
```

## Required Sections

```yaml
schema_version: expert_prior.v0
model_family: axisymmetric_single_cell_rf_vacuum
units:
  length: mm
target_body: {}
axis: {}
feature_mappings: {}
grammar: {}
fit_policy: {}
validation: {}
interface_policy: {}
human_notes: {}
```

Unknown additive fields are preserved in the resolved prior, but they do not drive calculations unless the code supports them.

## Feature Mapping Rules

Each rule defines how one reviewed feature type becomes parameters and profile segments.

```yaml
feature_mappings:
  EquatorRegion:
    rule_id: feature.equator
    human_description: Equator faces provide the maximum RF cavity radius.
    consumes: maximum radial extent of tagged equator faces
    defines:
      - equator_radius
    parameter_ids:
      - equator_radius
    segment_ids:
      - seg_equator
    extraction: max_radial_extent
    confidence: 0.9
    required: true
    affects_generated_step: true
    affects_translator: false
    fallback_policy: use_model_bbox_radius
```

Supported `extraction` values in v0:

- `semantic_only`
- `bbox_span`
- `median_radius`
- `median_radius_and_max_z_span`
- `max_radial_extent`
- `half_local_radial_span`

Forbidden:

- Python code
- `eval`
- arbitrary formulas
- natural language as direct calculation input

Natural-language fields such as `human_description`, `consumes`, and `fallback_policy` are for experts, LLM conversion, and audit views. They do not execute.

## Grammar Rules

The single-cell v0 grammar has two layers:

- a legacy declared segment template list for simple fallback generation
- a curve-policy layer for supported 500 MHz variants

```yaml
grammar:
  variant_policy:
    default_selected_variant: free_equator_smooth
    enabled_variants:
      - iris_torus_exact
      - expanded_smooth_nose
      - free_equator_smooth
    curve_selection:
      nose:
        iris_torus_exact: smooth_semicircle_then_reverse_quarter_arc
        expanded_smooth_nose: local_nurbs_smooth_fallback
      equator:
        iris_torus_exact: cylinder
        free_equator_smooth: local_nurbs_crown
  profile_controls:
    beam_radius:
      source: parameter
      parameter: beam_pipe_radius_left
  segment_order:
    - seg_beam_pipe_left
    - seg_blend_left
    - seg_nose_left
    - seg_equator
    - seg_nose_right
    - seg_blend_right
    - seg_beam_pipe_right
  segment_templates:
    seg_equator:
      kind: line
      start: [-60.0, equator_radius]
      end: [60.0, equator_radius]
      feature_refs: [EquatorRegion]
      confidence: 0.9
```

Allowed segment kinds in v0:

- `line`
- `arc`
- `ellipse`
- `local_spline`
- `nurbs`

The current generator emits a stable r-z profile and revolves it around the z axis. Arc and NURBS-like curve controls are now part of the 500 MHz geometry authoring path. CAD-native NURBS export may still fall back to a dense sampled profile; this must be recorded in validation.

## Variant Policy

`grammar.variant_policy` controls which geometry branches are generated and which one is copied to the top-level compatibility package.

```yaml
grammar:
  variant_policy:
    default_selected_variant: free_equator_smooth
    enabled_variants:
      - iris_torus_exact
      - expanded_smooth_nose
      - free_equator_smooth
      - manual_equator_inset_3mm
    curve_selection:
      nose:
        iris_torus_exact: smooth_semicircle_then_reverse_quarter_arc
        free_equator_smooth: local_nurbs_smooth_fallback
      equator:
        iris_torus_exact: cylinder
        free_equator_smooth: local_nurbs_crown
        manual_equator_inset_3mm: local_nurbs_crown
```

Supported v0 curve choices:

- `smooth_semicircle_then_reverse_quarter_arc`: NoseCone rule confirmed for the 500 MHz baseline. From pipe, draw a 10 mm semicircle, then a reversed 10 mm quarter arc, then return tangent to the conductive wall.
- `local_nurbs_smooth_fallback`: Local smooth NURBS-like curve controls. Export may use dense sampled profile fallback.
- `cylinder`: Conventional constant-radius equator.
- `local_nurbs_crown`: Configurable equator crown curve with fixed endpoints and shared crown controls.

## Curve Parameters

Variant-specific curve parameters live under `grammar.variant_policy.curve_parameters`.

```yaml
grammar:
  variant_policy:
    curve_parameters:
      equator:
        free_equator_smooth:
          crown_radius_delta_mm: 0.0
          crown_z_mid_mm: 0.0
          shoulder_z_abs_mm: 30.0
        manual_equator_inset_3mm:
          crown_radius_delta_mm: -3.0
          crown_z_mid_mm: 0.0
          shoulder_z_abs_mm: 28.0
```

For `local_nurbs_crown`:

- `crown_radius_delta_mm` is added to the equator endpoint radius.
- `crown_z_mid_mm` defines the middle control point axial position.
- `shoulder_z_abs_mm` normalizes left/right shoulder control points as `-abs` and `+abs`.

Do not use arbitrary formulas. Add new named fields only when the generator explicitly supports them.

## Derived Parameters

`parametric_geometry.v0.json` contains two parameter sections:

- `named_parameters`: feature-derived physical dimensions, such as `beam_pipe_radius_left`, `equator_radius`, and `nose_radius_left`.
- `derived_parameters`: curve-control parameters promoted from generated profile segments.

Examples of `derived_parameters`:

```json
{
  "arc_radius__seg_blend_left": {
    "value": 75.05064728615,
    "unit": "mm",
    "parameter_role": "derived_curve_control",
    "optimization_candidate": true
  },
  "shared_equator_crown_delta_r_mm": {
    "value": -3.0,
    "unit": "mm",
    "normalization": "shared_symmetric_parameter",
    "optimization_candidate": true
  }
}
```

Derived parameters are allowed to drive later optimization, but they are not the same as reviewed Feature labels. Their provenance must point back to segment curve controls, expert prior rules, and feature/face evidence.

## Current 500 MHz Variants

Current generated variants:

| Variant | Purpose |
|---|---|
| `iris_torus_exact` | Evidence-exact nose/blend reference using arc segments. |
| `expanded_smooth_nose` | Smooth nose reference with conventional equator. |
| `free_equator_smooth` | Current selected working baseline with configurable equator crown. |
| `manual_equator_inset_3mm` | Visual probe: equator crown radius reduced by 3 mm. |
| `manual_equator_bulge_3mm` | Visual probe: equator crown radius increased by 3 mm. |
| `manual_equator_wide_soft` | Visual probe: wider, softer inward equator crown. |

Manual variants may fail baseline-difference thresholds by design. They are visual and parameterization probes until a physics-based acceptance criterion is defined.

## Validation

Validation thresholds belong in the prior:

```yaml
validation:
  purpose: exploratory_shape_generation
  bbox_abs_error_mm: 0.3
  bbox_rel_error: 0.002
  volume_rel_error: 0.01
  surface_area_rel_error: 0.01
  profile_rms_error_mm: 0.15
  profile_max_error_mm: 0.5
  baseline_difference_policy:
    bbox: warning
    volume: warning
    surface_area: warning
  hard_gate_policy:
    brep_valid: blocking
    profile_simple: blocking
    all_r_ge_0: blocking
```

`baseline_difference_policy` controls whether differences from the seed STEP are blocking, warning-only, or ignored. For the current optimization phase, baseline bbox/volume/surface differences are warning-only because the goal is to discover new cavity shapes, not to reproduce the original STEP exactly. BRep validity and basic profile topology remain hard gates.

## LLM Conversion Checklist

When converting expert text into YAML:

- Keep feature labels separate from modeling rules.
- Prefer an existing `extraction` method before requesting a new one.
- Prefer an existing `curve_selection` method before requesting a new curve type.
- Do not invent executable expressions.
- Mark uncertain expert statements in `human_notes` or an additive field, not as a calculation rule.
- Preserve schema version and model family.
- Record whether the rule affects generated STEP or only audit/reporting.
- For optimization candidates, make the curve control explicit in `curve_parameters` and confirm it appears in `derived_parameters`.
- Run the no-CST pipeline and inspect `resolved_expert_prior.v0.yaml` plus the audit HTML before live-CST.

## Audit Checklist

Before accepting a prior:

- Required feature mappings exist.
- Each parameter has a rule id and provenance.
- Curve choices are listed in `grammar.variant_policy.curve_selection`.
- Manual perturbation values are listed in `grammar.variant_policy.curve_parameters`.
- `derived_parameters` exposes the expected arc/NURBS/shared controls.
- Unknown fields are intentional and preserved.
- No rule silently changes CST face-level boundaries.
- Geometry validation passes or explains warnings.
- The audit HTML shows the expected expert text and mapping rules.

## Optimization Override Contract

The 500 MHz exploratory optimizer writes geometry controls back through an
expert-prior override. It must not edit STEP directly and must not use CST
`StoreParameter` as the RF-CEM geometry source of truth.

Current `exploratory_12d` controls are:

| Parameter | Prior target | Meaning |
|---|---|---|
| `equator_crown_delta_r_mm` | `curve_parameters.equator.<variant>.crown_radius_delta_mm` | Equator crown radial offset. |
| `equator_crown_z_mid_mm` | `curve_parameters.equator.<variant>.crown_z_mid_mm` | Equator crown midpoint z offset. |
| `equator_left_shoulder_z_abs_mm` | `curve_parameters.equator.<variant>.left_shoulder_z_abs_mm` | Left equator shoulder z position. |
| `equator_right_shoulder_z_abs_mm` | `curve_parameters.equator.<variant>.right_shoulder_z_abs_mm` | Right equator shoulder z position. |
| `equator_left_shoulder_delta_r_mm` | `curve_parameters.equator.<variant>.left_shoulder_delta_r_mm` | Left shoulder radial offset. |
| `equator_right_shoulder_delta_r_mm` | `curve_parameters.equator.<variant>.right_shoulder_delta_r_mm` | Right shoulder radial offset. |
| `nose_left_inner_delta_r_mm` | `curve_parameters.nose.<variant>.left_inner_delta_r_mm` | Left nose internal NURBS-control radial offset. |
| `nose_right_inner_delta_r_mm` | `curve_parameters.nose.<variant>.right_inner_delta_r_mm` | Right nose internal NURBS-control radial offset. |
| `nose_left_inner_delta_z_mm` | `curve_parameters.nose.<variant>.left_inner_delta_z_mm` | Left nose internal NURBS-control z offset. |
| `nose_right_inner_delta_z_mm` | `curve_parameters.nose.<variant>.right_inner_delta_z_mm` | Right nose internal NURBS-control z offset. |
| `blend_left_radius_delta_mm` | `curve_parameters.blend.<variant>.left_radius_delta_mm` | Left large blend arc radius offset. |
| `blend_right_radius_delta_mm` | `curve_parameters.blend.<variant>.right_radius_delta_mm` | Right large blend arc radius offset. |

Endpoints adjacent to modified blend arcs are re-anchored by grammar generation
so the profile remains continuous before validation. Baseline bbox, volume, and
surface differences are advisory during exploratory optimization; BRep validity,
profile simplicity, and non-negative radius remain hard gates.
