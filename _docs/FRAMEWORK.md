# Framework Notes

This file is a compact architecture overlay for the current repository state.
It is not the source of truth for CST APIs and should not grow into another
phase report.

For project history, workflow status, and milestone tags, read
`reports/project_context_capsule.md`.

## Current Code Map

### Shared Core (`src/cst_optimization/`)

| Module | Role |
|---|---|
| `core/` | CST abstractions: connection, project, solver, retry (3-tier), results, cleanup, messages, errors, timeout |
| `evaluation/` | CST-free evaluation database + retry infrastructure: schema, storage (SQLite), dedup, warm_start, success_reuse, failure_skip, retry_loop, retry_taxonomy, recovery_safety |
| `workflows/recovery.py` | Shared types only: MetricSpec, FrequencyGate, EvaluationStatus, EvaluationResult |
| `objectives/` | Objective functions: frequency, quality, field, wakefield, antenna, modes |
| `optimization/` | Optimisation: SAO, SAEA, acquisition functions, adaptive bounds, conditional gate |
| `parameters/` | ParameterSet, GeometryParameter |
| `physics/` | Physics formulas: cavity, half-power bandwidth, heating, Poynting |
| `sensitivity/` | Sobol sensitivity, robustness |
| `builders.py` | Shared config→object builders: _build_parameters, _build_sao, _resolve_named_weights, etc. |
| `factory.py` | Thin delegation layer: build_workflow_2 → rfgun_hom_antenna |
| `checkpoint.py` | CheckpointManager (pickle-based persistence) |
| `database.py` | 1D curve recording/replay (RecordingResultReader, VirtualResultReader) |

### Workflow Packages

| Package | Role |
|---|---|
| `workflows/rfgun_sao/` | **WF1**: SAO optimisation (single-pass + two-pass recovery + staged/adaptive search) |
| `workflows/rfgun_hom_antenna/` | **WF2**: Dual-project HOM antenna optimisation (owns DualProjectOrchestrator) |
| `workflows/rfgun_tolerance/` | **WF3**: Tolerance analysis — CST sampling around nominal (runner.py) + statistical analysis (cli.py, analysis.py, etc.) |

### Root Shims

| File | Delegates to |
|---|---|
| `run_workflow_1.py` | `workflows.rfgun_sao.run.main()` |
| `run_workflow_2.py` | `workflows.rfgun_hom_antenna.run.main()` |

## CST Documentation

`_docs/Python/` and `_docs/PythonTutorial/` are local CST documentation
references. When writing code that calls CST Studio Suite, use these local docs,
user-supplied official docs, or already verified repository wrappers. Do not
invent `cst.interface` or `cst.results` APIs.

## Migration Rules

- Keep workflow-specific behaviour inside its workflow package until reuse is proven.
- Promote code into `src/cst_optimization/` only when it has a stable cross-workflow contract.
- Current code, tests, and git diff are authoritative. Historical reports and tags are evidence only.
- Root compatibility shims (`run_workflow_*.py`) should remain stable unless a scoped migration explicitly changes them.

## Validation Baseline

For repository-wide no-CST validation, use:

```powershell
.venv\Scripts\python.exe -m pytest tests --tb=short -q
.venv\Scripts\python.exe -m compileall src workflows run_workflow_1.py run_workflow_2.py
```
