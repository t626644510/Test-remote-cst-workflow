# Phase A12 — Injectable two-pass runtime evaluator skeleton

## Task

Upgrade A11's constant placeholder evaluator to an injectable two-pass
runtime evaluator skeleton with pluggable calibration/measurement runners.
Default behaviour does **not** change: placeholder runners still produce
calibration failure, penalty 1.0, and no CST connection.

This is **not** live CST two-pass — it establishes the orchestration
interface and enables fake-runner tests of the real control flow
(param_dict → calibration → decision gating → measurement → weighted
scalar → checkpoint).

## Summary

### two_pass.py additions
- `make_placeholder_calibration_runner()` — returns a runner that always
  produces `CalibrationResult(success=False)`.
- `make_placeholder_measurement_runner()` — returns a runner that always
  produces `EvaluationResult(status=SOLVER_FAILED)`.
- `make_two_pass_runtime_evaluator(**kwargs)` — the core factory,
  taking keyword-only `param_names`, `metric_names`, `objectives`,
  `weights`, gates, `calibration_runner`, `measurement_runner`, and
  optional `checkpoint_callback`. Internal control flow:
  1. `x_phys` → `param_dict`
  2. `calibration_runner` → `CalibrationResult`
  3. `evaluate_two_pass_decision` → gate check
  4. Rejected: `penalty=1.0`, no measurement call
  5. Accepted: `measurement_runner` → `EvaluationResult`
  6. Penalty extraction & weighted scalar → checkpoint → return

### workflow.py changes
- Re-added `param_names` and `weights` (now actually consumed by the
  runtime evaluator, not unused locals).
- Switched from `make_two_pass_placeholder_evaluator` to
  `make_two_pass_runtime_evaluator` with placeholder runners.
- Forwarded `checkpoint_callback` to the runtime evaluator.

### Test additions
- `_FakeCalibrationRunner` and `_FakeMeasurementRunner` helper classes.
- 5 new tests (total: 53 → 58).

## Files changed

| File | Action |
|---|---|
| `workflows/rfgun_sao/two_pass.py` | Added placeholder runners + `make_two_pass_runtime_evaluator`; preserved `make_two_pass_placeholder_evaluator` unchanged |
| `workflows/rfgun_sao/workflow.py` | Re-added `param_names`/`weights`; switched to runtime evaluator with placeholder runners |
| `tests/workflows/test_rfgun_sao_imports.py` | Added `_FakeCalibrationRunner`, `_FakeMeasurementRunner` + 5 new tests |
| `workflows/rfgun_sao/README.md` | Updated Implemented/Not-implemented lists |
| `reports/restructure_plan/phase_A12_two_pass_runtime_skeleton.md` | Created (this file) |

## Behavioural changes

**None for production behaviour.**
- `single_pass` path: **unchanged**.
- `two_pass` default: still returns penalty 1.0, `workflow._conn is None`,
  no CST connection created.
- The control flow now runs through `make_two_pass_runtime_evaluator`
  instead of the constant-1.0 placeholder, but with placeholder runners
  the result is identical.

**Fake-runner-verifiable orchestration is now available:**
- Successful calibration + measurement can be fully exercised in no-CST tests.
- Gate rejection (frequency, s11 depth) is tested without CST.
- Checkpoint callback is called from two-pass path.
- Weighted scalar arithmetic is validated.

**Protected areas confirmed unchanged:**

| Area | Status |
|---|---|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `config.local.yaml` | **Not modified / not committed** |

**two_pass placeholder invariant:** `workflow._conn is None` still holds;
no CST connection is created.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
# … 58/58 passed (see result below)

$ git diff --name-only
workflows/rfgun_sao/README.md
workflows/rfgun_sao/two_pass.py
workflows/rfgun_sao/workflow.py
tests/workflows/test_rfgun_sao_imports.py
reports/restructure_plan/phase_A12_two_pass_runtime_skeleton.md
```

## Notes / caveats

- A12 adds injectable orchestration only — the production default still
  uses placeholder runners that always fail calibration.
- Real CST calibration/measurement runners should be implemented in A13
  or later.
- No CST imports were added to `two_pass.py`; it remains pure Python with
  no dependency on CST-related modules.
- `cst_optimization.workflows.recovery` is not imported anywhere in
  `workflows/rfgun_sao/`.

## Commits

```
978c25c
```
