# Phase C2 — JSONL diagnostics sidecar runtime opt-in wiring (no-CST)

## Summary

Wire the C1 JSONL sidecar helpers into the ``rfgun_sao`` explicit runner
(``run.py``) with opt-in-only runtime writing.  The sidecar records core
evaluation data (``x_phys``, ``objective_names``, ``raw_values``,
``penalties``, ``solver_ok``, ``error``) and metadata when
``logging.evaluation_records.enabled: true`` is set.  Default config does
not enable JSONL writes; ``.ckpt`` remains authoritative.

## Base commit

``46a1315a8051410d7aa0a0bf5ccfead8f3b31969`` (C1 accepted HEAD)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/run.py`` | Added ``_record_jsonl_sidecar_evaluation`` helper; called from ``_on_evaluation`` after checkpoint write; ``resolve_records_config`` called in ``main()`` |
| ``workflows/rfgun_sao/README.md`` | Updated JSONL future work to "opt-in only; default disabled; C2 wiring done" |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added C2 to Phase C table |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AE with 8 C2 tests |
| ``reports/restructure_plan/phase_C2_jsonl_runtime_opt_in_no_cst.md`` | Created (this file) |

## Design decisions

| Aspect | Decision |
|--------|----------|
| Default state | **Disabled** — no JSONL file created, no writes |
| Opt-in key | ``logging.evaluation_records.enabled: true`` |
| Path | Auto-derived from ``logging.output_dir`` or explicit ``path`` |
| Failure handling | Non-fatal — ``logger.warning`` on error, returns ``False`` |
| Content | Core evaluation record (schema_version, iteration, objective_names, raw_values, penalties, solver_ok, error, x_phys, metadata) |
| Diagnostics/gate_results | **Deferred** — C2 writes core records only |
| Recovery source | JSONL is **not** a recovery source; only ``.ckpt`` is authoritative |
| Metric name validation | Uses ``_checkpoint_metric_names_from_wf_ref``; mismatch → skip + warning |

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "jsonl_sidecar" --tb=short
7/7 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
206/206 passed (full suite)

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
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes (verified: no ``evaluation_records`` key) |
| ``config.local.yaml`` committed | no |
| Generated JSONL/ckpt/logs committed | no |
| CST artifacts committed | no |
| ``.claude/settings.local.json`` modified by C2 | no |

## Commit hashes

- C2 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- JSONL sidecar writes core evaluation records **only** — diagnostics and
  gate_results enrichment remain deferred (C3 or later).
- ``.ckpt`` / ``CheckpointManager`` remains the authoritative record.
- Next possible direction: JSONL diagnostics/gate_results enrichment, or
  Ctrl+C hard-exit cleanup hardening.
