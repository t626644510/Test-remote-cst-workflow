# CST optimisation shared core

This `main` branch is the strict shared baseline for the CST automation and
optimisation project. Concrete RF workflows do not live on `main`; check out a
canonical `workflow/*` branch for runnable campaign entry points and configs.

Shared packages on `main`:

- `cst_optimization`: verified CST wrappers, physics, objectives, optimisation,
  persistence, diagnostics, and reusable workflow contracts.
- `cst_history_extractor`: CST history extraction and recipe manifests.
- `step_feature_assistant`: review-first STEP geometry and feature semantics.

Install and validate without CST:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
```

See `docs/PROJECT_STATUS_CONTEXT.md` for branch names, workflow entry points,
runtime requirements, validation baselines, and recovery notes.
