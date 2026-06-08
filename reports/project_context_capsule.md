# Project Context Capsule

Date: 2026-06-08 (updated after Phase 1-8 decoupling refactor)

This is the compact recovery entry point for the repository. Code, tests,
and current git diff are authoritative; older reports and deleted branches
are recoverable through git history and milestone tags.

## Long-Term Goal

Build a maintainable Python framework for automatic CST Studio Suite microwave
accelerator-cavity simulation and surrogate-model optimisation while reducing
long-term context cost, branch sprawl, and workflow coupling.

## Current Framework (post-Phase-8)

| Area | Current role |
|---|---|
| `src/cst_optimization/core/` | Shared CST abstractions (connection, project, solver, retry, cleanup...) |
| `src/cst_optimization/evaluation/` | Shared evaluation database + retry infrastructure (14 CST-free modules) |
| `src/cst_optimization/workflows/recovery.py` | Shared types: MetricSpec, FrequencyGate, EvaluationStatus, EvaluationResult |
| `src/cst_optimization/objectives/` | Objective function definitions (frequency, field, wakefield, antenna...) |
| `src/cst_optimization/optimization/` | SAO, SAEA, acquisition, adaptive bounds, conditional gate |
| `src/cst_optimization/parameters/` | ParameterSet, GeometryParameter, ConstraintSet |
| `src/cst_optimization/physics/` | Physics formulas (cavity, heating, Poynting, bandwidth...) |
| `src/cst_optimization/builders.py` | Shared config→object builders |
| `src/cst_optimization/factory.py` | Thin delegation: build_workflow_2 |
| `workflows/rfgun_sao/` | **WF1**: SAO optimisation (single-pass + two-pass recovery + staged/adaptive search) |
| `workflows/rfgun_hom_antenna/` | **WF2**: Dual-project HOM antenna optimisation (owns DualProjectOrchestrator) |
| `workflows/rfgun_tolerance/` | **WF3**: Tolerance analysis (CST sampling runner + statistical analysis CLI) |
| `run_workflow_1.py` | Shim → `rfgun_sao.run.main()` |
| `run_workflow_2.py` | Shim → `rfgun_hom_antenna.run.main()` |
| `config/` | Workflow-level configs (default.yaml for WF1, WF3 tolerance section) |

## Workflow Status

- **WF1 / SAO**: Active package is `workflows/rfgun_sao/`. Supports single-pass,
  two-pass calibration, staged search with adaptive bounds, evaluation database
  with success reuse and failure skip.
- **WF2 / HOM antenna**: Active package is `workflows/rfgun_hom_antenna/`.
  `DualProjectOrchestrator` moved to WF2 package (Phase 3).
- **WF3 / Tolerance**: Active package is `workflows/rfgun_tolerance/`.
  `runner.py` does CST Monte Carlo sampling; `cli.py` does statistical analysis
  from the evaluation database.

## Key Changes (Phase 1-8, 2026-06-08)

| Phase | Change |
|---|---|
| P1 | Unified EvaluationStatus/EvaluationResult in recovery.py |
| P2 | Promoted 14 CST-free modules to `cst_optimization.evaluation/` |
| P3 | Moved DualProjectOrchestrator to WF2 package |
| P4 | Deleted `rfgun_single_pass/` (absorbed by rfgun_sao) |
| P5 | Extracted tolerance modules to `rfgun_tolerance/` (WF3) |
| P6 | Moved RecoveryWorkflowEvaluator to WF1; recovery.py → types-only |
| P7 | Deleted backward-compat shims |
| P8 | Created WF3 tolerance sampler runner; deleted run_workflow_3.py |

## Milestone Tags

| Tag | Meaning |
|---|---|
| `milestone/pre-environment-prune-2026-06-08` | Main before cleanup |
| `milestone/workflow2-final-2026-06-08` | Final Workflow2 state |
| `milestone/workflow1-single-pass-baseline` | Single-pass baseline (deprecated, merged into rfgun_sao) |
| `milestone/workflow3-tolerance-analysis-baseline` | Tolerance analysis baseline |
| `milestone/decouple-phase8-final-2026-06-08` | End of Phase 1-8 decoupling refactor |

## Cleanup Policy

- Keep `main` plus only durable workflow baseline branches.
- Keep Markdown small and current-state oriented.
- Keep tests that protect current public runtime contracts and behaviour.
- Restore old evidence from git history, tags, or the cleanup bundle.
