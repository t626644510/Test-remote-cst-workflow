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

## Not implemented yet

- retry integration for CST two-pass
- inter-pass recovery for CST two-pass (warn-and-ignore if enabled)
- metric roles (optimize / threshold / report_only)
- adaptive bounds
- staged search
- root shim repointing (run_workflow_1.py still points to rfgun_single_pass)

**Notes:**
- evaluation.mode=two_pass defaults to placeholder (no CST, penalty=1.0).
- Set ``evaluation.two_pass.runtime: cst`` in config to activate real CST two-pass.
- config.local.yaml should be used for local CST paths and must not be committed.
- Single-pass is unchanged; run_workflow_1.py still points to rfgun_single_pass.

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
