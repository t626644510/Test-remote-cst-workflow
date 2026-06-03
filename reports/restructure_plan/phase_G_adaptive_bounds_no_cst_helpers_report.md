# Phase G — Adaptive bounds no-CST helpers

## Summary

Implement adaptive bounds no-CST helper skeleton: boundary/quality
detection, symmetric/asymmetric expansion, center shift, min-step
clamping, and the main ``recommend_adaptive_bounds`` policy in a new
``workflows/rfgun_sao/adaptive_bounds.py`` module.  No runtime wiring,
no CST, no evaluation database.

## Base commit

``935231c9c6368f4a9b6fdb87d54d758116e82fea`` (Phase F1 accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/adaptive_bounds.py`` | New — adaptive bounds helper module with input/recommendation dataclasses, boundary detection, expansion/shift helpers, main review policy |
| ``tests/workflows/test_rfgun_sao_adaptive_bounds.py`` | New — 22 no-CST tests covering all helpers and policy branches |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | F/F1 → Accepted; added G; cleaned stale next directions |

## Module contents

| Component | Description |
|-----------|-------------|
| ``AdaptiveBoundsAction`` | Enum: ``NO_CHANGE``, ``SYMMETRIC_EXPAND``, ``ASYMMETRIC_EXPAND``, ``SHIFT_CENTER``, ``BLOCK_SHRINK``, ``PERMIT_SHRINK``, ``STOP_INSUFFICIENT_EVIDENCE`` |
| ``AdaptiveBoundsInput`` | Input dataclass with validation, ``validate_proposed()`` |
| ``AdaptiveBoundsRecommendation`` | Output dataclass with action, reason, bounds, diagnostics |
| ``detect_best_boundary_clipping`` | Check if best candidate is near bounds while proposed is shrinking |
| ``detect_quality_boundary_clustering`` | Check if high-quality points cluster near bounds |
| ``clamp_to_hard_bounds_and_min_step`` | Clamp bounds to hard limits; enforce min step |
| ``apply_symmetric_expand`` | Expand both sides, clamped to hard bounds |
| ``apply_asymmetric_expand`` | Expand specified sides only |
| ``apply_center_shift`` | Shift proposed center while preserving span |
| ``recommend_adaptive_bounds`` | Main review policy (insufficient evidence → anti-clipping → clustering → permit shrink → no change) |

## Policy priority

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | No best_x or high_quality points | ``STOP_INSUFFICIENT_EVIDENCE`` |
| 2 | Best near low boundary + proposed shrinking | ``ASYMMETRIC_EXPAND`` (low side) |
| 3 | Best near high boundary + proposed shrinking | ``ASYMMETRIC_EXPAND`` (high side) |
| 4 | Both sides clipped + shrinking | ``SYMMETRIC_EXPAND`` or ``BLOCK_SHRINK`` (no room) |
| 5 | Quality points clustered near boundary | ``ASYMMETRIC_EXPAND`` or ``SYMMETRIC_EXPAND`` |
| 6 | Safe shrink (centered, no clipping) | ``PERMIT_SHRINK`` |
| 7 | Not shrinking, no clipping | ``NO_CHANGE`` |

## Validation

```
$ python -m compileall workflows/rfgun_sao/adaptive_bounds.py tests/workflows/test_rfgun_sao_adaptive_bounds.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_adaptive_bounds.py --tb=short -v
22/22 passed

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short
32/32 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

Total: 273/273 passed.

## Explicit statements

- **No CST run.**
- **No runtime wiring** — adaptive_bounds.py is pure helpers only.
- **No stage runtime integration.**
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
| ``.claude/settings.local.json`` modified by Phase G | no |

## Commit hashes

- Phase G implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
