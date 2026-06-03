# Phase B2 — Threshold penalty skeleton (no-CST)

## Summary

Extend the B1 metric roles skeleton with threshold penalty formula support:
``MetricSpec`` now carries ``threshold``/``sigma``/``direction``/``report_as``
fields, a ``compute_threshold_penalty`` pure function implements the legacy
Workflow 3 formula, and the workflow container exposes ``metric_specs``,
``optimize_metric_names``, and ``threshold_metric_names``.

No live CST was run; no threshold penalty is wired into the live evaluator.

## Scope

- **no-CST threshold penalty formula skeleton** — parser, pure function,
  container metadata only.
- **No wiring into live evaluator** — threshold penalty is not yet called
  during ``evaluate_single_pass``.
- **No JSONL sidecar**, no gate role, no report_only live extraction.

## B1 caveats addressed

| B1 caveat | B2 status |
|-----------|-----------|
| Threshold role only classification, no formula | ✅ ``compute_threshold_penalty`` with legacy less_than/greater_than formula |
| MetricSpec missing threshold/sigma/direction/report_as | ✅ Fields added with top-level + ``mode_params`` fallback parsing |
| ``normalize_metric_role`` name not present | ✅ ``normalize_metric_role`` alias added |

## B1 caveats still open

- **Report_only live extraction** — not implemented (future).
- **Gate role** — not implemented (future).
- **JSONL sidecar** — not implemented (future).

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/metrics.py`` | Extended ``MetricSpec`` with threshold fields; added ``_validate_direction``, ``_resolve_threshold_field``, ``normalize_metric_role``, ``compute_threshold_penalty``, ``_safe_sigma``, ``optimize_metric_names``, ``threshold_metric_names`` |
| ``workflows/rfgun_sao/workflow.py`` | Updated import; added ``metric_specs``, ``optimize_metric_names``, ``threshold_metric_names`` to both containers |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section V with 10 B2 tests |
| ``reports/restructure_plan/phase_B2_threshold_penalty_skeleton.md`` | Created (this file) |

## Production code changed

**Parser/pure-function/container-metadata only.**  No evaluator, checkpoint,
or two-pass orchestration code was changed.

- ``metrics.py``: 150 lines added (pure functions, field parsing, validation).
- ``workflow.py``: 6 lines added (imports + 3 container attributes per branch).

## Semantics

- **``objective_names``** = optimize + threshold (unchanged from B1).
- **``report_metric_names``** = report_only (unchanged).
- **``metric_specs``** = full spec list (new).
- **``optimize_metric_names`` / ``threshold_metric_names``** = role-filtered (new).

### Threshold penalty formula

| Condition | Penalty |
|-----------|---------|
| ``direction="less_than"``, ``value ≤ threshold`` | ``0.0`` |
| ``direction="less_than"``, ``value > threshold`` | ``1.0 - exp(-(value - threshold) / sigma)`` |
| ``direction="greater_than"``, ``value ≥ threshold`` | ``0.0`` |
| ``direction="greater_than"``, ``value < threshold`` | ``1.0 - exp(-(threshold - value) / sigma)`` |
| Non-finite value | ``1.0`` |
| ``sigma`` missing / non-finite | default ``1.0`` |
| ``sigma`` clamped to | ``max(abs(sigma), 1e-12)`` |
| Invalid direction at parse time | ``ValueError`` with ``"Unknown threshold direction"`` |
| ``compute_threshold_penalty`` on non-THRESHOLD spec | ``TypeError`` with ``"Expected role threshold"`` |

### ``report_as`` handling

The ``report_as`` field is parsed and stored in ``MetricSpec`` but **not yet
wired** into any output-name resolution. ``objective_metric_names`` and
related helpers still return the source ``name``. Output-alias wiring is
deferred to a future phase.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "threshold_penalty or normalize_metric_role or backward_compatibility" -v --tb=short
7/7 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
126/126 passed (full suite)
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

## Commit hashes

- B2 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- **Threshold penalty is not wired into the live evaluator** — integration
  with ``Workflow1Evaluator`` or the two-pass measurement runner remains
  for a future phase (B3 or later).
- **Report_only live extraction** still future.
- **Gate role** still future.
- **JSONL sidecar** still future.
- **Suggested B3 direction:** Wire threshold penalty into the single-pass
  evaluator or two-pass measurement runner, or implement report_only
  diagnostic extraction, depending on priority.
