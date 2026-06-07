# Workflow2 Current Context

## Role Model

- **Web reviewer/planner**: high-context, full-repo access, challenges reports,
  designs follow-up prompts. May be expensive.
- **Local bounded implementer**: receives concise prompts with bounded read
  set, explicit edit scope, targeted validation. Cheap and repeatable.

## Governance

Highest-priority governance file:

- `reports/restructure_plan/agent_operating_charter.md`

Source of truth is current code, tests, and git diff — not old reports.

## Direction

**Scheme 1.5**: isolate workflow2 first; do not extract shared core without
cross-workflow evidence.  Workflow-specific logic stays workflow-specific.
Module is core candidate only after reuse is demonstrated.

---

## Accepted Phase Map

| Phase | Description | Commit |
|-------|-------------|--------|
| W2-0  | Context document landed | — |
| W2-1  | No-CST characterisation tests (21 tests) | — |
| W2-2  | Package skeleton (`workflows/rfgun_hom_antenna/`) | — |
| W2-3  | Local config snapshot (`config.yaml`) | — |
| W2-4A | Builder ownership seam (delegation wrapper) | — |
| W2-4B | Builder implementation migrated to workflow package | `7e1cf1a` |
| W2-5  | Orchestrator ownership assessment (no migration) | `d168f42` |
| W2-6  | Semantic risk cleanup plan | `2636321` |
| W2-6A | Root docstring fix (R1 resolved) | `01c599e` |
| W2-6D | Scheduler/root shim compatibility tests (15 tests) | `5f7152a` |
| W2-6B | Solver timeout decision (R2 characterised) | `e5f8370` |
| W2-6C | Checkpoint callback decision (R4 characterised) | `47469c2` |
| W2-6E | Evaluator-only callback ownership (R4 resolved) | `126ba00` |
| **W2-6F** | Solver timeout fix (R2 resolved) | **current** |

---

## Current Runtime Facts

| Component | Status |
|-----------|--------|
| Public entry | `run_workflow_2.py` (root, unchanged) |
| Scheduler | `scripts/schedule_workflow2.ps1` — still binds root entry |
| Runtime config source | `config/default.yaml` → `workflow_2` subtree |
| Local config snapshot | `workflows/rfgun_hom_antenna/config.yaml` — **not** runtime source of truth |
| Builder owner | `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2` |
| Factory compat wrapper | `src/cst_optimization/factory.py::build_workflow_2` (lazy import + delegation) |
| Orchestrator | `src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator` — **not** promoted to shared core |
| CLI flags | `--auto-resume`, `--heartbeat`, `--warmup-from-db` — pinned by AST tests |

---

## Accepted Semantic Decisions

### R1 — Docstring (W2-6A, resolved)

Root docstring now accurately describes single CST DE connection with
sequential phase execution.  No longer claims "two independent CST windows".

### R6 — Scheduler/Root Shim (W2-6D, characterised)

- Scheduler still invokes `run_workflow_2.py` — no migration.
- 15 no-CST tests pin CLI flags and root import path via AST inspection.
- Future option: make root shim delegate to workflow package while keeping
  the file path (scheduler compatibility preserved).

### R2 — Solver Timeout (W2-6B/W2-6F, resolved)

- **W2-6B** (characterisation): identified mismatch — `optimization.solver`
  value 7200.0 was ignored; `SolverRunner` received 300.0 from fallback.
  See `workflow2_solver_timeout_decision.md` for analysis.
- **W2-6F** (fix): `optimization.solver` now overrides fallback solver for
  overlapping keys.  Effective Workflow2 timeout is **7200.0** from
  `workflow_2.optimization.solver.stagnation_timeout_s`.
- Fields not set in `optimization.solver` (e.g. `settle_s = 2.0`) still
  fall back to `workflow_2.solver`.

**Summary**: R2 resolved.  The intent 7200.0 is now consumed.

### R4 — Checkpoint Callback (W2-6C/W2-6E, resolved)

- **W2-6C** (decision): Option C — evaluator should be sole callback owner.
  See `workflow2_checkpoint_callback_ownership_decision.md`.
- **W2-6E** (implementation): `DualProjectOrchestrator` no longer fires
  `checkpoint_callback`.  Evaluator wrappers (SAO retry, SAO non-retry,
  SAEA) fire exactly **one callback per logical evaluation**.
- SAO non-retry preserves `solver_ok`/`error` semantics via
  `orchestrator.last_solver_ok`.
- W2-1 P0.3 tests updated: `call_count` 2 → 1.
- W2-6C duplicate-record tests updated: 2 records → 1 record.

**Summary**: one `checkpoint_callback` invocation per logical evaluation
across all three algorithm paths.  Root `_on_evaluation` will create one
checkpoint record per evaluation, not two.

---

## Current Do-Not-Do List

- ❌ No CST / live workflow unless explicitly approved
- ❌ No full pytest by default (targeted tests only)
- ❌ Do not modify `run_workflow_2.py` (root entry), `scripts/` (scheduler),
  `config/default.yaml`, `src/cst_optimization/core/**` unless the phase
  specifically permits it
- ❌ Do not move `DualProjectOrchestrator`
- ❌ Do not promote shared core without cross-workflow evidence

---

## Key Documents

| Document | Content |
|----------|---------|
| `workflow2_semantic_risk_cleanup_plan.md` | W2-6 plan — R1/R2/R4/R6 risk analysis and proposed future phases |
| `workflow2_solver_timeout_decision.md` | R2 analysis, 3 options, Option A recommended |
| `workflow2_checkpoint_callback_ownership_decision.md` | R4 analysis, 4 options, Option C recommended |
| `workflow2_orchestrator_ownership_assessment.md` | W2-5 — DualProjectOrchestrator ownership analysis |

---

## Integration Status

**Current Workflow2 integration branch**: `docs/workflow2-context-compaction`.
W2-6F merge: `a65593f`.  All 14 phases W2-0 through W2-6F accepted.
No phase has been merged to `main` yet.

### Main-merge readiness

| Item | Status |
|------|--------|
| Phases included | W2-0 through W2-6F (14 phases) |
| Files changed (22 total vs main) | `workflows/rfgun_hom_antenna/` (new package), `run_workflow_2.py` (import + docstring fix), `src/cst_optimization/core/orchestrator.py` (callback removed), `src/cst_optimization/factory.py` (compat wrapper — no semantic change), `tests/workflows/` (new/updated no-CST tests), `reports/restructure_plan/` (docs) |
| Files intentionally unchanged | `config/default.yaml`, `scripts/schedule_workflow2.ps1`, `src/cst_optimization/core/**` (except orchestrator.py callback removal) |
| Public entry | `run_workflow_2.py` — unchanged, still public entry |
| Scheduler | `scripts/schedule_workflow2.ps1` — unchanged, still binds root entry |
| Config source | `config/default.yaml` — unchanged, remains runtime source of truth |
| Local config | `workflows/rfgun_hom_antenna/config.yaml` — snapshot only, not runtime source |
| Builder owner | `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2` |
| Factory compat wrapper | `src/cst_optimization/factory.py::build_workflow_2` — unchanged semantics |
| Orchestrator | `src/cst_optimization/core/orchestrator.py` — callback removed W2-6E; **not moved**, not promoted to shared core |
| Checkpoint callback | Fires exactly once per evaluation (W2-6E) |
| Solver timeout (R2) | Effective 7200.0 from `optimization.solver` (W2-6F — resolved) |
| No-CST validation | 64 targeted tests across 4 suites (34 char + 15 sched + 6 config + 9 skeleton) |
| Live CST validation | Not run — recommended before production deployment |
| Config/runtime behaviour | Root entry unchanged, scheduler unchanged, config loading unchanged |
| Risk before main PR | Low — all semantic risks (R1 docstring, R4 callback, R2 timeout) resolved; no-CST tests pass |

**Decision**: integration branch is ready for main-integration review.  Do not
merge to main without explicit approval.  After approval, the merge should
be a single PR containing all 22 changed files with the summary above.

## Recommended Next Phase

Pending: R2 (solver timeout) characterisation is accepted but the 7200s
intent remains unconsumed.  A future phase could implement Option B or C
from `workflow2_solver_timeout_decision.md`, but no immediate phase is
queued.

---

## Implementation Note — W2-6E (Checkpoint Callback Fix)

This implements W2-6C Option C (evaluator-only callback ownership).

**Changes**:
- `src/cst_optimization/core/orchestrator.py`: Removed `self._checkpoint_callback()`
  call from `DualProjectOrchestrator.execute()`.  Orchestrator only sets `last_*`
  state; no longer fires callback.
- `workflows/rfgun_hom_antenna/workflow.py`: SAO retry and non-retry evaluator
  paths already owned the callback — unchanged.  SAEA path: replaced bare
  `evaluator = orchestrator.execute` with a wrapper that fires
  `checkpoint_callback` once per call.
- Tests: `call_count` assertions updated 2→1; duplicate-record tests updated
  2 record → 1 record; SAEA callback test added; partial-eval NaN test added.

**Result**: one `checkpoint_callback` invocation per logical evaluation
across all three algorithm paths (SAO retry, SAO non-retry, SAEA).
