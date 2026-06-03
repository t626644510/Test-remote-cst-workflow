# MH1 — accepted branch merge hygiene audit / plan

## Metadata

| Field | Value |
|-------|-------|
| Date | 2026-06-04 |
| Phase label | `MH1 — accepted branch merge hygiene audit / plan` |
| Current branch | `feature/wf1-db-warm-start` |
| Current HEAD | `71158056c0a16aa55721786152f319cc0aec376b` |
| Merge target | `origin/main` @ `4b8225a2abb0e644711e09f7239d23f961d0ad1c` |
| Live CST | **No** |
| Merge performed | **No** |
| GitHub write operation | **No** |

---

## 1. Repository state

### Current branch

```
feature/wf1-db-warm-start
HEAD: 7115805
```

### Working tree

Only `config.local.yaml` (untracked, WS4 artifact) — clean otherwise.

### Accepted branch heads

All local heads match remote heads exactly — no unpushed drift.

### Merge target

`origin/main` at `4b8225a` is the upstream target.
`origin/master` does not exist — no ambiguity.
`main` has only 2 commits (initial commit + "Remove local test results").
All feature branches fork from `main` and are **147+ commits ahead**.

---

## 2. Accepted branch table

| # | Branch | Accepted final HEAD | Current remote HEAD | Matches? | Already merged? |
|---|--------|---------------------|---------------------|----------|-----------------|
| 1 | `refactor/wf1-sao-consolidation` | — | `c58b40a` | N/A (no accepted SHA recorded, Phase V closed) | No (147 ahead of main) |
| 2 | `feature/wf1-real-com-recovery` | `3650752` | `3650752` | **Yes** | No |
| 3 | `feature/wf1-durable-evaluation-db` | `cf31c2e` | `cf31c2e` | **Yes** | No |
| 4 | `feature/wf1-db-success-reuse` | `b532856` | `b532856` | **Yes** | No |
| 5 | `feature/wf1-db-warm-start` | `7115805` | `7115805` | **Yes** | No |

**Note on #1**: `refactor/wf1-sao-consolidation` was accepted at Phase V without
a formally recorded accepted SH A in the task prompt.  The current HEAD `c58b40a`
is the natural final state (Phase V closeout commit).  All downstream branches
fork from this commit, confirming it as the accepted consolidation endpoint.

---

## 3. Git ancestry / dependency chain

```
main (4b8225a)
  └── refactor/wf1-sao-consolidation (c58b40a)              # base for all
        ├── feature/wf1-real-com-recovery (3650752)          # RW + RCR phases
        │     └── (included in downstream branches)
        └── feature/wf1-durable-evaluation-db (cf31c2e)      # includes com-recovery
              └── feature/wf1-db-success-reuse (b532856)     # includes durable-eval-db
                    └── feature/wf1-db-warm-start (7115805)  # includes success-reuse
```

Confirmed via `git merge-base --is-ancestor`:
- sao-consolidation → ancestor of com-recovery → **YES**
- com-recovery → ancestor of durable-eval-db → **YES**
- durable-eval-db → ancestor of success-reuse → **YES**
- success-reuse → ancestor of warm-start → **YES**

Each downstream branch includes **all** commits from every upstream branch.

---

## 4. Recommended merge order

The linear dependency chain forces **sequential merge order**:

| Order | Branch | Must follow | Reason |
|-------|--------|-------------|--------|
| **1** | `refactor/wf1-sao-consolidation` | — | Base for all others |
| **2** | `feature/wf1-real-com-recovery` | #1 | Branches from consolidation |
| **3** | `feature/wf1-durable-evaluation-db` | #1, #2 | Branches from com-recovery |
| **4** | `feature/wf1-db-success-reuse` | #3 | Branches from durable-eval-db |
| **5** | `feature/wf1-db-warm-start` | #4 | Branches from success-reuse |

No branch can merge out of order.  Merge #1 first, then #2, etc.

---

## 5. Per-branch risk table

### Files changed categories legend

- `src/**` — core optimization library
- `workflows/rfgun_sao/` — consolidated workflow package
- `workflows/rfgun_single_pass/` — protected reference
- `tests/` — test files
- `reports/` — documentation
- `.claude/` — Claude config

### Branch 1: `refactor/wf1-sao-consolidation` (172 files vs main)

| Category | Count | Notes |
|----------|-------|-------|
| `workflows/rfgun_sao/` | ~30 | Core consolidation target |
| `workflows/rfgun_single_pass/` | ~6 | Protected; Phase S repoint was scoped |
| `run_workflow_1.py` | 1 | Protected; Phase S repoint was scoped |
| `reports/` | ~120 | Phase design reports |
| `tests/` | ~15 | Import and no-CST tests |
| `.claude/settings.local.json` | 1 | **Artifact risk** — should not have been committed |

**Conflict risk**: **Low** — only ~2 commits on main, no conflicting changes.
**Artifact risk**: **Medium** — `.claude/settings.local.json` was committed in a
Phase O commit.  Should be removed before or immediately after merge.
**Recommendation**: Merge now.  Strip `.claude/settings.local.json` from history
or add `.gitignore` entry and commit removal in a follow-up.

### Branch 2: `feature/wf1-real-com-recovery` (13 unique files vs consolidation)

| Category | Count | Files |
|----------|-------|-------|
| `workflows/rfgun_sao/` | 3 | `retry_runtime.py`, `retry_runtime_cst.py`, `run.py`, `workflow.py` |
| `tests/` | 3 | `test_rfgun_sao_retry_runtime_cst.py`, `test_rfgun_sao_retry_runtime_workflow.py`, `test_rfgun_sao_retry_runtime_recovery.py` |
| `reports/` | 6 | RCR1-RCR3, RW1-RW3 reports |

**Conflict risk**: **Low** — files are additive (new modules + test files).
**Artifact risk**: **Low** — no forbidden artifacts.
**Recommendation**: Merge after #1.

### Branch 3: `feature/wf1-durable-evaluation-db` (9 unique files vs com-recovery)

| Category | Count | Files |
|----------|-------|-------|
| `workflows/rfgun_sao/` | 3 | `evaluation_database_schema.py`, `evaluation_database_storage.py`, `run.py` (modified), `workflow.py` (modified) |
| `tests/` | 2 | `test_rfgun_sao_evaluation_database_storage.py`, `test_rfgun_sao_evaluation_database_workflow.py` |
| `reports/` | 4 | DDB1-DDB3 reports |

**Conflict risk**: **Low** — `run.py` and `workflow.py` modifications are
additive to existing code.  No structural conflicts expected with com-recovery.
**Artifact risk**: **Low** — no forbidden artifacts.
**Recommendation**: Merge after #2.

### Branch 4: `feature/wf1-db-success-reuse` (8 unique files vs durable-eval-db)

| Category | Count | Files |
|----------|-------|-------|
| `workflows/rfgun_sao/` | 2 | `evaluation_success_reuse.py`, `workflow.py` (modified) |
| `tests/` | 2 | `test_rfgun_sao_evaluation_success_reuse.py`, `test_rfgun_sao_evaluation_success_reuse_workflow.py` |
| `reports/` | 4 | SR1-SR4 reports |

**Conflict risk**: **Low** — `workflow.py` changes are additive.
**Artifact risk**: **Low** — no forbidden artifacts.
**Recommendation**: Merge after #3.

### Branch 5: `feature/wf1-db-warm-start` (12 unique files vs success-reuse)

| Category | Count | Files |
|----------|-------|-------|
| `workflows/rfgun_sao/` | 5 | `evaluation_database_storage.py` (modified), `evaluation_database_warm_start.py` (new), `run.py` (modified), `workflow.py` (modified), `BRANCH_CONTEXT.md`, `README.md` |
| `tests/` | 2 | `test_rfgun_sao_db_warm_start_ws2.py`, `test_rfgun_sao_db_warm_start_ws3.py` |
| `reports/` | 4 | WS1-WS4 reports |

**Conflict risk**: **Low** — all changes are additive to existing modules.
`evaluation_database_storage.py` is minimally modified (docstring only).
**Artifact risk**: **Low** — no forbidden artifacts (local `config.local.yaml`
is untracked).
**Recommendation**: Merge after #4.

---

## 6. Protected path changes analysis

| Protected path | Changed by | Scope accepted? |
|----------------|-----------|-----------------|
| `workflows/rfgun_single_pass/` | Consolidation branch | **Yes** — Phase S root-shim repoint |
| `run_workflow_1.py` | Consolidation branch | **Yes** — Phase S root-shim repoint |
| `src/cst_optimization/` | **Not changed** | N/A |

No protected-path violations found beyond already-accepted scope.

---

## 7. Artifact / local config risk

| Pattern | Found in committed diff? | Status |
|---------|-------------------------|--------|
| `config.local.yaml` | No | Clean — untracked |
| `*.sqlite` / `*.db` | No | Clean |
| `*.jsonl` | No | Clean |
| `*.ckpt` | No | Clean |
| `workflow_1_runtime.log` | No | Clean |
| `scripts/inspect_db.py` | No | Clean (deleted) |
| `.claude/settings.local.json` | **Yes** — in consolidation branch | **Should be removed** |

**Recommendation**: Post-merge (or pre-merge in consolidation branch), add
`.claude/settings.local.json` to `.gitignore` and commit its removal.

---

## 8. Doc / context consistency issues

### Issue 1: README stale test count
- **File**: `workflows/rfgun_sao/README.md`
- **Current**: `# 184/184 as of B9`
- **Reality**: 230 tests in `test_rfgun_sao_imports.py`
- **Severity**: Low — cosmetic.
- **Recommendation**: Update as a pre-merge or post-merge cleanup commit.

### Issue 2: BRANCH_CONTEXT tracks WS phases as "completed / pending review"
- **File**: `workflows/rfgun_sao/BRANCH_CONTEXT.md`
- **Current**: All WS1-WS4 phases listed as "Completed / pending review"
- **Severity**: Low — accurate for current branch state.
- **Recommendation**: Update to "Completed / accepted" after merge.

### Issue 3: `.claude/settings.local.json` committed
- **File**: `.claude/settings.local.json` (in consolidation branch)
- **Severity**: Medium — violates "do not commit local settings" policy.
  However, it was committed before the policy was formalized.
- **Recommendation**: Add to `.gitignore` and commit removal as a pre-merge
  hygiene fix in the consolidation branch.

---

## 9. Minimal no-CST post-merge validation plan

Post-merge commands (no live CST, no large campaigns):

```powershell
# Compile check
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py

# Import integrity
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short

# Durable DB storage
pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short
pytest tests/workflows/test_rfgun_sao_evaluation_database_workflow.py --tb=short

# Success reuse
pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short

# DB warm-start (WS2 + WS3)
pytest tests/workflows/test_rfgun_sao_db_warm_start_ws2.py --tb=short
pytest tests/workflows/test_rfgun_sao_db_warm_start_ws3.py --tb=short
```

These test files do not exist on `main` before merges — they will be
post-merge only.  No pre-merge validation is possible on target.

Expected totals after sequential merges:
- 230 imports + 12 single_pass imports = 242 baseline
- + storage tests (40+10 = 50)
- + success reuse (35 + workflow)
- + warm-start (45 + 42 = 87)
- **Estimated final total: ~414 tests**

---

## 10. Explicit non-goals

| Item | Status |
|------|--------|
| Live CST | **Not run** |
| Merge performed | **Not performed** |
| GitHub write operation | **None** |
| Branch deletion / archive | **Not performed** |
| New feature work | **None** |
| Large validation campaign | **None** |
| Destructive COM kill / fault injection | **None** |

---

## 11. Maintainer recommendation

### Merge sequence

1. **`refactor/wf1-sao-consolidation`** → merge first.  Optionally strip
   `.claude/settings.local.json` before merging (or immediately after).
2. **`feature/wf1-real-com-recovery`** → merge second.  No expected conflicts.
3. **`feature/wf1-durable-evaluation-db`** → merge third.  No expected conflicts.
4. **`feature/wf1-db-success-reuse`** → merge fourth.  No expected conflicts.
5. **`feature/wf1-db-warm-start`** → merge fifth.  No expected conflicts.

### Pre-merge hygiene (optional but recommended)

- Remove `.claude/settings.local.json` from consolidation branch
- Update README stale test count (`184/184` → `230`)

### Post-merge follow-up

- Update BRANCH_CONTEXT from "pending review" → "accepted"
- Create a `merge/archive` tag for each merged branch

### Next phase recommendation

**MH2 should be a merge-execution phase** either:
- **Option A (direct push)**: If maintainer has write access, execute the
  5-branch sequential merge directly via `git merge --no-ff` on each branch
  in order, pushing only after each merge is verified locally.
- **Option B (PR-based)**: Open PRs for each branch against `main` in the
  recommended order, wait for CI, then merge.
- **Recommended**: Option A for speed (low conflict risk), followed by
  Option B's validation commands to confirm.

---

## 12. Commit message

```
docs(wf1): plan accepted branch merge hygiene MH1

- Inspected all 5 accepted branches against target origin/main
- Confirmed strict linear dependency chain (consolidation -> com-recovery
  -> durable-eval-db -> success-reuse -> warm-start)
- All remote heads match accepted final SHAs; no drift
- Low conflict risk across all branches; all changes are additive
- Only artifact concern: .claude/settings.local.json committed in
  consolidation branch (pre-dates policy)
- README test count stale (184/230); flagged for cleanup
- Recommended sequential merge order, Option A with local verified merge
- No merge performed; no live CST; no GitHub write operations
```
