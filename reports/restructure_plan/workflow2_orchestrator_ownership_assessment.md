# Workflow 2 — Orchestrator Ownership Assessment (W2-5)

## 1. Current Facts

### Definition Location

```
src/cst_optimization/core/orchestrator.py
  line  43  — dataclass ProjectSpec
  line  68  — class DualProjectOrchestrator
```

### Import Consumers

| File | Usage | Workflow |
|------|-------|----------|
| `workflows/rfgun_hom_antenna/workflow.py:19` | `from cst_optimization.core.orchestrator import DualProjectOrchestrator, ProjectSpec` | **WF2** (builds orchestrator at line 206) |
| `src/cst_optimization/factory.py:24` | `from .core.orchestrator import DualProjectOrchestrator, ProjectSpec` | Shared factory — types referenced in `build_workflow_2` signature and `_make_sao_evaluator` (dead code, never called) |

### Construction Sites

| File | Line | Context |
|------|------|---------|
| `workflows/rfgun_hom_antenna/workflow.py` | 206 | `orchestrator = DualProjectOrchestrator(...)` — WF2 builder only |

**No other workflow** constructs a `DualProjectOrchestrator`. WF1 returns a `_Workflow1Container` (line 312–321 of `factory.py`). WF3 returns a `RecoveryWorkflowEvaluator`.

### Non-WF2 References

The `DualProjectOrchestrator` type appears in:
- `src/cst_optimization/factory.py:646` — `_make_sao_evaluator` signature (dead code, never called)
- `tests/workflows/test_workflow2_characterization.py` — annotation assertions about the builder return signature

**No cross-workflow shared-core evidence exists.** WF1 and WF3 have their own orchestration logic and do not import or use `DualProjectOrchestrator`.

---

## 2. Workflow2-Specific Behavior Inventory

All behaviors listed below are implemented in `src/cst_optimization/core/orchestrator.py`:

| Feature | Relevant Code Lines | WF2-Specific? |
|---------|-------------------|---------------|
| Multi-project phase sequencing | `execute()` (144–608) — loops over `ProjectSpec` list sorted by `is_pre_filter` then `condition_trigger` | **Yes** — WF1/WF3 are single-project |
| Frequency-domain / wakefield / wakefield-offset semantics | Phase labels `f2f`, `f2w`, `f2wo` appear throughout `execute()` and `_execute_phase_1()` | **Yes** — hard-coded phase labels and three-phase workflow |
| Pre-filter behaviour | `_check_pre_filter()` (855–878) — evaluates antenna absorption objectives and rejects if above threshold | **Yes** — concept belongs to the HOM antenna optimisation domain |
| Conditional project execution | Phase 1.5 (lines 280–418) — runs wakefield projects only when trigger objective penalty is below threshold | **Yes** — WF2-specific gating policy |
| Adaptive gate integration | Lines 331–348, 484–497 — GP-gated skip decisions for conditional projects | **Yes** — tightly coupled to WF2's conditional project logic |
| Raw curve / .npz recording | Lines 202–208, 263–267, 408–417, 534–565 — optional recording session with "atomize" saves | **Mostly WF2** — recording infrastructure could be generic, but the phase-label convention and F2F/F2W/F2WO semantics are WF2-specific |
| Phase labels F2F / F2W / F2WO | `start_phase="f2f"/"f2w"`, `_has = {"has_f2f", "has_f2w", "has_f2wo"}`, `_save_phase_npz(iteration, "f2f", phases)` | **Yes** — hard-coded strings reflecting the RF gun HOM antenna workflow |
| Pre-solve cleanup | `remove_result_folder()`, `remove_lock_file()` (lines 643–645) | Generic utility — but called inline in `_execute_phase_1` |
| Inter-pass DE reset | `_reset_connection()` (lines 805–853) — kills and recreates CST DE between phases | **Yes** — only needed when switching solver types (freq-domain → wakefield) |
| Checkpoint callback | `self._checkpoint_callback(...)` (line 567) | Generic protocol — could be shared |
| Optimisation logging | Phase 3.5 (lines 500–531) — writes to Excel logger | Generic — `OptimizationLogger` is not orchestrator-specific |
| Curves database index | Lines 534–565 — saves `index.jsonl` with phase-completion flags | Mostly generic infrastructure, but the `has_f2f`/`has_f2w`/`has_f2wo` keys are WF2-specific |

**Summary**: ~80 % of the orchestrator's code is workflow2-specific. The generic parts (checkpoint callback, optimisation logging, project cleanup) are simple utility calls rather than reusable abstractions.

---

## 3. Shared-Core Assessment

### Parts That Look Generic (potential future core candidates)

- **`ProjectSpec` dataclass**: Simple data holder. Could be generic but currently only used by WF2.
- **Checkpoint callback protocol**: The callback signature `(params, raw_values, penalties, solver_ok, error) → None` is used by both WF2 and WF3. Could be formalised.
- **`_run_solver_with_mesh_retry()`**: Solver mesh retry logic (lines 767–803) could be useful for any CST workflow.

### Parts That Look WF2-Specific

- **Phase sequencing logic** (`start_phase`, `skip_phases`, `f2f_ok` tracking)
- **Hard-coded phase labels** (`f2f`, `f2w`, `f2wo`, `frequency_domain`, `wakefield`, `wakefield_offset`)
- **Conditional project gating** (trigger penalties, `_gate_predictions`)
- **Adaptive gate integration** (GP-based skip decisions)
- **Pre-filter evaluation** (antenna absorption threshold checks)
- **`_has` dictionary keys** (`has_f2f`, `has_f2w`, `has_f2wo`)
- **`_reset_connection()`** — kills CST between phases; only meaningful in multi-solver contexts
- **Per-phase `.npz` atomize** — phase-label naming convention
- **`_check_pre_filter()`** — evaluates antenna absorption objectives specifically

### Missing Evidence Before Promoting to Shared Core

1. **No cross-workflow consumer**: WF1 and WF3 have their own orchestration — neither uses `DualProjectOrchestrator`.
2. **No isolated interface**: The orchestrator is instantiated with WF2-specific config keys (projects, objectives with project_map, adaptive_gate, curves_db_dir).
3. **No demonstrated reuse**: The `_run_solver_with_mesh_retry()` method could be useful generically, but no workflow has requested it as a shared service.
4. **Phase label coupling**: F2F/F2W/F2WO are embedded in method signatures and index records.

---

## 4. Recommendation

**Keep `DualProjectOrchestrator` in `src/cst_optimization/core/orchestrator.py` for now.**

Rationale:
- The orchestrator is ~80 % workflow2-specific.
- No cross-workflow dependency exists.
- Moving it to `workflows/rfgun_hom_antenna/` would create an import dependency from the shared factory (which types-annotates `DualProjectOrchestrator` in `build_workflow_2`'s return signature). The factory's dependency is only a type reference, but resolving it at import time would require either:
  - A re-export from the workflow package (creates a circular-smelling dependency from shared factory → workflow package)
  - Or changing the factory's return annotation to `Any` (loses type-safety)

**If migration were desired later**, the recommended approach would be:
1. Extract the truly generic sub-components (checkpoint protocol, solver mesh retry) into `cst_optimization/core/_orchestration_base.py` or similar.
2. Move `DualProjectOrchestrator` + `ProjectSpec` as a unit into `workflows/rfgun_hom_antenna/`.
3. Update the factory wrapper's type annotation to use a forward reference or `Protocol`.

**This recommendation is documentation only — no migration is proposed in this phase.**

---

## 5. Proposed Next Phase

**W2-6: semantic risk cleanup planning.**

The following risks (identified in W2-0/W2-1) remain unresolved and should be planned for remediation:
- R2: Solver timeout config hierarchy mismatch (intent 7200s vs actual 300s)
- R4: Checkpoint callback double-trigger (2 calls/evaluation)
- R1: Stale docstring in `run_workflow_2.py` about "two independent CST windows"
- R6: Scheduler bound to root entry (mitigation planning)

Each risk should have a proposed fix approach, an impact estimate, and a test plan before implementation begins in a later phase.

---

## Appendix: Search Commands Used

```powershell
# Find all DualProjectOrchestrator references
grep -rn "DualProjectOrchestrator" src/ workflows/ tests/ run_workflow_2.py

# Find all ProjectSpec references
grep -rn "ProjectSpec" src/ workflows/ tests/

# Inventory workflow2-specific patterns in orchestrator
grep -n "f2f\|f2w\|wakefield\|frequency_domain\|pre_filter\|adaptive_gate\|start_phase\|skip_phase\|curves_db" src/cst_optimization/core/orchestrator.py

# Check WF1 builder return type
grep -A 10 "def build_workflow_1" src/cst_optimization/factory.py | head -15
```
