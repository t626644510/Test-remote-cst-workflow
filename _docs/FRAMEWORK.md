# Framework Notes

Compact architecture overlay for the current repository state (Phase 14).

## Shared Core (`src/cst_optimization/`)

| Module | Role |
|---|---|
| `core/` | CST abstractions: connection, project, solver, retry, results, cleanup, timeout |
| `evaluation/` | CST-free evaluation DB + retry: schema, storage (SQLite), dedup, warm_start, success_reuse, failure_skip, retry_runtime, retry_taxonomy |
| `diagnostics.py` | Unified diagnostics: exception hierarchy, CST message capture, optimisation Excel logger |
| `workflows/recovery.py` | Shared types: MetricSpec, FrequencyGate, EvaluationStatus, EvaluationResult |
| `workflows/base_evaluator.py` | Shared WF1 evaluator base class (physics post-processing) |
| `objectives/` | Shared objectives: frequency, quality, field, modes (antenna/wakefield → WF2 local) |
| `optimization/` | SAO, SAEA, acquisition, adaptive bounds, conditional gate |
| `parameters/` | ParameterSet, GeometryParameter |
| `physics/` | Cavity, formulas, heating, Poynting, wakefield, quantities |
| `factory.py` | Shared config→object builders + `build_workflow_2` wrapper |
| `runner.py` | `BaseRunner` class for workflow CLI entry points |
| `checkpoint.py` | CheckpointManager (pickle) |
| `database.py` | 1D curve recording/replay |

## Workflow Packages

| Package | Role |
|---|---|
| `workflows/rfgun_sao/` | **WF1 active**: SAO + two-pass + staged/adaptive search |
| `workflows/rfgun_single_pass/` | **WF1 reference**: validated single-pass baseline |
| `workflows/rfgun_hom_antenna/` | **WF2**: Dual-project HOM antenna (owns DualProjectOrchestrator, antenna/wakefield objectives) |
| `workflows/rfgun_recovery/` | **WF3**: Recovery optimisation (run.py + workflow.py + evaluator.py) |
| `workflows/rfgun_tolerance/` | **WF3 tolerance**: Monte Carlo sampling + statistical analysis |

## Root Shims

| File | Delegates to |
|---|---|
| `run_workflow_1.py` | `workflows.rfgun_sao.run` |
| `run_workflow_2.py` | `workflows.rfgun_hom_antenna.run` |
| `run_workflow_3.py` | `workflows.rfgun_recovery.run` |

## Migration Rules

- Workflow-specific behaviour stays in its package until reuse is proven.
- Promote to shared core only with stable cross-workflow contract.
- Code, tests, and git diff are authoritative.
- Root shims remain stable unless migration explicitly changes them.

## Validation

```powershell
.venv\Scripts\python.exe -m pytest tests --tb=short -q
.venv\Scripts\python.exe -m compileall src workflows run_workflow_*.py
```

## Tolerance Analysis Toolchain

`workflows/rfgun_tolerance/` provides Monte Carlo tolerance sampling and sweep analysis.

**Sampling** (requires CST):
```powershell
# Run multiple tolerance levels in one command; auto-detects existing DBs
python -m workflows.rfgun_tolerance.run --config config/default.yaml --tolerance-scale 1.0 1.67 3.33 5.0 6.67 10.0 2.33 4.0 8.33

# Recovery mode: re-run only previously failed records (no new random samples)
python -m workflows.rfgun_tolerance.run --config config/default.yaml --tolerance-scale 10.0 --recover
```

**Single-database analysis** (no CST required):
```powershell
python -m workflows.rfgun_tolerance.cli --db path\to\evaluations.db --output runs\tolerance\report.md
```

**Cross-level campaign analysis** (no CST required):
```powershell
python -m workflows.rfgun_tolerance.campaign_cli `
  --config config\default.yaml `
  --db 3=path\to\tolerance_eval_3um.db `
  --db 5=path\to\tolerance_eval_5um.db `
  --output runs\tolerance\campaign_report.md
```

Key `tolerance:` config fields:
- `output_dir`: optional DB and log root; override with `--output-dir`
- `db_path`: optional SQLite DB path template
- `max_samples`: samples per level
- `project_path`: CST project file
