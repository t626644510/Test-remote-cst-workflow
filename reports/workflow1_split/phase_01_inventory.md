# Phase 01 鈥?Workflow 1 Dependency Inventory

## Summary

This report catalogues every module, config key, and runtime dependency touched by Workflow 1 (single-project single-pass frequency-domain SAO optimisation for the X-band RF gun cavity). The goal is to establish a clean baseline so subsequent refactoring can extract WF1 into its own package without breaking Workflow 2 (HOM antenna wakefield) or Workflow 3 (recovery/tolerance optimisation).

## Files inspected

| File | Role |
|---|---|
| `run_workflow_1.py` | Entry point script |
| `config/default.yaml` | Shared configuration (WF1 + WF2 + WF3) |
| `src/cst_optimization/factory.py` | Builds all workflow objects |
| `src/cst_optimization/checkpoint.py` | Checkpoint persistence |
| `src/cst_optimization/core/connection.py` | CST DesignEnvironment lifecycle |
| `src/cst_optimization/core/project.py` | CST project parameter management |
| `src/cst_optimization/core/solver.py` | Solver execution + error classification |
| `src/cst_optimization/core/results.py` | Result reading layer (S-param, scalars, 2D) |
| `src/cst_optimization/core/retry.py` | Three-tier escalation retry handler |
| `src/cst_optimization/core/errors.py` | Exception hierarchy |
| `src/cst_optimization/core/cleanup.py` | Process kill + lock/result folder removal |
| `src/cst_optimization/core/timeout.py` | Wall-clock timeout for COM calls |
| `src/cst_optimization/core/messages.py` | CST message window capture (WF2) |
| `src/cst_optimization/core/orchestrator.py` | Multi-project orchestrator (WF2) |
| `src/cst_optimization/parameters/base.py` | ParameterSet, ParamRange, constraints |
| `src/cst_optimization/parameters/geometry.py` | GeometryParameter |
| `src/cst_optimization/objectives/base.py` | ObjectiveFunction ABC |
| `src/cst_optimization/objectives/modes.py` | OptimizationMode implementations |
| `src/cst_optimization/objectives/registry.py` | Global @register_objective / @register_mode |
| `src/cst_optimization/objectives/frequency.py` | ResonantFreqObjective |
| `src/cst_optimization/objectives/quality.py` | Q0, CouplingBeta, InputPower objectives |
| `src/cst_optimization/objectives/field.py` | PeakE, MaxModifiedPoynting, Flatness, PulsedHeating |
| `src/cst_optimization/objectives/wakefield.py` | Z_long, Z_trans objectives (WF2 only) |
| `src/cst_optimization/objectives/antenna.py` | Antenna absorption objectives (WF2 only) |
| `src/cst_optimization/optimization/base.py` | BaseOptimizer, OptimizationResult |
| `src/cst_optimization/optimization/sao.py` | SurrogateAssistedOptimizer |
| `src/cst_optimization/optimization/acquisition.py` | EI / UCB / PI acquisition functions |
| `src/cst_optimization/optimization/sampling.py` | LHS, Sobol, random sampling |
| `src/cst_optimization/optimization/logging.py` | Excel dual-sheet optimisation logger |
| `src/cst_optimization/optimization/adaptive_bounds.py` | Two-phase adaptive bounds control |
| `src/cst_optimization/optimization/conditional_gate.py` | Adaptive GP-gated conditional (WF2) |
| `src/cst_optimization/physics/formulas.py` | Half-power BW, coupling beta, Q0 |
| `src/cst_optimization/physics/poynting.py` | Modified Poynting vector |
| `src/cst_optimization/physics/heating.py` | Pulsed heating delta-T |
| `src/cst_optimization/physics/cavity.py` | PhysicsQuantity classes (LoadedQ, IntrinsicQ, etc.) |
| `src/cst_optimization/physics/wakefield.py` | Wake impedance reading/scalarization (WF2) |
| `src/cst_optimization/physics/quantities.py` | PhysicsQuantity ABC |
| `src/cst_optimization/workflows/recovery.py` | RecoveryWorkflowEvaluator (WF3) |

---

## Workflow 1 call graph

```
run_workflow_1.py::main()
  |
  +-- yaml.safe_load(CONFIG_PATH)                    # config/default.yaml
  +-- _setup_logging(cfg["logging"])
  |
  +-- CheckpointManager(ckpt_path)                   # checkpoint.py
  +-- _on_evaluation()  [inner callback]
  |
  +-- build_workflow_1(cfg, checkpoint_callback=...)  # factory.py
  |     |
  |     +-- _build_parameters(cfg["parameters"])      # GeometryParameter 脳 13
  |     |     +-- GeometryParameter                   # parameters/geometry.py
  |     |     +-- ParameterSet                         # parameters/base.py
  |     |
  |     +-- _build_objectives(cfg["objectives"])       # 7 objectives
  |     |     +-- get_objective / get_mode              # objectives/registry.py
  |     |     +-- modes module (side-effect imports)    # objectives/modes.py
  |     |     +-- frequency module (side-effect)        # objectives/frequency.py
  |     |     +-- quality module (side-effect)          # objectives/quality.py
  |     |     +-- field module (side-effect)            # objectives/field.py
  |     |     +-- wakefield module (side-effect)        # objectives/wakefield.py (NOT used but imported)
  |     |     +-- antenna module (side-effect)          # objectives/antenna.py (NOT used but imported)
  |     |
  |     +-- CSTConnection(library_path, mode)           # core/connection.py
  |     |     +-- init_cst_path()                       # core/__init__.py
  |     |
  |     +-- SolverRunner(timeout_s, settle_s)           # core/solver.py
  |     |
  |     +-- _evaluate_single_pass()  [inner closure]
  |     |     |
  |     |     +-- conn.open_project(project_path)       # core/connection.py
  |     |     |     +-- CSTProject                       # core/project.py
  |     |     |
  |     |     +-- project.update_parameters(...)        # core/project.py
  |     |     +-- runner.run(project)                   # core/solver.py
  |     |     |     +-- SolverResult (dataclass)
  |     |     |
  |     |     +-- ResultReader(project.filename)         # core/results.py
  |     |     |     +-- cst.results (lazy import)
  |     |     |     +-- get_s_parameter()               # core/results.py
  |     |     |     +-- get_scalar(TREEPATH_MAX_E_Z*)   # core/results.py
  |     |     |
  |     |     +-- physics.formulas.half_power_bandwidth
  |     |     +-- physics.formulas.coupling_beta
  |     |     +-- physics.formulas.intrinsic_q0
  |     |     +-- physics.poynting.discover_field_files
  |     |     +-- physics.poynting.max_modified_poynting
  |     |     +-- physics.heating.max_h_from_field_file
  |     |     +-- physics.heating.pulsed_heating_delta_t
  |     |
  |     +-- EvaluationRetryHandler(conn, config)       # core/retry.py
  |     |     +-- RetryConfig
  |     |     +-- core/timeout.py
  |     |     +-- core/cleanup.py
  |     |
  |     +-- _build_sao(opt_cfg, param_set, ...)        # factory.py (local)
  |     |     +-- SurrogateAssistedOptimizer            # optimization/sao.py
  |     |     |     +-- BaseOptimizer                    # optimization/base.py
  |     |     |     +-- optimization/sampling.py
  |     |     |     +-- optimization/acquisition.py
  |     |
  |     +-- Returns (workflow_container, optimizer, evaluator)
  |
  +-- ckpt.get_warm_xy()                               # warm-start from checkpoint
  +-- opt.optimize(evaluator=evaluator, prior_data=...)
  |     |
  |     +-- LHS initial samples in [0,1]^D
  |     +-- denormalize -> evaluate -> penalize
  |     +-- GP fit -> acquisition max -> next point
  |     +-- Repeat n_iterations
  |
  +-- ckpt.clear()  (or preserved on Ctrl+C)
```

---

## Config keys used

Only the top-level keys and sub-keys actually read by `run_workflow_1.py` + `build_workflow_1()` are listed. Keys specific to Workflow 2 (`workflow_2:`) or Workflow 3 (`workflow_3.yaml`) are NOT included here.

```
cst:
  library_path            → CSTConnection
  connect_mode            → CSTConnection(mode=...)

solver:
  stagnation_timeout_s    → SolverRunner(timeout_s=...)
  settle_s                → SolverRunner(settle_s=...)

logging:
  output_dir              → log/workflow record path
  auto_flush_interval     → OptimizationLogger (imported but NOT instantiated in WF1 eval path)

project:
  cst_path                → path to the .cst file

evaluation:
  post_eval_recovery      → post-evaluation graceful reset (tier2 / "")

optimization:
  algorithm               → "sao" (currently the only used path)
  n_initial_samples       → SAO n_initial
  n_iterations            → SAO n_iterations
  acquisition_function    → ei / ucb / pi
  acquisition_xi          → ExpectedImprovement or ProbabilityOfImprovement
  acquisition_kappa       → UpperConfidenceBound
  seed                    → RNG seed
  retry:
    enabled               → master switch
    max_tier1             → simple retries
    max_tier2             → kill + reconnect
    max_tier3             → kill + clean result folder + reconnect
    cooldown_s            → pause between tiers

parameters:               → list of 13 geometry parameter dicts
  [i].name                → CST parameter name
  [i].display_name        → human label
  [i].unit                → "mm" (etc.)
  [i].low                 → lower bound
  [i].high                → upper bound
  [i].log_scale           → log-space flag

objectives:               → list of 7 objective dicts
  [i].name                → objective class name (resolved via registry)
  [i].mode                → penalty mode name
  [i].mode_params         → dict (e.g. {target, sigma, threshold})
  [i].obj_params          → dict (e.g. {project_dir, gc, e_target})
```

**Important**: the `tolerance:` section and `workflow_2:` section are also in `default.yaml` but are **not** read by Workflow 1.

---

## Dependency classification

### A. Direct dependencies of Workflow 1

These are modules whose code is actually **executed** during a Workflow 1 run:

| Module | Reason |
|---|---|
| `checkpoint.py` | CheckpointManager for warm-start and evaluation tracking |
| `factory.py` | build_workflow_1 entry point |
| `core/__init__.py` | init_cst_path() |
| `core/connection.py` | CSTConnection |
| `core/project.py` | CSTProject (parameter update, rebuild, close) |
| `core/solver.py` | SolverRunner, SolverResult |
| `core/results.py` | ResultReader (S11, 0D scalars) |
| `core/retry.py` | EvaluationRetryHandler (three-tier escalation) |
| `core/timeout.py` | run_with_wall_clock_timeout (called by retry handler) |
| `core/cleanup.py` | force_kill_cst, verify_process_cleanup, etc. |
| `core/errors.py` | CSTConnectionLostError, Solver* errors |
| `parameters/base.py` | ParameterSet, ParamRange |
| `parameters/geometry.py` | GeometryParameter |
| `objectives/base.py` | ObjectiveFunction ABC |
| `objectives/modes.py` | All OptimizationMode subclasses |
| `objectives/registry.py` | Global registries (read by _build_objectives) |
| `objectives/frequency.py` | ResonantFreqObjective |
| `objectives/quality.py` | Q0Objective, CouplingBetaObjective |
| `objectives/field.py` | PeakElectricField, MaxModifiedPoynting, FieldFlatness, PulsedHeating |
| `optimization/base.py` | BaseOptimizer, OptimizationResult |
| `optimization/sao.py` | SurrogateAssistedOptimizer |
| `optimization/acquisition.py` | EI / UCB / PI (used by SAO) |
| `optimization/sampling.py` | unit_cube_lhs (used by SAO) |
| `physics/formulas.py` | half_power_bandwidth, coupling_beta, intrinsic_q0 |
| `physics/poynting.py` | max_modified_poynting, discover_field_files |
| `physics/heating.py` | pulsed_heating_delta_t, max_h_from_field_file |

### B. Modules imported but NOT executed during Workflow 1

These are imported in `factory.py` via side-effect `# noqa: F401` imports or at the module level, but their code paths never fire during a WF1 run.

| Module | Why not executed |
|---|---|
| `objectives/wakefield.py` | Imported for @register_objective side-effect; WF1 objectives don't include `z_longitudinal` or `z_transverse` |
| `objectives/antenna.py` | Imported for @register_objective side-effect; WF1 objectives don't include `antenna_absorption` or `antenna_absorption_db` |
| `optimization/saea.py` | Imported at factory module top level; WF1 uses `algorithm="sao"` so SAEA path is skipped |
| `optimization/logging.py` | OptimizationLogger imported but WF1 evaluator does NOT create a logger instance |
| `optimization/adaptive_bounds.py` | AdaptiveBoundsConfig/Controller imported but `bounds_controller` is always `None` in WF1 |
| `workflows/recovery.py` | `EvaluationResult`, `EvaluationStatus` ARE used as data types in the evaluator |
| `core/orchestrator.py` | DualProjectOrchestrator is WF2-only |
| `core/messages.py` | MessageLogger is WF2-only |
| `physics/cavity.py` | Not used directly by WF1 (uses formulas.py directly). Used by WF3 recovery module |
| `physics/wakefield.py` | Wakefield impedance functions are WF2-only |
| `physics/quantities.py` | PhysicsQuantity ABC; not used by WF1 |

### C. Modules that will NOT be moved

These are cross-cutting concerns that all workflows depend on. They stay in `src/cst_optimization/` and are not candidates for extraction:

| Module | Used by |
|---|---|
| `core/__init__.py` (init_cst_path) | WF1, WF2, WF3 |
| `core/connection.py` | WF1, WF2, WF3 |
| `core/project.py` | WF1, WF2, WF3 |
| `core/solver.py` | WF1, WF2, WF3 |
| `core/results.py` | WF1, WF2, WF3 |
| `core/errors.py` | WF1, WF2, WF3 |
| `core/cleanup.py` | WF1, WF2, WF3 |
| `core/timeout.py` | WF1, WF2, WF3 (via retry handler) |
| `parameters/base.py` | WF1, WF2, WF3 |
| `parameters/geometry.py` | WF1, WF2, WF3 |
| `objectives/base.py` | WF1, WF2, WF3 |
| `objectives/registry.py` | WF1, WF2, WF3 |
| `objectives/modes.py` | WF1, WF2, WF3 |
| `optimization/base.py` | WF1, WF2, WF3 |
| `optimization/sao.py` | WF1, WF2, WF3 |
| `optimization/acquisition.py` | WF1, WF2, WF3 (via SAO) |
| `optimization/sampling.py` | WF1, WF2, WF3 (via SAO) |

---

## Risks

### Shared-module pollution risks

1. **`objectives/registry.py`** 鈥?Global dicts. WF1 factory imports ALL objective modules via `# noqa: F401` side-effect imports. Splitting WF1 to a separate package would require either (a) a selective import that only registers WF1 objectives, or (b) keeping the registries in a shared core package.

2. **`factory.py`** 鈥?The main "God object" factory. `build_workflow_1()`, `build_workflow_2()`, and `build_workflow_3()` all live in the same file. Any change to the shared builder helpers (`_build_parameters`, `_build_objectives`, `_build_sao`) affects all three workflows. The `_evaluate_single_pass()` closure is embedded inside `build_workflow_1()` and cannot be tested independently.

3. **`checkpoint.py`** 鈥?`EvalRecord` has polymorphic fields (`phases_done`, `f2f_params_hash`) that are specific to WF2 partial-phase tracking. The `get_warm_xy()` and `mark_phase_done()` methods serve both WF1 (simple pending/completed/failed) and WF2 (multi-phase atomize). Any schema change to `EvalRecord` affects both workflows.

4. **`core/retry.py`** 鈥?`EvaluationRetryHandler.execute()` has timeout logic and connection-factory branching that is shared across WF1 and WF3. The `force_reset()` method with `tier2`/`tier3` post-eval recovery is used by WF1 (tier2) and WF3 (tier3).

5. **`physics/formulas.py`** 鈥?Used directly by WF1's `_evaluate_single_pass()` AND by WF3's `RecoveryWorkflowEvaluator._calibration_solve()`. Also used by objective classes via `physics/cavity.py`. Any API change propagates to all three workflows.

### Files that must NOT be moved or deleted

Purely WF1-specific files that would break WF1 if removed but do NOT affect WF2/WF3:

- `run_workflow_1.py` (obvious; the entry point)

Files that affect ALL workflows if moved (must stay):

- Entire `src/cst_optimization/core/` directory (connection, project, solver, results, retry, errors, cleanup, timeout)
- `src/cst_optimization/parameters/`
- `src/cst_optimization/objectives/base.py`, `registry.py`, `modes.py`
- `src/cst_optimization/optimization/base.py`, `sao.py`, `acquisition.py`, `sampling.py`
- `src/cst_optimization/physics/formulas.py` (shared by WF1 and WF3)
- `src/cst_optimization/physics/poynting.py` (shared by WF1 and WF3)
- `src/cst_optimization/physics/heating.py` (shared by WF1 and WF3)
- `src/cst_optimization/checkpoint.py` (shared by WF1 and WF2)
- `src/cst_optimization/factory.py` (shared builder code)

Config files that must NOT be deleted:
- `config/default.yaml` (WF1 reads the root keys)

---

## Tests / commands run

```bash
python -m compileall src run_workflow_1.py
```

This command was run after the inventory was compiled to verify syntactic correctness of all inspected files. No bytecode compilation errors were expected since no code was modified.

```bash
git add reports/workflow1_split/phase_01_inventory.md
git commit -m "refactor(workflow1): inventory dependencies"
```

---

## Recommended next phase

Based on this inventory, the recommended first extraction steps are:

1. **Extract WF1-specific objectives** into a dedicated module set (e.g. `wf1_objectives/`) that only registers the 6 objectives used by WF1 (resonant_freq, coupling_beta, q0, peak_e_field, field_flatness, max_modified_poynting, pulsed_heating). This breaks the side-effect import chain that currently loads WF2 objectives into the global registry during WF1 runs.

2. **Extract the `_evaluate_single_pass()` closure** from `factory.py::build_workflow_1()` into a standalone evaluator class (e.g. `wf1_evaluator.py`). The evaluator should accept a `CSTConnection`, `SolverRunner`, and `ParameterSet` via constructor injection, making it independently testable.

3. **Separate WF1 config schema** into its own `config/workflow_1.yaml` (or extract the WF1-relevant keys into a validated pydantic model). The shared `default.yaml` would remain, but WF1 would only pull the config tree it actually uses.

4. **Move `run_workflow_1.py`** into an `entrypoints/` or `workflows/` directory as a thin CLI script that instantiates the extracted evaluator and optimizer.

5. **Clean up factory.py** by removing unused imports (`wakefield`, `antenna`, `saea`, `logging`, `adaptive_bounds`) from the `build_workflow_1()` code path. These would remain only in the `build_workflow_2()` and `build_workflow_3()` paths.

The guiding principle: **never duplicate shared core types**. `core/`, `parameters/`, and `optimization/` (except WF2-specific algorithms) should remain shared. The extraction boundary is at the application-logic layer 鈥?evaluator closures, objective registrations, and config schemas.
