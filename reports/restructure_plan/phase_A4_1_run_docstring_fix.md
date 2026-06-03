# Phase A4.1 -- Fix rfgun_sao run.py docstring

## Summary

Fixed the top-level docstring in `workflows/rfgun_sao/run.py` which
still referenced the old `rfgun_single_pass` module paths and falsely
claimed `run_workflow_1.py delegates directly to this module`.

## Exact issue fixed

**Before:**
`
    .venv\\Scripts\\python -m workflows.rfgun_single_pass.run
    .venv\\Scripts\\python run_workflow_1.py --config workflows/rfgun_single_pass/config.yaml
The backwards-compatible entry point `run_workflow_1.py` ...
delegates directly to :func:main in this module.
`

**After:**
`
    .venv\\Scripts\\python -m workflows.rfgun_sao.run
    .venv\\Scripts\\python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.yaml
The backwards-compatible root entry point `run_workflow_1.py` still
delegates to `workflows.rfgun_single_pass.run` during A-series
consolidation.  It is intentionally not repointed to this module yet.
`

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/run.py` | Docstring fixed | Modified |
| `reports/restructure_plan/phase_A4_1_run_docstring_fix.md` | Created | New |

## Behaviour impact

None.  Only the module docstring was changed.  All imports, CLI flags,
and runtime logic are identical.

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
python -m workflows.rfgun_sao.run --help
Select-String -Path workflows/rfgun_sao/run.py -Pattern "workflows.rfgun_single_pass.run|workflows/rfgun_single_pass/config.yaml|delegates directly to :func"
`

### Real terminal output

**compileall:** exit 0.
**single_pass tests:** 12/12 passed.
**sao tests:** 14/14 passed.
**--help:** exit 0, correct flags.

**Select-String:** Two matches found, both EXPECTED:
- Line 10: `delegates to `workflows.rfgun_single_pass.run` ` (intentional documentation note)
- Line 29: `# run.py lives at workflows/rfgun_single_pass/run.py` (path comment during A-series)

The stale problematic patterns (`delegates directly to :func`,
`workflows/rfgun_single_pass/config.yaml`) have **zero matches**.

## Risks

None.  Only a docstring was changed.

## Recommended next phase

**A5:** Add `objective_weights` support to the rfgun_sao builder.
