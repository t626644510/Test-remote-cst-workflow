You are the local execution agent for P04-direction-2-feasibility-spike follow-up.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/phase_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/executor_prompt.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/phase_review.md`
- `.agent/skills/multi-agent-git-dev/templates/execution_report.md`

Follow-up goal:
Fix documentation/evidence gaps only. Do not change the scientific conclusion unless re-running the commands changes the numeric evidence.

Required branch:
`phase/S01-P04-direction-2-feasibility-spike`

Hard constraints:
- Fetch origin and fast-forward pull this phase branch before editing.
- Do not push to `main`.
- Do not push to `stage/*`, tags, or unrelated branches.
- Push only this `phase/*` branch.
- Do not merge branches.
- Do not modify production code, tests, CST API, `src/cst_optimization/**`, scalarization semantics, or stage-level plans.

Allowed modified files:
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md`

Required fixes:
1. Add a `Commands Run` section to `feasibility_report.md` containing the exact inline Python commands used for:
   - exact and perturbed subtraction,
   - finite wake length / windowing / wake-to-impedance reconstruction,
   - fundamental decay and frequency-error-vs-length checks.
2. Update `execution_report.md` so the synthetic experiment command evidence is exact, not abbreviated as `py -c "..."`.
3. Replace the stale commit placeholder in `execution_report.md` with the relevant commit hash. If you create a follow-up commit, state both the original report commit `24eb83e76f6969c1fc2208eeebb86a47c3332505` and the new follow-up commit after it exists.
4. Replace the stale push placeholder with the actual pushed result for `origin phase/S01-P04-direction-2-feasibility-spike`.
5. Re-run the regression command unless you can justify why report-only edits do not require a rerun; record the decision and evidence.

Required regression command if run:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

After editing:
- Commit only the two allowed report files.
- Push only `phase/S01-P04-direction-2-feasibility-spike`.
- Leave P04 ready for Web Phase Review.

If the exact synthetic commands are no longer recoverable, re-run equivalent inline commands, update the numerical tables if needed, and clearly say the follow-up commands reproduced or superseded the previous evidence.
