# Phase A13.3 — Calibration diagnostics for live two-pass smoke

## Task

Add comprehensive calibration diagnostics to the opt-in CST two-pass runner
adapters (``two_pass_cst.py``), surface the calibration error in the
checkpoint/log path (``two_pass.py``), and re-run live CST smoke with the
improved observability to identify the root cause of the calibration failure
seen in A13.2.

This is a **diagnostics + smoke rerun**, not a full two-pass validation.

## Summary

- **Calibration diagnostics added** to ``make_cst_calibration_runner`` meta:
  solver fields, S11 summary, HPBW status, exception detail.
- **``_decision_error_message`` helper** added to ``two_pass.py`` so the
  checkpoint error string includes the detailed calibration.error (not just
  ``"calibration_failed"``).
- **Rejection logging** now records ``cal_success``, ``f0_ghz``,
  ``s11_min_db``, ``cal_method``, ``cal_error``, and ``meta``.
- **no-CST tests:** 76/76 passed (72 existing + 4 new in Section L).
- **Live CST smoke rerun:** exit code 0, calibration diagnostics now show
  the explicit root cause (see below).

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/two_pass_cst.py`` | Enhanced meta diagnostics |
| ``workflows/rfgun_sao/two_pass.py`` | Added ``_decision_error_message``, ``_safe_meta_str``, improved rejection logging |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section L with 4 tests |
| ``reports/restructure_plan/phase_A13_3_calibration_diagnostics.md`` | Created (this file) |

## Behavioural changes

**None for production defaults.**

- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged** (no CST, penalty
  1.0, ``workflow._conn = None``).
- ``runtime=cst`` remains **opt-in only**.
- Calibration failure errors are now surfaced in:
  - The checkpoint error string (previously just ``"calibration_failed"``)
  - The runtime log with full meta diagnostics
- No retry, inter-pass recovery, metric roles, staged search implemented.

## Diagnostics added

### Meta fields (``CalibrationResult.meta``)

| Field | Source | Present in |
|-------|--------|------------|
| ``iteration`` | Runner argument | Always |
| ``calibration_guess_ghz`` | Factory argument | Always |
| ``project_filename`` | ``project.filename`` | After open |
| ``update_ok`` | ``project.update_parameters`` return | After update |
| ``solver_success`` | ``solver_result.success`` | After solver |
| ``solver_error_type`` | ``solver_result.error_type`` | After solver |
| ``solver_error_message`` | ``solver_result.error_message`` | After solver |
| ``solver_elapsed_s`` | ``solver_result.elapsed_s`` | If available |
| ``solver_mesh_cells`` | ``solver_result.mesh_cells`` | If available |
| ``result_reader_ok`` | Whether ResultReader succeeded | After S11 attempt |
| ``s11_points`` | ``len(mag)`` | S11 read succeeded |
| ``s11_freq_min_ghz`` | ``min(frequencies)`` | S11 read succeeded |
| ``s11_freq_max_ghz`` | ``max(frequencies)`` | S11 read succeeded |
| ``s11_min_db`` | ``s11_min_db_from_magnitude`` | S11 read succeeded |
| ``hpbw_ok`` | Whether HPBW succeeded | S11 read succeeded |
| ``hpbw_error`` | HPBW exception message | HPBW failed |
| ``fallback_used`` | ``"dip_minimum"`` if HPBW fell back | HPBW failed |
| ``exception_type`` | ``type(exc).__name__`` | Top-level exception |
| ``exception_message`` | ``str(exc)[:200]`` | Top-level exception |

No full S11 arrays are stored.

### Two-pass logging (rejected path)

When a calibration/decision rejection occurs, the runtime evaluator now logs:

```
Two-pass rejected: reason=calibration_failed cal_success=False f0_ghz=nan
s11_min_db=nan cal_method=cst_s11 cal_error=<error detail>
meta={<compact meta>}
```

## Validation

### 1. no-CST pytest

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
76/76 passed
```

New tests in Section L:

| Test | What it verifies |
|------|-----------------|
| ``test_two_pass_runtime_calibration_failed_error_includes_detail`` | Checkpoint error includes both ``calibration_failed`` and the detailed ``calibration.error`` |
| ``test_cst_calibration_runner_result_reader_failure_reports_error_and_meta`` | ResultReader failure returns ``CalibrationResult(success=False)`` with ``error`` containing exception and ``meta.result_reader_ok=False`` |
| ``test_cst_calibration_runner_success_meta_contains_s11_summary`` | Success path meta includes ``s11_points``, ``s11_min_db``, ``hpbw_ok=True``, no full arrays |
| ``test_decision_error_message_for_gate_reject_remains_reason`` | ``_decision_error_message`` returns clear reason strings for gate rejections, and appends ``calibration.error`` for ``calibration_failed`` |

### 2. Live CST smoke rerun

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml ^
    --n-initial 1 --n-iter 0
```

**Exit code:** 0

**Key log lines:**
```
2026-06-01 20:51:56 [WARNING] workflows.rfgun_sao.calibration:
    Calibration failed (success=False, f0=nan), falling back to 11.424000 GHz

2026-06-01 20:51:56 [WARNING] workflows.rfgun_sao.two_pass:
    Two-pass rejected: reason=calibration_failed cal_success=False f0_ghz=nan
    s11_min_db=nan cal_method=cst_s11
    cal_error=Project file not found: F:/workflow_elgun/PickupDesign_2026.cst
    meta={iteration=0, calibration_guess_ghz=11.424, result_reader_ok=False,
    exception_type=FileNotFoundError,
    exception_message=Project file not found: F:/workflow_elgun/PickupDesign_2026.cst}
```

**Stdout:**
```
Best F: [1.]
```

**Result:** Partial pass (graceful degradation, no crash).

## Calibration diagnosis

**Root cause category:** E — environment / file system.

**Evidence:** The new diagnostics clearly show:

1. ``result_reader_ok=False`` — S11 was never attempted
2. ``exception_type=FileNotFoundError``
3. ``exception_message=Project file not found: F:/workflow_elgun/PickupDesign_2026.cst``

The project path ``F:/workflow_elgun/PickupDesign_2026.cst`` does not exist on
this machine.  The ``connection.open_project(project_path)`` call raised
``FileNotFoundError``, which was caught by the top-level ``except`` clause
and classified as a non-COM error.

**This is not a calibration sensitivity or HPBW tuning issue.**  The A13.2
failure had the same root cause — the diagnostics were simply not surfaced.

**Next recommended action:** Ensure the CST project file exists at the
configured path, or update ``config.local.yaml`` ``project.cst_path`` to
point to a valid file.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** (modified locally for smoke, restored) |
| CST project/result artifacts | **Not committed** |

## Notes / caveats

- A13.3 improves observability only.  No calibration tuning was applied.
- The A13.2 calibration failure is confirmed to be a missing project file, not
  a physics/solver issue.
- Real calibration tuning (if needed for a different environment) is future
  A13.4 or later.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search) remains future work.

## Commits

- Implementation/fix commit: ``HEAD`` — ``A13.3 add CST calibration diagnostics``
- Report commit: included in implementation commit (same hash)
- Final pushed HEAD: ``<filled after push>``
