# Framework Notes

This file is a compact architecture overlay for the current repository state.
It is not the source of truth for CST APIs and should not grow into another
phase report.

For project history, workflow status, and milestone tags, read
`reports/project_context_capsule.md`.

## Current Code Map

- `src/cst_optimization/` contains shared framework code with cross-workflow
  contracts: CST wrappers, retry/recovery utilities, physics calculations,
  objective functions, optimisation helpers, checkpointing, and persistence.
- `workflows/rfgun_single_pass/` is the validated single-pass reference
  workflow.
- `workflows/rfgun_sao/` is the current Workflow 1 style SAO package and owns
  its workflow-local runtime helpers.
- `workflows/rfgun_hom_antenna/` is the Workflow 2 package. Workflow-specific
  builder and orchestration behaviour should remain local unless reuse is
  proven.
- `run_workflow_1.py`, `run_workflow_2.py`, and `run_workflow_3.py` are root
  compatibility shims and should remain stable unless a scoped migration
  explicitly changes them.
- `config/` still contains shared or legacy defaults plus Workflow 3 runtime
  configuration. Avoid treating old config comments as architecture authority.

## CST Documentation

`_docs/Python/` and `_docs/PythonTutorial/` are local CST documentation
references. When writing code that calls CST Studio Suite, use these local docs,
user-supplied official docs, or already verified repository wrappers. Do not
invent `cst.interface` or `cst.results` APIs.

## Migration Rules

- Keep workflow-specific behaviour inside its workflow package until a stable
  cross-workflow contract exists.
- Promote code into `src/cst_optimization/` only when reuse is real and tested.
- Keep tests focused on current public runtime contracts rather than historical
  phase scaffolding.
- Treat historical reports, branch names, and old examples as evidence only;
  current code, tests, and git diff are authoritative.

## Validation Baseline

For repository-wide no-CST validation, use:

```powershell
.venv\Scripts\python.exe -m pytest tests --tb=short -q
.venv\Scripts\python.exe -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
```
