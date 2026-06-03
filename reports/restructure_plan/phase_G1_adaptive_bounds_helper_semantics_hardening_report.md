# Phase G1 — Adaptive bounds helper semantics hardening

## Summary

Fix four semantic issues in Phase G ``adaptive_bounds.py`` and add 11
focused no-CST regression tests.  No runtime wiring, no CST, no
evaluation database.

## Base commit

``935231c9c6368f4a9b6fdb87d54d758116e82fea`` (Phase F1 accepted HEAD)

## Reviewed Phase G commit

``c64fedf7e0913b2abf09b6e44cd42bc0f989011b`` (requires G1 polish)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/adaptive_bounds.py`` | Per-parameter clipping detection; affected-param-only asymmetric expansion via new ``apply_asymmetric_expand_for_params``; comprehensive input validation (best_x length, high_quality_points length, hard bounds ordering, current bounds within hard, min_step positive); quality clustering threshold (``min_cluster_count=2``) |
| ``tests/workflows/test_rfgun_sao_adaptive_bounds.py`` | 33 tests (22 Phase G + 11 G1 regression) covering per-param clipping, affected-param expansion, validation, clustering threshold, no-room scenarios |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | G → Reviewed / needs G1 polish; added G1 row |

## Design decisions

### Per-parameter clipping

Previously, clipping was a global boolean (any parameter shrinking + any
parameter near boundary).  Now ``detect_best_boundary_clipping`` computes
``params_clipped_lo`` and ``params_clipped_hi`` per parameter: a param
is clipped on a side only when its best point is near that side **and**
that side's proposed bound moves inward.

### Affected-param-only expansion

New ``apply_asymmetric_expand_for_params`` helper expands only the
specific parameters listed in ``expand_low_params`` / ``expand_high_params``.
Parameters not listed retain their proposed bounds.  ``recommend_adaptive_bounds``
uses this to expand only the clipped params/sides.

### No-room / block-shrink

If a clipped side has no room to expand (hard bounds = proposed bound),
``_recommend_anti_clipping_by_param`` returns ``BLOCK_SHRINK`` with
clear diagnostics listing which params are blocked.

### Quality clustering threshold

``detect_quality_boundary_clustering`` now requires at least
``min_cluster_count`` distinct points (default 2) within the cluster
fraction to trigger.  A single near-boundary outlier no longer triggers
cluster-based expansion.

### Input validation

Added checks:
- ``best_x`` length must equal ``param_names`` length.
- Each ``high_quality_points[i]`` length must equal ``param_names``.
- ``hard_low < hard_high`` for all params.
- ``current_low < current_high``.
- ``current`` bounds must be within ``hard`` bounds.
- ``min_step > 0``.

## Validation

```
$ python -m compileall workflows/rfgun_sao/adaptive_bounds.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_adaptive_bounds.py --tb=short -v
33/33 passed

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
- **No runtime wiring.**
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
| ``.claude/settings.local.json`` modified by Phase G1 | no |

## Commit hashes

- Phase G1 implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
