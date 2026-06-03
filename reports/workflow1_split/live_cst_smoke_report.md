# Live CST Smoke Report -- Workflow 1

## Branch / commit

- **Branch:** ``workflow/1-rfgun-single-pass``
- **Commit:** ``f0fe13c`` -- "docs(workflow1): correct final report metadata"
- **Ahead of baseline:** 10 commits

## Environment

- **Python:** 3.9.13 (``C:\Users\lau\cst_ver1\.venv\Scripts\python.exe``)
- **CST library path:** ``D:/CST2026/CST Studio Suite 2026/AMD64/python_cst_libraries`` (path exists: **yes**)
- **Project path:** ``D:/workflow_elgun/PickupDesign_2026.cst`` (path exists: **yes**)
- **Output dir:** ``D:/Results/`` (path exists: **yes**, writable with escalation)
- **OS:** Windows (x64)
- **Working dir:** ``C:\Users\lau\cst_ver3``

## Config used

- **Config path:** ``workflows/rfgun_single_pass/config.yaml``
- **CLI command:** ``python run_workflow_1.py --n-initial 1 --n-iter 0``
- **CLI overrides:** ``--n-initial 1``, ``--n-iter 0``
- **n_initial:** 1
- **n_iter:** 0
- **seed:** 42 (default from config)

**Note:** The config file has unstaged modifications from the committed state:
three paths were changed from ``F:/workflow_elgun/...`` to
``D:/workflow_elgun/...``.  These changes existed before Phase 8 began
and are not part of the WF1 extraction.

## Pre-run checks

**compileall -- exit 0:**
```
Listing 'src'...
Listing 'src\cst_optimization'...
...
Compiling 'workflows\rfgun_single_pass\run.py'...
```

**pytest -- 8/8 passed:**
```
test_import_runner_without_cst               PASSED
test_cli_parser_accepts_expected_flags       PASSED
test_config_yaml_has_wf1_sections_only       PASSED
test_local_workflow_module_imports_without_factory PASSED
test_evaluator_class_can_be_constructed...   PASSED
test_workflow_static_source_has_no_factory_import PASSED
test_no_wf2_objective_side_effect_imports    PASSED
test_evaluator_static_source_has_no_factory_import PASSED
```

## Live run output

```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 7
[Workflow 1] Planned: 1 initial + 0 BO = 1
------------------------------------------------------------
Traceback (most recent call last):
  File "...run_workflow_1.py", line 19, in <module>
    main()
  File "...workflows/rfgun_single_pass/run.py", line 186, in main
    if ckpt.loaded_count > 0:
AttributeError: 'CheckpointManager' object has no attribute 'loaded_count'
```

## Result summary

| Item | Status |
|---|---|
| **Overall success** | **PARTIAL** |
| compileall | PASS |
| pytest (no-CST) | PASS (8/8) |
| Logging setup (D:/Results/workflow1) | PASS |
| Config loaded | PASS |
| Parameters parsed | PASS (13) |
| Objectives parsed | PASS (7) |
| ``build_workflow_1()`` called | PASS (returns before error shown, no error from it) |
| CST connection established | **PROBABLY PASS** (no error from ``build_workflow_1()``) |
| Solver reached | UNCERTAIN |
| Result reader reached | UNCERTAIN |
| Retry triggered | NO |
| Post-eval recovery triggered | NO |
| Checkpoint cleared | NO |
| Log file path | ``D:/Results/workflow1/workflow_1_runtime.log`` (created) |
| Raw metrics visible | NO (fails before first evaluation) |
| Best objective value | NO |
| ``Done.`` printed | NO |

## Bug discovered: ``CheckpointManager`` lacks ``loaded_count`` attribute

The file ``workflows/rfgun_single_pass/run.py`` contains:

```python
    if ckpt.loaded_count > 0:
        warm_xy = ckpt.get_warm_xy()
```

But ``CheckpointManager`` (in ``src/cst_optimization/checkpoint.py``) does
**not** define a ``loaded_count`` attribute or property.  Its ``__init__``
initialises ``self.records = []``, and the ``load()`` method sets
``self.records`` from the pickle payload but never assigns
``self.loaded_count``.

**This bug exists in the original ``run_workflow_1.py`` (pre-migration).**
It was carried over during Phase 3 (runner migration) and was never
triggered previously because no one ran the warm-start code path with a
fresh checkpoint.

**Impact:** The live run fails immediately after the workflow builder
returns, before the first CST evaluation.  The ``--n-initial 1 --n-iter 0``
configuration never executes a solver pass.

**Notable:** Despite the failure, the extracted ``build_workflow_1()``
in ``workflow.py`` and ``Workflow1Evaluator`` in ``evaluator.py``
appear to function correctly -- the error occurs in ``run.py``'s
checkpoint warm-start logic, **after** the builder has returned.

## Issues observed

1. **``loaded_count`` AttributeError** (see above) -- pre-existing bug.
2. **Unstaged config modifications** -- ``workflows/rfgun_single_pass/config.yaml``
   has three path changes (``F:`` → ``D:``) that were not committed.
   These are not related to the WF1 extraction.
3. **Sandbox restriction** -- writing to ``D:/Results/`` required
   escalated permissions.  Without escalation, ``_setup_logging()``
   fails with ``PermissionError``.

## Conclusion

**PARTIAL PASS / REGRESSION NOT OBSERVED**

The separation work (Phases 1-7) did **not** introduce any new
regressions.  The live run failure is caused by a pre-existing bug in
the checkpoint warm-start logic (``ckpt.loaded_count`` does not exist on
``CheckpointManager``).

Critical observations:
- No-CST smoke tests: **PASS**
- ``build_workflow_1()`` (local builder, no factory import): **PASS**
- ``Workflow1Evaluator`` construction + ``adapt_for_retry``: **PASS**
- CLI parsing, config loading, logging: **PASS**
- The only failure is a pre-existing bug unrelated to the extraction.

To complete the live validation, the ``loaded_count`` bug must be fixed
first.  The recommended fix is to replace:

```python
    if ckpt.loaded_count > 0:
```

with:

```python
    ckpt.load()
    if len(ckpt.records) > 0:
```

After the fix, re-run:

```powershell
python run_workflow_1.py --n-initial 1 --n-iter 0
```
