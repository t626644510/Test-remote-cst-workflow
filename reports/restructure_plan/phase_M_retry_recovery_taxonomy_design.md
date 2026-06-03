# Phase M — Retry / recovery taxonomy design

## Base commit

``195883c3376fd7d4bd2f8a7ca393c68e0115e48a``

## Scope

Design document only.  No runtime code, no durable DB, no retry/recovery
implementation, no live CST, no root shim repoint.

---

## 1. Accepted context summary (through L1)

| Area | Status |
|------|--------|
| Phase C JSONL sidecar | Diagnostic-only, opt-in, default disabled. **Not** a recovery/warm-start source. |
| Phase J evaluation database schema | Schema/dataclass/DDL only. No durable DB. |
| Phase K dedup helpers | In-memory only. Failure reuse deferred. |
| Phase L/L1 warm-start/prior | In-memory only. Success-only eligibility. Diagnostic-only ignored. Provenance not blocking. |
| Phase D Ctrl+C cleanup | Normal cleanup validated. Hard-exit live validation blocked by non-interactive environment. |
| Stage/adaptive helpers (F–I) | No-CST helpers + opt-in runtime wiring. Disabled by default. |
| Root shim | Unrepointed. Deferred until after staged/adaptive/retry/database stable. |

### Failure reuse policy (current, from Phase E design)

| Outcome | Reuse for warm-start? | Retry? | Classification |
|---------|----------------------|--------|----------------|
| SUCCESS, finite metrics | ✅ Yes (L phase) | N/A | ``usable_success`` |
| Gate rejected | ❌ No | N/A | ``ignored_failure`` |
| Calibration failed | ❌ No | ✅ Yes (future N) | ``ignored_failure`` |
| Solver failed | ❌ No | ✅ Yes (future N) | ``ignored_failure`` |
| Transient failed | ❌ No | ✅ Yes (future N) | ``ignored_failure`` |
| Unknown failed | ❌ No | ⚠️ TBD | ``ignored_failure`` |
| Diagnostic-only | ❌ No | N/A | ``ignored_diagnostic_only`` |

---

## 2. Failure taxonomy

### Status categories (from ``StageCandidateStatus`` and ``EvaluationDatabaseStatus``)

| Status | Category | Eligible for warm-start? | Retryable? |
|--------|----------|--------------------------|------------|
| ``completed`` / ``success`` | Success | ✅ Yes | N/A |
| ``gate_rejected`` | Gate rejection | ❌ No | **No** — measurement produced valid data but gates failed. Retrying should use same raw data. |
| ``calibration_failed`` | Calibration failure | ❌ No | ✅ Yes — transient, may succeed after retry |
| ``solver_failed`` | Solver failure | ❌ No | ✅ Yes — may be mesh/COM/stagnation |
| ``transient_failed`` | Transient failure | ❌ No | ✅ Yes — by definition retryable |
| ``unknown_failed`` | Unknown failure | ❌ No | ⚠️ Best-effort retry |
| ``database_reused`` | Accounting only | — | — |
| ``diagnostic_only`` | Explicit marker | ❌ No | N/A |

### Failure classes

1. **Transient failures** — expected to be retryable:
   - COM loss / connection interruption
   - Solver timeout / stagnation
   - Intermittent mesh error
   - File I/O race condition
   - **Policy:** retry up to tier limit. No permanent classification from a single occurrence.

2. **Persistent failures** — may recur but are not structurally infeasible:
   - Calibration fails consistently in a parameter region (high fail rate → stage search recenters)
   - Solver converges poorly in a region (may be real physics, not a bug)
   - **Policy:** track per-parameter-region failure rate. Stage search handles this via feasibility-aware recenter/shift (Phase F). Retry individually but don't skip region.

3. **Permanent failures** — should only be classified after explicit threshold rules:
   - Calibration or solver fails on *every* retry tier for the same parameter set
   - Clear error taxonomy indicates infeasibility (e.g. zero-volume geometry after parameter update)
   - **Policy:** not implemented in M/N. A future error taxonomy + retry threshold may mark these as ``probably_infeasible``. A single failure never qualifies.

### Gate rejection semantics

Gate rejection is **not a solver failure.** The solver produced valid
raw data.  The candidate was rejected because gate constraints were not
satisfied.  Gate-rejected records:
- Are **not** warm-start priors (the raw data may not satisfy current
  gate configuration).
- Should **not** be retried automatically (same parameters → same gate result).
- Can be useful for stage search feasibility tracking (gate reject rate
  triggers recenter/shift, not blind shrink).

---

## 3. Recovery mechanism separation

| Mechanism | Scope | Current rfgun_sao status |
|-----------|-------|--------------------------|
| **Tier retry** | Re-run a failed evaluation (solver/mesh/COM) through multiple escalation tiers. Associated with ``EvaluationRetryHandler``. | ⚠️ ``EvaluationRetryHandler`` is wired in the single-pass path only. Two-pass path does not use it. |
| **Inter-pass recovery** | Recovery between calibration and measurement passes within a single two-pass evaluation. | ⚠️ ``inter_pass_recovery`` config key exists, warn-and-ignore in two-pass CST path. |
| **Post-eval recovery** | Graceful reset after each evaluation to prevent solver state bleed into the next evaluation. | ⚠️ ``post_eval_recovery`` config key exists (``tier2``), wired in single-pass path only. |
| **Ctrl+C cleanup** | Best-effort connection cleanup before hard exit. | ✅ Phase D. Normal cleanup validated live. |

### Design rules

1. **Tier retry** is about recovery from transient/permanent failure.
   Each tier has a different escalation level (reconnect → rebuild → force).
   - Tier 1: reconnect COM → re-run solver
   - Tier 2: full parameter rebuild → re-run solver
   - Tier 3: force-close project → re-open → re-run solver
   - Parameters sets should NOT be permanently skipped after a single tier-3 failure.
   - Only after repeated tier-3 failures with the same error pattern may a
     ``probably_infeasible`` classification be considered (requires threshold
     design in a future phase).

2. **Inter-pass recovery** is about solver state after the calibration
   pass.  If the calibration solver succeeds but the measurement solver
   fails, the system should recover and retry rather than discarding the
   calibration result.

3. **Post-eval recovery** is about preventing solver state bleed into
   the next evaluation.  A forced reset ensures a clean solver state
   before the next candidate.

4. These three are **independent** mechanisms and should be configured
   separately.

---

## 4. Evaluation database interaction

| Record type | In dedup index? | Warm-start prior? | Retry eligible? |
|------------|----------------|-------------------|-----------------|
| SUCCESS + finite metrics | ✅ Yes | ✅ Yes | N/A |
| SUCCESS, no useful payload | ✅ Yes (if identity present) | ❌ No | N/A |
| Gate rejected | ✅ Yes (for accounting) | ❌ No | ❌ No (not a solver failure) |
| Calibration/solver/transient failed | ✅ Yes (for accounting) | ❌ No | ✅ Yes |
| Unknown failed | ✅ Yes (for accounting) | ❌ No | ⚠️ Best-effort |
| Diagnostic-only | ❌ No | ❌ No | N/A |
| Incompatible schema | ❌ No | ❌ No | N/A |

### Failure records in the database

- Failure records are stored with their status, error message, and retry
  count for diagnostic/reporting purposes.
- They are **not** warm-start priors.
- They are **not** dedup skips (the same parameter set may succeed after
  a retry).
- Repeated failure records may contribute to a future ``probably_infeasible``
  classification, but this requires explicit threshold rules (Phase N+).

---

## 5. Future API sketch (Phase N)

Suggested pure helper structure (not implemented in M):

```python
# workflows/rfgun_sao/retry_taxonomy.py (suggested Phase N)

class RetryEligibility(Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE_GATE_REJECTED = "ineligible_gate_rejected"
    INELIGIBLE_DIAGNOSTIC_ONLY = "ineligible_diagnostic_only"
    INELIGIBLE_ALREADY_MAX_TIERS = "ineligible_already_max_tiers"
    PERMANENT_INFEASIBLE = "permanent_infeasible"  # future only

def classify_retry_eligibility(
    record, max_tiers=3,
) -> RetryEligibility: ...

def suggest_next_tier(
    record, current_tier=0,
) -> int: ...

def should_escalate_to_permanent_infeasible(
    failure_history, threshold_config,
) -> bool: ...  # future only
```

No runtime wiring in Phase N.  No CST.  Disabled by default.

---

## 6. Future phase order

| Phase | Scope |
|-------|-------|
| **N** | Retry taxonomy no-CST helper skeleton — eligibility, tier suggestion, failure-record classification |
| **N1** (if needed) | Helper semantics hardening |
| **O** | Retry/inter-pass recovery runtime wiring — no-CST only, opt-in, disabled by default |
| **P** | Live CST smoke for retry/recovery (only when explicitly requested) |
| **Q+** | Production-scale validation, root shim repointing (last) |

---

## 7. Non-goals (explicit)

This design document does **not**:
- Implement any runtime code.
- Implement retry/recovery.
- Implement durable evaluation database.
- Implement failure reuse.
- Implement ``probably_infeasible`` classification.
- Read Phase C JSONL sidecar as recovery/warm-start source.
- Import ``cst_optimization.factory`` or ``cst_optimization.workflows.recovery``.
- Copy legacy ``RecoveryWorkflowEvaluator``.
- Run live CST.
- Repoint root shim.
- Change default config to enable retry, database, or live CST.
