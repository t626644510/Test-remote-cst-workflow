# Agent Context Recovery and Maintenance Runbook

Updated: 2026-08-20

Purpose: restore reliable context after a crash, context compaction, task handoff, stale GUI process, interrupted no-CST run, or branch confusion.

This document is procedural. Project truth is `PROJECT_STATUS_CONTEXT.md`; RF-CEM phase gates are in `RF_CEM_ROADMAP_AND_ARCHITECTURE.md`; commands and feature details are in `FUNCTIONS_AND_ENTRYPOINTS.md`; CST interface authority is in `CST_AUTOMATION_INTERFACES.md`.

## 1. Recovery goal

At the end of context recovery, the agent must know:

1. which repository, worktree, branch and HEAD are active;
2. whether the tree was dirty before the current task;
3. whether the requested work belongs to shared `main` or a concrete workflow branch;
4. which source/runtime artifacts are user-owned and must remain untouched;
5. whether live CST is authorized;
6. what validation evidence already exists and what must be rerun;
7. what the next bounded action is.

Do not begin by rereading every historical report. Read the maintained documents, inspect the current diff, then inspect only the source and tests in scope.

## 2. Five-minute cold-start procedure

Run from the directory supplied by the user:

```powershell
$here = (Resolve-Path '.').Path
$here
git status --short --branch
git rev-parse --show-toplevel
git rev-parse HEAD
git branch --show-current
git worktree list --porcelain
git remote -v
```

Then read, in order:

1. root `AGENTS.md`;
2. root `README.md` if human/scientific background is needed;
3. `docs/PROJECT_STATUS_CONTEXT.md`;
4. `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md` for RF-CEM R0B–R5 work;
5. this runbook;
6. `docs/FUNCTIONS_AND_ENTRYPOINTS.md` for the target feature;
7. `docs/CST_AUTOMATION_INTERFACES.md` before touching any CST-facing code.

Inspect local changes:

```powershell
git diff --stat
git diff --check
git diff
git status --short
```

Interpretation:

- modified/untracked files may belong to the user;
- ignored `runs/`, `analysis_outputs/`, CST projects, sessions and PDFs are local evidence, not disposable cache;
- a clean branch does not imply no external live process exists;
- a historical document or tag does not override code/tests.

## 3. Branch ownership decision

Use this decision table before editing:

| Requested change | Correct owner |
| --- | --- |
| Generic CST wrapper, evaluation DB, retry, objective, parameter or optimiser contract | `main` first |
| Generic history/macro extraction | `main` |
| Generic STEP facts, Feature review, resolved labels | `main` |
| RF gun SAO behavior/config/entry | `workflow/1-rfgun-sao` |
| HOM antenna/wake PSO behavior | `workflow/2-rfgun-hom-antenna` |
| Recovery or tolerance behavior | `workflow/3-rfgun-recovery-tolerance` |
| HOM eigenmode campaign behavior | `workflow/4-rfgun-hom-eigenmode` |
| 500 MHz parametric RF-CEM or live campaign | `workflow/rf-cem-500mhz` |
| Literature evidence, semantics, geometry review or GUI | `workflow/rf-cem-literature-review` |
| RF-CEM family contract, R1 semantic topology, R2 representation/compiler, R3 family induction, R4 observation/constraints, R5 result/mode/field contracts, Workbench W0–W5 | `workflow/rf-cem-literature-review` |

If current cwd is the wrong owner:

1. do not copy the target package into the current branch;
2. inspect the correct existing worktree;
3. change cwd or create an explicitly authorized worktree;
4. preserve the user’s dirty changes;
5. record the branch change.

## 4. Discovering worktrees

Worktree directory names are local state, not repository truth. Never infer branch ownership from a directory name. Discover the current machine's mapping:

```powershell
git worktree list --porcelain
git branch --show-current
git rev-parse --show-toplevel
```

The canonical branch names are listed in section 3 and `PROJECT_STATUS_CONTEXT.md`. A new contributor may use one clone without additional worktrees; worktrees are optional.

## 5. Recovering an interrupted documentation or code task

### 5.1 Determine whether edits are intentional

```powershell
git status --short
git diff --name-status
git diff --stat
```

For each changed file:

- identify whether the change predates the current task;
- compare with the most recent commit;
- do not reset, checkout, delete or overwrite unknown edits;
- if overlap is unavoidable, stop and ask the user.

### 5.2 Check the last completed task boundary

```powershell
git log -8 --oneline --decorate
git reflog -12 --date=iso
```

If a commit exists, inspect it rather than recreating work:

```powershell
git show --stat --summary HEAD
git show --name-status HEAD
```

If no commit exists, use the current diff as the only authoritative partial state.

### 5.3 Validate the partial state before continuing

Start with syntax and targeted tests. Use the active clone/worktree's environment:

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
& $py -m compileall -q src workflows
& $py -m pytest -q path\to\target_test.py
```

Do not run live CST as a “validation shortcut”.

## 6. Recovering the literature review GUI

The GUI is a local HTTP service, not a static HTML application.

### 6.1 Find the current launch record

Given the session root:

```powershell
$SessionRoot = '<LOCAL_REVIEW_SESSION_ROOT>'
$launchPath = Join-Path $SessionRoot 'review_launch.json'
$launch = Get-Content -Raw -Encoding UTF8 $launchPath | ConvertFrom-Json
$launch.review_url
$launch.pid
```

Open the full `review_url` including token.

### 6.2 Verify the old process

Never assume the PID is still the review server:

```powershell
Get-Process -Id $launch.pid | Select-Object Id,ProcessName,StartTime,Path
```

If process lookup fails or the URL is unreachable, start a new service. Preserve the old session root if the source hash still matches; otherwise create a new session root.

### 6.3 Restart

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
$BundleRoot = '<LOCAL_LITERATURE_BUNDLE_ROOT>'
$SessionRoot = Join-Path $BundleRoot 'review_sessions\sls2_gui'

& $py -m rf_cem.literature_semantics review-gui `
  --bundle-root $BundleRoot `
  --manifest corpus_manifest.json `
  --paper-id sls2 `
  --session-root $SessionRoot
```

If the session reports a source-payload hash mismatch, do not bypass it. Use a new `--session-root`. Old state remains audit evidence.

### 6.4 Session invariants

- one paper;
- one operating regime;
- one source hash;
- one review revision stream;
- literature decisions separate from Helper2 decisions;
- unsubmitted parameter-form text is not persistent;
- submitted geometry candidates are content-addressed;
- concurrent tabs may produce revision conflict; refresh before retrying.

## 7. Recovering a no-CST validation

### 7.1 Targeted test

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
& $py -m pytest -q tests\test_target.py
```

### 7.2 Full current-branch suite

```powershell
& $py -m pytest -q -m 'not cst_required'
```

### 7.3 Intermittent interpreter failure

This workstation has previously produced one-off Python 3.9/PyYAML/SciPy `SystemError: unknown opcode` and occasional socket/process-exit faults.

Policy:

1. preserve the first output;
2. close that Python process;
3. rerun the same bounded test in a fresh interpreter;
4. treat a stable repeat as a code failure;
5. do not delete sessions, STEP files, results or environments because of one transient exception.

CadQuery/OCP teardown faults require the same distinction: check whether the isolated worker produced a valid structured result before classifying the geometry action.

### 7.4 Recover the RF-CEM semantic/compiler/induction/observation/result proofs and Workbench W0–W5

The R1 content-addressed semantic proof is generated from the Stage C profile and frozen SLS-2 generation/semantics/review sources. The R2 compiler proof binds that profile and R1 proof to two deterministic no-CST STEP/B-Rep compiles. The R3 induction proof aligns only the two reviewed R1 graphs, records an explicit proposal/review/patch chain, then classifies the held-out LEReC 704 MHz reviewed graph. The R4 observation proof reads those exact R2 compiles plus matching R1 graphs and adds separate exact/shape/scalar identities and non-mutating engineering-constraint evaluations. The R5 readiness proof replays R4 and adds planned RF500 cases plus strict result, mode, metric, external-field, convergence, provenance and comparability contracts without supplying live values. Workbench W0–W5 is a derived database, not a session and not a source artifact. First inspect the branch and source state; then use the exact semantic/compiler/induction/observation/result validation, Workbench `status`, and rebuild commands in `FUNCTIONS_AND_ENTRYPOINTS.md`.

```powershell
$WorkbenchDatabase = 'analysis_outputs\rf_cem_workbench\w5.sqlite'
& $py -m rf_cem.workbench status --database $WorkbenchDatabase --repo-root $RepoRoot
```

If the database is absent, or any source reports `stale`/`missing`, do not patch SQLite or copy an older database. Rebuild the explicitly named target from the canonical profile, validation, frozen semantic/review inputs and architecture document. The rebuild is atomic and does not run CST. A running Workbench is a foreground loopback process; stop that owned foreground process normally and start a new `serve` command after rebuild. Never kill unrelated processes or alter source sessions as a Workbench recovery shortcut.

For W1, also supply exactly one `family_grammar.v0`, both canonical instance graphs and the directed SLS-2-to-RF500 graph diff from the same proof directory. The indexer revalidates both graphs and recomputes the diff; never mix files from different content-addressed proofs. If a semantic proof source hash or review binding fails, return to the named frozen source files and diagnose the mismatch. Do not edit a proof JSON, overwrite an existing proof directory, weaken a review state or infer a missing nose parameter.

For W2, the canonical local proof is `analysis_outputs/rf_cem_boundary_compiler/r2_boundary_compiler.aa66a3e90125437b/`. First run `python -m rf_cem.compiler validate` on both records with that bundle as `--bundle-root`; it rechecks strict `compile_record.v0` identity and all output sizes/hashes. Then rebuild Workbench with the complete W1 inputs plus exactly these two record paths. The W2 indexer independently rebinds grammar/graph/profile hashes, region order, landmarks and output artifacts. If validation fails, do not hand-edit JSON/STEP, copy a record from another bundle, weaken a tolerance, overwrite the immutable target or delete the prior proof. Diagnose the named source or code change and intentionally build into a fresh output root; `build` refuses an existing content-addressed target.

For W3, the canonical local proof is `analysis_outputs/rf_cem_family_induction/r3_family_induction.2f6c02557798e606/`. First run `python -m rf_cem.semantic.induction validate --bundle <that-directory>`; it rechecks the manifest, all eight artifact hashes and every alignment/proposal/review/patch/blind identity. Rebuild W3 only with the complete W1 triple, both canonical R2 compile records and this one R3 directory supplied by `--family-induction-bundle`. The indexer must report `roadmap_phase=R3`, `indexer_version=r3.w3.v0`, a passing `w3.family-induction-hard-gate`, both training IDs and the distinct held-out LEReC ID. If a PDF, graph, grammar, representation sentinel or artifact is stale, do not edit JSON, substitute another graph, feed LEReC into training, overwrite the proof or weaken review. Diagnose the named source/code change and intentionally build a fresh content-addressed bundle with a new explicit review revision if warranted.

For W4, the canonical local proof is `analysis_outputs/rf_cem_observation_contract/r4_observation_contract.d06695921d941eee/`. First run `python -m rf_cem.observation validate --bundle <that-directory>`; it re-hashes all 11 declared repository sources and 25 artifacts, recomputes the input SHA-256 preimage and rechecks both instances plus all exact/shape/registry/bundle/constraint/evaluation identities. Rebuild W4 only with complete W1/W2/W3 inputs and this one directory supplied by `--observation-contract-bundle`. The indexer must report `roadmap_phase=R4`, `indexer_version=r4.w4.v0`, `w4_observation_contract=indexed`, both R4 observation bundle IDs and a passing `w4.observation-contract-hard-gate`. If a code/document input, graph, compile record or proof artifact is stale, do not edit JSON, patch SQLite, overwrite the proof, loosen units/tolerances or substitute sampled data for exact geometry. Diagnose the named source change and intentionally build a new content-addressed bundle only after the source contract is final.

For W5, the canonical local proof is `analysis_outputs/rf_cem_rf_result_contract/r5_rf_result_readiness.d917acb00f4bfbdf/`. First run `python -m rf_cem.physics validate --bundle <that-directory>`; it replays R4, re-hashes 23 declared sources and 56 artifacts, recomputes the input preimage and rechecks the manifest assertions, exact inventories, three unique cases, provenance, modes, nine metric definitions, 27 null observations, three external-field placeholders, convergence, recomputed comparability and both instance-link records. Rebuild W5 only with complete W1/W2/W3/W4 inputs and this directory supplied by `--rf-result-bundle`. The indexer must report `roadmap_phase=R5`, `indexer_version=r5.w5.v0`, `w5_rf_result_contract=indexed`, RF500 `planned_not_run`, SLS-2 `not_linked`, and a passing readiness gate that does not claim physical acceptance. If a source or artifact is stale, do not edit proof JSON, patch SQLite, insert historical scalar values, relabel Q perturbation as Q0, or weaken mode/comparability rules. Diagnose the named input and intentionally build a new content-addressed readiness bundle only after its source contract is final.

R1/R2/R3/R4/R5 readiness recovery remains no-CST. A valid STEP/B-Rep, accepted proposal, blind classification, descriptor value, constraint result, readiness contract or `status=pass` does not authorize CST, establish RF values or establish physical acceptance. Do not open CST, run a solver, kill processes, remove locks or clean results as a semantic/compiler/induction/observation/physics/Workbench recovery shortcut.

The user separately authorized nominal R5 live-CST Stage A on 2026-08-20, but the first isolated attempt did not cross the CST connection gate. Preserve `analysis_outputs/rf_cem_r5_live_stage_a/rf500_nominal.20260820.auth01a01a79/` unchanged: its report has zero setup actions and no solver result because CST 2026 rejected the reachable local FlexNet `start` feature with error `-8,523`. This is an external license prerequisite, not a campaign-recovery condition. Do not import/edit a license file, stop/restart the license service, kill CST, remove locks/results or reuse that output. After the user's license administrator confirms a valid CST 2026 frontend checkout, rerun `python -m rf_cem.live_r5_stage_a` only with the exact R2 input, the current strict readiness proof and a new non-existing output directory. The existing authority covers one nominal Stage A solve and UI evidence capture only; coarse/fine Stage B, physical acceptance, campaigns and optimization remain separately gated.

## 8. Recovering a live-CST campaign

This section is a safety checklist, not authorization to run or resume CST.

### 8.1 Required explicit authority

Before action, determine separately whether the user authorized:

- opening/connecting CST;
- running a solver;
- resuming a campaign;
- writing a new CST project;
- overwriting any output;
- killing a process;
- deleting a lock;
- removing a result folder;
- retrying failed candidates.

If any materially required permission is absent, stop before mutation.

### 8.2 Read-only audit first

Inspect:

- config and local overrides;
- output directory;
- `live_records.jsonl`;
- summary/checkpoint/state/heartbeat;
- candidate directories;
- project filenames;
- last diagnostic report;
- CST message log;
- process list and window titles.

Do not edit JSONL, delete locks, or infer next index until cross-file consistency is checked.

### 8.3 Candidate integrity

For RF-CEM, verify that one record’s:

- candidate ID;
- parameter vector;
- package directory;
- generated STEP;
- validation report;
- CST project path;
- live diagnostic path;
- metric values

all refer to the same index and source hash.

### 8.4 Process cleanup

Prefer an owned `mode=new` process and targeted PID cleanup after explicit project save/close. A machine-wide CST sweep is never a default recovery method.

If PID cleanup cannot be verified, record `cleanup_incomplete` and stop. Do not delete locks merely because a GUI is not visible.

## 9. Backup procedure before large change

At minimum:

```powershell
git status --short --branch
git rev-parse HEAD
$BackupRoot = '<BACKUP_DIRECTORY_OUTSIDE_WORKTREE>'
$BundlePath = Join-Path $BackupRoot 'repository_all_refs.bundle'
git bundle create $BundlePath --all
git bundle verify $BundlePath
Get-FileHash -Algorithm SHA256 -LiteralPath $BundlePath
```

For dirty or untracked user inputs, a Git bundle is insufficient. Create a scoped filesystem archive that:

- records included/excluded paths;
- excludes large reproducible caches only by explicit policy;
- never moves or deletes the source;
- has a SHA-256;
- is stored outside the worktree when practical.

Relevant backup names and remote refs:

```text
<BACKUP_ROOT>\rf-cem-literature-review-pre-handoff-20260713-144716.bundle
SHA-256: F77586AB38E70E2B293AEABACCFBB48E9AE3EB4F01BFCE10C38C287733EA0AC6
remote tag: backup/rf-cem-literature-review-pre-handoff-20260713-144716
pre-rebase tag: backup/rf-cem-literature-review-pre-canonical-rebase-20260713-145915

<BACKUP_ROOT>\rf_cem_docs_consolidation_20260712_224614\repository_all_refs.bundle
<BACKUP_ROOT>\cst_ver3_strict_reorg_backup_20260710T121115\
documentation_archive\markdown_before_consolidation_20260712_HEAD-0663994.zip
```

## 10. Safe restore procedure

Do not restore over the active worktree.

Preferred Git bundle inspection:

```powershell
$BundlePath = '<PATH_TO_VERIFIED_GIT_BUNDLE>'
$RestoreRoot = '<NEW_EMPTY_RESTORE_DIRECTORY>'
git clone $BundlePath $RestoreRoot
Set-Location $RestoreRoot
git branch --all
git log --oneline --all --decorate --graph -30
```

Then compare and selectively cherry-pick or copy reviewed files. For archived documentation, extract to a separate directory and read only; do not reintroduce the old document set wholesale.

## 11. Canonical literature-review branch relationship

Recorded ancestry before the handoff/portability commits:

```text
workflow/rf-cem-500mhz
  + 3803921 literature semantics hardening
  + 6faeee7 interactive literature geometry review
  + 0663994 paper isolation + Helper2 audit
  + 0a675df documentation consolidation
  -> workflow/rf-cem-literature-review
```

`workflow/rf-cem-literature-review` is the canonical owner of literature ingestion, semantic review, geometry projection, the local GUI, Stage C family profile, R1 semantic topology, R2 boundary representation/compiler, R3 family induction, R4 observation/constraints, the R5 result/mode/field contract line and Workbench W0–W5. Stage C was merged by PR #4 at `3867a9a8eae502359556a83bcad15b3a519e64de`; R0B by PR #5 at `c0b4574ee2dc87ee98938b282ec023aeebfa12d3`; R1 by PR #6 at `5ae1ba07b841d6adf6e180ec1eedfd073657987b`; R2 by PR #7 at `e81ad20942258380cccb93d17cfdf0ca7e2d0e21`; R3 by PR #8 at `585d549c7a5dac0304852a0150f0c4114fd5b6e9`; and R4 by PR #9 at `8c6bd0be38e8b2bbf5d72c1254413ee6b552defe`. R5 no-CST readiness and the guarded Stage A entry are active on `codex/rf-cem-r5-rf-result-field`. Nominal Stage A is explicitly authorized but externally blocked before connection by the CST 2026 license error above; no live RF result exists and the complete R5 hard gate remains open. `workflow/rf-cem-500mhz` remains the canonical owner of the 500 MHz live geometry/campaign workflow. Do not merge the complete literature branch into either `workflow/rf-cem-500mhz` or `main`.

Before integrating a reusable subset elsewhere:

1. fetch and compare current refs;
2. identify the smallest stable contract and its actual consumers;
3. open a focused change against the correct owner branch;
4. run full no-CST on both relevant states if needed;
5. inspect package-data and ignored-output assumptions;
6. preserve NC/SRF isolation, local GUI authentication and CadQuery worker behavior;
7. preserve user review sessions outside Git;
8. use a backup ref/bundle before history-changing integration;
9. never copy a shared module back under a second name.

## 12. Documentation maintenance procedure

The eight maintained project documents are `README.md`, `CONTRIBUTING.md`, the five files under `docs/` listed below, and the active `.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md`. `AGENTS.md` is the governance entry; `.github/pull_request_template.md` is collaboration infrastructure.

When code changes:

1. update the smallest authoritative document;
2. replace obsolete state rather than appending a report;
3. keep commands in `FUNCTIONS_AND_ENTRYPOINTS.md`;
4. keep CST evidence in `CST_AUTOMATION_INTERFACES.md`;
5. keep transient recovery steps here;
6. keep human explanations in root `README.md`;
7. keep Git/PR instructions in `CONTRIBUTING.md`;
8. update `PROJECT_STATUS_CONTEXT.md` for architecture, maturity, branch or priority changes;
9. run a Markdown inventory and link/path scan.

Expected tracked source Markdown:

```text
AGENTS.md
CONTRIBUTING.md
README.md
.github/pull_request_template.md
docs/AGENT_CONTEXT_RECOVERY.md
docs/CST_AUTOMATION_INTERFACES.md
docs/FUNCTIONS_AND_ENTRYPOINTS.md
docs/PROJECT_STATUS_CONTEXT.md
docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md
.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md
```

Runtime-generated reports such as `review_report.md`, `calibration_report.md` or `history_analysis_report.md` may appear only under output directories and are not added to the maintained set.

## 13. Handoff record template

At the end of an agent task, report:

```text
Goal:
Worktree:
Branch:
HEAD before:
HEAD after:
Pre-existing dirty files:
Files changed:
Scientific assumptions/units:
no-CST validation:
live-CST validation:
Live processes started/stopped:
Local outputs created:
Backups:
Known limitations:
Next safe action:
```

Never claim “validated” without naming the exact command and whether CST was involved.

## 14. Stop conditions

Stop and request direction when:

- branch ownership is ambiguous and the choice changes architecture;
- required user data or paper is missing;
- a user-owned dirty change overlaps the target;
- live-CST authority is incomplete;
- a restore would overwrite an active worktree;
- candidate/record/project provenance cannot be reconciled;
- NC and SRF data appear mixed in one human-review payload;
- the only way forward requires guessing a CST API;
- the requested scientific definition or units are ambiguous;
- cleanup would require killing unrelated processes or deleting unverified locks.
