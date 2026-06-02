# Phase B7 — Gate metric role skeleton (no-CST)

## Summary

Add a minimal local ``gate`` metric role skeleton to ``workflows/rfgun_sao``
without wiring runtime rejection.  The gate role is now parsed, exposed as
``gate_metric_names`` on workflow containers, and pure pass/fail helpers
(``compute_gate_pass``, ``compute_gate_results``) are provided.  Gate
metrics are excluded from ``objective_names``, checkpoint arrays, and
``compute_role_penalties`` — they must not affect the scalar objective
until a future phase wires rejection.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/metrics.py`` | Added ``GATE`` to ``MetricRole``; added ``gate_metric_names``, ``compute_gate_pass``, ``compute_gate_results``; updated direction validation for gate; excluded gate from ``compute_role_penalties`` |
| ``workflows/rfgun_sao/workflow.py`` | Added ``gate_metric_names`` import; added ``workflow.gate_metric_names = gate_metric_names(specs)`` to both containers |
| ``workflows/rfgun_sao/README.md`` | Added "Gate role runtime enforcement" to future work |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added B7 to Phase B table; added gate to authoritative behaviour; updated caveats and next directions |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AB with 15 B7 tests; added ``B7`` to README assertion |
| ``reports/restructure_plan/phase_B7_gate_role_skeleton.md`` | Created (this file) |

## Gate role semantics implemented

| Aspect | Behaviour |
|--------|-----------|
| Role acceptance | ``MetricRole.GATE``, ``normalize_metric_role("gate")`` returns ``"gate"`` |
| Direction validation | Validated for gate (same as threshold): ``"less_than"`` or ``"greater_than"`` |
| ``objective_metric_names`` | Excludes gate |
| ``report_metric_names`` | Excludes gate |
| ``gate_metric_names`` | Returns enabled gate source names |
| ``compute_role_penalties`` | Skips gate (same as report_only) |
| ``compute_gate_pass(spec, value)`` | Pure pass/fail; requires ``role==GATE``; non-finite value → ``False``; missing threshold → ``False`` |
| ``compute_gate_results`` | Dict of gate results by output key (``report_as`` or name); duplicate keys → ``ValueError`` |
| Runtime rejection | **Not wired** — no candidate is rejected based on gate results yet |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "gate or role_penalt" -v --tb=short
45/45 passed (targeted — includes all B7 gate tests + existing gate tests)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
173/173 passed (full suite)
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
| ``.claude/settings.local.json`` modified by B7 | no |

## Commit hashes

- B7 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- **Gate role runtime rejection is not yet wired.**  ``compute_gate_results``
  returns pass/fail values, but no candidate is rejected based on them.
  A future phase (B8 or later) could wire gate rejection into the two-pass
  decision path.
- Gate does not affect the scalar objective, checkpoint arrays, or
  ``compute_role_penalties`` in this phase.
- JSONL sidecar, gate runtime enforcement, and Ctrl+C hardening remain
  future work.
- Next possible direction: gate role runtime rejection wiring.
