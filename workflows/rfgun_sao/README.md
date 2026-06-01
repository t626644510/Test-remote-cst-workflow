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
- two-pass/gate config helpers (A9)
- two-pass orchestration skeleton: TwoPassDecision, evaluate_two_pass_decision (A10): _build_*, _resolve_two_pass_settings (A9)

## Not implemented yet

- actual two-pass CST execution (evaluation.mode: two_pass still NotImplementedError)
- gate integration into evaluator (two_pass.py exists but not plugged into workflow)
- metric roles (optimize / threshold / report_only)
- adaptive bounds
- staged search
- root shim repointing (run_workflow_1.py still points to rfgun_single_pass)

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
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short          # 51/51 as of A10
`
