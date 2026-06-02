# Phase P3 — CST cleanup runtime hardening

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `d3b6668bc45b3ae050f2507d217b1633f8cf7b16` |
| Phase label | `Phase P3 — CST cleanup runtime hardening, explicitly approved only` |
| Branch | `refactor/wf1-sao-consolidation` |
| Operator explicitly approved touching `src/cst_optimization/` | **Yes** |
| Live CST validation run | **Yes** — operator approved post-fix validation |
| Cleanup gap status | **Fixed** — orphan DE no longer remains after workflow cleanup |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added `workflow._retry_handler` attribute for both single-pass and two-pass paths |
| `workflows/rfgun_sao/run.py` | **Modified** | `_cleanup_workflow_connection` now calls `retry_handler.close_all(force)` to close ALL connections |
| `tests/workflows/test_rfgun_sao_imports.py` | **Modified** | Added `test_workflow_build_retry_handler_attribute` |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | Phase P2 accepted; P3 row added |
| `reports/restructure_plan/phase_P3_cleanup_runtime_hardening_report.md` | **Added** | This report |

---

## Cleanup root-cause summary

### The orphan DE chain (Phases P and P2)

1. **Evaluation completes** → `post_eval_recovery == "tier2"` triggers `retry_handler.force_reset()`.
2. **`force_reset()`** → `_graceful_clean_and_reconnect()`:
   - Calls `self._conn.close(force=False)` on the shared `CSTConnection` object → `close()` hangs.
   - `self._de` is set to `None` on the **shared** connection object.
   - `kill_all_cst_processes()` → kills the original DE.
   - `self._conn = _make_new_connection()` → creates a **new** `CSTConnection` with a new DE.
   - `on_reconnect()` → updates `evaluator._conn` but **not** `workflow._conn`.
3. **Final cleanup** → `_cleanup_workflow_connection(workflow)`:
   - Reads `workflow._conn` → the old **nulled** connection → `pid = None`, close is a no-op.
   - The **replacement DE** (referenced only by `retry_handler._conn` after scope exit) survives as an orphan window.
4. **Manual `taskkill /F` required** in both Phase P (PID 30808) and Phase P2 (PID 36496).

### Key insight

The `EvaluationRetryHandler` already tracks all connections in `self._all_connections` and has a `close_all()` method. The gap was that `_cleanup_workflow_connection` never called it — it only closed `workflow._conn` (the old nulled reference).

---

## Implementation change

### Change 1: Store retry handler on workflow (`workflow.py`)

Both single-pass and two-pass code paths now set:
```python
workflow._retry_handler = retry_handler
```

This makes the retry handler accessible to the cleanup function, even after `force_reset()` replaces its internal connection.

### Change 2: Close all retry handler connections in cleanup (`run.py`)

`_cleanup_workflow_connection()` now calls `retry_handler.close_all(force)` after closing `workflow._conn`:

```python
rh = getattr(workflow, "_retry_handler", None)
if rh is not None:
    rh.close_all(force=force)
```

`close_all()` iterates every connection in `_all_connections` (including the replacement DE created by `force_reset()`) and calls `close(force)` on each. Even when `close()` hangs (COM timeout), the force-kill fallback in `CSTConnection.close()` terminates the OS process.

### Why `cstd.exe` is protected

- `close_all()` delegates to `CSTConnection.close()` which targets specific PIDs.
- `kill_all_cst_processes()` has an explicit `CST_PROCESS_WHITELIST = {"cstd.exe"}`.
- The P1 diagnostic helper `should_force_kill_orphan_de()` also correctly rejects `cstd.exe`.
- No change touches the licensing service.

---

## Live CST validation result

### Command

```powershell
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

### Observations

| Metric | Phase P (no fix) | Phase P2 (no fix) | Phase P3 (with fix) |
|--------|-------------------|-------------------|---------------------|
| Best F | -15392.38 | -15392.37 | -15392.38 |
| Original DE PID | 56996 | 50324 | 18252 |
| Replacement DE PID | 30808 | 36496 | 57924 |
| close() hangs | 1 (original) | 1 (original) | 2 (original + replacement) |
| `close_all` called? | N/A | N/A | **Yes** |
| Orphan DE after cleanup | ✅ PID 30808 | ✅ PID 36496 | ❌ **None** |
| Manual `taskkill` needed? | **Yes** | **Yes** | **No** |

The fix introduces a second `close()` hang (on the replacement DE) but properly terminates it via the `force_kill` fallback.

### Post-run process classification (P1 helper)

```
workflow_claimed_closed: True
remaining_count: 1
orphan_candidates: []
summary: "1 process remaining, none orphan"
```

Only `cstd.exe` PID 10184 (licensing service) remained — normal state.

---

## Validation commands and results

```powershell
python -m compileall workflows/rfgun_sao src/cst_optimization tests/workflows/test_rfgun_sao_imports.py
```
→ Compiles OK.

```powershell
pytest tests/workflows/test_rfgun_sao_cst_cleanup_diagnostics.py --tb=short -v
```
→ **24 passed**.

```powershell
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short
```
→ **83 passed**.

```powershell
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short
```
→ **50 passed**.

```powershell
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
```
→ **230 passed** (1 pre-existing warning). Includes new `test_workflow_build_retry_handler_attribute`.

```powershell
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
```
→ **12 passed**.

**Total: 399 passed, 1 pre-existing warning.**

---

## Remaining risks

1. **Two close hangs per run**: Both the original and replacement DE now have their `close()` called, which generates two "close hung" warnings. This is cosmetic — the processes are force-killed properly. A future improvement could skip the graceful `close()` attempt if the connection is known to be dead.

2. **Upstream `close()` hang root cause**: The `DesignEnvironment.close()` COM hang persists. The fix works around it but does not address the underlying COM issue. This is in `cst.interface` (CST library) and cannot be fixed from our side.

3. **`pid=none` in cleanup log**: `workflow._conn.pid` still reads as `None` in the log message because the old nulled connection is checked for the final display. This is cosmetic — all DE processes are properly terminated regardless.

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Operator approved touching `src/cst_optimization/` | ✅ Yes |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| JSONL sidecar as recovery/warm-start source | ❌ Not used |
| probably-infeasible for skip/reuse/runtime discard | ❌ Not used |
| Root shim repoint | ❌ Not done |
| Default config change | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Retry runtime wired to CST runner | ❌ Not wired |
| Cleanup reliability gap | ✅ **Fixed** — verified by live CST |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/core/retry.py` | **Not modified** (used existing `close_all()` API only) |
| `src/cst_optimization/core/connection.py` | **Not modified** |
| `src/cst_optimization/core/cleanup.py` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |
| Legacy `RecoveryWorkflowEvaluator` | **Not copied or referenced** |
| `workflows/rfgun_sao/config.yaml` default behaviour | **Not modified** |
| `workflows/rfgun_sao/cst_cleanup_diagnostics.py` | **Not modified** |
| Root shim | **Not repointed** |

---

## Artifacts check

| Artifact type | Generated | Committed |
|---------------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | `D:/Results/workflow1/workflow1.ckpt` | **Not committed** (outside repo) |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | `D:/Results/workflow1/workflow_1_runtime.log` | **Not committed** (outside repo) |
| CST output dirs | `D:/workflow_elgun/PickupDesign_2026` | **Not committed** (outside repo) |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
Phase P3 rfgun_sao CST cleanup runtime hardening

- Root cause: force_reset() creates replacement DE, but workflow._conn
  still references old nulled connection; final cleanup misses replacement
- Fix: store _retry_handler on workflow container; _cleanup_workflow_connection
  calls retry_handler.close_all(force) to close ALL connections
- Live CST validation confirms cleanup gap FIXED:
  Phase P (no fix): orphan PID 30808 required manual taskkill
  Phase P2 (no fix): orphan PID 36496 required manual taskkill
  Phase P3 (with fix): both original PID 18252 and replacement PID 57924
  properly terminated; only cstd.exe licensing service remains
- 399 tests pass (230+24+83+50+12)

No durable DB, no failure reuse, no retry runtime wiring, no root shim repoint.
```
