# RCR2 — Retry-runtime recovery callback + dedicated registry no-CST implementation

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `48eea9619c85ad7f81b0f6f1cfbfb63bf8a37315` |
| Phase label | `RCR2 — Retry-runtime recovery callback + dedicated registry` |
| Branch | `feature/wf1-real-com-recovery` |
| Live CST | **No** — pure no-CST implementation |
| Real COM disconnect | **Not validated** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/retry_runtime_cst.py` | **Modified** | Added `CstConnectionRegistry` dataclass and `make_cst_recovery_callback()` factory |
| `workflows/rfgun_sao/workflow.py` | **Modified** | Creates registry + recovery callback when retry_runtime enabled; stores registry on workflow |
| `workflows/rfgun_sao/run.py` | **Modified** | `_cleanup_workflow_connection` closes `workflow._retry_connection_registry` |
| `tests/workflows/test_rfgun_sao_retry_runtime_recovery.py` | **Added** | 20 no-CST tests for registry, callback, integration, safety |
| `reports/restructure_plan/rcr2_retry_runtime_recovery_no_cst_report.md` | **Added** | This report |

---

## Implementation summary

### CstConnectionRegistry

Added to `retry_runtime_cst.py`. Pure no-CST dataclass:

| Method | Behaviour |
|--------|-----------|
| `track(conn)` | Adds connection to internal list |
| `tracked_count` | Returns current list length |
| `close_all(force=True)` | Iterates all connections, calls `close(force)` on each; collects errors; clears list. Returns diagnostic dict with `attempted`, `closed_ok`, `errors` |

Key design:
- No CST imports at module level — connections are duck-typed.
- `close_all` continues after individual connection close errors.
- Registry is cleared after close attempts regardless of errors.
- Works independently of legacy `retry_handler`.

### make_cst_recovery_callback()

Factory function in `retry_runtime_cst.py`:

| Input | Source |
|-------|--------|
| `connection_factory` | Injected zero-arg callable (creates new CST connection) |
| `evaluator` | Duck-typed `Workflow1Evaluator` (provides `on_reconnect`) |
| `registry` | `CstConnectionRegistry` instance |
| `logger` | Optional logger |

Behaviour by tier:

| Tier | Action | Returns |
|------|--------|---------|
| 1 | No-op (no factory call, no registry entry) | `True` |
| 2+ | `registry.close_all(force)`, `connection_factory()`, `evaluator.on_reconnect()`, `registry.track()` | `True` |
| Any exception | Caught, logged, no untracked connection | `False` |

Exception handling policy:
- If `connection_factory()` raises → exception caught, `False` returned, no new connection in registry.
- If `evaluator.on_reconnect()` raises → exception caught, `False` returned, new connection not tracked (track() not reached).
- No silent untracked connection.

### Workflow wiring

In `workflow.py` single_pass path:

1. When `retry_runtime` is enabled and legacy retry disabled:
   - `_retry_runtime_registry = CstConnectionRegistry()`
   - `_retry_runtime_recovery = make_cst_recovery_callback(factory, evaluator, registry, logger)`
   - `evaluator` closure passes `recovery_callback=_retry_runtime_recovery` to `run_retry_loop_no_cst`
   - `workflow._retry_connection_registry = _retry_runtime_registry`

2. Default behaviour unchanged when retry_runtime absent/disabled.
3. Legacy retry mutex behaviour unchanged.

### Cleanup integration

In `_cleanup_workflow_connection` (`run.py`):

```python
reg = getattr(workflow, "_retry_connection_registry", None)
if reg is not None:
    diag = reg.close_all(force=force)
```

Runs independently of legacy `retry_handler.close_all(force)`. Both may execute safely and idempotently.

---

## Test coverage (20 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestCstConnectionRegistry` | 4 | track and close_all, error continuation, empty registry, clear after close |
| `TestRecoveryCallbackUnit` | 5 | Tier 1 no-op (no factory), Tier 2 create+track, factory exception, on_reconnect exception, works without legacy handler |
| `TestEvaluateOnceRecoveryFree` | 1 | Adapter has no recovery_callback parameter |
| `TestRetryLoopWithRecovery` | 4 | Tier 1 no-op integration, Tier 2 invoked after first failure, recovery exception bounded, max_tier exhaustion bounded |
| `TestAdapterRecoveryAbsent` | 1 | Adapter API verified: no recovery parameter |
| `TestCleanupIntegration` | 2 | Registry close_all in cleanup path, None registry is no-op |
| `TestSafety` | 3 | No CST imports, no factory, no recovery import |

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py --tb=short -v
→ 20 passed

pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short → 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short → 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py --tb=short → 24 passed
pytest tests/workflows/test_rfgun_sao_retry_taxonomy.py --tb=short → 50 passed
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short → 12 passed

Total: 457 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | ❌ Not run |
| Real COM disconnect validated | ❌ Not validated |
| Default config changed | ❌ Not changed |
| `config.local.yaml` committed | ❌ Not committed |
| Generated artifacts committed | ❌ Not committed |
| Durable DB | ❌ Not implemented |
| Failure reuse | ❌ Not implemented |
| probably-infeasible skip | ❌ Rejected at runtime |
| Adapter-level recovery (`make_cst_retry_evaluate_once`) | ❌ No recovery parameter |
| Legacy retry handler dependency for registry | ❌ Registry works independently |

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
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `run_retry_loop_no_cst` | **Not modified** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | No | N/A |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## Commit message proposal

```
RCR2 rfgun_sao retry-runtime recovery callback + dedicated registry

- Add CstConnectionRegistry: track/close_all/best-effort error handling
- Add make_cst_recovery_callback: tier 1 no-op, tier 2+ reconnect via
  injected factory + evaluator.on_reconnect + registry.track
- Wire into workflow.py: registry + recovery_callback when retry_runtime
  enabled; stored on workflow for cleanup
- Cleanup in run.py: _cleanup_workflow_connection closes registry
- 20 no-CST tests: registry lifecycle, callback tiers, integration,
  adapter verified recovery-free, safety

No live CST, no real COM disconnect, no legacy handler dependency,
no default config change.
```
