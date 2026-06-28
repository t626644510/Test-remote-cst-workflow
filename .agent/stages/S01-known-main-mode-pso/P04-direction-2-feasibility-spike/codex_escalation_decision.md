# Codex Escalation Decision: P04-direction-2-feasibility-spike

## Decision
REQUIRE_FINAL_REPORT_ONLY_FIX

## Context
Web Phase Review escalated P04 to Codex after the same evidence issue remained unresolved across two reviews. The reports contain useful scientific conclusions and the phase stayed within scope, but the synthetic experiment command evidence remains incomplete: several inline command blocks still contain ellipses or omitted loop logic.

## Codex Judgment
P04 should not be accepted yet, and the evidence standard should not be relaxed.

Reason:

- P04 is a research spike whose conclusion may decide whether Direction 2 becomes a later implementation stage.
- The phase plan explicitly required recording inline Python synthetic experiment commands and conclusions.
- The current report includes quantitative tables, but some command bodies are not copy-pasteable and therefore cannot independently reproduce the reported numbers.
- The missing evidence is narrow and report-only. It does not require production code, test changes, CST access, or Web Phase Planner generating another follow-up prompt.

## Authorized Final Action
Codex authorizes exactly one final report-only correction by the local execution agent.

Allowed files:

- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/execution_report.md`

Forbidden:

- Production code changes.
- Test file changes.
- CST API changes.
- `src/cst_optimization/` changes.
- Scalarization changes.
- New persistent experiment scripts.
- Any `main` or `stage/*` push.

## Required Fix
Replace abbreviated command sections containing `...` with complete reproducibility evidence.

Acceptable evidence forms:

1. Fully copy-pasteable inline commands, preferably PowerShell here-string commands of the form:

   ```powershell
   @'
   # complete Python experiment body
   '@ | py -
   ```

2. A complete command transcript in `feasibility_report.md` that includes all Python code needed to reproduce each table, without referring to uncommitted scripts.

The report must include enough command/code detail to reproduce:

- Exact fundamental subtraction.
- Frequency perturbation table.
- Q perturbation table.
- R/Q perturbation table.
- Fundamental decay and frequency-error-vs-length table.
- Finite wake length / windowing / wake-to-impedance reconstruction summary.

## Required Validation
The local execution agent must rerun:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

The local execution agent must also rerun or otherwise verify the synthetic experiment commands reported in `feasibility_report.md`.

## Completion Standard
After this final report-only fix:

- Web Phase Planner may review once more only to verify the Codex-required report evidence was added.
- If the commands are complete and no scope violations occurred, P04 may be marked `PHASE_ACCEPTED`.
- If the same exact-command evidence remains incomplete, P04 should be escalated to the user as a process failure rather than generating more follow-up prompts.

## Status
P04 remains not accepted until this final report-only fix is completed and reviewed.
