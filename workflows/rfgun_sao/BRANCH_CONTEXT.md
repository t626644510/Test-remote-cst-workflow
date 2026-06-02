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

**Status:** JSONL diagnostics sidecar milestone closed through C3.5.

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| C1 | JSONL diagnostics sidecar skeleton — ``records.py`` helpers | Accepted |
| C2 | JSONL runtime opt-in wiring — ``_record_jsonl_sidecar_evaluation``, ``_on_evaluation`` integration, no-CST tests | Accepted |
| C2.1 | JSONL sidecar polish — write-failure monkeypatch test, doc wording hardening | Accepted |
| C3 | JSONL diagnostics/gate_results enrichment — extended callback, two-pass runtime enrichment, no-CST tests | Accepted |
| C3.1 | JSONL mode gating fix — `_should_use_enriched_jsonl` helper, single_pass core-only path preserved | Accepted |
| C3.2 | JSONL counter ordering fix — enriched path no longer double-increments; each path increments once per eval | Accepted |
| C3.3 | JSONL docs/status polish — final Phase C docs alignment | Accepted |
| C3.4 | README JSONL policy cleanup — removed stale `not written` wording | Accepted |
| C3.5 | JSONL milestone closeout — status alignment | Accepted |

### Authoritative behaviour

- ``.ckpt`` / ``CheckpointManager`` remains the authoritative persisted
  evaluation record.
- JSONL sidecar helpers exist and runtime writing is wired **only as
  explicit opt-in** via ``logging.evaluation_records.enabled: true``.
- ``resolve_records_config`` reads ``logging.evaluation_records`` config key.
- Default config keeps JSONL **disabled**; JSONL is **not** a recovery source.
- ``single_pass`` + JSONL enabled → core-only C2 fallback.
- ``two_pass`` + JSONL enabled → enriched diagnostics/gate_results callback (C3).
- Each evaluation increments exactly once; iteration starts at 0.

### Known caveats

- JSONL diagnostics/gate_results enrichment is wired for two-pass; single_pass gets core-only fallback.
- No live CST validation of JSONL sidecar output yet.
- JSONL is diagnostic only; not a recovery or warm-start source.
- Second Ctrl+C now performs best-effort cleanup before hard exit (D1);
  live CST validation of D1 cleanup pending.

### Next possible directions

a) Live CST JSONL sidecar smoke (only when explicitly requested).
b) Phase C docs/report consolidation (if needed).

## Phase D — Ctrl+C hard-exit cleanup (D1)

**Status:** Phase D blocked cleanup milestone accepted through D2.6; D2.7 closeout pending review. Normal live CST cleanup validated; hard-exit live Ctrl+C validation deferred to future true interactive terminal.

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| D1 | Ctrl+C hard-exit cleanup skeleton — `_handle_sigint_event` helper, best-effort cleanup before `_os._exit`, no-CST tests | Accepted |
| D1.1 | D1 helper polish — return-after-exit guard, cleanup failure warning fallback, BRANCH_CONTEXT cleanup | Accepted |
| D1.2 | Phase C/D BRANCH_CONTEXT table structure cleanup — removed stray D1 from Phase C table | Accepted |
| D1.3 | D1 milestone closeout — status alignment | Accepted |
| D2 | Live CST validation of D1 hard-exit cleanup | Partial / normal cleanup passed; hard-exit blocked |
| D2.1 | Hard-exit live validation retry — attempted but blocked by non-interactive Windows signal delivery | Attempted / blocked |
| D2.2 | Blocked closeout — honest status correction, future validation deferred to interactive terminal | Accepted |
| D2.3 | Blocked closeout status polish | Accepted |
| D2.4 | Duplicate D2.2 row cleanup | Accepted |
| D2.5 | Blocked closeout final status polish | Accepted |
| D2.6 | Final acceptance polish | Accepted |
| D2.7 | Blocked cleanup milestone closeout | Completed / pending review |

### Authoritative behaviour

- Normal completion and first Ctrl+C → `finally` block runs
  `_cleanup_workflow_connection` as before.
- Second Ctrl+C → `_handle_sigint_event` runs
  `_cleanup_workflow_connection(force=True)` best-effort before
  `_os._exit(130)`.  If cleanup raises, a warning is logged and
  hard-exit proceeds.
- Normal cleanup live CST validated (D2).
- Hard-exit live Ctrl+C validation remains blocked — requires true
  interactive operator-controlled terminal outside local-agent tool context.

### Known caveats

- If the Python runtime or OS-level kill (``taskkill /F``, SIGKILL) is used,
  cleanup is bypassed entirely.
- Hard-exit live Ctrl+C validation remains future; blocked by non-interactive
  execution environment (see D2.2 report).

### Next possible directions

a) True manual interactive live CST Ctrl+C validation outside local-agent
   tool context.
b) Move on to other non-live hardening or documentation work.

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
