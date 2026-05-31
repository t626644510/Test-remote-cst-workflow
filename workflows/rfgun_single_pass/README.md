# Workflow 1 -- RF Gun Single-Pass SAO Optimisation

## Purpose

Single-project single-pass frequency-domain Surrogate-Assisted
Optimisation (SAO) for the X-band RF gun cavity.  Workflow 1 evaluates
a single CST project with a one-pass solve (fixed `f_data`), wrapped in
a three-tier retry handler with post-evaluation graceful reset.

## Current status (Phase 7 -- finalised)

Workflow 1 has been separated from the monolithic
``src/cst_optimization/factory.py`` into its own package under
``workflows/rfgun_single_pass/``.  The separation is stable: no-CST
smoke tests pass, imports are clean, and the CLI/config/evaluator
are independently testable.

## Running

```powershell
# Default config:
python run_workflow_1.py

# Explicit config:
python run_workflow_1.py --config workflows/rfgun_single_pass/config.yaml

# Via module:
python -m workflows.rfgun_single_pass.run

# CLI overrides:
python run_workflow_1.py --seed 43 --n-iter 5 --n-initial 3
```

## Default config

``workflows/rfgun_single_pass/config.yaml`` (extracted from the shared
``config/default.yaml`` in Phase 4).

## Structure

```
run_workflow_1.py                          # compatibility shim
workflows/rfgun_single_pass/
    __init__.py                            # package marker
    config.yaml                            # WF1-specific config
    run.py                                 # CLI runner + build_arg_parser()
    workflow.py                            # local build_workflow_1() builder
    evaluator.py                           # Workflow1Evaluator class
    README.md                              # this file
    BRANCH_CONTEXT.md                      # branch rules and roadmap
```

## Dependencies

**Shared (reused from ``src/cst_optimization/``):**
- ``core/`` (CSTConnection, SolverRunner, ResultReader, EvaluationRetryHandler)
- ``parameters/`` (ParameterSet, GeometryParameter)
- ``objectives/`` (frequency, quality, field, modes, registry)
- ``optimization/`` (SAO, acquisition functions)
- ``physics/`` (formulas, poynting, heating)
- ``checkpoint.py`` (CheckpointManager)
- ``workflows/recovery.py`` (EvaluationResult, EvaluationStatus)

**Not imported (WF2/WF3 specific, not needed for WF1):**
- ``cst_optimization.factory`` (monolithic builder -- was WF1 entry point)
- ``objectives/wakefield.py`` (WF2 HOM analysis)
- ``objectives/antenna.py`` (WF2 absorption analysis)
- ``optimization/saea.py`` (WF2/3 evolutionary algorithm)

## Smoke tests

No-CST smoke tests verify structural integrity without launching CST:

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v
```

## Live CST validation

This branch has only passed no-CST smoke tests.  Numerical / behavioural
equivalence with the pre-separation state must be validated with a
small live CST run (e.g. ``--n-initial 1 --n-iter 0``) on a machine
with CST Studio Suite installed before merging.
