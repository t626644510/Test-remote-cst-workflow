# Phase C1 — JSONL diagnostics sidecar skeleton (no-CST)

## Summary

Add a no-CST JSONL diagnostics sidecar skeleton to ``workflows/rfgun_sao``
(``records.py``).  Helper functions for JSON-safe conversion, record
building, append/read I/O, and config resolution are implemented and
tested.  Runtime JSONL writing is **disabled by default** — the ``.ckpt``
/ ``CheckpointManager`` remains the authoritative persisted evaluation
record.

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/records.py`` | New — ``make_json_safe``, ``build_evaluation_record``, ``append_jsonl_record``, ``read_jsonl_records``, ``resolve_records_config`` |
| ``workflows/rfgun_sao/README.md`` | Updated JSONL future work to reference C1 skeleton |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | Added Phase C section with C1 completion table |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AD with 14 C1 tests |
| ``reports/restructure_plan/phase_C1_jsonl_diagnostics_sidecar_skeleton.md`` | Created (this file) |

## Helper semantics

| Function | Purpose |
|----------|---------|
| ``make_json_safe(value)`` | Recursively sanitise a value for JSON serialisation; ``NaN``/``Inf`` → ``None``; numpy scalars → Python scalars; unsupported → truncated repr |
| ``build_evaluation_record(...)`` | Build a JSON-safe evaluation dict with ``raw_values``/``penalties`` keyed by ``objective_names``; length mismatch → ``ValueError``; diagnostics/gate_results included only when non-empty |
| ``append_jsonl_record(path, record)`` | Append one JSON line to file; creates parent dir |
| ``read_jsonl_records(path)`` | Read all records from JSONL file; returns ``[]`` if missing |
| ``resolve_records_config(cfg)`` | Parse ``logging.evaluation_records`` from YAML config; returns ``{"enabled": bool, "path": str\|None}`` |

## Runtime wiring

**Deferred.**  The helper module exists and is tested, but no code in
``run.py``, ``evaluator.py``, or ``two_pass.py`` writes JSONL records
automatically.  ``resolve_records_config`` returns ``{"enabled": False}``
by default.  A future phase may wire runtime writing with explicit opt-in
via ``logging.evaluation_records.enabled: true`` in an untracked local
config.

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "jsonl or records or sidecar or make_json or build_eval" --tb=short
14/14 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
198/198 passed (full suite)
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
| ``.claude/settings.local.json`` modified by C1 | no |

## Commit hashes

- C1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / next recommended phase

- JSONL runtime writing is **disabled by default**; ``.ckpt`` remains
  authoritative.
- Next possible direction: wire JSONL runtime records with explicit opt-in
  via ``logging.evaluation_records.enabled``.
