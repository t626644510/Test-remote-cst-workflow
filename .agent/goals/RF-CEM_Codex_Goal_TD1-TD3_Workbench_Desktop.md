# RF-CEM Goal：TD1–TD3 技术债修复与 Workbench Desktop v0

**Target agent**：Codex 5.6-sol-max
**Mode**：Goal mode
**Repository**：`t626644510/Test-remote-cst-workflow`
**Canonical base**：`workflow/rf-cem-literature-review`
**Recommended branch**：`codex/rf-cem-td1-td3-workbench-desktop`
**Human technical record**：`docs/RF_CEM_TECHNICAL_RECORD_2_TD1_TD3_WORKBENCH_DESKTOP.md`
**Goal policy**：一个大阶段、一条分支、阶段末一次 push/PR。
**CST policy**：本 Goal 全程 no-CST；不得启动、连接、清理或修改 CST/许可证。

---

## 0. Mission

Complete four bounded tasks:

```text
TD1 Continuity Contract
→ TD2 Spline Contract Rename
→ TD3 R3 Ablation / Score Refactor
→ Workbench Desktop v0
```

Do not continue R5 live work.

The finished system must:

1. use explicit continuity contracts rather than `source_native_segment_ref`;
2. describe the current spline implementation as an approximation, while preserving optimization usefulness and compatibility;
3. prove R3 can add a motif from reviewed graph differences after seed-grammar ablation;
4. replace probability-like confidence with structured proposal support;
5. provide a Windows EXE launcher that opens and controls the Workbench without requiring the user to type commands.

---

## 1. Starting state and branch discipline

### 1.1 Preflight

Before editing:

1. Read:
   - `AGENTS.md`
   - `README.md`
   - `CONTRIBUTING.md`
   - `docs/PROJECT_STATUS_CONTEXT.md`
   - `docs/AGENT_CONTEXT_RECOVERY.md`
   - `docs/FUNCTIONS_AND_ENTRYPOINTS.md`
   - `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`
   - `.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md`
   - the new human technical record.
2. Inspect:
   - current branch and HEAD;
   - worktree status;
   - local uncommitted changes;
   - remote canonical branch;
   - `codex/rf-cem-r5-rf-result-field`.
3. Preserve unknown user changes.
4. Do not delete ignored:
   - proof bundles;
   - SQLite databases;
   - STEP files;
   - review sessions;
   - CST projects;
   - failed R5 Stage A output.
5. Start this goal from the latest `workflow/rf-cem-literature-review`.
6. Do not merge, rebase, rewrite or extend `codex/rf-cem-r5-rf-result-field`.
7. Create one new branch:

```text
codex/rf-cem-td1-td3-workbench-desktop
```

If canonical has advanced, use its actual latest HEAD.

### 1.2 Push policy

During development:

- local commits/checkpoints are allowed;
- do not push each subtask;
- do not create micro-PRs;
- finish TD1, TD2, TD3 and Desktop v0 on one branch;
- push once after the complete Hard Gate;
- create one coherent PR to `workflow/rf-cem-literature-review`.

---

## 2. Global non-goals

Do not:

- launch CST;
- import or connect `cst.interface` in any test or runtime;
- modify CST license files;
- kill CST or run process sweeps;
- continue R5 Stage A/B;
- add COMSOL or solver Translator work;
- add new RF metrics;
- create live result bundles;
- run optimization campaigns;
- implement Semantic Graph Acquisition;
- parse raw figures/PDFs into new semantic graphs;
- implement exact NURBS backend;
- add arbitrary command execution to Workbench;
- expose a Web write API.

All new tests must be no-CST.

---

## 3. Architecture invariants

1. `source_native_segment_ref` is provenance only.
2. Semantic/continuity intent must not depend on a concrete curve implementation.
3. Representation internal joins default to G1 hard.
4. Cross-semantic RF wall interfaces default to G1 hard.
5. C0 is allowed only through an explicit interface/intentional-corner contract.
6. G2 remains supported but is not the default.
7. Profile endpoints use endpoint contracts, not fake two-sided continuity joins.
8. `semantic` does not import concrete representation implementations.
9. `representation` does not import concrete semantic types/families.
10. `compiler` evaluates the explicit policy and records all C0/G1/G2 diagnostics.
11. Current spline approximation remains optimization-capable.
12. Existing proof/schema readers remain compatible.
13. R3 consumes reviewed graphs; it does not acquire semantics from raw evidence.
14. Reviewed graph intrinsic validity and family admission are separate.
15. Workbench Web remains read-only.
16. Desktop Launcher executes only fixed allowlisted actions with `shell=False`.
17. Desktop Launcher may stop only the Workbench child process it started.
18. No CST action or button exists in the launcher.

---

# 4. TD1 — Explicit Continuity Contract

## 4.1 Implement

Create a versioned continuity policy contract, preferably:

```text
boundary_continuity_policy.v0
```

The exact module/file layout may follow repository conventions, but the contract must represent:

```text
internal_patch_policy
semantic_interface_default
semantic_interface_overrides
supported_levels
policy provenance/version
```

Required semantics:

```text
internal patch default = G1 hard
cross semantic interface default = G1 hard
intentional corner override = C0 hard
G2 = supported extension, not default
```

Add explicit endpoint constraints or endpoint classification so profile endpoints are not processed as ordinary joins.

## 4.2 Compiler changes

Refactor continuity selection:

```text
within_region
    → internal patch policy

cross_region
    → explicit interface override
      or family default
```

Remove this decision path:

```text
same source_native_segment_ref
    → G2
else
    → C0
```

Keep `source_native_segment_ref` in records for provenance.

Always calculate and record:

```text
c0_gap_mm
tangent_angle_deg
curvature_delta_per_mm
c0_pass
g1_pass
g2_pass
```

Add:

```text
requirement_source
policy_ref
intentional_corner
```

or functionally equivalent fields.

## 4.3 Required tests

1. within-region line→arc tangent join passes G1 and is not required to pass G2;
2. cross-region ordinary RF wall defaults to G1;
3. intentional-corner C0 override passes despite G1 failure;
4. explicit G2 policy fails if curvature delta exceeds tolerance;
5. source-native segment identity changes do not change required level;
6. endpoint is not emitted as a two-sided continuity check;
7. SLS-2 real compile passes;
8. RF500 real compile passes;
9. Workbench W2 displays policy source and required level;
10. old compile record/proof remains readable.

## 4.4 TD1 Hard Gate

TD1 is complete only when all ten requirements above pass and no CST is run.

---

# 5. TD2 — Spline Approximation Contract

## 5.1 Implement accurate naming

Introduce canonical:

```text
SplineApproxRepresentation
```

The implemented contract must explicitly state:

```text
fidelity = approximate
backend_contract = cadquery.splineApprox.v0
approximation_tolerance_mm = 0.001
optimization_ready = true
exact_nurbs = false
```

Rename or clarify fields so input fitting points are not misrepresented as final exact NURBS poles.

Preferred field semantics:

```text
fit_input_points
source_control_point_hints
max_degree
backend_contract
approximation_tolerance_mm
```

Use the simplest migration consistent with compatibility.

## 5.2 Compatibility

Preserve:

```text
SplineNurbsRepresentation
```

as a deprecated Python/schema compatibility path if required.

Requirements:

- old representation payloads load;
- old R2/R4 proofs load;
- new compiler outputs use accurate naming/version;
- no old proof bundle is overwritten;
- no global proof rebuild is required solely for naming.

Do not create a fake exact NURBS runtime class.

A future `ExactNurbsRepresentation` may appear only as documented/planned capability metadata.

## 5.3 Workbench

Representation page must show:

```text
Approximate
CadQuery/OCCT splineApprox
Tolerance 0.001 mm
Optimization ready
Exact NURBS not implemented
```

## 5.4 Required tests

1. old v0 spline payload loads;
2. new canonical payload round-trips;
3. new and old payloads generate equivalent accepted geometry within current tolerance;
4. current optimization-facing parameters remain mutable/usable;
5. SLS-2/RF500 compile regression passes;
6. R4 observation regression passes;
7. Workbench does not label current implementation as exact NURBS.

## 5.5 TD2 Hard Gate

TD2 is complete only when all seven requirements pass and no CST is run.

---

# 6. TD3 — R3 Grammar Ablation and Support Refactor

## 6.1 Separate validation layers

Implement or formalize:

```text
validate_reviewed_graph_intrinsic(...)
validate_graph_against_grammar(...)
```

Intrinsic reviewed-graph validation checks:

- ontology types;
- IDs;
- topology;
- landmarks/interfaces;
- evidence;
- terminal review state;
- finite/portable contracts.

It must not require every reviewed motif to already exist in the seed grammar.

Family admission remains a separate post-patch check.

## 6.2 Detector architecture

Refactor R3 into a detector/strategy architecture:

```text
FamilyInductionEngine
    detectors: tuple[MotifDetector, ...]
```

Implement at least:

```text
PairedOptionalMotifDetector
SingleOptionalMotifDetector
AlternativeTopology fallback
```

The real SLS-2/RF500 case continues using the paired detector.

The single optional detector may use synthetic fixtures; do not invent a new real family semantic.

## 6.3 Grammar ablation proof

Create a seed grammar fixture/proof derived from the canonical grammar but with:

```text
nose motif removed
nose cardinality removed
nose insertion adjacency removed
```

Keep reviewed RF500 graph NoseRegion nodes.

Expected flow:

```text
intrinsic reviewed graph validation
→ alignment
→ nose optional motif proposal
→ manual accepted review
→ add_optional_motif
→ grammar patch
→ SLS-2/RF500 family admission pass
```

The proposal must be created without reading common geometry parameter names.

## 6.4 Support model

Replace or supersede probability-like scalar confidence with structured support:

```text
structural_match
evidence_completeness
review_coverage
cross_instance_support
population_size
symmetry_assumption_used
detector_id
detector_version
proposal_score
score_semantics = heuristic_support_not_probability
```

A scalar ranking score is allowed only if the non-probability semantics are explicit.

Existing R3 v0 proof must remain readable.

Prefer a new proposal schema version rather than silently changing strict v0 keys.

## 6.5 Workbench

W3 must display:

- seed grammar before ablation patch;
- selected detector;
- structured support;
- symmetry assumption;
- sample/population size;
- pending proposal;
- accepted review;
- `add_optional_motif`;
- grammar before/after diff;
- final admission of both real graphs;
- synthetic single optional detector test/fixture status.

## 6.6 Required tests

1. canonical current paired detector still works;
2. seed grammar without nose does not admit RF500 before patch;
3. RF500 remains intrinsically reviewed-valid;
4. R3 proposes a nose motif;
5. accepted review creates `add_optional_motif`;
6. patched grammar admits SLS-2 and RF500;
7. rejected and needs-evidence do not mutate grammar;
8. synthetic one-sided optional motif is handled by the single detector;
9. support payload is deterministic and explicitly not probability;
10. old R3 v0 proof remains readable;
11. Workbench W3 renders the new fields;
12. no native parameter-name dependence is introduced.

## 6.7 TD3 Hard Gate

TD3 is complete only when all twelve requirements pass and no CST is run.

---

# 7. Workbench Desktop v0

## 7.1 User experience

Double-clicking:

```text
RF-CEM-Workbench.exe
```

must:

1. locate or ask for the repository;
2. load a portable Workbench profile;
3. check source/database freshness;
4. rebuild when missing/stale and sources are available;
5. start the existing authenticated loopback Workbench server;
6. open the default browser automatically;
7. leave a small native control window for safe common actions.

No command line is required for normal use.

## 7.2 Keep Web read-only

Do not add arbitrary action endpoints to `server.py`.

The Web Workbench remains:

```text
GET-only
token-authenticated
127.0.0.1
read-only SQLite
no shell
no CST
```

Operational buttons belong in the native launcher.

## 7.3 Portable profile

Implement a tracked portable profile/schema, for example:

```text
config/rf_cem_workbench_profile.v0.json
```

It should contain repository-relative source recipes for currently canonical W0–W4 inputs and support optional future W5 inputs.

Add a typed profile loader.

Allow local override/config under:

```text
%LOCALAPPDATA%\RF-CEM\
```

Do not hard-code workstation absolute paths in tracked files.

Add CLI/API support equivalent to:

```text
rebuild --profile <profile>
status --profile <profile>
serve --profile <profile>
```

## 7.4 Launcher behavior

Preferred implementation:

```text
Python stdlib tkinter
thin launcher
PyInstaller Windows EXE
```

The launcher may invoke the repository `.venv\Scripts\python.exe` with fixed argument arrays.

Repository discovery order:

1. explicit argument;
2. executable directory/parents;
3. cwd/parents;
4. saved local config;
5. folder picker.

Freshness behavior:

```text
fresh DB
    → open immediately

missing/stale DB + complete sources
    → rebuild and open

missing source
    → show actionable diagnostics
```

## 7.5 Required fixed actions

Buttons:

```text
Open / Start Workbench
Rebuild Database
Refresh Source Status
Stop Workbench
Open Roadmap
Open Project Status
Open analysis_outputs
Copy Workbench URL
Run Quick no-CST Self Check
View Logs
```

Security:

- no arbitrary command textbox;
- no raw shell string;
- `shell=False`;
- fixed action registry;
- validate all paths stay inside expected repo/user config roots;
- launcher stops only its own Workbench child;
- no CST/live/license/cleanup action.

## 7.6 EXE packaging

Add:

```text
scripts/build_rf_cem_workbench_desktop.ps1
```

Use PyInstaller or another locally available Windows packager that produces a real `.exe`.

Preferred output:

```text
dist/RF-CEM-Workbench.exe
```

or one-folder equivalent.

Binary is ignored and not committed.

Launcher must support:

```text
--self-test
--repo-root
--no-browser
```

`--self-test` must avoid GUI/CST and validate:

- repo discovery;
- profile loading;
- Python detection;
- fixed action registry;
- no arbitrary shell;
- configuration write/read;
- dry-run command construction.

## 7.7 Required tests

1. profile schema/load;
2. repo discovery;
3. missing repo/source diagnostics;
4. fresh DB flow;
5. stale DB flow;
6. fixed action allowlist;
7. shell injection rejection;
8. owned-child start/stop;
9. URL/token capture;
10. launcher self-test;
11. Web server remains read-only;
12. W0–W4 pages open from launcher;
13. local EXE build succeeds;
14. EXE `--self-test` passes.

## 7.8 Desktop Hard Gate

Desktop v0 is complete only when all fourteen requirements pass.

---

# 8. Documentation and Workbench updates

Update only canonical docs:

```text
README.md
docs/PROJECT_STATUS_CONTEXT.md
docs/AGENT_CONTEXT_RECOVERY.md
docs/FUNCTIONS_AND_ENTRYPOINTS.md
docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md
docs/RF_CEM_TECHNICAL_RECORD_2_TD1_TD3_WORKBENCH_DESKTOP.md
```

Update the active goal/handoff only once at closeout.

Do not create dated mini-status documents.

Document:

- new continuity semantics;
- spline approximation naming;
- R3 ablation result;
- support score semantics;
- EXE path/build;
- one-click use;
- recovery when DB/source is stale;
- no-CST status;
- deferred Semantic Graph Acquisition.

---

# 9. Test and closeout policy

## 9.1 During development

Run targeted tests for the current subtask.

Use local commits as checkpoints.

Do not push.

## 9.2 Overall Hard Gate

Before final push, all must pass:

1. TD1 Hard Gate;
2. TD2 Hard Gate;
3. TD3 Hard Gate;
4. Desktop Hard Gate;
5. SLS-2 no-CST compile;
6. RF500 no-CST compile;
7. old R1–R4 proof/schema compatibility;
8. new grammar ablation proof;
9. deterministic Workbench rebuild;
10. Workbench W2/W3 UI/browser smoke;
11. launcher EXE local smoke;
12. targeted tests;
13. full:

```text
pytest -q -m "not cst_required"
```

14. `compileall`;
15. `git diff --check`;
16. clean tracked worktree after commit;
17. no live CST;
18. no license change;
19. no CST cleanup;
20. no R5 continuation.

## 9.3 Closeout report

Produce one report containing:

```text
branch
base
HEAD
TD1 behavior before/after
TD2 migration/compatibility
TD3 ablation result
detectors implemented
support schema
Workbench profile
EXE build path
EXE self-test
targeted tests
full no-CST tests
browser/launcher QA
files changed
old proof compatibility
deferred work
push/PR status
```

## 9.4 Final Git action

After the complete Hard Gate:

1. create one coherent closeout commit;
2. push once;
3. open one PR to `workflow/rf-cem-literature-review`;
4. do not target `main`;
5. do not merge R5 live work.

---

# 10. Autonomy

Proceed without asking the user for ordinary implementation choices.

Ask only when:

- an action would delete or overwrite user-owned ignored data;
- the canonical base/branch cannot be resolved;
- a scientific continuity default would materially change the agreed policy;
- no Windows EXE build tool can be made available after trying the simplest local option.

When choosing among compatible implementations, prefer:

```text
simpler
backward-compatible
no-CST
human-visible
testable
fast to finish
```

Do not stop for minor docs, optional hashes, UI cosmetics or stale wording during implementation. Record them and fix once at closeout.

---

# 11. Closeout execution record — 2026-08-24

Implementation on `codex/rf-cem-td1-td3-workbench-desktop` started exactly from R4 canonical merge `8c6bd0be38e8b2bbf5d72c1254413ee6b552defe`. TD1, TD2, TD3 and Desktop v0 are implemented as one no-CST change; R5 and `codex/rf-cem-r5-rf-result-field` were not modified.

Hard-gate evidence:

```text
TD1/TD2 R2 proof:
  r2_boundary_compiler.8f47ca735db8ce8a
TD3 ablation proof:
  r3_family_induction_ablation.59db0a7b5f8e158c
current R4 regression proof:
  r4_observation_contract.a0fd43bd4bf4de2f
portable Workbench:
  65 fresh sources / 738 entities / 1539 relations
  input-set 6bcfd185b18fb3011aff2279c383db4984158fb7e926cce749b5834c8c06e7ad
  snapshot 56d8d9a8b63358fa8a12f02d3183bf9f78ab05477b810c895f8b631ac8fd302c
targeted TD1–TD3/R4/Workbench/Desktop/architecture: 54 passed
full no-CST: 787 passed / 11 skipped
Windows EXE: 10,634,218-byte thin build; --self-test exit 0
native launcher/default-browser smoke: pass
live CST / licence / cleanup / R5: not run or changed
```

The detailed before/after, migration, support schema, Desktop security model, proof identities, QA and deferred work are recorded in `docs/RF_CEM_TECHNICAL_RECORD_2_TD1_TD3_WORKBENCH_DESKTOP.md`. Final commit HEAD, push and PR URL are external Git closeout evidence and are reported after this execution record is committed.
