# Project Context Capsule

Date: 2026-06-08 (post-Phase-11 architecture consolidation)

Compact recovery entry point. Code, tests, and git diff are authoritative.

## Long-Term Goal

Build a maintainable Python framework for automatic CST Studio Suite microwave
accelerator-cavity simulation and surrogate-model optimisation.

## Current Framework (post-Phase-11)

| Area | Current role |
|---|---|
| `src/cst_optimization/core/` | CST abstractions: connection, project, solver, retry, results, cleanup, timeout |
| `src/cst_optimization/evaluation/` | Unified evaluation DB + retry (14 modules, canonical after Phase 10 P2 merge) |
| `src/cst_optimization/diagnostics.py` | Unified diagnostics: error types + CST message capture + Excel optimisation log |
| `src/cst_optimization/workflows/recovery.py` | Shared types: MetricSpec, FrequencyGate, EvaluationStatus, EvaluationResult |
| `src/cst_optimization/workflows/base_evaluator.py` | Shared WF1 evaluator base class (physics post-processing) |
| `src/cst_optimization/objectives/` | Shared objectives: frequency, quality, field, modes (antenna/wakefield → WF2) |
| `src/cst_optimization/optimization/` | SAO, SAEA, acquisition, adaptive bounds, conditional gate |
| `src/cst_optimization/parameters/` | ParameterSet, GeometryParameter |
| `src/cst_optimization/physics/` | Cavity, formulas, heating, Poynting, wakefield, quantities |
| `src/cst_optimization/factory.py` | Shared config-to-object builders + build_workflow_2/3 |
| `src/cst_optimization/checkpoint.py` | CheckpointManager |
| `workflows/rfgun_sao/` | **WF1 active**: SAO + two-pass + staged/adaptive (gate_builder, evaluator, metrics) |
| `workflows/rfgun_single_pass/` | **WF1 reference**: validated single-pass baseline (evaluator.py + workflow.py only) |
| `workflows/rfgun_hom_antenna/` | **WF2**: Dual-project HOM antenna (owns DualProjectOrchestrator, antenna/wakefield objectives) |
| `workflows/rfgun_recovery/` | **WF3**: Recovery optimisation (run.py + evaluator.py + workflow.py) |
| `workflows/rfgun_tolerance/` | **WF3 tolerance**: Monte Carlo sampling + statistical analysis |
| `run_workflow_1.py` | Shim → `workflows.rfgun_sao.run` |
| `run_workflow_2.py` | Shim → `workflows.rfgun_hom_antenna.run` |
| `run_workflow_3.py` | Shim → `workflows.rfgun_recovery.run` |

## Workflow Status

- **WF1 / SAO**: Active. Supports single-pass, two-pass calibration, staged search
  with adaptive bounds, evaluation DB with success reuse and failure skip.
- **WF2 / HOM antenna**: Active. DualProjectOrchestrator local to WF2 package.
  Antenna/wakefield objectives moved to WF2 (Phase 10 P1).
- **WF3 / Recovery**: Active. `run_workflow_3.py` is now a shim (Phase 10 P4c).
  Runner logic in `workflows/rfgun_recovery/run.py`.

## Key Changes (Phase 9-11)

| Phase | Change |
|---|---|
| 9.0 | Fix pyproject.toml pytest config + EvaluationStatus drift + dead factory code |
| 10 P0 | Delete 6 dead modules (orchestrator, watchdog, sensitivity/*, utils/plotting) |
| 10 P1 | Demote antenna/wakefield objectives to WF2 package |
| 10 P2 | Unify two parallel Evaluation DB implementations (14→14 merge) |
| 10 P3a | Merge _build_objectives (3→1 shared in factory) |
| 10 P4c | WF3 package-ification (run_workflow_3.py → shim + rfgun_recovery/) |
| 10 P5 | Unify diagnostics: core/errors + core/messages + optimization/logging → diagnostics.py |
| 11.0 | Merge builders.py → factory.py |
| 11.1 | Extract shared BaseWorkflow1Evaluator (eliminate ~170 lines duplication) |
| 11.2 | Split RecoveryWorkflowEvaluator from rfgun_sao → rfgun_recovery |
| 11.3 | Extract gate_builder.py from rfgun_sao/workflow.py |
| 11.4-6 | WF3 builder stub + FRAMEWORK.md refresh |

## Explicitly Skipped / Deferred (for user decision)

| Item | Reason | Plan |
|---|---|---|
| **11.4 deep**: Extract `build_workflow_3()` from factory.py into `rfgun_recovery/workflow.py` | ~280 lines, has many internal factory dependencies. Currently re-exports via stub. | Phase 12 |
| **11.5**: Extract shared `BaseRunner` class | Three run.py files (~340-700 lines each) share identical patterns (_on_evaluation closure, signal handling, checkpoint setup, optimize loop) but differ in build signatures, cleanup, and CLI flags. Needs careful abstraction design. | Phase 12 |
| **P3b**: Extract shared `Workflow1Evaluator` base class for `adapt_for_retry` | `adapt_for_retry` still duplicated in both evaluators | Phase 12 |
| **P4d**: Merge `builders.py` already done (11.0). Factory still ~900 lines. | Acceptable for now; WF3 builder extraction will reduce it | Phase 12 |
| **rfgun_single_pass**: Missing `run.py` — not independently executable | Design choice: reference-only package | Accepted |

## Milestone Tags

| Tag | Meaning |
|---|---|
| `milestone/pre-phase9-fixes-merge-2026-06-08` | Main before Phase 9 fixes |
| `milestone/phase9-fixes-merged-2026-06-08` | Phase 9 fixes merged |
| `milestone/pre-phase1-dedup-merge-2026-06-08` | Main before Phase 1-8 merge |
| `milestone/phase1-dedup-merged-2026-06-08` | Phase 1-8 dedup merged |

## Validation Baseline

```powershell
.venv\Scripts\python.exe -m pytest tests --tb=short -q
.venv\Scripts\python.exe -m compileall src workflows run_workflow_*.py
```
