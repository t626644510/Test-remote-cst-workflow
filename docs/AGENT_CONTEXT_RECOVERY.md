# Agent Context Recovery and Maintenance Runbook

Updated: 2026-07-12

Purpose: restore reliable context after a crash, context compaction, task handoff, stale GUI process, interrupted no-CST run, or branch confusion.

This document is procedural. Project truth is `PROJECT_STATUS_CONTEXT.md`; commands and feature details are in `FUNCTIONS_AND_ENTRYPOINTS.md`; CST interface authority is in `CST_AUTOMATION_INTERFACES.md`.

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
4. this runbook;
5. `docs/FUNCTIONS_AND_ENTRYPOINTS.md` for the target feature;
6. `docs/CST_AUTOMATION_INTERFACES.md` before touching any CST-facing code.

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
| Literature semantics/GUI currently under review | `codex/rf-cem-literature-review-gui` until integration decision |

If current cwd is the wrong owner:

1. do not copy the target package into the current branch;
2. inspect the correct existing worktree;
3. change cwd or create an explicitly authorized worktree;
4. preserve the user’s dirty changes;
5. record the branch change.

## 4. Known worktrees

```text
C:\Users\lau\cst_ver3                         main
C:\Users\lau\cst_ver3_wf1                     workflow/1-rfgun-sao
C:\Users\lau\cst_ver3_wf2_major_refactor      workflow/2-rfgun-hom-antenna
C:\Users\lau\cst_ver3_wf3                     workflow/3-rfgun-recovery-tolerance
C:\Users\lau\cst_ver3_HOMwork                 workflow/4-rfgun-hom-eigenmode
C:\Users\lau\cst_ver3_project                 workflow/rf-cem-500mhz
C:\Users\lau\cst_ver3_rf_cem_semantics        codex/rf-cem-literature-semantics-hardening
C:\Users\lau\cst_ver3_rf_cem_review_gui       codex/rf-cem-literature-review-gui
```

Always confirm with `git worktree list`. These paths are a recovery hint, not a guarantee.

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

Start with syntax and targeted tests. Use the shared environment unless the active worktree has its own known-good environment:

```powershell
$py = 'C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')
& $py -m compileall -q src workflows
& $py -m pytest -q path\to\target_test.py
```

Do not run live CST as a “validation shortcut”.

## 6. Recovering the literature review GUI

The GUI is a local HTTP service, not a static HTML application.

### 6.1 Find the current launch record

Given the session root:

```powershell
$launchPath = 'C:\path\to\review_session\review_launch.json'
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
Set-Location C:\Users\lau\cst_ver3_rf_cem_review_gui
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')
$py = 'C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe'

& $py -m rf_cem.literature_semantics review-gui `
  --bundle-root analysis_outputs\rf_cem_literature_pilot_20260710 `
  --manifest corpus_manifest.json `
  --paper-id sls2 `
  --session-root analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui
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
$py = 'C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')
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
git bundle create C:\safe\path\repository_all_refs.bundle --all
git bundle verify C:\safe\path\repository_all_refs.bundle
```

For dirty or untracked user inputs, a Git bundle is insufficient. Create a scoped filesystem archive that:

- records included/excluded paths;
- excludes large reproducible caches only by explicit policy;
- never moves or deletes the source;
- has a SHA-256;
- is stored outside the worktree when practical.

Current relevant backups:

```text
C:\Users\lau\cst_ver3_backups\rf_cem_docs_consolidation_20260712_224614\repository_all_refs.bundle
C:\Users\lau\cst_ver3_strict_reorg_backup_20260710T121115
documentation_archive\markdown_before_consolidation_20260712_HEAD-0663994.zip
```

## 10. Safe restore procedure

Do not restore over the active worktree.

Preferred Git bundle inspection:

```powershell
git clone C:\path\repository_all_refs.bundle C:\path\restored_repository
Set-Location C:\path\restored_repository
git branch --all
git log --oneline --all --decorate --graph -30
```

Then compare and selectively cherry-pick or copy reviewed files. For archived documentation, extract to a separate directory and read only; do not reintroduce the old document set wholesale.

## 11. Integration recovery for the current GUI branch

Recorded relation:

```text
workflow/rf-cem-500mhz
  + 3803921 literature semantics hardening
  + 6faeee7 interactive literature geometry review
  + 0663994 paper isolation + Helper2 audit
```

Before merging into canonical RF-CEM:

1. fetch and compare current refs;
2. ensure canonical did not advance;
3. run full no-CST on both relevant states if needed;
4. inspect all changed package-data and ignored-output assumptions;
5. verify NC/SRF isolation tests;
6. verify local GUI authentication tests;
7. verify CadQuery worker behavior;
8. preserve user review sessions outside Git;
9. use a backup ref/bundle;
10. integrate into `workflow/rf-cem-500mhz`, not `main`.

Do not merge literature-specific CLI or GUI directly into strict `main`.

## 12. Documentation maintenance procedure

Only the five maintained documents plus `AGENTS.md` are source documentation.

When code changes:

1. update the smallest authoritative document;
2. replace obsolete state rather than appending a report;
3. keep commands in `FUNCTIONS_AND_ENTRYPOINTS.md`;
4. keep CST evidence in `CST_AUTOMATION_INTERFACES.md`;
5. keep transient recovery steps here;
6. keep human explanations in root `README.md`;
7. update `PROJECT_STATUS_CONTEXT.md` for architecture, maturity, branch or priority changes;
8. run a Markdown inventory and link scan.

Expected tracked source Markdown:

```text
AGENTS.md
README.md
docs/AGENT_CONTEXT_RECOVERY.md
docs/CST_AUTOMATION_INTERFACES.md
docs/FUNCTIONS_AND_ENTRYPOINTS.md
docs/PROJECT_STATUS_CONTEXT.md
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
