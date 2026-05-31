# Workflow 1 -- RF Gun Single-Pass SAO Optimisation

## Purpose

Single-project single-pass frequency-domain Surrogate-Assisted
Optimisation (SAO) for the X-band RF gun cavity.  Workflow 1 evaluates
a single CST project with a one-pass solve (fixed `f_data`), wrapped in
a three-tier retry handler with post-evaluation graceful reset.

## Current status (Phase 5 -- evaluator extracted)

- The **actual runner** lives at ``run.py`` inside this package.
- The root ``run_workflow_1.py`` is a thin compatibility shim.
- The **default config** is ``config.yaml`` in this directory.
- ``evaluator.py`` contains the ``Workflow1Evaluator`` class extracted
  from the monolithic ``src/cst_optimization/factory.py``.
- ``workflow.py`` contains the local ``build_workflow_1()`` builder that
  does **not** import ``cst_optimization.factory``.
- ``run.py`` now imports from ``workflows.rfgun_single_pass.workflow``
  instead of ``cst_optimization.factory``.
- All shared infrastructure (``core/``, ``parameters/``,
  ``objectives/``, ``optimization/``) is still reused.

## Config

The default config file is ``workflows/rfgun_single_pass/config.yaml``
(extracted from the shared ``config/default.yaml`` in Phase 4).

To use a different config:

```powershell
python run_workflow_1.py --config path/to/config.yaml
```

The original ``config/default.yaml`` is **not deleted** -- it continues
to serve Workflow 2, Workflow 3, and any legacy entry points.

## Constraints respected in all phases

| Constraint | Status |
|---|---|
| Modify `config/default.yaml` | Never (only WF1 ``config.yaml`` is modified) |
| Modify `src/cst_optimization/` | Default is not to modify; if a generic API must be extracted, a report entry is written first for review, never changed in the current phase |
| Modify Workflow 2 / 3 code | Never |
| Move `examples/` | Never |
| Change runtime behaviour | Not before Phase 7 (final validation) |

## Smoke test

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "from workflows.rfgun_single_pass.evaluator import Workflow1Evaluator; print(Workflow1Evaluator.__name__)"
python -c "from workflows.rfgun_single_pass.workflow import build_workflow_1; print(build_workflow_1.__name__)"
```

All must pass without errors.
