# Phase 05.1 -- Path fix: hardcoded src path replaced with dynamic resolution

## Summary

Replaced the machine-specific absolute path ``_SRC_DIR = r"C:\Users\lau\cst_ver3\src"``
with the portable ``_SRC_DIR = str(_PROJECT_ROOT / "src")`` in both
``evaluator.py`` and ``workflow.py``.  The path is now computed
relative to ``__file__``, matching the pattern already established in
``run.py``.

## Files changed

| File | Action | Status |
|---|---|---|
| ``workflows/rfgun_single_pass/evaluator.py`` | Fixed path setup | Modified |
| ``workflows/rfgun_single_pass/workflow.py`` | Fixed path setup | Modified |
| ``reports/workflow1_split/phase_05_1_path_fix.md`` | Created | New |

## Exact issue fixed

**Before (both files):**
```python
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = r"C:\Users\lau\cst_ver3\src"       # hardcoded, machine-specific
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
```

**After (both files):**
```python
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")          # computed relative to __file__
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
```

This matches the pattern already used in ``run.py``.

## Behaviour impact

None.  The resolved path is identical on the current machine.  The code
will now work correctly if the repository is moved to a different
directory.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "from workflows.rfgun_single_pass.evaluator import Workflow1Evaluator; print(Workflow1Evaluator.__name__)"
python -c "from workflows.rfgun_single_pass.workflow import build_workflow_1; print(build_workflow_1.__name__)"
python -c "import workflows.rfgun_single_pass.workflow as w; print(w._SRC_DIR)"
python -c "import workflows.rfgun_single_pass.evaluator as e; print(e._SRC_DIR)"
python -c "import sys; import workflows.rfgun_single_pass.workflow; print('cst_optimization.factory' in sys.modules)"
Select-String -Path workflows/rfgun_single_pass/*.py -Pattern "C:\\Users\\lau\\cst_ver3"
```

### Real terminal output

**Test 1 -- compileall (exit 0):**
```
Listing 'src'...
Listing 'src\cst_optimization'...
...
Compiling 'workflows\rfgun_single_pass\evaluator.py'...
```

**Test 2 -- --help (exit 0):**
```
usage: run_workflow_1.py [-h] [--config CONFIG] [--seed SEED] ...
```

**Test 3 -- Workflow1Evaluator import (exit 0):**
```
Workflow1Evaluator
```

**Test 4 -- build_workflow_1 import (exit 0):**
```
build_workflow_1
```

**Test 5 -- workflow._SRC_DIR (exit 0):**
```
C:\Users\lau\cst_ver3\src
```

**Test 6 -- evaluator._SRC_DIR (exit 0):**
```
C:\Users\lau\cst_ver3\src
```

**Test 7 -- factory not loaded (exit 0):**
```
False
```

**Test 8 -- hardcoded path check (exit 0, zero matches):**
(No output -- Select-String found zero matches.)

## Risks

None.  This is a pure refactor that does not change any runtime
behaviour.

## Next recommended phase

**Phase 6: No-CST smoke tests.**  Add unit/integration tests under
``tests/workflows/``.
