# Repository Instructions

This project develops Python automation for CST Studio Suite microwave
accelerator-cavity simulation and surrogate-model optimisation.

## Hard Rules

- CST API fidelity is mandatory. Code that talks to CST must use only official
  CST documentation supplied by the user or wrappers already verified in this
  repository. Do not invent `cst.interface` or `cst.results` APIs.
- Scientific calculations must state units and assumptions in comments or
  docstrings when they involve frequency, Q factor, accelerating gradient,
  power, field metrics, or derived objective values.
- Prefer typed, object-oriented Python with clear docstrings for public
  classes, builders, runners, and data containers.
- Use established numerical libraries for optimisation work: scikit-learn for
  Gaussian processes, scipy for fitting/root finding, and pymoo for
  multi-objective evolutionary optimisation when needed.

## Architecture Direction

- `main` is a strict shared-core baseline. It must not contain concrete
  workflow packages, workflow entry points, campaign configs, or workflow-only
  tests.
- Concrete workflow packages and their root compatibility shims live only on
  canonical `workflow/*` branches documented in
  `docs/PROJECT_STATUS_CONTEXT.md`.
- **Shared core** is `src/cst_optimization/`:
  - `core/` — CST abstractions (connection, project, solver, retry, cleanup)
  - `evaluation/` — unified evaluation DB + retry infrastructure
  - `diagnostics.py` — error types + CST message capture + Excel logger
  - `factory.py` — shared config-to-object builders only; concrete workflow
    builders belong to workflow branches
  - `runner.py` — `BaseRunner` class for workflow CLI entry points
  - `checkpoint.py` — `CheckpointManager`
- Generic CST history extraction and human-reviewed STEP feature tooling live
  in `src/cst_history_extractor/` and `src/step_feature_assistant/` on `main`.
- Keep workflow-specific behaviour inside its workflow package until reuse is proven.
- Promote code into `src/cst_optimization/` only when it has a stable cross-workflow contract.
- Current code, tests, and git diff are authoritative. Historical reports, tags, and branch names are evidence only.
- Workflow branches are rebased or rebuilt from the current `main`; never copy
  shared modules back into a workflow package under a second name.

## Validation And Hygiene

- Use `.venv\Scripts\python.exe` for local validation.
- Prefer targeted tests for bounded changes; run the full branch-local no-CST
  suite when shared core, runtime entrypoints, persistence, recovery, or config
  ownership changes.
- Separate no-CST validation from live-CST validation and record which was run.
- Do not commit local configs, CST outputs, databases, JSONL sidecars,
  checkpoints, logs, or one-off scratch scripts.
