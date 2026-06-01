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
- two-pass runtime placeholder path: evaluation.mode=two_pass returns placeholder penalty=1.0 (A11)

## Not implemented yet

- actual two-pass CST calibration/measurement execution (placeholder path exists but not physically meaningful)
- gate integration into evaluator (two_pass.py exists but placeholder only)
- metric roles (optimize / threshold / report_only)
- adaptive bounds
- staged search
- root shim repointing (run_workflow_1.py still points to rfgun_single_pass)

**Note:** evaluation.mode=two_pass no longer raises NotImplementedError, but returns placeholder (1.0) penalties and is not physically meaningful.

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
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short          # 53/53 as of A11
`
