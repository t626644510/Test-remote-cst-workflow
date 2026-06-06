# Agent Operating Charter -- Scheme 1.5

This document supersedes older local-agent prompt notes for future planning
work.  Use it as the fixed governance input for web-agent planning before the
Workflow 2 refactor.

## Primary Objective

The refactor exists to reduce long-term context cost and coupling.  Bug fixing
is necessary, but it is not the primary goal.  Every phase should move the
project toward:

- smaller workflow-specific context;
- clearer boundaries between core and workflow code;
- fewer repeated full-repository reads by local agents;
- fewer repeated broad test runs by local agents;
- safer promotion of truly reusable modules back toward main.

## Scheme 1.5 Direction

Do not immediately perform a large main/core extraction.  Do not start
Workflow 2 as an unconstrained continuation of the current large branch.

Instead:

1. Establish these governance rules first.
2. Continue Workflow 2 on a dedicated isolation branch.
3. Let Workflow 2 expose which pieces are actually reusable.
4. Mark reusable pieces as core candidates during Workflow 2 work.
5. Refine main/core after Workflow 2 has produced evidence across workflows.

## Role Boundaries

- Web agent: strict high-context reviewer and planner.  It may inspect the full
  repository when needed, but should produce concise execution prompts.
- Local agent: execution worker.  It should receive bounded prompts with a
  small initial read set, targeted tests, and explicit non-goals.
- Codex review layer: final high-level reviewer after major refactors.  It may
  inspect broadly and run broad tests for acceptance.

## Source of Truth

Code, tests, and current git diff are authoritative.  Historical reports,
phase plans, merge notes, and status documents are evidence only.  Do not use
old reports as conclusions without checking current code.

## Core and Branch Policy

- Workflow-specific logic should remain workflow-specific until reuse is
  demonstrated.
- Core code may be changed when a workflow genuinely needs a shared contract
  fix, but such changes require explicit scope and broader validation.
- A module is a core candidate only after it is useful across workflows or has
  a stable cross-workflow interface.
- Main should accept stable core capabilities, not every workflow convenience
  layer.

## Local-Agent Prompt Contract

Every local-agent prompt should contain only:

1. Objective: one sentence.
2. Background: at most five current facts.
3. Read first: a bounded file list.
4. Scope: allowed edits and forbidden edits.
5. Validation: targeted tests first; broader tests only if shared core changes.
6. Output: changed files, rationale, tests run, remaining risks.

Avoid asking the local agent to read the whole repository by default.  Avoid
asking it to repeat already-passed broad tests unless touched code justifies it.

## Reporting Policy

Reports are useful for major milestones and live CST evidence.  They should not
be produced for every small patch.  Prefer concise summaries for patch-level
work.

## CST API Rule

Any CST Studio Suite code must be based on provided official documentation or
existing verified wrappers.  Do not invent `cst.interface` or `cst.results`
APIs.

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
- broader only if shared core changed: <commands>

Return:
- changed files
- rationale
- tests run
- residual risks
```
