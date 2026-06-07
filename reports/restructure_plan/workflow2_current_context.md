# Workflow2 Current Context

This is the compact handoff for Workflow2 after PR #1 was merged to `main`.
Use it as the first Workflow2 read before opening historical decision records.

## Authority

- Governance: `reports/restructure_plan/agent_operating_charter.md`
- Safety checklist: `reports/restructure_plan/agent_standing_rules.md`
- Current facts come from code, tests, and git diff; reports are evidence only.
- Bounded live smoke and clean direct merge are allowed by default when the
  phase plan names the scope and validation gate.

## Merge Status

- PR #1, `docs/workflow2-context-compaction` -> `main`, is merged.
- Merge commit: `b1829c6` (`Merge Workflow2 integration: W2-0 through W2-6F`).
- Included work: W2-0 through W2-6F.
- Current branch baseline: `main` contains the Workflow2 package skeleton,
  builder migration, callback ownership fix, solver-timeout fix, and tests.

## Runtime Shape

| Component | Current state |
|-----------|---------------|
| Public entry | `run_workflow_2.py` remains the public entrypoint |
| Scheduler | still targets root `run_workflow_2.py` |
| Runtime config | `config/default.yaml` -> `workflow_2` subtree |
| Workflow-local config | `workflows/rfgun_hom_antenna/config.yaml` is a snapshot, not runtime source |
| Builder owner | `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2` |
| Factory path | `src/cst_optimization/factory.py::build_workflow_2` is a compatibility wrapper |
| Orchestrator | `src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator` remains in core path |

## Accepted Semantic State

- R1 docstring fixed: root docstring describes one CST DesignEnvironment with
  sequential project execution.
- R2 solver timeout fixed: `workflow_2.optimization.solver` overrides fallback
  solver keys; effective Workflow2 timeout is `7200.0` from
  `workflow_2.optimization.solver.stagnation_timeout_s`.
- R4 checkpoint callback fixed: evaluator wrappers fire one callback per
  logical evaluation; `DualProjectOrchestrator.execute()` no longer fires it.
- R6 scheduler/root compatibility characterized: CLI flags and scheduler root
  entry are pinned by tests.

## Current Boundaries

- Do not promote shared core just because Workflow2 convenience code exists.
- Do not move `DualProjectOrchestrator` without a dedicated boundary phase.
- Do not make `workflows/rfgun_hom_antenna/config.yaml` the runtime source
  without a config-ownership migration phase.
- Do not repoint scheduler/root entry without preserving CLI compatibility.
- Live Workflow2 smoke is allowed when bounded and recorded; long campaigns
  still need an explicit phase plan.

## Key Evidence Documents

| Document | Use |
|----------|-----|
| `workflow2_solver_timeout_decision.md` | Historical R2 analysis plus W2-6F supersession |
| `workflow2_checkpoint_callback_ownership_decision.md` | Historical R4 analysis plus W2-6E supersession |
| `workflow2_orchestrator_ownership_assessment.md` | W2-5 evidence for keeping orchestrator out of new shared surfaces |
| `workflow2_semantic_risk_cleanup_plan.md` | Historical risk map for R1/R2/R4/R6 |
| `workflow2_main_pr_summary.md` | Historical PR #1 merge summary |

## Next Direction

Use `reports/restructure_plan/workflow2_next_phase_plan.md` for the next
planning handoff to the web agent. The next work should focus on root
shim/scheduler readiness, config ownership, bounded live smoke, and the
orchestrator boundary decision.
