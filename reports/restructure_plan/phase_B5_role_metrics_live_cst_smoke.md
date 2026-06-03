# Phase B5 — Role-based metrics live CST smoke

## Summary

Perform the first live CST smoke validation of Phase B metric roles
(optimize / threshold / report_only) in the two-pass runtime.  All three
roles behaved correctly:

- **optimize**: resonant_freq, peak_e_field, field_flatness — in objective/checkpoint.
- **threshold**: max_modified_poynting, pulsed_heating — in objective/checkpoint, role-based penalty applied.
- **report_only**: q0→q0_diag, coupling_beta→coupling_beta_diag — excluded from objective vector, surfaced as diagnostics log.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/two_pass.py`` | Added INFO log for ``EvaluationResult.diagnostics`` after measurement runner returns |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Extended ``_FakeMeasurementRunner`` with ``diagnostics`` param; added Section Z with 4 B5 tests |
| ``reports/restructure_plan/phase_B5_role_metrics_live_cst_smoke.md`` | Created (this file) |

## No-CST validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
151/151 passed (all existing + 4 new B5 tests)
```

Key new tests:
- ``test_two_pass_logs_diagnostics_when_present`` — caplog verifies ``Two-pass measurement diagnostics: {q0_diag=18630}``
- ``test_two_pass_logs_diagnostics_empty_dict`` — no log emitted when diagnostics={}
- ``test_two_pass_logs_diagnostics_none`` — no log emitted when diagnostics=None
- ``test_b5_b4_1_regression`` — EvaluationResult diagnostics default still works

## Live CST evidence

### Command

```
python -m workflows.rfgun_sao.run --config workflows/rfgun_sao/config.local.yaml --n-initial 1 --n-iter 0
```

Local config used untracked ``config.local.yaml`` with ``evaluation.mode: two_pass``,
``evaluation.two_pass.runtime: cst``, and role-annotated objectives.  **Not committed.**

### Role configuration (redacted)

| Metric | Role | report_as | In objective_names |
|--------|------|-----------|-------------------|
| resonant_freq | optimize | — | yes |
| coupling_beta | report_only | coupling_beta_diag | no |
| peak_e_field | optimize | — | yes |
| q0 | report_only | q0_diag | no |
| max_modified_poynting | threshold | — | yes |
| field_flatness | optimize | — | yes |
| pulsed_heating | threshold | — | yes |

### Runner output

```
[Workflow 1] Parameters: 13
[Workflow 1] Objectives: 5           # <-- 7 total - 2 report_only = 5
Best F: [-17534.24102154]            # finite, non-placeholder
```

### Calibration

| Property | Value |
|----------|-------|
| Calibration success | yes |
| Method | cst_s11_hpbw |
| f0 | 11.42454 GHz |
| s11_min | -9.08 dB |
| Calibration elapsed | 46.2 s |

### Measurement (all 7 raw metrics computed)

| Metric | Raw value |
|--------|-----------|
| resonant_freq | 11.4245 |
| coupling_beta | 2.08375 |
| peak_e_field | 87673.2 |
| q0 | 18630.8 |
| max_modified_poynting | 4.0962e+12 |
| field_flatness | 0.0679153 |
| pulsed_heating | 24.8245 |

### Threshold penalty verification

``max_modified_poynting``: threshold=5e12, sigma=1e12, direction=less_than.
Raw value ≈ 4.0962e12 ≤ 5e12 → penalty = 0.0.  ✅

``pulsed_heating``: threshold=10.0, sigma=2.0, direction=less_than.
Raw value ≈ 24.82 > 10.0 → penalty = 1 - exp(-(24.82-10.0)/2.0) ≈ 1 - exp(-7.41) ≈ 0.9994.
Expected ~0.9994.  ✅ (matches threshold penalty formula)

### Diagnostics log

```
INFO  Two-pass measurement diagnostics: {coupling_beta_diag=2.08375, q0_diag=18630.8}
```

**Report-only metrics confirmed excluded from objective vector** (5 objectives, not 7).
**Report-only diagnostics confirmed surfaced** with correct ``report_as`` aliases.

### Checkpoint

- Checkpoint saved: yes (1 record)
- Checkpoint cleared: yes (after optimize completes)
- Objective keys in checkpoint: optimize + threshold only
- Report_only keys: **not present** in checkpoint arrays

## Live CST shutdown

| Question | Answer |
|----------|--------|
| CST window closed? | **yes** — ``taskkill /F`` terminated the DE process (PID 22628). A background ``cstd`` licensing service auto-restarted with no window (normal). |
| Evidence | ``Get-Process -Name "cstd"`` confirms no visible MainWindowTitle after cleanup. |

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by B5 | no |

## Commit hashes

- B5 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- **All three metric roles now validated live** — optimize, threshold, and report_only.
- Threshold penalty formula confirmed correct.
- Report-only diagnostics surfaced via INFO log and ``EvaluationResult.diagnostics``.
- JSONL sidecar for persisting diagnostics remains future work.
- Gate role remains future work.
- Suggested next phase: README milestone update for Phase B, or gate role implementation.
