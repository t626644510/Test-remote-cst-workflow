You are the local execution agent for P04-direction-2-feasibility-spike.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/phase_plan.md`
- `.agent/skills/multi-agent-git-dev/templates/execution_report.md`

Your task:
Execute only the P04 research spike and write the feasibility evidence. This is not a production implementation phase.

Required branch:
`phase/S01-P04-direction-2-feasibility-spike`

Hard constraints:
- Fetch origin and fast-forward pull the assigned phase branch before reading local workflow files.
- Do not push to `main`.
- Do not push to `stage/*`, tags, or unrelated branches.
- Push only the current `phase/*` branch after the report files are committed.
- Do not merge branches.
- Do not modify stage-level plans.
- Do not modify `.agent/skills/**`.
- Do not modify production code, CST API, `src/cst_optimization/**`, `tests/**`, or scalarization semantics.
- Do not implement Direction 2 production code.

Allowed modified files:
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md`

Work to perform:
1. Inspect existing no-CST utilities and prior phase evidence as needed.
2. Run a no-CST synthetic experiment with a known fundamental plus multiple HOMs.
3. Test exact fundamental subtraction against the known HOM-only residual.
4. Test sensitivity to small frequency, Q, and R/Q perturbations of the fundamental.
5. Evaluate finite wake length and truncation/windowing effects on residual wake-to-impedance reconstruction.
6. Write a concise go/no-go feasibility report.
7. Run the required regression test.
8. Write the execution report using the shared execution-report template.
9. Commit the two report files and push only this phase branch.

Write the feasibility report to:
`.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`

Write the execution report to:
`.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md`

Required regression command:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Synthetic experiment guidance:
- Keep the experiment no-CST.
- Prefer inline Python commands or temporary local-only scratch code; do not commit scripts unless you stop and justify a blocker.
- Use existing wake-fitting/reconstruction utilities where practical rather than duplicating production logic.
- Record exact commands, synthetic mode parameters, metrics, and conclusions in the feasibility report.
- Include enough quantitative evidence for a reviewer to understand whether Direction 2 should be `GO`, `NO-GO`, or `CONDITIONAL-GO`.

Minimum report evidence:
- Fundamental and HOM synthetic mode table.
- Exact subtraction residual quality.
- Frequency/Q/RQ perturbation sensitivity table or equivalent quantitative summary.
- Finite wake length / windowing reconstruction comparison.
- Explicit CST convention checks required before any production Direction 2 implementation.
- Assumptions and limitations.
- Clear final recommendation.

If pull, commit, push, regression testing, or the synthetic experiment is blocked, stop and document the blocker in `execution_report.md`. Do not ask for review of an invisible or stale local diff.
