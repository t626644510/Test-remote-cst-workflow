# Agent Operating Charter

This document is the reusable governance baseline for future development in
this repository. It is intentionally workflow-agnostic. Workflow-specific
plans, branch strategies, and local prompts may add temporary context, but
they must not weaken the principles below.

## Primary Objective

Development should reduce long-term context cost, coupling, and recovery
burden while preserving strict code quality. Bug fixing is necessary, but it
should not become a substitute for improving the structure of the project.

Every major phase should move the project toward:

- smaller workflow-specific context;
- clearer boundaries between shared core code and workflow-specific code;
- fewer repeated full-repository reads by execution agents;
- fewer repeated broad test runs when targeted validation is enough;
- safer promotion of genuinely reusable modules into stable shared surfaces;
- accurate documentation that reflects current implementation, not intent.

## Role Boundaries

- Web agent: high-context reviewer and planner. It may inspect the full
  repository when needed, challenge reports, and design follow-up prompts.
- Local agent: bounded execution worker. It should receive concise prompts
  with a small initial read set, explicit edit scope, and targeted validation.
- Codex review layer: final broad reviewer after major refactors. It may
  inspect broadly and run broad tests for acceptance.

The web agent may be strict and expensive with context. The local agent should
be cheap, focused, and repeatable.

## Source Of Truth

Code, tests, and current git diff are authoritative. Historical reports,
phase plans, merge notes, and status documents are evidence only. Do not use
old reports as conclusions without checking current code.

When documents disagree with code, trust the code first, then either update
the document or record the discrepancy for the next planning step.

## Architecture Policy

- Workflow-specific logic should remain workflow-specific until reuse is
  demonstrated.
- Shared core code may be changed when a workflow genuinely needs a stable
  cross-workflow contract, but such changes require explicit scope and broader
  validation.
- A module is a core candidate only after it is useful across workflows or has
  a stable interface that can be tested independently.
- Stable branches should accept durable shared capabilities, not every
  workflow convenience layer.

## Branch And Scope Policy

- Use branch isolation for large workflow refactors, risky architecture work,
  or experiments that may not belong in stable shared code.
- Keep each phase small enough that its diff can be reviewed independently.
- Do not mix governance/documentation cleanup, runtime behavior fixes, and
  broad architecture changes in one local-agent task unless the connection is
  explicit.
- Treat high-blast-radius paths as sensitive, not impossible to change. The
  prompt must name the file, reason, and validation when such paths are in
  scope.
- Clean direct merge is allowed after the named review and validation gates
  pass. Do not delay a clean merge solely to ask for operator approval.

## Local-Agent Prompt Contract

Every local-agent prompt should contain only:

1. Objective: one sentence.
2. Background: at most five current facts.
3. Read first: a bounded file list.
4. Scope: allowed edits and forbidden edits.
5. Validation: targeted tests first; broader tests only if risk justifies it.
6. Output: changed files, rationale, tests run, remaining risks.

Avoid asking the local agent to read the whole repository by default. Avoid
asking it to repeat already-passed broad tests unless touched code justifies
it.

## Validation Policy

- Prefer targeted tests for bounded changes.
- Escalate to broader tests when shared core code, cross-workflow contracts,
  persistence, recovery behavior, or runtime entrypoints change.
- For live CST work, separate no-CST validation from live-CST validation and
  state which one was actually run.
- Bounded live smoke is allowed when it is part of the phase validation plan.
  It must name the command, scope, timeout or stop condition, output location,
  and cleanup check. Long production campaigns, destructive process
  manipulation, and default-config changes still require explicit phase scope.
- Record exact commands and outcomes for major milestones.

## Reporting Policy

Reports are useful for major milestones, architecture decisions, and live CST
evidence. They should not be produced for every small patch. Prefer concise
summaries for patch-level work.

### Context-Compaction Rule

After each major workflow phase or accepted phase cluster, workflow-specific
current-context documents must be compacted. The compacted version must:

- be bounded, with a target of 150-250 lines;
- be current-state oriented;
- work as a local-agent handoff without full historical reading;
- point to decision records, reports, git history, or phase files for detailed
  evidence instead of copying their contents;
- remove stale append-only logs, old read lists, old execution logs, and
  duplicated phase details;
- keep phase, component, and risk status current enough that a local agent can
  start the next phase from the compacted context alone.

This rule exists because append-only current-context documents grow linearly
with each phase and defeat their own purpose.

### Main PR Review Priority

When reviewing a main-integration or integration-readiness PR, reviewers must
prioritize:

1. Diff safety: changed files and contents are correctly scoped and free of
   unintended side effects.
2. Runtime semantics: behavior matches accepted phase contracts.
3. Live CST decision: live smoke is either run, scoped for the phase, or
   intentionally deferred with rationale.
4. Boundary integrity: root entry, scheduler, config, shared-core, and
   workflow-specific boundaries remain as designed.

The following should not block a phase by themselves:

- mechanical documentation counts unless they materially misstate
  architecture, runtime behavior, validation results, or risk;
- cosmetic wording diffs in non-authoritative documents;
- minor summary drift between `git diff --name-only` and hand-written PR
  descriptions. Treat `git diff` as authoritative.

Only block on documentation issues when they would mislead a future reader
about architecture, runtime safety, validation scope, or risk.

## CST API Rule

Any CST Studio Suite code must be based on provided official documentation or
existing verified wrappers. Do not invent `cst.interface` or `cst.results`
APIs.

## Scientific Rigor

When code computes or reports physical quantities, comments and docstrings
should make units and assumptions explicit, especially for frequency, quality
factor, accelerating gradient, power, and field-derived metrics.

## Prompt Template

```text
Goal:
<one sentence>

Current facts:
- <fact 1>
- <fact 2>
- <fact 3>

Read first:
- <path 1>
- <path 2>
- <path 3>

Allowed edits:
- <scope>

Forbidden:
- no full-repo scan unless the bounded read set cannot explain the issue
- no changes outside <scope>
- no new CST API assumptions
- no historical report conclusions without code verification

Validation:
- targeted: <commands>
- broader only if risk justifies it: <commands>

Return:
- changed files
- rationale
- tests run
- residual risks
```
