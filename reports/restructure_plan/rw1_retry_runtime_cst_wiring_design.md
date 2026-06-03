# RW1 — Retry runtime CST wiring design / adapter plan

## Metadata

| Field | Value |
|-------|-------|
| Base branch | `feature/wf1-retry-runtime-cst-wiring` |
| Base commit (from consolidation closeout) | `c58b40a2b09ef2aac10a021618d7503f7ad341d6` |
| Phase label | `RW1 — Retry runtime CST wiring design / adapter plan` |
| Nature | **Docs-only design** — no runtime code changed, no live CST |
| Previous track | Consolidation closeout at Phase V (`refactor/wf1-sao-consolidation`) |

---

## Current retry runtime no-CST skeleton summary

The existing `workflows/rfgun_sao/retry_runtime.py` provides:

| Component | Description |
|-----------|-------------|
| `RetryRuntimeConfig` | Dataclass with `enabled=False`, `max_tier=3`, `allow_unknown_retry=True`, `allow_gate_retry=False`, inter-pass/post-eval recovery flags, `use_probably_infeasible_for_skip=False` |
| `resolve_retry_runtime_config()` | Config parser; accepts nested `{"retry": ...}` or flat shape; defaults disabled |
| `should_use_retry_runtime()` | Returns `config.enabled` |
| `RetryAttemptRecord` | One retry attempt: index, tier, status before/after, recovery info, error, diagnostics |
| `RetryRuntimeResult` | Loop result: final_status, attempts list, retry_count_consumed, succeeded, stopped_reason, diagnostics |
| `_normalize_retry_record()` | Ensures retry_count monotonically advances; prevents infinite loops from misbehaving callbacks |
| `run_retry_loop_no_cst()` | Main retry loop: injectable `evaluate_once(tier, record) -> EvaluationDatabaseRecord`, injectable `recovery_callback(tier, record) -> bool`, uses `classify_retry_eligibility()` for retry decisions, bounded by `attempts_consumed >= max_tier`, no file I/O, no CST |
| `run_inter_pass_recovery_no_cst()` | Callback-only inter-pass recovery skeleton |
| `run_post_eval_recovery_no_cst()` | Callback-only post-eval recovery skeleton |

### Taxonomy support (`retry_taxonomy.py`)

| Component | Description |
|-----------|-------------|
| `classify_failure_record()` | Maps `EvaluationDatabaseRecord` to `RetryFailureClass` (SUCCESS, GATE_REJECTED, CALIBRATION_FAILED, SOLVER_FAILED, TRANSIENT_FAILED, UNKNOWN_FAILED, DIAGNOSTIC_ONLY, INCOMPATIBLE_SCHEMA, etc.) |
| `classify_retry_eligibility()` | Returns `RetryEligibilityAction` (RETRY_ELIGIBLE, NO_RETRY_SUCCESS, NO_RETRY_GATE_REJECTED, NO_RETRY_MAX_TIERS_REACHED, etc.) |
| `RetryPolicy` | Controls `max_tier`, `allow_unknown_retry`, `allow_gate_retry`, `enable_permanent_infeasible` |

---

## Current legacy CST retry / cleanup interaction summary

The existing `cst_optimization.core.retry.EvaluationRetryHandler` handles retries at a **different layer** — it wraps `evaluate_single_pass` and retries on `COM_LOST` / `SOLVER_FAILED` by escalating through tier 1 (same connection), tier 2 (kill + reconnect), tier 3 (kill + clean result folder + reconnect).

Key interactions with the new retry runtime:

| Aspect | Legacy `EvaluationRetryHandler` | New `retry_runtime.py` |
|--------|-------------------------------|----------------------|
| Scope | Wraps a single evaluation call | Wraps the evaluation + retry loop |
| Config | `optimization.retry.*` in config | New `retry_runtime.*` config section |
| Disabled by default? | Yes (via config, `enabled: false` in default config.yaml) | Yes (`enabled=False` in dataclass) |
| Progress guard | Inherits `close()` hang → orphan DE (pre-P3) | `attempts_consumed` counter (P3 handles orphan) |
| Cleanup interaction | Was cause of orphan DE; P3 `close_all()` now handles it | Must use same `close_all()` pattern |

**Important**: The legacy `EvaluationRetryHandler` operates WITHIN a single evaluation. The new `retry_runtime.run_retry_loop_no_cst()` operates AT the evaluation level — it evaluates, classifies, and potentially re-evaluates. These are complementary, not conflicting. The legacy handler may fire during an evaluation attempt within the retry loop.

---

## CST status / error path → retry taxonomy mapping

The `Workflow1Evaluator.evaluate_single_pass()` returns `EvaluationStatus`:

| Legacy Status | Condition | Maps to `EvaluationDatabaseStatus` | Retry eligible? |
|---------------|-----------|-------------------------------------|-----------------|
| `SUCCESS` | Solver OK, all physics computed | `SUCCESS` | No (done) |
| `COM_LOST` | COM/connection error caught in exception handler | `TRANSIENT_FAILED` or `SOLVER_FAILED` | Yes |
| `SOLVER_FAILED` | Solver completed but result not usable | `SOLVER_FAILED` | Yes |

For `adapt_for_retry` (legacy adapter), the status is returned as `EvaluationResult.status`. The new CST adapter must bridge this to `EvaluationDatabaseRecord`:

```python
def _cst_status_to_database_status(eval_status) -> str:
    """Map legacy EvaluationStatus to EvaluationDatabaseStatus string."""
    if eval_status == _ES.SUCCESS:
        return EvaluationDatabaseStatus.SUCCESS
    elif eval_status == _ES.COM_LOST:
        # COM loss is transient — encourage retry
        return EvaluationDatabaseStatus.TRANSIENT_FAILED
    elif eval_status == _ES.SOLVER_FAILED:
        return EvaluationDatabaseStatus.SOLVER_FAILED
    else:
        return EvaluationDatabaseStatus.UNKNOWN_FAILED
```

The calibration path (two-pass mode) would map differently:
| Calibration result | `EvaluationDatabaseStatus` |
|-------------------|---------------------------|
| Calibration success, f0 found, within gate | `SUCCESS` → calibration accepted |
| Calibration fail (no resonance) | `CALIBRATION_FAILED` |
| Gate reject (frequency out of range / S11 too shallow) | `GATE_REJECTED` |

---

## Proposed insertion points

### 1. New module: `workflows/rfgun_sao/retry_runtime_cst.py`

A new CST adapter module that provides:

```python
def make_cst_retry_evaluate_once(
    evaluator: Workflow1Evaluator,
    config: RetryRuntimeConfig,
    project_path: str,
    *,
    recovery_callback: Callable | None = None,
) -> Callable[[int, EvaluationDatabaseRecord], EvaluationDatabaseRecord]:
    """Create a CST-backed evaluate_once callback for run_retry_loop_no_cst.
    
    The returned callback:
    1. Converts EvaluationDatabaseRecord → parameter vector for the evaluator.
    2. Calls evaluator.evaluate_single_pass() → gets (raw, pen, ok, status, error).
    3. Maps EvaluationStatus → EvaluationDatabaseStatus.
    4. Builds and returns an EvaluationDatabaseRecord with the result.
    
    On COM_LOST or connection error, calls recovery_callback before returning
    the failure record, so the retry loop can decide to retry with a fresh
    connection.
    
    No-CST testable: inject a mock evaluator that returns controlled statuses.
    """
```

### 2. Config shape

New config section in `workflows/rfgun_sao/config.yaml`:

```yaml
retry_runtime:
  enabled: false          # master switch; false = no retry loop
  max_tier: 3             # same meaning as RetryRuntimeConfig
  allow_unknown_retry: true
  allow_gate_retry: false
  inter_pass_recovery:
    enabled: false
  post_eval_recovery:
    enabled: false
  use_probably_infeasible_for_skip: false  # rejected in runtime
```

Configuration resolution should merge `retry_runtime.*` into an `RetryRuntimeConfig` instance. The existing `resolve_retry_runtime_config()` uses the key `"retry"` for nested lookup. This can be adapted to also accept `"retry_runtime"`.

### 3. Workflow integration point (`workflows/rfgun_sao/workflow.py`)

In the `build_workflow_1()` function, after the evaluator is constructed:

```python
# Resolve retry runtime config
retry_runtime_cfg = resolve_retry_runtime_config(
    config.get("retry_runtime", None)
)
if should_use_retry_runtime(retry_runtime_cfg):
    cst_evaluate_once = make_cst_retry_evaluate_once(
        evaluator=wf1_evaluator,
        config=retry_runtime_cfg,
        project_path=project_path,
        recovery_callback=_cst_recovery_callback,
    )
    # Wrap the SAO evaluator to use retry loop
    _make_retry_runtime_evaluator(
        wf1_evaluator, cst_evaluate_once, retry_runtime_cfg,
    )
```

Where `_make_retry_runtime_evaluator` creates the `evaluate(x_phys, iteration) -> float` closure that `build_workflow_1` returns to the optimizer:

```python
def _make_retry_runtime_evaluator(wf1_evaluator, cst_evaluate_once, config):
    """Wrap the SAO evaluator to run evaluations through the retry loop."""
    def evaluate(x_phys, iteration):
        param_dict = dict(zip(param_names, x_phys))
        
        # Initial evaluation via evaluate_single_pass
        raw, pen, ok, status, err = wf1_evaluator.evaluate_single_pass(
            param_dict, iteration,
        )
        
        # Build initial record
        initial_record = _build_record_from_result(
            param_dict, raw, pen, ok, status, err,
        )
        
        # Run retry loop if initial attempt failed
        if initial_record.status != EvaluationDatabaseStatus.SUCCESS:
            result = run_retry_loop_no_cst(
                initial_record=initial_record,
                evaluate_once=cst_evaluate_once,
                config=config,
                recovery_callback=_recovery_callback,
            )
            # Use final record for penalty computation
            if result.succeeded:
                # Extract metrics from final successful record
                ...
                return float(np.dot(penalties_arr, weights))
        
        # Normal path (single attempt or retry loop exhausted)
        penalties = compute_role_penalties(...)
        return float(np.dot(penalties_arr, weights))
    
    return evaluate
```

### 4. Recovery callback

For CST-backed recovery (connection loss, need to reconnect):

```python
def _cst_recovery_callback(tier: int, record: EvaluationDatabaseRecord) -> bool:
    """Recovery callback for CST retry: close connection and reconnect.
    
    Leverages P3 cleanup hardening:
    - retry_handler.close_all(force=True) closes ALL tracked connections,
      including replacement DEs created by legacy force_reset().
    - After close_all, a new CSTConnection is created.
    - The evaluator's on_reconnect() updates its internal _conn reference.
    
    Returns True if reconnection succeeded.
    """
    if tier >= 2:
        # Force-close all connections, then reconnect fresh
        try:
            close_all_connections(force=True)
            new_conn = CSTConnection(library_path, mode="new")
            new_conn.connect()
            wf1_evaluator.on_reconnect(new_conn)
            _logger.info("Retry runtime: reconnected to new CST DE, PID=%s", new_conn.pid)
            return True
        except Exception as exc:
            _logger.warning("Retry runtime recovery failed: %s", str(exc)[:200])
            return False
    return True  # tier 1: no recovery needed
```

---

## Inter-pass recovery vs post-eval recovery vs tier retry

The Phase M retry/recovery design separates three mechanisms:

| Mechanism | When | What it does | Current status |
|-----------|------|-------------|----------------|
| **Tier retry** | After a failed evaluation within the retry loop | Re-evaluate with same or new CST connection | Phase O/O1 skeleton exists; CST wiring = this track |
| **Inter-pass recovery** | Between calibration and measurement in two-pass mode | If calibration fails, attempt recovery before proceeding to measurement | Callback-only skeleton in `retry_runtime.py` |
| **Post-eval recovery** | After a single evaluation completes | Graceful reset (close + clean + reconnect) for next evaluation | Already handled by legacy `force_reset()` in `workflow.py` |

### Design for RW2+ implementation

**Tier retry** (primary focus): 
- `run_retry_loop_no_cst()` with CST-backed `evaluate_once` callback.
- Evaluation failure → classify → retry eligible → recovery callback + re-evaluate.
- `max_tier` controls number of retry attempts.
- Recovery callback at tier 2+ closes all connections via `close_all()` and creates a fresh `CSTConnection`.

**Inter-pass recovery**: 
- Only relevant for two-pass mode (calibration → measurement).
- Skeleton exists; needs CST wiring if two-pass is enabled.
- Low priority; two-pass mode is disabled by default.

**Post-eval recovery**: 
- Already handled by legacy `retry_handler.force_reset()`.
- P3 hardening already ensures `close_all()` terminates replacement DEs.
- The new retry runtime does NOT need to duplicate this — it runs its own recovery inside the retry loop as needed.

---

## Adapter design for fake/no-CST tests

The new `retry_runtime_cst.py` module must be **fully testable without CST**.

```python
# Fake evaluator for tests
class FakeCstEvaluator:
    def __init__(self, results: list[EvaluationResult]):
        self._results = results
        self._call_count = 0
    
    def evaluate_single_pass(self, param_dict, iteration):
        result = self._results[self._call_count % len(self._results)]
        self._call_count += 1
        # Map from EvaluationResult's fields
        return (result.raw_metrics or {}, result.penalty_values or {},
                result.status == _ES.SUCCESS, result.status, result.error)
    
    def on_reconnect(self, new_conn):
        pass

# Test: single retry on COM_LOST
fake = FakeCstEvaluator([
    EvaluationResult(status=_ES.COM_LOST, error="COM lost"),
    EvaluationResult(status=_ES.SUCCESS, error=""),
])
callback = make_cst_retry_evaluate_once(fake, RetryRuntimeConfig(enabled=True))
initial = EvaluationDatabaseRecord(
    parameter_identity=pid, status="solver_failed", retry_count=0,
)
result = run_retry_loop_no_cst(initial, callback, config=RetryRuntimeConfig(enabled=True))
assert result.succeeded is True
assert len(result.attempts) == 1
```

Test scenarios for RW2:
1. SUCCESS on first attempt → no retry.
2. SOLVER_FAILED → retry eligible → retry → SUCCESS.
3. COM_LOST → retry eligible → retry → SUCCESS.
4. Repeated SOLVER_FAILED → max_tier exhausted → terminal failure result returned; optimizer receives failure penalty (all-ones).
5. GATE_REJECTED → not retried by default; gate rejection result returned to optimizer.
6. Recovery callback called on tier 2+ retry.
7. Recovery callback failure → retry still attempted.
8. `use_probably_infeasible_for_skip=True` rejected at runtime.

---

## Checkpoint / log / reporting semantics for retry attempts

Each retry attempt within the loop should produce:

1. **Log messages**: 
   - `"Retry runtime: attempt N at tier T (previous status: X)"`
   - `"Retry runtime: attempt N succeeded (final status: SUCCESS)"`
   - `"Retry runtime: attempt N failed (status: Y); max_tier reached, returning failure penalty"`

2. **Diagnostics on `RetryRuntimeResult`**:
   - `attempts` list with per-attempt details (tier, status_before, status_after, recovered, error).
   - `diagnostics["progress_guard_activations"]` if normalisation fires.
   - `diagnostics["retry_count_consumed"]` reflecting total attempts.

3. **Checkpoint interaction**: The checkpoint records only the final evaluation result — i.e. the one that the optimizer actually uses for its surrogate model. Intermediate retry attempts must NOT create checkpoint entries.

   The policy:
   - The initial evaluation call from the optimizer produces a result (possibly failed).
   - If the retry loop succeeds on a later attempt, the checkpoint records that successful result (penalties, raw_metrics, solver_ok=True).
   - If the retry loop exhausts `max_tier`, the checkpoint records the last-failure penalty (all-ones or computed from last available metrics) with `solver_ok=False`.
   - Intermediate retry attempts appear only in:
     - runtime log messages
     - `RetryRuntimeResult.attempts` diagnostics
     - optional JSONL sidecar entries (see JSONL note below)
   - The checkpoint must not contain duplicate or intermediate entries that would confuse the optimizer's warm-start.

4. **JSONL sidecar**: If JSONL is enabled, each retry attempt produces a separate JSONL entry for the same `(x_phys, iteration)`. The iteration counter alone is insufficient to distinguish retry attempts. Each retry-attempt JSONL entry must include explicit retry diagnostics:
   - `retry_attempt_index`: 0-based index within the retry loop.
   - `retry_tier`: tier at which this attempt ran.
   - `status_before`: status that triggered the retry.
   - `status_after`: status returned by this attempt.
   - `same_parameter_identity`: `true` (same x_phys is being re-evaluated).
   - `recovery_label`: whether recovery was attempted and its outcome.

   Without these fields, JSONL consumers cannot distinguish an initial evaluation from a retry attempt. The JSONL record writer (`records.py` / `_record_jsonl_sidecar_evaluation`) must be extended to accept and include these retry diagnostics when present.

   This is acceptable because JSONL is diagnostic-only and not an authoritative recovery source.

---

## Cleanup / orphan-DE risk assessment

### Dependency on P3 `close_all(force)`

The P3 hardening (`retry_handler.close_all(force)` in `_cleanup_workflow_connection`) ensures that ALL tracked CST connections are terminated when the workflow closes. This is the safety net for any retry that creates new connections.

However, the retry loop operates **within** a workflow's evaluation, before the final cleanup runs. If a retry opens a new CST connection (via recovery callback at tier 2+), that new connection is tracked in `retry_handler._all_connections` (legacy) or must be tracked in a new connection registry.

### Orphan DE risk during retry loop

Risk is **mitigated** by P3 `close_all(force)`, but **not eliminated**. RW3 live smoke is required before accepting any runtime CST retry wiring.

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Retry at tier 1 (same connection) | Low — no new connection created | N/A |
| Retry at tier 2+ (new connection via recovery callback) | Medium — new DE created before old one fully dies | Recovery callback must call `close_all()` before creating new connection [P3 pattern]; final workflow cleanup calls `close_all()` again as safety net |
| Retry loop interrupted (Ctrl+C) | Low — P3 `_cleanup_workflow_connection` still runs in finally block | No additional risk beyond normal Ctrl+C |
| Legacy `EvaluationRetryHandler` fires during retry attempt (if both enabled — not recommended) | Medium — legacy handler's `force_reset()` may create additional DEs | P3 hardening already mitigates; legacy handler's new DE is tracked in `retry_handler._all_connections` |

**RW3 dependency**: The orphan-DE mitigation must be explicitly verified by a live CST smoke that exercises a retry path (engineered failure → retry → success) and confirms no orphan DE remains after the run. Without this evidence, the cleanup claim is a design assumption, not validated behaviour.

### Recommended approach

```python
def _retry_recovery_close_and_reopen(tier, record):
    """Recovery callback for retry runtime: close all, reopen."""
    if tier >= 2:
        # Close ALL tracked connections (including legacy handler's)
        if retry_handler is not None:
            retry_handler.close_all(force=True)
        # Open new connection
        new_conn = CSTConnection(library_path, mode="new")
        new_conn.connect()
        new_conn.set_quiet_mode(True)
        # Update evaluator reference
        wf1_evaluator.on_reconnect(new_conn)
        # Track in legacy handler's connection list (for final cleanup)
        if retry_handler is not None:
            retry_handler._all_connections.append(new_conn)
        return True
    return True  # tier 1: no action needed
```

---

## Config shape (detailed)

```yaml
retry_runtime:
  enabled: false
  max_tier: 3
  allow_unknown_retry: true
  allow_gate_retry: false
  inter_pass_recovery:
    enabled: false
  post_eval_recovery:
    enabled: false
  use_probably_infeasible_for_skip: false
```

The `resolve_retry_runtime_config()` function already supports the flat shape `{"enabled": True, ...}`. The nested `retry_runtime` key in config is mapped:

```python
# config.yaml
retry_runtime:
  enabled: true
  max_tier: 3

# resolve step:
raw = config_dict.get("retry_runtime", config_dict)  # accept nested key
cfg = resolve_retry_runtime_config({"retry": raw})    # reuse existing resolver
```

Or the resolver can be extended to also recognize `"retry_runtime"` as a valid root key. Either approach preserves the core resolver unchanged.

---

## Legacy retry nesting / mutex strategy

The existing config has `optimization.retry.*` which controls the legacy `EvaluationRetryHandler`. The new retry runtime has `retry_runtime.*`. If both are enabled simultaneously, a single evaluation could be retried TWICE — once by the legacy handler at the evaluation-call level, and once by the new retry runtime at the evaluation-result level.

### Default strategy (RW2)

**Fail-fast**: If `optimization.retry.enabled` is `True`, the new retry runtime must refuse to enable itself with a clear warning:

```python
if config.get("optimization", {}).get("retry", {}).get("enabled", False):
    _logger.warning(
        "retry_runtime.enabled is True but legacy optimization.retry.enabled is also True. "
        "Disabling retry_runtime to avoid double retry. "
        "Set optimization.retry.enabled=false to use retry_runtime."
    )
    retry_runtime_cfg = RetryRuntimeConfig()  # disabled
```

This avoids silent double-retry without requiring the user to discover the conflict.

### Future nesting (separate phase, if ever pursued)

If a future phase wants to allow both retry mechanisms to coexist (e.g., legacy handler for COM-level retries at tier 1, new runtime for taxonomy-driven retries at tier 2+), the following must be explicitly designed and live-validated:

- Total max-attempt budget: `legacy_max_tiers + runtime_max_tier` must not silently multiply.
- Cleanup semantics: both mechanisms must share `close_all()` to avoid orphan DE accumulation.
- Diagnostics: clear audit trail distinguishing which mechanism fired at each attempt.
- Live smoke: must verify that double retry does not occur despite both being enabled.

This is explicitly **not planned for RW2–RW3**.

---

## Explicit non-goals for RW1–RW3

| Capability | Not in scope | Notes |
|------------|-------------|-------|
| Durable evaluation DB | ❌ | Separate track; this track uses in-memory records only |
| DB-backed success reuse | ❌ | Separate track |
| DB warm-start | ❌ | Separate track |
| Failure reuse / permanent skip | ❌ | Separate track; Phase N1 `probably_infeasible` remains advisory |
| probably-infeasible skip | ❌ | `use_probably_infeasible_for_skip=True` still rejected |
| Production-scale campaign | ❌ | Only single-eval retry smoke |
| Default config change | ❌ | Retry runtime remains disabled by default |
| Modifying legacy `EvaluationRetryHandler` | ❌ | Not touched; complementary, not replacement |
| Modifying `src/cst_optimization/` | ❌ | Out of scope |
| Modifying `workflows/rfgun_single_pass/` | ❌ | Frozen |

---

## Proposed next phases

| Phase | Scope | Live CST? |
|-------|-------|-----------|
| **RW2** | No-CST adapter implementation (`retry_runtime_cst.py` with fake evaluator tests) | No |
| **RW3** | Explicit live retry smoke (single engineered failure + retry) | Only if operator explicitly approves |
| RW4+ | Inter-pass/post-eval recovery CST wiring (lower priority) | TBD |

---

## Summary

This document defines the design for wiring the Phase O/O1 retry runtime into the CST evaluation pipeline. The key elements are:

1. **New adapter module** `retry_runtime_cst.py` with `make_cst_retry_evaluate_once()`.
2. **Status mapping** from legacy `EvaluationStatus` → `EvaluationDatabaseStatus` for taxonomy consumption.
3. **Recovery callback** leveraging P3 `close_all()` for safe CST reconnection.
4. **No-CST testable** with `FakeCstEvaluator`.
5. **Disabled by default** — no config default changes.
6. **Orphan-DE risk mitigated by P3 `close_all(force)`, but RW3 live smoke required** before accepting runtime CST wiring.

Next actionable phase: **RW2** — implement the adapter with full no-CST test coverage.

---

## RW1.1 correction note

This section documents the changes made in RW1.1 (docs-only semantics correction).

| Item | What changed |
|------|-------------|
| Nature | Docs-only — no runtime code changed, no config changed, no live CST, no generated artifacts committed |
| 1. Checkpoint semantics | Clarified that checkpoint records only the optimizer-used final result; intermediate retry attempts never create checkpoint entries |
| 2. Legacy retry mutex | Added explicit "fail-fast" strategy: new retry runtime refuses to enable if legacy `optimization.retry.enabled` is True; future nesting would require separate phase |
| 3. "Skipped" wording | Replaced "evaluation skipped" with "terminal failure result returned; optimizer receives failure penalty" throughout; removed language implying permanent skip |
| 4. JSONL diagnostics | Removed "iteration counter alone distinguishes attempts"; added explicit required fields: `retry_attempt_index`, `retry_tier`, `status_before`, `status_after`, `same_parameter_identity`, `recovery_label` |
| 5. Orphan-DE claim | Changed from "no new orphan DE risk" to "risk mitigated by P3 `close_all(force)`, but RW3 live smoke required before accepting runtime CST wiring" |
| 6. This section | Added RW1.1 correction note |

Validation:

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
→ Compiles OK.

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short  → 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short → 12 passed
Total: 242 passed, 1 pre-existing warning.
```

No source files were modified. The document on this branch includes all corrections from RW1.1.

Final HEAD SHA: **to be confirmed by reviewer**.
