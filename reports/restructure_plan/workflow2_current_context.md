# Workflow2 Current Context

Short, current-state handoff.  The authoritative recovery capsule is
`workflow2_final_context_capsule.md`.  Code, tests, and git diff are
authoritative over reports.

## Status

All W2 migration phases (W2-0 through W2-10A) are complete and merged to
`main`.  No W2-10B code movement is planned.  No further Workflow2
migration work is in progress.

## Final Ownership

| Component | Owner |
|-----------|-------|
| Public entry | `run_workflow_2.py` (compatibility shim) |
| Runner | `workflows/rfgun_hom_antenna/run.py` |
| Runtime config | `workflows/rfgun_hom_antenna/config.yaml` (W2-8) |
| Builder | `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2` |
| Factory wrapper | `src/cst_optimization/factory.py::build_workflow_2` (re-export) |
| Orchestrator | `src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator` (W2-10A: kept) |
| Scheduler target | `run_workflow_2.py` (unchanged) |

## Runtime Invariants

- `python run_workflow_2.py` — public command.
- Scheduler (`scripts/schedule_workflow2.ps1`) targets root `run_workflow_2.py`.
- Config source: `workflows/rfgun_hom_antenna/config.yaml` with `cst`/`solver`/`logging` fallbacks.
- `config/default.yaml["workflow_2"]` is legacy; not read at runtime.
- Solver timeout: `7200.0` from `optimization.solver.stagnation_timeout_s` (W2-6F).
- Checkpoint: one callback per logical evaluation (W2-6E).
- Live smoke: F2F + trigger sufficient; no full wakefield required (W2-9).

## Orchestrator (W2-10A)

Keep `DualProjectOrchestrator` in `src/cst_optimization/core/`.  No move
planned.  Do not add new WF2-specific phase/project logic into core
without a bounded boundary phase.

## Known Caveats

- `config/default.yaml["workflow_2"]` is legacy (future cleanup).
- Unrelated WF1 warm-start test failure in broad sweeps — not a W2 blocker.
- Factory type-annotates `DualProjectOrchestrator` — cosmetic import.

## Next Direction

Stop Workflow2 migration work.  Move to next workflow or shared-core
assessment.  If W2 work resumes, start from `workflow2_final_context_capsule.md`.
