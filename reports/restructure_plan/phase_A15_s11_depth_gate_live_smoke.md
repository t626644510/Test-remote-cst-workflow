# Phase A15 — S11 depth gate live smoke

## Task

Validate the S11 depth gate rejection path of the opt-in ``runtime=cst``
two-pass runtime: CST connection → calibration success → S11 depth gate
reject → measurement skipped → scalar 1.0 → checkpoint/log with clear gate
rejection.

This is **not** retry, recovery, or staged-search implementation.  It only
validates gate semantics and logging/checkpoint behaviour.

## Summary

- **Project path exists:** ``Test-Path D:/workflow_elgun/PickupDesign_2026.cst``
  → ``True``.
- **no-CST tests:** 77/77 passed.
- **Live CST smoke:** **S11 depth gate rejected as expected.**
  - Calibration succeeded (``cst_s11_hpbw``, f0=11.42454 GHz,
    s11_min_db=-9.08 dB).
  - S11 depth gate (threshold=-100.0 dB) correctly rejected
    (``-9.08 <= -100.0`` is False).
  - Measurement runner **not invoked**.
  - Best F = 1.0 (all-penalty rejection scalar).
  - Checkpoint recorded with ``solver_ok=False`` and
    ``error=s11_depth_gate_reject``.
  - Full calibration meta visible in the rejection log.
- **No code changes needed** — gate logic and diagnostics worked correctly.

## Files changed

| File | Action |
|------|--------|
| ``reports/restructure_plan/phase_A15_s11_depth_gate_live_smoke.md`` | Created (this file) |

No production code was modified.

## Local config

Used ``workflows/rfgun_sao/config.local.yaml`` (gitignored):

| Key | Value |
|-----|-------|
| ``evaluation.mode`` | ``two_pass`` |
| ``evaluation.two_pass.runtime`` | ``cst`` |
| ``s11_depth_gate.enabled`` | ``true`` |
| ``s11_depth_gate.threshold_db`` | ``-100.0`` (impossibly deep — forces rejection) |
| ``frequency_gate.enabled`` | ``false`` |
| ``optimization.n_initial_samples`` | ``1`` |
| ``optimization.n_iterations`` | ``0`` |
| ``retry.enabled`` | ``false`` |

Restored to ``single_pass`` after smoke.  **Not committed.**

## Validation

### 1. Git status

```
$ git status --short
(clean — no staged/unstaged changes)
```

### 2. Project path

```powershell
PS> Test-Path D:/workflow_elgun/PickupDesign_2026.cst
True
```

### 3. no-CST pytest

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
77/77 passed
```

### 4. Live CST smoke

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml
    --n-initial 1 --n-iter 0
```

**Exit code:** 0

**Runtime log:** ``D:/Results/rfgun_sao_A15_s11_gate_smoke/workflow1/workflow_1_runtime.log``

## Live CST evidence

### Key log line (rejection)

```
WARNING  workflows.rfgun_sao.two_pass:
Two-pass rejected: reason=s11_depth_gate_reject
cal_success=True f0_ghz=11.424540000000002
s11_min_db=-9.083000809287805 cal_method=cst_s11_hpbw cal_error=
meta={iteration=0, calibration_guess_ghz=11.424,
project_filename=D:\workflow_elgun\PickupDesign_2026.cst,
update_ok=True, solver_success=True, solver_error_type=,
solver_error_message=, solver_elapsed_s=43.9581,
result_reader_ok=True, s11_points=1001,
s11_freq_min_ghz=11.414, s11_freq_max_ghz=11.434,
s11_min_db=-9.083, hpbw_ok=True}
```

### Summary table

| Property | Value |
|----------|-------|
| **Exit code** | 0 |
| **CST connection** | Created (PID in log — ``two_pass CST``) |
| **Calibration success** | ✅ ``True`` |
| **f0_ghz** | 11.42454 GHz |
| **s11_min_db** | -9.08 dB |
| **Calibration method** | ``cst_s11_hpbw`` |
| **Solver elapsed** | 43.96 s |
| **S11 points** | 1001 (11.414–11.434 GHz) |
| **Gate config** | ``threshold_db=-100.0`` (impossibly deep) |
| **Rejection reason** | ``s11_depth_gate_reject`` |
| **Measurement invoked** | ❌ No (correct) |
| **Best F** | 1.0 (all-penalty) |
| **Checkpoint** | Saved (1 record) → cleared |

## Behavioural changes

**None.** No production code was modified.

- ``single_pass`` path: **unchanged**.
- ``two_pass`` default ``placeholder`` runtime: **unchanged**.
- ``runtime=cst`` remains **opt-in only**.
- No retry, inter-pass recovery, metric roles, staged search implemented.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` | **Not modified** |
| ``run_workflow_1.py`` | **Not modified** |
| ``src/cst_optimization/`` | **Not modified** |
| ``config.local.yaml`` | **Not committed** (modified locally for smoke, restored) |
| CST project/result artifacts | **Not committed** |

## Diagnosis

**S11 depth gate behaviour: passed.** The gate correctly:

1. Received s11_min_db=-9.08 dB from the calibrated HPBW analysis.
2. Compared against ``threshold_db=-100.0``.
3. ``s11_min_db <= threshold_db`` evaluated as ``-9.08 <= -100.0`` = ``False``
   → returned ``accepts()=False``.
4. Runtime evaluator logged ``s11_depth_gate_reject`` with full calibration
   meta (A13.3 diagnostics).
5. Measurement runner was **not called**.
6. Checkpoint received ``solver_ok=False`` and error string
   ``s11_depth_gate_reject`` (A13.3 ``_decision_error_message``).
7. Evaluator returned ``1.0`` (weighted all-ones penalty vector).

**All gate rejection features worked correctly.**
- ``_decision_error_message`` returned the plain reason (no
  ``calibration.error`` to append — correct for gate rejections).
- Rejection log included solver time, S11 stats, HPBW confirmation.

**No issues found.** No code changes needed.

## Notes / caveats

- This validates **S11 depth gate rejection only**.
- Multi-dip detection and mixed gate configurations remain future work.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search) remains future work.

## Commits

- Implementation/fix commit: **none** — no code changes needed.
- Report commit: ``HEAD`` — ``A15 report S11 depth gate live smoke``
- Final pushed HEAD: ``2a258c6``
