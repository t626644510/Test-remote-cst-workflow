# Agent Project Status Context

Status timestamp: 2026-08-18 Asia/Shanghai

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
| RF-CEM literature review/GUI | `workflow/rf-cem-literature-review` | canonical; colleague handoff target | `0a675df8714564e03ce305959095183524238850` before portability/handoff changes |

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

Stage C is complete on branch `codex/rf-cem-family-profile-v0`, implementation commit `d28ffcfd4db1a81e907316b8966178decf6cd003`. The canonical family is `nc_axisymmetric_single_cell_rf_vacuum` with independent identity fields `operating_regime=normal_conducting`, `symmetry=axisymmetric`, `cell_count=single`, and `geometry_scope=rf_vacuum`.

The two input manifests were consumed read-only and rechecked after proof generation:

- `sls2.r149.6593e02e`: `analysis_outputs/rf_cem_literature_pilot_20260710/frozen_baselines/sls2.r149.6593e02e/baseline_manifest.v0.json`, raw SHA-256 `19a15b0ea8248a85b698d9ace32e87ae190b6356b814fb3c1817d89987da0ffb`;
- `rf500.2c27faee.b1r3`: owner bundle `analysis_outputs/rf_cem_family_instance_sources/rf500.2c27faee.b1r3/instance_source_manifest.v0.json`, raw SHA-256 `4c64d1497bfcd98749fa2df7a742614820159e8ceaa665e6bec95d2ea4b916a5`.

The SLS-2 native payload has one unique source: `generation.core.json#/parameter_tuple/values`. Its six original names and values are `L=680.0`, `l=188.671`, `r=50.0`, `R=249.901`, `a=125.232`, and `b=70.2322`, all in `mm`, with scope `published_candidate`. The source artifact raw SHA-256 is `31051d936b71682ffc64dea4c174dde7b56f2e7eed31aa7d87f9e32d6e159fa1`; the six-value native canonical SHA-256 is `bdc9e7e251e628933aeeb82a5d3165578a33b52d6b62635fb36757d0986b2620`. The frozen revision-149 session/source binding remains payload SHA `99f51410d436116f99fe4c165b1580aa9037ac91e1f66d7245fecaac85f0ee8e`; it is provenance for the review payload, not a replacement for the six-value locator.

The RF-CEM native payload retains the original `parametric_geometry.v0` schema, model type, variant, `named_parameters` group (15 entries), and `derived_parameters` group (52 entries). Original units remain `MHz`, `mm`, and `ns`; source payload raw SHA-256 is `2c27faeecb5d36f9815fb5045d6c967749ddaaff3dec080a5ffa00599bb69a3f` and source canonical SHA-256 is `d392a87f4f6cee5793747dede68c51e0738a80b0439c6c80d686e74f2e277557`. The portable family-native projection has canonical SHA-256 `9bd06e773a84861439e0851a2c2e30a24223c088b0932b274c45eeb2fe8d8461`; only machine-absolute source-path strings are path-neutralized, while named/derived fields, values, units, scope and the source raw/canonical hashes remain bound.

The generic schema is under `src/rf_cem/family_profile/schema.py` and uses `$defs/family_instance.v0`, `instances.minItems=1`, unconstrained native schema/group names and non-fixed parameter counts. The two adapters are `Sls2FamilyInstanceAdapter` and `Rf500FamilyInstanceAdapter`; their no-CST build and portable restore round-trips passed. The eight validation layers remain separate for both instances. `live_cst` is `not_run` for SLS-2 and `not_linked` for RF-CEM; both `physical_acceptance` values remain `not_established`; the metric contract remains `excluded_pending_definition`, with no executable family objectives.

The ignored proof bundle is `analysis_outputs/rf_cem_family_profiles/nc_axisymmetric_single_cell_rf_vacuum.75f6cba4/`. Its deterministic files and hashes are:

- `family_profile.v0.json`: raw `9a33cdbf6a2c4d28ab90eabb81fd45628e9eead3b07a390ff87bb7eced085275`, canonical `75f6cba4bb92208b9a64349c09fd5c0a4ff8c6dd775c173f327593214e05abab`;
- `family_profile_validation.v0.json`: raw `73ac686e55ac5a12791f4fe9d21a88ae1eb2399e45b07d23bf1eb3f6086da2a5`, canonical `6ee60e1d72a879a09e2cd7573fd43a02bacb77683182dfc44316239aad573463`;
- `adapter_roundtrip_report.v0.json`: raw `911fb500e1310d068d87e2d7f32f430452e5641a0e9864f17ea7cda5713d3852`, canonical `b973dc99a9991c96d369f301c4a27e49210832a613c83306e6d7266735984031`;
- `source_binding_manifest.v0.json`: raw `13a299b237531cdede416267d2e3c9c83f7e08a9e8dc4a0846366c87e2803ca7`, canonical `1d79bb45927aca0edabfbfad38543d1b44ce2db48b68981db7cf04f783c27f54`.

Two builds from the same inputs produced identical profile bytes and canonical SHA. Validation commands were `.venv\Scripts\pytest.exe -q -p no:cacheprovider tests\test_rf_cem_family_profile.py tests\test_rf_cem_literature_geometry_candidate.py tests\test_rf_cem_literature_review_bundle.py tests\test_rf_cem_literature_review_app.py tests\test_rf_cem_literature_semantics_v0.py` (`58 passed`) and `.venv\Scripts\pytest.exe -q -p no:cacheprovider -m "not cst_required"` (`709 passed, 11 skipped`). `python -m rf_cem.family_profile validate --profile <proof>/family_profile.v0.json` passed. No CST, solver, campaign, recovery, merge-prior, push or PR was run/performed. `family_schema_established=true` and `adapter_established=true` are established for this two-instance no-CST contract only; they do not imply parameter equivalence, metric equivalence, live-CST linkage, or physical acceptance. SLS-2 soft-only ranges remain soft-only.

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

Full no-CST result after the SLS-2 GUI closeout:

```text
697 passed, 11 skipped in 11.82s
```

This result includes the literature review GUI and Helper2 integration. It does not include live CST. The consolidation verification also completed:

- full current-branch no-CST suite;
- `compileall` for source and workflows;
- `git diff --check`;
- tracked-Markdown inventory and link/path scan;
- CLI `--help` smoke for maintained entries.

Historical branch-specific pass counts from 2026-07-10 are archived and must not be copied as current evidence without rerunning those worktrees.

## 13. Current priorities

Priority order:

1. Stage B only: in the `workflow/rf-cem-500mhz` owner, obtain one real hash-pinned `parametric_geometry.v0` instance; do not create the family schema in this stage.
2. Audit RF-CEM candidates 039 and 046 on the workstation.
3. Implement/test the 490–510 MHz window objective.
4. Add arbitrary live-record seed loading with provenance validation.
5. Add campaign collision, resume and idempotency contract.
6. Validate semantic generalisation on new normal-conducting papers.
7. Run a blinded superconducting transfer benchmark with domain-specific priors isolated.
8. Keep literature/GUI development on `workflow/rf-cem-literature-review`; do not merge the complete workflow into `workflow/rf-cem-500mhz`.
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
