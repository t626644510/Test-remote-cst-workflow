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
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short  # 86/86 as of A17
```

The no-CST test suite covers imports, gate utilities, calibration primitives,
orchestration skeleton, injectable runners, CST adapter unit tests (with fake
CST objects), calibration diagnostics, accepted/rejected path logging, mixed
gate precedence, and multi-dip diagnostic status.

### Live CST two-pass (opt-in ``runtime=cst``)

| Phase | Validation | Result |
|-------|------------|--------|
| A13.4 | Full minimal pass — calibration success, measurement reached, 7 metrics computed | **Best F = -15185.95**, exit 0 |
| A14 | Frequency gate rejection — ``target_ghz=0.0``, ``max_abs_offset_mhz=1.0`` | ``frequency_gate_reject``, measurement skipped, Best F = 1.0 |
| A15 | S11 depth gate rejection — ``threshold_db=-100.0`` | ``s11_depth_gate_reject``, measurement skipped, Best F = 1.0 |
| A16 | Mixed gate precedence no-CST regression | Cal failure > frequency > S11 depth > measurement, scalar/checkpoint semantics locked |
| A17 | Multi-dip diagnostic status clarified | Diagnostic-only, runtime stores compact S11 summaries only, live plumbing future |

Each live smoke used a valid local CST project (``D:/workflow_elgun/PickupDesign_2026.cst``)
with ``n_initial_samples=1``, ``n_iterations=0``, ``retry.enabled=false``.

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
- Metric roles (optimize / threshold / report_only)
- Adaptive bounds
- Staged search
- Live/runtime multi-dip detection (needs S11 array plumbing from
  calibration solve; currently stores only compact summaries)
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
