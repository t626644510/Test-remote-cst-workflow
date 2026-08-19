# Agent Project Status Context

Status timestamp: 2026-08-19 Asia/Shanghai

Repository family: CST accelerator-cavity automation and surrogate optimisation

Repository root: resolve locally with `git rev-parse --show-toplevel`; no workstation path is canonical.

Canonical branch: `workflow/rf-cem-literature-review`

Pre-handoff documentation baseline: `0a675df8714564e03ce305959095183524238850`

This file is the detailed machine-oriented project state. Current code, tests, Git graph, and local runtime evidence have higher authority than prose. Historical tags, reports, archived Markdown, and campaign summaries are evidence only.

## 1. Documentation contract

The maintained project-document set is:

| Path | Contract |
| --- | --- |
| `README.md` | Chinese human handoff, background, current progress, basic use. |
| `CONTRIBUTING.md` | Chinese Git/PR workflow, branch routing and contributor checklist. |
| `docs/PROJECT_STATUS_CONTEXT.md` | This authoritative agent state model. |
| `docs/AGENT_CONTEXT_RECOVERY.md` | Recovery procedure after crash, compaction, or agent handoff. |
| `docs/FUNCTIONS_AND_ENTRYPOINTS.md` | Feature and executable-entry inventory. |
| `docs/CST_AUTOMATION_INTERFACES.md` | CST official APIs, verified wrappers, and direct-file evidence. |
| `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md` | RF-CEM architecture decisions, Workbench W0/W1 contract, and R0B–R5 gates. |
| `.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md` | Active autonomous R0B–R5 execution and phase-closeout contract. |
| `AGENTS.md` | Automatically loaded governance/index stub; not a status document. |
| `.github/pull_request_template.md` | Maintained review checklist; collaboration infrastructure, not project state. |
| `.github/workflows/no-cst.yml` | Cross-branch offline validation gate; collaboration infrastructure, not project state. |

All tracked Markdown that existed before consolidation was archived at:

```text
documentation_archive/markdown_before_consolidation_20260712_HEAD-0663994.zip
SHA-256: 342f999e67bc10ccf6a8d7d6685ca57a93bc27fb666c9c5c61516b0c5e986ab6
```

Generated run reports may still use a `.md` extension. They are runtime artifacts, not maintained repository documentation.

## 2. Non-negotiable invariants

1. `main` is a strict shared-core baseline. It contains no concrete workflow packages, workflow entry points, campaign configuration, or workflow-only tests.
2. Concrete workflows live only on their canonical `workflow/*` branch.
3. Shared code owner is `src/cst_optimization/`; generic history and STEP tools are `src/cst_history_extractor/` and `src/step_feature_assistant/`.
4. Workflow-specific behavior remains inside its workflow package until a stable cross-workflow contract and at least two real consumers exist.
5. Never invent `cst.interface` or `cst.results` APIs. Use user-supplied official documentation or repository wrappers already verified.
6. Frequency, Q, field, power, impedance, gradient, wake, and derived objectives require explicit units and assumptions.
7. Local configs, CST projects, PDFs, STEP inputs, result folders, databases, JSONL, NPZ, checkpoints, sessions, logs, and scratch scripts are not source artifacts.
8. no-CST and live-CST evidence are recorded separately.
9. Running CST does not imply permission to kill processes, delete locks, remove result folders, overwrite campaigns, or launch recovery.
10. A large change requires a backup before mutation.

## 3. Canonical Git/worktree topology

State observed on 2026-07-13. Worktree directories are local choices and deliberately omitted; discover them with `git worktree list --porcelain`.

| Responsibility | Branch/ref | Status | Audited baseline HEAD |
| --- | --- | --- | --- |
| Shared core | `main` | canonical | `8f3f89d7f6627feb98f8338416500a4ce457a31c` |
| WF1 SAO | `workflow/1-rfgun-sao` | canonical | `63207ba5a992d44823a19b8b848a4f542e1f0b6a` |
| WF2 HOM antenna | `workflow/2-rfgun-hom-antenna` | canonical | `6a6c99d484362ce02c08589d0b3bd0e2793ce9e0` |
| WF3 recovery/tolerance | `workflow/3-rfgun-recovery-tolerance` | canonical | `5ba5e1f4a2c505dcdbf82eb55b45c7ca5c924430` |
| WF4 HOM eigenmode | `workflow/4-rfgun-hom-eigenmode` | canonical | `7226c0fa01b3e913ca88a4272b22ad54846fc709` |
| RF-CEM live geometry/campaign | `workflow/rf-cem-500mhz` | canonical | `af690d5d946406e2876679d62489574d4fa3807d` |
| Literature semantics staging | `codex/rf-cem-literature-semantics-hardening` | historical staging ref | `38039219bdce73ef9aaf490d911ba0a1dffe758a` |
| RF-CEM literature review/GUI and R0B–R5 architecture | `workflow/rf-cem-literature-review` | canonical; Stage C and R0B integrated by PRs #4/#5 | R0B merge commit `c0b4574ee2dc87ee98938b282ec023aeebfa12d3`; R1 closeout is being prepared |

The runtime-feature baseline originally audited here was exactly 3 commits ahead and 0 commits behind `workflow/rf-cem-500mhz`:

1. `3803921 feat(rf-cem): harden literature semantics pipeline`
2. `6faeee7 feat(rf-cem): add interactive literature geometry review`
3. `0663994 feat(rf-cem): isolate paper reviews and integrate helper2 audit`

The documentation-consolidation and handoff commits sit on top of that feature baseline; resolve the current HEAD with Git rather than copying a prose hash. `workflow/rf-cem-literature-review` is now an independent canonical workflow branch, not an experiment waiting for wholesale merge into `workflow/rf-cem-500mhz`. The two branches share ancestry but have different owners: live cavity optimisation remains on `workflow/rf-cem-500mhz`; literature evidence, semantics and human review remain here.

WF2 compatibility ref `codex/S01-known-mode-pso-closure` points to the same commit as its canonical workflow branch. Other `backup/*` refs are recovery evidence, not development baselines.

## 4. Source ownership model

### 4.1 Shared core on `main`

| Package/path | Responsibility |
| --- | --- |
| `src/cst_optimization/core/` | CST connection, project, solver, results, retry, timeout, cleanup. |
| `src/cst_optimization/evaluation/` | Evaluation DB schema/storage/dedup/warm start/reuse/failure skip/retry runtime. |
| `src/cst_optimization/objectives/` | Generic frequency, quality, field, mode objectives. |
| `src/cst_optimization/optimization/` | SAO, SAEA, acquisition, sampling, adaptive bounds, conditional gates, resume. |
| `src/cst_optimization/parameters/` | Typed parameters, bounds, geometry parameter sets. |
| `src/cst_optimization/physics/` | Unit-aware cavity, wakefield, Poynting, heating formulas. |
| `src/cst_optimization/workflows/` | Stable generic evaluator/recovery contracts only. |
| `src/cst_optimization/factory.py` | Shared config-to-object builders; no concrete workflow builders. |
| `src/cst_optimization/runner.py` | `BaseRunner` for workflow CLIs. |
| `src/cst_optimization/checkpoint.py` | Checkpoint state management. |
| `src/cst_optimization/database.py` | Curve/result recording and offline replay infrastructure. |
| `src/cst_history_extractor/` | History/macro extraction, classification, recipe manifest. |
| `src/step_feature_assistant/` | STEP topology, geometry facts, Feature candidates, partial UDSG, reviewer. |

### 4.2 Current literature-review workflow additions

| Package/path | Responsibility |
| --- | --- |
| `src/rf_cem/design_package.py` | 500 MHz baseline paths and package structure. |
| `src/rf_cem/history_templates.py` | Extract verified setup blocks from baseline `ModelHistory.json`. |
| `src/rf_cem/udsg_builder.py` | Baseline semantic/UDSG construction. |
| `src/rf_cem/translator.py` | Deterministic CST actions, mapping table, VBA script, report. |
| `src/rf_cem/parametric_geometry/` | STEP ingest, feature projection, grammar, reconstruction, validation, interfaces. |
| `src/rf_cem/literature_semantics/` | arXiv/PDF evidence, semantic schema, prior draft, audits, GUI, geometry candidate. |
| `src/rf_cem/family_profile/` | Source-lossless `family_profile.v0` and two real-instance adapters. |
| `src/rf_cem/semantic/` | R1 representation-independent `family_grammar.v0`, instance graphs, ontologies, motifs, interfaces, graph diff, source adapters, and deterministic proof bundles. |
| `src/rf_cem/representation/` | Family-independent mathematical boundary representation; full R2 contract is not yet implemented. |
| `src/rf_cem/compiler/` | Sole semantic/representation composition boundary; Compiler v0 is deferred to R2. |
| `src/rf_cem/observation/` | Read-only observation boundary; full R4 contract is not yet implemented. |
| `src/rf_cem/workbench/` | R0B/W1 no-CST derived SQLite registry and authenticated loopback read-only catalog/semantic-graph views. |
| `workflows/rf_cem_500mhz_parametric_opt/` | no-CST scan and live campaign. |

The current literature and geometry-review implementation remains RF-CEM-specific. It is not eligible for `main` promotion until a second real workflow uses a stable subset.

## 5. Workflow status matrix

Maturity terms:

- `FM0` concept only;
- `FM1` no-CST prototype;
- `FM2` real single-case or controlled live validation;
- `FM3` repeatable batch/campaign;
- `FM4` operational with portable, idempotent recovery.

Architecture terms:

- `AC0` implicit;
- `AC1` explicit interfaces;
- `AC2` auditable provenance/validation;
- `AC3` fail-closed and recoverable;
- `AC4` versioned reuse with multiple consumers.

| Capability | FM | AC | State |
| --- | ---: | ---: | --- |
| Shared CST wrappers | FM3 | AC2 | Used across workflows; API boundary documented. Some cleanup paths are intentionally high risk. |
| Evaluation DB/retry | FM3 | AC3 | Extensive no-CST coverage; concrete ownership differs by workflow. |
| CST history extractor | FM2 | AC2 | Exported macro and direct `ModelHistory.json` supported; direct format is unofficial. |
| STEP Feature Assistant | FM2 | AC2 | CadQuery/OCP facts, stable generated IDs, review HTML, resolved labels, calibration and advisory ML. |
| WF1 | FM3 | AC2-3 | Single/two pass, roles/gates, staged/adaptive search, DB/retry; live configuration is opt-in. |
| WF2 | FM3 | AC3 | Closure branch, dual-project orchestration, recovery, warmup, bounded unknown-HOM fit. |
| WF3 | FM2-3 | AC2 | Recovery and tolerance chain; local datasets remain external. |
| WF4 | FM3 | AC3 | Campaign and offline audit; physical ambiguity/enumeration censoring remain. |
| RF-CEM design package | FM3 | AC2 | 500 MHz chain and batch live results verified. |
| RF-CEM parametric geometry | FM3 | AC2 | 12D candidate regeneration stable; physical hard gates incomplete. |
| RF-CEM result readback | FM3 | AC2 | Frequency, R/Q, Q verified through result-tree paths. |
| RF-CEM campaign | FM3 | AC2 | 60/60 success; objective, arbitrary record seed, resume lifecycle incomplete. |
| Literature semantics | FM2 | AC2-3 | Fixed-version two-paper pilot, validation, hashes, draft merge gates, audit HTML. |
| Literature review GUI | FM1-2 | AC2-3 | Functional no-CST local GUI with isolated paper/regime sessions and Helper2 integration. |
| Family profile v0 | FM1 | AC3 | Stage C source-native two-instance profile; metrics, live CST and physical acceptance remain excluded. |
| RF-CEM Workbench W0 | FM1 | AC2-3 | Deterministic derived registry, source-hash audit, fixed read-only views and no-CST security tests. |
| RF boundary semantic core R1 | FM1-2 | AC3 | One reviewed family grammar accepts the nose-free SLS-2 and paired-nose RF500 topologies; evidence-bound diff is parameter-independent. |
| RF-CEM Workbench W1 | FM1 | AC3 | W0 registry extended with grammar, ontology, motif, graph, interface, nose-state and graph-diff views. |
| Multi-cell/X-band grammar | FM0 | AC0 | Planned only; STEP semantic profile exists but no RF-CEM generation closure. |
| Multi-physics/HOM/coupler RF-CEM | FM0 | AC0 | Explicitly out of current scope. |

## 6. RF-CEM 500 MHz state

### 6.1 Geometry contract

Current selected variant: `free_equator_smooth`.

Current optimisation preset: `exploratory_12d`.

The 12 parameters are:

1. shared equator crown radial offset, mm;
2. equator crown axial midpoint, mm;
3. left shoulder absolute z, mm;
4. right shoulder absolute z, mm;
5. left shoulder radial offset, mm;
6. right shoulder radial offset, mm;
7. left nose internal radial offset, mm;
8. right nose internal radial offset, mm;
9. left nose internal axial offset, mm;
10. right nose internal axial offset, mm;
11. left blend arc radius offset, mm;
12. right blend arc radius offset, mm.

Parameter values are written into an expert-prior override, then the pipeline regenerates:

```text
resolved_expert_prior
  -> profile segments
  -> parametric_geometry.v0.json
  -> generated_vacuum.step
  -> geometry_validation.json
  -> CSTTranslator payload
```

`parametric_geometry.v0.json` is the run truth source. STEP is an export artifact. CST `StoreParameter` is not the geometry source of truth for this workflow.

Variants retained by the grammar:

| Variant | Role |
| --- | --- |
| `iris_torus_exact` | Evidence-exact nose/blend reference. |
| `expanded_smooth_nose` | Smooth-nose reference with conventional equator. |
| `free_equator_smooth` | Current selected working baseline. |
| `manual_equator_inset_3mm` | Visual inward crown probe. |
| `manual_equator_bulge_3mm` | Visual outward crown probe. |
| `manual_equator_wide_soft` | Wider soft inward-crown probe. |

CadQuery-native smooth curves can fall back to dense sampled profiles. The generation mode and fallback provenance must remain in validation output.

### 6.2 Live CST contract

Verified path:

- CST 2026 Python libraries;
- disposable or candidate-specific project;
- global background material `Copper (annealed)`, conductivity `5.8e7 S/m`;
- imported RF-vacuum body explicitly assigned `Vacuum`;
- `Tetrahedral` eigenmode solver, `Solver_HF_TET_E`;
- template registration through `Model/3D/Model.rpp` plus three `.r0d` artifacts;
- saved result readback through `cst.results.ProjectFile`.

Verified result paths:

```text
Tables\0D Results\Frequency (Mode 1)                 [MHz]
Tables\0D Results\R over Q (Mode 1)                  [Ohm]
Tables\0D Results\Q-Factor (Perturbation) (Mode 1)   [dimensionless]
```

Representative live evidence:

- Frequency: 505.583944055 MHz;
- R/Q: 428.086330643 ohm;
- Q perturbation: 45867.1264209.

Campaign evidence: 60 evaluations, 60 `SUCCESS`. Candidate 039 was the recorded R/Q leader; candidate 046 was the recorded `R=(R/Q)*Q` leader. These remain audit candidates, not accepted designs.

`EvaluateResultTemplates` is not enabled by default. On the verified Tetrahedral path it may emit a non-blocking `HEX mesh is invalid` message even when the required result-tree values are readable.

### 6.3 Objective gap

Current physical intent:

```text
frequency acceptance: 490 MHz <= f <= 510 MHz
primary improvement: maximize R/Q and R=(R/Q)*Q
Q: soft floor, currently 30000
novelty: optional low-weight term
```

The current scalar penalty still over-rewards proximity to 500 MHz inside the acceptable band. Required hardening:

- explicit zero/weak penalty inside the configured window;
- distance-to-nearest-boundary penalty outside the window;
- tests at 490, 500, 510 MHz and immediately outside both boundaries;
- versioned weights and normalization;
- no infinite reward for Q above the soft floor.

### 6.4 Campaign lifecycle gap

Current CLI can seed SAO from a configured quick-scan candidate index. It cannot yet load an arbitrary prior `live_records.jsonl` item. It also lacks a complete fail-closed output-directory resume contract.

Required additions before FM4:

- `--seed-record-path` and `--seed-record-index`;
- schema, dimension, name, unit, finite-value and bounds validation;
- record/file hash provenance;
- output-directory collision refusal by default;
- explicit `--resume` with next-index and optimizer-state restoration;
- no record duplication and no candidate/project overwrite;
- interrupted/incomplete record semantics.

## 7. Literature semantics state

### 7.1 Safety model

Allowed pipeline:

```text
arXiv discovery metadata
  -> human selection of explicit version
  -> immutable PDF + SHA-256 manifest
  -> selected PDF pages
  -> literature_semantics.v0
  -> expert_prior.draft.v0
  -> human review
  -> optional reviewed merge
```

Disallowed automatic transition:

```text
search rank / natural language / image pixels
  -X-> production geometry / STEP / CST command / campaign
```

Search rank is not authority. PDF ingestion requires an explicit arXiv version. Image-only evidence cannot support a hard numeric rule. Single-source numeric values are soft candidates. All executable patches are pending by default.

### 7.2 Semantic schema

`literature_semantics.v0` top-level sections:

- `request_context`;
- `evidence_sources`;
- `text_evidence`;
- `image_evidence`;
- `classification`;
- `named_features`;
- `shape_motifs`;
- `curve_priors`;
- `parameter_ranges`;
- `optimization_objectives`;
- `physical_constraints`.

Review statuses:

- `pending`;
- `accepted`;
- `accepted_as_soft_only`;
- `rejected`;
- `needs_more_evidence`.

Semantic item display is normalized into `literature_semantic_candidate_view.v1` with subject, claim/predicate, value, applicability, confidence, geometry binding, and evidence. Missing values are JSON `null` and GUI `N/A`; non-standard `NaN` is not used.

Executable draft targets are restricted to ontology-supported grammar variant fields. Other information is additive metadata. `merge-prior` verifies semantic-package, base-prior and immutable-draft hashes; accepted-as-soft-only patches do not alter executable grammar.

### 7.3 Normal-conducting / superconducting isolation

The same corpus may hold different papers, but human decision state must remain isolated:

- one paper;
- one operating regime;
- one review session;
- one GUI page/URL.

`corpus-audit --paper-id` produces an isolated static audit. Combined reports are for integrity/statistics only. The SLS-2 geometry generator is fail-closed unless the package classification is:

```text
operating_regime = normal_conducting
cavity_family = elliptical
cell_count = single
geometry_scope = axisymmetric_single_cell_rf_vacuum
```

NC and SRF may share schemas, evidence navigation and UI components. They do not share material-loss, cryogenic, Q0, peak-field, multipacting, mechanical or cell-coupling priors by default.

### 7.4 GUI implementation

Current GUI layers:

1. Evidence: text/image evidence, page navigation, embedded verified source PDF page;
2. Semantic candidates: grouped normalized candidates, draft patch group, review status, Chinese note, structured Add;
3. Geometry projection:
   - Geometry parameters and generation validation;
   - Helper2 Features;
   - partial UDSG bindings.

Model comparison traces:

- baseline: immutable published-parameter candidate;
- previous: immediate parent candidate;
- current: current human-preview edit.

SLS-2 v0 parameters, all in mm:

| Parameter | Baseline | Meaning |
| --- | ---: | --- |
| `L` | 680.0 | total axial length |
| `l` | 188.671 | straight beam-pipe length per side |
| `r` | 50.0 | beam-pipe radius |
| `R` | 249.901 | equator radius for published candidate 1 |
| `a` | 125.232 | upper/equator ellipse axial semi-axis |
| `b` | 70.2322 | upper/equator ellipse radial semi-axis |

Reconstruction assumptions:

```text
h = L/2 - l
lower axial semi-axis = h - a
lower radial semi-axis = R - r - b
guards:
  L > 2l
  0 < a < h
  0 < b < R-r
  r > 0
```

The four 90-degree analytic ellipse arcs are sampled and fit using CadQuery `Workplane.splineApprox`, degree at most 5. The STEP curves are spline approximations, not exact conic entities. This assumption is provenance, not a paper claim.

Human edits set `origin=human_preview_edit`, clear source refs, set `published_value_claim=false`, retain the immutable paper baseline, and link to the parent by content hash.

Helper2 review state is stored separately from literature review state under `helper2_reviews.<projection_id>`.

### 7.5 Local review service

Security properties:

- binds only `127.0.0.1`;
- random token per launch;
- Host and Origin validation;
- no CORS;
- request-body limit;
- token header on API;
- no shell, CST, production prior merge, or campaign endpoint;
- atomic session replacement and append-only event log;
- optimistic revision conflict detection.

Session outputs are under a user-provided ignored directory and include:

- `review_session.v1.json`;
- `review_events.jsonl`;
- single-paper review HTML;
- `review_launch.json`;
- content-addressed geometry preview directories;
- generation report and review snapshots;
- Helper2 face mesh.

`review_launch.json` is launch/runtime metadata only; it is not freeze evidence and must not be used to record a PID or bearer token in an audit baseline.

Do not trust an old PID or token. Read the current launch record and verify the process before stopping it.

### 7.6 2026-08-18 frozen SLS-2 revision-149 audit baseline

Baseline ID: `sls2.r149.6593e02e`. The ignored local session `sls2_gui_isolated_final_20260712` is closed at revision 149 for paper `sls2` in the `normal_conducting` operating regime. It contains 30 review decisions in terminal states: 18 `accepted` and 12 `accepted_as_soft_only`. Both `parameter_ranges` decisions are explicitly soft-only. Helper2 records 8 accepted geometry faces, 9 confirmed Feature candidates and 13 accepted Feature-to-Geometry bindings.

The required raw SHA-256 values are: `review_session.v1.json` `6593E02EB1B968D7BF12BC243CCF7ABD86784C9E67A53E41D50B8CF8D951240D`; `review_events.jsonl` `1EFAED66D907914DFB1888481B5C54B6B748112592BED91475BC9A1A4909DACE`; `generation.core.json` `31051D936B71682FFC64DEA4C174DDE7B56F2E7EED31AA7D87F9E32D6E159FA1`; `helper2_face_mesh.json` `BBAC2B76CF1F7B12AC7065703E3D981DCC83A8518BCD936AD8E22FFC05B69E9B`; and `cavity.step` `97DD3F3F23C0E9A1DE671011D9F3B3E52A36936DFF1AB7BC7BB8BC2864B40767`. The event log contains 149 valid JSONL records with unique, continuous revisions 1–149.

The immutable source bindings were re-read as UTF-8 with the repository `canonical_sha256` helper: `literature_semantics.v0.json` raw `1191238875D1EB6FA145CE6291AB2EA536F56A6B09A2661D7140CC17D85C43B9`, canonical `sha256:e23fa66d7cb2f0515bfc9ae57a31ad085b1426b40ded699e688d015a1dda00e5`; `expert_prior.draft.v0.yaml` raw `E23A936ADBE3E0E9232AD0801FBA50934C893BC32990B181F588C6B7638F1069`, canonical `sha256:923113a16834127514820138b8d1d935dd8d2615ac42ad38c0484ff80579711f`. The session source binding also records payload `sha256:99f51410d436116f99fe4c165b1580aa9037ac91e1f66d7245fecaac85f0ee8e` and geometry projection canonical `sha256:f801015edb5bc605d85315f246087b2a1956684704428e6ca02dbccffd79ced6`.

Truth layers are deliberately separate and must be combined as `immutable generation.core + frozen revision-149 session + Helper2 overlay`: (1) `generation.core.json` is the immutable geometry-generation record and may still show `review_status=pending`; (2) the human acceptance state comes from the frozen `review_session.v1.json`; (3) Helper2 decisions come from the independent overlay under the session's matching projection ID; (4) interactive HTML is a review view/tokenized UI shell, not the sole or self-contained final audit record. Never select a “latest” review snapshot by file mtime. Pending and accepted snapshots may coexist and must not override the session state. Validation evidence remains layered as `geometry_generation`, `human_geometry_review`, `helper2_review`, `live_cst`, and `physical_acceptance`; this baseline does not collapse them into `validation_status=pass`.

This remains no-CST, local audit evidence. It did not edit the hash-bound `literature_semantics.v0` source package, did not change the draft-prior YAML, and did not run `merge-prior`. The draft YAML remains in its existing state. The baseline closes the current SLS-2 instance review; the separate Stage C record below is the evidence for the two-instance family contract.

The old session root is frozen and is no longer a writable continuation target. Every later review must create a new session root, even when the paper or source package is unchanged.

Post-audit GUI maintenance keeps the v1 schemas unchanged and narrows interaction behavior:

- Evidence and Semantic status changes persist only to the review session and no longer request a geometry preview;
- adding a manual structured semantic does not request a geometry preview;
- Geometry review decisions, explicit refresh and `L/l/r/R/a/b` parameter submission retain preview behavior;
- Semantic candidates are visibly separated into paper facts, paper-scoped objectives/constraints and repository mapping proposals;
- the UI states that `accepted` confirms a source claim only within its applicability, while `accepted_as_soft_only` preserves non-executable transfer limits.

Maintenance validation on 2026-08-18 used the branch `.venv`: targeted reviewer/server/app tests passed 30/30, and `pytest -q -m "not cst_required"` passed 697 tests with 11 skipped in 11.82s. No live CST validation was run.

### 7.7 2026-08-18 Stage C family profile v0 validation

Stage C is formally passed and has one canonical owner. Branch `codex/rf-cem-family-profile-v0` was validated, reviewed in PR #4, and merged into `workflow/rf-cem-literature-review` as merge commit `3867a9a8eae502359556a83bcad15b3a519e64de`; the original profile implementation commit is `619e3051077e8083488b570a7d1be29d80232f3d`. The canonical family is `nc_axisymmetric_single_cell_rf_vacuum` with independent identity fields `operating_regime=normal_conducting`, `symmetry=axisymmetric`, `cell_count=single`, and `geometry_scope=rf_vacuum`.

The two input manifests were consumed read-only and rechecked after proof generation:

- `sls2.r149.6593e02e`: `analysis_outputs/rf_cem_literature_pilot_20260710/frozen_baselines/sls2.r149.6593e02e/baseline_manifest.v0.json`, raw SHA-256 `19a15b0ea8248a85b698d9ace32e87ae190b6356b814fb3c1817d89987da0ffb`;
- `rf500.2c27faee.b1r3`: owner bundle `analysis_outputs/rf_cem_family_instance_sources/rf500.2c27faee.b1r3/instance_source_manifest.v0.json`, raw SHA-256 `4c64d1497bfcd98749fa2df7a742614820159e8ceaa665e6bec95d2ea4b916a5`.

The SLS-2 native payload has one unique source: `generation.core.json#/parameter_tuple/values`. Its six original names and values are `L=680.0`, `l=188.671`, `r=50.0`, `R=249.901`, `a=125.232`, and `b=70.2322`, all in `mm`, with scope `published_candidate`. The source artifact raw SHA-256 is `31051d936b71682ffc64dea4c174dde7b56f2e7eed31aa7d87f9e32d6e159fa1`; the source-native input and restored canonical SHA-256 are both `bdc9e7e251e628933aeeb82a5d3165578a33b52d6b62635fb36757d0986b2620`. The frozen revision-149 session/source binding remains payload SHA `99f51410d436116f99fe4c165b1580aa9037ac91e1f66d7245fecaac85f0ee8e`; it is provenance for the review payload, not a replacement for the native locator.

The RF-CEM source-native payload retains the original `parametric_geometry.v0` schema, model type, variant, `named_parameters` group (15 entries), and `derived_parameters` group (52 entries). Original units remain `MHz`, `mm`, and `ns`; source payload raw SHA-256 is `2c27faeecb5d36f9815fb5045d6c967749ddaaff3dec080a5ffa00599bb69a3f`; source-native input and restored canonical SHA-256 are both `d392a87f4f6cee5793747dede68c51e0738a80b0439c6c80d686e74f2e277557`. The path-free portable projection has independent canonical SHA-256 `9bd06e773a84861439e0851a2c2e30a24223c088b0932b274c45eeb2fe8d8461`; it is never used as native round-trip evidence. Unknown native fields, names, groups, values, units and scope preservation checks passed.

The generic schema is under `src/rf_cem/family_profile/schema.py` and uses `$defs/family_instance.v0`, `instances.minItems=1`, unconstrained native schema/group names and non-fixed parameter counts. The two adapters are `Sls2FamilyInstanceAdapter` and `Rf500FamilyInstanceAdapter`; source-backed native restoration re-reads and hash-verifies the bound frozen artifact. A profile-only validation remains structural/portable-only and reports `source_roundtrip=not_run` with `roundtrip_all_passed=False`; both manifests are required for a native pass. The eight validation layers remain separate for both instances. `live_cst` is `not_run` for SLS-2 and `not_linked` for RF-CEM; both `physical_acceptance` values remain `not_established`; the metric contract remains `excluded_pending_definition`, with no executable family objectives.

The previous ignored proof bundle `analysis_outputs/rf_cem_family_profiles/nc_axisymmetric_single_cell_rf_vacuum.75f6cba4/` is retained read-only and is superseded: audit found that it proved only portable self-consistency, not source-native RF500 restoration. It is not deleted. The corrected ignored proof bundle is `analysis_outputs/rf_cem_family_profiles/nc_axisymmetric_single_cell_rf_vacuum.00414d4f/`; its files and hashes are:

- `family_profile.v0.json`: raw `712d0afd7fb00517d6fb83679f93b7d55049731613ed8dbeb983d877ff217106`, canonical `00414d4f419af9de37269baacd96397562089578d9ab149386731fded0df41dc`;
- `family_profile_validation.v0.json`: raw `74e506792baa6458425226cac957b38018c422cd5e4a11fb3138687765276bd6`, canonical `e63dcdeb4be268e6b677a65ca74d98ccc1eff379f9a2a733afe61ba431070a12`;
- `adapter_roundtrip_report.v0.json`: raw `51f0dd658dae2fca254513d146913e3a954e1bf41b398b8a163ca7f90ea81759`, canonical `016a2128c7a4d1e4fe7215bd40fae8a317e9de3eb8b051473aa9c9db3d37754`;
- `source_binding_manifest.v0.json`: raw `76f10392498d5d41236a3aebcf66139671cd1b6cd3f29439d2fc7a053dd40fd6`, canonical `c3647b2e50ef661bbee1937e109e6e0900b9c856848658228127d8a9da625f18`.

Two builds from the same inputs produced identical profile objects, bytes and canonical SHA. The corrected report records the implementation commit, generated-at time, no-absolute-path equivalent argv, command exit status, both input manifest IDs/raw SHA, both source-native input/restored SHA, targeted `64 passed`, full `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m "not cst_required"` result `715 passed, 11 skipped`, and `cst=not_run`. With both frozen manifests, `python -m rf_cem.family_profile validate` reported structural validation passed, portable projection validation passed, `source_roundtrip=passed`, and `roundtrip_all_passed=True`; without manifests it reported `source_roundtrip=not_run` and `roundtrip_all_passed=False`. No CST, solver, campaign, recovery, merge-prior, push or PR was run/performed. `family_schema_established=true` and `adapter_established=true` are established for this corrected two-instance no-CST contract only; they do not imply metric equivalence, live-CST linkage, or physical acceptance. SLS-2 soft-only ranges remain soft-only.

The 2026-08-19 Stage C closeout added D0 source-binding hardening in implementation commit `4023eec5c13c72e00857cf4d033dc7f2b3d8ceb1`: source-backed verification now fails closed on manifest schema, complete artifact-list, adapter locator, native artifact raw hash, materialized source/native hashes, RF native envelope, and parameter/group scope cross-bindings; build provenance also preserves the repository-relative `analysis_outputs/...` suffix and records the test-result arguments. This is validation/provenance hardening only. The deterministic profile and four corrected proof artifacts above remain byte/hash unchanged, were generated by `619e3051077e8083488b570a7d1be29d80232f3d`, and were not regenerated or overwritten. Stage C still excludes RF performance metrics and executable objectives (`metric_contract_status=excluded_pending_definition`); no live CST result or physical acceptance is established. The active sequence is now the canonical R0B–R5 roadmap, not the superseded Stage D1 proposal.

### 7.8 R0B architecture and Workbench W0

R0B is closed and canonical. PR #5 merged implementation commit `f69bd8d58711c79ed73c2a90ed8476e79f616281` into `workflow/rf-cem-literature-review` as merge commit `c0b4574ee2dc87ee98938b282ec023aeebfa12d3`. R0B established dependency boundaries without pretending that the later phase contracts already existed: `semantic` cannot depend on representations, geometry kernels or CST; `representation` cannot depend on semantic families or CST; `compiler` is the composition boundary; `observation` is read-only and does not generate geometry. AST dependency tests enforce these boundaries. Representation/compiler and observation contracts remain deferred to R2 and R4.

Workbench W0 is implemented as a deletable derived read model in `src/rf_cem/workbench/`. Its SQLite registry is rebuilt atomically from explicitly supplied source files and stores repository-relative source identity plus raw SHA-256. It indexes the real `sls2.r149.6593e02e` and `rf500.2c27faee.b1r3` instances, separate validation layers, frozen review decisions, Helper2 semantics, current expert-prior grammar variants/control policies, legacy compile placeholders, capability coverage, and R0B–R5 gates. The browser binds only to `127.0.0.1`, requires a random token with Host/Origin validation, exposes fixed GET views/APIs, opens SQLite read-only, and offers no shell, arbitrary file browser, CST control or mutation endpoint.

The ignored local rebuild target is `analysis_outputs/rf_cem_workbench/w0.sqlite`; it is disposable and must never become an engineering source of truth or a tracked artifact. Source status must be `fresh` before its content is used; a changed or missing source is shown as `stale` or `missing` until an explicit rebuild. The canonical architecture/gate source is `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`. R1 began only after the R0B hard gate, closeout validation, PR checks, and canonical merge passed.

Two consecutive real-source rebuilds produced the same input-set SHA-256 `a84aa1b70a5757e752622599cf50d52ab22de0ea24d8aa4edd9cbb29b9a12929`, with 7 fresh sources, 131 entities and 21 relations. The canonical portable snapshot SHA-256 was `9e389d9d807d116123723de1f8755dbf88b7e09eeef5724a7fb0acef15964165`. This is local no-CST verification evidence, not a tracked proof bundle or physical validation.

### 7.9 2026-08-20 R1 RF boundary semantic core and Workbench W1

R1 implements a representation-independent semantic topology contract in `src/rf_cem/semantic/`. The public contracts are `family_grammar.v0`, `instance_boundary_graph.v0`, `semantic_region_ontology.v0`, `semantic_landmark_ontology.v0`, `semantic_motif.v0`, the `boundary_interface` object, and `instance_boundary_graph_diff.v0`. The package imports neither CadQuery/OCP nor CST, does not compile geometry, and records `parameter_contract=not_applicable_semantic_topology_only`; the diff records `not_applicable_no_common_geometry_parameter_vector`.

The real graphs use the same ordered nine-region backbone: left beam pipe, iris, gap shaping and outer wall; center equator; right outer wall, gap shaping, iris and beam pipe. `sls2.r149.6593e02e` has 9 regions and `nose_presence=absent_reviewed_topology`. Its absence assertion is jointly bound to the frozen six-segment generation profile, accepted geometry projection revision 72, and complete Helper2 candidate review revision 147, whose nine confirmed candidate types contain no nose. `rf500.2c27faee.b1r3` has 11 regions and activates `motif.nose_pair.v0`: a reviewed `NoseCone` binding supports one left and one right `NoseRegion` inserted at the two iris/gap-shaping interfaces. Its outer-wall nodes bind the reviewed `ConductingWall` source feature. Every region and landmark has a stable instance-namespaced ID, source evidence and terminal review state; every adjacent pair has exactly one oriented interface and junction landmark.

One grammar accepts both graphs with exact type cardinalities, exact backbone/motif adjacency coverage and paired optional nose count `{0, 2}`. Invalid adjacency, cardinality, motif placement, interface order, endpoint/aperture/symmetry rules, source hash, review revision and unexpected SLS-2 nose candidates fail closed. The graph diff reports 9 common semantic regions, 2 RF500-only nose regions and 6 rewired adjacencies; it does not interpret the topology difference as missing geometry parameters.

The current ignored proof is `analysis_outputs/rf_cem_semantic_core/r1_semantic_core.28e8d6fa9efa221f/`, content SHA-256 `28e8d6fa9efa221f5fd1e0817bded2e1855066869d0e84c3910529ee2ca248fe`. It is content-addressed, refuses an existing target, contains no timestamps or absolute paths, and can be recreated without CST. Two fresh real-source output roots produced the same bundle ID and six byte-identical files. Raw artifact hashes are:

- `family_grammar.v0.json`: `c877da7d0bfed75fc00af917db44fa136bb78e8d0fcb4e637bfb41f416ea9525`;
- SLS-2 graph: `5183ad5cc40516689d2c17a27d34a0c89930dc196b4ce4bca4f7c9ab686c8ce2`;
- RF500 graph: `c04b43090bf5fe385e32843eaa25a23d4e648c76e8b3a2533c4ab1b9fef8d739`;
- `instance_graph_diff.v0.json`: `31a85d06368ce24eb56fe5bd834a2deb0954aaa01624b55d4cd1c3128542a20d`;
- `semantic_validation.v0.json`: `cc2c96fe7c31b6482af32224a256400fa08835c064d8cddca5dab1d247733f8d`;
- `source_binding_manifest.v0.json`: `ef25c10543f78b95d755dfa3a99a0f3777ee411764e002657614075254b1a8a9`.

Workbench indexer `r1.w1.v0` adds a fixed `/semantic-graphs` view and indexes grammar, both ontologies, motif, two instance graphs, 20 regions, 24 landmarks, 18 interfaces and the graph diff. Two consecutive real rebuilds produced input-set SHA-256 `6bb5624f5f6c081e69e0ecd589c443199bc52c0c82ef2beadc37f0f5449fe351`, 11 fresh sources, 214 entities and 154 relations. The portable registry snapshot SHA-256 is `2dba89cc8cb0df87982f56ff50ee47426934d64e725bd69073ce419781627128`. W1 remains a derived read model, not source truth or physical evidence.

## 8. STEP Feature Assistant state

Primary CLI supports:

- `fallback` STEP text diagnostics;
- `cadquery` geometry-kernel facts;
- `auto` with recorded fallback;
- model profiles `bare_cavity_500mhz`, `normal_conducting_500mhz` and `xband_2.3cell_gun`;
- geometry manifest, face inventory, adjacency, FeatureGraph draft;
- stable generated face IDs and groups;
- offline Plotly reviewer;
- reviewed-label validation and resolved FeatureGraph;
- geometry graph, feature candidates and partial UDSG layer;
- manual groups, face-ref editing and binding review;
- calibration proposals from reviewed projects;
- advisory one-vs-rest logistic-regression classifier.

Production authority is human-reviewed labels. Rule calibration and ML suggestions never mutate production rules automatically.

CadQuery/OCP is executed in an isolated worker for risky geometry operations. On this Windows/Python environment, a process-exit access violation can occur even after useful results were written; callers must distinguish worker result status from interpreter teardown status.

## 9. CST history extractor state

Inputs:

- exported `.bas` or macro/history text;
- `.cst` project with adjacent unpacked `Model/3D/ModelHistory.json`;
- optional CST library path to open a project and trigger unpacking.

Outputs:

- raw history and source metadata;
- classified command inventory;
- recipe manifest;
- geometry summary;
- unknown/unclassified command list;
- human-readable generated report.

Direct `ModelHistory.json` parsing is an observed internal project format, not an official Python API. Unknown operations are preserved. `get_tree_items` returns navigation-tree paths and cannot replace history-body extraction.

## 10. Workflow-specific status

### 10.1 WF1

Owner: `workflow/1-rfgun-sao`. Root compatibility entry exists only on that branch.

Capabilities include default single-pass SAO, opt-in two-pass CST runtime, calibration, metric roles (`optimize`, `threshold`, `report_only`, `gate`), gates, staged search, adaptive bounds, checkpoint, optional diagnostic JSONL, evaluation DB, warm start/reuse, and retry.

Do not confuse placeholder two-pass runtime with live results. Local CST paths belong in ignored local config.

### 10.2 WF2

Owner: `workflow/2-rfgun-hom-antenna`. Canonical config is package-local.

Capabilities include dual-project orchestration, per-attempt template copies, heartbeat, phase snapshot, recovery, warmup total bundle, adaptive gate, direct and reconstructed wake objectives, fixed known modes, and optional bounded fit of unknown longitudinal-mode frequency.

Frequency fitting is disabled by default. It must never affect known modes or transverse modes, and overlapping frequency windows fail closed. A single PSO inverse result is non-unique evidence.

### 10.3 WF3

Owner: `workflow/3-rfgun-recovery-tolerance`.

Includes recovery optimisation plus tolerance simulation, single-database no-CST analysis, and cross-level campaign analysis. Resume input must be schema-compatible; local datasets and reports are not source files.

### 10.4 WF4

Owner: `workflow/4-rfgun-hom-eigenmode`.

Supports planning, resume preview, offline-only reprocessing and result audit. Historical state recorded 60 targets, 39 clusters, 116 windows and 323 eigenmode candidates, with severe ambiguity and mode-enumeration censoring. Those numbers are historical campaign evidence, not regenerated by this branch.

Template revision adoption is explicit and provenance-bound. Dedicated `mode=new` processes use targeted cleanup; failure to verify PID exit stops the campaign as `cleanup_incomplete`. No machine-wide process sweep is allowed.

## 11. Known risks and required controls

| Risk | Required control |
| --- | --- |
| Geometry visually plausible but RF-invalid | Separate BRep/profile checks from live solver and mode review. |
| STEP face IDs change | Use generated stable geometry IDs, facts and human review; never bind by raw kernel ID alone. |
| Natural language becomes executable | Ontology whitelist, pending draft, hashes and human patch review. |
| NC/SRF semantic contamination | Paper/regime/session isolation and fail-closed classification. |
| Single-paper numeric overfitting | Soft-only default and independent-paper validation. |
| Objective rewards frequency too strongly | Window objective with boundary tests and explicit normalization. |
| Candidate/project numbering mismatch | Candidate-specific package/project paths and record cross-check. |
| Campaign output overwrite | Default collision refusal and explicit resume contract. |
| Result template absent from history | Register `Model.rpp` plus `.r0d`; verify result-tree paths. |
| Misleading `HEX mesh is invalid` | Do not switch mesh blindly; inspect template registration, material, solver state and actual result readback. |
| Unsaved CST result cache | Save project, then invalidate/reopen `ResultReader` cache. |
| CST process cleanup affects other work | Target owned PID only; global sweep needs explicit authority. |
| Windows Unicode/encoding corruption | UTF-8 reads/writes; use patch-based Chinese source edits. |
| PowerShell case-insensitive JSON keys | Do not inspect `L` and `l` tuples with Windows PowerShell 5.1 `ConvertFrom-Json`; use Python or GUI. |

## 12. Verification state

Recommended interpreter: the active clone/worktree's `.venv\Scripts\python.exe`, resolved from the repository root rather than another workstation directory.

Current-branch full no-CST command:

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
& $Python -m pytest -q -m 'not cst_required'
```

R0B closeout verification on 2026-08-19:

```text
targeted Stage C + review GUI + architecture + Workbench: 52 passed in 1.45s
full branch-local no-CST: 738 passed, 11 skipped in 10.64s
```

These results include the Stage C profile, literature review GUI, architecture dependency guards, deterministic registry rebuild, source-staleness audit, and loopback server security contracts. They do not include live CST. The closeout verification also includes:

- full current-branch no-CST suite;
- `compileall` for source and workflows;
- `git diff --check`;
- tracked-Markdown inventory and link/path scan;
- CLI `--help` smoke for maintained entries.

R1 closeout verification on 2026-08-20:

```text
targeted semantic core + Workbench W0/W1 + architecture: 19 passed in 1.98s
explicit no-CST marker set: 192 passed, 11 skipped, 553 deselected in 10.23s
full default branch suite (CST-required tests skipped): 745 passed, 11 skipped in 12.01s
authenticated loopback browser QA: Semantic Graphs / W1 and Roadmap / Gates rendered correctly; no console warnings/errors
live CST: not run
```

The R1 checks cover typed/schema round trips, both real topologies, reviewed nose absence/presence, exact grammar acceptance, fail-closed invalid adjacency/cardinality/interface/source-review cases, deterministic/refuse-overwrite proof bundles, semantic CLI, W1 deterministic indexing and fixed-route rendering. They establish semantic topology only; no `RegionGeometry`, Compiler v0, family induction, RF metric equivalence, live solver result or physical acceptance is claimed.

Historical branch-specific pass counts from 2026-07-10 are archived and must not be copied as current evidence without rerunning those worktrees.

## 13. Current priorities

Priority order:

1. Close and merge R1 from `codex/rf-cem-r1-semantic-core` into `workflow/rf-cem-literature-review`; preserve its proof bundle and W1 registry as ignored, rebuildable no-CST artifacts.
2. R2: implement family-independent boundary representations plus Compiler v0 at the declared composition boundary, without moving family semantics into representation classes.
3. R3: implement evidence-gated family induction/extension without silent migration of legacy artifacts.
4. R4: implement representation-independent observations and engineering constraints with explicit units and validation states.
5. R5: define RF result/mode/field contracts no-CST first. Any live-CST validation remains separately blocked on explicit user authorization.
6. Keep the entire R0B–R5 line on `workflow/rf-cem-literature-review`; do not merge the concrete workflow into `workflow/rf-cem-500mhz` or `main`.
7. Promote only demonstrated cross-workflow contracts to `main`, using a separate focused change and compatibility evidence.

## 14. Backup and recovery references

Local backup paths are workstation-specific and must be configured as `<BACKUP_ROOT>` rather than copied literally. Relevant local evidence names are:

```text
<BACKUP_ROOT>\rf-cem-literature-review-pre-handoff-20260713-144716.bundle
SHA-256: F77586AB38E70E2B293AEABACCFBB48E9AE3EB4F01BFCE10C38C287733EA0AC6

<BACKUP_ROOT>\rf_cem_docs_consolidation_20260712_224614\repository_all_refs.bundle
<BACKUP_ROOT>\cst_ver3_strict_reorg_backup_20260710T121115\
```

Important remote backup refs include:

- `backup/rf-cem-literature-review-pre-handoff-20260713-144716`;
- `backup/rf-cem-literature-review-pre-canonical-rebase-20260713-145915`;
- `backup/pre-strict-reorg-20260710-main`;
- `backup/pre-strict-reorg-20260710-homwork`;
- `backup/pre-strict-reorg-20260710-cst-step`;
- `backup/pre-strict-reorg-20260710-wf2-closure`;
- `backup/pre-clean-wf2-closure-20260710`;
- `backup/pre-strict-reorg-20260710-wf2-worktree`;
- `backup/pre-strict-reorg-20260710-stale-workflows`;
- `backup/post-backup-cst-step-assistant-changes-20260710`.

Never restore over a live worktree. Clone a bundle or add a new recovery worktree, inspect it, and selectively integrate.

## 15. State-update protocol

Update this file when any of these changes:

- canonical branch/worktree ownership;
- canonical branch ownership or cross-branch integration state;
- shared-core contract;
- RF-CEM geometry schema, parameter set, solver/material/result path;
- literature schema, review status, isolation or merge gate;
- entry point ownership;
- latest verified no-CST or live-CST evidence;
- campaign objective/resume state;
- high-priority blockers;
- backup location required for recovery.

Do not append dated mini-reports. Replace obsolete state and retain only concise provenance. Put operational commands in `FUNCTIONS_AND_ENTRYPOINTS.md` and restart procedures in `AGENT_CONTEXT_RECOVERY.md`.
