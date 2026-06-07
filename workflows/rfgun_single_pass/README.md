# Workflow 1 -- RF Gun Single-Pass SAO Optimisation

## Status: VALIDATED

The Workflow 1 separation is complete and validated end-to-end with
both no-CST smoke tests and a live CST Studio Suite run.

## Purpose

Single-project single-pass frequency-domain Surrogate-Assisted
Optimisation (SAO) for the X-band RF gun cavity.  Workflow 1 evaluates
a single CST project with a one-pass solve (fixed `f_data`), wrapped in
a three-tier retry handler with post-evaluation graceful reset.

## Validation

| Check | Result | Detail |
|---|---|---|
| no-CST smoke tests | **12/12 passed** | ``pytest tests/workflows/test_rfgun_single_pass_imports.py -v`` |
| Live CST smoke | **PASS** | ``--n-initial 1 --n-iter 0``, all 7 metrics computed, no Python exceptions |
| Historical pointer | ``milestone/workflow1-single-pass-baseline`` tag |

## Running

```powershell
# Production run (after localising config paths):
python run_workflow_1.py --config workflows/rfgun_single_pass/config.local.yaml --n-initial 1 --n-iter 0

# Quick smoke test (no CST):
pytest tests/workflows/test_rfgun_single_pass_imports.py -v
```

**Important:** ``config.local.yaml`` is a local copy of the config with
machine-specific paths.  It should not be committed to the repository.
Copy ``workflows/rfgun_single_pass/config.yaml`` to ``config.local.yaml``
and adjust the ``cst.library_path`` and ``project.cst_path`` to match
your environment.

### CLI flags

| Flag | Description |
|---|---|
| ``--config`` | Path to YAML config (default: ``config.yaml`` next to runner) |
| ``--seed`` | Override optimizer seed |
| ``--n-iter`` | Override ``n_iterations`` |
| ``--n-initial`` | Override ``n_initial_samples`` |

## Structure

```
run_workflow_1.py                          # compatibility shim
workflows/rfgun_single_pass/
    __init__.py                            # package marker
    config.yaml                            # WF1-specific config (8 sections, 13 params, 7 objectives)
    run.py                                 # CLI runner + build_arg_parser()
    workflow.py                            # local build_workflow_1() builder
    evaluator.py                           # Workflow1Evaluator class
    README.md                              # this file
tests/workflows/
    test_rfgun_single_pass_imports.py       # 12 no-CST smoke tests
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

**Not imported (intentionally excluded):**
- ``cst_optimization.factory``
- ``objectives/wakefield.py``
- ``objectives/antenna.py``

## Branch recommendation

This branch (``workflow/1-rfgun-single-pass``) can be kept as a
long-lived Workflow 1 branch for ongoing development.  It should not
be merged into ``main`` until the Workflow 2 and Workflow 3
separation strategy is decided.  Generic improvements can be
cherry-picked into ``main`` as needed.
