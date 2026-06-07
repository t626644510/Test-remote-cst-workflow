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

- Keep workflow-specific behaviour inside its workflow package until reuse is
  proven.
- Promote code into `src/cst_optimization/` only when it has a stable,
  cross-workflow contract or is clearly generic.
- Current code, tests, and git diff are authoritative. Historical reports,
  tags, and branch names are evidence only.
- Maintain root compatibility shims (`run_workflow_1.py`, `run_workflow_2.py`,
  `run_workflow_3.py`) unless a scoped migration explicitly changes them.

## Validation And Hygiene

- Use `.venv\Scripts\python.exe` for local validation.
- Prefer targeted tests for bounded changes; run broader tests when shared
  core, runtime entrypoints, persistence, recovery, or config ownership change.
- Separate no-CST validation from live-CST validation and record which was run.
- Do not commit local configs, CST outputs, databases, JSONL sidecars,
  checkpoints, logs, or one-off scratch scripts.
