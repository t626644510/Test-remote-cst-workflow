# Phase P1 — CST cleanup reliability gap analysis / hardening plan

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `38d3d86aaa60ca16c0d8c805e606f1115c7fa48f` |
| Phase label | `Phase P1 — CST cleanup reliability gap analysis / hardening plan` |
| Branch | `refactor/wf1-sao-consolidation` |
| No-CST helper added | **Yes** — `workflows/rfgun_sao/cst_cleanup_diagnostics.py` |
| Live CST run | **No** — not required for this phase |
| Cleanup gap fixed | **No** — remaining open; diagnostic helper added only |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/cst_cleanup_diagnostics.py` | **Added** | No-CST diagnostic helpers: `classify_cst_process`, `should_force_kill_orphan_de`, `summarize_cleanup_observation` |
| `tests/workflows/test_rfgun_sao_cst_cleanup_diagnostics.py` | **Added** | 24 tests covering classification, orphan detection, observation summary, safety |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | Phase P marked Accepted at 38d3d86; P1 row added; caveats and next directions updated |
| `reports/restructure_plan/phase_P1_cleanup_reliability_gap_report.md` | **Added** | This report |

---

## Phase P cleanup evidence (summary)

From Phase P live smoke (minimal single-pass, `n_initial=1, n_iter=0`):

| Event | Detail |
|-------|--------|
| **Initial DE** | PID 56996 — connected and ran 1 evaluation |
| **Evaluation** | Best F = -15392.38, all 7 metrics computed |
| **Close hang** | `DesignEnvironment.close() hung (PID=56996) — abandoning COM thread` |
| **Proactive reset** | Legacy `cst_optimization.core.retry` triggered a "Proactive graceful reset" and connected a new DE (PID 30808) for cleanup |
| **Workflow log** | `CST cleanup: attempted=True closed=True pid=None` |
| **Orphan DE** | PID 30808 (`CST DESIGN ENVIRONMENT_AMD64`) remained with visible window — required manual `taskkill /F` |
| **Licensing** | `cstd.exe` PID 10184 remained running normally (expected) |

### Root-cause sketch

The sequence has three stages:

1. **Normal operation**: CST DE connects, evaluation runs, workflow completes.
2. **Close hang**: The `close()` COM call on the original DE (PID 56996) does not return promptly.
   The `cst_optimization.core.connection` module abandons the COM thread and marks the
   connection as closed.
3. **Legacy retry proactive reset**: The `cst_optimization.core.retry` module detects
   the abandoned connection, treats it as a recoverable fault, and opens a **new** DE
   (PID 30808) to perform cleanup operations (removing result directory, clearing
   checkpoint). This new DE is then closed via a normal `close()` call, but the
   underlying OS process (PID 30808) is not terminated — only the COM reference is
   released. The process continues running with a visible GUI window.

The result: `closed=True` is reported, but an orphan DE window remains.

### Why this affects retry/recovery integration

If the Phase O/O1 retry runtime were wired to the CST pipeline, each retry attempt
that restarts CST could potentially leave orphan DE windows, especially if:
- The evaluation triggers a `close()` hang on the current DE.
- The reconnect logic opens a new DE without force-killing the previous one.
- The retry budget (e.g., `max_tier=3`) multiplies the number of potential orphans.

A reliable retry/recovery mechanism must ensure that CST process lifecycle
(connect → evaluate → disconnect → force-cleanup-on-hang) is deterministic, with
no dangling GUI processes.

---

## Scope decision: no-CST diagnostic helper

**Decision**: Add a no-CST diagnostic helper (`cst_cleanup_diagnostics.py`) with
pure classification and decision-support functions, but **do not modify** any
runtime cleanup code.

Rationale:
- The cleanup gap lives in `src/cst_optimization/core/connection.py` and
  `src/cst_optimization/core/retry.py` — touching these is outside Phase P1's
  protected-area boundary and requires deeper understanding of the COM lifecycle.
- A diagnostic helper provides immediate value for future phases that DO address
  the runtime code: it can classify processes, identify orphans, and produce
  structured observations without importing CST or calling OS kill functions.
- Live CST is **not needed** — all helpers are pure Python with no side effects.

---

## No-CST helper design

### Module: `workflows/rfgun_sao/cst_cleanup_diagnostics.py`

#### `classify_cst_process(process_name, *, has_window_title, main_window_title) -> str`

Classifies a process name into one of three categories:
- `"licensing_service"` — matches `cstd` / `cstd.exe`.
- `"design_environment"` — matches known DE names (`cst_design_environment_amd64`,
  `cst_design_environment`) or any name containing both "cst" and "design" (heuristic).
- `"unknown"` — everything else.

Raises `ValueError` on empty/whitespace input.

#### `should_force_kill_orphan_de(process_info, *, workflow_claimed_closed) -> tuple[bool, str]`

Conservative diagnostic policy (never kills — returns recommendation only):

| Condition | Kill? | Reason |
|-----------|-------|--------|
| Licensing service | ❌ No | Must remain running |
| Unknown process | ❌ No | Conservative skip |
| Invalid PID (≤ 0) | ❌ No | Cannot identify |
| Empty process name | ❌ No | Cannot classify |
| DE with visible window | ✅ Yes | Window present after workflow cleanup |
| DE without window, cleanup claimed | ✅ Yes | Orphan process after claimed cleanup |
| DE without window, cleanup not claimed | ❌ No | May be starting / idle |

#### `summarize_cleanup_observation(...) -> dict`

Aggregates multiple `CstProcessInfo` records into a structured observation dict
with `workflow_claimed_closed`, `workflow_pid`, `remaining_count`,
`orphan_candidates` list, and a human-readable `summary` string.

### Safety guarantees

- No `cst.interface`, `cst.results`, or `cst_optimization` imports.
- No `taskkill`, `os.kill`, `subprocess`, `Popen`, or `TerminateProcess` calls.
- No file I/O (`open()`, `.write`, `.read`).
- No `psutil` dependency.
- No live CST interaction.

---

## Test coverage (24 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestClassifyCstProcess` | 6 | cstd, DE, heuristic variant, unknown, empty raises, window-title passthrough |
| `TestShouldForceKillOrphanDe` | 8 | licensing skip, DE+window orphan, DE no-window+claimed orphan, DE no-window no-claim not orphan, invalid PID, empty name, unknown process, heuristic variant orphan |
| `TestSummarizeCleanupObservation` | 6 | empty, default args, licensing only, orphan DE detected, multiple orphans, None workflow_pid |
| `TestSafety` | 4 | no CST imports, no taskkill/kill, no file I/O, no psutil |

---

## Validation commands and results

All commands run from repository root (`c:\Users\lau\cst_ver3`):

```powershell
# 1. Compile check
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
```
→ Compiles OK.

```powershell
# 2. New cleanup diagnostics tests
pytest tests/workflows/test_rfgun_sao_cst_cleanup_diagnostics.py --tb=short -v
```
→ **24 passed**.

```powershell
# 3. Retry runtime tests (no regression)
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short
```
→ **83 passed**.

```powershell
# 4. Retry taxonomy tests (no regression)
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
```
→ **50 passed**.

```powershell
# 5. rfgun_sao imports (no regression)
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```
→ **229 passed** (1 pre-existing warning).

```powershell
# 6. rfgun_single_pass imports (no regression)
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
```
→ **12 passed**.

**Total: 398 passed, 1 pre-existing warning.**

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run (no-CST phase) |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Root shim repoint | ❌ Not done |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Retry runtime wired to CST runner | ❌ Not wired |
| Cleanup reliability gap | ⚠️ Open — diagnostic helper added only; runtime code not modified |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/retry_runtime.py` | **Not modified** |
| `workflows/rfgun_sao/retry_taxonomy.py` | **Not modified** |
| `workflows/rfgun_sao/config.local.yaml` | **Not committed** |
| Root shim | **Not repointed** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Key findings

1. **Cleanup gap is pre-existing and understood**: The `close()` hang + legacy retry
   proactive reset chain that creates orphan DE windows is a known behaviour pattern
   (B5.1). It is not specific to Phase O/O1 work.

2. **No-CST diagnostic helper added**: `cst_cleanup_diagnostics.py` provides pure
   classification and decision-support functions for identifying orphan DE processes
   vs. the licensing service. This can be used by future phases that implement
   runtime cleanup hardening.

3. **Cleanup gap remains open**: Runtime code in `src/cst_optimization/` was not
   modified. The diagnostic helper only observes and reports; it does not fix the
   orphan DE issue.

4. **Retry runtime not wired**: Phase O/O1 `retry_runtime.py` remains a standalone
   no-CST module. Wiring it into the CST pipeline should only proceed after cleanup
   reliability is addressed, or with explicit understanding that orphan windows may
   accumulate during retry loops.

---

## Final HEAD commit SHA

**To be confirmed by reviewer.** Expected to include:
- `workflows/rfgun_sao/cst_cleanup_diagnostics.py` (added)
- `tests/workflows/test_rfgun_sao_cst_cleanup_diagnostics.py` (added)
- `workflows/rfgun_sao/BRANCH_CONTEXT.md` (updated)
- `reports/restructure_plan/phase_P1_cleanup_reliability_gap_report.md` (added)

---

## Commit message proposal

```
Phase P1 rfgun_sao CST cleanup reliability gap analysis / hardening plan

- Added no-CST cst_cleanup_diagnostics.py helper:
  classify_cst_process() — distinguishes licensing service from DE
  should_force_kill_orphan_de() — conservative orphan detection policy
  summarize_cleanup_observation() — structured observation aggregator
- 24 no-CST tests covering classification, orphan detection, safety
- BRANCH_CONTEXT.md: Phase P accepted, P1 row added, caveats updated

Cleanup gap remains open (diagnostic helper only; runtime code untouched).
No live CST, no durable DB, no failure reuse, no retry runtime wiring.
```
