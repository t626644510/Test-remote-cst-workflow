# Branch Context -- `workflow/1-rfgun-single-pass`

## Goal

Separate Workflow 1 (single-project single-pass RF gun SAO
optimisation) from the shared `cst_optimization` package into its own
independent workflow package under `workflows/rfgun_single_pass/`.

## Status (Phase 7 -- complete)

Workflow 1 now has its own:

- **Runner** -- ``run.py`` with CLI flags and ``build_arg_parser()``
- **Config** -- ``config.yaml`` (WF1 sections only)
- **Builder** -- ``workflow.py::build_workflow_1()`` (local, no factory import)
- **Evaluator** -- ``Workflow1Evaluator`` in ``evaluator.py``
- **Tests** -- ``tests/workflows/test_rfgun_single_pass_imports.py`` (8 no-CST smoke tests)
- **Shim** -- ``run_workflow_1.py`` (backward-compatible entry point)

## Allowed modifications

| Path | When |
|---|---|
| `workflows/rfgun_single_pass/` | All phases |
| `workflows/rfgun_single_pass/config.yaml` | Phase 4 onward (with report) |
| `workflows/rfgun_single_pass/evaluator.py` | Phase 5 onward (behaviour-preserving changes only) |
| `workflows/rfgun_single_pass/workflow.py` | Phase 5 onward (behaviour-preserving changes only) |
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
