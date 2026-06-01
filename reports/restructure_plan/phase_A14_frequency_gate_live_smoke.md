# Phase A14 — Frequency gate live smoke

## Task

Validate the frequency gate rejection path of the opt-in ``runtime=cst``
two-pass runtime: CST connection → calibration success → frequency gate
reject → measurement skipped → scalar 1.0 → checkpoint/log with clear gate
rejection.

This is **not** retry, recovery, or staged-search implementation.  It only
validates gate semantics and logging/checkpoint behaviour.

## Summary

- **Project path exists:** ``Test-Path D:/workflow_elgun/PickupDesign_2026.cst``
  → ``True``.
- **no-CST tests:** 77/77 passed.
- **Live CST smoke:** **Frequency gate rejected as expected.**
  - Calibration succeeded (``cst_s11_hpbw``, f0=11.42454 GHz).
  - Frequency gate (target=0.0 GHz, ±1 MHz) correctly rejected.
  - Measurement runner **not invoked**.
  - Best F = 1.0 (all-penalty rejection scalar).
  - Checkpoint recorded with ``solver_ok=False`` and
    ``error=frequency_gate_reject``.
  - Full calibration meta visible in the rejection log.
- **No code changes needed** — all A13 diagnostics and gate logic worked
  correctly.

## Files changed

| File | Action |
|------|--------|
| ``reports/restructure_plan/phase_A14_frequency_gate_live_smoke.md`` | Created (this file) |

No production code was modified.

## Local config

Used ``workflows/rfgun_sao/config.local.yaml`` (gitignored):

| Key | Value |
|-----|-------|
| ``evaluation.mode`` | ``two_pass`` |
| ``evaluation.two_pass.runtime`` | ``cst`` |
| ``frequency_gate.enabled`` | ``true`` |
| ``frequency_gate.target_ghz`` | ``0.0`` (impossible — forces rejection) |
| ``frequency_gate.max_abs_offset_mhz`` | ``1.0`` |
| ``s11_depth_gate.enabled`` | ``false`` |
| ``multi_dip_detection.enabled`` | ``false`` |
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

**Runtime log:** ``D:/Results/rfgun_sao_A14_frequency_gate_smoke/workflow1/workflow_1_runtime.log``

## Live CST evidence

### Key log line (rejection)

```
WARNING  workflows.rfgun_sao.two_pass:
Two-pass rejected: reason=frequency_gate_reject
cal_success=True f0_ghz=11.424540000000002
s11_min_db=-9.083001397799817 cal_method=cst_s11_hpbw cal_error=
meta={iteration=0, calibration_guess_ghz=11.424,
project_filename=D:\workflow_elgun\PickupDesign_2026.cst,
update_ok=True, solver_success=True, solver_error_type=,
solver_error_message=, solver_elapsed_s=42.7256,
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
| **Solver elapsed** | 42.7 s |
| **S11 points** | 1001 (11.414–11.434 GHz) |
| **Gate config** | ``target_ghz=0.0, max_abs_offset_mhz=1.0`` |
| **Rejection reason** | ``frequency_gate_reject`` |
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

**Frequency gate behaviour: passed.** The gate correctly:

1. Received f0=11.42454 GHz from the calibrated HPBW analysis.
2. Compared against ``target_ghz=0.0`` with ``max_abs_offset_mhz=1.0``.
3. Detected offset far exceeding 1 MHz → returned ``accepts()=False``.
4. Runtime evaluator logged ``frequency_gate_reject`` with full calibration
   meta (A13.3 diagnostics).
5. Measurement runner was **not called**.
6. Checkpoint received ``solver_ok=False`` and error string
   ``frequency_gate_reject`` (A13.3 ``_decision_error_message``).
7. Evaluator returned ``1.0`` (weighted all-ones penalty vector).

**All A13 diagnostic features worked correctly on the gate rejection path:**
- ``_safe_meta_str`` rendered the solver/S11/HPBW meta compactly.
- ``_decision_error_message`` used the plain reason (no calibration.error
   to append).
- Rejection log included calibration success details.

**No issues found.** No code changes needed.

## Notes / caveats

- This validates **frequency gate rejection only**.
- S11 depth gate live validation remains future work.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search, multi-dip detection) remains future work.

## Commits

- Implementation/fix commit: **none** — no code changes needed.
- Report commit: ``HEAD`` — ``A14 report frequency gate live smoke``
- Final pushed HEAD: ``<filled after push>``
