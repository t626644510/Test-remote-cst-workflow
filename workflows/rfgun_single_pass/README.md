# Workflow 1 -- RF Gun Single-Pass SAO Optimisation

## Purpose

Single-project single-pass frequency-domain Surrogate-Assisted
Optimisation (SAO) for the X-band RF gun cavity.  Workflow 1 evaluates
a single CST project with a one-pass solve (fixed `f_data`), wrapped in
a three-tier retry handler with post-evaluation graceful reset.

## Current status (Phase 6 -- no-CST smoke tests)

- The **actual runner** lives at ``run.py`` inside this package.
- The root ``run_workflow_1.py`` is a thin compatibility shim.
- The **default config** is ``config.yaml`` in this directory.
- ``evaluator.py`` contains the ``Workflow1Evaluator`` class extracted
  from ``src/cst_optimization/factory.py``.
- ``workflow.py`` contains the local ``build_workflow_1()`` builder that
  does **not** import ``cst_optimization.factory``.
- ``run.py`` now exposes a ``build_arg_parser()`` for CLI-parser testing
  and imports from ``workflows.rfgun_single_pass.workflow``.
- ``tests/workflows/test_rfgun_single_pass_imports.py`` provides
  **no-CST smoke tests** that verify structure, imports, and config.

## Config

The default config file is ``workflows/rfgun_single_pass/config.yaml``.

To use a different config:

```powershell
python run_workflow_1.py --config path/to/config.yaml
```

## Constraints respected in all phases

| Constraint | Status |
|---|---|
| Modify `config/default.yaml` | Never |
| Modify `src/cst_optimization/` | Not modified for WF1 extraction |
| Modify Workflow 2 / 3 code | Never |
| Move `examples/` | Never |
| Change runtime behaviour | Not before Phase 7 (final validation) |

## Smoke tests

No-CST smoke tests can be run with:

```powershell
pytest tests/workflows/test_rfgun_single_pass_imports.py
```

These tests verify imports, CLI parser, config YAML structure, and
absence of factory / WF2 objective couplings.  They do **not** start
CST Studio Suite.

Full compile check:

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
```
