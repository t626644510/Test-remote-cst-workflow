# Phase 06 -- No-CST smoke tests

## Summary

Added a suite of no-CST smoke tests under ``tests/workflows/`` that
validate the structural integrity of the extracted Workflow 1 package
without launching CST Studio Suite.  Also refactored ``run.py`` to
expose ``build_arg_parser()`` for testability.

## Files changed

| File | Action | Status |
|---|---|---|
| ``tests/workflows/test_rfgun_single_pass_imports.py`` | Created | New |
| ``workflows/rfgun_single_pass/run.py`` | Extracted ``build_arg_parser()`` | Modified |
| ``workflows/rfgun_single_pass/README.md`` | Added smoke test instructions | Modified |
| ``workflows/rfgun_single_pass/BRANCH_CONTEXT.md`` | Updated rule 4 with pytest | Modified |
| ``reports/workflow1_split/phase_06_smoke_tests.md`` | Created | New |

## Tests added (8 tests, all no-CST)

| Test | What it verifies |
|---|---|
| ``test_import_runner_without_cst`` | ``run.py`` imports, ``DEFAULT_CONFIG_PATH`` resolves |
| ``test_cli_parser_accepts_expected_flags`` | ``--config``, ``--seed``, ``--n-iter``, ``--n-initial`` work |
| ``test_config_yaml_has_wf1_sections_only`` | 8 sections present, ``workflow_2``/``tolerance`` absent, 13 params, 7 objectives |
| ``test_local_workflow_module_imports_without_factory`` | ``workflow.py`` imports without loading ``cst_optimization.factory`` |
| ``test_evaluator_class_can_be_constructed_without_cst_connection`` | ``Workflow1Evaluator`` instantiable with dummies |
| ``test_workflow_static_source_has_no_factory_import`` | Source contains no ``cst_optimization.factory`` import |
| ``test_no_wf2_objective_side_effect_imports`` | No ``wakefield``/``antenna`` imports in workflow.py |
| ``test_evaluator_static_source_has_no_factory_import`` | Same check for evaluator.py |

## Refactoring: ``build_arg_parser()`` extracted

The argparse construction was moved from inside ``main()`` to a new
module-level function ``build_arg_parser()`` in ``run.py``.  ``main()``
now calls ``build_arg_parser()``.  CLI help output is identical.

## What is intentionally not tested

- ``build_workflow_1()`` -- not called because it would connect to CST.
- ``evaluate_single_pass()`` -- not called because it would open CST.
- All physics/formulas -- these are in ``src/cst_optimization/`` and have
  their own test coverage (not part of WF1 extraction).

## No-CST guarantee

All tests pass on a machine **without** CST Studio Suite installed.
They only verify Python imports, static file analysis, CLI parsing, and
YAML structure.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "import sys; import workflows.rfgun_single_pass.workflow; print('factory loaded:', 'cst_optimization.factory' in sys.modules)"
Select-String -Path workflows/rfgun_single_pass/*.py -Pattern "from cst_optimization.factory|import cst_optimization.factory"
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
```

### Real terminal output

**Test 1 -- compileall:** exit 0 (all clean).

**Test 2 -- --help:** exit 0, all flags shown.

**Test 3 -- factory loaded check:**
```
factory loaded: False
```

**Test 4 -- Select-String import check:** zero matches.

**Test 5 -- pytest (8 tests):**
```
============================= test session starts =============================
platform win32 -- Python 3.9.13, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\lau\cst_ver3, configfile: pyproject.toml
collected 8 items

tests/workflows/test_rfgun_single_pass_imports.py::test_import_runner_without_cst PASSED [ 12%]
tests/workflows/test_rfgun_single_pass_imports.py::test_cli_parser_accepts_expected_flags PASSED [ 25%]
tests/workflows/test_rfgun_single_pass_imports.py::test_config_yaml_has_wf1_sections_only PASSED [ 37%]
tests/workflows/test_rfgun_single_pass_imports.py::test_local_workflow_module_imports_without_factory PASSED [ 50%]
tests/workflows/test_rfgun_single_pass_imports.py::test_evaluator_class_can_be_constructed_without_cst_connection PASSED [ 62%]
tests/workflows/test_rfgun_single_pass_imports.py::test_workflow_static_source_has_no_factory_import PASSED [ 75%]
tests/workflows/test_rfgun_single_pass_imports.py::test_no_wf2_objective_side_effect_imports PASSED [ 87%]
tests/workflows/test_rfgun_single_pass_imports.py::test_evaluator_static_source_has_no_factory_import PASSED [100%]

============================== 8 passed in 6.73s =============================
```

## Risks

None.  These tests are purely structural and do not affect runtime
behaviour.

## Next recommended phase

**Phase 7: Documentation / final report.**  Summarise the entire
separation effort, update any remaining docstrings, and optionally
create an end-to-end validation plan for the WF1 behaviour.
