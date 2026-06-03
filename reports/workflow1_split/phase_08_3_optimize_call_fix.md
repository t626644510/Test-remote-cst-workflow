# Phase 08.3 -- optimize() call fix

## Summary

Fixed a pre-existing bug where ``run.py`` passed ``n_initial`` and
``n_iterations`` keyword arguments to ``opt.optimize()``, which
``SurrogateAssistedOptimizer.optimize()`` does not accept (these
values are already set in the constructor).

## Bug fixed

**Symptom:** Running ``python run_workflow_1.py --n-initial 1 --n-iter 0``
failed with::

    TypeError: optimize() got an unexpected keyword argument "n_initial"

**Root cause:** The ``opt.optimize()`` call in ``run.py`` was:

```python
result = opt.optimize(
    evaluator=evaluator,
    prior_data=prior_data,
    n_initial=n_initial,       # NOT supported by the optimize() signature
    n_iterations=n_iterations, # NOT supported by the optimize() signature
)
```

The ``SurrogateAssistedOptimizer.optimize()`` method accepts only
``evaluator``, ``bounds_controller``, ``prior_data``, and
``n_initial_extra``.  The ``n_initial`` and ``n_iterations`` values are
set during SAO construction (via ``_build_sao()``).  The CLI overrides
(``--n-initial``, ``--n-iter``) were already correctly modifying the
config dict before the SAO constructor ran, so no override logic was
lost.

**Fix:** Remove the two unsupported keyword arguments:

```python
result = opt.optimize(
    evaluator=evaluator,
    prior_data=prior_data,
)
```

The ``n_initial`` and ``n_iterations`` variables are still used for
logging and the startup banner (lines 135, 138, 177-178, 182).

**This bug existed in the pre-migration code** (Phase 1's
``run_workflow_1.py`` also passed ``n_initial`` and ``n_iterations`` to
``optimize()``).  It was masked by the ``loaded_count`` bug which
crashed the run earlier in the startup sequence (fixed in Phase 8.1).

## Files changed

| File | Action | Status |
|---|---|---|
| ``workflows/rfgun_single_pass/run.py`` | Removed 2 invalid kwargs from ``opt.optimize()`` | Modified |
| ``tests/workflows/test_rfgun_single_pass_imports.py`` | Added AST-based regression test | Modified |
| ``reports/workflow1_split/phase_08_3_optimize_call_fix.md`` | Created | New |

## Why this is safe

1. ``n_initial`` and ``n_iterations`` are already set in the SAO
   constructor via ``_build_sao()``.  The constructor reads from
   ``opt_cfg`` which includes the CLI overrides.
2. The ``n_initial`` and ``n_iterations`` variables remain in ``run.py``
   for logging/display purposes only.
3. The SAO's own ``optimize()`` method uses ``self._n_initial``
   (set in constructor) internally.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
python -c "import inspect; ...; print(inspect.signature(SurrogateAssistedOptimizer.optimize))"
Select-String -Path workflows/rfgun_single_pass/run.py -Pattern "n_initial=n_initial|n_iterations=n_iterations"
```

### Real terminal output

**Test 1 -- compileall (exit 0):**
```
Compiling "workflows\\rfgun_single_pass\\run.py"...
```

**Test 2 -- --help (exit 0):**
```
usage: run_workflow_1.py [-h] [--config CONFIG] [--seed SEED] ...
```

**Test 3 -- pytest (10/10 passed):**
```
test_runner_optimize_uses_only_supported_kwargs PASSED  [ 90%]  ← NEW
```

**Test 4 -- SAO.optimize() signature:**
```
(self, evaluator, bounds_controller, prior_data, n_initial_extra)
```
No ``n_initial`` or ``n_iterations`` parameters.

**Test 5 -- Select-String for invalid kwargs:**
```
zero matches for invalid kwargs
```

## Live CST re-run instruction

After this fix (combined with the Phase 8.1 checkpoint fix):

```powershell
python run_workflow_1.py --n-initial 1 --n-iter 0
```

## Risks

None.  ``n_initial`` and ``n_iterations`` were redundant (already set
in the SAO constructor).  Removing them from the ``optimize()`` call
changes the error from ``TypeError`` to a successful run.

## Next recommended phase

**Phase 8.4:** Re-run live CST validation now that both pre-existing
bugs are fixed.
