# Functions and Entrypoints Catalog

Updated: 2026-08-20

Audience: agents and maintainers locating an existing capability before adding code.

This catalog describes executable entries, important public classes, inputs, outputs, CST requirements, and branch ownership. Source and `--help` output are authoritative.

## 1. Execution conventions

From a clone/worktree root, resolve the repository and its own virtual environment:

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
```

External paths are local configuration, not repository-relative paths. Examples use these explicit placeholders:

```powershell
$CstLibraryPath = '<CST_PYTHON_LIBRARY_DIR>'
$TemplateProjectDir = '<CST_TEMPLATE_PROJECT_DIR>'
$LocalDataRoot = '<LOCAL_DATA_ROOT>'
```

Replace each placeholder on the current machine before running a command. Never commit the resolved values.

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

Do not install or upgrade dependencies during a bounded audit unless necessary and authorized. Each contributor clone/worktree should use its own known-good environment; do not hard-code another worktree's interpreter.

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
| `python -m rf_cem.literature_semantics ...` | `workflow/rf-cem-literature-review` | no | Literature discovery, evidence, semantics, audits, GUI |
| `python -m rf_cem.semantic ...` | `workflow/rf-cem-literature-review` | no | Build, validate and diff R1 semantic topology contracts |
| `python -m rf_cem.semantic.induction ...` | `workflow/rf-cem-literature-review` | no | Build/validate reviewed R3 v0 or seed-ablation/v1 detector/support proofs |
| `python -m rf_cem.compiler ...` | `workflow/rf-cem-literature-review` | no | Build/validate both R2 boundary compiles with explicit continuity and v0/v1 records |
| `python -m rf_cem.observation ...` | `workflow/rf-cem-literature-review` | no | Build and validate the R4 exact/shape/scalar observation and engineering-constraint proof |
| `python -m rf_cem.workbench ...` | `workflow/rf-cem-literature-review` | no | Rebuild, audit and browse the derived Workbench W0–W4 registry |
| `python -m rf_cem.workbench.desktop ...` | `workflow/rf-cem-literature-review` | no | Run/self-test the fixed-action Workbench Desktop launcher source |
| `scripts/build_rf_cem_workbench_desktop.ps1` | `workflow/rf-cem-literature-review` | no | Build and self-test ignored `dist/RF-CEM-Workbench.exe` |
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
$CstProjectFile = '<CST_PROJECT_FILE>'
& $py -m cst_history_extractor `
  --cst-file $CstProjectFile `
  --output-dir runs\project_history `
  --cst-library-path $CstLibraryPath
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
  --library-path $CstLibraryPath `
  --connect-mode new
```

This creates a disposable CST project and executes generated setup blocks. It intentionally does not run the solver.

### 6.4 One parametric package live diagnostic

```powershell
& $py -m rf_cem.live_500mhz_parametric_diagnostic `
  --package-dir runs\parametric_geometry_500mhz `
  --library-path $CstLibraryPath `
  --connect-mode new `
  --run-solver
```

Without `--run-solver` it is import/setup only. With it, solver timeout defaults to 7200 seconds.

### 6.5 Postprocessing-template diagnostic

```powershell
& $py -m rf_cem.live_500mhz_postprocessing_diagnostic `
  --package-dir runs\parametric_geometry_500mhz `
  --template-project-dir $TemplateProjectDir `
  --library-path $CstLibraryPath `
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

Owner: live campaign behavior belongs to `workflow/rf-cem-500mhz`; the literature branch inherits this baseline only for review/geometry comparison and must not become a second live-campaign owner.

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
  --template-project-dir $TemplateProjectDir `
  --library-path $CstLibraryPath `
  --start-at-index 1 `
  --max-evals 4
```

### 7.3 seeded SAO

```powershell
& $py -m workflows.rf_cem_500mhz_parametric_opt.live_campaign `
  --mode sao `
  --output-dir runs\rf_cem_sao `
  --template-project-dir $TemplateProjectDir `
  --library-path $CstLibraryPath `
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
$Package = '<LITERATURE_PACKAGE_OR_FILE>'
& $py -m rf_cem.literature_semantics validate --package $Package
```

Accepts a package directory or JSON/YAML file. Returns nonzero on validation errors and prints exact field paths.

### 8.2 `draft-prior`

```powershell
$Package = '<LITERATURE_SEMANTICS_JSON>'
$BasePrior = '<EXPERT_PRIOR_YAML>'
$DraftPrior = '<OUTPUT_DRAFT_PRIOR_YAML>'
& $py -m rf_cem.literature_semantics draft-prior `
  --package $Package `
  --base-prior $BasePrior `
  --out $DraftPrior
```

All generated patch items start `pending` and are hash-bound to the semantic package and base prior.

### 8.3 `merge-prior`

```powershell
$Package = '<LITERATURE_SEMANTICS_JSON>'
$BasePrior = '<EXPERT_PRIOR_YAML>'
$ReviewedDraft = '<REVIEWED_DRAFT_PRIOR_YAML>'
$ReviewedPrior = '<OUTPUT_REVIEWED_PRIOR_YAML>'
& $py -m rf_cem.literature_semantics merge-prior `
  --package $Package `
  --base-prior $BasePrior `
  --draft-prior $ReviewedDraft `
  --out $ReviewedPrior
```

Default `--require-reviewed` blocks pending/rejected/needs-evidence patches. `--allow-unreviewed` is an explicit diagnostic mode and still enforces integrity and ontology validation.

### 8.4 `audit`

```powershell
$Package = '<LITERATURE_SEMANTICS_JSON>'
$DraftPrior = '<DRAFT_PRIOR_YAML>'
$AuditHtml = '<OUTPUT_AUDIT_HTML>'
& $py -m rf_cem.literature_semantics audit `
  --package $Package `
  --draft-prior $DraftPrior `
  --out $AuditHtml
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
$SourcePdf = '<SOURCE_PDF>'
$FigureDir = '<OUTPUT_FIGURE_DIRECTORY>'
$PdfToPpm = '<PDFTOPPM_EXECUTABLE>'
& $py -m rf_cem.literature_semantics render-evidence `
  --pdf $SourcePdf `
  --pages 4 8 9 11 `
  --out-dir $FigureDir `
  --pdftoppm $PdfToPpm `
  --dpi 150
```

Page numbers are one-based. Writes rendered images and `render_manifest.json`.

### 8.8 `corpus-audit`

Isolated human audit:

```powershell
$BundleRoot = '<LOCAL_LITERATURE_BUNDLE_ROOT>'
$Manifest = Join-Path $BundleRoot 'corpus_manifest.json'
$AuditHtml = Join-Path $BundleRoot 'normal_conducting_sls2.html'
& $py -m rf_cem.literature_semantics corpus-audit `
  --bundle-root $BundleRoot `
  --manifest $Manifest `
  --paper-id sls2 `
  --out $AuditHtml
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

Full 3D/profile/Helper2 visual review requires the declared `cad` and `review` extras. Without Plotly the page intentionally falls back to tables; without CadQuery/OCP cached artifacts may remain readable, but a new parameter variant cannot be materialized.

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

The GUI presents these as three review lanes:

1. paper facts and geometry semantics;
2. paper-scoped objectives and constraints;
3. repository mapping proposals / draft patches.

The v1 session still uses one review status for source support and transfer authority. `accepted` means that evidence supports the claim inside the displayed applicability; it is not a universal family rule. Use `accepted_as_soft_only` for single-source numeric values, paper-specific objectives, unverified metric equivalence or non-executable repository mappings.

Unified display schema: `literature_semantic_candidate_view.v1`. Duplicate subjects such as `equator` are grouped; separate cards represent different predicates/claims, not accidental duplicate rows.

Structured Add requires:

- target section;
- unique item ID;
- JSON object;
- evidence/provenance fields.

Added items start pending. Adding or reviewing Evidence/Semantic items updates only the session; it does not request a geometry preview or infer a parameter change.

### 9.3 Geometry projection

Current generator is SLS-2-specific:

- parameters `L/l/r/R/a/b` in mm;
- immutable published baseline;
- content-addressed human variants;
- baseline/previous/current 3D and r-z comparison;
- STEP, BRep, mesh and bounding-box validation;
- candidate-level review state and Chinese note.

It does not derive numeric changes from accepted natural-language semantics.

Geometry review decisions still refresh the candidate review/validation overlay. Kernel materialization is content-addressed: unchanged parameters reuse the existing artifact, while an explicit `L/l/r/R/a/b` submission creates a human-preview variant when values differ.

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

GUI decisions are a source-bound session overlay. They do not rewrite the semantic package or the draft-prior YAML, and they are not an implicit `merge-prior` authorization.

### 9.6 Frozen SLS-2 revision-149 baseline

Baseline ID `sls2.r149.6593e02e` closes the ignored `sls2_gui_isolated_final_20260712` session at revision 149. The frozen decision source is `review_session.v1.json` (30 terminal decisions: 18 `accepted`, 12 `accepted_as_soft_only`); the event source is `review_events.jsonl` with 149 valid records and continuous revisions 1–149. `generation.core.json` remains an immutable geometry-generation record and may say `pending`; it is not a replacement for the frozen human session. Helper2 Geometry/Features/UDSG counts are an independent projection-ID overlay: 8 accepted faces, 9 confirmed candidates and 13 accepted bindings.

The interactive HTML is only the authenticated review view/UI shell. It is not a self-contained final review record, and `review_launch.json` is runtime metadata rather than freeze evidence. Do not choose a snapshot by mtime or treat a pending/accepted snapshot as authoritative over the session. For a new audit, create a new session root; the frozen session is not a writable continuation target.

This closeout is no-CST. It does not run `merge-prior`, change the existing draft YAML, or establish physical acceptance. At the time of this frozen SLS-2 closeout, the family profile was not yet established; Stage C evidence is recorded separately below. Keep validation evidence separate as `geometry_generation`, `human_geometry_review`, `helper2_review`, `live_cst`, and `physical_acceptance`; never summarize this baseline as one `validation_status=pass`.

### 9.7 Family profile v0 (Stage C)

The no-CST family-profile CLI consumes two frozen source manifests and keeps their native payloads separate:

```powershell
& $py -m rf_cem.family_profile build `
  --sls2-baseline-manifest analysis_outputs\rf_cem_literature_pilot_20260710\frozen_baselines\sls2.r149.6593e02e\baseline_manifest.v0.json `
  --rf500-instance-manifest <RF500_OWNER_WORKTREE>\analysis_outputs\rf_cem_family_instance_sources\rf500.2c27faee.b1r3\instance_source_manifest.v0.json `
  --proof-root analysis_outputs\rf_cem_family_profiles `
  --implementation-commit <implementation-commit> `
  --targeted-tests-result "<targeted result>" `
  --full-no-cst-tests-result "<full result>"
& $py -m rf_cem.family_profile validate `
  --profile analysis_outputs\rf_cem_family_profiles\nc_axisymmetric_single_cell_rf_vacuum.<profile-hash-8>\family_profile.v0.json `
  --sls2-baseline-manifest <SLS2_MANIFEST> `
  --rf500-instance-manifest <RF500_MANIFEST>
```

`src/rf_cem/family_profile/` provides the generic `family_profile.v0`/`family_instance.v0` schema, typed containers, finite-value/hash validation, canonical JSON v0 hashing, `Sls2FamilyInstanceAdapter`, `Rf500FamilyInstanceAdapter`, deterministic builder, and source-backed native round-trip verifier. The schema accepts one or more instances with different native schemas, groups, units and dimensions; the Stage C builder intentionally requires the two frozen inputs for its integration proof. The CLI separates structural validation, portable projection validation and source-backed native validation. Without source manifests, `validate` must report `source_roundtrip=not_run` and `roundtrip_all_passed=False`; with both manifests it re-reads and hash-verifies the source objects. The CLI is no-CST and refuses an existing proof target.

The old `nc_axisymmetric_single_cell_rf_vacuum.75f6cba4` proof is retained read-only but superseded because it demonstrated only portable self-consistency. The corrected proof is `nc_axisymmetric_single_cell_rf_vacuum.00414d4f`; it contains `family_profile.v0.json`, `family_profile_validation.v0.json`, `adapter_roundtrip_report.v0.json`, and `source_binding_manifest.v0.json`. The profile core contains no absolute paths. RF500 source-native restoration is `d392... -> d392...`; SLS-2 is `bdc... -> bdc...`. A portable projection hash, when present, is a separate field and is not a native source hash. The family contract excludes RF performance metrics and objectives pending a separate definition (`metric_contract_status=excluded_pending_definition`). `live_cst` and `physical_acceptance` must remain separate validation states and are not established by this CLI.

The Stage C D0 closeout is implemented by `4023eec5c13c72e00857cf4d033dc7f2b3d8ceb1`. Source-backed verification cross-checks the profile's manifest schema, full artifact bindings, adapter-specific native locator, native artifact raw hash, source/native materialized hashes, RF native envelope, and exact native/group scopes. Build provenance keeps portable manifest arguments as `<WORKTREE>/analysis_outputs/...` and records `--implementation-commit`, `--targeted-tests-result`, and `--full-no-cst-tests-result`. D0 does not alter or regenerate the deterministic `00414d4f` profile/proof generated by `619e3051077e8083488b570a7d1be29d80232f3d`. Stage C was merged by PR #4 into `workflow/rf-cem-literature-review` at `3867a9a8eae502359556a83bcad15b3a519e64de`. The active sequence is R0B–R5; metrics/objectives remain excluded, and neither live CST nor physical acceptance is established.

### 9.8 RF boundary semantic core (R1)

`src/rf_cem/semantic/` owns the representation-independent R1 contracts. `build` consumes the corrected Stage C profile plus the frozen SLS-2 generation, literature-semantics and revision-149 review files. It cross-checks source hashes and review revisions, then writes one content-addressed proof without timestamps or absolute paths. It never imports a geometry kernel or CST.

```powershell
$FamilyProfile = 'analysis_outputs\rf_cem_family_profiles\nc_axisymmetric_single_cell_rf_vacuum.00414d4f\family_profile.v0.json'
$Sls2Baseline = 'analysis_outputs\rf_cem_literature_pilot_20260710\frozen_baselines\sls2.r149.6593e02e'
$SemanticRoot = 'analysis_outputs\rf_cem_semantic_core'

& $py -m rf_cem.semantic build `
  --repo-root $RepoRoot `
  --family-profile $FamilyProfile `
  --sls2-generation (Join-Path $Sls2Baseline 'generation.core.json') `
  --sls2-semantics (Join-Path $Sls2Baseline 'literature_semantics.v0.json') `
  --sls2-review (Join-Path $Sls2Baseline 'review_session.v1.json') `
  --output-root $SemanticRoot
```

The current proof directory is `r1_semantic_core.28e8d6fa9efa221f`, content SHA-256 `28e8d6fa9efa221f5fd1e0817bded2e1855066869d0e84c3910529ee2ca248fe`. `build` refuses an existing content-addressed target; use a fresh output root when intentionally testing a second byte-identical build. Never delete or overwrite an older proof just to reuse its name.

Validate either or both graphs against the grammar:

```powershell
$SemanticProof = Join-Path $SemanticRoot 'r1_semantic_core.28e8d6fa9efa221f'
& $py -m rf_cem.semantic validate `
  --grammar (Join-Path $SemanticProof 'family_grammar.v0.json') `
  --graph (Join-Path $SemanticProof 'instances\sls2.r149.6593e02e.instance_boundary_graph.v0.json') `
  --graph (Join-Path $SemanticProof 'instances\rf500.2c27faee.b1r3.instance_boundary_graph.v0.json')

& $py -m rf_cem.semantic diff `
  --left (Join-Path $SemanticProof 'instances\sls2.r149.6593e02e.instance_boundary_graph.v0.json') `
  --right (Join-Path $SemanticProof 'instances\rf500.2c27faee.b1r3.instance_boundary_graph.v0.json')
```

The grammar has a nine-region backbone and `motif.nose_pair.v0` with exact allowed counts 0 or 2. SLS-2 supplies reviewed absence evidence; RF500 supplies the reviewed paired `NoseCone` topology. The diff is semantic/topological and explicitly declines common-parameter comparison. These semantic commands do not compile geometry; the R2 compiler below consumes their contracts without moving representations into the semantic package.

### 9.9 RF boundary representation and Compiler v0/v1 (R2 + TD1/TD2)

Public contracts:

```text
rf_cem.representation.BoundaryRepresentation
rf_cem.representation.LineRepresentation
rf_cem.representation.CircularArcRepresentation
rf_cem.representation.EllipseArcRepresentation
rf_cem.representation.SplineApproxRepresentation
rf_cem.representation.SplineNurbsRepresentation  # deprecated v0 compatibility
rf_cem.representation.CompositeRegionRepresentation
rf_cem.representation.GeometryPatch
rf_cem.representation.RegionGeometry
rf_cem.compiler.CompileRequest
rf_cem.compiler.CompileRecord
rf_cem.compiler.BoundaryContinuityPolicy
rf_cem.compiler.ProfileCompiler.compile
```

`ProfileCompiler.compile` is the single semantic/representation composition entry. Length is in `mm`, tangent angle in `deg`, curvature in `1/mm`, area in `mm^2` and volume in `mm^3`. `boundary_continuity_policy.v0` makes internal and ordinary cross-semantic RF-wall joins G1 hard by default, allows C0 only through an explicit intentional-corner override, supports explicit G2, and classifies endpoints separately. `source_native_segment_ref` is provenance only. Every join records C0 gap, tangent angle, curvature delta and C0/G1/G2 pass regardless of the required level. It creates an oriented outer r-z profile, validates simplicity/nonnegative radius, generates STEP through the isolated CadQuery/OCP worker, validates B-Rep and writes exact hashes into `compile_record.v1`; strict v0 loading remains supported. It never calls CST.

`SplineApproxRepresentation` is canonical `boundary_representation.v1`: `fidelity=approximate`, `backend_contract=cadquery.splineApprox.v0`, `approximation_tolerance_mm=0.001`, `optimization_ready=true`, `exact_nurbs=false`. `SplineNurbsRepresentation` remains only as a deprecated v0 compatibility route; no exact-NURBS runtime exists.

Build both canonical cases into one immutable content-addressed bundle:

```powershell
$CompilerRoot = 'analysis_outputs\rf_cem_boundary_compiler_td1_td2'
$FamilyProof = 'analysis_outputs\rf_cem_family_profiles\nc_axisymmetric_single_cell_rf_vacuum.00414d4f'
$Sls2Baseline = 'analysis_outputs\rf_cem_literature_pilot_20260710\frozen_baselines\sls2.r149.6593e02e'
$SemanticProof = 'analysis_outputs\rf_cem_semantic_core\r1_semantic_core.28e8d6fa9efa221f'

& $py -m rf_cem.compiler build `
  --repo-root $RepoRoot `
  --family-profile (Join-Path $FamilyProof 'family_profile.v0.json') `
  --family-grammar (Join-Path $SemanticProof 'family_grammar.v0.json') `
  --instance-boundary-graph (Join-Path $SemanticProof 'instances\sls2.r149.6593e02e.instance_boundary_graph.v0.json') `
  --instance-boundary-graph (Join-Path $SemanticProof 'instances\rf500.2c27faee.b1r3.instance_boundary_graph.v0.json') `
  --sls2-generation (Join-Path $Sls2Baseline 'generation.core.json') `
  --sls2-baseline-step (Join-Path $Sls2Baseline 'cavity.step') `
  --output-root $CompilerRoot
```

The current TD1/TD2 bundle is `r2_boundary_compiler.8f47ca735db8ce8a`, input SHA-256 `8f47ca735db8ce8ae4f0d6bb55555e22e5aa3726a72b8f9a661f5d3a492c9610`. `build` refuses an existing target. It writes two compiled profiles, two normalized STEP files, two v1 records and a source-binding manifest. SLS-2 contains 9 regions/10 patches; RF500 contains 11 regions/12 patches. The original v0 bundle `r2_boundary_compiler.aa66a3e90125437b` remains unchanged and readable.

Validate strict record identity and every output artifact size/hash:

```powershell
$CompilerProof = Join-Path $CompilerRoot 'r2_boundary_compiler.8f47ca735db8ce8a'
& $py -m rf_cem.compiler validate `
  --record (Join-Path $CompilerProof 'records\sls2.r149.6593e02e.compile_record.v1.json') `
  --record (Join-Path $CompilerProof 'records\rf500.2c27faee.b1r3.compile_record.v1.json') `
  --bundle-root $CompilerProof
```

The RF500 accepted STEP is hash-bound but not locally materialized. Its passing comparison is deliberately limited to source-native profile equivalence plus new B-Rep validity and retains an explicit warning. Neither command defines RF metrics, runs CST, claims physical acceptance, induces a family or performs optimisation.

### 9.10 RF family induction/extension v0/v1 (R3 + TD3)

`src/rf_cem/semantic/induction/` aligns intrinsically valid reviewed instance graphs and emits a proposal; family admission is a separate post-patch check. It does not discover semantics from raw pixels/STEP or import the representation package. `FamilyInductionEngine` runs paired optional, single optional and alternative-topology fallback detectors. A new proposal is always pending/non-mutating. v1 support contains structure/evidence/review/cross-instance fields, population, symmetry and detector identity; `proposal_score` is explicitly `heuristic_support_not_probability`. `review_proposal` keeps grammar byte-identical for `rejected`/`needs_evidence`; only accepted review can create/apply a hash-bound patch.

Build the canonical accepted-review proof from the two R1 training graphs and the two held-out LEReC primary PDFs:

```powershell
$InductionRoot = 'analysis_outputs\rf_cem_family_induction'
$InductionSources = Join-Path $InductionRoot 'sources\lerec704'
$SemanticProof = 'analysis_outputs\rf_cem_semantic_core\r1_semantic_core.28e8d6fa9efa221f'

& $py -m rf_cem.semantic.induction build-ablation `
  --repo-root $RepoRoot `
  --family-grammar (Join-Path $SemanticProof 'family_grammar.v0.json') `
  --training-graph (Join-Path $SemanticProof 'instances\sls2.r149.6593e02e.instance_boundary_graph.v0.json') `
  --training-graph (Join-Path $SemanticProof 'instances\rf500.2c27faee.b1r3.instance_boundary_graph.v0.json') `
  --lerec-design-pdf (Join-Path $InductionSources 'source.pdf') `
  --lerec-test-pdf (Join-Path $InductionSources 'design_and_test_2018.pdf') `
  --output-root 'analysis_outputs\rf_cem_family_induction_ablation' `
  --review-decision accepted `
  --reviewer-id codex.r3-explicit-review `
  --review-rationale 'Explicit closeout review: graph locators and paired residual adjacency support the optional nose motif; LEReC remains held out until after patch application.' `
  --review-revision 1
```

The current ablation proof is `r3_family_induction_ablation.59db0a7b5f8e158c`, input SHA-256 `59db0a7b5f8e158cddd713f6ff8c4bafd8b2fa56ac08eb000c819c3c70054312`. Its seed removes nose motif/cardinality/insertion adjacency while RF500 retains reviewed NoseRegion; accepted review emits `add_optional_motif` and both real graphs then pass admission. The command refuses an existing target. The original v0 proof `r3_family_induction.2f6c02557798e606` remains unchanged/readable.

Validate the manifest, all eight artifacts and every cross-contract identity:

```powershell
$InductionProof = 'analysis_outputs\rf_cem_family_induction_ablation\r3_family_induction_ablation.59db0a7b5f8e158c'
& $py -m rf_cem.semantic.induction validate --bundle $InductionProof
```

The output additionally contains `family_grammar.seed_ablation.v0.json`, `family_extension_proposal.v1.json` and a v1 manifest. The real result selects `paired_optional_motif`; a synthetic test covers a non-symmetric single optional motif and fallback tests cover alternative topology. It records accepted review, explicit add/diff, both training graphs admitted and held-out classification `known_optional_motif_present`. `representation_contract=not_imported_or_modified` and `live_cst_status=not_run`; no RF metric or physical acceptance is established.

### 9.11 RF boundary observation and engineering constraints (R4)

`src/rf_cem/observation/` observes passing R2 compiled geometry through generic representation operations plus reviewed R1 topology. It never reads source-native parameter/feature names, generates geometry, mutates geometry or calls CST. Exact geometry, normalized semantic shape and scalar descriptors are separate hash-bound layers. Build the canonical proof from exactly two compile records and their matching graphs:

```powershell
$ObservationRoot = 'analysis_outputs\rf_cem_observation_contract_td'
$SemanticProof = 'analysis_outputs\rf_cem_semantic_core\r1_semantic_core.28e8d6fa9efa221f'
$CompilerProof = 'analysis_outputs\rf_cem_boundary_compiler_td1_td2\r2_boundary_compiler.8f47ca735db8ce8a'

& $py -m rf_cem.observation build `
  --root $RepoRoot `
  --output-root $ObservationRoot `
  --compile-record (Join-Path $CompilerProof 'records\sls2.r149.6593e02e.compile_record.v1.json') `
  --compile-record (Join-Path $CompilerProof 'records\rf500.2c27faee.b1r3.compile_record.v1.json') `
  --instance-graph (Join-Path $SemanticProof 'instances\sls2.r149.6593e02e.instance_boundary_graph.v0.json') `
  --instance-graph (Join-Path $SemanticProof 'instances\rf500.2c27faee.b1r3.instance_boundary_graph.v0.json') `
  --architecture-document 'docs\RF_CEM_ROADMAP_AND_ARCHITECTURE.md'
```

The current TD1/TD2 regression proof is `r4_observation_contract.a0fd43bd4bf4de2f`, input SHA-256 `a0fd43bd4bf4de2f8a2ea9e6777154b541556a189ee888f4c2e895c0e0383b20`. It binds 11 sources and declares 25 artifacts: one 21-definition descriptor registry, six reviewed constraint demonstrations, two exact references, two 65-sample-per-region shape observations, two bundles with 240 values, and 12 evaluations. The original R4 proof remains unchanged/readable through an exact canonical bundle/path/hash/size compatibility allowlist for its three evolved tracked inputs; arbitrary source mismatches still fail closed.

The command refuses an existing content-addressed target. Never delete or overwrite a proof to reuse its name. Strictly validate its source hashes, artifact inventory, input preimage and cross-contract identities with:

```powershell
$ObservationProof = Join-Path $ObservationRoot 'r4_observation_contract.a0fd43bd4bf4de2f'
& $py -m rf_cem.observation validate --bundle $ObservationProof
```

R4 length/radius values use `mm`, curvature uses `1/mm`, area uses `mm^2`, volume uses `mm^3`, tangents use dimensionless `1`, and discrete values use `count`/`bool`. Unknown units, non-finite values, invalid landmarks and descriptor/constraint scope mismatches fail closed. The canonical manifest records `live_cst_status=not_run` and `physical_acceptance_status=not_established`; no RF metric, mode, field or optimization contract is defined.

### 9.12 RF-CEM Workbench W0/W1/W2/W3/W4 (R0B/R1/R2/R3/R4)

`src/rf_cem/workbench/` builds a deterministic, disposable SQLite read model. The tracked `config/rf_cem_workbench_profile.v0.json` is the canonical portable W0–W4 recipe: every path is repository-relative, the database remains ignored, and `optional_w5_bundle` is reserved. Profile status verifies declared-source presence, every indexed source hash, and the profile recipe hash itself. Use the profile interface for ordinary status/rebuild/serve:

```powershell
$WorkbenchProfile = 'config\rf_cem_workbench_profile.v0.json'

& $py -m rf_cem.workbench status `
  --repo-root $RepoRoot `
  --profile $WorkbenchProfile

& $py -m rf_cem.workbench rebuild `
  --repo-root $RepoRoot `
  --profile $WorkbenchProfile

& $py -m rf_cem.workbench serve `
  --repo-root $RepoRoot `
  --profile $WorkbenchProfile `
  --port 0
```

`blocked_missing_sources` lists exact missing repository-relative paths and is not rebuildable; `missing`, `stale` or `invalid` with complete sources requires an atomic rebuild; only `fresh` should be served. The explicit-source form below remains a compatibility/recovery interface for intentionally selected historical v0 proofs.

```powershell
$WorkbenchDatabase = 'analysis_outputs\rf_cem_workbench\w4.sqlite'
$FamilyProof = 'analysis_outputs\rf_cem_family_profiles\nc_axisymmetric_single_cell_rf_vacuum.00414d4f'
$Sls2Baseline = 'analysis_outputs\rf_cem_literature_pilot_20260710\frozen_baselines\sls2.r149.6593e02e'
$SemanticProof = 'analysis_outputs\rf_cem_semantic_core\r1_semantic_core.28e8d6fa9efa221f'
$CompilerProof = 'analysis_outputs\rf_cem_boundary_compiler\r2_boundary_compiler.aa66a3e90125437b'
$InductionProof = 'analysis_outputs\rf_cem_family_induction\r3_family_induction.2f6c02557798e606'
$ObservationProof = 'analysis_outputs\rf_cem_observation_contract\r4_observation_contract.d06695921d941eee'

& $py -m rf_cem.workbench rebuild `
  --database $WorkbenchDatabase `
  --repo-root $RepoRoot `
  --family-profile (Join-Path $FamilyProof 'family_profile.v0.json') `
  --family-profile-validation (Join-Path $FamilyProof 'family_profile_validation.v0.json') `
  --architecture-document 'docs\RF_CEM_ROADMAP_AND_ARCHITECTURE.md' `
  --literature-package (Join-Path $Sls2Baseline 'literature_semantics.v0.json') `
  --review-session (Join-Path $Sls2Baseline 'review_session.v1.json') `
  --family-grammar (Join-Path $SemanticProof 'family_grammar.v0.json') `
  --instance-boundary-graph (Join-Path $SemanticProof 'instances\sls2.r149.6593e02e.instance_boundary_graph.v0.json') `
  --instance-boundary-graph (Join-Path $SemanticProof 'instances\rf500.2c27faee.b1r3.instance_boundary_graph.v0.json') `
  --instance-graph-diff (Join-Path $SemanticProof 'instance_graph_diff.v0.json') `
  --compile-record (Join-Path $CompilerProof 'records\sls2.r149.6593e02e.compile_record.v0.json') `
  --compile-record (Join-Path $CompilerProof 'records\rf500.2c27faee.b1r3.compile_record.v0.json') `
  --family-induction-bundle $InductionProof `
  --observation-contract-bundle $ObservationProof

& $py -m rf_cem.workbench status `
  --database $WorkbenchDatabase `
  --repo-root $RepoRoot

& $py -m rf_cem.workbench serve `
  --database $WorkbenchDatabase `
  --repo-root $RepoRoot
```

`rebuild` validates required source schemas, requires the real instance IDs `sls2.r149.6593e02e` and `rf500.2c27faee.b1r3`, and requires the complete W1 triple (one grammar, exactly two graphs, one diff) when any W1 source is supplied. It revalidates both graphs against the grammar and recomputes the directed SLS-2-to-RF500 diff. W2 additionally requires exactly two unique canonical compile records under immutable bundle `records/` directories and rechecks profile/grammar/graph canonical/raw hashes, instance/region order, landmarks, representation reuse, no-CST/physical status and all output bindings. W3 additionally refuses to run without complete W2, loads one immutable R3 directory, checks its manifest/eight artifacts/two primary PDFs/representation sentinel, rebinds both training graphs and base/patched grammar, requires accepted manual review and an applied patch, revalidates both training graphs, and proves the LEReC graph was held out. W4 refuses to run without complete W3, strictly reloads one immutable R4 bundle, checks its 11 declared sources and 25 artifacts, requires both canonical instances and all exact/shape/registry/bundle/constraint/evaluation bindings, and indexes located findings without treating them as physical acceptance. It writes to a temporary database, atomically replaces the named target and refuses source paths outside the repository. Rebuilding from identical bytes yields the same canonical registry snapshot and input-set SHA-256; SQLite file bytes themselves are not the contract. The database belongs under ignored `analysis_outputs/`, is never committed, and can always be rebuilt from the listed truth sources.

The current full W2 source set rebuilds to 17 fresh sources, 372 entities and 534 relations. Two consecutive rebuilds produced input-set SHA-256 `91f6fdc82ba77f73f8b452b3a0499ad56178f23719f0848978af4a743b591a74`; its canonical portable snapshot SHA-256 is `d9139bfe7d3a4e2a536545addc45999a61f5fa337dd23733a3c6379a28b271fc`.

The current full W3 source set rebuilds to 29 fresh sources, 418 entities and 571 relations. Its input-set SHA-256 is `97fab22424ed421108f99b81ca6d629a52d7e6e8d2d368589ee1cdddb95ded18`; canonical portable snapshot SHA-256 is `f51eadc28ad97d1b2207e15a96ccedd5b42bcec280a43667587a573abcc6c66e`. The W3-specific inventory includes one alignment, 9 backbone slots, 2 residuals, one proposal/review/patch/application, 6 grammar-diff rows, one held-out graph, one blind validation and the passing `w3.family-induction-hard-gate`.

The current full W4 source set rebuilds to 66 fresh sources, 779 entities and 1484 relations. Two consecutive rebuilds produced input-set SHA-256 `b5cffc768d13956af8426ddf99f7081a4b6bfa98b2211c8bd5d6aff2d0fae0bb`; canonical portable snapshot SHA-256 is `39eea8fbae12e90726246666057c93d18a0023c53d9357ed9a094cbde2b84b49`. W4 adds 2 exact references, 2 shape observations, 20 region observations, 24 landmark observations, 21 descriptor definitions, 240 descriptor values, 6 constraints, 12 evaluations/findings and the passing `w4.observation-contract-hard-gate`.

The tracked TD1–TD3/Desktop profile uses the v1 R2 compile pair, ablation R3 and current R4 regression proof. Two consecutive rebuilds produce 65 fresh sources, 738 entities and 1539 relations, input-set SHA-256 `6bcfd185b18fb3011aff2279c383db4984158fb7e926cce749b5834c8c06e7ad` and portable snapshot SHA-256 `56d8d9a8b63358fa8a12f02d3183bf9f78ab05477b810c895f8b631ac8fd302c`. The lower entity count than the historical full W4 recipe reflects removal of optional literature/review display sources from this portable profile, not loss of W1–W4 hard-gate entities.

`status` opens SQLite in read-only mode and re-hashes every indexed source. `serve` binds only to `127.0.0.1`, chooses a random port/token and prints the authenticated URL. It exposes fixed GET pages/APIs for overview, families, instances, semantics, **Semantic Graphs / W1**, representations, algorithms, reviews, validation, roadmap/gates, capability coverage, **Compile Records / W2**, **Family Induction / W3** and **Observations & Constraints / W4**. W2 shows explicit policy source/required level/endpoints and all continuity diagnostics. W3 v1 shows seed grammar, selected detector, structured support, symmetry/population, pending proposal, accepted review, `add_optional_motif`, diff, final admission, single-detector fixture and blind result. Host/Origin/token checks are fail-closed; POST is rejected and there is no shell, arbitrary file browser, CST action, filesystem mutation or write API. Stop a foreground CLI process with Ctrl+C.

R4 implements representation-independent geometry observations and non-mutating constraint evaluation, but not RF result/mode/field contracts, RF metric equivalence, live-CST validation or physical acceptance. Those remain gated by R5.

### 9.13 Workbench Desktop v0

Source entry and local Windows build:

```powershell
& $py -m rf_cem.workbench.desktop --self-test --repo-root $RepoRoot --no-browser
& .\scripts\build_rf_cem_workbench_desktop.ps1
& .\dist\RF-CEM-Workbench.exe --self-test --repo-root $RepoRoot --no-browser
```

The build script requires PyInstaller in the active repository `.venv`, builds one ignored `dist/RF-CEM-Workbench.exe`, excludes CST/CadQuery/OCP/scientific stacks from the thin launcher, and automatically runs the EXE self-test. The binary is local output and must not be committed. Normal double-click use finds the repository in this order: explicit `--repo-root`, EXE parents, cwd parents, saved config, then a folder picker. `%LOCALAPPDATA%\RF-CEM\workbench_launcher_config.v0.json` stores only the chosen absolute repo plus repository-relative profile; logs are in the same user-local directory.

The native window has exactly these fixed actions: Open/Start Workbench, Rebuild Database, Refresh Source Status, Stop Workbench, Open Roadmap, Open Project Status, Open `analysis_outputs`, Copy Workbench URL, Run Quick no-CST Self Check, and View Logs. There is no arbitrary command field. Every subprocess uses a fixed argument tuple and `shell=False`; the launcher can stop only its held child. Open/Start serves a fresh database immediately, atomically rebuilds a complete missing/stale database, or shows missing-source diagnostics. It starts only the existing token-authenticated loopback GET-only Web Workbench and opens the default browser unless `--no-browser` is passed. It has no CST/live/R5/license/cleanup/process-sweep action.

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
$WarmupIndex = '<WF2_WARMUP_INDEX_JSONL>'
$SmokeConfig = '<WF2_SMOKE_CONFIG_YAML>'
& $py run_workflow_2.py --help
& $py run_workflow_2.py --auto-resume --heartbeat
& $py run_workflow_2.py --auto-resume --recovery-only
& $py run_workflow_2.py --warmup-from-db $WarmupIndex
& $py run_workflow_2.py --config $SmokeConfig --smoke-only
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
$EvaluationDb = '<TOLERANCE_EVALUATION_DB>'
& $py -m workflows.rfgun_tolerance.cli `
  --db $EvaluationDb `
  --output runs\tolerance\report.md
```

Cross-level analysis, no-CST:

```powershell
$Tolerance3Db = '<TOLERANCE_3UM_DB>'
$Tolerance5Db = '<TOLERANCE_5UM_DB>'
& $py -m workflows.rfgun_tolerance.campaign_cli `
  --config config\default.yaml `
  --db "3=$Tolerance3Db" `
  --db "5=$Tolerance5Db" `
  --output runs\tolerance\campaign_report.md
```

### 10.4 WF4: `workflow/4-rfgun-hom-eigenmode`

```powershell
$CampaignRoot = '<WF4_CAMPAIGN_ROOT>'
& $py run_workflow_4.py --help
& $py run_workflow_4.py --plan-only
& $py run_workflow_4.py --resume-preview
& $py run_workflow_4.py --offline-only $CampaignRoot
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

RF-CEM R0B–R4 architecture, semantic, compiler, induction, observation and Workbench:

```powershell
& $py -m pytest -q `
  tests\test_rf_cem_architecture_boundaries.py `
  tests\test_rf_cem_semantic_core.py `
  tests\test_rf_cem_boundary_compiler.py `
  tests\test_rf_cem_family_induction.py `
  tests\test_rf_cem_observation_contract.py `
  tests\test_rf_cem_workbench.py `
  tests\test_rf_cem_workbench_desktop.py
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
