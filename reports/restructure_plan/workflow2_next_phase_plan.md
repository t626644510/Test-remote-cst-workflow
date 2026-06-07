# Workflow2 Next Phase Plan

This document is a technical planning handoff for the web agent. It defines
the next Workflow2 directions after PR #1 merged W2-0 through W2-6F into
`main`. The web agent should use this to design bounded local-agent prompts;
it should not treat historical reports as current state without checking code.

## Goals

- Continue reducing long-term token cost, context recovery cost, and coupling.
- Keep Workflow2-specific behavior inside `workflows/rfgun_hom_antenna/`
  unless reuse is proven.
- Preserve root entry and scheduler compatibility until a bounded migration
  phase explicitly changes them.
- Add live evidence through bounded smoke, not broad campaigns.

## Phase W2-7: Root Shim And Scheduler Readiness

Decision to make:

- Whether `run_workflow_2.py` should stay as the public entry with a thinner
  delegation body, or whether scheduler/runtime should move toward
  `workflows/rfgun_hom_antenna/run.py`.

Required evidence:

- AST or source tests proving existing CLI flags remain available:
  `--auto-resume`, `--heartbeat`, `--warmup-from-db`.
- Scheduler compatibility check for `scripts/schedule_workflow2.ps1`.
- No live CST required unless the implementation changes runtime invocation.

## Phase W2-8: Config Ownership

Decision to make:

- Whether `workflows/rfgun_hom_antenna/config.yaml` becomes the runtime source
  or remains a snapshot while `config/default.yaml` remains authoritative.

Required evidence:

- Exact comparison between committed workflow-local config and
  `config/default.yaml["workflow_2"]`.
- Clear precedence rules for top-level fallback sections: `cst`, `solver`,
  `logging`.
- Tests proving solver timeout still resolves to `7200.0` from
  `workflow_2.optimization.solver.stagnation_timeout_s`.

## Phase W2-9: Bounded Live Smoke

Purpose:

- Collect first post-merge Workflow2 live smoke evidence using the current root
  entry and current config path.

Minimum requirements:

- One bounded smoke command with explicit timeout or stop condition.
- Output and logs outside tracked source unless a concise evidence report is
  intentionally added.
- Record CST process cleanup state after the run.
- Record checkpoint behavior: one record per logical evaluation.
- Record effective solver timeout/config source.

Live smoke is allowed by default under the charter when scoped this way.

## Phase W2-10: Orchestrator Boundary Decision

Decision to make:

- Keep `DualProjectOrchestrator` in `src/cst_optimization/core/`, migrate it
  into `workflows/rfgun_hom_antenna/`, or extract a smaller generic interface.

Default recommendation:

- Do not move it until W2-7 through W2-9 provide enough evidence. Treat the
  class as high-blast-radius because it currently mixes generic utilities with
  Workflow2-specific phase labels and CST recovery details.

Required evidence:

- Current import consumers and construction sites.
- List of truly generic responsibilities vs Workflow2-specific logic.
- Targeted tests if any boundary changes touch shared core.

## Web Agent Output Contract

For each phase, return a local-agent prompt with:

- one-sentence objective;
- at most five current facts;
- bounded read-first files;
- allowed and forbidden edits;
- targeted validation commands;
- residual risks and live/no-CST status.
