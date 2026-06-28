You are the local execution agent for P01-fixed-mode-core.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/skills/multi-agent-git-dev/templates/execution_report.md`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/phase_plan.md`

Task:
Implement core known/fixed-mode support in `workflows/rfgun_hom_antenna/pso_wake_fit.py`, with tests in `tests/workflows/test_workflow2_pso_wake_fit.py`.

Required focus:
- Add a typed known-mode container for fixed longitudinal resonator modes.
- Compute known-mode wake from `frequency_hz`, `q`, and `r_over_q_ohm` using the existing form-factor convention.
- Ensure fixed known modes are not optimized by PSO.
- Filter known-mode-matched peaks from unknown-mode PSO variables.
- Preserve default no-known-mode behavior.

Do not:
- Parse workflow config; that belongs to P02.
- Modify `wakefield_objective.py`.
- Modify CST API or `src/cst_optimization/`.
- Implement Direction 2.

Required validation:
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Write the execution report using `.agent/skills/multi-agent-git-dev/templates/execution_report.md`, then commit and push only `phase/S01-P01-fixed-mode-core`.
