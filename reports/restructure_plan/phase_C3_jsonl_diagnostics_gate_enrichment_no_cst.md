# Phase C3 — JSONL diagnostics/gate_results enrichment (no-CST)

## Summary

Extend the opt-in JSONL sidecar with diagnostics and gate_results
enrichment via a new ``evaluation_record_callback`` in the two-pass
runtime evaluator.  The callback fires after both rejected and
measurement paths, carrying report-only diagnostics, gate pass/fail
results, and contextual metadata.  Default config remains JSONL-disabled;
``.ckpt`` remains authoritative.

## Base commit

``734ef927b9d3aaf06f7c053fbd0c63c9f374bd4a`` (C2.1 accepted HEAD)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Extended ``_record_jsonl_sidecar_evaluation`` with ``diagnostics``, ``gate_results``, ``extra_metadata`` kwargs; added ``_enrichment_callback`` closure and two-pass wiring in ``main()`` |
| ``workflows/rfgun_sao/two_pass.py`` | Added ``evaluation_record_callback`` parameter; fires in rejected path (with calibration meta) and measurement path (with diagnostics + gate_results) |
| ``workflows/rfgun_sao/workflow.py`` | Added ``evaluation_record_callback`` parameter; passed to ``make_two_pass_runtime_evaluator`` for two-pass branch |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AG with 7 C3 tests |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | C2.1 → Accepted; added C3; updated caveats |
| ``reports/restructure_plan/phase_C3_jsonl_diagnostics_gate_enrichment_no_cst.md`` | Created (this file) |

## Runtime callback design

| Aspect | Detail |
|--------|--------|
| Callback signature | ``evaluation_record_callback(x_phys, raw_values, penalties, solver_ok, error, diagnostics, gate_results, metadata)`` — keyword-only |
| Rejected path | Passes ``diagnostics=calibration_meta``, ``gate_results=None``, ``metadata={two_pass_phase: rejected, reject_reason: ...}`` |
| Measurement path | Passes ``diagnostics=result.diagnostics``, ``gate_results`` from ``compute_gate_results``, ``metadata={two_pass_phase: measurement}`` |
| Gate fail | ``gate_results`` contains failing keys, ``solver_ok=False``, ``error="gate_reject:..."`` |
| Exception safety | Callback exception caught, logged as warning, does not affect scalar or checkpoint |
| Run.py wiring | Two-pass with JSONL enabled → enriched callback used; ``_on_evaluation`` skips core-only JSONL write |

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "c3_" --tb=short
6/6 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
214/214 passed (full suite)

$ pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
12/12 passed
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
| Generated JSONL/ckpt/logs committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by C3 | no |

## Commit hashes

- C3 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
