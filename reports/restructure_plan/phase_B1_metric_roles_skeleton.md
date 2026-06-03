# Phase B1 — Metric roles skeleton (no-CST)

## Summary

Add a lightweight metric role parsing skeleton to ``workflows/rfgun_sao``,
enabling classification of objective entries as ``optimize``, ``threshold``,
or ``report_only``.  The two-pass and single-pass workflow containers now
expose both ``objective_names`` (optimize + threshold) and
``report_metric_names`` (report_only).  No live CST was run; no legacy
recovery module was imported.

## Scope

- **no-CST metric roles skeleton only** — parser/dataclass/container changes,
  no change to objective computation or live runtime behaviour.
- **No threshold penalty implementation** — threshold roles are classified
  in B1 but treated identically to optimize for objective vector purposes.
- **No report_only live extraction** — report_only names are surfaced on the
  container but not computed or checkpointed.
- **No JSONL sidecar**.
- **No gate role** (legacy Workflow 3 gate role not implemented).

## Legacy parity mapping

| Workflow 3 role | B1 equivalent | In objective_names | In report_metric_names |
|----------------|---------------|-------------------|----------------------|
| ``optimize`` | ``optimize`` | yes | no |
| ``threshold`` | ``threshold`` | yes (no penalty yet) | no |
| ``report_only`` | ``report_only`` | no | yes |
| ``gate`` | not implemented | — | — |

## Files changed

| File | Action |
|------|--------|
| ``workflows/rfgun_sao/metrics.py`` | New — ``MetricRole`` enum, ``MetricSpec`` dataclass, ``build_metric_specs``, ``objective_metric_names``, ``report_metric_names``, ``parse_metric_role_config`` |
| ``workflows/rfgun_sao/workflow.py`` | Imported ``build_metric_specs`` / ``objective_metric_names`` / ``report_metric_names``; both branches now compute and set ``workflow.report_metric_names``; objectives filtered to optimize+threshold only for ``_build_objectives`` |
| ``tests/workflows/test_rfgun_sao_imports.py`` | Added Section U (B1) with 8 tests |
| ``reports/restructure_plan/phase_B1_metric_roles_skeleton.md`` | Created (this file) |

## Production code changed

**Minimal parser/container changes only:**

- ``workflows/rfgun_sao/metrics.py`` — new module, no existing code touched.
- ``workflows/rfgun_sao/workflow.py`` — added 4 lines of import + 8 lines of
  spec parsing (2 lines in each of two branches for ``build_metric_specs``,
  ``objective_metric_names``, ``report_metric_names``, and entry filtering);
  1 line for ``workflow.report_metric_names = report_names`` in each container.
  The ``_build_objectives`` function is unchanged.

No changes to evaluator, two-pass orchestration, checkpoint, gates, or
legacy recovery modules.

## Semantics

- ``objective_names`` = optimize + threshold (same as flat config with no
  role for backward compatibility).
- ``report_metric_names`` = report_only (empty list for flat config).
- Missing role → defaults to ``optimize``.
- Unknown role → ``ValueError`` with ``"Unknown metric role"``.
- Disabled entries are handled by existing ``_build_objectives`` filtering.
- Checkpoint/evaluator arrays sized to ``objective_names`` (excludes
  report_only).

## Validation

```
$ pytest tests/workflows/test_rfgun_sao_imports.py -k "metric_role or role_split or unknown_role or placeholder_with_role" -v --tb=short
7/7 passed (targeted)

$ pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
116/116 passed (full suite)
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

## Commit hashes

- B1 implementation/report commit: reported in final execution message
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: reported in final execution message

## Caveats / follow-up

- **Threshold penalty behaviour not implemented** — threshold metrics are
  classified but treated as optimize in B1.
- **Report_only live extraction not implemented** — names are on the
  container only.
- **Gate role not implemented** — legacy Workflow 3 gate role deferred.
- **JSONL sidecar still future.**
- **Suggested B2 direction:** Threshold penalty formula integration or
  report_only diagnostic extraction, depending on priority.
