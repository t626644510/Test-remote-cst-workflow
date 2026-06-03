# Phase F1 — Stage search helper semantics hardening

## Summary

Fix three semantic issues in Phase F ``stage_search.py`` and add 7 focused
no-CST regression tests.  No runtime wiring, no CST, no adaptive bounds,
no evaluation database.

## Base commit

``e019c1c4d1294c9048085dc05040ec212ad148bf`` (Phase E accepted HEAD)

## Reviewed Phase F commit

``4cc3b7b9f75c7f45908d8669667311f9abd68b8c`` (requires F1 polish)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/stage_search.py`` | Fixed min-span logic (``reference_span`` parameter); fixed database-reused accounting (also check ``status == DATABASE_REUSED``); fixed rate clamp (``min(..., 1.0)``) |
| ``tests/workflows/test_rfgun_sao_stage_search.py`` | Added 7 F1 tests (TestF1DatabaseReused 2×, TestF1MinSpan 2×, TestF1HighFailRate 2×, TestF1BoundaryReview 1×) |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | F → Reviewed / needs F1 polish; added F1 row |
| ``reports/restructure_plan/phase_F1_stage_search_helper_semantics_hardening_report.md`` | Created (this file) |

## Design decisions

### Min-span semantics

- ``decide_stage_transition`` now accepts an optional ``reference_span``
  (``np.ndarray``).  If not provided, falls back to ``bounds.span``
  (backward-compatible).
- ``min_span = reference_span * min_span_fraction``.
- If ``bounds.span < min_span`` for any parameter, ``SHRINK`` is blocked.
  The current fallback action is ``CONTINUE_CURRENT`` (or the appropriate
  action for whatever other trigger fires next).

### Database reused semantics

- ``summarize_stage_observations`` counts an observation as reused if
  ``o.reused is True`` **or** ``o.status == DATABASE_REUSED``.
- ``actual_cst_solves_count = proposed - database_reused_count``.
- ``valid_completed_rate`` and ``reject_failure_rate`` use
  ``actual_cst_solves`` as denominator, clamped to ``[0.0, 1.0]``.
- ``DATABASE_REUSED`` with finite objective/raw evidence is counted as
  completed for warm-start purposes, but not as a CST solve.

### Rate denominator

- Solve-rate metrics (``valid_completed_rate``, ``reject_failure_rate``)
  use ``actual_cst_solves_count`` as denominator (non-reused observations
  only).  This avoids rate inflation from database hits.
- Rates are clamped to ``[0.0, 1.0]``.

## Validation

```
$ python -m compileall workflows/rfgun_sao/stage_search.py tests/workflows/test_rfgun_sao_stage_search.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short -v
32/32 passed (25 F + 7 F1)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed
```

## Explicit statements

- **No CST run.**
- **No runtime wiring.**
- **No adaptive bounds implementation.**
- **No evaluation database implementation.**
- **No root shim repoint.**

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase F1 | no |

## Commit hashes

- Phase F1 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
