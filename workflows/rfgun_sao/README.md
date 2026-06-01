# RF Gun SAO -- Consolidated SAO Workflow (Experimental)

## Status: EXPERIMENTAL CONSOLIDATION

This package is derived from the validated
`workflows/rfgun_single_pass/` (Phase 8.8 validated) and is the
target for consolidating legacy Workflow 3 SAO capabilities.

**Default runtime remains validated single-pass.**

## Implemented so far

- objective_weights support (named dict, validated, A5)
- evaluation.mode skeleton (single_pass default, two_pass fail-fast, A6)
- pure gate utilities: FrequencyGate, S11DepthGate, MultiDipDetector (A7)
- calibration primitives: CalibrationResult, MeasurementPlan, helpers (A8)
- two-pass/gate config helpers: _build_*, _resolve_two_pass_settings (A9)
- two-pass orchestration skeleton: TwoPassDecision, evaluate_two_pass_decision (A10)
- injectable two-pass runtime evaluator skeleton with pluggable calibration/measurement runners (A11→A12)
  - make_two_pass_runtime_evaluator with full control flow
  - placeholder calibration runner (always fails)
  - placeholder measurement runner (always fails)
  - default path returns penalty=1.0 (simulating failed calibration)
  - fake-runner tests verify real orchestration path
- opt-in CST two-pass calibration/measurement runner adapters (A13)
  - make_cst_calibration_runner: S11-based f0 detection with HPBW/dip-minimum
  - make_cst_measurement_runner: delegates to Workflow1Evaluator
  - only active when evaluation.two_pass.runtime=cst; default remains placeholder
- calibration diagnostics: compact S11 meta (points, freq range, min) without full arrays (A13.3)
- accepted/rejected path logging with full calibration detail (A13.3/A13.5)
- mixed gate precedence no-CST regression tests: cal failure > frequency > S11 depth > measurement (A16)
- MultiDipDetector utility can detect close dips; evaluate_two_pass_decision writes diagnostics["multi_dip_detected"] when S11 arrays are explicitly supplied (A17)
  - runtime CST two-pass stores only compact S11 summaries, not full frequency/magnitude arrays
  - multi-dip remains diagnostic-only: does not reject candidates, does not affect penalty/scalar

## Not implemented yet

- retry integration for CST two-pass
- inter-pass recovery for CST two-pass (warn-and-ignore if enabled)
- metric roles (optimize / threshold / report_only)
- adaptive bounds
- staged search
- root shim repointing (run_workflow_1.py still points to rfgun_single_pass)
- live multi-dip detection (runtime needs S11 frequency/magnitude array plumbing; currently stores only compact S11 summaries)

**Notes:**
- evaluation.mode=two_pass defaults to placeholder (no CST, penalty=1.0).
- Set ``evaluation.two_pass.runtime: cst`` in config to activate real CST two-pass.
- config.local.yaml should be used for local CST paths and must not be committed.
- Single-pass is unchanged; run_workflow_1.py still points to rfgun_single_pass.
- MultiDipDetector is diagnostic-only: it does not reject candidates.
  - ``evaluate_two_pass_decision`` writes ``diagnostics["multi_dip_detected"]`` only when ``frequencies_ghz`` / ``s11_magnitude`` arrays are explicitly supplied.
  - The CST runtime calibration path stores only compact S11 summaries (points, freq range, min dB) to avoid storing full arrays.
  - Live/runtime multi-dip detection (deriving dip features from the calibration solve) is future work.

## Running

rfgun_sao only runs explicitly via `python -m workflows.rfgun_sao.run`.
The root shim `run_workflow_1.py` still points to `rfgun_single_pass`
and is not changed during consolidation.

`powershell
python -m workflows.rfgun_sao.run --help
python -m workflows.rfgun_sao.run --n-initial 1 --n-iter 0
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.yaml
`

## No-CST tests

`powershell
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short  # 12/12
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short          # 66/66 as of A13
`
