# Functions and Entrypoints Catalog

Updated: 2026-07-12

Audience: agents and maintainers locating an existing capability before adding code.

This catalog describes executable entries, important public classes, inputs, outputs, CST requirements, and branch ownership. Source and `--help` output are authoritative.

## 1. Execution conventions

Recommended interpreter for the current RF-CEM worktrees:

```text
C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe
```

From a worktree root:

```powershell
$py = 'C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')
```

Dependency groups:

| Group | Contents/use |
| --- | --- |
| base | NumPy, SciPy, Matplotlib, scikit-learn, pymoo, PyYAML |
| `cad` | CadQuery 2.5.2 for geometry-kernel STEP work |
| `review` | Plotly 5.24.1 for offline/GUI geometry visualization |
| `dev` | pytest and pytest-cov |

Editable install:

```powershell
& $py -m pip install -e '.[dev,cad,review]'
```

Do not install or upgrade dependencies during a bounded audit unless necessary and authorized. The current GUI worktree normally reuses the canonical RF-CEM virtual environment.

## 2. Quick entrypoint index

| Entrypoint | Owner | CST | Primary purpose |
| --- | --- | --- | --- |
| `python -m cst_history_extractor` | `main` | optional probe | Extract history, classify commands, build recipe manifest |
| `python -m step_feature_assistant` | `main` | no | STEP geometry/Feature/UDSG review package |
| `python -m step_feature_assistant.calibration_cli` | `main` | no | Propose rules from reviewed projects |
| `python -m step_feature_assistant.classifier_cli` | `main` | no | Export data/train advisory classifier |
| `python -m rf_cem` | RF-CEM | no | Alias of 500 MHz baseline builder |
| `python -m rf_cem.build_500mhz_baseline` | RF-CEM | no | UDSG + CSTTranslator baseline artifacts |
| `python -m rf_cem.build_500mhz_parametric_geometry` | RF-CEM | no | Reverse/reconstruct parameterized STEP package |
| `python -m rf_cem.live_500mhz_diagnostic` | RF-CEM | yes, no solver | Baseline import/setup live smoke |
| `python -m rf_cem.live_500mhz_parametric_diagnostic` | RF-CEM | optional solver | One generated package live smoke |
| `python -m rf_cem.live_500mhz_postprocessing_diagnostic` | RF-CEM | yes | Attach templates, solve, read Frequency/RQ/Q |
| `python -m workflows.rf_cem_500mhz_parametric_opt.runner` | RF-CEM | no | Generate baseline and exploratory candidates |
| `python -m workflows.rf_cem_500mhz_parametric_opt.live_campaign` | RF-CEM | yes | Repeated quick-live or SAO campaign |
| `python -m rf_cem.literature_semantics ...` | current GUI branch | no | Literature discovery, evidence, semantics, audits, GUI |
| `python run_workflow_1.py` | WF1 branch only | normally yes | RF gun SAO |
| `python run_workflow_2.py` | WF2 branch only | yes | Dual-project HOM antenna workflow |
| `python run_workflow_3.py` | WF3 branch only | yes | Recovery optimisation |
| `python -m workflows.rfgun_tolerance.*` | WF3 branch only | mixed | Tolerance sampling/analysis |
| `python run_workflow_4.py` | WF4 branch only | mode-dependent | HOM eigenmode planning/campaign/audit |

“No” under CST means the entry itself is designed for no-CST operation. It may still read prior artifacts derived from CST.

## 3. Shared core API

These are importable building blocks, not standalone CLIs.

### 3.1 CST lifecycle

#### `cst_optimization.core.connection.CSTConnection`

Responsibilities:

- lazy CST library-path setup;
- `DesignEnvironment.new` / `connect_to_any` / `connect_to_any_or_new`;
- open existing project;
- create MWS project;
- quiet mode;
- PID lookup;
- reconnect;
- graceful, forced, or targeted cleanup.

Important methods:

| Method | Contract |
| --- | --- |
| `connect()` | Establish the configured DesignEnvironment connection. |
| `open_project(path)` | Return a `CSTProject` wrapper; path must exist. |
| `new_mws_project()` | Create a new Microwave Studio project. |
| `set_quiet_mode(enable)` | Best-effort suppression of message boxes. |
| `close(force=False)` | Graceful close with PID verification; legacy fallback may be broad. |
| `close_targeted(...)` | Kill only the recorded process tree; no global sweep. |
| `reconnect()` | Close/wait/reconnect. |
| `pid` | Best-effort DesignEnvironment PID. |

Use `close_targeted` only for an owned, dedicated `mode="new"` process after project save/close.

#### `cst_optimization.core.project.CSTProject`

Responsibilities:

- cached project filename;
- parameter update wrapper;
- model rebuild;
- execute VBA through `Model3D.add_to_history`;
- save/close/activate;
- CST message retrieval.

Important methods:

| Method | Contract |
| --- | --- |
| `update_parameters(params, use_full_rebuild=False)` | Existing compatibility wrapper; first tries native-style `StoreParameter` then verified VBA fallback. |
| `rebuild()` | `full_history_rebuild`. |
| `execute_vba(code, header, timeout)` | Add and execute a history block. |
| `get_active_solver_name()` | Diagnostic solver name. |
| `save(path, include_results, allow_overwrite)` | Guarded project save. |
| `close(save=True)` | Independently guards save and close. |
| `get_messages()` | CST Message Window payload. |

New code should consume this wrapper rather than copying CST calls.

#### `cst_optimization.core.solver.SolverRunner`

- synchronous `model3d.run_solver(timeout=...)`;
- elapsed time and mesh-cell diagnostics;
- timeout/mesh/COM/convergence/unknown error classification;
- `abort(project)` support.

Returns typed `SolverResult`.

#### `cst_optimization.core.results.ResultReader`

Typed result access:

- `get_s_parameter`;
- `get_scalar`;
- `get_1d_result`;
- `get_result_item`;
- `get_2d_result`;
- `list_tree_items` and `list_colormap_items`;
- `get_run_ids` / `get_all_run_ids`;
- `get_parameter_combination`;
- `invalidate_cache` after a CST save.

Data containers:

- `SParameterData`;
- `ScalarResult`;
- `Result2DData`;
- `ResultBundle`.

### 3.2 Evaluation and recovery

`src/cst_optimization/evaluation/` provides:

- versioned evaluation-database schemas;
- storage and skip-record storage;
- parameter deduplication;
- warm-start extraction;
- successful-evaluation reuse;
- failure-skip candidate generation and enforce/dry-run paths;
- retry taxonomy;
- generic and CST-aware retry runtime;
- stage observation;
- extreme-recovery safety.

Search this package before creating a new JSONL/SQLite retry implementation. Concrete workflow ownership still belongs on the workflow branch.

### 3.3 Optimisation

`src/cst_optimization/optimization/` contains:

- base optimizer contract;
- Latin-hypercube and other sampling;
- SAO;
- SAEA;
- acquisition functions;
- adaptive bounds;
- conditional gates;
- resume helpers.

Use scikit-learn for Gaussian processes, SciPy for fitting/root finding, and pymoo for multi-objective evolutionary optimisation.

### 3.4 Objectives, parameters and physics

- `objectives/`: frequency, Q/quality, field and mode objectives plus registry;
- `parameters/`: typed parameter ranges and geometry parameters;
- `physics/`: cavity, formulas, heating, Poynting, wakefield and typed quantities;
- `utils/units.py`: unit conversion helpers.

Scientific calculations must preserve unit/definition information in code and outputs.

## 4. CST history extractor

Module:

```powershell
& $py -m cst_history_extractor --help
```

### 4.1 Exported macro input

```powershell
& $py -m cst_history_extractor `
  --history-macro examples\example_history.bas `
  --output-dir runs\history_example `
  --project-id example
```

### 4.2 CST project input

```powershell
& $py -m cst_history_extractor `
  --cst-file C:\path\project.cst `
  --output-dir runs\project_history `
  --cst-library-path 'D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries'
```

The library path is optional. It is used only to open the project and attempt to trigger unpacking when adjacent `Model/3D/ModelHistory.json` is absent.

### 4.3 Outputs

```text
<output>/
  raw_history/
    history_raw.txt
    history_items.json
    cst_probe.json
    history_source_metadata.json
  analysis/
    command_inventory.json
    cst_recipe_manifest.json
    geometry_history_summary.json
    unknown_or_unclassified_commands.json
  reports/
    history_analysis_report.md
```

Key modules:

- `history_reader.py`: macro/direct-project source selection;
- `macro_parser.py`: history-block parsing;
- `command_classifier.py`: deterministic command categories;
- `recipe_builder.py`: recipe and geometry summaries;
- `report_writer.py`: generated human report.

Limit: there is no confirmed official Python API for reading all existing History List bodies. Direct `ModelHistory.json` reading is version-sensitive evidence.

## 5. STEP Feature Assistant / Helper2

### 5.1 Main extraction

```powershell
& $py -m step_feature_assistant `
  --step-file StepData\bare_cavity_500mhz.stp `
  --output-dir runs\bare_cavity_review `
  --axis z `
  --model-type bare_cavity_500mhz `
  --backend cadquery `
  --preview html
```

Required:

- `--step-file`;
- `--output-dir`;
- `--model-type`.

Options:

| Option | Values/meaning |
| --- | --- |
| `--axis` | `x`, `y`, `z`; default `z` |
| `--model-type` | `normal_conducting_500mhz`, `xband_2.3cell_gun`, `bare_cavity_500mhz` |
| `--backend` | `fallback`, `cadquery`, `auto` |
| `--preview` | `html` or `none` |
| `--open-reviewer` | Open generated reviewer |
| `--rules` | Reviewed rule-profile override |
| `--classifier-model` | Advisory trained model |
| `--hints` | Optional labeling hints |
| `--reviewed-labels` | Human-reviewed labels for resolved graph |
| `--legacy-only` | Omit geometry graph / candidates / partial UDSG |

Backend semantics:

- `cadquery`: preferred kernel facts for human review;
- `auto`: try CadQuery, record fallback;
- `fallback`: portable STEP-text diagnostics, lower geometric authority.

### 5.2 Outputs

```text
<output>/
  geometry_manifest.json
  face_inventory.json
  face_inventory.csv
  adjacency_graph.json
  feature_graph_draft.json
  geometry_graph.json
  feature_candidates.json
  udsg_geometry_layer.json
  reviewed_feature_labels.template.yaml
  review_report.md
  classifier_suggestions.json              optional
  resolved_feature_graph.json              with --reviewed-labels
  preview/
    model_review.html
    face_coloring_legend.json
```

Reviewer capabilities:

- Geometry facts, surface classes and adjacency;
- Feature grouping, confidence/evidence and overlap warnings;
- face highlight/select;
- confirm/requires-review/reject;
- edit Feature type and geometry refs;
- manual face groups;
- partial UDSG binding accept/edit/delete/restore;
- download reviewed labels and review-session snapshot.

`reviewed_feature_labels.yaml` is the resolver authority. Browser `review_session.json` is audit state, not a substitute.

### 5.3 Geometry facts and candidate rules

The fallback AP242 text reader recognizes:

- `MANIFOLD_SOLID_BREP` and `CLOSED_SHELL`;
- `ADVANCED_FACE` and face bounds;
- edge loops, oriented edges, edge curves and vertices;
- Cartesian points;
- plane, cylindrical, conical, toroidal and spherical analytic surfaces.

It can enumerate topology and shared-edge adjacency. Area and normal values remain estimates with method/confidence metadata.

CadQuery/OCP adds kernel `Area()`, `Center()`, bounding box, geometry type, normals, solid/shell refs, backend hash and tessellated face meshes where available.

Face-ID policy:

- fallback IDs such as `F0001` follow STEP entity order;
- CadQuery IDs follow kernel traversal;
- either order can change after STEP re-export;
- matching must use fingerprint, surface type, centroid/bbox, area, adjacency and axis/radius facts, not ID alone.

All semantic rules generate candidates only:

| Candidate | Main evidence |
| --- | --- |
| `BeamPipeLeft/Right`, `BeamAperture`, `BeamExit` | axisymmetric cylinder near axial end, smaller than cavity maximum radius |
| `ConductingWall` | connected wall-like axisymmetric plane/cylinder/cone/torus/revolution/spline at large radius |
| `Iris` | axisymmetric interior small-radius region |
| `EquatorRegion` | axisymmetric interior large-radius region |
| `CathodeSurface` | for X-band profile, plane near the cathode-side axial end |
| `TransitionBlend` | small-radius torus/cone/spline/cylinder adjacent to at least two faces |
| `UnknownSidePort` | non-axisymmetric side-wall opening away from beam axis |

`UnknownSidePort` requires human refinement to an input coupler, waveguide, coaxial, pickup, pump port or artifact. Cathode/nose separation is intentionally conservative and benefits from hints.

Translator handoff uses `resolved_feature_graph.json`:

- `RFVacuumVolume` maps to imported body;
- `ConductingWall` provides a conducting/material role;
- `CathodeSurface` needs reviewed selection and recipe;
- apertures/exits take electric or open/waveguide behavior from the simulation recipe;
- all side ports require manual confirmation before port generation.

Helper2 does not generate CST macros.

### 5.4 Rule calibration

```powershell
& $py -m step_feature_assistant.calibration_cli `
  --review-roots runs\reviewed_projects `
  --output-dir runs\calibration
```

Outputs:

- `calibration_proposal.yaml`;
- generated `calibration_report.md`.

The proposal never changes production rules automatically.

### 5.5 Advisory classifier

Export:

```powershell
& $py -m step_feature_assistant.classifier_cli export `
  --review-roots runs\reviewed_projects `
  --output-dir runs\training_dataset
```

Train:

```powershell
& $py -m step_feature_assistant.classifier_cli train `
  --dataset-dir runs\training_dataset `
  --output-dir runs\classifier_baseline
```

The baseline is a multi-label one-vs-rest logistic regression with project-grouped validation. Suggestions cannot modify the rule-based draft or resolved graph.

### 5.6 Internal workers

- `step_feature_assistant.cadquery_worker`;
- `rf_cem.parametric_geometry.core.cadquery_worker`.

These are subprocess protocols, not user-facing CLIs. Do not invoke them manually unless debugging their structured stdin/stdout contract.

## 6. RF-CEM baseline and parametric geometry

Required baseline layout:

```text
Appendix/500MHz_baseline/
  500MHz.stp
  500MHz/Model/3D/ModelHistory.json
  step_feature_assistant/
    geometry_graph.json
    feature_graph_draft.json
    geometry_manifest.json
    reviewed_feature_labels.yaml
    review_session.json              optional
```

### 6.1 Build imported-baseline translator artifacts

`python -m rf_cem` is an alias for this entry:

```powershell
& $py -m rf_cem.build_500mhz_baseline `
  --appendix Appendix\500MHz_baseline `
  --output-dir runs\rf_cem_baseline `
  --step-filename-mode star-basename
```

`--step-filename-mode`:

- `star-basename`: portable CST-import placeholder convention;
- `absolute`: explicit path, primarily live diagnostic.

Outputs:

```text
semantic/udsg.v0.json
generated/review_session_diff.json
generated/cst_actions.json
generated/cst_mapping_table.json
generated/translator_report.json
generated/cst_script.bas
```

No CST is launched.

### 6.2 Reverse/reconstruct parameterized geometry

```powershell
& $py -m rf_cem.build_500mhz_parametric_geometry `
  --appendix Appendix\500MHz_baseline `
  --output-dir runs\parametric_geometry_500mhz `
  --target-body-index 0 `
  --axis z `
  --deflection-mm 0.25 `
  --expert-prior Appendix\500MHz_baseline\expert_prior.v0.yaml
```

The prior argument is optional. Precedence is explicit CLI prior, case prior, built-in prior, emergency fallback.

`expert_prior.v0` supported sections:

```yaml
schema_version: expert_prior.v0
model_family: axisymmetric_single_cell_rf_vacuum
units: {}
target_body: {}
axis: {}
feature_mappings: {}
grammar: {}
fit_policy: {}
validation: {}
interface_policy: {}
human_notes: {}
```

Supported feature-extraction operations are declared names such as semantic-only, bounding-box span, median radius, median radius plus axial span, maximum radial extent and half local radial span. Arbitrary Python, `eval` and natural-language formulas are forbidden.

Supported profile segment kinds are `line`, `arc`, `ellipse`, `local_spline` and `nurbs`. Validation separates baseline-difference warnings from blocking BRep/profile topology guards. Every run writes the resolved prior for reproduction.

Main outputs:

```text
variant_index.json
variants/<variant>/...
geometry/generated_vacuum.step
metadata/parametric_geometry.v0.json
metadata/resolved_expert_prior.v0.json
metadata/resolved_expert_prior.v0.yaml
metadata/geometry_validation.json
metadata/source_evidence.json
translator/cst_payload.json
translator/rf_cem_artifacts/...
audit/parametric_geometry_audit.html
audit/variant_comparison.html
```

Exit code 1 means blocking geometry errors were reported.

### 6.3 Baseline live import/setup diagnostic

```powershell
& $py -m rf_cem.live_500mhz_diagnostic `
  --appendix Appendix\500MHz_baseline `
  --output-dir runs\baseline_live_smoke `
  --library-path 'D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries' `
  --connect-mode new
```

This creates a disposable CST project and executes generated setup blocks. It intentionally does not run the solver.

### 6.4 One parametric package live diagnostic

```powershell
& $py -m rf_cem.live_500mhz_parametric_diagnostic `
  --package-dir runs\parametric_geometry_500mhz `
  --library-path 'D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries' `
  --connect-mode new `
  --run-solver
```

Without `--run-solver` it is import/setup only. With it, solver timeout defaults to 7200 seconds.

### 6.5 Postprocessing-template diagnostic

```powershell
& $py -m rf_cem.live_500mhz_postprocessing_diagnostic `
  --package-dir runs\parametric_geometry_500mhz `
  --template-project-dir D:\ModelData\bare `
  --library-path 'D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries' `
  --connect-mode new `
  --run-solver
```

Optional `--evaluate-templates` is disabled by default.

Flow:

1. create/save project from CST actions;
2. copy verified Frequency, R/Q and Q `.r0d` files;
3. install filtered or verified-minimal `Model.rpp`;
4. merge `PC_integration.json` output variables;
5. reopen/save;
6. optionally solve/evaluate;
7. inspect unpacked artifacts;
8. read result-tree scalars.

Outputs:

- candidate-specific CST project;
- `live_postprocessing/live_postprocessing_diagnostic_report.json`;
- result-tree probe and scalar values.

## 7. RF-CEM parametric optimisation workflow

Owner: `workflow/rf-cem-500mhz` and current descendant GUI branch.

### 7.1 no-CST scan

```powershell
& $py -m workflows.rf_cem_500mhz_parametric_opt.runner `
  --config workflows\rf_cem_500mhz_parametric_opt\config.yaml `
  --output-dir runs\rf_cem_no_cst_scan
```

If baseline `parametric_geometry.v0.json` is missing, the runner regenerates it from `Appendix/500MHz_baseline`.

Outputs:

- `parameter_table.json`;
- `scan_report.json`;
- `candidates/candidate_###/geometry/generated_vacuum.step`;
- candidate metadata, validation and translator payload.

`POSTPROCESS_TEMPLATE_MISSING` and `SOLVER_NOT_RUN` are not geometry failures; they mean the candidate is not a live success sample.

### 7.2 quick-live campaign

```powershell
& $py -m workflows.rf_cem_500mhz_parametric_opt.live_campaign `
  --mode quick-live `
  --output-dir runs\rf_cem_quick_live `
  --template-project-dir D:\ModelData\bare `
  --library-path 'D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries' `
  --start-at-index 1 `
  --max-evals 4
```

### 7.3 seeded SAO

```powershell
& $py -m workflows.rf_cem_500mhz_parametric_opt.live_campaign `
  --mode sao `
  --output-dir runs\rf_cem_sao `
  --template-project-dir D:\ModelData\bare `
  --library-path 'D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries' `
  --seed-candidate-index 4 `
  --local-bounds-scale 0.35 `
  --n-initial 6 `
  --n-iterations 4 `
  --max-evals 10
```

Current limitations:

- seed index refers to configured quick-scan points, not arbitrary live records;
- no complete explicit resume mode;
- reusing a populated output directory is unsafe unless manually audited;
- objective hardening remains pending.

Outputs:

```text
live_records.jsonl
live_summary.json
sao_result.json                         SAO mode
candidates/candidate_###/...
cst_projects/candidate_###_postprocess_solver.cst
```

## 8. Literature semantics CLI

Top-level help:

```powershell
& $py -m rf_cem.literature_semantics --help
```

Subcommands:

### 8.1 `validate`

```powershell
& $py -m rf_cem.literature_semantics validate --package C:\path\paper
```

Accepts a package directory or JSON/YAML file. Returns nonzero on validation errors and prints exact field paths.

### 8.2 `draft-prior`

```powershell
& $py -m rf_cem.literature_semantics draft-prior `
  --package C:\path\literature_semantics.v0.json `
  --base-prior C:\path\expert_prior.v0.yaml `
  --out C:\path\expert_prior.draft.v0.yaml
```

All generated patch items start `pending` and are hash-bound to the semantic package and base prior.

### 8.3 `merge-prior`

```powershell
& $py -m rf_cem.literature_semantics merge-prior `
  --package C:\path\literature_semantics.v0.json `
  --base-prior C:\path\expert_prior.v0.yaml `
  --draft-prior C:\path\reviewed.draft.v0.yaml `
  --out C:\path\expert_prior.reviewed.v0.yaml
```

Default `--require-reviewed` blocks pending/rejected/needs-evidence patches. `--allow-unreviewed` is an explicit diagnostic mode and still enforces integrity and ontology validation.

### 8.4 `audit`

```powershell
& $py -m rf_cem.literature_semantics audit `
  --package C:\path\literature_semantics.v0.json `
  --draft-prior C:\path\expert_prior.draft.v0.yaml `
  --out C:\path\paper_audit.html
```

Writes one self-contained static paper audit.

### 8.5 `arxiv-search`

```powershell
& $py -m rf_cem.literature_semantics arxiv-search `
  --query 'all:"radio frequency cavity" AND all:optimization' `
  --max-results 10 `
  --out analysis_outputs\literature\search_candidates.json
```

Outputs discovery metadata only. It does not classify authority, “classic” status or applicability.

### 8.6 `arxiv-fetch`

```powershell
& $py -m rf_cem.literature_semantics arxiv-fetch `
  --id 1810.02990v3 `
  --out-dir analysis_outputs\literature\papers\sls2
```

Requires an explicit version for PDF download. Writes immutable `source.pdf` and `source_manifest.json` with SHA-256.

### 8.7 `render-evidence`

```powershell
& $py -m rf_cem.literature_semantics render-evidence `
  --pdf C:\path\source.pdf `
  --pages 4 8 9 11 `
  --out-dir C:\path\figures `
  --pdftoppm C:\path\pdftoppm.exe `
  --dpi 150
```

Page numbers are one-based. Writes rendered images and `render_manifest.json`.

### 8.8 `corpus-audit`

Isolated human audit:

```powershell
& $py -m rf_cem.literature_semantics corpus-audit `
  --bundle-root C:\path\corpus `
  --manifest C:\path\corpus\corpus_manifest.json `
  --paper-id sls2 `
  --out C:\path\normal_conducting_sls2.html
```

Omit `--paper-id` only for combined integrity/statistical reporting. Do not use a combined NC/SRF page as the human OK/Reject surface.

The loader enforces bundle-root containment, file-size limits, PDF/image signatures and hashes, manifest consistency, semantic/draft integrity, and evidence-reference completeness.

### 8.9 `review-gui`

```powershell
& $py -m rf_cem.literature_semantics review-gui `
  --bundle-root analysis_outputs\rf_cem_literature_pilot_20260710 `
  --manifest corpus_manifest.json `
  --paper-id sls2 `
  --session-root analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui `
  --port 0 `
  --deflection-mm 0.5
```

`--port 0` selects an available local port. The service prints:

- authenticated review URL;
- generated HTML path;
- initial STEP path.

It blocks until Ctrl+C.

## 9. Literature review GUI functions

### 9.1 Evidence

- current-paper-only text and image evidence;
- paper/page/section/Figure/Table provenance;
- embedded rendered page;
- local verified PDF same-page navigation;
- evidence review status and Chinese notes.

Exact paragraph highlighting requires evidence `bbox` or `text_anchor`. Page-only evidence is never presented as exact text localization.

### 9.2 Semantic candidates

Displayed groups:

- classification;
- named features;
- shape motifs;
- curve priors;
- parameter ranges;
- optimisation objectives;
- physical constraints;
- draft-prior configuration suggestions.

Unified display schema: `literature_semantic_candidate_view.v1`. Duplicate subjects such as `equator` are grouped; separate cards represent different predicates/claims, not accidental duplicate rows.

Structured Add requires:

- target section;
- unique item ID;
- JSON object;
- evidence/provenance fields.

Added items start pending.

### 9.3 Geometry projection

Current generator is SLS-2-specific:

- parameters `L/l/r/R/a/b` in mm;
- immutable published baseline;
- content-addressed human variants;
- baseline/previous/current 3D and r-z comparison;
- STEP, BRep, mesh and bounding-box validation;
- candidate-level review state and Chinese note.

It does not derive numeric changes from accepted natural-language semantics.

### 9.4 Helper2 integration

Features:

- grouped candidates;
- face highlighting;
- status editing;
- Feature type and geometry-ref editing;
- manual Feature group.

UDSG:

- geometry nodes;
- Feature candidates;
- topology;
- grouped bindings;
- edit/delete/restore and status;
- validation warnings.

`partial_ok` means only that the current geometry-layer candidate has no blocking error. It is not a complete RF-CEM UDSG or CST validation.

### 9.5 Session storage

```text
review_session.v1.json
review_events.jsonl
rf_cem_literature_review_<paper-id>.html
review_launch.json
geometry_previews/<content-hash>/cavity.step
generation.core.json
*.review_snapshot.json
helper2_face_mesh.json
```

Literature decisions and Helper2 reviews use separate namespaces.

## 10. Workflow branch entries

These entries do not belong on `main`. Run them only from their canonical branch/worktree.

### 10.1 WF1: `workflow/1-rfgun-sao`

Entries:

```powershell
& $py run_workflow_1.py --help
& $py -m workflows.rfgun_sao.run --help
```

Typical:

```powershell
& $py run_workflow_1.py `
  --config workflows\rfgun_sao\config.local.yaml `
  --seed 43 `
  --n-initial 1 `
  --n-iter 0
```

Default mode is single-pass. Two-pass CST is opt-in. Root `run_workflow_1.py` is a compatibility shim owned by this branch.

### 10.2 WF2: `workflow/2-rfgun-hom-antenna`

```powershell
& $py run_workflow_2.py --help
& $py run_workflow_2.py --auto-resume --heartbeat
& $py run_workflow_2.py --auto-resume --recovery-only
& $py run_workflow_2.py --warmup-from-db D:\Results\wf2_warmup_total\index.total.jsonl
& $py run_workflow_2.py --config D:\smoke\config.yaml --smoke-only
```

The package-local `workflows/rfgun_hom_antenna/config.yaml` is the tracked source of truth. Scheduler compatibility remains at the root shim.

### 10.3 WF3: `workflow/3-rfgun-recovery-tolerance`

Recovery:

```powershell
& $py run_workflow_3.py --help
& $py run_workflow_3.py --resume-from runs\workflow3\stage_2\evaluation_records.jsonl
```

Tolerance simulation, requires CST:

```powershell
& $py -m workflows.rfgun_tolerance.run `
  --config config\default.yaml `
  --tolerance-scale 1.0 1.67 3.33
```

Single database analysis, no-CST:

```powershell
& $py -m workflows.rfgun_tolerance.cli `
  --db C:\path\evaluations.db `
  --output runs\tolerance\report.md
```

Cross-level analysis, no-CST:

```powershell
& $py -m workflows.rfgun_tolerance.campaign_cli `
  --config config\default.yaml `
  --db 3=C:\path\tolerance_eval_3um.db `
  --db 5=C:\path\tolerance_eval_5um.db `
  --output runs\tolerance\campaign_report.md
```

### 10.4 WF4: `workflow/4-rfgun-hom-eigenmode`

```powershell
& $py run_workflow_4.py --help
& $py run_workflow_4.py --plan-only
& $py run_workflow_4.py --resume-preview
& $py run_workflow_4.py --offline-only C:\path\campaign
& $py run_workflow_4.py --audit-results
```

Actual resume/run CST requires explicit user authority. Template revision adoption is explicit and provenance-bound.

## 11. Repository scripts

### 11.1 CST help scanner

`scripts/cst_help_automation_scan.py` rescans a local CST Online Help tree for official automation pages.

Use `--help` before invocation. It is a documentation-audit aid, not a CST control API.

### 11.2 Workstation package

`scripts/package_rf_cem_workstation.ps1` creates a code package for the RF-CEM workstation. It intentionally excludes runs, Appendix inputs, virtual environments, CST projects and databases.

After documentation consolidation it includes the maintained documentation set, not archived individual status files.

### 11.3 Workstation bootstrap

`scripts/rf_cem_workstation_bootstrap.ps1` prepares the local Python package/environment path expected by RF-CEM workstation operations. Inspect before running; do not assume paths are portable.

## 12. Schemas and example fixtures

Tracked JSON schemas:

- `schemas/geometry_manifest.schema.json`;
- `schemas/feature_graph_draft.schema.json`;
- `schemas/resolved_feature_graph.schema.json`;
- `schemas/command_inventory.schema.json`;
- `schemas/cst_recipe_manifest.schema.json`.

Examples:

- `examples/example_history.bas`: parser fixture, not certified production macro;
- `examples/reviewed_feature_labels.example.yaml`;
- `examples/user_hints.example.yaml`;
- `examples/expected_outputs/`: representative machine-readable extractor outputs.

Literature ontology:

- `src/rf_cem/literature_semantics/ontology_v0.yaml`.

Parametric-geometry prior:

- `src/rf_cem/parametric_geometry/priors/axisymmetric_single_cell.v0.yaml`.

Workflow config:

- `workflows/rf_cem_500mhz_parametric_opt/config.yaml`.

## 13. Test routing

Full current branch:

```powershell
& $py -m pytest -q -m 'not cst_required'
```

Literature/GUI:

```powershell
& $py -m pytest -q `
  tests\test_rf_cem_arxiv_ingest.py `
  tests\test_rf_cem_pdf_evidence.py `
  tests\test_rf_cem_literature_semantics_v0.py `
  tests\test_rf_cem_literature_corpus_audit.py `
  tests\test_rf_cem_literature_geometry_candidate.py `
  tests\test_rf_cem_literature_interactive_reviewer.py `
  tests\test_rf_cem_literature_review_bundle.py `
  tests\test_rf_cem_literature_review_server.py `
  tests\test_rf_cem_literature_review_app.py
```

RF-CEM geometry/optimisation:

```powershell
& $py -m pytest -q `
  tests\test_rf_cem_500mhz.py `
  tests\test_rf_cem_parametric_geometry_500mhz.py `
  tests\test_rf_cem_parametric_optimization.py
```

History/STEP:

```powershell
& $py -m pytest -q `
  tests\test_history_reader.py `
  tests\test_macro_parser.py `
  tests\test_command_classifier.py `
  tests\test_recipe_builder.py `
  tests\test_cadquery_reader.py `
  tests\test_feature_candidate_generator.py `
  tests\test_reviewer_layers.py `
  tests\test_review_merger.py
```

Core evaluation/retry tests are under `tests/core/`.

Tests marked `cst_required` are excluded by the no-CST command. Never report skipped live tests as live validation.

## 14. Before adding a new feature

Search in this order:

1. this catalog;
2. `rg` in the owning package;
3. current tests;
4. adjacent generic contracts in `src/cst_optimization/`;
5. the canonical workflow branch;
6. archived documentation only if provenance is needed.

Do not create:

- a second CST connection wrapper;
- a second evaluation database under a workflow-specific name;
- a duplicate Helper2 reviewer;
- a new literature review status vocabulary;
- a generic geometry generator on `main` without a second consumer;
- an undocumented CST method call.
