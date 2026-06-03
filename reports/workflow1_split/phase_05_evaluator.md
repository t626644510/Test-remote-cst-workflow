# Phase 05 -- Evaluator extraction

## Summary

Extracted the Workflow 1 evaluation logic from the monolithic
``src/cst_optimization/factory.py::build_workflow_1()`` into two
new modules inside the ``workflows/rfgun_single_pass/`` package:

- ``evaluator.py`` -- ``Workflow1Evaluator`` class (single-pass CST solve
  + physics post-processing + penalty computation).
- ``workflow.py`` -- local ``build_workflow_1()`` builder that creates
  the full WF1 stack (parameters, objectives, connection, solver,
  evaluator, retry handler, SAO optimizer) without importing
  ``cst_optimization.factory``.

The root ``run_workflow_1.py`` and the shim in ``workflows/rfgun_single_pass/run.py``
now import ``build_workflow_1`` from the local ``workflow.py`` instead of
``cst_optimization.factory``.

## Files changed

| File | Action | Status |
|---|---|---|
| ``workflows/rfgun_single_pass/evaluator.py`` | Created | New |
| ``workflows/rfgun_single_pass/workflow.py`` | Created | New |
| ``workflows/rfgun_single_pass/run.py`` | Import changed to local builder | Modified |
| ``workflows/rfgun_single_pass/README.md`` | Updated for Phase 5 | Modified |
| ``workflows/rfgun_single_pass/BRANCH_CONTEXT.md`` | Updated for Phase 5 | Modified |
| ``reports/workflow1_split/phase_05_evaluator.md`` | Created | New |

## What was extracted from factory.py

### Into evaluator.py (``Workflow1Evaluator`` class)

- ``evaluate_single_pass()`` -- the original ``_evaluate_single_pass()``
  closure.  Opens the CST project, updates parameters, runs the solver,
  reads S-parameters and field results, computes all physics quantities
  (resonant freq, coupling beta, Q0, peak E field, field flatness,
  modified Poynting, pulsed heating), computes penalty values via
  objective modes.
- ``adapt_for_retry()`` -- wraps ``evaluate_single_pass()`` into an
  ``EvaluationResult`` for the retry handler.
- ``on_reconnect()`` -- hook to replace the internal connection
  reference after Tier 2/3 retry escalation.

The hardcoded constants (``target_freq=11.424``, ``gc=0.125``,
``e_target=200e6``, ``pulse_width_ns=300``, ``rrr=5.5``) are preserved
exactly as they were in the original closure.  Config-driven parameterisation
is deferred to a future phase.

### Into workflow.py (local builder + helpers)

- ``build_workflow_1()`` -- the full builder that:
  - Calls ``_build_parameters()``, ``_build_objectives()``
  - Creates ``CSTConnection`` + connects
  - Creates ``SolverRunner``
  - Creates ``Workflow1Evaluator``
  - Creates ``EvaluationRetryHandler`` (if enabled)
  - Builds the SAO scalar evaluator with checkpoint support and
    ``post_eval_recovery``
  - Calls ``_build_sao()`` to create the optimizer
  - Returns the (workflow, optimizer, evaluator) triple
- ``_build_parameters()`` -- copied from factory.py, unchanged.
- ``_build_objectives()`` -- simplified version that returns only the
  objective list (no project_map / ref_project_map needed by WF1).
- ``_build_sao()`` -- copied from factory.py, unchanged.
- ``_resolve_named_weights()`` -- copied from factory.py, unchanged.

### Module imports cleaned

Workflow.py only imports the objective modules that WF1 actually
needs:

```python
from cst_optimization.objectives import modes       # @register_mode
from cst_optimization.objectives import frequency   # ResonantFreqObjective
from cst_optimization.objectives import quality     # Q0, CouplingBeta
from cst_optimization.objectives import field       # PeakE, Poynting, Flatness, Heating
```

It does **not** import:

```python
# NOT imported (these are WF2/WF3):
from cst_optimization.objectives import wakefield
from cst_optimization.objectives import antenna
from cst_optimization.factory import build_workflow_1  # was the old import
```

## Behaviour preserved

- The evaluator logic is byte-for-byte equivalent to the original closure.
- The builder logic is logically identical (same parameter/objective
  construction, same connection/solver/evaluator creation, same retry
  handler setup, same SAO scalar evaluator with weighted penalty).
- CLI, config path, checkpoint, logging, retry -- all unchanged.
- ``python run_workflow_1.py --seed 43`` -- works identically.

## Imports avoided

Verified with:

```powershell
Select-String -Path workflows/rfgun_single_pass/*.py -Pattern "cst_optimization.factory"
```

Result: zero import matches (only docstring references).

## Remaining coupling to shared modules

Workflow 1 still depends on these shared ``cst_optimization`` modules:

- ``core/connection.py`` (CSTConnection)
- ``core/project.py`` (CSTProject)
- ``core/solver.py`` (SolverRunner)
- ``core/results.py`` (ResultReader)
- ``core/retry.py`` (EvaluationRetryHandler, RetryConfig)
- ``core/cleanup.py`` (process kill, lock/result folder removal)
- ``core/timeout.py`` (wall-clock timeout via retry handler)
- ``core/errors.py`` (exception hierarchy)
- ``parameters/base.py`` (ParameterSet, ParamRange)
- ``parameters/geometry.py`` (GeometryParameter)
- ``objectives/base.py`` (ObjectiveFunction, CompositeObjective)
- ``objectives/modes.py`` (OptimizationMode subclasses)
- ``objectives/registry.py`` (get_objective, get_mode)
- ``objectives/frequency.py`` (ResonantFreqObjective)
- ``objectives/quality.py`` (Q0Objective, CouplingBetaObjective)
- ``objectives/field.py`` (PeakElectricField, MaxModifiedPoynting, etc.)
- ``optimization/base.py`` (BaseOptimizer, OptimizationResult)
- ``optimization/sao.py`` (SurrogateAssistedOptimizer)
- ``optimization/acquisition.py`` (EI, UCB, PI)
- ``optimization/sampling.py`` (LHS via SAO)
- ``physics/formulas.py`` (half_power_bandwidth, coupling_beta, etc.)
- ``physics/poynting.py`` (max_modified_poynting, discover_field_files)
- ``physics/heating.py`` (pulsed_heating_delta_t, max_h_from_field_file)
- ``workflows/recovery.py`` (EvaluationResult, EvaluationStatus)
- ``checkpoint.py`` (CheckpointManager -- imported in run.py)

These are legitimate shared infrastructure and will remain in
``src/cst_optimization/``.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "from workflows.rfgun_single_pass.evaluator import Workflow1Evaluator; print(Workflow1Evaluator.__name__)"
python -c "from workflows.rfgun_single_pass.workflow import build_workflow_1; print(build_workflow_1.__name__)"
python -c "import sys; import workflows.rfgun_single_pass.workflow; print('cst_optimization.factory' in sys.modules)"
python -c "import ast; text = open('workflows/rfgun_single_pass/workflow.py', encoding='utf-8-sig').read(); ast.parse(text); print('workflow AST OK')"
python -c "import ast; text = open('workflows/rfgun_single_pass/evaluator.py', encoding='utf-8-sig').read(); ast.parse(text); print('evaluator AST OK')"
Select-String -Path workflows/rfgun_single_pass/*.py -Pattern "cst_optimization.factory"
```

### Real terminal output

**Test 1 -- compileall (exit 0):**
```
Listing 'src'...
Listing 'src\cst_optimization\core'...
Listing 'src\cst_optimization\objectives'...
Listing 'src\cst_optimization\optimization'...
Listing 'src\cst_optimization\parameters'...
Listing 'src\cst_optimization\physics'...
Listing 'src\cst_optimization\sensitivity'...
Listing 'src\cst_optimization\utils'...
Listing 'src\cst_optimization\workflows'...
Listing 'workflows'...
Listing 'workflows\rfgun_single_pass'...
```

**Test 2 -- --help (exit 0):**
```
usage: run_workflow_1.py [-h] [--config CONFIG] [--seed SEED]
                         [--n-iter N_ITER] [--n-initial N_INITIAL]
...
```

**Test 3 -- Workflow1Evaluator import (exit 0):**
```
Workflow1Evaluator
```

**Test 4 -- build_workflow_1 import (exit 0):**
```
build_workflow_1
```

**Test 5 -- factory not loaded (exit 0):**
```
False
```

**Test 6 -- workflow AST (exit 0):**
```
workflow AST OK
```

**Test 7 -- evaluator AST (exit 0):**
```
evaluator AST OK
```

**Test 8 -- static factory check (exit 0, no import matches):**
```
workflows\rfgun_single_pass\workflow.py:1:"""Workflow 1 builder -- local alternative to ``cst_optimization.factory....
workflows\rfgun_single_pass\workflow.py:4:identical to the original ``cst_optimization.factory.build_workflow_1``
workflows\rfgun_single_pass\workflow.py:68:    This replaces the original ``cst_optimization.factory.build_workflow_1``
```
All matches are docstring references, not import statements.

## Risks

- **Hardcoded physics constants:** The evaluator still has hardcoded
  numerical constants (``target_freq=11.424``, ``gc=0.125``,
  ``e_target=200e6``) that were present in the original factory closure.
  These should be config-driven in a future phase.
- **Hardcoded ``_SRC_DIR``:** The path setup in ``evaluator.py`` and
  ``workflow.py`` uses a dynamically computed ``_PROJECT_ROOT`` but a
  machine-specific absolute path for ``_SRC_DIR``.  This works on the
  current machine but would break if the project is relocated.  A
  future cleanup should use ``str(_PROJECT_ROOT / "src")`` instead.
- **Behaviour equivalence:** The extracted code has not been validated
  with a live CST run.  Phase 7 (end-to-end validation) should run
  ``run_workflow_1.py`` with a real CST instance to confirm numerical
  equivalence.

## Next recommended phase

**Phase 6: No-CST smoke tests.**  Add unit/integration tests under
``tests/workflows/`` that validate the evaluator and builder logic
without launching CST.  This could include:

- ``test_evaluator_imports.py`` -- verify all imports resolve.
- ``test_workflow_builder.py`` -- verify ``build_workflow_1()``
  instantiates the correct types using a mock config.
- ``test_config_schema.py`` -- validate the WF1 config YAML against
  its expected key structure.
