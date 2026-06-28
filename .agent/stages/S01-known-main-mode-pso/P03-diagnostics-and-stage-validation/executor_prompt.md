You are the local execution agent for P03-diagnostics-and-stage-validation.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/skills/multi-agent-git-dev/templates/execution_report.md`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P03-diagnostics-and-stage-validation/phase_plan.md`

Task:
Add reviewable diagnostics for known-mode PSO wake fitting.

Required focus:
- Distinguish `known_modes` from fitted `modes`.
- Expose known-mode wake, unknown-mode wake, total fit, and residual wake.
- Add structured diagnostics for mode counts, labels, RMS values, normalized error, correlation, and known-mode filtered peaks.
- Ensure known-only zero-unknown-mode objective value reports actual residual SSE.
- Verify objective-level access through existing `last_fit_result`.

Do not:
- Modify CST API.
- Modify `src/cst_optimization/`.
- Change scalarization behavior.
- Implement Direction 2.
- Add live-CST validation.

Required validation:
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Write the execution report using `.agent/skills/multi-agent-git-dev/templates/execution_report.md`, then commit and push only `phase/S01-P03-diagnostics-and-stage-validation`.
