# RF-CEM R0B–R5 Goal Document for Codex 5.6-sol-max

**Target agent**: Codex 5.6-sol-max
**Mode**: Goal mode
**Repository**: `t626644510/Test-remote-cst-workflow`
**Initial staging branch**: `codex/rf-cem-family-profile-v0`
**Canonical workflow owner**: `workflow/rf-cem-literature-review`
**Goal scope**: Close the existing Stage C branch, then execute RF-CEM Roadmap R0B through R5 phase by phase.
**Primary human-readable architecture document**: `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`

---

## 0. Mission

Transform the current RF-CEM implementation from:

```text
one successful parametric 500 MHz workflow
+
literature/geometry review tools
+
a two-instance provenance-oriented family profile
```

into:

```text
family semantic grammar
→ instance RF-boundary topology
→ independent boundary representations
→ generic geometry compiler
→ family induction and extension
→ representation-independent observations and constraints
→ mode-identified RF result/field contract
→ human-visible project workbench
```

The core model is:

\[
T_x=\operatorname{Instantiate}(F,M_x)
\]

\[
H_i=R_i(\theta_i)
\]

\[
G=\operatorname{Compile}\left(T_x,\{H_i\}\right)
\]

\[
O=\operatorname{Observe}(G,T_x)
\]

Interpretation:

- `FamilyGrammar` defines allowed semantic structures.
- `InstanceBoundaryGraph` defines the actual semantic topology of one cavity.
- `BoundaryRepresentation` defines how one region is mathematically generated.
- `RegionGeometry` may generate one or more patches.
- Every patch has exactly one semantic-region owner.
- `Compiler` combines topology and representations.
- `Observation` derives common shape information and engineering descriptors.
- RF results are added only after geometry identity and observation contracts are stable.

---

## 1. User priorities

1. Develop quickly and pragmatically.
2. Push only at major phase closeout.
3. Do not create micro-PRs for hash changes, minor documentation drift or cosmetic fixes.
4. Preserve strong provenance where it prevents wrong source binding or data loss.
5. Do not turn this personal project into a heavyweight compliance system.
6. Treat the old 500 MHz optimizer integration as a closed historical spike.
7. Build the RF-CEM Workbench early so humans can see:
   - families;
   - instances;
   - semantics;
   - motifs;
   - boundary representations;
   - algorithms;
   - compile records;
   - validation states;
   - roadmap gates;
   - capability coverage.
8. No large-scale optimization before R5 is closed.
9. No live CST before R5 unless the user explicitly authorizes a bounded validation action.
10. Prefer working implementations and clear contracts over premature generality.

---

## 2. Starting-state requirements

Before new architecture work:

1. Read:
   - `AGENTS.md`;
   - `README.md`;
   - `CONTRIBUTING.md`;
   - `docs/PROJECT_STATUS_CONTEXT.md`;
   - `docs/AGENT_CONTEXT_RECOVERY.md`;
   - `docs/FUNCTIONS_AND_ENTRYPOINTS.md`;
   - `docs/CST_AUTOMATION_INTERFACES.md`;
   - `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`.
2. Inspect:
   - current branch and HEAD;
   - worktree status;
   - local changes;
   - existing ignored source/proof/session directories;
   - branch relation to `workflow/rf-cem-literature-review`.
3. Preserve unknown user changes.
4. Do not delete ignored analysis outputs, review sessions, STEP files, CST projects or proof bundles.
5. Validate the existing Stage C family-profile code with targeted no-CST tests.
6. Close `codex/rf-cem-family-profile-v0` as one coherent phase:
   - update stale status prose;
   - ensure source-lossless tests pass;
   - create one final closeout commit;
   - push once;
   - merge or prepare one PR into `workflow/rf-cem-literature-review`.
7. Start R0B from the updated canonical owner, not from an obsolete duplicate worktree.

### 2.1 Execution progress as of 2026-08-20

- Stage C: merged by PR #4 at `3867a9a8eae502359556a83bcad15b3a519e64de`.
- R0B: merged by PR #5 at `c0b4574ee2dc87ee98938b282ec023aeebfa12d3`.
- R1: merged by PR #6 at `5ae1ba07b841d6adf6e180ec1eedfd073657987b`.
- R2: merged by PR #7 at `e81ad20942258380cccb93d17cfdf0ca7e2d0e21` after its real no-CST proof, deterministic W2 rebuild, full regression and browser QA passed.
- R3: merged by PR #8 at `585d549c7a5dac0304852a0150f0c4114fd5b6e9` after graph alignment, common-backbone extraction, optional/alternative proposal contracts, explicit manual review/grammar patch, existing-instance revalidation, real held-out LEReC 704 MHz validation, deterministic W3, full no-CST regression and browser QA passed. The canonical proof is `r3_family_induction.2f6c02557798e606`.
- R4: closed and canonical. PR #9 merged the one closeout commit into `workflow/rf-cem-literature-review` at `8c6bd0be38e8b2bbf5d72c1254413ee6b552defe`. Both compiled real instances retain separate exact/shape/scalar contracts, 21 unit-bound descriptor definitions, 240 values, six reviewed non-mutating constraints, 12 evaluations and three located demonstration violations. Canonical proof `r4_observation_contract.d06695921d941eee`, deterministic W4 (66 fresh sources / 779 entities / 1484 relations), targeted 108-pass and full 767-pass/11-skip no-CST regression, browser QA and PR checks passed.
- R5: active on `codex/rf-cem-r5-rf-result-field`, created exactly from the R4 canonical merge. The no-CST contract/readiness layer now defines every required v0 case/mode/fingerprint/metric/field/convergence/provenance object, the nine initial metric semantics, external field-artifact hashing, replay validation, default-deny comparability, three planned RF500 mesh levels, explicit null/not-established observations, SLS-2 `not_linked`, and Workbench W5. It does not claim a live RF value, mesh convergence or physical acceptance. The remaining Hard Gate requires explicit user authorization followed by bounded live-CST evidence; no such authorization has been received.

---

## 3. Development policy

### 3.1 Branch and push policy

Use one branch per major phase:

```text
codex/rf-cem-r0b-workbench
codex/rf-cem-r1-semantic-core
codex/rf-cem-r2-boundary-compiler
codex/rf-cem-r3-family-induction
codex/rf-cem-r4-observation-contract
codex/rf-cem-r5-rf-result-field
```

During a phase:

- local commits/checkpoints are allowed;
- do not push every local commit;
- do not open micro-PRs;
- push once when the phase Hard Gate is satisfied;
- prepare one coherent closeout PR/merge per phase;
- update canonical docs once at closeout.

### 3.2 Blocking policy

Block development only for:

- possible source corruption or data loss;
- semantic/representation dependency violation;
- invalid topology;
- incorrect geometry compile;
- invalid B-Rep/STEP;
- source-native payload loss;
- stable targeted-test failure;
- unsupported physical claims;
- workbench state contradicting canonical source.

Do not repeatedly stop for:

- stale dates or counts in prose;
- optional missing hashes in derived caches;
- cosmetic UI defects;
- small Markdown formatting issues;
- lint outside modified scope;
- a superseded historical report;
- inability to regenerate an old immutable proof after a non-semantic code/doc change.

Record non-blocking defects and fix them in phase closeout.

### 3.3 Hash and provenance policy

Strictly hash/bind:

- canonical source manifests;
- external evidence;
- exact geometry artifacts;
- instance graphs and family grammars at compile boundaries;
- compile/result source links;
- immutable review or proof inputs.

Do not require forensic-level hashing for:

- every SQLite row;
- UI cache;
- ephemeral query output;
- cosmetic static assets;
- every intermediate development snapshot.

Never regenerate or overwrite an immutable proof bundle solely because documentation or unrelated code changed.

### 3.4 Testing policy

For each phase:

1. write targeted no-CST contract tests;
2. run targeted tests frequently;
3. run the full current-branch `not cst_required` suite at phase closeout;
4. run `compileall` and `git diff --check` at closeout;
5. use live CST only when required by R5 and explicitly authorized;
6. do not treat skipped CST tests as live validation.

### 3.5 Documentation policy

Canonical maintained docs:

```text
README.md
CONTRIBUTING.md
AGENTS.md
docs/PROJECT_STATUS_CONTEXT.md
docs/AGENT_CONTEXT_RECOVERY.md
docs/FUNCTIONS_AND_ENTRYPOINTS.md
docs/CST_AUTOMATION_INTERFACES.md
docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md
.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md
```

At R0B:

- inventory all tracked `*.md`;
- delete superseded Markdown if recoverable from Git or already archived;
- archive only genuinely useful historical material;
- do not maintain parallel dated status reports;
- do not delete `_docs/` vendor/reference material merely because it is old;
- update, do not append duplicate truth.

---

## 4. Non-negotiable architecture invariants

1. `semantic` does not import:
   - CadQuery/OCP;
   - CST;
   - concrete representation implementations.
2. `representation` does not import:
   - concrete family IDs;
   - `NoseRegion`, `EquatorRegion`, etc.;
   - CST.
3. `compiler` may depend on semantic contracts and representation protocols.
4. `observation` reads compiled geometry and semantic topology but does not generate geometry.
5. One `SemanticRegion` owns one `RegionGeometry`.
6. One `RegionGeometry` owns one or more `GeometryPatch`.
7. Every `GeometryPatch` has exactly one semantic owner.
8. A patch never belongs to multiple semantic regions.
9. Cross-region interfaces are expressed through landmarks/interfaces, not shared patches.
10. Sampling points are not patches and not semantic regions.
11. `family_profile.v0` remains a source/provenance contract.
12. `family_grammar.v0` is a separate semantic contract.
13. Common observations/descriptors are not geometry generation parameters.
14. The workbench SQLite database is a rebuildable derived read model, not source truth.
15. Automatic family-extension proposals never mutate canonical grammar without explicit review.

---

# 5. Phase R0B — Architecture Re-baseline + Workbench W0

## Goal

Freeze architecture boundaries and create a usable human-visible project catalog before large semantic/compiler development.

## Required implementation

Create or formalize:

```text
src/rf_cem/semantic/
src/rf_cem/representation/
src/rf_cem/compiler/
src/rf_cem/observation/
src/rf_cem/workbench/
```

Implement W0:

- rebuildable SQLite registry;
- source adapters/indexers;
- local read-only server;
- Overview;
- Families;
- Instances;
- Semantics;
- Representations;
- Algorithms;
- Validation;
- Roadmap/Gates;
- Capability Coverage;
- Compile Records placeholder/legacy adapter.

Index current real assets:

- SLS-2 frozen instance;
- RF500 family instance;
- current family profile;
- literature semantic packages/reviews;
- Helper2 data;
- current geometry/curve implementations;
- current grammar variants/control policies;
- tests and validation evidence.

## R0B Hard Gate

R0B is closed only when:

- Stage C has one canonical owner;
- architecture dependency tests pass;
- SQLite can be deleted and deterministically rebuilt;
- W0 shows both real instances;
- W0 shows current semantic and representation/algorithm inventory;
- W0 shows roadmap and gate status;
- source hash changes are detected as stale/mismatch;
- no shell, arbitrary file browser or CST endpoint exists;
- targeted and no-CST regression tests pass;
- Markdown cleanup and canonical documentation update are complete;
- one phase closeout commit is created and pushed.

Do not implement full family grammar, compiler migration or live CST in R0B.

---

# 6. Phase R1 — RF Boundary Semantic Core

## Goal

Represent SLS-2 and RF500 as different semantic topologies in the same family.

## Required schemas/contracts

```text
family_grammar.v0
instance_boundary_graph.v0
semantic_region ontology
semantic_landmark ontology
boundary_interface contract
semantic_motif model
```

## Required real cases

- SLS-2: nose absent.
- RF500: nose present.

## R1 Hard Gate

R1 is closed only when:

- both instance graphs validate;
- SLS-2 has no nose node;
- RF500 has an evidence-bound nose node;
- graph diff shows semantic/topology difference, not missing parameters;
- one family grammar accepts both instances;
- nose is represented as optional motif or equivalent optional topology;
- invalid adjacency/cardinality fails closed;
- every region has stable identity, evidence and review state;
- W1 shows family grammar, instance graphs, nose presence and graph diff;
- no common geometry parameter vector is introduced;
- targeted and no-CST regression tests pass;
- one closeout push is performed.

Do not attempt family induction or generic geometry compilation yet.

---

# 7. Phase R2 — Boundary Representation Core + Compiler v0

## Goal

Implement the generic:

```text
Compile(T, {Ri, θi})
```

path and migrate SLS-2/RF500 through one compiler entry point.

## Required core types

```text
BoundaryRepresentation
RegionGeometry
GeometryPatch
BoundaryInterface
SemanticLandmark binding
CompileRequest
CompileResult
compile_record.v0
```

## Required first representations

```text
Line
CircularArc
EllipseArc
Spline/NURBS
CompositeRegionRepresentation
```

Use wrappers/adapters around existing generators where this accelerates development. Do not rewrite working geometry code purely for architectural purity.

## R2 Hard Gate

R2 is closed only when:

- semantic and representation independence is enforced;
- SLS-2 and RF500 use one compiler entry;
- every region owns 1..N patches;
- every patch has exactly one owner;
- no patch crosses semantic boundaries;
- shared landmarks connect adjacent regions;
- region/patch order and orientation are deterministic;
- required continuity checks execute and are recorded;
- profiles are closed, non-self-intersecting and produce valid B-Rep/STEP;
- new compiled outputs match accepted existing baselines within declared tolerance or have reviewed differences;
- source-native provenance is preserved;
- each compile emits `compile_record.v0`;
- W2 displays region→representation→patch, landmarks, validation and artifacts;
- at least one representation is reused in more than one semantic context;
- targeted geometry/contract tests and no-CST regression tests pass;
- one closeout push is performed.

Do not add complex analytic-expression design or optimization search.

---

# 8. Phase R3 — Family Induction / Extension v0

## Goal

Automatically propose family structure from reviewed instance graphs, with nose optionality as the primary proof.

## Required implementation

```text
graph alignment
common backbone extraction
optional motif proposal
alternative topology proposal
family_extension_proposal.v0
proposal review
grammar patch application
```

## Required blind validation

Add one third real NC axisymmetric single-cell instance not used to develop the rules.

## R3 Hard Gate

R3 is closed only when:

- alignment does not depend on common parameter names;
- SLS-2/RF500 yield a common backbone;
- the system proposes nose as optional motif;
- proposal includes evidence, locators, adjacency, confidence, algorithm version and review status;
- proposal does not mutate grammar automatically;
- accepted proposal updates grammar through an explicit patch;
- all existing instances revalidate after acceptance;
- rejected/needs-evidence proposal leaves grammar unchanged;
- third-instance blind validation succeeds as nose-present, nose-absent or a justified new extension proposal;
- W3 shows alignment, backbone, proposals, reviews and grammar diff;
- targeted, blind-fixture and no-CST regression tests pass;
- one closeout push is performed.

Do not claim unsupervised semantic discovery from raw pixels/STEP unless separately demonstrated.

---

# 9. Phase R4 — Observation & Engineering Constraint Contract

## Goal

Create a common observation space without turning it into a common generation parameter vector.

## Required layers

1. exact native geometry reference;
2. semantic shape observation;
3. scalar engineering descriptor.

## Required first descriptors

Global:

```text
total_cavity_length
maximum_radius
minimum_aperture_radius
vacuum_volume
surface_area
semantic_region_count
nose_present
```

Regional:

```text
axial_extent
arc_length
maximum_radius
minimum_radius
minimum_radius_of_curvature
endpoint tangent/curvature
nose_tip_radius
equator_crest_radius
```

## Required constraint types

```text
hard
soft
advisory/diagnostic
```

with units, tolerance, scope and provenance.

## R4 Hard Gate

R4 is closed only when:

- both real instances produce observation bundles from compiled geometry;
- observations do not depend on native parameter names;
- exact, shape-observation and scalar layers are separate;
- descriptors have definitions, units, versions and provenance;
- invalid units/non-finite values fail closed;
- equivalent geometry expressed with different patching/representation yields equivalent descriptors within tolerance;
- human constraints on length, radius, aperture, curvature and nose presence evaluate on both instances;
- constraints do not mutate geometry;
- W4 shows descriptors, constraints, violations and source;
- targeted, cross-representation and no-CST regression tests pass;
- one closeout push is performed.

Do not implement RF metrics or optimization in R4.

---

# 10. Phase R5 — RF Result / Mode / Field Contract

## Goal

Create auditable, comparable RF physics results linked to exact compiled geometry and mode identity. Formal optimization begins only after R5.

## Required contracts

```text
physics_case.v0
mode_identity.v0
mode_fingerprint.v0
metric_contract.v0
metric_observation.v0
field_bundle.v0
mesh_convergence.v0
result_provenance.v0
```

## Required initial RF quantities

Attempt to establish:

```text
eigenfrequency
R/Q
Q perturbation
stored energy
Epk
Bpk
Epk/Eacc
Bpk/Eacc
surface loss
```

Unsupported or unverified quantities remain explicitly not established.

## R5 Hard Gate

R5 is closed only when:

- each result binds to family, instance graph, compile record, exact geometry, physics case, solver/version, material, boundary, mesh, mode identity, locator, unit and extraction method;
- Q perturbation is not mislabeled as Q0;
- normalization and mode requirements are explicit;
- incompatible cases are `not_comparable` by default;
- one complete replayable RF500 live-CST bundle exists;
- one representative case has multi-level mesh convergence evidence;
- mode identity is not a bare mode index;
- field data is stored as external artifacts with manifest/hash references;
- W5 shows cases, modes, metrics, fields, convergence and comparability;
- SLS-2 remains `not_linked` if no live RF evidence exists;
- user explicitly authorizes the bounded live-CST validation;
- no large optimization campaign is required;
- no-CST contracts, replay tests and bounded live-CST validation pass;
- one closeout push is performed.

Do not enter multiphysics, HOM, ports/couplers or large-scale optimization in R5.

---

## 11. Workbench requirements across phases

### W0

Catalog, source status, roadmap/gates, coverage.

### W1

Family grammar, instance semantic graphs, nose present/absent, graph diff.

### W2

Compile trace, region ownership, patches, landmarks, continuity, artifacts.

### W3

Graph alignment, backbone, motif proposals, review, grammar diff.

### W4

Shape observations, descriptors, constraints and violations.

### W5

Physics cases, mode identity, scalar metrics, field artifacts, convergence and comparability.

Every new canonical object type must be visible in the workbench before its phase closes.

---

## 12. Phase closeout report

At each phase closeout, produce one concise report containing:

```text
phase
branch
HEAD
scope completed
hard gates passed
hard gates not passed
deferred issues
targeted tests
full no-CST tests
live CST status
source/provenance changes
Workbench views added
docs updated
files deleted/archived
push/PR status
next phase entry conditions
```

Do not create multiple dated mini-reports. Update canonical status and use the phase commit/PR as history.

---

## 13. Immediate goal

Close R3, then continue from its canonical merge:

```text
R3 full no-CST/documentation closeout
→ one push + PR checks + canonical merge
→ R4 Observation & Engineering Constraint Contract
```

Do not begin R4 until R3 Hard Gate passes and the R3 phase is integrated into the canonical owner.

Proceed autonomously using repository code, tests and maintained documentation. Ask the user only when:

- a destructive action affects user-owned data;
- live CST or process cleanup is required;
- a scientific definition materially changes the intended physics;
- branch ownership cannot be resolved from Git state.

For ordinary implementation choices, choose the simplest architecture consistent with the invariants and continue.
