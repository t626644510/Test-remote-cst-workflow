# Workflow 2 — HOM Antenna Multi-Project Optimisation

## Status

This package exclusively owns ``build_workflow_2`` and its retry adapter. The
strict shared ``main`` factory exposes only reusable config-to-object helpers;
there is no concrete WF2 compatibility wrapper on ``main``.

The root entry point (``run_workflow_2.py``) is now a **compatibility shim** that
``from workflows.rfgun_hom_antenna.run import main`` and delegates fully to
this package's runner::

```
python run_workflow_2.py [--auto-resume] [--heartbeat] [--warmup-from-db PATH]
```

The local ``config.yaml`` is the **Workflow2 runtime source of truth (W2-8)**.
It contains the ``workflow_2`` subtree plus top-level ``cst``, ``solver``, and
``logging`` fallback sections.  The ``run.py`` loader merges these fallbacks
before passing the effective config to ``build_workflow_2``.  The
Workflow2-effective solver timeout (7200.0 from
``workflow_2.optimization.solver.stagnation_timeout_s``) is consumed via
builder precedence (W2-6F).  ``config/default.yaml`` is no longer read by the
Workflow2 runner.

## Package structure

```
workflows/rfgun_hom_antenna/
    __init__.py      — Package metadata, version, legacy entry pointer
    run.py           — Runtime runner (argparse, config, checkpoint, heartbeat, optimisation loop)
    workflow.py      — Builder implementation (W2-4B), formerly in factory.py
    pso_wake_fit.py  — Known-mode/unknown-HOM wake fitting and optional bounded frequency fit
    config.yaml      — Workflow2 runtime config (W2-8): workflow_2 + fallback sections
    README.md        — This file
```

## Migration status

Workflow 2 lives only on ``workflow/2-rfgun-hom-antenna``. The cleaned closure
record is ``docs/workflows/wf2_known_mode_pso_closure.md``. Historical phase
evidence remains reachable through the pre-reorganisation backup refs.

## Constraints

- Do NOT repoint the scheduler away from root `run_workflow_2.py` until a dedicated scheduler migration is accepted.
- ``config/default.yaml`` is intentionally absent from this isolated branch;
  the package-local ``config.yaml`` is the sole tracked runtime source.
- Do not add new Workflow2-specific phase or project logic to shared core
  without a bounded boundary phase.
