# Phase A2 -- RF Gun SAO Consolidation Plan

## Summary

Consolidate the validated `workflows/rfgun_single_pass` (new WF1,
single-pass, verified end-to-end in Phase 8.8) with select capabilities
from legacy Workflow 3 into a new package `workflows/rfgun_sao/`.
The consolidated workflow preserves single-pass as the default behaviour
and adds opt-in features (two-pass calibration, frequency gate, objective
weights, adaptive bounds, metric roles) in a phased, testable manner.

## Confirmed naming

- **Target package name:** `workflows/rfgun_sao/`
- This name is user-decided and fixed for all subsequent phases.
- Do not create alternative names unless the user explicitly changes
  this decision.
- The existing `workflows/rfgun_single_pass/` remains as a validated
  reference and is not deleted.

## Target architecture

`workflows/rfgun_sao/` directory structure (final desired shape,
built incrementally across A3-A10):

`
workflows/rfgun_sao/
  __init__.py          # package marker
  README.md            # purpose, status, run instructions
  BRANCH_CONTEXT.md    # branch rules, feature adoption status
  config.yaml          # default config (single-pass mode)
  config.two_pass.yaml # example config with two-pass enabled (optional)
  run.py               # CLI entry point (builds on rfgun_single_pass/run.py)
  workflow.py          # builder: build_workflow_sao()
  evaluator.py         # Workflow1Evaluator (extended for two-pass)
  calibration.py       # calibration + measurement helpers (two-pass)
  gates.py             # frequency gate, S11 depth gate, multi-dip detection
  metrics.py           # MetricConfig handling, objective_weights resolution
  recovery.py          # post-eval recovery (future: inter-pass recovery)
`

**Initial creation (A3):** Copy `workflows/rfgun_single_pass/`
verbatim to `workflows/rfgun_sao/`, update package docs, add
import tests.

**Key file responsibilities:**
- `run.py` -- CLI runner (same as validated WF1, optionally extended)
- `workflow.py` -- `build_workflow_sao()` with opt-in features
- `evaluator.py` -- `Workflow1Evaluator` base class, extended for
  two-pass via subclass or mode flag
- `calibration.py` -- two-pass calibration/measurement logic
  (extracted and adapted from `RecoveryWorkflowEvaluator`)
- `gates.py` -- `FrequencyGate`, `S11DepthGate`, `MultiDipDetector`
  (extracted from `RecoveryWorkflowEvaluator`)
- `metrics.py` -- lightweight `MetricConfig` dataclass,
  `_resolve_named_weights()`, metric role aggregation

**Package invariant:** `workflows/rfgun_sao/` must never import
`cst_optimization.factory`, `cst_optimization.workflows.recovery`,
or any other WF3-specific module.  It reuses `core/`, `parameters/`,
`objectives/`, `optimization/`, `physics/`, and `checkpoint/`
the same way `rfgun_single_pass` does.

## Default behaviour policy

1. **Default mode is validated single-pass.**  The command
   `python run_workflow_1.py --n-initial 1 --n-iter 0` (Phase 8.8
   validation command) must remain reproducible with identical results
   throughout all A-series phases when no opt-in features are enabled.
2. **Two-pass, gates, adaptive bounds, metric roles are opt-in.**
   They must be explicitly enabled via config or CLI flags.  No phase
   may silently change the default evaluation behaviour.
3. **No factory import.**  The new `workflow.py::build_workflow_sao()`
   must not import `cst_optimization.factory`.  Shared helpers
   (`_build_parameters`, `_build_sao`) are copied and maintained
   locally, matching the validated WF1 pattern.
4. **Existing WF1 tests continue to pass.**  The 12 no-CST tests in
   `tests/workflows/test_rfgun_single_pass_imports.py` must remain
   passing.  New tests for `workflows/rfgun_sao/` are a separate
   test file.

## Feature adoption matrix

| Feature | Source | Adopt? | Priority | Default? | Target file(s) | Notes |
|---|---|---|---|---|---|---|
| two-pass calibration + measurement | WF3 | **Yes** | Medium | Off (opt-in) | `calibration.py`, `evaluator.py`, `config.yaml` (`mode`) | Essential for multi-cell cavities but overkill for default single-pass |
| frequency gate | WF3 | **Yes** | Medium | Off (opt-in) | `gates.py` | Reject candidates >20 MHz off-resonance; combined with two-pass |
| S11 depth gate | WF3 | **Yes** | Medium | Off (opt-in) | `gates.py` | Combined with two-pass |
| multi-dip detection | WF3 | **Yes** (diagnostic) | Low | Off (info-only) | `gates.py` | Log warnings only, never hard-fail |
| objective_weights | WF3 | **Yes** | **High** | Off (equal weights default) | `metrics.py`, `workflow.py`, `config.yaml` | Named dict `resonant_freq: 5.0`; compatible with current objective list |
| metric roles (optimize/threshold/report_only) | WF3 | **Yes** (simplified) | Medium | Off (all optimize default) | `metrics.py` | New lighter schema, not legacy `MetricSpec` |
| report_as alias | WF3 | **Yes** | Low | Off | `metrics.py` | Map internal name to display name |
| threshold / sigma / direction | WF3 | **Yes** | Medium | Off | `gates.py`, `metrics.py` | Soft penalty for threshold violations |
| adaptive bounds | WF3 | **Yes** | Low | Off | `workflow.py`, `config.yaml` | Already in `src/cst_optimization/`; enable in later phase |
| staged search | WF3 | **Yes** | Low | Off | `run.py`, `workflow.py` | Runner-level; copy and adapt `_make_stage_config` |
| resume from JSONL | WF3 | **Yes** | Low | Off | `workflow.py`, `run.py` | Use `load_prior_data_from_jsonl` from shared module |
| field export caching | WF3 | **Maybe** | Low | Off | `evaluator.py` | Only if two-pass enabled and result resets occur |
| SAEA algorithm path | WF3 | **No** | N/A | N/A | N/A | Adds complexity without demonstrated benefit |
| s21_at_f0_db objective | WF3 | **No** | N/A | N/A | N/A | Requires 2-port project; WF1 project is single-port |

## Metric role / MetricSpec decision

### What legacy MetricSpec did

`src/cst_optimization/workflows/recovery.py` defines:

`python
@dataclass
class MetricSpec:
    name: str           # e.g. "resonant_freq"
    role: str           # "optimize" | "threshold" | "report_only"
    priority: int = 1
    enabled: bool = True
    report_as: str | None = None  # alias for output
    objective: ObjectiveFunction | None = None  # None for report_only
    threshold: float | None = None
    sigma: float | None = None
    direction: str = "less_than"
    obj_params: dict | None = None
`

It is deeply coupled to `RecoveryWorkflowEvaluator` and
`factory.py::build_workflow_3()`.

### Why not copy MetricSpec directly

1. **Tight coupling** -- MetricSpec requires `ObjectiveFunction`
   instances and is built during `_build_workflow_3_metrics()` which
   accesses the global objective registry and mode registry.  This is
   WF3-specific plumbing.
2. **Overcomplexity for initial consolidation** -- The validated WF1
   works correctly with a simple objective list.  Adding full
   `MetricSpec` support before the two-pass skeleton is stable
   would introduce unnecessary risk.
3. **`priority` and `enabled` are already handled** -- The current
   objective list ignores disabled entries (`entry.get("enabled", True)`).
   Adding another `priority` filter is a minor enhancement, not a
   core requirement.

### What the consolidated rfgun_sao should adopt

The **concepts** are valuable and should be preserved in a lighter form:

- `role` -- `optimize` (enters SAO scalarisation), `threshold`
  (soft engineering limit, adds penalty), `report_only` (logged but
  not penalised)
- `report_as` -- alias for output logs and objective names
- `weight` -- per-objective scalarisation weight (replaces
  `objective_weights` dict)
- `threshold`, `sigma`, `direction` -- parameters for
  `threshold` role (soft penalty computation)
- `obj_params` -- passed to objective constructor (already supported)

### Proposed lightweight MetricConfig

`python
@dataclass
class MetricConfig:
    name: str                    # required, matches registry
    mode: str = "minimize"       # default mode name
    role: str = "optimize"       # optimize / threshold / report_only
    weight: float = 1.0          # scalarisation weight
    enabled: bool = True
    report_as: str | None = None # output alias
    # Threshold role parameters (only used when role="threshold"):
    threshold: float | None = None
    sigma: float | None = None
    direction: str = "less_than"
    # Mode params and objective params (as in current config):
    mode_params: dict | None = None
    obj_params: dict | None = None
`

The config YAML would look like:

`yaml
objectives:
  - name: resonant_freq
    role: optimize
    weight: 5.0
    mode: tolerance
    mode_params:
      target: 11.424
      sigma: 0.00333

  - name: max_modified_poynting
    role: threshold
    weight: 1.0
    threshold: 5.0e12
    sigma: 1.0e12
    direction: less_than
    obj_params:
      gc: 0.125
      e_target: 200000000.0

  - name: q_loaded
    role: report_only
    report_as: q_loaded
`

**Important:** This is a design proposal for A2 only.  Implementation
should not begin until A7/A8, after objective_weights and two-pass are
stable.

## Config schema proposal

### Sections and key structure

`
cst:
  library_path, connect_mode
solver:
  stagnation_timeout_s, settle_s
logging:
  output_dir
project:
  cst_path
evaluation:
  mode: single_pass | two_pass        # default: single_pass (backward-compatible)
  target_freq_ghz: 11.424            # configurable target, was hardcoded
  calibration_guess_ghz: 11.424      # used in two-pass mode
  post_eval_recovery: tier2           # default from validated WF1
  inter_pass_recovery: false          # only in two-pass
  frequency_gate:                     # opt-in
    enabled: false
    target_ghz: 11.424
    max_abs_offset_mhz: 20.0
  s11_depth_gate:                     # opt-in
    enabled: false
    threshold_db: -1.0
  multi_dip_detection:                # diagnostic only
    enabled: false
    mode_spacing_ghz: 0.04
optimization:
  algorithm: sao
  n_initial_samples: 20
  n_iterations: 100
  acquisition_function: ei
  acquisition_xi: 0.01
  acquisition_kappa: 2.0
  seed: 42
  objective_weights:                  # named dict, opt-in
    resonant_freq: 1.0
  retry:                              # (same as validated WF1)
  adaptive_bounds:                    # opt-in, later phase
    enabled: false
  staged_search:                      # opt-in, later phase
    enabled: false
  resume:                             # opt-in, later phase
    enabled: false
parameters:                           # low/high format (default)
objectives:                           # mode/mode_params/obj_params + optional role/weight
`

### Schema migration rules

1. **A3-A4 (initial creation):** Schema is identical to validated WF1
   `config.yaml`.  No new keys.  No semantic changes.
2. **A5 (objective_weights):** Add `optimization.objective_weights`
   as an optional dict.  Default equal weights.  No schema changes to
   `objectives` list.
3. **A6-A7 (two-pass + gates):** Add `evaluation.mode`,
   `evaluation.frequency_gate`, `evaluation.s11_depth_gate`.
   All default to off/single_pass.  No silent behaviour change.
4. **A8+ (metric roles):** Add optional `role`, `weight` fields to
   objective entries.  When absent, default values (`optimize`, 1.0)
   apply.

## Migration strategy

### A3: Create rfgun_sao package from validated rfgun_single_pass

- `mkdir workflows/rfgun_sao`
- Copy every file from `workflows/rfgun_single_pass/` to
  `workflows/rfgun_sao/`
- Update package docstrings: "Consolidated SAO workflow, experimental"
- Update `README.md`: status = "Copied from validated single-pass;
  consolidation in progress"
- Add `tests/workflows/test_rfgun_sao_imports.py` with same 12 tests
  as `test_rfgun_single_pass_imports.py` but targeting `rfgun_sao`
- Do NOT change `run_workflow_1.py` shim
- Do NOT change `rfgun_single_pass/` files
- **Verification:** compileall, 12 WF1 tests, 12 new SAO tests all pass

### A4: Make rfgun_sao runnable behind explicit command

- Add a runner command: `python -m workflows.rfgun_sao.run --help`
- Verify CLI parity with `rfgun_single_pass/run.py`
- Do NOT repoint `run_workflow_1.py`
- **Verification:** `--help` output matches, compileall passes

### A5: Add objective_weights support

- Add `_resolve_named_weights()` to `workflows/rfgun_sao/workflow.py`
  (copy from validated WF1; already present but unused by default)
- Add `objective_weights` to `config.yaml` as optional dict
- Keep default equal weights unchanged
- Add no-CST tests for weight resolution
- **Verification:** no-CST tests pass, default behaviour unchanged

### A6: Add optional two-pass skeleton

- Add `evaluation.mode: single_pass` to `config.yaml` (default)
- Create `calibration.py` with `CalibrationSolver` and
  `MeasurementSolver` classes (adapted from WF3's
  `RecoveryWorkflowEvaluator` methods)
- Add `build_workflow_sao()` mode branch: if `mode == "two_pass"`,
  use two-pass evaluator; else use single-pass (validated path)
- **No gates yet** -- just the dual-solve structure
- **Verification:** default single-pass produces identical output to
  validated WF1; two-pass requires explicit enable

### A7: Add frequency gate and S11 depth gate

- Create `gates.py` with `FrequencyGate`, `S11DepthGate`,
  `MultiDipDetector`
- All default-disabled in config
- All diagnostic-only: they log but never hard-fail by default
- **Verification:** gates work when enabled, no effect when disabled

### A8: Add no-CST tests for two-pass and gates

- Test config parsing for `mode`, `frequency_gate`, `s11_depth_gate`
- Test gate accept/reject logic with synthetic S11 data
- Test default `single_pass` mode still imports without factory
- **Verification:** all new tests pass, 12 original WF1 tests still pass

### A9: Live single-pass regression

- Run `python -m workflows.rfgun_sao.run --n-initial 1 --n-iter 0`
- Must produce `Done. Best X:`, `Best F:`, log path
- Compare output with Phase 8.8 validation command and verify same
  metrics within solver noise tolerance
- **Verification:** live single-pass PASS

### A10: Live two-pass smoke

- Enable `evaluation.mode: two_pass` in config
- Run one evaluation with `--n-initial 1 --n-iter 0`
- Verify calibration pass executes before measurement pass
- Verify `f_data` is corrected
- Verify all metrics produced
- **Verification:** live two-pass PASS (or diagnostic report)

### Later phases (after A10)

- Adaptive bounds (copy from `src/cst_optimization/optimization/adaptive_bounds.py`)
- Staged search (adapt from `run_workflow_3.py` helpers)
- Resume JSONL (use `load_prior_data_from_jsonl` from shared module)
- Field export caching
- Metric roles (adopt `MetricConfig` from this plan)
- Tolerance extraction into separate workflow

## Backward compatibility

1. `workflows/rfgun_single_pass/` remains as a validated reference
   throughout all A-series phases.  It is never modified or deleted.
2. `workflows/rfgun_sao/` starts as an exact copy and diverges
   gradually as opt-in features are added.
3. `run_workflow_1.py` is NOT repointed until at least A9 (live
   single-pass regression PASS).  The shim always imports from
   `rfgun_single_pass` until explicitly approved for change.
4. `config.local.yaml` remains `.gitignore`d.
5. No existing validated workflow is deleted during A-series.
6. The 12 no-CST tests for `rfgun_single_pass` continue to pass.

## Validation plan

| Phase | Minimum validation |
|---|---|
| A3 | `compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py`, pytest 12+12 tests |
| A4 | + `python -m workflows.rfgun_sao.run --help` |
| A5 | + no-CST weight resolution tests |
| A6 | + mode config parsing tests |
| A7 | + gate logic tests with synthetic data |
| A8 | + combined two-pass/gate config tests |
| A9 | **Live CST single-pass regression** (no-CST + live) |
| A10 | **Live CST two-pass smoke** (no-CST + live) |

## Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Changing validated single-pass behaviour | **Critical** | Default config produces identical results; opt-in features are disabled by default; A9 live regression must pass before any shim change |
| Importing `cst_optimization.factory` again | **Critical** | Explicit ban in BRANCH_CONTEXT.md; tested by `test_*_source_has_no_factory_import` and `sys.modules` check |
| Config schema drift between rfgun_single_pass and rfgun_sao | Medium | A3 creates an exact copy; AI-review schema diffs in later phases |
| Two-pass solver instability | Medium | Gates and retry handler catch solver failures; inter-pass recovery resets DE |
| Duplicate evaluator logic | Medium | Share core physics computation between single-pass and two-pass code paths |
| Metric role overcomplexity | Medium | Delayed to later phases (after objective_weights and two-pass are stable) |
| Accidental mutation of validated rfgun_single_pass | **High** | BRANCH_CONTEXT.md forbids modifying rfgun_single_pass during A-series |
| Local config paths leaking into git | Low | `config.local.yaml` is already in `.gitignore`; add `config.two_pass.yaml` to `.gitignore` as well |

## Recommended next phase

**A3: Create rfgun_sao package from validated rfgun_single_pass.**

Copy `workflows/rfgun_single_pass/` verbatim to
`workflows/rfgun_sao/`, update package docstrings for "experimental
consolidation" status, add 12 import tests pointing at the new package,
and verify both packages pass all no-CST checks.  Do not change any
behaviour, do not repoint the `run_workflow_1.py` shim, and do not
modify `rfgun_single_pass/`.

Summary prompt for A3::

   mkdir workflows/rfgun_sao; copy all files from
   workflows/rfgun_single_pass/ to workflows/rfgun_sao/; update
   README/BRANCH_CONTEXT/_init_ to say experimental consolidation;
   create tests/workflows/test_rfgun_sao_imports.py from the validated
   12-test template; verify compileall and 24 tests (12 old + 12 new)
   pass; do NOT change run_workflow_1.py.
