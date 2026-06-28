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

## Branching Model

Use the following branch pattern:

- `main`
- `stage/Sxx-short-name`
- `phase/Sxx-Pyy-short-name`

Local execution agents may work only on `phase/*` branches.

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