# Phase C2.1 — JSONL sidecar polish and hardening

## Summary

Polish Phase C documentation and harden the JSONL write-failure test
coverage.  C2 status updated to Accepted; C2.1 added; authoritative
behaviour wording clarified; a monkeypatch-based append failure test
added to verify non-fatal error handling.

## Base commit

``9856daa431bb6fe91f7f0923061f580971910694`` (C2 accepted HEAD)

## Files changed

| File | Change |
|------|--------|
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | C2 → Accepted; added C2.1; updated authoritative behaviour to state JSONL wired as opt-in, not "helper-only" |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section AF — monkeypatch test for ``append_jsonl_record`` failure |

## Documentation wording fixes

| Before | After |
|--------|-------|
| "JSONL sidecar is helper-only; runtime writing disabled by default" | "JSONL sidecar helpers exist and runtime writing is wired only as explicit opt-in via `logging.evaluation_records.enabled: true`" |
| Caveats redundantly repeated authoritative vs opt-in | Caveats now focus on deferred enrichment only |

## Test hardening

Added ``test_jsonl_sidecar_append_failure_caught`` which monkeypatches
``append_jsonl_record`` to raise ``OSError("forced jsonl failure")`` and
verifies:
- helper returns ``False`` without raising
- ``caplog`` contains ``"JSONL sidecar write failed"`` and ``"forced jsonl failure"``

## Validation

```
$ python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
(no errors)

$ pytest tests/workflows/test_rfgun_sao_imports.py -k "jsonl_sidecar or append_failure" --tb=short
8/8 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
207/207 passed (full suite)

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
| ``.claude/settings.local.json`` modified by C2.1 | no |

## Commit hashes

- C2.1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message
