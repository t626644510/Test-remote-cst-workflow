# RF Gun SAO -- Consolidated SAO Workflow (Experimental)

## Status: EXPERIMENTAL CONSOLIDATION

This package is derived from the validated
`workflows/rfgun_single_pass/` (Phase 8.8 validated) and is the
target for consolidating legacy Workflow 3 SAO capabilities.

**Default behaviour is still validated single-pass.**  No two-pass,
gates, objective_weights, or metric roles are implemented yet.

The validated reference at `workflows/rfgun_single_pass/` remains
untouched.

## Running

`powershell
# Explicit module invocation (current):
python -m workflows.rfgun_sao.run --help

# With overrides (same CLI as rfgun_single_pass):
python -m workflows.rfgun_sao.run --n-initial 1 --n-iter 0
`

The `run_workflow_1.py` shim still points to `rfgun_single_pass`
and is not changed by this phase.

## No-CST tests

`powershell
pytest tests/workflows/test_rfgun_sao_imports.py -v
`

Both the new SAO tests and the original single-pass tests must pass:

`powershell
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
`

## Structure

`
workflows/rfgun_sao/
    __init__.py       # package marker
    types.py          # EvaluationStatus, EvaluationResult (local, no recovery import)
    config.yaml       # default config (same schema as validated WF1)
    run.py            # CLI runner (imports from rfgun_sao.workflow)
    workflow.py       # build_workflow_1() builder
    evaluator.py      # Workflow1Evaluator (imports from rfgun_sao.types)
    gates.py           # FrequencyGate, S11DepthGate, MultiDipDetector (pure Python)
    calibration.py     # CalibrationResult, MeasurementPlan, helpers (primitives only)
    README.md         # this file
    BRANCH_CONTEXT.md # branch rules and phase status
tests/workflows/
    test_rfgun_sao_imports.py  # no-CST import tests (24+ tests)
`
