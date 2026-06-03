# RCR1 — Real COM recovery design + no-CST recovery callback planning

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `523d0b3cb2618c1df60083b98e3d862e9c5c644d` |
| Branch | `feature/wf1-real-com-recovery` |
| Phase label | `RCR1 — Real COM recovery design + no-CST recovery callback planning` |
| Nature | **Docs/design only** — no runtime code, no live CST |

---

## Current RW3.2 retry runtime state summary

| Component | Status |
|-----------|--------|
| `run_retry_loop_no_cst()` | Accepts `recovery_callback(tier, record) -> bool`; currently called with `recovery_callback=None` from workflow.py |
| `make_cst_retry_evaluate_once()` | Adapter-only: evaluates one attempt via `evaluator.adapt_for_retry()`, returns `EvaluationDatabaseRecord`; **no recovery logic** |
| `workflow.py` wiring | `_retry_runtime_cfg` resolved via `check_legacy_retry_mutex()`; evaluator path uses `recovery_callback=None` |
| Synthetic smoke validation | RW3: initial synthetic SOLVER_FAILED → retry loop → real CST evaluation → SUCCESS; **no COM loss tested** |
| P3 cleanup hardening | `retry_handler.close_all(force)` terminates all tracked connections; replacement DEs tracked via `_all_connections` |

### What RW3 validated

- Retry loop invoked via workflow wiring (synthetic initial failure).
- CST-backed `evaluate_once` adapter runs real CST evaluation on retry attempt.
- `final_record` with penalty extraction used by optimizer.
- Checkpoint records only final result.
- No orphan DE after single-attempt retry (`max_tier=1`, no reconnect).

### What RW3 did NOT validate

- Real COM loss/recovery (no engineered `COM_LOST`).
- Tier-2 recovery callback (reconnect CST DE).
- Multiple retry attempts with connection lifecycle.
- Replacement DE lifecycle management outside the evaluator.

---

## Why RW3 did not validate real COM recovery

1. **Scope constraint**: RW3 was bounded to `max_tier=1` with synthetic initial failure. The recovery callback path was never exercised because tier-2+ recovery was explicitly not in scope.

2. **Recovery callback not supplied**: `run_retry_loop_no_cst()` was called with `recovery_callback=None` in the RW3 wiring. The retry loop's recovery mechanism is entirely controlled by this callback — without it, no reconnection occurs.

3. **Adapter separation**: `make_cst_retry_evaluate_once()` correctly owns only single-attempt evaluation. Adding recovery there would create a hidden double-recovery path, which the RW1.1 design explicitly rejected.

4. **No controlled COM fault mechanism**: There is no safe, reproducible way to induce a real `COM_LOST` status without actually killing the CST Design Environment process — which would leave an orphan DE requiring manual cleanup. Unlike the synthetic SOLVER_FAILED hook (which is purely in-memory), a real `COM_LOST` has side effects on the OS process.

---

## Proposed recovery ownership

```
run_retry_loop_no_cst (retry_runtime.py)
    │
    ├── recovery_callback(tier, record) -> bool
    │   └── supplied by workflow.py when retry_runtime.enabled & !legacy retry
    │       └── owns: close old DE, reconnect, update evaluator._conn,
    │                 track new DE for final cleanup
    │
    └── evaluate_once(tier, record) -> EvaluationDatabaseRecord
        └── supplied by make_cst_retry_evaluate_once (retry_runtime_cst.py)
            └── owns: single attempt via evaluator.adapt_for_retry()
                NO recovery logic, NO hidden reconnect
```

### Responsibility boundary

| Layer | Owns | Does NOT own |
|-------|------|-------------|
| `run_retry_loop_no_cst` | Iteration, classification, recovery callback invocation, max-tier bound | CST lifecycle, connection management |
| `make_cst_retry_evaluate_once` | One CST evaluation via `adapt_for_retry`, record building | Recovery, reconnect, cleanup |
| `workflow.py` (caller) | Config resolution, mutex check, **supplying recovery callback**, orchestration | Taxonomy, retry loop internals |
| Recovery callback | Close old DE, create new DE, update evaluator, track for cleanup | Evaluation, classification |

---

## Proposed connection recovery adapter

### Recovery callback signature

```python
def _retry_recovery_callback(
    tier: int,
    record: EvaluationDatabaseRecord,
    *,
    library_path: str,
    evaluator: Workflow1Evaluator,
    retry_handler: Any | None,  # legacy handler for close_all tracking
) -> bool:
    """Recovery callback for retry runtime.

    Called by ``run_retry_loop_no_cst()`` before each retry-attempt
    ``evaluate_once`` call when the record is retry-eligible.

    Tier 1: No action needed (same connection).
    Tier 2+: Close current DE, create fresh connection, update evaluator.
    """
    if tier < 2:
        return True  # same connection is fine

    try:
        # Close ALL tracked connections via P3 pattern
        if retry_handler is not None:
            retry_handler.close_all(force=True)

        # Create new CST connection
        from cst_optimization.core.connection import CSTConnection
        new_conn = CSTConnection(library_path, mode="new")
        new_conn.connect()
        new_conn.set_quiet_mode(True)

        # Update evaluator reference
        evaluator.on_reconnect(new_conn)

        # Track in legacy handler for final cleanup
        if retry_handler is not None:
            retry_handler._all_connections.append(new_conn)

        _logger.info("RCR recovery: reconnected (tier=%d, PID=%s)", tier, new_conn.pid)
        return True
    except Exception as exc:
        _logger.warning("RCR recovery failed (tier=%d): %s", tier, exc)
        return False
```

### Connection registry for cleanup

The recovery callback creates new `CSTConnection` instances. These must be tracked for final cleanup. Two approaches:

**Approach A: Use legacy `retry_handler._all_connections`** (recommended for minimal change)
- The recovery callback appends new connections to `retry_handler._all_connections`.
- The existing `_cleanup_workflow_connection` already calls `retry_handler.close_all(force)`.
- No new registry needed.
- Condition: `retry_handler` must exist (even when legacy retry is disabled) for tracking purposes.

**Approach B: Dedicated retry-runtime connection registry**
- Add a module-level `_retry_runtime_connections: list[CSTConnection]` in `retry_runtime_cst.py`.
- Recovery callback appends to this list.
- Workflow cleanup iterates this list and calls `close(force)`.
- More explicit, less coupling to legacy code.
- Requires new cleanup code in `workflow.py`.

**Recommended: Approach A** for RCR2, falling back to Approach B if Approach A proves fragile.

---

## Cleanup / orphan-DE risk model

### Process lifecycle during recovery

```
Initial DE (PID A) — connected, running evaluation
         │
         ├── COM_LOST or SOLVER_FAILED → retry eligible
         │
         ▼
    Recovery callback (tier 2+)
         │
         ├── close_all(force) → kill PID A
         ├── new CSTConnection (PID B) → connect
         ├── evaluator.on_reconnect(PID B)
         └── track PID B in retry_handler._all_connections
         │
         ▼
    evaluate_once → CST evaluation on PID B
         │
         ├── SUCCESS → final_record = PID B's result
         └── FAILURE → retry again (max_tier bound)
```

### Orphan-DE risk scenarios

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Tier 1 retry (same connection) | Low — no new DE | N/A |
| Tier 2+ recovery (new DE) | Medium — PID A may survive `close_all()` hang | P3 pattern: `close_all(force)` + force-kill fallback + verify_process_cleanup |
| Recovery callback exception | Medium — PID A not killed, PID B not created | `_logger.warning`; retry loop continues with old DE (may fail again); max_tier bound prevents infinite loop |
| Ctrl+C during recovery | Low — `finally` block runs `retry_handler.close_all(force)` | P3 hardening covers this |
| Multiple retries (max_tier > 1) | Low — each recovery replaces DE; only latest + leftover tracked via `_all_connections` | `close_all(force)` iterates all tracked connections |

### Required invariants

| Invariant | Enforcement |
|-----------|-------------|
| No silent double retry with legacy `optimization.retry.enabled` | `check_legacy_retry_mutex()` disables new runtime if legacy enabled |
| No hidden adapter-level recovery | `make_cst_retry_evaluate_once` has no recovery parameters (removed in RW2.1) |
| No untracked replacement connection | Recovery callback appends to `retry_handler._all_connections` or equivalent registry |
| No retry beyond `max_tier` | `attempts_consumed >= max_tier` guard in `run_retry_loop_no_cst` |
| No failure reuse | Taxonomy: single failure never permanent; no `should_escalate_to_probably_infeasible` call |
| No probably-infeasible skip | `use_probably_infeasible_for_skip=True` rejected at runtime |
| Checkpoint records only final result | Evaluator closure calls checkpoint once with final_record payload |
| `cstd.exe` licensing service never killed | `CST_PROCESS_WHITELIST` in `cleanup.py`; recovery callback uses targeted PID kill, not broad `kill_all` |

---

## Proposed no-CST test strategy (RCR2)

### Fake objects

```python
class FakeConnection:
    """Duck-typed CSTConnection for no-CST recovery tests."""
    def __init__(self, pid=0):
        self._pid = pid
        self._closed = False
        self._force_closed = False

    @property
    def pid(self):
        return self._pid

    def close(self, force=False):
        self._closed = True
        if force:
            self._force_closed = True


class FakeEvaluatorWithReconnect:
    """Evaluator that spies on on_reconnect calls."""
    def __init__(self):
        self.reconnect_calls = []

    def on_reconnect(self, new_conn):
        self.reconnect_calls.append(new_conn)

    def adapt_for_retry(self, params, iteration):
        return EvaluationResult(status=EvaluationStatus.SUCCESS)
```

### Test scenarios

| Scenario | What it validates |
|----------|-------------------|
| Tier 1 recovery: callback not called | `run_retry_loop_no_cst` with `max_tier=1` does not invoke recovery for single attempt |
| Tier 2 recovery: callback called | Recovery callback invoked at tier 2; new connection created via factory |
| Recovery callback: success path | Callback returns True; new connection tracked for cleanup |
| Recovery callback: exception | Callback returns False (exception caught); retry loop continues but bounded |
| Recovery callback: close_all after replacement | `close_all(force)` called on all tracked connections; old DE marked closed |
| Recovery callback: on_reconnect called | Evaluator's `on_reconnect` invoked with new connection |
| Multiple recoveries: tracking | Each recovery adds to `_all_connections`; `close_all` iterates all |
| Recovery + max_tier exhaustion | Retries with recovery, hits max_tier, returns terminal failure |

### Test structure

Tests for RCR2 should be in `tests/workflows/test_rfgun_sao_retry_runtime_recovery.py`.

---

## Proposed live CST strategy (RCR3)

| Prerequisite | Condition |
|-------------|-----------|
| Operator approval | Explicit, before RCR3 starts |
| Branch | `feature/wf1-real-com-recovery` |
| RCR2 no-CST tests | All passing |
| Command | `python run_workflow_1.py --config config.local.yaml --n-initial 1 --n-iter 0` |
| Legacy retry | `optimization.retry.enabled: false` |
| Retry runtime | `retry_runtime.enabled: true, max_tier: 2` |
| Smoke injection | `retry_runtime.smoke_injection: true` + env var (for controlled failure) |

### What RCR3 should validate

1. Synthetic SOLVER_FAILED → retry loop → tier 1 recovery (no-op) → CST evaluation → SUCCESS or failure.
2. If `max_tier >= 2`, simulate a scenario where the first retry attempt fails with COM_LOST (via adapter that injects a second synthetic failure on the first real retry) → recovery callback invoked at tier 2 → new CST connection → real CST evaluation → SUCCESS.
3. No orphan DE after run.
4. No manual `taskkill` required.
5. Only `cstd.exe` licensing service remains.

### Risks

- Inducing a real COM disconnect is disruptive and may leave orphan DEs if not handled.
- The synthetic COM_LOST approach (second injection in the retry adapter) is safer but still requires the CST DE to survive the first real evaluation before the synthetic failure is returned.
- A safer approach: use the existing synthetic initial failure hook for the first failure, then let the retry adapter return the real CST result on the second attempt. This validates the recovery callback path at tier 2 without needing an actual COM loss.

---

## Non-goals

| Capability | Not in scope | Notes |
|------------|-------------|-------|
| Durable evaluation DB | ❌ | Separate track |
| DB-backed success reuse | ❌ | Separate track |
| DB warm-start | ❌ | Separate track |
| Failure reuse | ❌ | Separate track |
| probably-infeasible skip | ❌ | Rejected at runtime |
| Full production campaign | ❌ | Bounded single-eval only |
| Broad chaos testing | ❌ | Controlled recovery only |
| Real COM disconnect validation | ❌ | Unless operator explicitly approves live COM fault |

---

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Recovery callback leaves orphan DE | Medium | High — accumulates windows | P3 `close_all(force)` pattern; `verify_process_cleanup`; tracked connections |
| Recovery callback fails silently | Low | Medium — evaluation retried on stale DE | Exception caught, logged, retry continues; max_tier bound |
| Double retry with legacy handler | Low (mutex) | High — unpredictable behaviour | `check_legacy_retry_mutex()` disables new runtime; fail-fast diagnostic |
| Adapter creates hidden recovery | Low (design) | High — double recovery path | API removed in RW2.1; no `recovery_callback` param exists on `make_cst_retry_evaluate_once` |
| `cstd.exe` accidentally killed | Low | High — license lost | `CST_PROCESS_WHITELIST`; targeted PID kill in recovery callback |

### Acceptance criteria for RCR3

1. All RCR2 no-CST tests pass.
2. Live CST smoke completes: synthetic initial failure → tier 1 retry → (optionally tier 2 recovery) → SUCCESS.
3. No orphan DE after run.
4. No manual `taskkill` required.
5. Only `cstd.exe` licensing service remains.
6. Checkpoint contains exactly 1 entry (final result only).
7. Log contains clear recovery diagnostic messages.
8. No changes to default `config.yaml`.

---

## Summary

This document defines the design and planning for wiring real COM recovery into the retry runtime. The key difference from RW3 is the **recovery callback** — RW3 used `recovery_callback=None`; RCR2 will provide a callback that closes the old connection, creates a new one, and tracks it for cleanup. No adapter-level recovery. No silent double retry. No orphan DE risk beyond what P3 hardening already mitigates.

Next actionable phase: **RCR2** — implement the recovery callback with full no-CST test coverage.
