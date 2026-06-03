# Branch Context -- `rfgun_sao` (Experimental Consolidation)

## Status

This package is the experimental consolidation target for RF gun SAO
capabilities.  It is derived from the validated
`workflows/rfgun_single_pass/` package.

## Core rules

1. **Do not modify `workflows/rfgun_single_pass/`**.  The validated
   reference must remain untouched.
2. **Do not import `cst_optimization.factory`**.
3. **Do not import `cst_optimization.workflows.recovery`**.  Use
   `workflows.rfgun_sao.types` for evaluation types.
4. **`run_workflow_1.py` is already repointed to `workflows.rfgun_sao.run`
   and is protected; do not modify it unless a phase explicitly scopes
   root-shim work.**
5. **Default behaviour must remain validated single-pass** identical to
   `rfgun_single_pass`.  Opt-in features (two-pass, gates, metric
   roles, etc.) must be explicitly enabled.
6. **Do not commit `config.local.yaml`**, logs, checkpoints, CST
   artifacts, or output directories.
7. **CST licensing service (`cstd.exe` with no window) must not be
   confused with a CST Design Environment window.**

## Minimum validation before any commit

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
pytest tests/workflows/test_rfgun_sao_imports.py -v --tb=short
```

## Consolidation phases (O-V)

The consolidation branch covered phases O through V.  See
`reports/restructure_plan/` for detailed reports.

### Accepted live evidence (through Phase T)

| Phase | Scope | Evals | Best F | Orphan DE? |
|-------|-------|-------|--------|------------|
| P3 | Cleanup hardening fix | 1 | -15392.38 | None |
| Q1 | Multi-eval stability | 5 | -18002.12 | None |
| Q2 | Repeated-run (x3) | 15 | -18002/-18002/-17883 | None (3 runs) |
| S1 | Root shim sanity | 1 | -15392.37 | None |
| T | Production campaign | 9 | -18002.12 | None |
| **Total** | **7 runs** | **31** | | **Zero orphan DE** |

### Future tracks -- separate branches only

**This consolidation branch is complete after Phase V acceptance.**
Future feature tracks are independently planned on separate branches.

#### Accepted / merge-archive only

| Track | Branch | Final phase | Accepted HEAD |
|-------|--------|-------------|---------------|
| Durable evaluation DB | `feature/wf1-durable-evaluation-db` | DDB3.2 | `cf31c2e` |
| DB-backed success reuse | `feature/wf1-db-success-reuse` | SR4.1 | `b532856` |

#### Current track in progress

| Track | Branch | Status |
|-------|--------|--------|
| DB warm-start | `feature/wf1-db-warm-start` | WS1 design accepted; WS2 prior loader completed; WS2.1 semantics hardening; WS2.2 docs/review polish |

#### Planned future tracks

- Phase O/O1 retry runtime CST wiring -- no-CST callback-only skeleton
- Failure reuse -- last track, advisory-first
- Broader production campaigns (beyond 9 evals)

### DB warm-start phases (WS track)

| Phase | Scope | Live CST? |
|-------|-------|-----------|
| WS1 | Design docs-only | No |
| WS2 | DB prior loader / no-CST helper (config resolver, eligibility, dedup, capping, checkpoint dedup) | No |
| WS3 | Optimizer warm-start runtime wiring / no-CST | No |
| WS4 | Bounded live warm-start smoke (conditional) | Yes, only with explicit approval |

## Phase B -- Metric roles and gate (B1-B9) -- CLOSED

Accepted.  See reports for details.

## Key design policies

- JSONL diagnostic sidecar remains diagnostic-only; not a recovery or
  warm-start source.
- Evaluation database is a separate explicit opt-in; not equivalent to
  JSONL sidecar.
- No failure reuse implemented.  Single failure never permanent skip.
- Probably-infeasible is advisory; not used for skip/reuse/runtime discard.
- Root shim was repointed at Phase S (commit `76ac3bf`).  Rollback:
  `git revert 76ac3bf`.
- DDB and SR tracks are merge/archive only.
