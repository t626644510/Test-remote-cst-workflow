# Workflow2 Main PR Summary

**Target**: `docs/workflow2-context-compaction` → `main`
**Status**: Ready for review.  **Do not merge without explicit approval.**

---

## Scope

| Aspect | Detail |
|--------|--------|
| Phases | W2-0 through W2-6F (14 phases, all accepted) |
| Changed files | 19 vs `origin/main` |
| No-CST tests | 64 pass across 4 suites |

## Changed Files by Category

| Category | Files | Description |
|----------|-------|-------------|
| New workflow package | `workflows/rfgun_hom_antenna/{__init__.py,run.py,workflow.py,config.yaml,README.md}` | Workflow2 builder implementation, snapshot config, skeleton |
| Root entry | `run_workflow_2.py` | Import repoint (W2-4A) + docstring fix (W2-6A). CLI flags, scheduler contract unchanged. |
| Factory | `src/cst_optimization/factory.py` | `build_workflow_2` → compatibility wrapper (W2-4B). No semantic change. |
| Orchestrator | `src/cst_optimization/core/orchestrator.py` | `checkpoint_callback` call removed (W2-6E). Class not moved. |
| Tests | `tests/workflows/test_workflow2_*.py` (6 files) | Characterization, builder seam, scheduler shim, config isolation, skeleton. All no-CST. |
| Reports | `reports/restructure_plan/workflow2_*.md` (6 files) | Context docs, risk plans, decision records, ownership assessments. |

## Semantic Fixes

| Risk | Phase | Description |
|------|-------|-------------|
| R1 — Stale docstring | W2-6A | Root docstring corrected: single CST DE connection, sequential phases |
| R4 — Callback double-trigger | W2-6E | Orchestrator no longer fires callback. Evaluator fires once per evaluation. |
| R2 — Solver timeout | W2-6F | `workflow_2.optimization.solver` now consumed. Effective timeout 7200.0. |

## Intentional Non-Changes

- **Scheduler**: `scripts/schedule_workflow2.ps1` — unchanged, still binds root entry.
- **Config**: `config/default.yaml` — unchanged, remains runtime source of truth.
- **Workflow-local config**: `workflows/rfgun_hom_antenna/config.yaml` — snapshot only, not consumed.
- **Orchestrator**: `DualProjectOrchestrator` — not moved, not promoted to shared core.
- **Root config loading**: Merge semantics unchanged.

## Validated

| Suite | Command | Result |
|-------|---------|--------|
| Characterisation | `pytest -q tests/workflows/test_workflow2_characterization.py` | 34/34 passed |
| Scheduler shim | `pytest -q tests/workflows/test_workflow2_scheduler_shim.py` | 15/15 passed |
| Config isolation | `pytest -q tests/workflows/test_workflow2_config_isolation.py` | 6/6 passed |
| Package skeleton | `pytest -q tests/workflows/test_workflow2_package_skeleton.py` | 9/9 passed |

**Live CST smoke**: not run.  Recommended before production deployment, but must not be initiated without explicit approval.
