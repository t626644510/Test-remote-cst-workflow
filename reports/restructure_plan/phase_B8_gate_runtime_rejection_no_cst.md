# Phase B8 — Gate role runtime rejection wiring (no-CST)

## Summary

Wire gate metric role runtime candidate rejection into the two-pass
runtime evaluator.  After a successful measurement, enabled gate specs
are evaluated via ``compute_gate_results``; if any gate fails, the
candidate receives all-ones penalties, ``solver_ok=False``, and a stable
``"gate_reject:key1,key2"`` error in the checkpoint.  Gate metrics remain
excluded from ``objective_names`` and checkpoint arrays.

No live CST was run.

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/metrics.py`` | Added ``summarize_gate_results(gate_results) -> tuple[bool, str]`` helper |
| ``workflows/rfgun_sao/two_pass.py`` | Added ``metric_specs`` parameter; after measurement, compute gate results, log them, and override penalties/error if gate fails |
| ``workflows/rfgun_sao/workflow.py`` | Pass ``metric_specs=specs`` to ``make_two_pass_runtime_evaluator`` |
| ``workflows/rfgun_sao/README.md`` | Updated gate role future-work status to "live CST validation future" |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added B8 to table; updated gate authoritative behaviour; updated caveats and next directions |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AC with 11 B8 tests |
| ``reports/restructure_plan/phase_B8_gate_runtime_rejection_no_cst.md`` | Created (this file) |

## Gate runtime rejection semantics

| Aspect | Behaviour |
|--------|-----------|
| Trigger | After ``measurement_runner`` returns ``EvaluationResult`` with ``status==SUCCESS`` |
| Computation | ``compute_gate_results(metric_specs, result.raw_metrics)`` |
| Logging | ``INFO Two-pass gate results: {key=True/False, ...}`` when non-empty |
| All pass | Existing success behaviour unchanged |
| Any fail | ``penalties_arr = ones``, ``solver_ok=False``, ``error = "gate_reject:key1,key2"`` |
| Checkpoint arrays | Sized to ``objective_names`` only (gate metrics excluded) |
| ``metric_specs=None`` | Backward-compatible — no gate computation |
| ``result.status != SUCCESS`` | Existing failure path unchanged |
| ``summarize_gate_results`` | ``(True, "")`` if empty/all pass; ``(False, "gate_reject:k1,k2")`` if any fail; keys sorted |

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "b8 or summarize_gate or gate_pass or gate_fail" -v --tb=short
19/19 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
184/184 passed (full suite)
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
| ``.claude/settings.local.json`` modified by B8 | no |

## Commit hashes

- B8 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- Gate runtime rejection is **wired and tested** in the two-pass evaluator,
  but **live CST validation** of gate rejection remains future work.
- JSONL sidecar and Ctrl+C hard-exit cleanup remain future work.
- Next possible direction: gate role live CST smoke, or README milestone
  update for the complete Phase B.
