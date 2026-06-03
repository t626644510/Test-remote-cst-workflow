# Phase 08.7 -- OptimizationResult print fix

## Summary

Fixed the last pre-existing cosmetic bug in ``run.py`` where
``OptimizationResult`` was accessed with dictionary-style ``.get()``
calls instead of dataclass attribute access.

## Bug fixed

**Symptom (Phase 8.6):**

```python
print(f"Done. Best X: {result.get('x', 'N/A')}")
AttributeError: 'OptimizationResult' object has no attribute 'get'
```

**Fix:**

```python
print(f"Done. Best X: {result.x_opt}")
print(f"Best F: {result.f_opt}")
```

``SurrogateAssistedOptimizer.optimize()`` returns an
``OptimizationResult`` dataclass (with fields ``x_opt``, ``f_opt``,
``pareto_front``, etc.), not a dict.

**This bug existed in the pre-migration ``run_workflow_1.py``** (same
code pattern).  It was masked by the earlier bugs which prevented the
pipeline from ever reaching the final print statements.

## All three pre-existing bugs fixed

| Bug | Found | Fixed |
|---|---|---|
| ``ckpt.loaded_count`` not found | Phase 8.0 | Phase 8.1 |
| Invalid kwargs to ``opt.optimize()`` | Phase 8.2 | Phase 8.3 |
| ``result.get('x')`` vs ``result.x_opt`` | Phase 8.6 | Phase 8.7  **← This** |

## Files changed

| File | Action | Status |
|---|---|---|
| ``workflows/rfgun_single_pass/run.py`` | Fixed print calls | Modified |
| ``tests/workflows/test_rfgun_single_pass_imports.py`` | Added regression test | Modified |
| ``reports/workflow1_split/phase_08_7_result_print_fix.md`` | Created | New |

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
Select-String -Path workflows/rfgun_single_pass/run.py -Pattern "result.get"
```

### Real terminal output

**Test 1 -- compileall:** exit 0 (``run.py`` recompiled).

**Test 2 -- --help:** exit 0, CLI unchanged.

**Test 3 -- pytest (12/12 passed):**
```
test_runner_prints_optimization_result_attributes PASSED  [ 91%]  ← NEW
```

**Test 4 -- Select-String:**
```
zero matches for result.get
```

## Final live re-run instruction

After all three bugfixes, a clean live run should produce:

```powershell
python run_workflow_1.py --n-initial 1 --n-iter 0
```

Expected output:
```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 7
[Workflow 1] Planned: 1 initial + 0 BO = 1
------------------------------------------------------------
...
Done. Best X: [10.7803  4.0383  3.2798 ...]
Best F: [-10719.18]
Log: D:\Results\workflow1\workflow_1_runtime.log
```

## Risks

None.  ``OptimizationResult.x_opt`` and ``.f_opt`` are the documented
public attributes of the dataclass (defined in ``optimization/base.py``).
They have been present since Phase 1.

## Next recommended phase

**Phase 9:** Finalise the branch (keep as long-lived WF1 branch or
merge into ``main`` after conflict resolution).
