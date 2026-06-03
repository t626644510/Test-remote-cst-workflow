# Phase I1 — Stage runtime wiring semantics hardening

## Summary

Fix three semantic issues in Phase I stage runtime wiring: adaptive
config parameter propagation, BLOCK_STAGE_SHRINK non-transition handling,
and tightened test assertions.  No CST, no evaluation database, no
retry/recovery, no root shim repoint.

## Base commit

``d6713ed07c347d087d871759b103f8eaf420ef51`` (Phase H accepted HEAD)

## Reviewed Phase I commit

``37f5bc70cd55eea88b0b6d12633c7c4541caf203`` (requires I1 polish)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/stage_adaptive_policy.py`` | Added ``proximity_fraction`` parameter to ``combine_stage_and_adaptive_decisions``; propagated ``expand_fraction`` and ``proximity_fraction`` through ``_handle_stage_shrink``/``_handle_adaptive_review`` into ``recommend_adaptive_bounds`` |
| ``workflows/rfgun_sao/stage_runtime.py`` | Pass ``proximity_fraction`` from ``adaptive_cfg``; removed ``BLOCK_STAGE_SHRINK`` from transition-update path — block-shrink no longer advances stage or clears observations |
| ``tests/workflows/test_rfgun_sao_stage_adaptive_policy.py`` | Added 2 tests: custom ``expand_fraction`` affects expansion amount; custom ``proximity_fraction`` affects clipping decision |
| ``tests/workflows/test_rfgun_sao_stage_runtime.py`` | Tightened 11 tests: best-near-boundary deterministically asserts ``USE_ADAPTIVE_BOUNDS``; high fail/reject asserts stage decision is RECENTER/SHIFT; shrink-without-evidence checks shrink is not SHRINK; block-shrink tests stage/observations retention; min-span test asserts SHRINK blocked; config defaults verified |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | I → Reviewed / needs I1 polish; added I1 row |

## Design decisions

### Adaptive config propagation

``combine_stage_and_adaptive_decisions`` now accepts both
``expand_fraction`` and ``proximity_fraction`` and passes them through
the internal handler chain into ``recommend_adaptive_bounds``.
``maybe_update_stage_bounds`` reads both from ``adaptive_cfg``.
Tests confirm that custom values affect expansion amount and clipping
decisions.

### BLOCK_STAGE_SHRINK non-transition

Previously, ``BLOCK_STAGE_SHRINK`` was treated as a stage transition:
bounds were updated, stage counter incremented, and observations cleared.
Now it is **not** a transition: ``current_bounds`` remain unchanged,
``current_stage`` is not incremented, and observations are retained for
continued evaluation in the same stage.

### Tightened test assertions

- ``best_near_boundary_deterministically_uses_adaptive`` now asserts
  ``USE_ADAPTIVE_BOUNDS`` unconditionally when adaptive is enabled and
  clipping is present.
- High-calibration-fail and high-gate-reject tests now check
  ``last_stage_decision.action`` is ``RECENTER`` or ``SHIFT``, not
  ``SHRINK``.
- ``test_min_span_blocks_shrink_when_tight`` asserts ``SHRINK`` is
  blocked when reference span is large relative to current span.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_stage_adaptive_policy.py --tb=short
18/18 passed

$ pytest tests/workflows/test_rfgun_sao_stage_runtime.py --tb=short
17/17 passed

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short
32/32 passed

$ pytest tests/workflows/test_rfgun_sao_adaptive_bounds.py --tb=short
33/33 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

Total: **340/340 passed**.

## Explicit statements

- **No CST run.**
- **No live CST runtime validation.**
- **No evaluation database implementation.**
- **No retry/recovery implementation.**
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
| ``.claude/settings.local.json`` modified by Phase I1 | no |

## Commit hashes

- Phase I1 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
