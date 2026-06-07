# Workflow2 Next Phase Plan

This document is the current Workflow2 planning and recovery handoff after PR #1
merged W2-0 through W2-6F into `main` and the next execution direction was
accepted: run W2-7 first, then collect bounded live evidence, then decide config
ownership, then revisit the orchestrator boundary.

Use this file as a compact phase index for future web-agent planning and local
agent prompts. Code, tests, and current git diff remain authoritative; older
reports and merge notes are evidence only.

## Goals

- Continue reducing long-term token cost, context recovery cost, and coupling.
- Keep Workflow2-specific behavior inside `workflows/rfgun_hom_antenna/`
  unless reuse is proven.
- Preserve the public root command until a dedicated scheduler/public-entry
  migration is explicitly accepted.
- Keep no-CST validation and live CST smoke separate.
- Add live evidence through bounded smoke, not broad production campaigns.

## Recovery Index

- Baseline: PR #1 merged W2-0 through W2-6F into `main`.
- Active execution direction: W2-7 root shim / package runner migration.
- Public command remains `python run_workflow_2.py`.
- Scheduler remains `scripts/schedule_workflow2.ps1` targeting root
  `run_workflow_2.py` until a dedicated scheduler migration is accepted.
- Runtime config remains `config/default.yaml` -> `workflow_2` subtree.
- `workflows/rfgun_hom_antenna/config.yaml` remains a raw snapshot, not the
  runtime source.
- `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2` owns the builder.
- `src/cst_optimization/factory.py::build_workflow_2` remains a compatibility
  wrapper.
- `src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator` remains
  in shared core until W2-10.

## Recommended Phase Order

1. W2-7 — root shim / package runner migration.
2. W2-9 — bounded live CST smoke after runner migration.
3. W2-8 — config ownership decision and possible migration.
4. W2-10 — orchestrator boundary decision.

This order intentionally keeps the public entry stable before live evidence,
avoids mixing config-loader semantics into runner migration, and defers the
highest-blast-radius orchestrator decision until the runner and live behavior are
better characterized.

## Phase W2-7: Root Shim / Package Runner Migration

### Goal

Move Workflow2 runner ownership into `workflows/rfgun_hom_antenna/run.py`, while
keeping `run_workflow_2.py` as the public compatibility shim.

### Current evidence

- Root `run_workflow_2.py` still owns CLI parsing, config loading, checkpoint
  setup, heartbeat, resume handling, builder invocation, optimisation, and
  shutdown.
- `workflows/rfgun_hom_antenna/run.py` exists as the package runner location.
- Scheduler still invokes root `run_workflow_2.py --auto-resume --heartbeat`.
- Existing no-CST tests pin CLI flags, scheduler root target, root config path,
  and workflow-local builder import.

### Boundaries

- Do not repoint the scheduler.
- Do not migrate config ownership.
- Do not change `config/default.yaml` or `workflows/rfgun_hom_antenna/config.yaml`.
- Do not move `DualProjectOrchestrator`.
- Do not introduce new CST API assumptions.

### Targeted validation

```bash
python -m pytest tests/workflows/test_workflow2_scheduler_shim.py tests/workflows/test_workflow2_characterization.py -q
python -m pytest tests/workflows/test_workflow2_config_isolation.py -q
```

### Live CST

Not required for W2-7. W2-9 is the first required live-evidence gate after the
runner migration.

### Acceptance indicators

- Root command remains stable.
- Scheduler contract remains stable.
- Runtime config source remains `config/default.yaml`.
- Package runner owns the runtime body.
- Root script is a thin compatibility shim.
- Tests are updated to describe package-runner ownership without claiming that
  scheduler or config ownership has migrated.

## Phase W2-9: Bounded Live Smoke

### Goal

Collect the first post-runner-migration Workflow2 live CST evidence using the
current public command and current config source.

### Required evidence

- Exact command.
- Explicit timeout or stop condition.
- Output and log location outside tracked source, unless a concise evidence
  report is intentionally added.
- Effective config source and solver timeout.
- Checkpoint behavior: one record per logical evaluation.
- CST process cleanup state after the run.
- Whether CST Studio Suite was actually exercised.

### Boundaries

- No production campaign.
- Do not commit `.ckpt`, `.jsonl`, database, CST result, or scratch artifacts.
- No destructive process manipulation unless explicitly scoped.
- No default-config changes unless the phase explicitly authorizes them.
- No CST API assumptions beyond existing verified wrappers or user-provided
  official interface documentation.

### Targeted validation

First rerun the W2-7 no-CST tests, then run one bounded live smoke with recorded
cleanup state.

### Live CST

Required.

## Phase W2-8: Config Ownership

### Goal

Decide and implement whether `workflows/rfgun_hom_antenna/config.yaml` becomes
the runtime source, or remains a snapshot while `config/default.yaml` stays
authoritative.

### Required evidence

- Exact comparison between the local config and `config/default.yaml["workflow_2"]`.
- Clear precedence rules for fallback sections: `cst`, `solver`, and `logging`.
- Tests proving the effective solver timeout remains `7200.0` from
  `workflow_2.optimization.solver.stagnation_timeout_s`.
- Tests proving config source and scheduler/root behavior after any migration.

### Boundaries

- Do not mix config ownership with orchestrator migration.
- Do not leave two long-term runtime sources of truth.
- Do not silently drop fallback values such as `cst.library_path`,
  `logging.output_dir`, or solver `settle_s`.
- Do not change default production behavior without an explicit phase scope.

### Targeted validation

```bash
python -m pytest tests/workflows/test_workflow2_config_isolation.py tests/workflows/test_workflow2_characterization.py tests/workflows/test_workflow2_scheduler_shim.py -q
```

Add config-loader tests if a loader is introduced.

### Live CST

Not required for implementation. Recommended after acceptance if the runtime
config source changes.

## Phase W2-10: Orchestrator Boundary Decision

### Goal

Decide whether `DualProjectOrchestrator` should remain in shared core, move into
Workflow2, or be split behind a smaller generic interface.

### Required evidence

- Current import consumers.
- Construction sites.
- Generic responsibilities versus Workflow2-specific responsibilities.
- Impact on WF1/WF3 and shared core tests.
- Live evidence from W2-9 before any risky boundary change.

### Boundaries

- Do not promote shared core without cross-workflow evidence.
- Do not combine with config or scheduler migration.
- Do not invent CST APIs.
- Do not move high-blast-radius code without targeted and broader validation.

### Targeted validation

- If decision-only: no tests required, but cite current code evidence.
- If code moves: run Workflow2 tests plus affected shared-core tests.

### Live CST

Not required for decision-only work. Required after any runtime-affecting
orchestrator move.

## Local-Agent Prompt Contract Reminder

Each local-agent prompt should include only:

- Objective: one sentence.
- Current facts: at most five.
- Read first: bounded file list.
- Allowed edits and forbidden edits.
- Targeted validation commands.
- Return format: changed files, rationale, tests run, and residual risks.

Do not ask a local agent to reread the whole repository by default. Do not ask
it to run live CST unless the phase explicitly scopes command, timeout or stop
condition, output location, cleanup checks, and acceptance criteria.
