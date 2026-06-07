# Workflow 2 — Semantic Risk Cleanup Plan (W2-6)

## 1. Scope and Non-Goals

**W2-6 is planning only.** No runtime migration, no config behavior change,
no checkpoint behavior change, no scheduler change, no CST execution, no
live workflow.

| Non-goal | Status |
|----------|--------|
| Runtime code changes | ❌ Not in scope |
| Config layout changes | ❌ Not in scope |
| Checkpoint callback fix | ❌ Planning only |
| Solver timeout fix | ❌ Planning only |
| Scheduler change | ❌ Planning only |
| CST / live workflow | ❌ Not in scope |

---

## 2. Current Accepted Baseline

- W2-5 accepted at `d168f42`.
- Builder owner: `workflows/rfgun_hom_antenna/workflow.py::build_workflow_2`.
- Factory: `src/cst_optimization/factory.py::build_workflow_2` is a
  compatibility wrapper (lazy import + delegation).
- Orchestrator: `DualProjectOrchestrator` remains in
  `src/cst_optimization/core/orchestrator.py`; W2-5 found no cross-workflow
  evidence for accepted shared-core status.
- Config: `config/default.yaml["workflow_2"]` remains runtime source of
  truth (W2-3 local config is a snapshot only).
- Scheduler: `scripts/schedule_workflow2.ps1` invokes root
  `run_workflow_2.py`.
- W2-1 characterisation tests (21 tests) pin all current behaviours.
- W2-6 is planning only; no implementation is started.

---

## 3. Risk R1: Stale Root Docstring / CST Window Semantics

### Current Code Fact

`run_workflow_2.py` line 10:
```python
Reads ``config/default.yaml``, opens two independent CST windows (one per
project), builds the orchestrator + SAO optimiser, and runs the full
Bayesian optimisation loop.
```

### Current Actual Behaviour

The builder creates **one** `CSTConnection` and runs all projects
sequentially within a single DesignEnvironment.  The inter-pass reset
(`_reset_connection`) kills and recreates the DE between frequency-domain
and wakefield phases, but this is a sequential reset, not a second
simultaneous window.

The misleading docstring was already corrected in the workflow-local
builder (W2-4B), but the root `run_workflow_2.py` docstring was deferred
to W2-6 (per the W2-4B task spec).

### Proposed Cleanup Approach

Replace the single misleading sentence with accurate wording, for example:
```
Reads ``config/default.yaml``, opens one CST DesignEnvironment connection,
runs frequency-domain and wakefield solvers sequentially with an inter-pass
DE reset, and runs the full Bayesian optimisation loop.
```

### Impact Estimate

- **Low risk** of misinterpretation by future agents/developers:
  - Could lead to incorrect resource cleanup assumptions.
  - Could cause confusion about CST window management.
- No runtime impact.
- No test changes needed.

### Targeted Tests or Inspection Required

- Static inspection of root docstring only.
- No new tests needed.
- Existing W2-1 characterisation tests already pin the builder behaviour
  (single connection, sequential execution).

### Recommended Implementation Phase

**W2-6A** — standalone doc-only commit:
1. Edit `run_workflow_2.py` docstring (line 10).
2. Update `config/default.yaml` top-level docstring if present.
3. No runtime changes.
4. No test changes.
5. Self-contained, independently reviewable.

---

## 4. Risk R2: Solver Timeout Config Hierarchy Mismatch

### Current Intended Config Value

```
config/default.yaml → workflow_2.optimization.solver.stagnation_timeout_s: 7200.0
```

### Current Actual Builder Read Path

`workflows/rfgun_hom_antenna/workflow.py` line 144–148:
```python
solver_cfg = config.get("solver", {})
solver_runner = SolverRunner(
    timeout_s=solver_cfg.get("stagnation_timeout_s", 0.0),
    settle_s=solver_cfg.get("settle_s", 2.0),
)
```

Where `config` is the `workflow_2` section dict. This reads
`workflow_2.solver.stagnation_timeout_s`, **not**
`workflow_2.optimization.solver.stagnation_timeout_s`.

### Current Root Fallback Behaviour

`run_workflow_2.py` lines 99–101 merge top-level sections into
`workflow_2` only when the key doesn't already exist:
```python
for section in ("cst", "solver", "logging"):
    if section in cfg and section not in wf2_cfg:
        wf2_cfg[section] = cfg[section]
```

Since `workflow_2.solver` doesn't exist **as a direct key** in
`config/default.yaml`, the top-level `solver` (`stagnation_timeout_s:
300.0`) gets merged in.  The resulting `workflow_2.solver` has
`stagnation_timeout_s: 300.0`.

### W2-1 Characterisation Confirmation

`test_optimization_solver_key_is_not_read_by_builder` (P0.2) confirms
the `optimization.solver` path is **not consumed** by the builder.
`test_solver_timeout_comes_from_merged_solver_section` confirms the
effective value is the top-level fallback `300.0`.

### Options

#### Option A: Preserve Current Behaviour and Document It

- Accept that WF2 uses the same 300 s timeout as WF1.
- Remove the stale 7200.0 intent from `config/default.yaml`.
- Document this in the local `config.yaml` header.
- **Compatibility risk**: Low (preserves existing runtime behaviour).
- **Test needs**: None (existing W2-1 tests pass as-is).

#### Option B: Change Builder Read Path to Consume `optimization.solver`

- In `workflows/rfgun_hom_antenna/workflow.py`, change to:
  ```python
  opt_cfg = config.get("optimization", {})
  solver_cfg = opt_cfg.get("solver", {})
  timeout_s = solver_cfg.get("stagnation_timeout_s", 0.0)
  ```
- **Compatibility risk**: **High** — would change effective timeout from
  300 s to 7200 s for all evaluations.  Could mask genuine solver hangs.
- **Test needs**:
  - Update W2-1 P0.2 tests to pin new behaviour.
  - Add regression test checking the actual `SolverRunner._timeout_s`.
  - No-CST only.

#### Option C: Change Root Merge Behaviour

- Stop merging top-level `solver` into `workflow_2`, or only merge when
  `workflow_2.optimization.solver` is absent.
- **Compatibility risk**: **Medium** — would change effective timeout
  from 300 s to `SolverRunner._DEFAULT_TIMEOUT_S` (7200.0 s) if no
  `workflow_2.solver` exists.
- **Test needs**: Update config merge characterisation tests (P0.1).

#### Option D: Change Config Layout

- Move `workflow_2.optimization.solver.stagnation_timeout_s` to
  `workflow_2.solver.stagnation_timeout_s` in `config/default.yaml` and
  remove the top-level `solver` merge.
- **Compatibility risk**: **Medium** — changes the YAML layout that tools
  and operators may have hard-coded expectations about.
- **Test needs**: Update config parsing and merge tests.

### Recommendation

**Option A (preserve + document) for the immediate next phase, with
Option B as a deferred decision**:

1. In W2-6B, **do not change runtime behaviour**.  Accept that WF2
   currently uses 300 s (the merged fallback) for solver timeout.
2. Document this decision in the local `config.yaml` header comment
   (the existing comment already says the intent value is not consumed).
3. Optionally remove the stale 7200.0 from
   `config/default.yaml#workflow_2.optimization.solver.stagnation_timeout_s`
   in a later phase after confirming no external tooling depends on it.
4. If a longer timeout is genuinely needed for wakefield solvers, that
   should be a deliberate operational decision with its own
   implementation phase and acceptance tests.

**Do not implement any option in W2-6.** W2-6 is planning only.

---

## 5. Risk R4: Checkpoint Callback Double-Trigger

### Current Behaviour (Pinned by W2-1)

`TestCheckpointCallbackCount` (3 tests) confirms:
- `checkpoint_callback` fires **2 times per evaluation** on both
  retry-enabled and retry-disabled paths.
- Both the `DualProjectOrchestrator.execute()` method (line 567 in
  orchestrator.py) and the factory evaluator wrapper (lines 325–326 in
  workflow.py) invoke the same callback.

### Likely Sources of Duplicate

1. **Orchestrator path** (`orchestrator.py:567–571`):
   ```python
   if self._checkpoint_callback is not None:
       self._checkpoint_callback(params, raw_values, penalties,
                                  all_solvers_ok, error_str)
   ```
   This fires unconditionally at the end of every `execute()` call.

2. **Evaluator path** (`workflow.py:325–326`):
   ```python
   if checkpoint_callback is not None:
       checkpoint_callback(x_phys, raw_arr, penalties_arr,
                           result.status == _ES.SUCCESS, result.error or "")
   ```
   This fires after the `retry_handler` returns (retry path) or after
   direct orchestrator execution (non-retry path).

Because the evaluator calls `orch.execute()` internally, the orchestrator
fires the callback first, then the evaluator fires it again with the same
or derived data.

### Options

#### Option A: Preserve and Document

- Accept double-trigger as the current behaviour.
- Document it in the builder docstring and orchestrator docstring.
- No code changes.
- **Compatibility risk**: None.
- **Test needs**: Keep existing W2-1 tests as regression.

#### Option B: Disable Orchestrator Callback Path

- Remove `self._checkpoint_callback(...)` from `orchestrator.py` and rely
  solely on the evaluator wrapper to fire the callback.
- **Compatibility risk**: **Medium** — if any consumer depends on the
  orchestrator firing callbacks independently (e.g., during partial
  evaluations or retry recovery), they would lose logging.
- **Test needs**:
  - Update W2-1 P0.3 tests to expect 1 call (not 2).
  - Add tests verifying the evaluator path still fires on all code paths
    (retry, non-retry, error, success).
  - Add test verifying crash-resume path still fires callbacks.

#### Option C: Add De-Duplication

- Use a sentinel or evaluation-tracking set in the callback to skip
  duplicate invocations for the same `(x_phys, iteration)`.
- **Compatibility risk**: Low — preserves both paths, just suppresses
  the second call for the same data.
- **Test needs**:
  - Update W2-1 P0.3 tests to expect 1 call.
  - Add test verifying the dedup logic doesn't accidentally skip
    legitimate distinct evaluations.

#### Option D: Introduce Callback Ownership Rule

- Formally define that only the **evaluator wrapper** owns the callback
  contract.  The orchestrator should not call it.
- Remove from orchestrator; add assertion that no other path calls it.
- **Compatibility risk**: Medium (same as Option B but with stronger
  guarantees).

### Recommendation

**Option A (preserve + document) for the immediate next phase, with
Option D as the preferred eventual resolution**:

1. In W2-6C, accept that double-trigger exists and is pinned by tests.
2. Document that the current behaviour is intentional for crash-resume
   transparency (both orchestrator and evaluator report independently).
3. If a future phase decides to deduplicate, **Option D** (evaluator owns
   callback, orchestrator removed) is preferred because:
   - It eliminates the source of the double call.
   - The orchestrator's `execute()` already sets `last_raw_values` and
     `last_penalties` which the evaluator reads — data doesn't depend on
     the callback.
   - It simplifies the contract to: "the builder's evaluator callback
     is the sole observer."

**Do not implement any option in W2-6.** W2-6 is planning only.

---

## 6. Risk R6: Scheduler / Root Shim Compatibility

### Current Scheduler Entry Behaviour

`scripts/schedule_workflow2.ps1` (line 58):
```powershell
$ActionArgs = "`"$ScriptPath`" --auto-resume --heartbeat"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $ActionArgs
```

This directly references `run_workflow_2.py` (resolved via `$WorkDir`).
The script creates a Windows scheduled task that runs at startup with a
delay and uses `--auto-resume --heartbeat`.

### Why Root Shim Compatibility Remains a Hard Boundary

- The scheduler is a **Windows Task Scheduler registration script**.
- If `run_workflow_2.py` is moved or deleted, the scheduled task would
  fail with a file-not-found error.
- The scheduler is typically set up by an operator and may not be
  immediately updated after a code migration.
- Root `run_workflow_2.py` was designated as a protected path in W2-0.

### Planning Options for Future Migration

#### Option 1: Keep Scheduler Unchanged

- Maintain `run_workflow_2.py` as a permanent root shim.
- The shim delegates to the workflow-local builder (already the case
  since W2-4A).
- No scheduler changes needed ever.
- **Compatibility risk**: None.
- **Downside**: Perpetuates the root-level script.

#### Option 2: Make Root Shim Delegate to Workflow Package Runtime

- Replace `run_workflow_2.py` body with a thin CLI that imports and runs
  `workflows.rfgun_hom_antenna.run.main()`.
- Keep the file path and name unchanged (scheduler still references it).
- **Compatibility risk**: Low as long as CLI flags are preserved.
- **Test needs**:
  - Add no-CST test that `run_workflow_2.py --help` or equivalent
    minimal invocation works.
  - Add no-CST import-and-config test.
  - W2-1 `test_root_main_merges_cst_solver_logging` covers
    `run_workflow_2.main()` already.

#### Option 3: Introduce Scheduler Feature Flag

- Add an environment variable or config toggle that lets the scheduler
  switch between `run_workflow_2.py` and a future workflow-package entry.
- **Compatibility risk**: Medium (new config surface).
- **Test needs**: Config parsing tests for the feature flag.

### Required No-CST Tests Before Any Change

- **P0**: `test_root_main_merges_cst_solver_logging` (already exists in
  W2-1 characterisation) — pins config merge behaviour.
- **P1**: Static test confirming scheduler script still references
  `run_workflow_2.py` (already exists in W2-2 skeleton tests).
- **P1**: Import-and-extract CLI args test (not yet written).

### Recommendation

**Option 2** (root shim delegates to workflow package) is the preferred
end state, but **should not be implemented in W2-6**.  The current state
(Option 1) is acceptable for production because:
- The root shim already imports from the workflow package (W2-4A).
- All scheduler invocations continue to work.
- No operator-visible change is needed.

When migration is desired, the minimum change is:
1. Create `workflows/rfgun_hom_antenna/run.py::main()` that wraps the
   current `run_workflow_2.py::main()`.
2. Replace `run_workflow_2.py::main()` body to call
   `workflows.rfgun_hom_antenna.run.main()`.
3. Update the W2-1 `test_root_main_merges_cst_solver_logging` to import
   from the new location.
4. Keep `run_workflow_2.py` as a file (scheduler path remains valid).

**Do not implement any option in W2-6.** W2-6 is planning only.

---

## 7. Proposed Implementation Order After W2-6

Each phase is independently reviewable.  No phase changes runtime
behaviour unless explicitly stated.

| Phase | Scope | Est. Effort | Runtime Change? |
|-------|-------|-------------|-----------------|
| **W2-6A** | Root docstring cleanup (R1) | Tiny (1 file, 1 line) | ❌ Doc only |
| **W2-6B** | Solver timeout decision (R2) | Small (config+solver read path) | ⚠️ If Option B/C/D chosen |
| **W2-6C** | Checkpoint callback decision (R4) | Medium (orchestrator+evaluator) | ⚠️ If Option B/C/D chosen |
| **W2-6D** | Scheduler/root shim migration (R6) | Small (run.py delegation) | ⚠️ If Option 2 chosen |

**Recommended execution order** (deferring R2/R4 behaviour changes):

1. **W2-6A** first — trivial doc fix, quick acceptance.
2. **W2-6D** next — no behaviour change, just establishes the delegation
   pattern.
3. **W2-6B** — decide on solver timeout: Option A (document only) is
   quickest; Option B or C require careful review.
4. **W2-6C** — checkpoint callback: Option A (document only) is quickest;
   Option D requires orchestrator change and test updates.

---

## 8. Test Plan Matrix

| Risk | No-CST Tests to Add/Update | Existing Tests to Preserve | Forbidden Validations | Live CST Needed Later? |
|------|---------------------------|---------------------------|----------------------|----------------------|
| **R1** docstring | None needed | All W2-1, W2-2 | None | ❌ No |
| **R2** timeout | Option A: none.  Option B/C: update P0.2 `SolverRunner._timeout_s` assertions | `test_optimization_solver_key_is_not_read_by_builder`, `test_solver_timeout_*` | Do not delete P0.2 tests without replacement | ❌ No |
| **R4** callback | Option A: none.  Option D: update P0.3 expected call count 2→1 | `test_non_retry_path_*`, `test_retry_path_*`, `test_both_paths_invoke_callback_*` | Do not remove P0.3 tests | ❌ No |
| **R6** scheduler | Static text test (exists in W2-2); optional `run.py --help` test | `test_scheduler_*` in skeleton tests | Do not remove scheduler path test | ❌ No |

---

## Appendix: Search Commands Used

```powershell
# R1: stale docstring
grep -rn "two independent CST\|independent CST window" run_workflow_2.py

# R2: solver timeout read paths
grep -rn "stagnation_timeout_s" config/default.yaml workflows/ src/ tests/

# R4: checkpoint callback paths
grep -n "checkpoint_callback" workflows/rfgun_hom_antenna/workflow.py

# R6: scheduler entry
head -5 scripts/schedule_workflow2.ps1
```
