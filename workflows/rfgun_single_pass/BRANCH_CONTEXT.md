# Branch Context -- `workflow/1-rfgun-single-pass`

## Goal

Separate Workflow 1 (single-project single-pass RF gun SAO
optimisation) from the shared `cst_optimization` package into its own
independent workflow package under `workflows/rfgun_single_pass/`.

## Status (Phase 9 -- finalised)

Workflow 1 separation is complete and validated:

- **no-CST smoke tests:** 12/12 passed
- **Live CST smoke:** PASS (1 evaluation, all 7 metrics computed, no Python exceptions)
- **All pre-existing bugs fixed:** 4 bugs discovered and resolved

## Allowed modifications

| Path | When |
|---|---|
| `workflows/rfgun_single_pass/` | All phases |
| `workflows/rfgun_single_pass/config.yaml` | Phase 4 onward (with report) |
| `workflows/rfgun_single_pass/evaluator.py` | Phase 5 onward (behaviour-preserving only) |
| `workflows/rfgun_single_pass/workflow.py` | Phase 5 onward (behaviour-preserving only) |
| `reports/workflow1_split/` | All phases |
| `run_workflow_1.py` | Phase 3 onward (runner migration only) |
| `tests/workflows/` | Phase 6 onward (unit / integration tests) |

## Forbidden modifications (all phases)

- `run_workflow_2.py`
- `run_workflow_3.py`
- `config/default.yaml`
- `config/workflow_3.yaml`
- `src/cst_optimization/` (entire tree)
- `examples/` (entire tree)
- Writing Workflow 1 logic back into `src/cst_optimization/factory.py`
- Modifying Workflow 2/3 to suit Workflow 1

## Minimum validation before any WF1 commit

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
```

If modifying evaluator, solver, or result-reading logic, a live CST
smoke run must also be performed:

```powershell
python run_workflow_1.py --n-initial 1 --n-iter 0
```

## Phase roadmap (completed)

| Phase | Deliverable |
|---|---|
| 1 | Dependency inventory |
| 2 | Directory skeleton |
| 3 | Runner migration |
| 4 | Config split |
| 4.1 | Logging fix |
| 5 | Evaluator extraction |
| 5.1 | Path fix |
| 6 | No-CST smoke tests |
| 7 | Documentation / final report |
| 8.1 | Fix: checkpoint warm-start |
| 8.3 | Fix: optimize() kwargs |
| 8.5 | Fix: n_initial config key |
| 8.6 | Live CST re-run (partial) |
| 8.7 | Fix: result.get -> result.x_opt |
| 8.8 | Final live CST validation (PASS) |
| 9 | Branch finalisation |
