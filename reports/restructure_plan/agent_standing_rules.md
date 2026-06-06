# Agent Standing Rules

Reusable rules for local-agent prompts in the
`t626644510/Test-remote-cst-workflow` repository.

## Current status

For future planning and local-agent prompt construction, use
`reports/restructure_plan/agent_operating_charter.md` as the higher-priority
governance document. This OPS1 file is retained as a safety checklist only.
Do not use it as the full prompt template, and do not treat its old branch
state as current.

## Purpose

Reduce repetition in every prompt by encoding fixed boundaries, protected
areas, and artifact policies that apply to **all** local-agent work unless a
given phase explicitly overrides them.

## Core rules

### CST and destructive actions

- **No CST unless explicitly approved.** Every CST solve consumes a license
  and wall-clock time. No-CST phases are the default.
- **No destructive or process-kill action unless explicitly approved.**
  Killing orphan DE windows or CST licensing services requires a bounded,
  pre-authorized scenario.
- No runtime or default config changes unless explicitly scoped to the phase.

### Evidence sources

- **No JSONL or Excel as evidence source unless explicitly scoped.**
  JSONL sidecar files are diagnostic-only. Excel files (`.xlsx`, `.xls`)
  are not used as analysis inputs.

### Artifact policy -- never commit

| Artifact | Pattern / example |
|----------|-------------------|
| Local config | `config.local.yaml` |
| Database files | `*.sqlite`, `*.db`, `*.db-shm`, `*.db-wal` |
| JSONL sidecar | `*.jsonl` |
| Checkpoints | `*.ckpt` |
| Logs | `workflow_1_runtime.log`, `workflow_3_runtime.log` |
| CST outputs | `*.cst`, CST export files |
| Generated outputs | generated markdown, JSON, temp scripts |

All of the above **must not** appear in `git ls-files`. Use outside-repo
paths (`/tmp/`, `C:\temp\`, or an explicit scratch directory) for DB or live
outputs.

### Sensitive areas -- modify only with explicit scope

| Path | Reason |
|------|--------|
| `run_workflow_1.py` | Root shim -- validated in live campaigns |
| `run_workflow_3.py` | WF3 runner -- validated, protected |
| `workflows/rfgun_single_pass/` | Validated reference -- must remain untouched |
| `src/cst_optimization/` | Core optimisation library -- requires explicit scope and broader validation |

These paths are not automatically forbidden. They are high-blast-radius areas.
The local-agent prompt must name the file and reason when one of them needs a
change.

### Forbidden imports

- `cst_optimization.factory`
- `cst_optimization.workflows.recovery`

These may not appear in `workflows/rfgun_sao/` source files. The SAO
consolidation package may only import from `workflows.rfgun_sao.types` for
evaluation types.

### Legacy code

Do **not** copy or adapt `RecoveryWorkflowEvaluator`. It is a legacy
single-pass construct; new code should use the SAO equivalents.

### Reports

Reports under `reports/restructure_plan/` are intentional tracked artifacts for
major phases, architecture decisions, and live CST evidence. Do not create a
new report for every small patch. Generated outputs (sweep CSVs, formatted
tables, JSON dumps) are **not** reports and should live outside the tracked
tree.

### Live work

Live work (CST solves, process manipulation) requires:

1. Explicit operator approval naming the scenario.
2. Bounded commands (timeout, scope, clean-up).
3. A pre-approved kill/recovery plan.

## Override

A phase may override any of these rules if the override is **explicitly
stated** in the phase brief and approved by the operator. Default is always the
strictest interpretation.
