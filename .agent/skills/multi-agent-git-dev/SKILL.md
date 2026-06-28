# Multi-Agent Git Development Skill

## Purpose

This skill coordinates a three-layer agent development workflow based on Git.

The workflow has three roles:

1. Codex Orchestrator
2. Web Phase Planner
3. Local Execution Agent

Git is the source of truth.  
All important plans, reports, reviews, and summaries must be written into `.agent/`.

## Core Principle

Each agent must stay within its authority.

- Codex controls stage-level direction.
- Web ChatGPT controls phase-level planning and review.
- Local execution agents implement code and run tests.
- User makes final product-level decisions.

## Global Rules

1. Do not merge directly into `main`.
2. Do not push directly to `main`.
3. Every stage must have a `stage_plan.md`.
4. Every phase must have:
   - `phase_plan.md`
   - `executor_prompt.md`
   - `execution_report.md`
   - `phase_review.md`
   - `phase_summary.md`
5. If an agent finds unclear requirements, architecture conflict, or repeated failure, it must stop and escalate.
6. Do not silently expand scope.
7. Do not modify workflow files belonging to another role unless explicitly instructed.
8. Web Phase Planner writes workflow documents through remote Git changes under `.agent/`; it must not edit implementation files.
9. Local execution agents must fetch and fast-forward pull the assigned `phase/*` branch before reading local workflow files.
10. Local execution agents must make phase work reviewable through Git before requesting review: write the execution report, commit the allowed phase changes, and push only the current `phase/*` branch.
11. If a required phase pull, commit, or push fails, the local execution agent must stop and write a blocker report instead of asking Web ChatGPT to review an invisible or stale local diff.
12. Prompts and reports should reference shared templates instead of restating long formats. Add phase-specific evidence requirements only when the template is insufficient.

## Branching Model

Use the following branch pattern:

- `main`
- `stage/Sxx-short-name`
- `phase/Sxx-Pyy-short-name`

Local execution agents may work only on `phase/*` branches.
Local execution agents may push only the current `phase/*` branch. They must not push `main`, `stage/*`, tags, or unrelated branches.
Web Phase Planner may create or update remote `phase/*` branches for workflow documentation under `.agent/`, but must not edit implementation files.

## Phase Status

A phase may have one of the following states:

- `DRAFT`
- `CODEX_APPROVED`
- `EXECUTING`
- `READY_FOR_PHASE_REVIEW`
- `NEEDS_FOLLOWUP`
- `PHASE_ACCEPTED`
- `READY_FOR_STAGE_REVIEW`

Only Web ChatGPT can mark a phase as `PHASE_ACCEPTED`.

Only Codex can mark a stage as ready for PR or merge.

## Escalation Rule

If the same phase fails review twice, Web ChatGPT must stop generating follow-up prompts and escalate to Codex or the user.
