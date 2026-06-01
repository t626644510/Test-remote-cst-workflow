# Branch Context -- `rfgun_sao` (Experimental Consolidation)

## Status

This package is the experimental consolidation target for RF gun SAO
capabilities.  It is derived from the validated
`workflows/rfgun_single_pass/` package.

## Rules

1. **Do not modify `workflows/rfgun_single_pass/`** during A-series.
   The validated reference must remain untouched.
2. **Do not import `cst_optimization.factory`.**
3. **Do not import `cst_optimization.workflows.recovery`.**
   Use `workflows.rfgun_sao.types` for evaluation types.
4. **Do not change `run_workflow_1.py`** until live single-pass
   regression passes on this package.
5. **Default behaviour must remain validated single-pass** identical to
   `rfgun_single_pass`.  Opt-in features (two-pass, gates, etc.)
   must be explicitly enabled.

## Minimum validation before any commit

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
`

## Current phase

**A3:** Copy from `rfgun_single_pass` + import localisation (types.py).
No new features.  Default single-pass behaviour unchanged.

## A4 status

- Explicit module runner validated (`python -m workflows.rfgun_sao.run --help`).
- `run_workflow_1.py` remains untouched (still points to
  `workflows.rfgun_single_pass.run`).
- Any future phase that wants to repoint `run_workflow_1.py` must
  first pass a live single-pass regression on `rfgun_sao`.
