# STEP Feature Assistant Design

`step_feature_assistant` is a review helper for turning imported STEP vacuum
geometry into a draft RF FeatureGraph.  It deliberately separates objective
geometry facts from engineering semantics:

- `geometry_manifest.json` records STEP topology facts: solids, shells, faces,
  edges, surface type, approximate area, centroid, bbox, axis relation, and
  adjacency.
- `feature_graph_draft.json` records candidate semantic labels such as
  `BeamPipeLeft`, `ConductingWall`, `Iris`, `CathodeSurface`, or
  `UnknownSidePort`.
- `geometry_graph.json`, `feature_candidates.json`, and
  `udsg_geometry_layer.json` expose the same Helper2 facts as a geometry-only
  partial UDSG layer for CSTTranslator planning.
- `resolved_feature_graph.json` is produced only after human review labels are
  merged.

## Backends

v1 uses a conservative STEP AP242 text backend.  It parses:

- `MANIFOLD_SOLID_BREP`
- `CLOSED_SHELL`
- `ADVANCED_FACE`
- `FACE_OUTER_BOUND` / `FACE_BOUND`
- `EDGE_LOOP`
- `ORIENTED_EDGE`
- `EDGE_CURVE`
- `VERTEX_POINT`
- `CARTESIAN_POINT`
- analytic surfaces such as `PLANE`, `CYLINDRICAL_SURFACE`,
  `CONICAL_SURFACE`, `TOROIDAL_SURFACE`, and `SPHERICAL_SURFACE`

This fallback backend is enough to enumerate faces and build adjacency via
shared STEP edge ids.  It cannot perform exact CAD-kernel surface integration,
so area and normal values are marked as estimates with an `area_method` and
`area_confidence`.

v2 adds a CadQuery/OCP backend:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant --step-file StepData\bare_cavity_500mhz.stp --output-dir runs\bare_cavity_features_cad --axis z --model-type bare_cavity_500mhz --backend cadquery
```

The CLI supports:

- `--backend fallback`: v1 STEP text parser and default behavior.
- `--backend cadquery`: exact CAD-kernel measurements through CadQuery/OCP.
- `--backend auto`: try CadQuery first, then record the failure and fall back
  to the STEP text parser.

CadQuery is run in an isolated worker process on this Windows setup because the
local CadQuery/OCP import path can crash during normal interpreter shutdown.
The worker writes `geometry_manifest.json` and exits with `os._exit(0)`; the
main CLI process remains clean and continues with feature candidate generation.
On this machine, `import cadquery` can print successfully and still end with
Windows access violation `-1073741819` during shutdown.  Treat the worker-backed
CLI smoke test as the reliable installation check.

CadQuery-backed manifests use:

- `reader.backend = "cadquery_ocp"`;
- `reader.measurement_quality = "cad_kernel"`;
- exact `Area()`, `Center()`, `BoundingBox()`, `geomType()`, and
  `Face.normalAt()` values where CadQuery exposes them;
- optional `solid_refs`, `shell_refs`, `cadquery_hash`, and `backend_notes`.

## Stable Face IDs

Within one fallback STEP import, face ids are stable by STEP `ADVANCED_FACE`
entity order:

```text
F0001, F0002, ...
```

The CadQuery backend assigns face ids by CAD-kernel traversal order.  Across
re-exported STEP files, either order can change.  The manifest therefore adds a
`fingerprint` derived from surface type, area, centroid, bbox, and edge count.
A later matching tool should compare:

1. surface type;
2. centroid and bbox within tolerance;
3. area within tolerance;
4. adjacency neighborhood;
5. radius / axis relation.

## CSTTranslator Handoff

The translator should consume `resolved_feature_graph.json`, not the draft.
Recommended mapping:

- `RFVacuumVolume` -> imported STEP solid/body reference.
- `ConductingWall` with `default_boundary_role=electric` -> CST conducting wall
  or material assignment recipe.
- `CathodeSurface` -> named face selection plus electric boundary or material
  role.
- `BeamAperture` / `BeamExit` -> boundary role selected by simulation recipe,
  commonly electric for closed cavity recipes or open/waveguide for driven port
  recipes.
- `UnknownSidePort`, `WaveguidePort`, `CoaxialPort` -> candidate port/opening
  features requiring manual confirmation before CST port generation.

The helper does not write CST macros.  It produces traceable geometry references
that CSTTranslator can later map to selections, boundaries, ports, and material
assignments.

## Interactive Review

With `--backend cadquery --preview html`, the CadQuery worker tessellates every
face independently and the main process creates
`preview/model_review.html`.  The Plotly JavaScript runtime is embedded, so the
reviewer works offline.

The reviewer is a three-layer Helper2 audit console:

- `Geometry` reviews the geometry index, surface classes, selected-face facts,
  measurement confidence, axis-symmetry flags, adjacency, isolated faces, and
  optional topology adjacency overlay.
- `Features` reviews deterministic feature candidates, confidence/evidence,
  geometry references, overlap warnings, and low-confidence warnings.
- `UDSG` reviews the geometry-only partial UDSG nodes, feature bindings, and
  validation warnings.  Bindings marked `requires_review` can be accepted,
  rejected, kept as requiring review, edited, deleted, or restored in the
  browser audit session.  These edits are audit overrides recorded in
  `review_session.json`; they do not rewrite the original
  `udsg_geometry_layer.json`.

Unassigned faces remain highlighted in the feature view.  Clicking a face
displays its id, geometry facts, adjacency, rule candidates, and optional
experimental classifier suggestions.  The reviewer can confirm/reject
candidates, create manual face groups, edit candidate geometry references, and
download `reviewed_feature_labels.yaml`.

The reviewer can also download `review_session.json`, which preserves browser
review state, geometry audit status, UDSG binding audit status, UDSG binding
edit/delete overrides, and reviewer notes for audit.  The resolver consumes
`reviewed_feature_labels.yaml`; `review_session.json` is not a replacement for
reviewed labels.

The 3D toolbar defaults to a fast drag mode: labels, topology lines, and hover
text are disabled until requested, and the WebGL pixel ratio is reduced so
rotation and panning update interactively on larger tessellated models.

## Rule Calibration And Classifier Boundary

Human-confirmed labels are the production authority.  Calibration summarizes
reviewed surface types, relative radii, normalized axial positions, adjacency,
rejections, and missed expected features.  It creates proposals only.

The experimental classifier uses the same normalized face features through a
stable `FeatureScorer` interface.  The baseline is a multi-label one-vs-rest
logistic regression.  Its output is advisory and cannot mutate the rule-based
draft, review YAML, or resolved graph.
