You are the local execution agent for P02-objective-config-integration.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/skills/multi-agent-git-dev/templates/execution_report.md`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P02-objective-config-integration/phase_plan.md`

Task:
Wire `pso_fit.known_modes` into the Workflow-2 PSO wake fitting input builder.

Required focus:
- Parse longitudinal known modes into `KnownMode`.
- Validate required fields and units clearly.
- Ensure longitudinal `q > 0.5`.
- Reject non-finite or negative `frequency_tolerance_hz`.
- Keep `known_modes` config longitudinal-only for this stage.
- Verify `LongitudinalImpedanceObjective` passes configured known modes through the existing builder path.

Do not:
- Modify CST API.
- Modify `src/cst_optimization/`.
- Change scalarization behavior.
- Implement Direction 2.
- Add transverse known-mode production support.

Required validation:
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Write the execution report using `.agent/skills/multi-agent-git-dev/templates/execution_report.md`, then commit and push only `phase/S01-P02-objective-config-integration`.
