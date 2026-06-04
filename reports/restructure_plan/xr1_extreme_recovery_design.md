# XR1 — destructive recovery design / safety plan

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `XR1 — destructive recovery design / safety plan, docs-only` |
| Base branch | `main` |
| Base HEAD | `93a11d18de182f1345c05bf604760784d711f65c` (post-MH3) |
| New branch | `feature/wf1-extreme-com-recovery` |
| Live CST | **No** |
| Destructive fault injection | **No** |
| Runtime code changed | **No** |
| Default config changed | **No** |

---

## 1. Current accepted recovery baseline

### P3 cleanup runtime hardening (accepted, merged in `main`)

| Capability | Evidence |
|------------|----------|
| `_cleanup_workflow_connection()` closes all retry handler tracked connections | Accepted live validation |
| Replacement DE orphan gap fixed | No orphan DE observed |
| `retry_handler.close_all(force)` available | Cleanup uses it |
| No manual taskkill required | Accepted in P3, Q1, Q2, S1, T, WS4 |

### RCR3 synthetic tier-2 recovery (accepted, merged in `main`)

| Capability | Evidence |
|------------|----------|
| Synthetic initial failure injected | Accepted |
| Tier 1 no-op retry | Accepted |
| Synthetic retry failure injected | Accepted |
| Tier 2 recovery callback fires | Accepted |
| Replacement CST connection created | Accepted |
| Evaluator reconnect invoked | Accepted |
| Real CST evaluation after reconnect succeeds | Accepted |
| No orphan DE observed | Accepted |
| No manual taskkill required | Accepted |

### Remaining gap

**No real OS-level kill / destructive COM death test has been performed.**
All recovery phases to date used synthetic failures injected at the Python
layer.  The runtime retry machinery, CST connection lifecycle, and cleanup
paths have never been exercised against an actual CST Design Environment
process that was killed externally or a COM channel that was genuinely
severed.

The workstation environment is known to be unstable, making this gap both
more urgent and more risky.  A structured, safety-gated approach is
required before any destructive action is taken.

---

## 2. Fault taxonomy for future XR phases

| ID | Scenario | Description | Detection | Recovery path | DB / report status | Allowed in bounded XR? | Requires explicit approval? |
|----|----------|-------------|-----------|---------------|-------------------|----------------------|---------------------------|
| `de_process_killed_before_solve` | CST DE process killed externally before solver starts | Python holds a COM reference; COM call returns RPC error or hangs | COM exception on `evaluate_single_pass`; retry runtime detects failure | Tier 1 reconnection; tier 2 recovery callback creates replacement DE | SUCCESS after reconnect, or SOLVER_FAILED with error_taxonomy recording kill | Yes, XR3 candidate | Yes |
| `de_process_killed_during_solve` | CST DE process killed externally while solver is running | COM call in progress hangs; timeout triggers solver_stagnation or COM error | Stagnation timeout or COM exception | Tier 1/2 with evaluator reconnect; solver re-run on replacement DE | Same as above; raw_metrics may be partial | Yes, XR4 candidate | Yes |
| `de_process_killed_after_solve_before_cleanup` | CST DE killed after solver completes but before `_cleanup_workflow_connection` | Cleanup finds DE already dead; `close()` may hang | Cleanup timeout or COM error during `close()` | `close_all(force)` skips dead connection; registry closes remaining | Results already recorded; cleanup warning only | Yes, XR5 candidate | Yes |
| `com_call_hang` | COM call to CST DE hangs indefinitely | Python thread blocks on COM; timeout mechanism triggers | `stagnation_timeout_s` or `evaluation_timeout_s` expiry | Abort COM thread; retry with replacement DE; cleanup may log hang | SOLVER_FAILED with retry count; error_taxonomy records hang | Yes, XR3 or XR4 | Yes |
| `com_connection_lost` | COM channel severed (DE alive but RPC broken) | COM call returns `-2147221164` (CO_E_NOTINITIALIZED) or similar | COM exception with specific error code | Retry runtime tier 1 reconnection; evaluator reconnect | SOLVER_FAILED; reconnect success = SUCCESS on retry | Yes, XR3 | Yes |
| `solver_timeout` | CST solver converges but exceeds time limit (not process death) | `stagnation_timeout_s` triggers | `solver_runner.evaluate()` returns timeout | Legacy retry path: retry handler tier escalation. Retry runtime: tier 1/2 with re-evaluation | SOLVER_FAILED or SUCCESS if retry succeeds | Already tested in P2/P3 | Already covered |
| `replacement_de_orphan_candidate` | Replacement DE created by recovery callback, but original DE is still alive | Two DE processes exist; older PID not properly closed | Process inventory before/after; registry tracks all connections | Close original via registry; confirm single DE post-cleanup | Cleanup warning if orphan found; no eval impact | Yes, XR3 scenario | Yes |
| `cleanup_close_hang` | `DesignEnvironment.close()` hangs indefinitely | `close()` called but DE not responding | Timeout in `close()` (see A24.1, D2 evidence) | Abandon COM thread; log warning; proceed with `force=True` cleanup | Warning logged; no DB impact if results already saved | Previously observed in WS4 | Already tolerated |
| `license_daemon_must_not_kill` | `cstd.exe` — the CST licensing service | Background process, not a DE window | Pre- and post-run inventory must confirm it is never targeted | Not applicable — protected process | Must be recorded in inventory | Never allowed | N/A |
| `unknown_cst_process_state` | CST process found in unexpected state (zombie, hung, no window) | Process exists but is unresponsive / not a normal DE | Process inventory; window state check | Log warning; do not kill unless positively identified as orphan DE | Warning logged; no eval impact | Observe only | Yes |

---

## 3. Process safety policy

### Protected processes

These processes must **never** be killed or targeted by any XR phase:

| Process name | Role | Why protected |
|-------------|------|---------------|
| `cstd.exe` | CST licensing daemon | Headless; always running; not a DE window. Killing it loses the license for all CST instances. |
| `CSTDesignEnvironment.exe` (licensed) | CST DE | Must be positively identified as orphan before any action. Never kill by name alone. |
| Any process whose PID cannot be verified against the recovery registry | Unknown | If the process is not tracked by `CstConnectionRegistry` or `retry_handler`, it must not be killed. |

### Rules

1. **Never kill by broad process name** — always use PID-specific action verified against the recovery registry.
2. **PID must be recorded before action** — the target PID must be captured at creation time and logged.
3. **Pre-run and post-run process inventory required** — snapshot `Get-Process -Name "CST*"` before and after each bounded live XR run.
4. **Emergency cleanup is allowed only if recorded** — if a manual kill becomes necessary, the exact reason, command, time, and residual process state must be documented.
5. **`cstd.exe` / license daemon is protected in all circumstances** — if a kill would target it, the phase must stop immediately.
6. **Replacement DE orphan check** — after any recovery callback that creates a replacement connection, verify the old PID is properly closed.

### Abstract command shape (for planning only, not execution in XR1)

A future bounded XR phase may use a command of the general form:

```
# Identify target PID from retry handler registry or workflow._conn
# Kill confirmed CST DE only, not license daemon
# Pre- and post-run process inventory
```

No executable command is provided in XR1.  The exact command, PID target,
and safety checks will be specified in the approved protocol for each
future XR phase.

---

## 4. XR operator approval gate

Before any destructive live phase (XR3+) can proceed, the operator must
explicitly confirm all of the following:

| Requirement | Language |
|-------------|----------|
| Which phase is approved | "XR3 — bounded destructive live smoke, `de_process_killed_before_solve` scenario" |
| Single fault scenario | Exactly one scenario from the taxonomy (e.g., `de_process_killed_before_solve`) |
| Max evals | Max 1-3 CST solves; no production campaign |
| Is taskkill allowed as planned injection | **Yes** — but only via PID targeting a confirmed, registry-tracked DE |
| Is emergency cleanup allowed | **Yes** — with mandatory post-action recording |
| Where DB/log artifacts may be written | Outside-repo path only |
| `cstd.exe` / license daemon protected | **Confirmed** — never targeted |

---

## 5. Future bounded live test protocol (design, not executed)

### Preflight

- `git status --short` — clean working tree
- No forbidden artifacts tracked (`git ls-files` check)
- Process inventory: `Get-Process -Name "CST*"` before run
- Local config only (`config.local.yaml`, untracked)
- DB and log paths outside repo

### Seed / target run

- Bounded command: `--n-initial 1 --n-iter 0` (max 1-3 evals)
- No production campaign (max 9 evals ceiling, 1-3 preferred)
- Config: evaluation database enabled, success_reuse/warm-start disabled

### Injection point

- **Before solve:** Kill DE process via recorded PID before `evaluate_single_pass`
- **During solve:** Kill DE via recorded PID between solver start and completion (harder to time)
- **After solve before cleanup:** Kill DE after solver returns but before `_cleanup_workflow_connection`
- Exactly **one** scenario per XR phase

### Observation

| Metric | Source |
|--------|--------|
| Retry tier triggered | Retry runtime log |
| Reconnect event | Retry recovery callback log |
| Evaluator reconnect | `evaluator.on_reconnect` log |
| Final evaluation status | `EvaluationDatabaseRecord.status` |
| DB row written | `evaluation_database_storage` |
| Process state after run | `Get-Process -Name "CST*"` |
| Replacement DE orphan counts | `CstConnectionRegistry.close_all()` diagnostics |

### Cleanup

- Confirm **no orphan DE** after run
- **No manual taskkill** unless emergency
- If emergency cleanup required: record exact reason, command, time, residual state
- Clear local config / DB / log files if they would be accidentally committed

### Stop conditions

If any of these occur, stop the phase and report without proceeding further:

- License daemon ambiguity (cannot distinguish DE from `cstd.exe`)
- Unknown process target (PID not in registry)
- Repeated cleanup failure (>2 attempts)
- Working tree dirty with artifacts
- Live CST launch failure (DE fails to start)

---

## 6. DB / schema recording implications

Current v1 schema stores `error_taxonomy` as a JSON blob.  Future XR
phases may need structured fields.  This section identifies extension
points for coordination with a later schema track:

| Field / concept | Type | Purpose | Added when |
|-----------------|------|---------|------------|
| `failure_taxonomy_version` | int | Version of fault taxonomy used to classify the error | Future schema extension |
| `recovery_policy_version` | int | Version of recovery policy that handled this evaluation | Future schema extension |
| `fault_injection_scenario_id` | str or null | ID from the XR taxonomy if fault was injected; null for normal operation | Future schema extension |
| `process_target_metadata` | json | PID, process name, creation time of targeted CST DE | Future schema extension |
| `retry_tier` | int | Which retry tier handled the recovery (0, 1, 2, 3) | Already in `retry_count` |
| `recovery_action` | str | Specific action taken: `"reconnect"`, `"replacement_de"`, `"cleanup_force"`, etc. | Future schema extension |
| `cleanup_result` | json | `close_all` diagnostics: attempted, closed, errors, orphan candidates | Future schema extension |
| `orphan_candidate_count` | int | Number of processes that may be orphan DEs | Future schema extension |
| `emergency_cleanup_flag` | bool | Whether manual taskkill was used | Future schema extension |
| `operator_approval_id` | str or null | Reference to approved XR phase protocol | Future schema extension |
| `artifact_path_refs` | json | Paths to outside-repo logs, process dumps, etc. | Future schema extension |

The current v1 schema is sufficient for recording SUCCESS and
SOLVER_FAILED outcomes from destructive tests via `error_taxonomy`.
Structured fields should be added only after at least one bounded
destructive smoke validates the data model.

---

## 7. Relationship with failure skip

| Concern | Position |
|----------|----------|
| XR records as evidence | XR logs and DB rows may inform a future failure-skip heuristic, but XR1 does not implement skip |
| Transient vs deterministic failure | Process-kill / COM failures are transient environment faults. They **must not** automatically become `probably-infeasible` in the optimizer's surrogate model |
| Future skip criteria | Any future skip must: (a) be exact-key, (b) be opt-in, (c) distinguish environment failures from deterministic geometry/physics failures, (d) be fully auditable via DB records |
| Benefit of XR taxonomy | By classifying failures at injection time, XR makes it possible to later filter by `fault_injection_scenario_id`, enabling a skip policy that only skips environment failures, not physics-infeasible proposals |

---

## 8. Relationship with existing stage/adaptive features

| Feature | Current status | XR1 impact |
|---------|---------------|------------|
| Staged search | No-CST helpers + opt-in runtime wiring, default disabled | XR must not alter stage/adaptive logic. Future live staging practicalization can use XR taxonomy to avoid treating transient workstation faults as feasibility evidence |
| Adaptive bounds | No-CST helpers + opt-in runtime integration, default disabled | Same as staged search |
| Inter-pass recovery | No-CST callback skeleton only | Not modified by XR |
| Post-eval cleanup hardening | Accepted live evidence (P3) | XR builds on this but does not change it |

---

## 9. Future XR phase sequence

| Phase | Scope | Live CST? | Destructive? | Max evals |
|-------|-------|-----------|--------------|-----------|
| **XR1** | Destructive recovery design / safety plan, docs-only | No | No | N/A |
| XR2 | No-CST process/fault harness and classifier tests | No | No | N/A |
| XR3 | One bounded destructive live smoke (`de_process_killed_before_solve`) | **Yes, approved per scenario** | **Yes, one scenario** | 1-3 |
| XR4 | Optional: second scenario only if XR3 accepted | **Yes** | **Yes** | 1-3 |
| XR5 | Optional: DB schema extension / structured failure recording | No | No | N/A |

Each destructive phase requires separate explicit operator approval per
the approval gate in section 4.

---

## 10. Risk table

| Risk | Likelihood | Impact | Mitigation | Resolved by XR1? |
|------|-----------|--------|------------|-----------------|
| Killing wrong process (e.g., `cstd.exe`) | Low | Catastrophic (license lost) | PID verified against registry; target recorded before action; `cstd.exe` named as protected | Plans only |
| License daemon impact | Low | Catastrophic | `cstd.exe` never targeted; pre-run inventory distinguishes DE from daemon | Plans only |
| Orphan DE after kill | Medium | Moderate (leaked window) | Registry tracks all connections; `close_all(force)` on cleanup; pre/post process inventory | Plans only |
| Corrupted CST project | Low if DE killed during write | High | Project is on disk; CST versioning may recover; no project-level destructive action planned | Plans only |
| Hanging COM close | Medium | Moderate (thread leak) | Already handled by `close()` timeout + thread abandon (A24.1, WS4 evidence) | Already tolerated |
| Stale PID (DE restarted with same PID) | Very low | Low (wrong process targeted) | PID captured at connection time; race window negligible | Plans only |
| DB record ambiguity | Medium | Moderate (misclassified failure) | `error_taxonomy` JSON distinguishes transient vs deterministic; future schema will add `fault_injection_scenario_id` | Plans structured fields |
| Conflating transient failure with infeasible design | Medium | High (wrong optimizer skip) | XR taxonomy separates environment from physics failures; future skip must be exact-key and opt-in | Documents distinction |
| Generated artifacts committed by accident | Low | Moderate | `.gitignore`; pre-commit artifact check; outside-repo paths for DB/logs | Standard policy |

---

## 11. Explicit non-goals

| Item | Status |
|------|--------|
| Live CST | **Not run** |
| Destructive action (kill, fault injection) | **Not performed** |
| Runtime code (any `.py` change outside reports/docs) | **Not changed** |
| Taskkill (manual or scripted) | **Not executed** |
| Failure skip implementation | **Not implemented** |
| Probably-infeasible skip implementation | **Not implemented** |
| Schema migration (DB v1 → v2) | **Not implemented** |
| Success reuse semantics change | **Not changed** |
| Warm-start semantics change | **Not changed** |
| Stage/adaptive runtime change | **Not changed** |
| Workflow2 field objective work | **Deferred** |
| Default config changed | **Not changed** |

---

## 12. Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
-- 230 passed, 1 warning

pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
-- 12 passed
```

No live CST.  No destructive commands.

---

## 13. Commit message

```
docs(wf1): design extreme COM recovery safety plan XR1

- Define 10-entry fault taxonomy for future destructive test phases
- Establish process safety policy: no wildcard kill, PID-specific,
  pre/post process inventory required, cstd.exe protected
- Design operator approval gate with explicit per-phase language
- Design bounded live test protocol (preflight, injection, observation,
  cleanup, stop conditions)
- Identify DB schema extension points for structured failure recording
- Clarify relationship with failure skip (transient ≠ infeasible)
- Clarify relationship with stage/adaptive features (not modified)
- Propose XR1-XR5 phase sequence (XR1 docs-only, XR3+ destructive only
  with explicit approval and max 1-3 evals)
```
