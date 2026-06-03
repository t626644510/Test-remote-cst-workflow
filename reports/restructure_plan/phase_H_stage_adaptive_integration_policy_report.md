# Phase H — Stage + adaptive integration policy

## Summary

Implement stage search + adaptive bounds integration policy: a new
``stage_adaptive_policy.py`` module composes stage transition decisions
with adaptive bounds review to produce a single final bounds/action
recommendation.  No runtime wiring, no CST, no evaluation database.

## Base commit

``2e2bca7d0c81ab75c3cd1b9e4fc577ed5fda1506`` (Phase G1 accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/stage_adaptive_policy.py`` | New — integration policy with ``combine_stage_and_adaptive_decisions``, ``build_adaptive_input_from_stage_decision``, ``extract_high_quality_points`` |
| ``tests/workflows/test_rfgun_sao_stage_adaptive_policy.py`` | New — 16 no-CST tests covering all integration paths |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | G/G1 → Accepted; added H row |

## Integration semantics

| Stage action | Adaptive called? | Adaptive result | Final action |
|-------------|-----------------|-----------------|-------------|
| STOP | No | — | STOP |
| CONTINUE_CURRENT | No | — | CONTINUE_CURRENT |
| RECENTER / SHIFT | No | — | USE_STAGE_DECISION (preserve intent) |
| SHRINK | Yes | PERMIT_SHRINK | USE_STAGE_DECISION (stage bounds) |
| SHRINK | Yes | ASYMMETRIC/SYMMETRIC_EXPAND | USE_ADAPTIVE_BOUNDS (adaptive bounds) |
| SHRINK | Yes | BLOCK_SHRINK | BLOCK_STAGE_SHRINK (current bounds) |
| SHRINK | Yes | Insufficient evidence / other | USE_STAGE_DECISION (fallback) |
| REQUEST_ADAPTIVE_REVIEW | Yes | Expansion | USE_ADAPTIVE_BOUNDS |
| REQUEST_ADAPTIVE_REVIEW | Yes | No change / other | USE_STAGE_DECISION (current bounds) |

### Anti-clipping semantics

When adaptive expansion is applied, only the clipped parameters' affected
sides are expanded (per-parameter from G1).  The expansion is a partial
relaxation of proposed bounds, not a guarantee that all best/high-quality
evidence is re-included.  This is documented and reflected in diagnostics.

## Validation

```
$ python -m compileall workflows/rfgun_sao/stage_search.py workflows/rfgun_sao/adaptive_bounds.py workflows/rfgun_sao/stage_adaptive_policy.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short
32/32 passed

$ pytest tests/workflows/test_rfgun_sao_adaptive_bounds.py --tb=short
33/33 passed

$ pytest tests/workflows/test_rfgun_sao_stage_adaptive_policy.py --tb=short
16/16 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

Total: 306/306 passed.

## Explicit statements

- **No CST run.**
- **No runtime wiring.**
- **No stage runtime integration.**
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
| ``.claude/settings.local.json`` modified by Phase H | no |

## Commit hashes

- Phase H implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
