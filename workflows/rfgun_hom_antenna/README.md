# Workflow 2 — HOM Antenna Multi-Project Optimisation

## Status

**Skeleton only.** No runtime has been migrated yet.

The legacy entry point remains at the project root:

```
python run_workflow_2.py [--auto-resume] [--heartbeat] [--warmup-from-db PATH]
```

## Package structure

```
workflows/rfgun_hom_antenna/
    __init__.py      — Package metadata, version, legacy entry pointer
    run.py           — Placeholder / compatibility planning module (no CST calls)
    config.yaml      — (future) workflow-specific config
    README.md        — This file
```

## Migration plan (scheme 1.5)

See `reports/restructure_plan/workflow2_current_context.md` for the full
plan and current status.

Phases:
- W2-0 — Context document
- W2-1 — No-CST characterization tests
- **W2-2 — Package skeleton** ← current
- W2-3 — Config isolation
- W2-4 — Builder ownership migration
- W2-5 — Orchestrator ownership assessment
- W2-6 — Fix documented semantic risks
- W2-7 — Core candidate evaluation
- W2-8 — Minimal live CST validation

## Constraints

- Do NOT move `run_workflow_2.py` until the scheduler is updated.
- Do NOT rely on `config/default.yaml` after W2-3.
- Do NOT merge `DualProjectOrchestrator` into shared core without
  cross-workflow evidence.
