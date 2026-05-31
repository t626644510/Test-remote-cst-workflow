# Workflow 1 -- RF Gun Single-Pass SAO Optimisation

## Purpose

Single-project single-pass frequency-domain Surrogate-Assisted
Optimisation (SAO) for the X-band RF gun cavity.  Workflow 1 evaluates
a single CST project with a one-pass solve (fixed `f_data`), wrapped in
a three-tier retry handler with post-evaluation graceful reset.

## Current status (Phase 3 -- runner migrated)

- The **actual runner** lives at ``run.py`` inside this package.
- The root ``run_workflow_1.py`` is a thin compatibility shim that
  delegates to ``workflows.rfgun_single_pass.run.main``.
- CLI behaviour, config path, logging, checkpoint, and optimizer are
  identical to the pre-migration state.
- Phase 4 will split the config schema; Phase 5 will extract the
  evaluator.

## Constraints respected in all phases

| Constraint | Status |
|---|---|
| Modify `config/default.yaml` | Not before Phase 4 |
| Modify `src/cst_optimization/` | Default is *not* to modify; if a generic API must be extracted, a report entry is written first for review, never changed in the current phase |
| Modify Workflow 2 / 3 code | Never |
| Move `examples/` | Never |
| Change runtime behaviour | Not before Phase 7 (final validation) |

## Smoke test

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "from workflows.rfgun_single_pass.run import main; print(main.__name__)"
```

All files must compile without errors.  The ``--help`` flag must print
the expected argument list.  The import test must print ``main``.
