# Phase 07 -- Final report: Workflow 1 separation summary

## Summary

Workflow 1 (single-project single-pass RF gun SAO optimisation) has
been separated from the monolithic ``src/cst_optimization/factory.py``
into an independent package under ``workflows/rfgun_single_pass/``.

The entry point ``run_workflow_1.py`` is preserved as a compatibility
shim.  The actual runner, config, builder, evaluator, and no-CST smoke
tests are self-contained within the new package.  Shared infrastructure
(``core/``, ``parameters/``, ``objectives/``, ``optimization/``) is
still reused from ``src/cst_optimization/``.

## Git branch

``workflow/1-rfgun-single-pass``

## Commit range

8 commits ahead of the shared baseline (``main`` from which this branch
was created):

| Commit | Phase | Description |
|---|---|---|
| ``7a44263`` | 1 | Inventory dependencies |
| ``8fa2425`` | 2 | Add workflow scaffold |
| ``3084f44`` | 3 | Move runner behind compatibility shim |
| ``ffcb64d`` | 4 | Split workflow config |
| ``b3d9c6f`` | 4.1 | Log selected config after logging setup |
| ``11b81ed`` | 5 | Extract local evaluator and builder |
| ``c7ab320`` | 5.1 | Compute src path relative to workflow package |
| ``13bb3d5`` | 6 | Add no-CST smoke tests |
| *(current)* | 7 | Summarise split status |

## Final structure

```
run_workflow_1.py                                 # compatibility shim (unchanged, 12 lines)
workflows/
    __init__.py
    rfgun_single_pass/
        __init__.py                               # package marker
        config.yaml                               # WF1-specific config (8 sections, 13 params, 7 objectives)
        run.py                                    # CLI runner + build_arg_parser()
        workflow.py                               # local build_workflow_1() builder
        evaluator.py                              # Workflow1Evaluator class
        README.md
        BRANCH_CONTEXT.md
reports/
    workflow1_split/
        phase_01_inventory.md
        phase_02_scaffold.md
        phase_03_runner_shim.md
        phase_04_config_split.md
        phase_04_1_logging_fix.md
        phase_05_evaluator.md
        phase_05_1_path_fix.md
        phase_06_smoke_tests.md
        phase_07_final_report.md                  (this file)
tests/
    workflows/
        test_rfgun_single_pass_imports.py          # 8 no-CST smoke tests
```

## What changed

1.  **Phase 1 -- Inventory:**  Documented all modules, config keys, and
    runtime dependencies touched by Workflow 1.  Identified cross-workflow
    pollution risks and the first extraction candidates.
2.  **Phase 2 -- Skeleton:**  Created ``workflows/rfgun_single_pass/``
    directory with ``__init__.py``, ``README.md``, ``BRANCH_CONTEXT.md``.
3.  **Phase 3 -- Runner migration:**  Moved the complete runner logic
    from ``run_workflow_1.py`` to ``workflows/rfgun_single_pass/run.py``.
    The root script became a 12-line shim.  Path resolution uses
    ``Path(__file__).resolve().parents[2]``.
4.  **Phase 4 -- Config split:**  Extracted WF1-only sections from
    ``config/default.yaml`` into ``workflows/rfgun_single_pass/config.yaml``.
    Added ``--config`` CLI flag.  Default config path changed to the
    WF1-specific file.
5.  **Phase 4.1 -- Logging fix:**  Reordered log statements so the
    config path message is logged after ``_setup_logging()``.
6.  **Phase 5 -- Evaluator extraction:**  Extracted
    ``_evaluate_single_pass()`` from ``factory.py::build_workflow_1()``
    into ``Workflow1Evaluator``.  Created ``workflow.py`` with a local
    builder that does not import ``cst_optimization.factory``.  Objective
    module imports restricted to WF1-needs only (no wakefield/antenna).
7.  **Phase 5.1 -- Path fix:**  Replaced machine-specific absolute
    ``_SRC_DIR`` with portable ``str(_PROJECT_ROOT / "src")``.
8.  **Phase 6 -- Smoke tests:**  Added 8 no-CST smoke tests
    (``pytest``).  Extracted ``build_arg_parser()`` in ``run.py`` for
    CLI-parser testability.

## Current execution path

```
python run_workflow_1.py
  -> from workflows.rfgun_single_pass.run import main
  -> main()
    -> build_arg_parser() + parse_args
    -> yaml.safe_load(config_path)
    -> _setup_logging()
    -> CheckpointManager
    -> from workflows.rfgun_single_pass.workflow import build_workflow_1
    -> build_workflow_1(config, checkpoint_callback)
      -> _build_parameters()            (local)
      -> _build_objectives()             (local, WF1-only modules)
      -> CSTConnection + connect()
      -> SolverRunner
      -> Workflow1Evaluator              (evaluator.py)
      -> EvaluationRetryHandler           (core/retry.py, if enabled)
      -> _build_sao()                    (local)
      -> SurrogateAssistedOptimizer      (optimization/sao.py)
      -> returns (container, optimiser, scalar_evaluator)
    -> opt.optimize(evaluator=...)
```

All shared infrastructure is still resolved from ``src/cst_optimization/``.

## Dependencies removed

- ``run.py`` no longer imports ``cst_optimization.factory`` (was
  ``from cst_optimization.factory import build_workflow_1``).
- ``workflow.py`` does **not** import WF2/WF3 objective modules:
  ``wakefield``, ``antenna``.
- Workflow 1 default config is **not** ``config/default.yaml`` any more;
  it reads ``workflows/rfgun_single_pass/config.yaml``.
- Verified: ``import workflows.rfgun_single_pass.workflow`` does not
  load ``cst_optimization.factory`` into ``sys.modules``.

## Dependencies still shared

These modules are reused from ``src/cst_optimization/`` and are outside
the scope of this separation:

- ``core/connection.py`` -- ``CSTConnection``
- ``core/project.py`` -- ``CSTProject``
- ``core/solver.py`` -- ``SolverRunner``, ``SolverResult``
- ``core/results.py`` -- ``ResultReader``
- ``core/retry.py`` -- ``EvaluationRetryHandler``, ``RetryConfig``
- ``core/cleanup.py`` -- process kill, lock removal
- ``core/timeout.py`` -- wall-clock timeout
- ``core/errors.py`` -- exception hierarchy
- ``parameters/base.py`` -- ``ParameterSet``, ``ParamRange``
- ``parameters/geometry.py`` -- ``GeometryParameter``
- ``objectives/base.py`` -- ``ObjectiveFunction``, ``CompositeObjective``
- ``objectives/modes.py`` -- optimisation modes (minimize, maximize, etc.)
- ``objectives/registry.py`` -- ``get_objective``, ``get_mode``
- ``objectives/frequency.py`` -- ``ResonantFreqObjective``
- ``objectives/quality.py`` -- ``Q0Objective``, ``CouplingBetaObjective``
- ``objectives/field.py`` -- ``PeakElectricField``, ``MaxModifiedPoynting``, etc.
- ``optimization/base.py`` -- ``BaseOptimizer``, ``OptimizationResult``
- ``optimization/sao.py`` -- ``SurrogateAssistedOptimizer``
- ``optimization/acquisition.py`` -- EI, UCB, PI
- ``optimization/sampling.py`` -- LHS (via SAO)
- ``physics/formulas.py`` -- half-power bandwidth, coupling beta, Q0
- ``physics/poynting.py`` -- modified Poynting vector
- ``physics/heating.py`` -- pulsed heating delta-T
- ``workflows/recovery.py`` -- ``EvaluationResult``, ``EvaluationStatus``
- ``checkpoint.py`` -- ``CheckpointManager`` (imported in ``run.py``)

## What was intentionally not changed

- ``src/cst_optimization/`` -- **not modified** in any phase.
- ``run_workflow_2.py``, ``run_workflow_3.py`` -- **not modified**.
- ``config/default.yaml`` -- **not modified**; still serves WF2/WF3.
- ``config/workflow_3.yaml`` -- **not modified**.
- ``examples/`` -- **not modified**.
- ``run_workflow_1.py`` -- **not deleted**; kept as compatibility shim.
- The full CST workflow was **never executed** during this separation
  (all tests are no-CST).

## Validation performed

**Test 1 -- ``compileall`` (exit 0):**
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

**Test 2 -- ``--help`` (exit 0):**
```
usage: run_workflow_1.py [-h] [--config CONFIG] [--seed SEED]
                         [--n-iter N_ITER] [--n-initial N_INITIAL]
```

**Test 3 -- pytest (8/8 passed):**
```
tests/workflows/test_rfgun_single_pass_imports.py::test_import_runner_without_cst PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_cli_parser_accepts_expected_flags PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_config_yaml_has_wf1_sections_only PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_local_workflow_module_imports_without_factory PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_evaluator_class_can_be_constructed_without_cst_connection PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_workflow_static_source_has_no_factory_import PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_no_wf2_objective_side_effect_imports PASSED
tests/workflows/test_rfgun_single_pass_imports.py::test_evaluator_static_source_has_no_factory_import PASSED
```

**Test 4 -- factory not loaded:**
```
factory loaded: False
```

**Test 5 -- factory import static check:**
Zero matches.

## Remaining risks

1.  **Live CST equivalence not validated:**  All validation was done
    without CST Studio Suite.  Numerical equivalence with the
    pre-separation state should be verified with a small real run
    (``--n-initial 1 --n-iter 0``) before merging.
2.  **Hardcoded physics constants in evaluator:**  ``target_freq=11.424``,
    ``gc=0.125``, ``e_target=200e6``, ``pulse_width_ns=300``,
    ``rrr=5.5`` are still hardcoded in ``evaluate_single_pass()``.
    These should be config-driven in a follow-up.
3.  **Helper duplication:**  ``_build_parameters()``, ``_build_objectives()``,
    ``_build_sao()``, ``_resolve_named_weights()`` were copied (with
    minimal WF1-specific trimming) from ``factory.py``.  Any bugfix to
    the originals will need manual sync.
4.  **Branch not merged:**  This branch is 9 commits ahead and has not
    been merged into ``main``.  Conflict risk with any changes to the
    shared ``src/cst_optimization/`` modules in the meantime.

## Recommended next steps

1.  **Live CST smoke run:**  Execute
    ``python run_workflow_1.py --n-initial 1 --n-iter 0``
    on a machine with CST Studio Suite 2026 to verify that the full
    pipeline (connection, solver, evaluator, retry, checkpoint)
    produces identical results to the pre-separation code path.
2.  **Record live run report:**  Document the CST version, project path,
    solver time, and output values in a follow-up report.
3.  **Decide branch strategy:**  Either keep this as a long-lived WF1
    development branch, or merge into ``main`` after live validation.
    If merging, resolve any conflicts with changes to shared modules.
4.  **Config-drive physics constants:**  Extract the hardcoded evaluator
    constants into the ``config.yaml`` ``obj_params`` section to remove
    the remaining WF1-specific code from the evaluator.
5.  **Sync helpers:**  If ``factory.py`` helpers are updated for WF2/WF3,
    propagate the changes to the copies in ``workflow.py``.
