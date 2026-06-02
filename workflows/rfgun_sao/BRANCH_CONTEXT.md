# Branch Context -- `rfgun_sao` (Experimental Consolidation)

## Status

This package is the experimental consolidation target for RF gun SAO
capabilities.  It is derived from the validated
`workflows/rfgun_single_pass/` package.

## Core rules

1. **Do not modify `workflows/rfgun_single_pass/`**.  The validated
   reference must remain untouched.
2. **Do not import `cst_optimization.factory`**.
3. **Do not import `cst_optimization.workflows.recovery`**.  Use
   `workflows.rfgun_sao.types` for evaluation types.
4. **Do not change `run_workflow_1.py`** until live single-pass
   regression passes on this package.
5. **Default behaviour must remain validated single-pass** identical to
   `rfgun_single_pass`.  Opt-in features (two-pass, gates, metric
   roles, etc.) must be explicitly enabled.
6. **Do not commit `config.local.yaml`**, logs, checkpoints, CST
   artifacts, or output directories.
7. **CST licensing service (`cstd.exe` with no window) must not be
   confused with a CST Design Environment window.**

## Minimum validation before any commit

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
```

## Phase A — Two-pass orchestration and checkpoint (A1–A25.1)

See `reports/restructure_plan/` for detail.  Milestone summary:

- Two-pass runtime skeleton with injectable calibration/measurement runners
- CST runner adapters (HPBW / dip-min calibration)
- Calibration failure and gate rejection diagnostics
- Checkpoint persistence audit, hardening, and live evidence
- README validation taxonomy cleanup

**Status:** Closed.  Checkpoint milestone accepted through A25.1.

## Phase B — Metric roles and gate skeleton (B1–B7)

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| B1 | Metric roles skeleton (optimize / threshold / report_only) | Accepted |
| B2 | Threshold penalty formula (`compute_threshold_penalty`) | Accepted |
| B3 | Threshold penalty runtime wiring (`compute_role_penalties`) | Accepted |
| B4 | Report-only diagnostic extraction (`report_only_diagnostics`) | Accepted |
| B4.1 | Diagnostics preservation hardening (stale reset, measurement runner) | Accepted |
| B5 | Live CST role-metrics smoke (optimize + threshold + report_only) | Accepted |
| B5.1 | Runner-level CST cleanup (`_cleanup_workflow_connection`) | Accepted |
| B7 | Gate metric role skeleton (`compute_gate_pass`, `compute_gate_results`, no runtime rejection yet) | Accepted |

### Authoritative behaviour

- **optimize**: in `objective_names`, checkpoint arrays; penalty via
  `mode.compute`.
- **threshold**: in `objective_names`, checkpoint arrays; penalty via
  `compute_threshold_penalty(spec, value)` (less_than / greater_than formula).
- **report_only**: excluded from `objective_names` and checkpoint arrays;
  surfaced as `EvaluationResult.diagnostics`; logged in two-pass path when
  non-empty; `report_as` controls output key; **not** persisted to `.ckpt`
  or JSONL.
- **Runner-level CST cleanup**: `_cleanup_workflow_connection` runs in
  `finally` block, outputting
  `CST cleanup: attempted=<bool> closed=<bool> pid=<PID>`.
- **gate**: parsed and exposed as `gate_metric_names`; pure pass/fail
  helpers exist (`compute_gate_pass`, `compute_gate_results`); excluded
  from `objective_names`, checkpoint arrays, and `compute_role_penalties`;
  **runtime candidate rejection not yet wired**.

### Live evidence

| Smoke | Best F | Key confirmation |
|-------|--------|------------------|
| B5 (role metrics) | -17534.24 | optimize + threshold in objective (5 of 7 metrics); report_only diagnostics logged with `report_as` aliases; threshold penalty formula verified |
| B5.1 (shutdown) | — | `CST cleanup: attempted=True closed=True pid=50700`; no DE window left open after run |

### Known caveats

- `evaluation_records.jsonl` not written.
- Gate role runtime enforcement not yet wired (parsed and exposed as
  `gate_metric_names`; pure pass/fail helpers exist; candidate rejection
  is deferred).
- Report-only diagnostics not persisted to checkpoint.
- Second Ctrl+C / `_os._exit` bypasses cleanup.

### Next possible directions

a) Gate role runtime rejection wiring.
b) JSONL diagnostics sidecar.
c) Ctrl+C hard-exit cleanup hardening (if desired).
d) Additional live CST regression smoke (only when explicitly requested).
