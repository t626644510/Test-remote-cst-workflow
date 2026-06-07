# Workflow 2 — HOM Antenna Multi-Project Optimisation

## Status

**Builder implementation migrated (W2-4B).** This package now OWNS the
``build_workflow_2`` implementation.  The shared factory
(``cst_optimization.factory``) re-exports it as a compatibility wrapper.

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
    config.yaml      — Workflow2 runtime config (W2-8): workflow_2 + fallback sections
    README.md        — This file
```

## Migration plan (scheme 1.5)

See `reports/restructure_plan/workflow2_current_context.md` for the full
plan and current status.

Phases:
- W2-0 — Context document                                                ✅ done
- W2-1 — No-CST characterization tests                                  ✅ done
- W2-2 — Package skeleton                                                ✅ done
- W2-3 — Config isolation                                                ✅ done
- W2-4A — Builder ownership seam                                         ✅ done
- W2-4B — Builder implementation migration                               ✅ done
- W2-5 — Orchestrator ownership assessment                               ✅ done
- W2-6 — Semantic risk cleanup plan                                      ✅ done
- W2-6A — Root docstring fix (R1)                                        ✅ done
- W2-6D — Scheduler/root shim compatibility                              ✅ done
- W2-6B — Solver timeout decision (R2)                                   ✅ done
- W2-6C — Checkpoint callback decision (R4)                              ✅ done
- W2-6E — Evaluator-only callback ownership (R4 fixed)                     ✅ done
- W2-6F — Solver timeout runtime fix (R2 fixed)                           ✅ done
- W2-7 — Root shim / package runner migration                             ✅ done
- W2-8 — Config ownership migration                                       ✅ done

## Constraints

- Do NOT repoint the scheduler away from root `run_workflow_2.py` until a dedicated scheduler migration is accepted.
- The ``workflow_2`` section in ``config/default.yaml`` is **legacy** (W2-8).
  It may remain as a compatibility reference but is no longer the runtime
  source.  A later cleanup phase can remove it.
- Do NOT merge `DualProjectOrchestrator` into shared core without
  cross-workflow evidence.
