# Phase A1 -- Legacy Workflow 3 Inventory

## Summary

Legacy Workflow 3 is a **two-pass frequency-domain recovery optimisation**
workflow for the same X-band RF gun cavity used by Workflow 1.  It
calibrates the solver frequency, rejects off-resonance candidates early,
and supports staged refinement, adaptive bounds, and per-objective
weights.  It shares most core infrastructure with WF1 but adds a
significant evaluation logic layer (``RecoveryWorkflowEvaluator``) and
a multi-stage runner.

## Files inspected

| File | Role |
|---|---|
| ``run_workflow_3.py`` | Entry point with staged search logic |
| ``config/workflow_3.yaml`` | WF3-specific config schema |
| ``src/cst_optimization/factory.py`` | ``build_workflow_3()`` builder |
| ``src/cst_optimization/workflows/recovery.py`` | ``RecoveryWorkflowEvaluator``, ``FrequencyGate``, ``MetricSpec`` |
| ``src/cst_optimization/core/orchestrator.py`` | ``DualProjectOrchestrator`` (WF2 only; not used by WF3) |
| ``src/cst_optimization/core/retry.py`` | ``EvaluationRetryHandler`` (shared by WF1 and WF3) |
| ``src/cst_optimization/checkpoint.py`` | ``CheckpointManager`` (shared) |
| ``src/cst_optimization/optimization/resume.py`` | ``load_prior_data_from_jsonl`` (used by WF3 -- resume) |
| ``src/cst_optimization/optimization/adaptive_bounds.py`` | Adaptive bounds controller (used by WF3, available to WF1) |
| ``src/cst_optimization/optimization/base.py`` | ``BaseOptimizer``, ``OptimizationResult`` |
| ``src/cst_optimization/optimization/sao.py`` | ``SurrogateAssistedOptimizer`` |
| ``src/cst_optimization/optimization/acquisition.py`` | EI / UCB / PI |
| ``src/cst_optimization/objectives/field.py`` | ``MaxModifiedPoynting``, ``FieldFlatness``, ``PulsedHeating`` |
| ``src/cst_optimization/objectives/frequency.py`` | ``ResonantFreqObjective`` |
| ``src/cst_optimization/objectives/quality.py`` | ``Q0Objective``, ``CouplingBetaObjective``, ``InputPowerObjective`` |
| ``src/cst_optimization/objectives/antenna.py`` | ``TransmissionAtResonance`` (``s21_at_f0_db`` objective) |
| ``src/cst_optimization/objectives/registry.py`` | Global objective/mode registries |
| ``reports/workflow1_split/phase_09_finalisation.md`` | WF1 validated state |
| ``workflows/rfgun_single_pass/README.md`` | WF1 package documentation |
| ``workflows/rfgun_single_pass/workflow.py`` | WF1 local builder |
| ``workflows/rfgun_single_pass/evaluator.py`` | WF1 ``Workflow1Evaluator`` |

## Legacy Workflow 3 call graph

```
run_workflow_3.py::main()
  +-- yaml.safe_load(config/workflow_3.yaml)
  +-- _setup_runtime_logging(cfg)
  +-- if --resume-from:
  |     _make_stage_config(cfg, stage_index=0)  # no bound shrinking
  |     _run_single_stage("Resume", resume_jsonl_path=...)
  +-- else:
  |     _make_stage_config(cfg, stage_index=0)   # Stage 1
  |     result = _run_single_stage("Stage 1")
  |     if staged_search.enabled:
  |       _make_stage_config(cfg, stage_index=1, best_x=result.x_opt)
  |       _run_single_stage("Stage 2")            # bounds shrunk
  `-- print result

_run_single_stage(stage_name, resume_jsonl_path):
  +-- CheckpointManager(f"output_dir/{stage_name}").load()
  +-- if checkpoint has prior data: ckpt.get_warm_xy() -> prior_data
  +-- build_workflow_3(cfg, resume_jsonl, checkpoint_callback)
  |     -> factory.py::build_workflow_3()
  |       +-- _build_parameters()           (same helper as WF1)
  |       +-- _build_workflow_3_metrics()   (MetricSpec list)
  |       +-- CSTConnection + connect()
  |       +-- SolverRunner
  |       +-- FrequencyGate, MetricSpec list
  |       +-- RecoveryWorkflowEvaluator     (recovery.py)
  |       +-- EvaluationRetryHandler         (if enabled)
  |       +-- _build_sao() / SurrogateAssistedEA
  |       +-- Evaluator closure (scalar or multi-obj)
  |       +-- Prior data loading via resume.py
  |       +-- Adaptive bounds controller
  |       +-> return (workflow, optimizer, evaluator)
  +-- opt.optimize(evaluator=evaluator, bounds_controller=...)
  |     +-- LHS initial samples
  |     +-- evaluator(x_phys):
  |         (if retry enabled)
  |           retry_handler.execute(workflow.evaluate, x_phys, iteration)
  |         (else)
  |           workflow.evaluate(x_phys, iteration).scalar_evaluator(...)
  |     +-- RecoveryWorkflowEvaluator.evaluate(x_phys, iteration)
  |         +-- open project
  |         +-- update_parameters + rebuild
  |         +-- **Pass 1: calibration solve at guessed f_data**
  |         |   +-- solver.run(project)
  |         |   +-- S11 depth gate check
  |         |   +-- half_power_bandwidth(target_freq=guess)
  |         |   +-- multi-dip mode ambiguity detection
  |         |   +-- frequency gate: reject if |f0 - target| > 20 MHz
  |         |   +-- project.close()
  |         +-- (optional) inter_pass_recovery: kill DE + reconnect
  |         +-- **Pass 2: measurement solve at corrected f_data**
  |         |   +-- open project (or new DE after inter_pass_recovery)
  |         |   +-- update_parameters with f_data = f0 from Pass 1
  |         |   +-- solver.run(project)
  |         |   +-- ResultReader: S11, 0D scalars (MaxE_Z0/1/2)
  |         |   +-- CouplingBeta, InputPower, PeakSurfaceField, IntrinsicQ
  |         |   +-- LoadedQ, MinS11, field_flatness
  |         |   +-- discover_field_files -> max_modified_poynting, pulsed_heating
  |         |   +-- evaluate_configured_metrics (obj_params)
  |         |   +-- penalty computation via threshold_penalty + mode.compute
  |         +-- return EvaluationResult
  |     +-- GP fit + acquisition max -> next point
  |     +-- Repeat n_iterations
  +-- return OptimizationResult
```

## Legacy Workflow 3 config schema

``config/workflow_3.yaml`` has these top-level sections:

| Section | Key sub-keys | Purpose |
|---|---|---|
| ``cst`` | ``library_path``, ``connect_mode`` | CST connection |
| ``solver`` | ``stagnation_timeout_s``, ``settle_s``, ``evaluation_timeout_s`` | Solver config (extra timeout vs WF1) |
| ``logging`` | ``enabled``, ``output_dir``, ``auto_flush_interval`` | Logging to ``D:/Results/workflow3`` |
| ``project`` | ``cst_path`` | Different project from WF1 |
| ``evaluation`` | ``two_pass``, ``calibration_guess_ghz``, ``post_eval_recovery``, ``inter_pass_recovery``, ``s11_depth_threshold_db``, ``mode_spacing_ghz``, ``frequency_gate.*`` | Two-pass evaluation tuning |
| ``resume`` | ``enabled``, ``jsonl_path``, ``n_initial_extra``, ``tighten_bounds`` | Resume from prior run |
| ``optimization`` | ``algorithm``, ``n_initial``, ``n_iterations``, ``seed``, ``acquisition_function``, ``objective_weights`` (named dict), ``staged_search.*``, ``adaptive_bounds.*``, ``retry.*`` | SAO optimizer + staged search + adaptive bounds |
| ``parameters`` | 13 entries with ``name``, ``nominal``, ``delta``, ``min_step`` | Parameters at nominal + tolerance range |
| ``objectives`` | 11 entries with ``name``, ``role`` (optimize/threshold/report_only), ``priority``, ``mode``, ``mode_params``, ``obj_params`` | Multi-role objectives |

**Key differences from WF1 ``config.yaml``:**
- Uses ``n_initial`` (not ``n_initial_samples``)
- Has ``objective_weights`` as a named dict (WF1 doesn't)
- Has ``staged_search`` (WF1 doesn't)
- Has ``adaptive_bounds`` (WF1 doesn't)
- Has ``evaluation.two_pass``, ``frequency_gate``, ``inter_pass_recovery``
- Has ``resume`` section
- Parameters use ``nominal`` + ``delta`` (WF1 uses ``low`` + ``high``)
- 11 objectives instead of 7 (adds ``s21_at_f0_db``, ``e_peak``, ``s11_db``, ``q_loaded``)
- ``p_input`` replaces WF1's inline calculation
- Objectives have ``role``, ``priority``, ``report_as`` (WF1 doesn't)

## Execution model

| Feature | Legacy WF3 | New WF1 (validated) |
|---|---|---|
| Passes per eval | **2** (calibration + measurement) | **1** (fixed ``f_data``) |
| Solver runs per eval | **2** (only if frequency gate passes) | **1** |
| Frequency calibration | **Yes** -- ``half_power_bandwidth(target_freq=guess)`` | No (hardcoded ``target_freq=11.424``) |
| Frequency gate | **Yes** -- reject if ``|f0 - target| > 20 MHz`` | No |
| S11 depth gate | **Yes** -- reject shallow dips (``> -1 dB``) | No |
| Multi-dip detection | **Yes** -- ``scipy.signal.find_peaks`` | No |
| Post-eval recovery | ``tier3`` (force reset) | ``tier2`` (graceful reset) |
| Inter-pass recovery | **Yes** -- kill DE between calibration/measurement | N/A (single pass) |
| Staged search | **Yes** -- Stage 1 coarse → Stage 2 shrink+refine | No |
| Adaptive bounds | **Yes** -- Phase 1 LHS shrink + Phase 2 expand | No |
| Resume from JSONL | **Yes** -- ``load_prior_data_from_jsonl`` | No |
| Objective weights | **Yes** -- named dict ``resonant_freq: 5.0, ...`` | Equal weights only |
| Metric roles | **Yes** -- optimize / threshold / report_only | All metrics implicitly optimize |
| Parameters | ``nominal`` + ``delta`` + ``min_step`` | ``low`` + ``high`` |
| Project path | ``D:/ModelData/XBandGun_Workflow3.cst`` | ``F:/workflow_elgun/PickupDesign_2026.cst`` |
| SAO algorithm | Same ``SurrogateAssistedOptimizer`` | Same |
| Retry handler | Same ``EvaluationRetryHandler`` (3 tiers) | Same |
| Checkpoint | Same ``CheckpointManager`` | Same |
| Physics computed | Same 7 metrics + ``p_input``, ``s21_at_f0_db`` | 7 metrics (inline) |
| Field export caching | **Yes** -- copies to ``Results/fields/iter_NNNN/`` | No |
| Live validation | Not validated in this branch | **PASS** (Phase 8.8) |

## Compared with validated new Workflow 1

| Aspect | New WF1 (validated, ``workflows/rfgun_single_pass/``) | Legacy WF3 (``cst_optimization``) |
|---|---|---|
| **Runner** | ``run_workflow_1.py`` shim -> ``run.py`` | ``run_workflow_3.py`` (monolithic) |
| **Config** | ``config.yaml`` (8 sections) | ``workflow_3.yaml`` (separate file) |
| **Builder** | ``workflow.py::build_workflow_1()`` (local, no factory) | ``factory.py::build_workflow_3()`` (monolithic) |
| **Evaluator** | ``Workflow1Evaluator`` (self-contained) | ``RecoveryWorkflowEvaluator`` (recovery.py) |
| **Evaluator pattern** | Inline ``evaluate_single_pass()`` | Formal class with ``_calibration_solve`` + ``_measurement_solve`` |
| **Optimizer** | SAO only | SAO or SAEA |
| **Objectives** | 7 (from WF1-only modules) | 11 (from full registry, includes antenna) |
| **Recovery** | Post-eval ``tier2`` graceful reset | Post-eval ``tier3`` + inter-pass recovery |
| **Retry** | 3-tier ``EvaluationRetryHandler`` | Same handler (identical code) |
| **Checkpoint** | ``CheckpointManager`` with ``ckpt.load()`` | Same manager with stage-suffixed paths |
| **Result reading** | Inline in ``evaluate_single_pass()`` | Via ``PhysicsQuantity`` classes (``cavity.py``) |
| **Physics metrics** | ``formulas.py`` directly | ``cavity.py`` (wraps ``formulas.py``) |
| **Live validation** | **PASS** (Phase 8.8) | Not performed on this branch |

## WF3-only useful capabilities

These are features of legacy WF3 that would benefit the new validated
WF1 if merged selectively:

1. **Two-pass solve (calibration + measurement)** -- When ``f_data``
   is not known precisely, calibrating first avoids off-resonance
   S-parameter readings.  Critical for multi-cell cavities where
   the resonant frequency shifts with geometry.

2. **Frequency gate** -- Early rejection of candidates whose resonant
   frequency drifts >20 MHz from target.  Saves solver time on
   obviously invalid candidates.

3. **S11 depth gate** -- Rejects candidates with shallow S11 dips
   (poor coupling).  Catches mesh/geometry problems early.

4. **Objective weights** -- Named per-objective weights in config
   (``resonant_freq: 5.0``).  Allows fine-grained scalarisation
   without hardcoding in the evaluator.

5. **Adaptive bounds controller** -- Two-phase strategy:
   - Phase 1: LHS coarse scan with bounds shrinking toward best point
   - Phase 2: Post-SAO boundary proximity expansion
   This is already in ``src/cst_optimization/`` and could be enabled
   in the new WF1 builder with minimal config additions.

6. **Staged search** -- Stage 1 coarse SAO followed by Stage-2
   local refinement with shrunk bounds around the best point.
   Useful when the design space is large and the optimum is local.

7. **Resume from JSONL** -- ``load_prior_data_from_jsonl()`` lets
   the user load all prior evaluations from a previous run's
   ``evaluation_records.jsonl`` file into the GP surrogate.
   Useful for continuing interrupted optimisations.

8. **Multi-dip mode ambiguity detection** -- Uses
   ``scipy.signal.find_peaks`` to detect multiple S11 dips near the
   target frequency and logs warnings.  Diagnostic-only but valuable.

9. **Field export caching** -- ``_cache_field_exports()`` copies
   field monitor exports to ``Results/fields/iter_NNNN/``.  Helps
   preserve field data across CST result-folder resets.

10. **Metric role system** -- ``optimize`` / ``threshold`` /
    ``report_only`` roles separate concerns.  ``threshold`` metrics
    have soft engineering limits; ``report_only`` metrics are logged
    but not optimised.

## WF3-specific or obsolete logic

These should NOT be merged into the new WF1 SAO workflow:

1. **``RecoveryWorkflowEvaluator`` class** -- Too tightly coupled to
   ``factory.py::build_workflow_3()``.  Extracting just the
   calibration/measurement logic would be more effort than adapting
   ``Workflow1Evaluator`` to support two-pass mode.

2. **``MetricSpec`` dataclass** -- Legacy WF3's metric configuration
   model with roles/priorities/thresholds.  Overly complex for WF1's
   7 metrics.  The ``role`` system adds indirection without much
   benefit when all metrics share the same optimisation path.

3. **Staged search in ``run_workflow_3.py``** -- The two-stage runner
   logic (coarse SAO → shrink → refine) is specific to WF3's
   tolerance-analysis background.  If needed, it should be built as
   a generic ``run_stage()`` utility rather than tied to the evaluator.

4. **``PhysicsQuantity`` classes (``cavity.py``)** -- WF1 already uses
   ``formulas.py`` directly, which is simpler.  The ``PhysicsQuantity``
   abstraction (``compute(bundle)``) adds an extra layer of indirection
   that makes the code harder to follow.

5. **``ResultBundle`` intermediate object** -- Used by
   ``PhysicsQuantity.compute(bundle)`` to pass results.  WF1 reads
   results inline in the evaluator, which is more transparent.

6. **``s21_at_f0_db`` objective** -- Uses a transmission S-parameter
   that requires a second port.  This is WF3-specific (the WF3 project
   has a different geometry with an output port).  Not applicable to
   the WF1 single-port cavity.

7. **``_parameter_bounds`` + ``_make_stage_config`` in runner** -- These
   are runner-level helper functions that manipulate parameter bounds
   between stages.  They should remain in the entry-point script.

8. **SAEA algorithm path** -- ``SurrogateAssistedEA`` is imported but
   rarely used.  WF1 uses only SAO.  The SAEA path adds code
   complexity without demonstrated benefit.

## Suggested target shape

The new consolidated SAO workflow should live under
``workflows/rfgun_sao/`` with this structure:

```
workflows/rfgun_sao/
  __init__.py          # package marker
  run.py               # CLI entry point (builds on run_workflow_1.py)
  config.yaml          # consolidated config schema
  workflow.py          # builder: build_workflow_sao()
  evaluator.py         # Workflow1Evaluator (extended for optional two-pass)
  recovery.py          # optional: calibration / measurement helpers
                       # (only if two-pass is added)
```

The existing ``workflows/rfgun_single_pass/`` can remain as a
reference or be deprecated after the consolidation is validated.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Merging WF3 two-pass logic into WF1 single-pass changes behaviour that was validated in Phase 8.8 | **High** | Make two-pass optional (config toggle). Default = single-pass (identical to validated WF1). |
| ``build_workflow_3()`` is deeply coupled to ``RecoveryWorkflowEvaluator`` and ``factory.py`` | **High** | Do NOT import ``factory.py`` in the new workflow.  Copy and adapt the WF3 logic into the new package following the WF1 extraction pattern. |
| ``objective_weights`` as named dict requires parsing logic | Low | Already implemented in ``_resolve_named_weights()`` -- ready to copy. |
| ``staged_search`` runner logic is complex and difficult to test | Medium | Keep in ``run.py`` as optional CLI mode; unit-test the stage config helpers separately. |
| ``adaptive_bounds`` adds a complex loop inside SAO ``optimize()`` | Medium | Enable only when explicitly configured; test with no-CST smoke tests. |

## Recommended next phase

**Phase A2: Consolidation plan.**  Create a detailed implementation
plan for building ``workflows/rfgun_sao/`` that:

1. Copies the validated ``workflows/rfgun_single_pass/`` as the base.
2. Selectively merges WF3 capabilities (two-pass, frequency gate,
   objective weights, adaptive bounds) as **optional, opt-in features**
   with the WF1 single-pass behaviour unchanged by default.
3. Preserves the validated WF1 no-CST test suite (12 tests) and adds
   new tests for the opt-in features.
4. Produces a side-by-side comparison of the consolidated workflow
   vs the original validated WF1 before committing.
5. Does NOT touch ``src/cst_optimization/``.
