# Project Context Capsule

Date: 2026-06-08

This is the compact recovery entry point for the repository after the
environment-prune pass. Code, tests, and current git diff are authoritative;
older reports and deleted branches are recoverable through git history,
milestone tags, and the external cleanup bundle.

## Long-Term Goal

Build a maintainable Python framework for automatic CST Studio Suite microwave
accelerator-cavity simulation and surrogate-model optimisation while reducing
long-term context cost, branch sprawl, and workflow coupling.

## Current Framework

| Area | Current role |
|------|--------------|
| `src/cst_optimization/` | Shared core: CST wrappers, orchestration utilities, objectives, parameters, optimisers, physics helpers |
| `workflows/rfgun_sao/` | Current Workflow1-style SAO package and active `run_workflow_1.py` target |
| `workflows/rfgun_single_pass/` | Validated single-pass reference package |
| `workflows/rfgun_hom_antenna/` | Workflow2 package: runner, config, builder, and HOM antenna optimisation |
| `run_workflow_*.py` | Root compatibility entrypoints |
| `config/` | Legacy/shared defaults and Workflow3 config |
| `tests/` | Current no-CST regression and contract tests |

## Workflow Status

- Workflow1 / SAO: active package is `workflows/rfgun_sao/`; the older
  `workflows/rfgun_single_pass/` package remains as a validated reference.
- Workflow2 / HOM antenna: W2-0 through W2-10 are complete on `main`.
  `run_workflow_2.py` is a shim, runtime ownership lives in
  `workflows/rfgun_hom_antenna/run.py`, and runtime config lives in
  `workflows/rfgun_hom_antenna/config.yaml`.
- Workflow3 / tolerance and recovery work: historical branch tips were pruned
  from branch refs and preserved through milestone tags. Any future WF3
  package extraction should begin from current `main` plus the milestone tags.

## Key Historical Facts

- The monolith was split into workflow-specific branches to reduce coupling.
- Workflow2 migration is accepted: package runner ownership, workflow-local
  config ownership, bounded live smoke evidence, and orchestrator boundary
  decision are complete.
- `DualProjectOrchestrator` remains in shared core pragmatically; this is not
  proof of cross-workflow generic utility.
- Old phase reports and stage branches were removed from the working tree to
  keep future context small. Detailed history is retained by git and tags.

## Milestone Tags

| Tag | Meaning |
|-----|---------|
| `milestone/pre-environment-prune-2026-06-08` | Main before this cleanup |
| `milestone/workflow2-final-2026-06-08` | Final Workflow2 state |
| `milestone/workflow1-single-pass-baseline` | Validated single-pass baseline |
| `milestone/workflow3-tolerance-analysis-baseline` | Workflow3 tolerance-analysis baseline |
| `milestone/monolith-before-workflow1-split` | Pre-split monolith |
| `milestone/wf3-analysis-final` | WF3 tolerance-analysis final branch tip |
| `milestone/wf3-sweep-live-final` | WF3 tolerance-sweep live final branch tip |
| `milestone/wf3-campaign-final` | WF3 tolerance-campaign final local branch tip |

External refs backup:
`C:\Users\lau\cst_ver3_cleanup_backups\2026-06-08-environment-prune`.

## Cleanup Policy

- Keep `main` plus only durable workflow baseline branches.
- Keep Markdown small and current-state oriented.
- Keep tests that protect current public contracts and runtime behaviour.
- Restore old evidence from git history, tags, or the cleanup bundle instead
  of reintroducing phase report sprawl.
