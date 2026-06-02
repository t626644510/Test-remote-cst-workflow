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

## Phase C — Diagnostics sidecar

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| C1 | JSONL diagnostics sidecar skeleton — ``records.py`` helpers | Accepted |
| C2 | JSONL runtime opt-in wiring — ``_record_jsonl_sidecar_evaluation``, ``_on_evaluation`` integration, no-CST tests | Accepted |
| C2.1 | JSONL sidecar polish — write-failure monkeypatch test, doc wording hardening | Completed / pending review |

### Authoritative behaviour

- ``.ckpt`` / ``CheckpointManager`` remains the authoritative persisted
  evaluation record.
- JSONL sidecar helpers exist and runtime writing is wired **only as
  explicit opt-in** via ``logging.evaluation_records.enabled: true``.
- ``resolve_records_config`` reads ``logging.evaluation_records`` config key.
- Default config keeps JSONL **disabled**; JSONL is **not** a recovery source.

### Known caveats

- Diagnostics/gate_results enrichment in JSONL sidecar deferred to future phase.

### Next possible directions

a) JSONL diagnostics/gate_results sidecar enrichment.
b) Ctrl+C hard-exit cleanup hardening.
c) Production-scale live CST regression (only when explicitly requested).

## Phase B — Metric roles and gate (B1–B9) — **CLOSED**

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
| B7 | Gate metric role skeleton (`compute_gate_pass`, `compute_gate_results`) | Accepted |
| B8 | Gate runtime rejection wiring (no-CST) | Accepted |
| B9 | Gate runtime rejection live CST smoke — q0 gate fail confirmed, Best F=1.0, `gate_reject:q0_gate` | Accepted |

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
  helpers (`compute_gate_pass`, `compute_gate_results`, `summarize_gate_results`);
  excluded from `objective_names`, checkpoint arrays, and `compute_role_penalties`;
  **runtime candidate rejection wired** in two-pass evaluator;
  **live CST validated** (B9): q0 raw=18630.8 vs threshold=999999999 → fail,
  `error="gate_reject:q0_gate"`, Best F=1.0, cleanup closed=True.

### Live evidence

| Smoke | Best F | Key confirmation |
|-------|--------|------------------|
| B5 (role metrics) | -17534.24 | optimize + threshold in objective (5 of 7 metrics); report_only diagnostics logged with `report_as` aliases; threshold penalty formula verified |
| B5.1 (shutdown) | — | `CST cleanup: attempted=True closed=True pid=50700`; no DE window left open after run |
| B9 (gate rejection) | 1.0 | q0 raw=18630.8 vs threshold=999999999 greater_than → `q0_gate=False`; `error="gate_reject:q0_gate"`; objective/checkpoint arrays exclude gate; cleanup closed=True pid=59364 |

### Known caveats

- `evaluation_records.jsonl` not written.
- JSONL diagnostics sidecar remains future.
- Ctrl+C hard-exit cleanup hardening remains future.
- Production-scale validation remains future.
- Report-only diagnostics not persisted to checkpoint.
- Second Ctrl+C / `_os._exit` bypasses cleanup.

### Next possible directions

a) JSONL diagnostics sidecar.
b) Ctrl+C hard-exit cleanup hardening (if desired).
c) Additional live CST regression smoke (only when explicitly requested).
