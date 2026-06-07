# Workflow2 Final Context Capsule

**Date:** 2026-06-08
**Status:** W2-0 through W2-10 complete. All migration phases accepted and merged.
This is the preferred recovery entry point for future web-agent context.

> **Source of truth:** code, tests, and current git diff are authoritative.
> Decision reports and historical phase plans are evidence only.

---

## 1. Final Ownership Map

| Concern | Location | Notes |
|---------|----------|-------|
| **Public entry** | `run_workflow_2.py` | Compatibility shim: `from workflows.rfgun_hom_antenna.run import main` |
| **Runner owner** | `workflows/rfgun_hom_antenna/run.py` | Full runtime body: CLI, config load, checkpoint, heartbeat, warmup, optimise, shutdown |
| **Runtime config** | `workflows/rfgun_hom_antenna/config.yaml` | Contains `workflow_2` subtree + top-level `cst`, `solver`, `logging` fallbacks |
| **Builder owner** | `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2` | Sole runtime implementation; constructs orchestrator, solver, optimiser |
| **Factory wrapper** | `src/cst_optimization/factory.py::build_workflow_2` | Compatibility re-export; delegate only |
| **Orchestrator** | `src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator` | Kept in shared core per W2-10A (no cross-workflow reuse proven) |

---

## 2. Phase Ledger

| Phase | Description | Status |
|-------|-------------|--------|
| W2-0 | Context document | ✅ merged baseline |
| W2-1 | No-CST characterization tests | ✅ merged baseline |
| W2-2 | Package skeleton | ✅ merged baseline |
| W2-3 | Config isolation | ✅ merged baseline |
| W2-4A | Builder ownership seam | ✅ merged baseline |
| W2-4B | Builder implementation migration | ✅ merged baseline |
| W2-5 | Orchestrator ownership assessment | ✅ merged baseline |
| W2-6 | Semantic risk cleanup plan | ✅ merged baseline |
| W2-6A | Root docstring fix (R1) | ✅ merged baseline |
| W2-6B | Solver timeout decision (R2) | ✅ merged baseline |
| W2-6C | Checkpoint callback decision (R4) | ✅ merged baseline |
| W2-6D | Scheduler/root shim compatibility | ✅ merged baseline |
| W2-6E | Evaluator-only callback ownership (R4) | ✅ merged baseline |
| W2-6F | Solver timeout runtime fix (R2) | ✅ merged baseline |
| W2-7 | Runner body migrated to package run.py | ✅ accepted |
| W2-8 | Config ownership — local config.yaml is runtime source | ✅ accepted |
| W2-9 | Bounded live CST smoke (F2F + trigger) | ✅ accepted |
| W2-10A | Orchestrator boundary decision — keep in core | ✅ accepted |
| W2-10B | No-op / deferred | — |

---

## 3. Runtime Invariants

- **Public command** remains `python run_workflow_2.py`.
- **Scheduler** still targets root `run_workflow_2.py` (`scripts/schedule_workflow2.ps1`).
- **Config source** is `workflows/rfgun_hom_antenna/config.yaml` (W2-8).
- **`config/default.yaml["workflow_2"]`** is legacy/reference only; not read by runner.
- **Effective solver timeout** is `7200.0` from `workflow_2.optimization.solver.stagnation_timeout_s` (W2-6F).
- **Checkpoint** fires exactly one callback per logical evaluation (W2-6E); completed-eval checkpoint is tested via mocked orchestrator.
- **No full wakefield run** is required by current acceptance; startup + F2F + trigger is sufficient smoke evidence (W2-9).

---

## 4. Orchestrator Decision Summary (W2-10A)

- **Keep `DualProjectOrchestrator`** in `src/cst_optimization/core/orchestrator.py`.
- **Reason:** Only one runtime consumer (WF2). WF1 and WF3 use different orchestrators. No cross-workflow reuse evidence. Moving risks factory import coupling. Splitting is premature abstraction.
- **Future rule:** Do **not** add new Workflow2-specific phase/project logic into core without a bounded boundary phase. New WF2 logic should use Workflow2-local wrappers or adapters.

---

## 5. Live Evidence Summary

- **W2-9** exercised `python run_workflow_2.py --heartbeat`.
- Frequency-domain (`F2F.cst`) completed in 123s; pre-filter passed.
- Inter-pass DE reset executed (old DE hung, new DE created).
- Wakefield triggered correctly (`antenna_absorption raw=-13.12`).
- Wakefield was **intentionally interrupted** by operator instruction (F2W/F2WO computations are prohibitively slow for bounded smoke).
- CST orphan processes were manually confirmed cleaned after W2-9.
- Full W2-9 evidence: `reports/restructure_plan/workflow2_w2_9_live_smoke.md`.

---

## 6. Known Caveats

1. **Duplicate legacy `workflow_2` in `config/default.yaml`** — not removed; future cleanup phase may remove or deprecate it.
2. **Unrelated WF1 warm-start test failure** (`test_warm_start_does_not_reference_jsonl`) may appear in broad test runs. Do not treat as a W2 blocker.
3. **Factory type-annotation imports `DualProjectOrchestrator`** — cosmetic dependency; should use `TYPE_CHECKING` guard if class ever moves.
4. **`DualProjectOrchestrator` location is pragmatic, not proof of generic utility** — the class is 955 lines of mostly WF2-specific logic.

---

## 7. Recommended Next Direction

- **Stop Workflow2 migration work** unless a new explicit issue is opened.
- **Move to the next workflow or shared-core candidate assessment** under the charter (`agent_operating_charter.md`).
- If Workflow2 work resumes, the preferred entry points are:
  1. This capsule (`workflow2_final_context_capsule.md`)
  2. `workflow2_next_phase_plan.md` (all phases complete)
  3. Code and tests (authoritative)

---

## 8. Validation Snapshot

```
python -m pytest tests/workflows/test_workflow2_scheduler_shim.py \
                  tests/workflows/test_workflow2_config_isolation.py \
                  tests/workflows/test_workflow2_characterization.py -q
# 69 passed (last known run on main, commit e49718d)

python -m pytest tests/workflows/ -q
# 1238 passed, 1 failed (pre-existing WF1 warm-start, unrelated)
```

---

## 9. Key Documents Index

| Document | Purpose |
|----------|---------|
| `agent_operating_charter.md` | Governance baseline |
| `agent_standing_rules.md` | Safety checklist for prompts |
| `workflow2_final_context_capsule.md` | **This file** — preferred recovery entry point |
| `workflow2_next_phase_plan.md` | Phase ledger (all complete) |
| `workflow2_w2_9_live_smoke.md` | W2-9 live evidence |
| `workflow2_w2_10_orchestrator_boundary_assessment.md` | W2-10A decision |
| `workflow2_current_context.md` | Short, current-state handoff (compact version of this capsule) |
