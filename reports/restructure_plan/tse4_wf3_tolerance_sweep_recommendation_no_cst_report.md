# TSE4 — no-CST tolerance sweep recommendations

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `TSE4 — no-CST tolerance sweep recommendation rules` |
| Base branch | `main` |
| Base HEAD | `2cc4d3a655c7ab1fa4d96aee86153e85f71a3312` |
| Branch | `feature/wf3-tolerance-sweep-envelope-tse4` |
| Live CST | **No** |
| Runtime behavior changed | **No** |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/tolerance_sweep_recommendation.py` | **Added** | Recommendation rules, level evaluation, metric/overall envelope recommendation |
| `tests/workflows/test_rfgun_sao_tolerance_sweep_recommendation.py` | **Added** | 22 tests |
| `reports/restructure_plan/tse4_wf3_tolerance_sweep_recommendation_no_cst_report.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | TSE4 phase |

---

## Implemented module

| API | Description |
|-----|-------------|
| `MetricAcceptanceRule` | Threshold config: max_mean, min_mean, max_cv, clean CV, failure rate, outliers, delta from baseline |
| `MetricLevelDecision` | One level's evaluation status (pass/warning/fail/unknown) |
| `MetricToleranceRecommendation` | Recommended max tolerance for one metric |
| `SweepToleranceRecommendation` | Overall envelope recommendation across metrics |
| `evaluate_metric_level()` | Evaluate one level against one rule |
| `recommend_metric_tolerance()` | Recommend max tolerance for one metric curve |
| `recommend_tolerance_envelope()` | Combine multiple metric recommendations into envelope |
| `default_field_flatness_rule()` | Conservative placeholder rule |

---

## Rule semantics

### Status priority

| Condition | Status |
|-----------|--------|
| Values missing/non-finite | `unknown` |
| Any hard threshold violated | `fail` |
| Delta-from-baseline exceeded (no hard fail) | `warning` |
| All thresholds satisfied | `pass` |

### Hard thresholds

| Threshold | Fails if |
|-----------|----------|
| `max_mean` | `mean > max_mean` |
| `min_mean` | `mean < min_mean` |
| `max_cv_percent` | `cv_percent > max_cv_percent` |
| `max_clean_cv_percent` | `clean_cv_percent > max_clean_cv_percent` |
| `max_failure_rate` | `failure_rate > max_failure_rate` |
| `max_outliers` | `n_outliers > max_outliers` |
| `target_mean` + `max_abs_error_from_target` | `abs(mean - target) > max_abs_error` |

### Delta-from-baseline

Delta comparisons use the lowest tolerance level as baseline.  These produce
`warning` status unless a hard threshold already produced `fail`.  Relative
delta (`max_relative_delta_from_baseline`) uses `|delta| / |baseline_mean|`
and is skipped when `|baseline_mean| < 1e-12`.

---

## Recommended max tolerance policy

| Pattern | Recommended max |
|----------|----------------|
| All levels pass | Highest level |
| First level fails | `None` |
| Pass then fail | Highest pass level before first fail |
| Warning present | Highest pass level before first warning |
| Unknown levels | Do not expand recommendation |

### Overall envelope

`overall_recommended_max_tolerance_um` = minimum non-None recommendation
across all metrics.  `limiting_metrics` identifies which metrics set the limit.

---

## Field_flatness / offset1 synthetic example

| Level (um) | Mean | Status | Reason |
|-----------|------|--------|--------|
| 3 | 0.02 | pass | — |
| 10 | 0.04 | pass | — |
| 30 | 0.15 | fail | mean > max_mean (0.08) |

**Result:** recommended_max = 10um, first_failure = 30um, limiting = field_flatness.

---

## Tests

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestLevelEvaluation` | 9 | Pass, fail on max_mean/min_mean/max_cv/clean_cv/failure_rate/outliers/target_error, warning on delta |
| `TestMetricRecommendation` | 6 | All pass, first fail, pass-then-fail, pass-then-warning, knee candidate, empty curve |
| `TestFieldFlatnessExample` | 2 | Single metric envelope, full multi-metric envelope |
| `TestEnvelope` | 3 | Limiting metrics, missing rule, default rule |
| `TestGlobalSafety` | 2 | No factory/recovery imports, no JSONL/Excel |

**Total: 22 tests** (79 across TSE2+TSE3+TSE4)

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao/tolerance_sweep_recommendation.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_tolerance_sweep_dataset.py tests/workflows/test_rfgun_sao_tolerance_sweep_analysis.py tests/workflows/test_rfgun_sao_tolerance_sweep_recommendation.py -q
-- 79 passed in 0.21s
```

### Artifact grep

```
git ls-files | Select-String -Pattern "config.local.yaml|\.sqlite$|\.db$|\.db-shm$|\.db-wal$|\.jsonl$|\.ckpt$|workflow_1_runtime\.log|workflow_3_runtime\.log|\.claude/settings.local.json|\.cst$"
-- No forbidden artifacts tracked.
```

---

## Known limitations (deferred)

| Limitation | Phase |
|------------|-------|
| Sweep CLI / markdown/JSON report | TSE5 |
| Bounded live sweep | TSE-LIVE1 (requires explicit approval) |

---

## Explicit statements

| Item | Status |
|------|--------|
| Live CST | **No** |
| Runtime behavior changed | **No** |
| Default config changed | **No** |
| Generated artifacts committed | **No** |
| JSONL/Excel source | **No** |
| Factory/recovery imports | **No** |

---

## Patch notes (TSE4 hardening)

| Change | Description |
|--------|-------------|
| Non-finite threshold inputs | NaN/inf values now produce `unknown` status instead of incorrectly remaining `pass` |
| Warning/unknown stops expansion | First warning or unknown blocks further `last_valid_pass` updates; later pass levels no longer expand the recommended max |
| Reason summaries enhanced | Non-finite value reasons (e.g. `"mean is non-finite for max_mean"`) included in level decisions and recommendation summary |
| Tests added | 8 new tests covering `evaluate_metric_level` non-finite handling and `recommend_metric_tolerance` warning/unknown blocking (30 total) |
| `BRANCH_CONTEXT.md` updated | TSE1–TSE5 + TSE-LIVE1 track table added |
| Baseline delta non-finite | `unknown` returned when baseline or current mean is non-finite for delta rules |
| No thresholds configured | Returns `unknown` with reason `"no evaluable thresholds configured"` |

**Validation:**
```powershell
python -m pytest tests/workflows/test_rfgun_sao_tolerance_sweep_recommendation.py -q
-- 30 passed in 0.10s

python -m compileall workflows/rfgun_sao/tolerance_sweep_recommendation.py
-- Compiles OK.
```

Runtime behavior, default config, and CST unchanged.

---

## Final recommendation

**Accepted.** TSE4 provides threshold-based recommendation rules for tolerance
envelope analysis: per-metric evaluation, recommended max tolerance, and
overall envelope with limiting metrics.  TSE5 (sweep CLI) can proceed.
