# Phase E — Workflow3 capability migration design

## Base commit

``a688058066a1fe7cafefc87df76c163a495be63c``

## Scope

Design document only.  No runtime code, no live CST, no root shim repoint.

---

## 1. Legacy Workflow3 capability summary

The legacy ``cst_optimization.workflows.recovery`` module (Workflow 3, WF3)
provides:

| Capability | Description |
|------------|-------------|
| **Staged search** | Multi-stage SAO with fixed stage count (typically 2). Stage 1 broad exploration, Stage 2 focused refinement. Stage transition triggered by evaluation count. |
| **Adaptive bounds** | Parameter bound adjustment between stages. Prevents over-shrink and premature convergence. |
| **Metric roles** | ``optimize``, ``threshold``, ``report_only``, ``gate`` — now implemented in rfgun_sao (Phase B). |
| **Threshold penalty** | ``less_than`` / ``greater_than`` formula — now implemented in rfgun_sao (Phase B). |
| **Retry handler** | ``EvaluationRetryHandler`` with three-tier escalation (reconnect → full rebuild → final). Integrated with ``CSTConnection`` reconnect. |
| **Inter-pass recovery** | Recovery between calibration and measurement passes within two-pass evaluation. |
| **Post-eval recovery** | Graceful reset after each evaluation to prevent solver state bleed. |
| **Evaluation record** | JSONL sidecar with per-evaluation records (raw, penalty, metadata) used for **warm-start/prior loading**. |
| **Prior loading** | JSONL records from previous runs loaded as ``prior_data`` for SAO warm-start (same as ``CheckpointManager.get_warm_xy()``). |
| **Root shim** | ``run_workflow_{1,2,3}.py`` at repo root delegate to the corresponding workflow package. |
| **SAEA field extraction** | Separate SA (Simulated Annealing) path using field-level objectives (wakefield, antenna). |

---

## 2. New ``rfgun_sao`` capability summary

| Capability | Phase | Status |
|------------|-------|--------|
| Two-pass orchestration skeleton | A11–A12 | ✅ Accepted |
| CST runner adapters (HPBW/dip-min) | A13 | ✅ Accepted |
| Checkpoint hardening (persistence, metric names, invariants) | A19–A22 | ✅ Accepted |
| Injectable calibration/measurement runners | A12 | ✅ Accepted |
| Metric roles (optimize / threshold / report_only) | B1–B10 | ✅ Accepted |
| Threshold penalty formula + runtime wiring | B2–B3 | ✅ Accepted |
| Report-only diagnostics + ``EvaluationResult.diagnostics`` | B4 | ✅ Accepted |
| Gate role parsing + pass/fail helpers | B7 | ✅ Accepted |
| Gate runtime rejection (two-pass evaluator) | B8 | ✅ Accepted |
| JSONL diagnostic sidecar (opt-in, diagnostic-only) | C1–C3.5 | ✅ Accepted |
| Runner-level CST cleanup (finally) | B5.1 | ✅ Accepted |
| Ctrl+C hard-exit best-effort cleanup (second Ctrl+C) | D1 | ✅ Accepted |
| Normal cleanup live CST validation | D2 | ✅ Partial |
| Gate role live CST validation | B9 | ✅ Accepted |
| Role-based metrics live CST validation | B5 | ✅ Accepted |

---

## 3. Gap matrix

| WF3 capability | rfgun_sao status | Priority | Notes |
|----------------|------------------|----------|-------|
| Metric roles (optimize / threshold / report_only / gate) | ✅ Implemented (Phase B) | — | Gate runtime rejection live confirmed |
| Threshold penalty | ✅ Implemented (Phase B) | — | Matches legacy formula |
| Staged search | ❌ Not implemented | High | Phase F+ |
| Adaptive bounds | ❌ Not implemented | High | Phase G+ |
| Retry handler (3-tier) | ❌ Not implemented | High | Phase M–N |
| Inter-pass recovery | ❌ Not implemented | Medium | Phase N |
| Post-eval recovery | ⚠️ Partial | Medium | ``post_eval_recovery`` config key exists (``tier2``), wired in single-pass path only |
| JSONL evaluation records (for warm-start) | ⚠️ Different approach | — | rfgun_sao uses ``.ckpt`` / ``CheckpointManager`` for warm-start; JSONL sidecar is diagnostic-only |
| Prior loading from JSONL | ❌ Not implemented | Future | Planned as explicit ``EvaluationDatabase`` |
| SAEA field extraction | ❌ Not imported | Low | Phase 5 split intentionally excluded wakefield/antenna objectives |
| Root shim repointing | ❌ Deferred | Low | After staged/adaptive/retry/database stable |

---

## 4. Staged search design

**Do not copy legacy WF3 fixed-stage approach.**  Instead, design a
feasibility-aware multi-stage controller:

### Principles

1. **Stage = parameter-space region + optimization phase.**  A stage defines
   a parameter bound set, a candidate budget, and an acquisition strategy.
2. **Stage transition is triggered by feasibility heuristics**, not fixed
   evaluation counts:
   - High ``calibration_failed`` / ``solver_failed`` rate → recenter bounds,
     shift search region.
   - High gate reject rate → shrink bounds toward feasible region.
   - Low gate reject rate + convergence plateau → refine (narrow bounds).
3. **Feasibility tracking** accumulates per-parameter-region statistics:
   calibration success/fail, gate pass/fail, solver success/fail.
4. **Stage reports** distinguish:
   - ``proposed`` (optimizer requested)
   - ``reused`` (database hit)
   - ``solved`` (actual CST solve attempted)
   - ``retried`` (retry count per candidate)
   - ``completed`` (successful evaluation)
   - ``failed_calibration`` / ``failed_solver`` / ``rejected_gate``
5. **Candidate-level metadata** (iteration, status codes, region tags) flows
   through the evaluator and is recorded in the eventual evaluation database.

### Non-goals (Phase F)
- No runtime integration yet.
- No adaptive bounds interaction yet.
- No evaluation database yet.
- Pure helper functions + tests.

---

## 5. Adaptive bounds design

Adaptive bounds prevent staged search from over-shrinking and trapping the
optimizer in a local optimum.

### Principles

1. **Per-parameter adaptive range.**  Each parameter has a ``low``/``high``
   plus an adaptive buffer.
2. **Buffer adjustment** is based on:
   - Feasibility density: high fail rate → expand buffer.
   - Convergence: plateau in objective improvement → shrink buffer.
3. **Bounds composition:** final bound = ``[stage_nominal_low - buffer, stage_nominal_high + buffer]``,
   clamped to the config-level absolute min/max.
4. **Interaction with staged search:** the stage controller proposes nominal
   bounds; adaptive bounds adjust the effective search window.

### Non-goals (Phase G)
- No runtime integration yet.
- No staged search interaction yet.
- Pure helper functions + tests.

---

## 6. Retry / inter-pass / post-eval recovery distinction

| Concept | Scope | Current rfgun_sao status |
|---------|-------|--------------------------|
| **Retry** | Re-run a failed evaluation (solver/mesh/COM crash) through multiple escalation tiers. Associated with ``EvaluationRetryHandler``. | ⚠️ ``EvaluationRetryHandler`` from ``cst_optimization.core.retry`` is wired in the single-pass path only. The two-pass path does **not** use it. |
| **Inter-pass recovery** | Recovery between calibration and measurement passes within a single two-pass evaluation. Calibration succeeds but solver fails before measurement. Currently warn-and-ignore. | ⚠️ ``inter_pass_recovery`` config key exists, warn-and-ignore in two-pass CST path. |
| **Post-eval recovery** | Graceful reset (``force_reset``) after each evaluation to prevent solver state bleed into the next evaluation. | ⚠️ ``post_eval_recovery`` config key exists (``tier2``), wired in single-pass path only. |

### Design rules
1. Retry is about **recovery from transient failure** (COM loss, solver hang,
   mesh error).  Each tier has a different escalation level (reconnect → rebuild→force).
2. Inter-pass recovery is about **solver state after calibration pass** —
   if the measurement solver fails after a successful calibration, the
   system should recover and retry rather than discarding the calibration.
3. Post-eval recovery is about **preventing solver state bleed into the
   next evaluation** — a forced reset ensures a clean solver state.
4. These three are **independent** mechanisms and should be configured
   separately.

---

## 7. Evaluation database / raw-data resume design

### Motivation
The legacy WF3 JSONL records were used for warm-start (prior loading).
rfgun_sao currently uses ``CheckpointManager.get_warm_xy()`` for warm-start,
which is sufficient for current optimization.  However, as the system gains
staged search, adaptive bounds, and retry, a richer evaluation store becomes
necessary.

### Design

1. **Explicit ``EvaluationDatabase`` / ``RawEvaluationStore``.**
   - Separate concept from ``logging.evaluation_records`` (C-phase JSONL
     sidecar) and ``.ckpt`` (checkpoint).
   - Future new opt-in config section, e.g. ``evaluation.database``.
   - Stores raw computed data (objective raw values, parameter vector,
     solver status, gate results) as the canonical history.
   - The ``.ckpt`` / ``CheckpointManager`` continues to be the authoritative
     recovery source for the current run; the evaluation database is for
     cross-run resume and analysis.

2. **Reuse policies.**
   - **Success / raw data finite:** can be reused for warm-start, stage
     history, and meta-analysis.
   - **Calibration failure / solver failure / transient failures:** should be
     **retried**, not immediately skipped.  A single failure does not make a
     parameter point "infeasible."
   - **Repeated stable permanent failure:** after a defined error taxonomy +
     retry threshold, may be classified as ``probably_infeasible``.  This
     classification requires explicit taxonomy design (Phase M) and is not
     implemented in early phases.

3. **Provenance policy.**
   - Diagnostic metadata only by default: git commit, config fingerprint,
     CST version, machine hostname.
   - **Parameter match is the primary reuse key.**  Two evaluations with
     the same parameter vector (within tolerance) are considered the same
     point regardless of provenance differences.
   - Provenance differences are logged but do **not** block dedup.
   - If parameter schema changes (new parameter added, range changed),
     treat as new project; old data may still be usable if the parameter
     subset matches, but this is a future refinement.

4. **Budget accounting.**
   - Database reuse does **not** consume the CST solve budget.
   - Stage reports must distinguish:
     - optimizer proposed count
     - database reused count
     - actual CST solves count
     - retry attempts count
     - completed / failed / rejected breakdown

5. **Parallel / locking.**
   - Out of scope for initial design.
   - Reserve a small API hook (e.g., ``lock()`` / ``unlock()``) for future
     concurrent access, but do not implement.

6. **Relationship with JSONL sidecar.**
   - The C-phase JSONL sidecar (``logging.evaluation_records``) remains
     **diagnostic-only**.  It is not a recovery source.
   - The evaluation database is a future explicit opt-in concept and is
     **not** equivalent to the JSONL sidecar.

---

## 8. Budget accounting policy

- Each optimization run has a **solve budget** (``n_initial + n_iterations``).
- Database hits do not count toward the solve budget.
- Retry attempts do count toward the solve budget.
- Stage feasibility tracking uses a separate **feasibility observation count**
  which includes all attempted evaluations (including retries and rejects).
- Budget reporting is a cross-cutting concern across staged search, adaptive
  bounds, retry, and the evaluation database.

---

## 9. Root shim explanation

The "root shim" refers to the three files at the repository root:
``run_workflow_1.py``, ``run_workflow_2.py``, ``run_workflow_3.py``.
These delegate to the corresponding workflow packages (``workflows/rfgun_single_pass``,
``workflows/rfgun_double_pass``, ``workflows/rfgun_triple_pass`` in the legacy layout).

**Current status:**
- ``run_workflow_1.py`` still delegates to ``workflows.rfgun_single_pass.run``.
- During consolidation, ``rfgun_sao`` must be run explicitly via
  ``python -m workflows.rfgun_sao.run``.

**Why deferred:**
- Repointing ``run_workflow_1.py`` to ``rfgun_sao`` would make it the
  default entry point, which requires production-scale confidence in the
  consolidated package.
- Staged search, adaptive bounds, retry integration, and evaluation database
  should be stable before repointing.
- The explicit-runner requirement is a deliberate safety measure.

---

## 10. Failure reuse policy summary

| Outcome | Reuse for warm-start? | Retry? | Classification |
|---------|----------------------|--------|----------------|
| Solver OK, all metrics finite | ✅ Yes | N/A | ``completed`` |
| Solver OK, partial finite | ⚠️ Partial | N/A | ``partial`` |
| Calibration failed (first pass) | ❌ No | ✅ Yes (up to tier limit) | ``calibration_failed`` |
| Solver failed (COM/mesh/timeout) | ❌ No | ✅ Yes (up to tier limit) | ``solver_failed`` |
| Gate rejected (measurement OK) | ⚠️ Raw data finite | N/A | ``gate_rejected`` |
| Repeated permanent failure | ❌ No future reuse | ❌ No | ``probably_infeasible`` |

---

## 11. Provenance policy summary

| Data point | Use | Default action |
|------------|-----|----------------|
| Parameter vector | Primary dedup key | Match → reuse |
| Git commit | Diagnostic | Log, do not block |
| Config fingerprint | Diagnostic | Log, do not block |
| CST version | Diagnostic | Log, do not block |
| Machine hostname | Diagnostic | Log, do not block |
| Parameter schema change | Structural change | Treat as new project |

---

## 12. Future phase order

| Phase | Scope | Implementation plan |
|-------|-------|-------------------|
| **F** | Stage search no-CST helpers | Helper functions, feasibility tracker, stage transition logic. No runtime wiring. |
| **G** | Adaptive bounds no-CST helpers | Per-parameter buffer adjustment, clamp logic. No runtime wiring. |
| **H** | Stage + adaptive integration policy | Design how stage controller and adaptive bounds interact. Tests. |
| **I** | Stage runtime wiring no-CST | Wire stage controller into two-pass evaluator. No live CST yet. |
| **J** | Evaluation database design/schema | Data model, schema versioning, storage backend. No runtime wiring. |
| **K** | Evaluation database dedup no-CST skeleton | Dedup helpers, parameter matching, provenance logging. |
| **L** | Evaluation database warm-start / prior construction | Build prior_data from database for SAO warm-start. |
| **M** | Retry / recovery taxonomy design | Error taxonomy design document. Distinguish transient vs permanent. |
| **N** | Retry / inter-pass recovery skeleton | Wire retry handler into two-pass path. Inter-pass recovery for calibration→measurement gap. |
| **O+** | Live CST smokes / production validation | Only when explicitly requested. No automatic live runs. |

### Naming convention
All subsequent phases use single-letter names: F, G, H, I, J, K, L, M, N, O, P, ...
Sub-phases use decimal: F1, F2, G1, G2, ... No E1/E2/E3.  Phase E is the last
letter-phase with decimal sub-phases.

---

## 13. Non-goals (explicit)

This design document does **not**:
- Implement any runtime code.
- Run live CST.
- Repoint the root shim.
- Implement evaluation database.
- Implement staged search.
- Implement adaptive bounds.
- Implement retry / inter-pass recovery.
- Change JSONL sidecar semantics (remains diagnostic-only).
- Import ``cst_optimization.factory`` or ``cst_optimization.workflows.recovery``.
- Copy legacy ``RecoveryWorkflowEvaluator``.
