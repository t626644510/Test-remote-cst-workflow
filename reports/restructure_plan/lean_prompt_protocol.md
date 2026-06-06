# Lean Prompt Protocol

Guidelines for writing token-efficient prompts for local agents.

## Current status

For Workflow 2 and later planning, this protocol is subordinate to
`reports/restructure_plan/agent_operating_charter.md`. Use that charter for
role boundaries, Scheme 1.5 direction, and the default local-agent prompt
contract. This file remains a compact style guide.

## Rationale

Each prompt consumes context window and API tokens.  Long prompts that repeat
historical context, list every file in the repo, or describe well-known
patterns waste capacity that could be spent on actual reasoning.  The
protocol below reduces prompt bloat without sacrificing clarity.

## Principles

### 1. Delta-only by default

State only what **changed** since the last phase or the last prompt. Assume
the agent has access to:

- `reports/restructure_plan/agent_operating_charter.md` — current governance.
- `reports/restructure_plan/agent_standing_rules.md` — standing boundaries.
- `reports/restructure_plan/lean_prompt_protocol.md` — this protocol.
- `CLAUDE.md` — project-level instructions.

Do **not** repeat the full list of forbidden artifacts, protected areas, or
accepted-phase history unless it has changed.

`current_agent_state.md` may be stale. Use it only as a hint, never as an
authoritative planning source.

### 2. Reference, don't reproduce

Instead of:

> "Remember the TSE4 rules: max_mean checks, min_mean checks, non-finite
> handling, expanded_blocked logic…"

Write:

> "See TSE4 report for rule semantics (reports/restructure_plan/tse4_wf3_tolerance_sweep_recommendation_no_cst_report.md)."

### 3. Limit scope

- **Do not** ask the local agent to inspect the whole repository.
- **Do not** enumerate every file that might be relevant.
- Use an explicit **"Read only these files first"** section listing the 2–5
  files the agent should load to begin.

### 4. Minimal report format for patches

Patch phases (small fixes, polish, hardening) use a short format:

```markdown
## <phase-label>

### Changes
- <one line per file change>

### Validation
<paste command and result>

### Explicit statements
| Item | Status |
|------|--------|
| CST | No |
| Destructive action | No |
| Runtime config changed | No |
```

### 5. Full reports only for major phases

Phases that introduce new capabilities, change architecture, or include live
CST evidence may produce a full report with scope, design, implementation,
tests, validation, and explicit statements. Patch-level work should not create
new reports by default.

### 6. Use integration branches

For accepted phases, future work should start from the latest integration
branch when possible, reducing repeated diff expansion across merged history.

## Prompt template

```
Goal:
<one sentence>

Current facts:
- <fact 1>
- <fact 2>
- <fact 3>

Read first:
- <file1>
- <file2>
- <file3>

Allowed edits:
- <scope>

Forbidden:
- no full-repo scan unless the bounded read set cannot explain the issue
- no changes outside <scope>
- no new CST API assumptions
- no historical report conclusions without code verification

Validation:
- targeted: <commands>
- broader only if shared core changed: <commands>

Return:
- changed files
- rationale
- tests run
- residual risks
```
