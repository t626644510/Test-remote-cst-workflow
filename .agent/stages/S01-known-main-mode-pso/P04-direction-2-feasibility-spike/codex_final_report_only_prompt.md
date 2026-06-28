You are the local execution agent for a Codex-authorized final P04 report-only fix.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/phase_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/executor_prompt.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/phase_review.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/codex_escalation_decision.md`

Required branch:
`phase/S01-P04-direction-2-feasibility-spike`

Task:
Perform exactly one final report-only reproducibility fix for P04. Do not implement Direction 2.

Allowed files:
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md`

Forbidden:
- Production code changes.
- Test changes.
- CST API changes.
- `src/cst_optimization/` changes.
- Scalarization changes.
- Persistent experiment scripts.
- Main, stage, tag, or unrelated branch pushes.

Required report fix:
Replace all abbreviated inline command evidence that uses `...` or omitted loop logic with complete, copy-pasteable command evidence.

Preferred format:

```powershell
@'
# complete Python experiment body
'@ | py -
```

The command evidence must reproduce:
- Exact fundamental subtraction.
- Frequency perturbation table.
- Q perturbation table.
- R/Q perturbation table.
- Fundamental decay table.
- Frequency-error-vs-length table.
- Finite wake length / windowing / wake-to-impedance reconstruction summary.

You may consolidate experiments into one or more complete here-string commands. The commands do not need to be short; they need to be complete and reproducible without uncommitted scripts.

Required validation:
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Also run the reported synthetic experiment command(s), or explain in `execution_report.md` exactly which command(s) were rerun and what output matched the report.

Commit and push:
1. Commit only the allowed report files.
2. Push only `phase/S01-P04-direction-2-feasibility-spike`.

If this cannot be completed without changing forbidden files, stop and write the blocker in `execution_report.md`.
