# Phase B3 — Threshold penalty runtime wiring (no-CST)

## Summary

Wire the B2 ``compute_threshold_penalty`` pure function into the
``Workflow1Evaluator`` runtime penalty computation path via a new
``compute_role_penalties`` helper.  Also fix direction validation to
only reject invalid directions for threshold-role metrics (non-threshold
roles may carry arbitrary direction strings without failing).

No live CST was run.

## Scope

- **no-CST runtime penalty wiring** — penalty computation in
  ``Workflow1Evaluator.evaluate_single_pass`` now uses
  ``compute_role_penalties``.
- **Direction validation fix** — ``build_metric_specs`` only validates
  direction for ``THRESHOLD`` role.
- **No JSONL sidecar**, no report_only live extraction, no gate role.

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/metrics.py`` | Added ``compute_role_penalties``; fixed direction validation in ``build_metric_specs`` to only apply for threshold role |
| ``workflows/rfgun_sao/evaluator.py`` | Added ``metric_specs`` parameter to ``__init__`` with fallback flat-optimize specs; replaced hard-coded penalty loop with ``compute_role_penalties`` call |
| ``workflows/rfgun_sao/workflow.py`` | Pass ``metric_specs=specs`` to both ``Workflow1Evaluator`` constructor calls (two-pass CST and single-pass) |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section W with 8 B3 tests |
| ``reports/restructure_plan/phase_B3_threshold_penalty_runtime_wiring.md`` | Created (this file) |

## Production code changed

- **metrics.py**: ``compute_role_penalties`` (pure function, no CST dependency)
  + 4-line direction-validation condition.
- **evaluator.py**: 7 lines for ``__init__`` param + fallback; 3 lines
  replacing penalty loop with helper call.
- **workflow.py**: 2 lines (``metric_specs=specs`` in two constructor calls).

## Semantics

| Role | Penalty source | In penalty dict |
|------|---------------|----------------|
| ``optimize`` | ``obj.mode.compute(value)`` (unchanged) | yes |
| ``threshold`` | ``compute_threshold_penalty(spec, value)`` | yes |
| ``report_only`` | skipped | no |
| Missing / non-finite raw | 1.0 (any role) | yes (for optimize/threshold) |

### Direction validation change

| Scenario | Before B3 | After B3 |
|----------|-----------|----------|
| ``threshold`` role, ``direction="sideways"`` | ``ValueError`` | ``ValueError`` (unchanged) |
| ``optimize`` role, ``direction="sideways"`` | ``ValueError`` | **Allowed** (no effect on computation) |

### Fallback behavior (no metric_specs provided)

If ``Workflow1Evaluator`` is constructed without ``metric_specs``
(e.g. external callers not updated yet), it synthesizes flat optimize
specs from ``metric_names``, preserving backward compatibility.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "role_penalt or b3_ or direction_validation" -v --tb=short
8/8 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
134/134 passed (full suite)
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
| ``.claude/settings.local.json`` modified by B3 | no |

## Commit hashes

- B3 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- **Live CST validation** of threshold penalty wiring still future.
- **Report_only live extraction** still future.
- **Gate role** still future.
- **JSONL sidecar** still future.
- **Suggested B4 direction:** Live CST smoke with threshold role metrics,
  or report_only extraction, or another topic.
