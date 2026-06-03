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

#### Merged into main (MH2)

| Track | Branch | Final phase | Merged HEAD |
|-------|--------|-------------|-------------|
| WF1 SAO consolidation | `refactor/wf1-sao-consolidation` | Phase V | `c58b40a` |
| Real COM recovery runtime | `feature/wf1-real-com-recovery` | RCR3 | `3650752` |
| Durable evaluation DB | `feature/wf1-durable-evaluation-db` | DDB3.2 | `cf31c2e` |
| DB-backed success reuse | `feature/wf1-db-success-reuse` | SR4.1 | `b532856` |
| DB warm-start | `feature/wf1-db-warm-start` | WS4 | `b6538f2` |

All merged into `main` (final feature-merge commit `0a33148`, MH2 report commit `02106ea`) on 2026-06-04 via sequential no-ff merges.
`.claude/settings.local.json` removed from tracking as part of hygiene.
Remote branches archived in MH3.

#### Future planned tracks (post-merge)

- XR1 -- destructive recovery design / safety plan -- accepted at `0e5f09a`
- XR2 -- no-CST process/fault harness and classifier tests -- accepted at `624010d`
- XR2.1 -- safety harness hardening -- accepted at `b603d90`
- XR2.2 -- safety/docs cleanup -- accepted at `18dfc2c`
- XR3 -- bounded destructive live smoke -- accepted at `5bdf4bc`
- FS1 -- failure/probably-infeasible skip policy design -- accepted at `5f5bcb7`
- FS2 -- failure skip candidate loader/no-CST -- accepted at `dc0b702`
- FS2.1 -- candidate policy hardening -- accepted at `0829d6c`
- FS3 -- runtime dry-run diagnostics -- accepted at `ddbbcde`
- FS3.1 -- dry-run call-count hardening (current track)
- XR4 -- optional during-solve destructive smoke only with explicit approval
- FS -- failure/probably-infeasible skip, opt-in and fully audited
  - environment faults should generally be filtered out from skip evidence
  - deterministic/repeated exact-key failures are better skip candidates
- SE -- schema extension hooks if DB v1 becomes insufficient
- Workflow2 field objectives deferred

### DB warm-start phases (WS track)

| Phase | Scope | Live CST? |
|-------|-------|-----------|
| WS1 | Design docs-only | No |
| WS2 | DB prior loader / no-CST helper (config resolver, eligibility, dedup, capping, checkpoint dedup) | No |
| WS3 | Optimizer warm-start runtime wiring / no-CST | No |
| WS3.1 | Checkpoint dedup runtime fix / pure helpers / no-CST test hardening | No |
| WS3.2 | Runtime helper alignment / report polish | No |
| WS3.3 | Report/count cleanup only | No |
| WS4 | Bounded live warm-start smoke (conditional, explicit approval) | **Yes** |
| MH1 | Accepted branch merge hygiene audit / plan | No |
| MH2 | Sequential accepted branch merge execution / local verified merge | No |
| MH3 | Archive merged branches / final merge-hygiene cleanup | No |
| XR1 | Destructive recovery design / safety plan | No |
| XR2 | No-CST process/fault harness and classifier tests | No |
| XR2.1 | Safety harness hardening | No |
| XR2.2 | Safety/docs cleanup | No |
| XR3 | Bounded destructive live smoke | **Yes** |
| FS1 | Failure skip policy design | No |
| FS2 | Failure skip candidate loader / no-CST | No |
| FS2.1 | Candidate policy hardening | No |
| FS3 | Runtime dry-run diagnostics / no-CST | No |
| FS3.1 | Dry-run call-count hardening | No |

### WS4 live evidence (bounded smoke, 3 total CST solves)

| Metric | Seed run | Warm-start run |
|--------|----------|----------------|
| DB warm-start enabled | No | Yes |
| SUCCESS DB rows | 1 (written) | 3 (2 new from LHS) |
| accepted_priors | N/A | **1** (from seed row) |
| DB prior injected before CST eval | N/A | **Yes** (log: `Pre-loaded 1 prior`) |
| Success reuse observed | No | No |
| Best F | -13656.06 | -95592.44 |
| Orphan DE | No | No |
| Manual taskkill | No | No |

### XR3 live evidence (bounded destructive smoke, 1 scenario)

| Metric | Value |
|--------|-------|
| Scenario | `de_process_killed_before_solve` |
| Target PID | 5440 |
| Target process | `CST DESIGN ENVIRONMENT_AMD64` |
| Kill occurred | Before solver start (confirmed: `Failed to call: run_solver`) |
| Retry handler detected death | **Yes** (`Proactive graceful reset requested`) |
| Replacement DE created | **Yes** (new PID 56516) |
| Final eval status | `solver_failed` |
| DB row | 1 row, status=solver_failed, retry_count=0 |
| Best F | 1.0 (fallback) |
| Orphan DE | No |
| Manual taskkill | No |
| cstd.exe protected | Yes |

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
