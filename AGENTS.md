# Repository Instructions

This repository develops Python automation for CST Studio Suite accelerator-cavity simulation, semantic geometry tooling, and surrogate-model optimisation.

## Read first

Use only this maintained documentation set:

1. `docs/PROJECT_STATUS_CONTEXT.md` — authoritative detailed state;
2. `docs/AGENT_CONTEXT_RECOVERY.md` — crash/handoff recovery;
3. `docs/FUNCTIONS_AND_ENTRYPOINTS.md` — capabilities and commands;
4. `docs/CST_AUTOMATION_INTERFACES.md` — CST API and project-file authority;
5. `README.md` — Chinese human handoff;
6. `CONTRIBUTING.md` — Chinese Git/PR collaboration procedure.

This file is an automatically loaded governance/index stub, not a project-status report. `.github/` templates are maintained collaboration infrastructure. Other tracked Markdown is archival or generated output and must not become a new maintained status document.

## Hard rules

- CST API fidelity is mandatory. Use only user-supplied official CST documentation or wrappers already verified in this repository. Never invent `cst.interface`, `cst.results`, VBA, COM, command-line, or internal-file APIs.
- State units and assumptions for frequency, Q, accelerating gradient, power, field metrics, wake/impedance, and derived objectives.
- Prefer typed, object-oriented Python and clear docstrings for public classes, builders, runners, and data containers.
- Use scikit-learn for Gaussian processes, SciPy for fitting/root finding, and pymoo for multi-objective evolutionary optimisation when needed.
- Separate no-CST evidence from live-CST evidence.
- Do not run CST, kill processes, delete locks/results, clean campaigns, or launch recovery unless the user explicitly authorizes the specific action.

## Architecture

- `main` is strict shared core. It contains no concrete workflow packages, workflow entries, campaign configs, or workflow-only tests.
- Concrete packages and root compatibility shims live only on canonical `workflow/*` branches listed in `PROJECT_STATUS_CONTEXT.md`.
- `workflow/rf-cem-literature-review` is the canonical owner of RF-CEM literature ingestion, semantic review, geometry projection, and the local review GUI. It is separate from the `workflow/rf-cem-500mhz` live-campaign owner.
- Shared core is `src/cst_optimization/`:
  - `core/` — CST connection/project/solver/results/retry/cleanup/timeout;
  - `evaluation/` — evaluation DB and retry infrastructure;
  - `diagnostics.py` — diagnostics and CST message capture;
  - `factory.py` — shared config-to-object builders only;
  - `runner.py` — `BaseRunner`;
  - `checkpoint.py` — `CheckpointManager`.
- Generic CST history and reviewed STEP tooling live in `src/cst_history_extractor/` and `src/step_feature_assistant/`.
- Keep workflow behavior in its package until reuse is proven by at least two real consumers and a stable contract.
- Workflow branches are rebuilt/rebased from current `main`. Never copy shared modules back under a second name.
- Current code, tests and Git diff outrank prose and historical refs.

## Validation and hygiene

- Run commands from the repository root and use the active clone/worktree's `.venv\Scripts\python.exe` for local validation.
- Prefer targeted tests for bounded changes; run the full branch-local no-CST suite when shared core, runtime entries, persistence, recovery, schemas, config ownership, or review-session logic changes.
- Do not commit local configs, CST projects/results, PDFs, STEP inputs, databases, JSONL/NPZ, checkpoints, sessions, logs, or scratch scripts.
- Preserve user-owned dirty/untracked files. Back up before large mutation.
- Update an existing maintained document; do not add a new status/design/handoff Markdown file.
