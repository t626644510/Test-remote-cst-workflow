# Phase A3 -- Create rfgun_sao package from validated rfgun_single_pass

## Summary

Created the new `workflows/rfgun_sao/` package as a copy of the
validated `workflows/rfgun_single_pass/`, with import localisation
to decouple it from `cst_optimization.workflows.recovery` and
`cst_optimization.factory`.  All 26 no-CST tests pass (12 single_pass
+ 14 sao).  No runtime behaviour was changed.

## Files added

| File | Purpose |
|---|---|
| `workflows/rfgun_sao/__init__.py` | Package marker (copied) |
| `workflows/rfgun_sao/README.md` | Updated for experimental consolidation status |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | Updated for rules and A3 phase |
| `workflows/rfgun_sao/config.yaml` | Config (identical to validated WF1) |
| `workflows/rfgun_sao/run.py` | CLI runner (imports rfgun_sao.workflow) |
| `workflows/rfgun_sao/workflow.py` | Builder (imports rfgun_sao.evaluator and rfgun_sao.types) |
| `workflows/rfgun_sao/evaluator.py` | Evaluator (imports rfgun_sao.types) |
| `workflows/rfgun_sao/types.py` | **New**: EvaluationStatus + EvaluationResult (local, no recovery import) |
| `tests/workflows/test_rfgun_sao_imports.py` | 14 no-CST import tests |
| `reports/restructure_plan/phase_A3_create_rfgun_sao.md` | This report |

## Files intentionally not modified

- `workflows/rfgun_single_pass/` -- untouched validated reference
- `run_workflow_1.py` -- still points to rfgun_single_pass
- `run_workflow_2.py`, `run_workflow_3.py` -- untouched
- `src/cst_optimization/` -- untouched
- `config/default.yaml`, `config/workflow_3.yaml` -- untouched
- `examples/` -- untouched
- `reports/workflow1_split/` -- untouched

## Import localisation

| File | Import changed from | Import changed to |
|---|---|---|
| `run.py` | `workflows.rfgun_single_pass.workflow` | `workflows.rfgun_sao.workflow` |
| `workflow.py` | `workflows.rfgun_single_pass.evaluator` | `workflows.rfgun_sao.evaluator` |
| `workflow.py` | `cst_optimization.workflows.recovery` | `workflows.rfgun_sao.types` |
| `evaluator.py` | `cst_optimization.workflows.recovery` | `workflows.rfgun_sao.types` |

All references to `cst_optimization.factory` are docstring-only and
are kept for documentation accuracy.  The import checks verify only
actual import statements.

## Behaviour impact

- **No intended runtime behaviour change.**
- `rfgun_single_pass` remains the validated reference (Phase 8.8).
- `run_workflow_1.py` still points to `rfgun_single_pass`.
- `rfgun_sao` is only runnable explicitly via `python -m workflows.rfgun_sao.run`.

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
python -m workflows.rfgun_sao.run --help
python -c "import sys; import workflows.rfgun_sao.workflow; import workflows.rfgun_sao.evaluator; print('factory:', 'cst_optimization.factory' in sys.modules); print('recovery:', 'cst_optimization.workflows.recovery' in sys.modules)"
Select-String -Path workflows/rfgun_sao/*.py -Pattern "from cst_optimization.factory|import cst_optimization.factory|from cst_optimization.workflows.recovery|import cst_optimization.workflows.recovery"
`

### Real terminal output

**compileall:** exit 0 (`run.py`, `evaluator.py`, `workflow.py` recompiled).

**pytest single_pass:** 12/12 passed.

**pytest sao:** 14/14 passed.

**--help:** exit 0, flags correct.

**sys.modules check:**
`
factory: False
recovery: False
`

**Select-String:** zero matches for restricted imports.

## Risks

None.  The rfgun_sao package is an exact copy with import localisation.
No behaviour was changed.  The rfgun_single_pass validated reference
is untouched.

## Recommended next phase

**A4:** Make rfgun_sao runnable behind explicit command.  Add optional
runner entry point and verify CLI parity with rfgun_single_pass.
Still no behaviour changes, no two-pass, no shim repointing.
