# Phase B4 — Report-only diagnostic extraction skeleton (no-CST)

## Summary

Add report-only diagnostic extraction helpers to the metrics layer, wire
diagnostics into ``Workflow1Evaluator`` and ``EvaluationResult``, and
extend ``EvaluationResult`` with an optional ``diagnostics`` field.
No live CST was run; no checkpoint arrays were changed.

## Scope

- **no-CST report_only diagnostic skeleton** — pure helper + evaluator
  wiring + ``EvaluationResult.diagnostics`` field.
- **No JSONL sidecar**, no gate role, no checkpoint objective array changes.
- **No change to ``evaluate_single_pass`` return tuple shape** — diagnostics
  are stored as an instance attribute (``_last_diagnostics``) and surfaced
  via ``adapt_for_retry`` → ``EvaluationResult.diagnostics``.

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/metrics.py`` | Added ``report_only_diagnostics`` (duplicate-key detection, finite/non-finite handling) and ``report_only_output_names`` (report_as or source name) |
| ``workflows/rfgun_sao/types.py`` | Added ``diagnostics: dict[str, Any] \| None = None`` field to ``EvaluationResult`` |
| ``workflows/rfgun_sao/evaluator.py`` | Added ``report_only_diagnostics`` import; compute ``_last_diagnostics`` after penalties; include in ``adapt_for_retry`` return; initialize ``_last_diagnostics`` in ``__init__`` |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section X with 8 B4 tests |
| ``reports/restructure_plan/phase_B4_report_only_diagnostic_skeleton.md`` | Created (this file) |

## Production code changed

- **metrics.py**: ~60 lines (pure helpers).
- **types.py**: 2 lines (field + docstring).
- **evaluator.py**: 10 lines (import, init, computation call, adapt_for_retry
  integration).

All changes are backward-compatible:
- ``EvaluationResult()`` still works (``diagnostics`` defaults to ``None``).
- ``evaluate_single_pass`` return tuple unchanged.
- ``Workflow1Evaluator`` constructed without ``metric_specs`` still works
  (flat optimize fallback).

## Semantics

### Report-only diagnostics

| Aspect | Behavior |
|--------|----------|
| Source | ``raw_metrics`` (no extra CST computation) |
| Output key | ``spec.report_as`` if set, else ``spec.name`` |
| Finite raw value | ``float(value)`` |
| Missing / non-finite raw | ``numpy.nan`` |
| Disabled specs | excluded |
| Duplicate output keys | ``ValueError`` with ``"Duplicate report_only diagnostic key"`` |
| Penalty dict | report_only metrics **not** included (unchanged from B1–B3) |
| ``report_metric_names(specs)`` | still returns source names (unchanged) |

### ``EvaluationResult.diagnostics``

| Scenario | Value |
|----------|-------|
| ``metric_specs`` with report_only specs, finite raw | ``{"key": value, ...}`` |
| ``metric_specs`` with no report_only specs | ``{}`` (empty dict) |
| ``metric_specs=None`` (flat fallback) | ``{}`` |
| Exception during evaluation | ``{}`` (preserved from init) |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "report_only_diagnostic or b4_" -v --tb=short
7/7 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
142/142 passed (full suite)
```

## Live CST

- **Live CST run:** no
- **CST window closed:** N/A — no CST launched

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by B4 | no |

## Commit hashes

- B4 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- **Report-only diagnostics are surfaced via ``EvaluationResult.diagnostics``**
  but are **not persisted** to any sidecar (``.ckpt`` records do not include
  ``diagnostics``).  A future JSONL sidecar phase could persist them.
- **Live CST validation** of report-only diagnostics still future.
- **Gate role** still future.
- **Suggested B5 direction:** Live CST smoke with role-based metrics
  (threshold penalty + report_only diagnostics), or README milestone update.
