# Live CST Smoke Report 2 -- Workflow 1

## Branch / commit

- **Branch:** ``workflow/1-rfgun-single-pass``
- **Commit:** ``b3f1e78`` -- "fix(workflow1): load checkpoint before warm start"
- **Ahead of baseline:** 12 commits

## Environment

- **Python:** 3.9.13
- **CST library path:** ``D:/CST2026/CST Studio Suite 2026/AMD64/python_cst_libraries``
- **Project path:** ``D:/workflow_elgun/PickupDesign_2026.cst``
- **Output dir:** ``D:/Results/``
- **OS:** Windows x64

## Config used

- **Primary config:** ``workflows/rfgun_single_pass/config.yaml`` (unstaged
  modifications: 3 paths changed ``F:`` → ``D:``)
- **Local copy for run:** ``workflows/rfgun_single_pass/config.local.yaml``
  (git-ignored, not committed)
- **CLI command:** ``python run_workflow_1.py --config workflows/rfgun_single_pass/config.local.yaml --n-initial 1 --n-iter 0``
- **CLI overrides:** ``--n-initial 1``, ``--n-iter 0``
- **n_initial:** 1
- **n_iter:** 0
- **seed:** 42 (default from config)

## Pre-run checks

**compileall -- exit 0:**
```
Compiling "workflows\\rfgun_single_pass\\run.py"...
```

**pytest -- 9/9 passed:**
```
test_import_runner_without_cst                      PASSED
test_cli_parser_accepts_expected_flags              PASSED
test_config_yaml_has_wf1_sections_only              PASSED
test_local_workflow_module_imports_without_factory   PASSED
test_evaluator_class_can_be_constructed...           PASSED
test_workflow_static_source_has_no_factory_import    PASSED
test_no_wf2_objective_side_effect_imports            PASSED
test_runner_does_not_use_loaded_count               PASSED
test_evaluator_static_source_has_no_factory_import   PASSED
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
  File "...run.py", line 214, in main
    result = opt.optimize(
TypeError: optimize() got an unexpected keyword argument "n_initial"
```

Exit code: **1**

## Runtime milestones

| Milestone | Status |
|---|---|
| Config loaded | PASS |
| Logging setup | PASS |
| Checkpoint load | PASS (no prior checkpoint) |
| Builder returned | PASS |
| Parameters parsed (13) | PASS |
| Objectives parsed (7) | PASS |
| Workspace header printed | PASS |
| CST connection | PASS (no error from builder) |
| Solver reached | FAIL (never reached) |
| Solver completed | FAIL (never reached) |
| Result reader reached | FAIL (never reached) |
| Raw metrics computed | FAIL (never reached) |
| Retry triggered | NO |
| Post-eval recovery triggered | NO |
| Checkpoint cleared | NO |
| Done printed | NO |

## Result summary

**FAIL**

The live run was blocked before the first solver invocation by a second
pre-existing bug in the ``opt.optimize()`` call.

## Second bug discovered: invalid keyword arguments to ``optimize()``

The file ``workflows/rfgun_single_pass/run.py`` calls:

```python
result = opt.optimize(
    evaluator=evaluator,
    prior_data=prior_data,
    n_initial=n_initial,
    n_iterations=n_iterations,
)
```

However, ``SurrogateAssistedOptimizer.optimize()`` does **not** accept
``n_initial`` or ``n_iterations``.  Its signature is:

```python
def optimize(self, evaluator=None, bounds_controller=None,
             prior_data=None, n_initial_extra=0):
```

The ``n_initial`` and ``n_iterations`` values are already set during
SAO construction (via ``_build_sao()``).  The CLI overrides
(``--n-initial``, ``--n-iter``) correctly modify the config dict before
``_build_sao()`` reads it, so the SAO constructor already receives the
overridden values.  The extra keyword arguments in the ``optimize()``
call are both redundant and invalid.

**This bug exists in the original pre-migration code** (Phase 1's
``run_workflow_1.py`` had the same call pattern).  It was masked by the
``loaded_count`` bug in Phase 8.0 which crashed the run earlier in the
startup sequence.

**Impact:** The live run fails unconditionally when ``--n-initial`` or
``--n-iter`` are provided.  Without CLI overrides (default config values
n_initial_samples=20, n_iterations=100), the same bug would surface
because the default values are also passed to ``optimize()``.

**Fix:** Remove the two keyword arguments from the ``optimize()`` call
in ``run.py``:

```python
result = opt.optimize(
    evaluator=evaluator,
    prior_data=prior_data,
)
```

No other changes are needed.

## Issues observed

1. **``n_initial`` / ``n_iterations`` passed to ``optimize()``** --
   pre-existing bug, blocks all live runs.  See above.
2. **Unstaged config changes** -- ``config.yaml`` has three path changes
   (``F:`` → ``D:``) not committed.  Not related to WF1 extraction.
3. **Sandbox write restriction** -- writing to ``D:/Results/`` requires
   escalated permissions.

## Conclusion

**FAIL -- Two pre-existing bugs block the live CST run**

1. Phase 8.0: ``ckpt.loaded_count`` not found (fixed in Phase 8.1)
2. Phase 8.2: invalid keyword args to ``opt.optimize()`` (not yet fixed)

The extracted components (``workflow.py``, ``evaluator.py``) show no
signs of regression.  All no-CST smoke tests pass.  Once the second
bug is fixed, the live CST run should complete.

**Recommended fix timeline:**
- Phase 8.3: Fix the ``opt.optimize()`` call in ``run.py``
- Phase 8.4: Re-run live CST validation
- Phase 9: Finalise branch (keep or merge)
