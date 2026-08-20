# Agent Project Status Context

Status timestamp: 2026-08-20 Asia/Shanghai

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
| `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md` | RF-CEM architecture decisions, Workbench W0–W4 contract, and R0B–R5 gates. |
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
| RF-CEM literature review/GUI and R0B–R5 architecture | `workflow/rf-cem-literature-review` | canonical through R4; Stage C/R0B/R1/R2/R3/R4 integrated by PRs #4/#5/#6/#7/#8/#9; R5 readiness active; nominal Stage A authorized but blocked before connection by CST license error `-8,523` | R4 merge commit `8c6bd0be38e8b2bbf5d72c1254413ee6b552defe`; active R5 branch `codex/rf-cem-r5-rf-result-field` |

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
| `src/rf_cem/semantic/` | R1 representation-independent grammar/instance-graph core plus R3 reviewed graph alignment, extension proposal, explicit review/patch and held-out validation; imports neither representations nor CST. |
| `src/rf_cem/semantic/induction/` | R3 `graph_alignment.v0`, `family_extension_proposal.v0`, manual review, hash-bound grammar patch/application, real LEReC blind adapter, deterministic proof bundle and CLI. |
| `src/rf_cem/representation/` | R2 family-independent Line/CircularArc/EllipseArc/Spline-NURBS/Composite boundary contracts, `GeometryPatch` and `RegionGeometry`; imports neither semantic family types nor CST. |
| `src/rf_cem/compiler/` | R2 sole semantic/representation composition boundary, real-source adapters, Compiler v0, `compile_record.v0`, deterministic no-CST proof bundles and CLI. |
| `src/rf_cem/observation/` | R4 read-only exact/shape/scalar observation contracts, 21 unit-bound descriptors, non-mutating engineering constraints, deterministic proof bundle and CLI; imports no CST. |
| `src/rf_cem/physics/` | R5 strict RF case/result provenance, mode identity/fingerprint, unit-bound scalar metric, external field-artifact, mesh-convergence and default-deny comparability contracts plus no-CST readiness proof/CLI; imports no CST. |
| `src/rf_cem/workbench/` | W0–W5 no-CST derived SQLite registry and authenticated loopback read-only catalog, including semantic, compiler, induction, observation/constraint and RF result/mode/field readiness views. |
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
| RF boundary representation/compiler R2 | FM1-2 | AC3 | One compiler entry produces owner-safe region/patch geometry and deterministic valid STEP/B-Rep for both real topologies with source-native/baseline evidence. |
| RF-CEM Workbench W2 | FM1 | AC3 | Hash-verifies two compile records and output artifacts; exposes ownership, representation, landmark, continuity, validation, baseline and warning traces. |
| RF family induction/extension R3 | FM1-2 | AC3 | Aligns reviewed SLS-2/RF500 graphs without parameter names, proposes paired optional nose structure, requires accepted manual review for an explicit grammar patch and validates held-out real LEReC 704 MHz. |
| RF-CEM Workbench W3 | FM1 | AC3 | Rechecks the complete W2 chain and R3 bundle; exposes alignment, common backbone, residuals, proposal, review, grammar diff and held-out validation. |
| RF boundary observation/constraint R4 | FM1-2 | AC3 | Separates hash-bound exact geometry, normalized semantic shape and 21 versioned scalar descriptors; evaluates six reviewed, unit-aware non-mutating constraint demonstrations on both real compiled instances. |
| RF-CEM Workbench W4 | FM1 | AC3 | Rechecks the complete W1–W3 chain and R4 bundle; exposes exact/shape/scalar layers, descriptor provenance, constraints, evaluations and three located demonstration violations. |
| RF result/mode/field contract R5 readiness | FM1 | AC3 | Defines strict physics-case/provenance, mode identity/fingerprint, nine metric, external field, convergence and comparability contracts; three RF500 mesh cases remain planned and null until authorized live-CST evidence exists. |
| RF-CEM Workbench W5 | FM1 | AC3 | Rechecks the complete W1–W4 chain and R5 readiness bundle; exposes the authorization hard gate, per-instance linkage, cases, modes, metrics, external fields, convergence and comparability without promoting historical values. |
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

R0B is closed and canonical. PR #5 merged implementation commit `f69bd8d58711c79ed73c2a90ed8476e79f616281` into `workflow/rf-cem-literature-review` as merge commit `c0b4574ee2dc87ee98938b282ec023aeebfa12d3`. R0B established dependency boundaries without pretending that the later phase contracts already existed: `semantic` cannot depend on representations, geometry kernels or CST; `representation` cannot depend on semantic families or CST; `compiler` is the composition boundary; `observation` is read-only and does not generate geometry. AST dependency tests enforce these boundaries. The representation/compiler boundary was filled by R2 and the read-only observation/constraint boundary by R4.

Workbench W0 is implemented as a deletable derived read model in `src/rf_cem/workbench/`. Its SQLite registry is rebuilt atomically from explicitly supplied source files and stores repository-relative source identity plus raw SHA-256. It indexes the real `sls2.r149.6593e02e` and `rf500.2c27faee.b1r3` instances, separate validation layers, frozen review decisions, Helper2 semantics, current expert-prior grammar variants/control policies, legacy compile placeholders, capability coverage, and R0B–R5 gates. The browser binds only to `127.0.0.1`, requires a random token with Host/Origin validation, exposes fixed GET views/APIs, opens SQLite read-only, and offers no shell, arbitrary file browser, CST control or mutation endpoint.

The ignored local rebuild target is `analysis_outputs/rf_cem_workbench/w0.sqlite`; it is disposable and must never become an engineering source of truth or a tracked artifact. Source status must be `fresh` before its content is used; a changed or missing source is shown as `stale` or `missing` until an explicit rebuild. The canonical architecture/gate source is `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`. R1 began only after the R0B hard gate, closeout validation, PR checks, and canonical merge passed.

Two consecutive real-source rebuilds produced the same input-set SHA-256 `a84aa1b70a5757e752622599cf50d52ab22de0ea24d8aa4edd9cbb29b9a12929`, with 7 fresh sources, 131 entities and 21 relations. The canonical portable snapshot SHA-256 was `9e389d9d807d116123723de1f8755dbf88b7e09eeef5724a7fb0acef15964165`. This is local no-CST verification evidence, not a tracked proof bundle or physical validation.

### 7.9 2026-08-20 R1 RF boundary semantic core and Workbench W1

R1 is closed and canonical: PR #6 merged implementation commit `65d8d52350b9e536f3b2a0d30a0b18f24d447fdb` into `workflow/rf-cem-literature-review` as merge commit `5ae1ba07b841d6adf6e180ec1eedfd073657987b`. R1 implements a representation-independent semantic topology contract in `src/rf_cem/semantic/`. The public contracts are `family_grammar.v0`, `instance_boundary_graph.v0`, `semantic_region_ontology.v0`, `semantic_landmark_ontology.v0`, `semantic_motif.v0`, the `boundary_interface` object, and `instance_boundary_graph_diff.v0`. The package imports neither CadQuery/OCP nor CST, does not compile geometry, and records `parameter_contract=not_applicable_semantic_topology_only`; the diff records `not_applicable_no_common_geometry_parameter_vector`.

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

### 7.10 2026-08-20 R2 boundary representation/compiler and Workbench W2

R2 is closed and canonical. PR #7 merged implementation commit `f6df4c5589cf3c952c177e02dc053c6b7970b4d5` into `workflow/rf-cem-literature-review` as merge commit `e81ad20942258380cccb93d17cfdf0ca7e2d0e21`. `src/rf_cem/representation/` owns strict finite/versioned family-independent contracts for `LineRepresentation`, `CircularArcRepresentation`, `EllipseArcRepresentation`, `SplineNurbsRepresentation`, `CompositeRegionRepresentation`, `GeometryPatch` and `RegionGeometry`. The package imports neither `rf_cem.semantic` nor CST. One `RegionGeometry` owns 1..N ordered primitive patches; every patch has exactly one opaque region owner, deterministic global/local order and left-to-right orientation.

`src/rf_cem/compiler/ProfileCompiler.compile` is the sole composition entry for both real cases. Its strict inputs bind the Stage C profile, R1 grammar/graph, source-native payload/artifacts, semantic-region-to-representation assignments and declared baseline tolerances. The adapters reconstruct the six-segment SLS-2 analytic line/ellipse source and the seven-segment RF500 line/arc/spline source without changing their native schemas. Parameter-domain splitting maps these source curves to the 9-region SLS-2 graph and 11-region RF500 graph without allowing a patch to cross a semantic boundary. Landmark coordinates bind endpoints, region interfaces, internal patch joins and symmetry; continuity records C0, G1 and G2 diagnostics. Partitions of one native geometric segment require G2; other semantic-region interfaces require C0. Diagnostic G1/G2 failures above the required level remain explicit warnings and do not become false required-pass claims.

The ignored immutable proof is `analysis_outputs/rf_cem_boundary_compiler/r2_boundary_compiler.aa66a3e90125437b/`, input SHA-256 `aa66a3e90125437b32ef900feb296f4512ee4a199b372474cb4c24fb7740813c`. Two fresh output roots produced the same bundle ID and seven byte-identical files after normalizing only the non-geometric STEP `FILE_NAME` timestamp to the 1970 epoch. The two compile identities are:

- SLS-2: `sls2.r149.6593e02e.compile.ebe8e2827948ff96`, content SHA-256 `ebe8e2827948ff96a2f9ef8c8e985f20104ace16f2ef51870bd2534517df3fc8`, 9 regions, 10 patches, raw record SHA-256 `3af2b69da96076413e2d0c304c4a6931b665f286a8762b3dc7e40215fd5a3dbc`;
- RF500: `rf500.2c27faee.b1r3.compile.40891d70493951aa`, content SHA-256 `40891d70493951aa3a0e4df4d5f55cf7ee7564ba6fa9fe0552e040fbe6460cfc`, 11 regions, 12 patches, raw record SHA-256 `b929063ff7fd0bcf1761188f96db2be788aaca1972b87ecabb9c54ee01c3edae`.

Both source-profile maximum deviations are `2.842170943040401e-14 mm` against `1e-6 mm`. The materialized SLS-2 frozen STEP comparison passes: maximum bbox error is about `3.37e-8 mm`, volume relative error `1.9467e-5` and surface-area relative error `3.3299e-5`, against tolerances `0.3 mm`, `0.01` and `0.01`. RF500's accepted STEP is hash-bound as `766365b6b78f3d0a6929f2500cfb49fc306e54be048a638bc813e9c8aeb9e3cd` but not materialized locally; its accepted R2 basis is therefore source-native curve equivalence plus a newly valid B-Rep/STEP and an explicit unmaterialized-baseline warning, not a claim that legacy STEP geometry metrics were compared. The generated STEP hashes are SLS-2 `fe4898665074741cc3eda81fe5436f6387824e4449d757588e82bfd68f7abecc` and RF500 `dac9819443816cf67b7977a5504021df5cbd33e3f897beb761feafae784ac515`.

Workbench indexer `r2.w2.v0` requires the complete W1 proof and exactly two canonical `compile_record.v0` sources. It rechecks contract canonical hashes, raw source hashes, instance/region order, landmark coverage, representation reuse, output paths/sizes/hashes and no-CST/physical-status exclusions before indexing. The fixed `/compile-records` page shows the two compiler cards, 20 region→representation→patch traces, 24 landmark bindings, 20 continuity checks, B-Rep/STEP validation, baseline comparisons/warnings, 22 patch ownership records and four hash-verified output artifacts. Two consecutive full real-source rebuilds produced 17 fresh sources, 372 entities and 534 relations; final input-set SHA-256 is `91f6fdc82ba77f73f8b452b3a0499ad56178f23719f0848978af4a743b591a74` and portable snapshot SHA-256 is `d9139bfe7d3a4e2a536545addc45999a61f5fa337dd23733a3c6379a28b271fc`. Browser QA found no replacement characters, horizontal page overflow or console errors and also rechecked the W1 topology page.

All R2 geometry validation is no-CST via the existing isolated CadQuery/OCP worker. Length is `mm`, tangent angle `deg`, curvature `1/mm`, area `mm^2` and volume `mm^3`. Every record retains `live_cst_status=not_run` and `physical_acceptance_status=not_established`. R2 does not define frequency/Q/R/Q/field/power/wake objectives, run a solver, establish RF equivalence, perform family induction or launch optimisation.

### 7.11 2026-08-20 R3 family induction/extension and Workbench W3

R3 is closed and canonical. PR #8 merged it into `workflow/rf-cem-literature-review` as canonical merge `585d549c7a5dac0304852a0150f0c4114fd5b6e9`, based exactly on the R2 merge `e81ad20942258380cccb93d17cfdf0ca7e2d0e21`. `src/rf_cem/semantic/induction/` adds strict finite/versioned contracts for `graph_alignment.v0`, `family_extension_proposal.v0`, `family_extension_review.v0`, `family_grammar_patch.v0`, `family_grammar_patch_application.v0` and `family_induction_blind_validation.v0`. It remains inside the semantic dependency boundary: it imports neither `rf_cem.representation`, geometry kernels nor CST.

`rf_cem_family_induction.v0` consumes only reviewed `instance_boundary_graph.v0` contracts. Its deterministic progressive-LCS alignment reads each ordered `(side, region_type)` token and the graph/source hashes needed for audit; it does not read roles, native feature/parameter names or geometry vectors. The canonical SLS-2/RF500 alignment has nine common backbone slots and two RF500-only `NoseRegion` residuals. Those paired, mirrored residuals yield one `optional_motif` proposal for `motif.nose_pair.v0`, counts `{0, 2}`, explicit left/right insertion adjacencies, graph JSON locators, source evidence, algorithm version, limitations and confidence `0.95`. That confidence is deterministic evidence completeness, not a statistical probability. Unpaired residuals follow the separately tested `alternative_topology` path.

Every new proposal persists as `review_status=pending` and `grammar_mutation_status=not_applied`. Rejected and `needs_evidence` decisions return the exact original grammar bytes, no patch and no diff. The canonical closeout uses explicit accepted manual review revision 1 by `codex.r3-explicit-review`; only that hash-bound review authorizes the patch. Because the R1 grammar already contains the nose motif, the patch records `confirm_optional_motif`, updates the grammar identity to `nc_axisymmetric_single_cell_rf_vacuum.family_grammar.r3.v0`, appends induction evidence, replaces the review binding and updates the induction exclusions. Both canonical training graphs revalidate after application. No pending proposal mutates the grammar implicitly.

The held-out real case is the BNL LEReC 704 MHz normal-conducting single-cell cavity from the primary IPAC2015 design paper and 2018 design/test preprint. Their ignored source PDFs have raw SHA-256 `d806257972ae33208f5244ed31e1329064d120b82491bc4cb9a9e6afb544ba82` and `01b6a72aedf32783568cec6e0ab567cd6870d7f4ec7a2e98558d24b790baffab`. The adapter is deliberately limited to the axisymmetric main-cell RF-vacuum wall shown by the cited cross-sections; non-axisymmetric FPC, tuner, pickup, pump and flange details are excluded. The reviewed blind graph has the nine-slot backbone plus paired left/right nose regions. It is constructed only after proposal review/patch application, is absent from the alignment training IDs and validates as `known_optional_motif_present`. This is post-induction classification of reviewed literature geometry, not raw-pixel/STEP unsupervised semantic discovery.

The canonical ignored immutable proof is `analysis_outputs/rf_cem_family_induction/r3_family_induction.2f6c02557798e606/`, input SHA-256 `2f6c02557798e6062e961d6dea3b4220e4d4076310579754567d570f6ae7c4f0`. Its key identities are alignment `nc_axisymmetric_single_cell_rf_vacuum.alignment.a337c02c967c3ca2`, proposal `nc_axisymmetric_single_cell_rf_vacuum.proposal.d251b136d1f083ee`, review `nc_axisymmetric_single_cell_rf_vacuum.proposal.d251b136d1f083ee.review.89d6484b1e098d35`, patch `nc_axisymmetric_single_cell_rf_vacuum.family_grammar.v0.patch.41648ea3abc8d689`, application `nc_axisymmetric_single_cell_rf_vacuum.proposal.d251b136d1f083ee.application.8d3102fd549c2767` and blind validation `lerec704.wepwi061.arxiv1804-02007.blind_validation.7555433415beb669`. Two fresh test builds from the same sources/review are byte-identical; the loader rechecks all eight artifact sizes/hashes and their cross-contract identities. Older R3 proof directories are preserved and not overwritten.

Workbench indexer `r3.w3.v0` adds `--family-induction-bundle` and requires the complete W1 and W2 inputs before W3 can be indexed. It independently rechecks the two training graph bindings, base/patched grammar hashes, proposal/alignment binding, accepted manual review, applied patch, both training revalidations, blind separation/classification, manifest inventory, two primary PDFs and the unchanged `src/rf_cem/representation/core.py` hash sentinel. The full source set yields 29 fresh sources, 418 entities and 571 relations; input-set SHA-256 is `97fab22424ed421108f99b81ca6d629a52d7e6e8d2d368589ee1cdddb95ded18` and canonical portable snapshot SHA-256 is `f51eadc28ad97d1b2207e15a96ccedd5b42bcec280a43667587a573abcc6c66e`. The fixed `/family-induction` page exposes the alignment summary, common backbone, residual evidence, pending/non-mutating proposal, accepted review, grammar before/after diff and held-out LEReC result. Authenticated in-app browser QA confirmed every section is present exactly once and the page reports parameter names unread, blind training use false, representation not imported/modified and no live CST.

R3 establishes reviewed semantic family induction only. It adds no geometry generation, observation/constraint contract, frequency/Q/R/Q/field/power/wake result, CST execution, physical acceptance or optimization search. Geometry lengths in the cited LEReC evidence remain source units; no new RF metric or derived engineering objective is inferred from them.

### 7.12 2026-08-20 R4 boundary observation/engineering constraints and Workbench W4

R4 is closed and canonical. PR #9 merged the R4 line into `workflow/rf-cem-literature-review` at `8c6bd0be38e8b2bbf5d72c1254413ee6b552defe`; it was created exactly from R3 canonical merge `585d549c7a5dac0304852a0150f0c4114fd5b6e9`. `src/rf_cem/observation/` adds strict finite schemas for `exact_geometry_reference.v0`, `semantic_shape_observation.v0`, `scalar_descriptor_registry.v0`, `observation_bundle.v0`, `engineering_constraint.v0` and `constraint_evaluation.v0`. The package imports no CST and cannot generate or mutate geometry.

Each exact reference rechecks its R2 compile record plus all declared compiled profile/STEP identities. The shape observer reads only generic `RegionGeometry` operations and the reviewed R1 semantic graph, never source-native parameter or feature names. It emits 65 arc-length-normalized samples per semantic region with `z/r` in `mm`, tangent/normal, signed curvature in `1/mm`, extrema, convexity, monotonic intervals and compiled landmark coordinates. Exact geometry, sampled shape and scalar descriptors retain independent content identities; the shape layer does not replace the exact geometry.

Registry `scalar_descriptor_registry.da3b02daef2b8d88` defines 21 descriptors with value kind, unit, definition, algorithm version, absolute equivalence tolerance, applicability and provenance. The eight global definitions cover total length, maximum radius, minimum aperture, volume, surface area, semantic-region count, nose presence and minimum curvature radius. The thirteen regional definitions cover axial extent, arc length, radius range, minimum curvature radius, start/end tangent components and curvature, nose-tip radius and equator-crest radius. Allowed units are `mm`, `mm^2`, `mm^3`, `1/mm`, dimensionless `1`, `count` and `bool`; unknown units, non-finite values, invalid landmarks and scope/type mismatches fail closed. Tests prove descriptor equivalence within each definition's tolerance for the same geometry expressed through a different representation seam and a different patch segmentation.

The six reviewed contract demonstrations exercise `hard`, `soft`, `advisory` and `diagnostic` behavior for total length, maximum radius, minimum aperture, minimum curvature radius, nose presence and regional equator radius. Every constraint binds its registry/descriptor version, unit, scope, operator, tolerance, author, rationale and provenance. The evaluator is immutable and stores measured values, deviation and semantic/sample locations; `geometry_mutation_authority=none`. Across both instances there are 12 evaluations and three intentionally visible demonstration violations: RF500 minimum aperture, SLS-2 total length and SLS-2 nose presence. These thresholds demonstrate the contract only and are not manufacturing rules or physical acceptance.

The canonical ignored immutable proof is `analysis_outputs/rf_cem_observation_contract/r4_observation_contract.d06695921d941eee/`, input SHA-256 `d06695921d941eee06972ad11de7d2b8f5ad1cddb7d932c795385876db869b59`. It contains 25 declared artifacts bound to 11 repository sources. RF500 has exact identity `rf500.2c27faee.b1r3.exact_geometry.58105c1e869d0cde`, shape identity `rf500.2c27faee.b1r3.shape_observation.5e9d74d21db4ba5d`, 11 regions and 132 descriptor values; SLS-2 has exact identity `sls2.r149.6593e02e.exact_geometry.7dad12661b126be5`, shape identity `sls2.r149.6593e02e.shape_observation.4625ea7c0317a83d`, 9 regions and 108 values. The strict loader re-hashes every source/artifact, recomputes the input preimage and rechecks all cross-contract identities. Build refuses overwrite of an existing content-addressed target; older proofs must be preserved.

Workbench indexer `r4.w4.v0` adds `--observation-contract-bundle` and refuses W4 without the complete W1/W2/W3 chain. Two consecutive full-source rebuilds produced 66 fresh sources, 779 entities and 1484 relations with identical input-set SHA-256 `b5cffc768d13956af8426ddf99f7081a4b6bfa98b2211c8bd5d6aff2d0fae0bb` and portable snapshot SHA-256 `39eea8fbae12e90726246666057c93d18a0023c53d9357ed9a094cbde2b84b49`. The fixed `/observations` page displays the three layers, both compiled real instances, 21 definitions, 240 values, six constraints, 12 evaluations, violation locations and source IDs. Authenticated in-app browser QA confirmed every key section appears once, all three violation cards render, no replacement characters or horizontal overflow occur at 1280 px, and the console is empty.

R4 is entirely no-CST: `live_cst_status=not_run` and `physical_acceptance_status=not_established`. It defines no frequency, Q, R/Q, field, power, wake, mode identity or optimization objective. R5 now defines the offline contracts for a bounded subset. The user later authorized only the bounded R5 Stage A action described below; that authorization does not retroactively change R4 or the immutable no-CST readiness proof.

### 7.13 2026-08-20 R5 RF result/mode/field readiness and Workbench W5

R5 is active on `codex/rf-cem-r5-rf-result-field`, created exactly from the canonical R4 merge `8c6bd0be38e8b2bbf5d72c1254413ee6b552defe`. The no-CST readiness layer is implemented in `src/rf_cem/physics/`; it imports no CST and defines strict `physics_case.v0`, `result_provenance.v0`, `mode_identity.v0`, `mode_fingerprint.v0`, `metric_contract.v0`, `metric_observation.v0`, `field_bundle.v0` and `mesh_convergence.v0` contracts. `physics_link_status.v0` and `result_comparability.v0` make per-instance linkage and default-deny comparison decisions explicit.

Three RF500 cases bind the same R1 semantic graph, R2 compile record and R4 exact geometry at planned coarse/nominal/fine mesh levels. The repository-verified setup evidence identifies CST 2026 `Solver_HF_TET_E`, Copper (annealed) at `5.8e7 S/m` and Vacuum, but the exact boundary values, numerical mesh controls and CST build remain `not_established`. The nine scalar definitions are eigenfrequency (`MHz`), R/Q (`ohm`), Q perturbation (`1`), stored energy (`J`), Epk (`MV/m`), Bpk (`mT`), Epk/Eacc (`1`), Bpk/Eacc (`mT/(MV/m)`) and surface loss (`W`). Only the existing eigenfrequency, R/Q and `Q-Factor (Perturbation)` result locators are repository-verified; Q perturbation is not relabeled as Q0, and all remaining locators stay `not_established`.

A mode can never be accepted by a bare enumeration index. An established fingerprint requires frequency plus R/Q and symmetry/field evidence. Field data must remain external hash-bound artifacts; inline payloads are forbidden. Mesh convergence needs at least three valid samples, while normal result comparison fails closed on material, boundary, mesh, normalization or mode-identity differences. The special mesh-convergence context relaxes only the intentional mesh difference. SLS-2 remains explicitly `not_linked` because no materialized live-CST result chain exists for that instance.

The current canonical ignored immutable readiness proof is `analysis_outputs/rf_cem_rf_result_contract/r5_rf_result_readiness.d917acb00f4bfbdf/`, input SHA-256 `d917acb00f4bfbdfd9210624fe06890f58c3e657c2f4926743a9ec87cd87378b`. It contains 56 declared artifacts plus its source-binding manifest: three cases/provenance/mode identities/fingerprints/field bundles, 27 null metric observations, nine metric definitions, one unestablished convergence record, two `not_comparable` decisions and two instance-link records. The loader replays the complete R4 proof, re-hashes 23 sources and all artifacts, recomputes the R5 input preimage, reasserts no-CST/authorization/physical status, rejects duplicate or orphan contracts and substituted comparison objects, and recomputes the two planned comparability decisions. This fresh proof was built after the Stage A status/interface source updates and then strictly replayed; its manifest raw SHA-256 is `9ff5da0f9fecbd4f2bd543b6a1e680685e36ec396c928e88fd999435158787bf`. The prior content-addressed proof remains unchanged.

Workbench indexer `r5.w5.v0` adds `--rf-result-bundle` and refuses W5 without the complete W1/W2/W3/W4 chain. Two consecutive full-source rebuilds, retaining the explicit frozen literature package and review session, produced 146 fresh sources, 855 entities and 1635 relations with identical input-set SHA-256 `532de7ce15a16036322088b6b17f552bcf7ddbd9be5f8ebb4ff611444ece90e9` and portable snapshot SHA-256 `8a56f24287b34108a5741af976b1f818aec5b7e2ffb2fffc20074e42c992fed3`. The fixed `/rf-results` page exposes the authorization hard gate, per-instance linkage, physics cases, mode identity/fingerprints, scalar definitions and null observations, provenance, external fields, convergence and comparability. Authenticated in-app browser QA at 1280 px confirmed every result section appears once, the pending-authorization/no-CST/SLS-2 `not_linked` states render, historical scalar values are absent, and there are no replacement characters, page overflow or console warnings/errors.

This is readiness evidence only. The manifest states `validation_mode=no_cst_readiness_only`, `live_cst_authorization=not_requested`, `live_cst_status=not_run` and `physical_acceptance_status=not_established`; all 27 metric values are null. Those assertions describe the immutable readiness bundle and are not hand-edited after later authorization. R5 cannot satisfy its physical hard gate or close until bounded live-CST mode/metric/field/convergence provenance passes these contracts.

On 2026-08-20 the user explicitly authorized live-CST Stage A only: one new isolated RF500 nominal eigenmode project bound to the exact R2 STEP, using the recorded CST 2026 tetrahedral/order-3/one-mode/498–530 MHz setup, with replayable results plus native result-tree, mesh and field-export evidence. The scope forbids reuse or overwrite of an existing output, optimization campaigns, process termination, lock/result deletion, cleanup, recovery, unverified CST API/VBA and license-file import or modification. `src/rf_cem/live_r5_stage_a.py` implements a fail-closed preflight and a guarded `--execute-live` path. It deliberately avoids the shared context-manager close path because that path can force-kill after a timeout; Stage A attempts only native graceful close and records that no force kill or global sweep was attempted.

The exact no-CST preflight passed against R2 bundle `r2_boundary_compiler.aa66a3e90125437b`, R5 readiness bundle `r5_rf_result_readiness.2f5b48efb5568f85`, RF500 STEP SHA-256 `dac9819443816cf67b7977a5504021df5cbd33e3f897beb761feafae784ac515`, and installed CST build `2026.0.1465899`. The first live attempt used new ignored directory `analysis_outputs/rf_cem_r5_live_stage_a/rf500_nominal.20260820.auth01a01a79/` and is preserved as failed evidence. CST launched but `DesignEnvironment.new()` could not connect while the frontend displayed `Specify License`; the report contains zero setup actions, no project PID, no solver result and `graceful_close.status=not_connected`. A read-only follow-up confirmed that the local FlexNet service and `27075@localhost` server/vendor daemon were reachable, but CST 2026 rejected the `start` feature with `Invalid (inconsistent) license key`, FlexNet error `-8,523`. No project setup action or solver ran, no license file was imported or edited, no process was killed, and no lock/result/campaign cleanup or recovery was performed. The CST frontend exited after the dialog was cancelled; the license service remained running. Stage A is therefore authorized but externally blocked before CST connection. Resume it only after a valid CST 2026 license checkout is available and only in another fresh non-existing output directory. Coarse/fine convergence Stage B remains separately unauthorized.

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

R2 closeout verification on 2026-08-20:

```text
targeted representation/compiler + semantic/W2 + architecture: 26 passed in 11.85s
explicit no-CST marker set: 752 passed, 11 skipped in 28.55s
full default branch suite (CST-required tests skipped): 752 passed, 11 skipped in 21.85s
compileall: pass
git diff --check: pass
authenticated loopback browser QA: W2 compile trace and W1 semantic graphs rendered correctly; no replacement characters, horizontal page overflow or console errors
live CST: not run
```

The R2 checks cover every representation round trip, strict finite schemas, ownership and component mismatch rejection, the same compiler entry on two topology sizes, incomplete partition failure, kernel-fallback failure, output tamper detection, two byte-identical real proof builds, strict record loading, complete W2/W1 linkage, deterministic registry rebuild, UI rendering and source/artifact hash fail-closed behavior. They establish no-CST geometry compilation only; R3 subsequently establishes reviewed family induction and R4 establishes geometry observations/constraint evaluation, while RF metric contracts, live solver results and physical acceptance remain unestablished.

R3 closeout verification on 2026-08-20:

```text
targeted R3 induction + R2 compiler + R1 semantic + W0–W3 + architecture: 36 passed in 14.33s
explicit no-CST marker set: 762 passed, 11 skipped in 26.84s
full default branch suite (CST-required tests skipped): 762 passed, 11 skipped in 29.32s
compileall: pass
authenticated in-app browser QA: W3 hard-gate cards/backbone/review/diff/blind sections rendered once; no functional error
live CST: not run
```

The R3 checks cover side/type-only alignment and invariance to native names/roles, common-backbone/residual extraction, optional-motif and alternative-topology proposals, strict finite/hash identities, pending nonmutation, accepted patch application, rejected/needs-evidence exact grammar preservation, existing-instance revalidation, held-out classification, representation isolation, byte-identical real bundles, artifact/manifest tamper rejection, deterministic complete W2→W3 rebuild, source freshness, fixed-route rendering and architecture dependency guards. They establish reviewed semantic induction only; R4 subsequently establishes geometry observations/constraint evaluation, while RF metrics/mode/field results, live solver validation and physical acceptance remain unestablished.

R4 closeout verification on 2026-08-20:

```text
targeted R0B–R4 observation/compiler/induction/semantic/Workbench/architecture: 108 passed in 21.41s
explicit no-CST marker set: 767 passed, 11 skipped in 31.29s
post-UI wording targeted observation + Workbench: 13 passed in 3.36s
compileall: pass
authenticated in-app browser QA: W4 three layers/two instances/constraints/three violation cards each rendered as expected; no replacement characters, horizontal overflow or console errors
live CST: not run
```

The R4 checks cover strict schema/identity round trips, both real compiled instances, exact/shape/scalar separation, native-name isolation, 21 descriptor definitions and 240 values, unit/non-finite/landmark failure, cross-representation and cross-patch equivalence, all constraint kinds and required scopes, immutable geometry, located violations, byte-identical content-addressed proofs, source/artifact/manifest tamper rejection, deterministic complete W1→W4 rebuilding, freshness audit, fixed-route rendering and architecture dependency guards. They establish a geometry observation and contract-evaluation layer only; RF metrics, mode/field contracts, live solver validation and physical acceptance remain unestablished.

R5 no-CST readiness verification on 2026-08-20:

```text
targeted R0B–R5 semantic/compiler/induction/observation/physics/Workbench/architecture: 59 passed in 23.59s
full branch-local no-CST: 785 passed, 11 skipped in 32.51s
compileall for rf_cem.physics and rf_cem.workbench: pass
strict canonical R5 replay: pass; 3 cases, 9 metric contracts, 27 null observations, SLS-2 not_linked
W5 source audit: 146/146 fresh; indexer r5.w5.v0; roadmap phase R5
git diff --check: pass
authenticated in-app browser QA: all W5 sections unique and visible; authorization/no-CST states explicit; historical scalar values absent; no replacement characters, horizontal page overflow or console warnings/errors
live CST: not run; authorization not requested
```

The R5 checks cover strict finite/unit/path/hash schemas; complete R1/R2/R4 case binding; rejection of bare mode indices; fingerprint evidence rules; null-versus-established metric invariants; Q perturbation/Q0 separation; external field tamper rejection; unique three-sample convergence; default-deny comparability with referenced-object rebinding checks; result provenance; full R4 replay; source/artifact/manifest/status tamper rejection; duplicate/orphan contract rejection; byte-identical 57-file readiness builds; deterministic complete W1→W5 rebuilding; freshness audit; fixed-route rendering; and architecture dependency guards. They establish only an auditable extraction/readiness boundary. No CST process, RF value, field artifact, convergence result or physical acceptance was established.

R5 Stage A no-CST guard closeout on 2026-08-20:

```text
targeted Stage A guard + RF500 + R5 contract: 24 passed, 4 skipped in 3.01s
full branch-local default suite: 789 passed, 11 skipped in 36.75s
compileall for src and tests: pass
strict current R5 replay: r5_rf_result_readiness.d917acb00f4bfbdf; pass
Stage A no-CST preflight: ready_no_cst_preflight; exact STEP hash pass; output absent before and after
git diff --check: pass
live CST: not rerun; prior isolated attempt remains blocked before connection by FlexNet -8,523
```

This closeout verifies the bounded Stage A entry, exact recorded nominal solver controls, no-overwrite preflight, native-close-only behavior and external field-file hashing without launching CST. The prior failed output and both content-addressed readiness proofs remain untouched. No license, process, lock, result or campaign cleanup action was performed.

Historical branch-specific pass counts from 2026-07-10 are archived and must not be copied as current evidence without rerunning those worktrees.

## 13. Current priorities

Priority order:

1. Preserve the canonical R5 readiness proof, W5 registry and failed Stage A output as ignored evidence; do not hand-edit, delete or overwrite them.
2. Restore a valid CST 2026 frontend/`start` license checkout through the user's license administrator; do not modify or work around licensing as part of Stage A.
3. Resume the already authorized nominal Stage A only in a fresh non-existing output directory, then capture the saved result tree, mesh/scalars and native field-export evidence without process termination or cleanup.
4. Obtain separate user authorization before coarse/fine convergence Stage B, physical-acceptance decisions, campaigns or optimization.
5. Prove mode identity without a bare index, extract only verified metrics/fields, and require three-level convergence before deciding physical acceptance.
6. Keep representation classes family-independent and treat R2 compile, R3 induction, R4 observations/constraints and R5 readiness records as auditable layers, not interchangeable RF physical evidence.
7. Preserve exact geometry authority: normalized shape samples, scalar descriptors and result contracts never replace R2 profile/STEP identities.
8. Keep the entire R0B–R5 line on `workflow/rf-cem-literature-review`; do not merge the concrete workflow into `workflow/rf-cem-500mhz` or `main`.
9. Promote only demonstrated cross-workflow contracts to `main`, using a separate focused change and compatibility evidence.

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
