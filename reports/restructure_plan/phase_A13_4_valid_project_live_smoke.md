# Phase A13.4 — Valid-project live CST smoke

## Task

Use a valid local CST project file to run the opt-in ``runtime=cst`` two-pass
live smoke.  Previous smokes (A13.2, A13.3) failed because the configured
project path did not exist.  The goal is to exercise the full two-pass path:

CST connection → calibration runner → solver/S11 read → f0 detection
→ gate decision → measurement runner → scalar / checkpoint / log.

This is **smoke-level validation**, not full production validation.

## Summary

- **Project path existence:** ``Test-Path D:/workflow_elgun/PickupDesign_2026.cst``
  → ``True``.
- **no-CST tests:** 76/76 passed.
- **Live CST smoke:** **Full minimal pass** — every step of the two-pass
  orchestration succeeded.
- **No code changes needed** — all A13 adapters functioned correctly with a
  real CST project.
- **Measurement reached:** Yes — ``Workflow1Evaluator.evaluate_single_pass``
  returned full metric set.
- **Best F:** -15185.95 (finite, non-trivial, not 1.0).

## Files changed

| File | Action |
|------|--------|
| ``reports/restructure_plan/phase_A13_4_valid_project_live_smoke.md`` | Created (this file) |

No production code was modified.

## Local config

Used ``workflows/rfgun_sao/config.local.yaml`` (gitignored):

- ``evaluation.mode: two_pass``
- ``evaluation.two_pass.runtime: cst``
- ``optimization.n_initial_samples: 1``, ``n_iterations: 0``
- ``retry.enabled: false``
- ``project.cst_path: D:/workflow_elgun/PickupDesign_2026.cst``

Restored to ``single_pass`` after smoke.  **Not committed.**

## Validation

### 1. Git status check

```
$ git status --short
(clean — no staged/unstaged changes)
```

### 2. Project path existence

```powershell
PS> Test-Path D:/workflow_elgun/PickupDesign_2026.cst
True
```

### 3. no-CST pytest

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
76/76 passed
```

### 4. Live CST smoke

**Command:**
```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml
    --n-initial 1 --n-iter 0
```

**Exit code:** 0

**Runtime log:** ``D:/Results/rfgun_sao_A13_4_smoke/workflow1/workflow_1_runtime.log``

## Live CST evidence

| Property | Value |
|----------|-------|
| **Exit code** | 0 |
| **CST PID** | 40320 |
| **Project path exists** | True |
| **CST branch entered** | Yes (``two_pass CST`` log line) |
| **Calibration success** | True (no failure/warning logged) |
| **f0_ghz** | ``11.4245`` (from evaluator post-processing) |
| **Calibration method** | HPBW or dip-min (not observable from accepted-path log — no rejection logged) |
| **Measurement invoked** | Yes |
| **Evaluator metrics** | ``resonant_freq=11.4245, coupling_beta=2.08375, field_flatness=0.0679153, max_modified_poynting=4.0962e+12, peak_e_field=87673.2, pulsed_heating=24.8245, q0=18630.8`` |
| **Checkpoint saved** | Yes (1 record) |
| **Checkpoint cleared** | Yes |
| **Best F** | -15185.95 |
| **CST artifacts created** | Not checked into git |

## Diagnosis

**Root cause category:** A — Full minimal pass.

**Evidence:** The runtime log shows:
1. CST connection established (PID=40320) — line 5
2. Two-pass CST branch entered — line 5
3. Calibration succeeded (no ``Calibration failed`` warning, no
   ``Two-pass rejected`` log)
4. Measurement runner invoked → ``Workflow1Evaluator.evaluate_single_pass``
   called — line 8-9
5. All 7 metrics computed successfully — line 9
6. Checkpoint saved and cleared — lines 10-11
7. Best F = -15185.95 (finite) — line 12

**Conclusion:** The A13 two-pass CST runtime adapter is functionally correct
for the basic smoke path.  The A13.2/A13.3 failures are confirmed to have been
caused solely by the invalid project path.

**No further action required** for the basic two-pass orchestration.
Future phases (retry, recovery, gates, staged search) remain separate.

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

## Notes / caveats

- A13.4 confirms the two-pass CST adapter works end-to-end with a valid
  project file.
- The calibration succeeded silently (no rejection log) — the A13.3
  diagnostics are only exercised on the failure path, which is correct
  behaviour.
- Full production validation (retry, inter-pass recovery, metric roles,
  staged search, enabled gates) remains future work.
- No gates were enabled — the ``accepted`` path is the only one exercised.

## Commits

- Implementation/fix commit: **none** — no code changes needed
- Report commit: ``HEAD`` — ``A13.4 report valid-project live CST smoke``
- Final pushed HEAD: ``44dcece``
