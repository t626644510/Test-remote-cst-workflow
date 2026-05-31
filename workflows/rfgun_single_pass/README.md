# Workflow 1 — RF Gun Single-Pass SAO Optimisation

## Purpose

Single-project single-pass frequency-domain Surrogate-Assisted
Optimisation (SAO) for the X-band RF gun cavity.  Workflow 1 evaluates
a single CST project with a one-pass solve (fixed `f_data`), wrapped in
a three-tier retry handler with post-evaluation graceful reset.

## Current status (Phase 2 scaffold)

- The **real runner** still lives at `../../run_workflow_1.py` (project
  root).  This directory is an empty skeleton.
- Phase 3 will migrate the runner into this package.
- Phase 4+ will extract the evaluator, objectives, and config schema.

## Constraints respected in all phases

| Constraint | Status |
|---|---|
| Modify `config/default.yaml` | ❌ Not before Phase 5 |
| Modify `src/cst_optimization/` | ❌ Never for WF1 extraction |
| Modify Workflow 2 / 3 code | ❌ Never |
| Move `examples/` | ❌ Never |
| Change runtime behaviour | ❌ Not before Phase 7 (final validation) |

## Smoke test

```powershell
python -m compileall src workflows run_workflow_1.py
```

All files must compile without errors.
