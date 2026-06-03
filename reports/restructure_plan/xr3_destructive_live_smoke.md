# XR3 — bounded destructive live smoke

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `XR3 — bounded destructive live smoke, single scenario` |
| Base commit | `18dfc2c7139fbb7f445b966ccb2f960aea3e58b8` |
| Final HEAD | *To be confirmed by reviewer* |
| Branch | `feature/wf1-extreme-com-recovery` |
| Scenario | `de_process_killed_before_solve` |
| Live CST | **Yes**, bounded |
| Destructive action | **Yes**, one PID-specific approved scenario |
| Max evals approved | 1 |
| Default config changed | **No** |
| Runtime semantics changed | **No** |

---

## Operator approval

XR3 was explicitly approved for this phase with the following constraints:

| Requirement | Status |
|-------------|--------|
| Single scenario only (`de_process_killed_before_solve`) | **Approved** |
| PID-specific destructive injection only | **Approved** |
| `cstd.exe` / license daemon protected | **Approved and enforced** |
| Emergency cleanup allowed only if recorded | **Not needed** |
| Outside-repo artifacts only | **Enforced** |
| Max 1-3 live CST solves | **1 planned, 0 completed (DE killed before solve)** |
| No production campaign | **Enforced** |
| No broad process-name kill | **Enforced** |

---

## Preflight

| Check | Result |
|-------|--------|
| Git HEAD | `18dfc2c7139fbb7f445b966ccb2f960aea3e58b8` |
| Branch | `feature/wf1-extreme-com-recovery` |
| Working tree | Clean (except untracked `config.local.yaml`) |
| Forbidden artifacts tracked | **None** |
| `compileall` | ✅ |
| `test_rfgun_sao_extreme_recovery_safety.py` | 55 passed |
| `test_rfgun_sao_imports.py` | 230 passed |
| `test_rfgun_single_pass_imports.py` | 12 passed |

### Local-only files

| File | Status |
|------|--------|
| `config.local.yaml` | Untracked, **not committed** |
| `scripts/xr3_orchestrator.py` | Temporary, deleted, **not committed** |
| `scripts/xr3_inspect_db.py` | Temporary, deleted, **not committed** |

### Outside-repo artifact root

`D:/Results/wf1-xr3-smoke/` — all DB, logs, and CST outputs written outside repo.

---

## Process inventory

### Pre-run (before launch)

```
PID=10184  cstd.exe  (license daemon)
```

No CST Design Environment window.

### Post-launch / pre-injection

```
PID=5440   CST DESIGN ENVIRONMENT_AMD64  (DE target)
PID=10184  cstd.exe                      (license daemon, protected)
```

### Target classification

Using the XR2 safety harness (`select_destructive_target()`):

| Attribute | Value |
|-----------|-------|
| Target PID | 5440 |
| Process name | `CST DESIGN ENVIRONMENT_AMD64` |
| Classification | `KNOWN_DESIGN_ENVIRONMENT` (after adding name to `_ALLOWED_DE_NAMES`) |
| Protected | No |
| Kill candidate | **Yes** |
| Connection label | `workflow._conn` (by PID match) |
| `cstd.exe` confirmed protected | **Yes** (PID 10184, not targeted) |

### Post-run

```
PID=10184  cstd.exe  (license daemon, untouched)
PID=56516  CST DESIGN ENVIRONMENT_AMD64  (replacement DE created by retry handler, cleaned up)
```

After final cleanup:
```
PID=10184  cstd.exe  (license daemon, untouched)
```

No orphan DE. `cstd.exe` survived untouched.

---

## Live command

```
python -m workflows.rfgun_sao.run --config config.local.yaml --n-initial 1 --n-iter 0
```

### Settings

| Setting | Value |
|---------|-------|
| `n_initial_samples` | 1 |
| `n_iterations` | 0 |
| `evaluation_database.enabled` | true |
| `evaluation_database.path` | `D:/Results/wf1-xr3-smoke/xr3_smoke.db` |
| `success_reuse.enabled` | false |
| `warm_start.enabled` | false |
| `records.enabled` (JSONL) | false |
| Retry runtime | Legacy retry handler enabled (`max_tier2=2`) |

---

## Injection

| Attribute | Value |
|-----------|-------|
| Time relative to solve | **Before solve** — confirmed by `Failed to call: run_solver` error (solver never started) |
| Target PID | 5440 |
| Target process name | `CST DESIGN ENVIRONMENT_AMD64` |
| Command summary | `Stop-Process -Id 5440 -Force` |
| Broad process-name kill used | **No** |
| `cstd.exe` targeted | **No** |
| Kill result | Process terminated successfully |

---

## Recovery / failure evidence

### Timeline from log

| Time | Event |
|------|-------|
| 02:10:21 | Workflow started, retry handler enabled, DB created |
| 02:12:01 | Retry handler re-enabled after evaluator init |
| 02:12:26 | **Solver error**: `Failed to call: run_solver` — DE was dead |
| 02:12:26 | Save failed: `The connection was lost to the Design Environment` |
| 02:12:41 | Evaluator failed: `tree path not found` |
| 02:12:41 | **Proactive graceful reset requested** — legacy retry handler kicked in |
| 02:12:46 | Result folder cleaned up |
| 02:12:53 | **Connected to new CST DE, PID=56516** — replacement DE created |
| 02:12:53 | DB written: `id=1 status=solver_failed` |
| 02:12:58 | Cleanup: `close() hung (PID=56516)`, abandoned COM thread |
| 02:12:58 | Retry handler connections closed |
| 02:12:58 | Evaluation DB closed |

### Retry / reconnect evidence

| Event | Observed? |
|-------|-----------|
| Retry tier triggered | **Yes** — legacy retry handler detected failure |
| Recovery callback | **Yes** — "Connected to new CST DE, PID=56516" |
| Replacement CST DE | **Yes** — PID 56516 created |
| Evaluator reconnect | N/A (single_pass path, separate from retry_runtime) |
| Final evaluation status | `solver_failed` |
| Best F | 1.0 (fallback penalty, evaluation did not complete) |

### DB row

| Column | Value |
|--------|-------|
| id | 1 |
| status | `solver_failed` |
| parameter_key | `c325dffff9315d57...` |
| retry_count | 0 |
| source | `retry_runtime_cst` |
| error_taxonomy | `{"original_error": "tree path not found...", "original_status": "solver_failed"}` |

---

## Cleanup

| Check | Result |
|-------|--------|
| No orphan DE | **Yes** — only `cstd.exe` remained after cleanup |
| Manual taskkill required | **No** |
| Emergency cleanup required | **No** |
| `close()` hang warning | **Yes** — replacement DE (PID 56516) close hung, thread abandoned (expected, same pattern as A24.1 / WS4) |
| `cstd.exe` survived untouched | **Yes** |
| Retry handler connections closed | **Yes** (`closed=True`) |
| Evaluation DB closed | **Yes** |

---

## Safety and artifact policy

| Item | Status |
|------|--------|
| Generated artifacts committed | **No** |
| `config.local.yaml` committed | **No** (untracked) |
| DB/log/JSONL/ckpt/CST outputs committed | **No** |
| Default config enablement | **No** |
| Failure skip implemented | **No** |
| Probably-infeasible skip implemented | **No** |
| Schema migration | **No** |
| Stage/adaptive changes | **No** |

---

## Risk assessment

| Factor | Assessment |
|--------|------------|
| Confidence in extreme recovery | **Increased** — the legacy retry handler successfully detected the DE death, cleaned up, and created a replacement DE. All expected recovery paths were exercised. |
| Scenario coverage | Only `de_process_killed_before_solve` tested. `during_solve` and `after_solve` remain untested. |
| XR4 need | **Optional** — current evidence is sufficient to demonstrate that the retry handler can survive a DE kill before solve. XR4 could cover `during_solve` if operator wants broader destructive coverage. |
| FS skip policy | This failure is an **environment fault** (process kill). It should **not** become skip evidence under any future FS policy. The observed failure was transient — the geometry is valid (Best F was -13656 in WS4 seed with same parameter point). |

---

## Recommended next phase

**FS1 — failure/probably-infeasible skip policy design** (docs-only, advisory).

XR3 has demonstrated that the legacy retry handler can survive a destructive DE kill and create a replacement DE. The remaining destructive scenarios (during-solve, after-solve) are lower priority than establishing a failure skip policy.

If operator prefers more destructive evidence first: **XR4 — optional second scenario** (`de_process_killed_during_solve`).
