# Phase F — Stage search no-CST helpers

## Summary

Implement stage search no-CST helper skeleton: dataclasses, aggregation
functions, feasibility-aware transition policy, and bound manipulation
helpers in a new ``workflows/rfgun_sao/stage_search.py`` module.
No runtime wiring, no adaptive bounds, no evaluation database, no CST.

## Base commit

``e019c1c4d1294c9048085dc05040ec212ad148bf`` (Phase E accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/stage_search.py`` | New — stage search helper module with dataclasses, policy helpers, bounds manipulation |
| ``tests/workflows/test_rfgun_sao_stage_search.py`` | New — 25 no-CST tests covering all helpers and policy rules |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Phase E → Accepted; added Phase F row |

## Module contents

| Component | Description |
|-----------|-------------|
| ``StageCandidateStatus`` | Enum: ``COMPLETED``, ``GATE_REJECTED``, ``CALIBRATION_FAILED``, ``SOLVER_FAILED``, ``TRANSIENT_FAILED``, ``UNKNOWN_FAILED``, ``DATABASE_REUSED`` |
| ``StageObservation`` | Per-candidate evaluation record |
| ``StageBounds`` | Parameter bounds with validation (low/high, optional hard_low/hard_high) |
| ``StageSummary`` | Aggregate stats with accounting fields |
| ``StageTransitionAction`` | Enum: ``CONTINUE_CURRENT``, ``RECENTER``, ``SHIFT``, ``SHRINK``, ``REQUEST_ADAPTIVE_REVIEW``, ``STOP`` |
| ``StageTransitionDecision`` | Transition recommendation with reason and proposed bounds |
| ``summarize_stage_observations`` | Aggregate observations → ``StageSummary`` |
| ``select_best_completed`` | Best objective from completed candidates |
| ``select_most_feasible_point`` | Most feasible point (completed > gate-rejected > cal-failed > first) |
| ``detect_boundary_proximity`` | Check if best point is near bounds |
| ``decide_stage_transition`` | Feasibility-aware transition policy |
| ``make_recentered_bounds`` | Recenter around a candidate point |
| ``make_shrunk_bounds`` | Shrink bounds (delegates to recentered for now) |

## Policy rules implemented

| Priority | Rule | Action |
|----------|------|--------|
| 1 | Max stages reached | ``STOP`` |
| 2 | No useful evidence | ``CONTINUE_CURRENT`` |
| 3 | High calibration/solver fail rate | ``RECENTER`` or ``SHIFT`` (never shrink) |
| 4 | High gate reject rate | ``RECENTER`` or ``SHIFT`` (never blind shrink) |
| 5 | Best near boundary with sufficient completed | ``REQUEST_ADAPTIVE_REVIEW`` (block shrink) |
| 6 | Stable feasible region, sufficient completed, no boundary clip | ``SHRINK`` |
| 7 | Insufficient completed fraction | ``CONTINUE_CURRENT`` |
| 8 | Catch-all | ``CONTINUE_CURRENT`` |

## Explicit statements

- **No CST run.**
- **No runtime wiring** — stage_search.py is pure helpers only.
- **No adaptive bounds implementation** — boundary clipping returns ``REQUEST_ADAPTIVE_REVIEW`` instead of expanding.
- **No evaluation database implementation** — ``DATABASE_REUSED`` is accounting only.
- **No root shim repoint.**

## Validation

```
$ python -m compileall workflows/rfgun_sao/stage_search.py tests/workflows/test_rfgun_sao_stage_search.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short -v
25/25 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase F | no |

## Commit hashes

- Phase F implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
