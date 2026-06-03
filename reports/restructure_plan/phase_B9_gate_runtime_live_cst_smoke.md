# Phase B9 — Gate runtime rejection live CST smoke

## Summary

Run a live CST smoke to validate gate metric role runtime rejection.
A gate metric (q0 with impossibly high threshold 999999999 greater_than)
was configured in an untracked local config.  The gate correctly rejected
the candidate after measurement, producing all-ones penalties,
``solver_ok=False``, ``error="gate_reject:q0_gate"``, and ``Best F = 1.0``.

## Files changed

| File | Action |
|------|--------|
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added ``B8`` to README assertion |
| ``workflows/rfgun_sao/README.md`` | Added B7/B8 entries to no-CST milestones table |
| ``reports/restructure_plan/phase_B9_gate_runtime_live_cst_smoke.md`` | Created (this file) |

No runtime production code was modified.

## No-CST validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "b8 or gate or two_pass" -v --tb=short
82/82 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
184/184 passed (full suite)
```

## Live CST configuration

| Key | Value |
|-----|-------|
| ``evaluation.mode`` | ``two_pass`` |
| ``evaluation.two_pass.runtime`` | ``cst`` |
| ``optimization.n_initial_samples`` | ``1``, ``n_iterations=0`` |
| ``retry.enabled`` | ``false`` |
| Gate metric | ``q0`` with ``threshold=999999999``, ``direction="greater_than"``, ``report_as="q0_gate"`` |
| Report_only metric | ``coupling_beta`` with ``report_as="coupling_beta_diag"`` |
| Config file | ``workflows/rfgun_sao/config.local.yaml`` (untracked, not committed) |

## Live CST evidence

### Calibration

| Property | Value |
|----------|-------|
| Calibration success | yes |
| Method | ``cst_s11_hpbw`` |
| f0 | 11.42454 GHz |
| s11_min | -9.08 dB |

### Measurement (all raw metrics computed)

```
Workflow 1 iter 0 done: coupling_beta=2.08375, field_flatness=0.0679153,
max_modified_poynting=4.0962e+12, peak_e_field=87673.2, pulsed_heating=24.8245,
q0=18630.8, resonant_freq=11.4245
```

**q0 raw value = 18630.8** — finite, but far below gate threshold 999999999.

### Gate rejection log

```
Two-pass gate results: {q0_gate=False}
```

✅ Gate correctly flagged as failing.

### Report-only diagnostics (unaffected by gate)

```
Two-pass measurement diagnostics: {coupling_beta_diag=2.08375}
```

✅ Report-only behavior unchanged from B5.

### Scalar / checkpoint evidence

| Property | Value |
|----------|-------|
| Objectives printed | **5** (7 total - 1 gate - 1 report_only = 5) |
| Best F | **1.0** (all-ones penalties after gate rejection) |
| Checkpoint saved | yes (1 record) |
| Checkpoint cleared | yes |
| Gate metric in checkpoint arrays | **no** — checkpoint arrays sized to objective_names only |

### CST cleanup

```
CST cleanup: attempted=True closed=True pid=59364
```

| Property | Value |
|----------|-------|
| DE PID | 59364 |
| Cleanup attempted | True |
| Cleanup closed | True |
| Visible DE window after run | **no** (``Get-Process -Id 59364`` → not found) |
| Background licensing ``cstd`` | present with no window (normal) |

## Live CST shutdown

| Question | Answer |
|----------|--------|
| CST window closed? | **yes** — DE process terminated by runner cleanup |
| Background licensing service | ``cstd`` with no window (normal) |

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by B9 | no |

## Commit hashes

- B9 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- **Gate role rejection validated live.** The full cycle — calibration,
  measurement, gate evaluation, candidate rejection, all-ones penalty,
  checkpoint with ``gate_reject:q0_gate`` — was confirmed.
- JSONL sidecar and Ctrl+C hard-exit cleanup remain future work.
- Next possible direction: README milestone update for complete Phase B,
  or JSONL diagnostics sidecar implementation.
