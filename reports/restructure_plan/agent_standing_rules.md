# Agent Standing Rules

This file is a short safety checklist for local-agent prompts. The
authoritative governance document is
`reports/restructure_plan/agent_operating_charter.md`; if the two documents
disagree, follow the charter.

## Purpose

Keep fixed repository hygiene rules out of repeated prompts. Do not use this
file as a phase plan, current-state source, or full prompt template.

## Default Permissions

- Bounded live smoke is allowed when it is part of the phase validation plan.
- Clean direct merge is allowed after the named review and validation gates
  pass.
- Long production campaigns, destructive process manipulation, default-config
  changes, and broad shared-core changes still require explicit phase scope.
- All live work must record command, timeout or stop condition, outputs,
  cleanup state, and whether CST was actually exercised.

## Never Commit

| Artifact | Pattern / example |
|----------|-------------------|
| Local config | `config.local.yaml`, `workflows/**/config.local.yaml` |
| Databases | `*.sqlite`, `*.db`, `*.db-shm`, `*.db-wal` |
| JSONL sidecars | `*.jsonl` |
| Checkpoints | `*.ckpt` |
| Logs | `workflow_1_runtime.log`, `workflow_3_runtime.log` |
| CST outputs | `*.cst`, CST export files, result folders |
| Scratch scripts | one-off generated scripts, patch helpers |

Use outside-repo paths such as `C:\temp`, `D:\Results`, or an explicit scratch
directory for live outputs, databases, and generated evidence.

## Sensitive Paths

These paths are not forbidden, but the phase prompt must name them, explain
why they are in scope, and specify validation:

| Path | Reason |
|------|--------|
| `run_workflow_1.py` | validated root shim |
| `run_workflow_2.py` | Workflow2 public entry and scheduler contract |
| `run_workflow_3.py` | validated WF3 runner |
| `scripts/` | scheduler and helper entrypoints |
| `config/default.yaml` | shared runtime defaults |
| `src/cst_optimization/` | shared core library |
| `workflows/rfgun_single_pass/` | validated reference workflow |

## Forbidden Imports

In `workflows/rfgun_sao/` source files, do not import:

- `cst_optimization.factory`
- `cst_optimization.workflows.recovery`

The SAO consolidation package should use its own workflow package types and
helpers instead of reviving legacy factory/recovery coupling.

## Evidence Sources

- Code, tests, current git diff, and live logs from the current run are
  primary.
- Historical reports are evidence only; they are not current-state authority.
- JSONL and Excel files are diagnostic artifacts unless a phase explicitly
  scopes them as evidence sources.
