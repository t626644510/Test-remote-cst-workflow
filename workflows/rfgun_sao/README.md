# RF Gun SAO -- Consolidated SAO Workflow (Experimental)

## Status

**Experimental consolidation.**  This package is derived from the validated
``workflows/rfgun_single_pass/`` (Phase 8.8 validated) and is the target for
consolidating legacy Workflow 3 SAO capabilities.

**Default runtime remains validated single-pass.**  The root shim
``run_workflow_1.py`` still points to ``rfgun_single_pass`` and is
intentionally not repointed during consolidation.  ``rfgun_sao`` only runs
explicitly via ``python -m workflows.rfgun_sao.run``.

---

## Default behavior

- ``workflows/rfgun_sao/config.yaml`` defaults to ``evaluation.mode: single_pass``
  (same physics as ``rfgun_single_pass``).
- ``evaluation.mode: two_pass`` defaults to **placeholder** runtime (no CST
  connection, returns penalty 1.0) unless ``evaluation.two_pass.runtime: cst``
  is explicitly set.
- ``runtime=cst`` is **opt-in only** — the two-pass CST path is never active
  by default.
- Local CST paths (project, library) belong in **``config.local.yaml``**,
  which is gitignored and must not be committed.

---

## Validated so far

### no-CST tests

```powershell
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short  # 184/184 as of B9
```

The no-CST test suite covers imports, gate utilities, calibration primitives,
orchestration skeleton, injectable runners, CST adapter unit tests (with fake
CST objects), calibration diagnostics, accepted/rejected path logging, mixed
gate precedence, multi-dip diagnostic status, checkpoint semantics audit,
checkpoint persistence hardening, metric invariant hardening, metric roles
skeleton, threshold penalty computation, report-only diagnostic extraction,
CST cleanup helper, and gate role pass/fail and runtime rejection.

### Live CST smokes (opt-in ``runtime=cst``)

| Phase | Type | Validation | Result |
|-------|------|------------|--------|
| A13.4 | Live CST | Full minimal pass — calibration success, measurement reached, 7 metrics computed | **Best F = -15185.95**, exit 0 |
| A14 | Live CST | Frequency gate rejection — ``target_ghz=0.0``, ``max_abs_offset_mhz=1.0`` | ``frequency_gate_reject``, measurement skipped, Best F = 1.0 |
| A15 | Live CST | S11 depth gate rejection — ``threshold_db=-100.0`` | ``s11_depth_gate_reject``, measurement skipped, Best F = 1.0 |
| A24 | Live CST | Successful measurement checkpoint evidence — ``solver_ok=True``, 7 metrics | **Best F = -15185.95**, ``status=completed`` |
| B5 | Live CST | Role-based metrics: optimize + threshold in objective vector, report_only excluded, diagnostics logged | **Best F = -17534.24**, threshold penalty verified, diagnostics INFO log confirmed |
| B9 | Live CST | Gate runtime rejection: q0 raw=18630.8 vs threshold=999999999 greater_than | **Best F = 1.0**, ``gate_reject:q0_gate``, cleanup closed=True |

Each live smoke used a valid local CST project (``D:/workflow_elgun/PickupDesign_2026.cst``)
with ``n_initial_samples=1``, ``n_iterations=0``, ``retry.enabled=false``.

### No-CST / policy / hardening milestones

| Phase | Type | Validation | Result |
|-------|------|------------|--------|
| A16 | no-CST regression | Mixed gate precedence | Cal failure > frequency > S11 depth > measurement, scalar/checkpoint semantics locked |
| A17 | no-CST regression | Multi-dip diagnostic status clarified | Diagnostic-only, runtime stores compact S11 summaries only, live plumbing future |
| A19 | no-CST audit | Checkpoint/evaluation-records semantics audit | 7-path semantic matrix, 6 new tests (93→93) |
| A20 | no-CST fix | Checkpoint persistence semantics fix | ``_record_checkpoint_evaluation`` helper, ``solver_ok``-driven decision, 5 new tests (98→98) |
| A21 | no-CST hardening | Checkpoint objective_names hardening | ``_checkpoint_metric_names_from_wf_ref`` helper, 4 new tests (102→102) |
| A22 | no-CST hardening | Checkpoint metric invariant hardening | String/duplicate/invalid name rejection, raw/penalty length check, 5 new tests (107→107) |
| A23 | policy / docs | Report hash cleanup and evaluation_records policy | ``.ckpt`` authoritative, ``evaluation_records.jsonl`` not written, policy documented |
| A24.1 | shutdown correction | CST shutdown correction | Lingering DE process force-closed; background licensing service (no window) normal |
| B1 | no-CST skeleton | Metric roles skeleton — optimize / threshold / report_only | ``MetricSpec``, ``build_metric_specs``, ``objective_metric_names``, ``report_metric_names`` |
| B2 | no-CST skeleton | Threshold penalty formula — ``compute_threshold_penalty`` | ``direction="less_than"/"greater_than"``, non-finite → 1.0 |
| B3 | no-CST wiring | Threshold penalty runtime wiring — ``compute_role_penalties`` | ``Workflow1Evaluator`` penalty loop uses role-aware helper |
| B4 | no-CST skeleton | Report-only diagnostic extraction — ``report_only_diagnostics`` | ``EvaluationResult.diagnostics``, ``report_as`` alias, duplicate-key detection |
| B4.1 | no-CST hardening | Diagnostics preservation — stale reset, measurement runner wiring | ``_last_diagnostics`` reset on each eval, ``last_diagnostics()`` accessor |
| B5.1 | no-CST fix + live | Runner-level CST cleanup — ``_cleanup_workflow_connection`` | ``CST cleanup: attempted=True closed=True pid=<PID>``; live verified |
| B7 | no-CST skeleton | Gate metric role — ``compute_gate_pass``, ``compute_gate_results`` | ``gate_metric_names`` exposed; direction validated; excluded from objective/penalty |
| B8 | no-CST wiring | Gate runtime rejection — ``summarize_gate_results``, two-pass evaluator override | Gate fail → all-ones penalties, ``solver_ok=False``, ``error="gate_reject:..."`` |

---

## Implemented capabilities

### Config and runner identity
- objective_weights support (named dict, validated, A5)
- evaluation.mode skeleton (single_pass default, two_pass fail-fast, A6)

### Two-pass orchestration skeleton
- Calibration primitives: CalibrationResult, MeasurementPlan, helpers (A8)
- Decision types: TwoPassDecision, evaluate_two_pass_decision (A10)
- Injectable runtime evaluator with pluggable calibration/measurement runners
  (A11→A12)
- Placeholder runners (always fail) as default; default path returns penalty 1.0

### CST two-pass adapters (opt-in ``runtime=cst``)
- ``make_cst_calibration_runner`` — S11-based f0 detection via HPBW / dip-min
  fallback (A13)
- ``make_cst_measurement_runner`` — delegates to ``Workflow1Evaluator``,
  reuses single-pass post-processing (A13)
- Only active when ``evaluation.two_pass.runtime: cst``; default remains
  placeholder

### Diagnostics and logging
- Calibration diagnostics: compact S11 meta (points, freq range, min dB)
  without full arrays (A13.3)
- Rejected-path logging: ``Two-pass rejected`` with ``cal_success``,
  ``f0_ghz``, ``s11_min_db``, ``cal_method``, ``cal_error``, compact
  ``meta`` (A13.3)
- Accepted-path logging: ``Two-pass accepted`` with same calibration detail
  (A13.5)
- ``_decision_error_message`` helper enriches checkpoint error string with
  ``calibration.error`` on ``calibration_failed`` (A13.3)

### Gates
- FrequencyGate: enabled/disabled, target_ghz, max_abs_offset_mhz (A7)
- S11DepthGate: enabled/disabled, threshold_db (A7)
- Mixed gate precedence: calibration_failed > frequency_gate_reject >
  s11_depth_gate_reject (A16)
- Gate rejection does not call measurement runner, returns all-ones penalty
  scalar (dot(ones, normalized weights) = 1.0)

### Checkpoint persistence
- ``_record_checkpoint_evaluation`` module-level helper in ``run.py`` (A20)
- Completed-record semantics: ``solver_ok=True`` **and** all raw values finite
  **and** valid metric names **and** raw/penalty length match → ``mark_completed``
  (A20, A22)
- Failure/rejection paths → ``mark_failed`` with stable error string;
  decision driven by ``solver_ok``, not ``all_finite(raw)`` alone (A20)
- Metric name validation: rejects ``str``/``bytes``, empty, duplicate, or
  invalid-member ``objective_names`` (A21, A22)
- Persistent record: ``CheckpointManager`` writes ``.ckpt`` file;
  ``evaluation_records.jsonl`` is **not** currently written (A23 policy)
- Live evidence: successful two-pass measurement produces ``status=completed``,
  ``solver_ok=True``, ``error=''``, all 7 objective raw/penalty entries (A24)

### Metric roles (optimize / threshold / report_only / gate)
- ``MetricRole`` enum and ``MetricSpec`` dataclass with ``threshold``/``sigma``/
  ``direction``/``report_as`` fields (B1, B2)
- ``build_metric_specs`` parses config entries into specs (B1)
- ``objective_metric_names`` = optimize + threshold; ``report_metric_names`` =
  report_only (source names); ``report_only_output_names`` = report_as aliases (B1, B4)
- Missing role defaults to ``optimize``; unknown role raises ``ValueError`` (B1)
- Direction validated for threshold and gate roles; optimize/report_only do not use direction for scalar behaviour (B3, B7)
- ``compute_threshold_penalty(spec, value)`` — less_than / greater_than formula (B2)
- ``compute_role_penalties`` integrates role-based penalties into ``Workflow1Evaluator`` (B3)
  - optimize: uses ``objective.mode.compute(value)``
  - threshold: uses ``compute_threshold_penalty(spec, value)``
  - report_only: excluded from penalty dict
- ``report_only_diagnostics`` extracts report-only values from ``raw_metrics`` into
  ``EvaluationResult.diagnostics`` (B4)
- Diagnostics surfaced in two-pass measurement path via INFO log when non-empty (B5)
- ``evaluation_records.jsonl`` is **not** written; ``.ckpt`` is authoritative (A23)
- **Gate role (B7, B8, B9)**:
  - Parsed as ``MetricRole.GATE``; direction validated (B7)
  - Exposed as ``gate_metric_names`` on workflow containers (B7)
  - ``compute_gate_pass(spec, value)`` — less_than / greater_than pass/fail (B7)
  - ``compute_gate_results`` — bulk evaluation with ``report_as`` alias and duplicate-key detection (B7)
  - ``summarize_gate_results`` — compact pass summary with stable ``"gate_reject:key1,key2"`` error (B8)
  - Runtime rejection wired in two-pass evaluator: after measurement SUCCESS, failing gate → all-ones penalties, ``solver_ok=False``, ``error="gate_reject:..."`` (B8)
  - **Live CST validated** — B9 confirmed q0 gate fail with ``gate_reject:q0_gate``, Best F=1.0, cleanup closed=True
  - Excluded from ``objective_names``, checkpoint arrays, and ``compute_role_penalties`` in all phases

### Multi-dip detection
- MultiDipDetector utility: detects close dips when S11 arrays are explicitly
  supplied (A7)
- ``evaluate_two_pass_decision`` writes ``diagnostics["multi_dip_detected"]``
  when ``frequencies_ghz`` / ``s11_magnitude`` are provided (A17)
- **Diagnostic-only** — does not reject candidates, does not affect penalty
  or scalar (A16, A17)
- Runtime CST calibration currently stores compact S11 summaries only; full
  arrays are not plumbed for live multi-dip analysis (A17)

---

## Not implemented yet / future work

- Retry integration for CST two-pass
- Inter-pass recovery for CST two-pass (currently warn-and-ignore if enabled)
- Adaptive bounds
- Staged search
- Live/runtime multi-dip detection (needs S11 array plumbing from
  calibration solve; currently stores only compact summaries)
- ``evaluation_records.jsonl`` runtime sidecar writer (helper module exists,
  runtime writing **opt-in only** via ``logging.evaluation_records.enabled: true``;
  default disabled; C2 runtime wiring done; diagnostics/gate_results enrichment deferred)
- Production-scale validation (full parameter ranges, enabled gates, retry,
  warm-start from single-pass checkpoint)
- Root shim repointing (``run_workflow_1.py`` still points to
  ``rfgun_single_pass``; intentionally deferred)

---

## Running

### no-CST tests (no CST Studio Suite required)

```powershell
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
```

### rfgun_sao explicitly (CST Studio Suite required for ``runtime=cst``)

```powershell
# Default single-pass (config.yaml)
python -m workflows.rfgun_sao.run --n-initial 1 --n-iter 0

# Explicit config
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.yaml

# Two-pass with local CST config (use config.local.yaml, do not commit)
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml
```

### DO NOT use ``run_workflow_1.py`` for rfgun_sao

The root entry point ``run_workflow_1.py`` still delegates to
``workflows.rfgun_single_pass`` and is **intentionally not repointed** during
consolidation.  Always use ``python -m workflows.rfgun_sao.run`` to run the
consolidated workflow.

---

## Local CST config (``config.local.yaml``)

For ``runtime=cst`` operation you need a local ``config.local.yaml``
(gitignored) that overrides:

- ``cst.library_path`` — your CST Python libraries
- ``project.cst_path`` — a local ``.cst`` project file (use a copy, not the
  only working file)
- ``logging.output_dir`` — where logs / checkpoints go

**Never commit ``config.local.yaml``.**  Always restore it to
``evaluation.mode: single_pass`` after live smokes that change it to
``two_pass``.

**Live CST shutdown note:** The explicit runner (``run.py``) now runs
``_cleanup_workflow_connection`` in a ``finally`` block after every
``opt.optimize()`` call, closing the CST Design Environment connection
on both normal completion and ``KeyboardInterrupt``.  The final output
includes ``CST cleanup: attempted=True closed=True pid=<PID>``.
If a second ``Ctrl+C`` is pressed or ``_os._exit`` is invoked, cleanup may
be bypassed.  After any live run, verify via ``Get-Process`` /
``MainWindowTitle`` that no DE window remains.  A background ``cstd``
licensing service with no window is normal and should not be confused
with an open DE.  See B5.1 report for implementation details.
