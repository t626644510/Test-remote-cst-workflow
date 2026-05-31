# Branch Context -- `workflow/1-rfgun-single-pass`

## Goal

Separate Workflow 1 (single-project single-pass RF gun SAO
optimisation) from the shared `cst_optimization` package into its own
independent workflow package under `workflows/rfgun_single_pass/`.

## Branch strategy

This branch is created from the shared codebase after Phase 1
(inventory).  Every phase creates or updates a report in
`reports/workflow1_split/phase_XX_*.md`.

## Allowed modifications

| Path | When |
|---|---|
| `workflows/rfgun_single_pass/` | Phase 2 onward |
| `workflows/rfgun_single_pass/config.yaml` | Phase 4 onward |
| `reports/workflow1_split/` | Phase 1 onward |
| `run_workflow_1.py` | Phase 3 onward (runner migration only) |
| `tests/workflows/` | Phase 6 onward (unit / integration tests) |

## Forbidden modifications (all phases)

- `run_workflow_2.py`
- `run_workflow_3.py`
- `config/default.yaml`
- `config/workflow_3.yaml`
- `src/cst_optimization/` (entire tree)
- `examples/` (entire tree)

## Rules

1. Never modify Workflow 2 or Workflow 3 code to suit Workflow 1.
2. Never push Workflow 1-specific logic back into `core/`.
3. Every phase must add or update a report in `reports/workflow1_split/`
   documenting what was done, what was tested, and the real terminal
   output.
4. Every phase must run `python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py`
   and paste the real output into the phase report.
5. Runtime behaviour must not change until Phase 7 (final end-to-end
   validation with identical results).

## Phase roadmap

| Phase | Deliverable |
|---|---|
| 1 | Dependency inventory |
| 2 | Directory skeleton |
| 3 | Runner migration |
| 4 | Config split |
| 5 | Evaluator extraction |
| 6 | No-CST smoke tests |
| 7 | Documentation / final report |
