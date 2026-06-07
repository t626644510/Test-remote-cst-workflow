# Workflow 2 — HOM Antenna Multi-Project Optimisation

## Status

**Builder implementation migrated (W2-4B).** This package now OWNS the
``build_workflow_2`` implementation.  The shared factory
(``cst_optimization.factory``) re-exports it as a compatibility wrapper.

The root entry point imports ``build_workflow_2`` from this package::

```
python run_workflow_2.py [--auto-resume] [--heartbeat] [--warmup-from-db PATH]
```

The local ``config.yaml`` is a **staging / snapshot** of the ``workflow_2``
section from the global ``config/default.yaml``.  It is **not yet consumed**
by the runtime.  The root entry point and all scheduler invocations still
read the legacy config.  See the header comment in ``config.yaml`` for the
known W2-1 solver-timeout discrepancy and migration constraints.

## Package structure

```
workflows/rfgun_hom_antenna/
    __init__.py      — Package metadata, version, legacy entry pointer
    run.py           — Placeholder / compatibility planning module (no CST calls)
    workflow.py      — Builder implementation (W2-4B), formerly in factory.py
    config.yaml      — (future) workflow-specific config
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

## Constraints

- Do NOT move `run_workflow_2.py` until the scheduler is updated.
- Do NOT treat `workflows/rfgun_hom_antenna/config.yaml` as the runtime
  source of truth until a later root-shim / config-loader migration is
  implemented and tested.
- Do NOT remove or stop maintaining the ``workflow_2`` section in
  ``config/default.yaml`` until that migration is accepted.
- Do NOT merge `DualProjectOrchestrator` into shared core without
  cross-workflow evidence.
