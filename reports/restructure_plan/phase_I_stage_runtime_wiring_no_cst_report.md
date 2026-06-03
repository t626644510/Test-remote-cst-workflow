# Phase I — Stage runtime wiring no-CST

## Summary

Add opt-in stage/adaptive runtime wiring with ``StageRuntimeState``,
``record_stage_observation``, ``maybe_update_stage_bounds``, and config
resolution helpers.  Disabled by default.  No CST, no evaluation database,
no retry/recovery, no root shim repoint.

## Base commit

``d6713ed07c347d087d871759b103f8eaf420ef51`` (Phase H accepted HEAD)

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/stage_runtime.py`` | New — runtime state, observation recording, bounds update, config helpers |
| ``tests/workflows/test_rfgun_sao_stage_runtime.py`` | New — 17 no-CST tests covering config, disabled, completed, high-fail, reference-span, observation-recording |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | H → Accepted; added I; updated next directions to J/K/L |

## Design decisions

### Opt-in config semantics

| Config key | Default | Effect |
|-----------|---------|--------|
| ``optimization.stage_search.enabled`` | ``false`` | When ``false``, stage search is completely no-op. |
| ``optimization.stage_search.max_stages`` | ``5`` | Max stage transitions before ``STOP``. |
| ``optimization.stage_search.min_completed_fraction`` | ``0.3`` | Minimum completed fraction for shrink. |
| ``optimization.stage_search.high_fail_rate`` | ``0.5`` | Threshold triggering recenter/shift. |
| ``optimization.adaptive_bounds.enabled`` | ``false`` | When ``false``, stage decisions are used directly. |
| ``optimization.adaptive_bounds.expand_fraction`` | ``0.1`` | Expansion fraction for anti-clipping. |

### Shrink-without-evidence protection

``maybe_update_stage_bounds`` delegates to ``decide_stage_transition``
which handles "no useful evidence" via ``CONTINUE_CURRENT``.  The runtime
wiring does not perform shrink when completed/best evidence is
unavailable.

### JSONL sidecar remains separate

The C-phase JSONL sidecar is not read by stage runtime logic.
``resolve_stage_search_config`` and ``resolve_adaptive_bounds_config``
only read ``optimization.*`` keys.

### Phase H caveats handled

- SHRINK without best evidence: ``decide_stage_transition`` returns
  ``CONTINUE_CURRENT`` when no completed observations exist.
- Reference span is explicitly passed to ``decide_stage_transition``,
  so min-span comparison uses initial span, not current span.

## Validation

```
$ python -m compileall workflows/rfgun_sao/stage_runtime.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_stage_runtime.py --tb=short -v
17/17 passed

$ pytest tests/workflows/test_rfgun_sao_stage_adaptive_policy.py --tb=short
16/16 passed

$ pytest tests/workflows/test_rfgun_sao_adaptive_bounds.py --tb=short
33/33 passed

$ pytest tests/workflows/test_rfgun_sao_stage_search.py --tb=short
32/32 passed

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
229/229 passed

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
```

Total: 322/322 passed.

## Explicit statements

- **No CST run.**
- **No live CST runtime validation.**
- **No evaluation database implementation.**
- **No retry/recovery implementation.**
- **No root shim repoint.**
- **Default config does not enable stage search or adaptive bounds** (verified by ``test_default_config_not_enabled``).

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| Generated artifacts committed | no |
| ``.claude/settings.local.json`` modified by Phase I | no |

## Commit hashes

- Phase I implementation/report commit: reported in final execution message
- Final pushed HEAD: reported in final execution message
