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
4. **Do not change `run_workflow_1.py`** until live single-pass
   regression passes on this package.
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

## Phase A 鈥?Two-pass orchestration and checkpoint (A1鈥旀弬25.1)

See `reports/restructure_plan/` for detail.  Milestone summary:

- Two-pass runtime skeleton with injectable calibration/measurement runners
- CST runner adapters (HPBW / dip-min calibration)
- Calibration failure and gate rejection diagnostics
- Checkpoint persistence audit, hardening, and live evidence
- README validation taxonomy cleanup

**Status:** Closed.  Checkpoint milestone accepted through A25.1.

## Phase C 鈥?Diagnostics sidecar

**Status:** JSONL diagnostics sidecar milestone closed through C3.5.

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| C1 | JSONL diagnostics sidecar skeleton 鈥?``records.py`` helpers | Accepted |
| C2 | JSONL runtime opt-in wiring 鈥?``_record_jsonl_sidecar_evaluation``, ``_on_evaluation`` integration, no-CST tests | Accepted |
| C2.1 | JSONL sidecar polish 鈥?write-failure monkeypatch test, doc wording hardening | Accepted |
| C3 | JSONL diagnostics/gate_results enrichment 鈥?extended callback, two-pass runtime enrichment, no-CST tests | Accepted |
| C3.1 | JSONL mode gating fix 鈥?`_should_use_enriched_jsonl` helper, single_pass core-only path preserved | Accepted |
| C3.2 | JSONL counter ordering fix 鈥?enriched path no longer double-increments; each path increments once per eval | Accepted |
| C3.3 | JSONL docs/status polish 鈥?final Phase C docs alignment | Accepted |
| C3.4 | README JSONL policy cleanup 鈥?removed stale `not written` wording | Accepted |
| C3.5 | JSONL milestone closeout 鈥?status alignment | Accepted |

### Authoritative behaviour

- ``.ckpt`` / ``CheckpointManager`` remains the authoritative persisted
  evaluation record.
- JSONL sidecar helpers exist and runtime writing is wired **only as
  explicit opt-in** via ``logging.evaluation_records.enabled: true``.
- ``resolve_records_config`` reads ``logging.evaluation_records`` config key.
- Default config keeps JSONL **disabled**; JSONL is **not** a recovery source.
- ``single_pass`` + JSONL enabled 閳?core-only C2 fallback.
- ``two_pass`` + JSONL enabled 閳?enriched diagnostics/gate_results callback (C3).
- Each evaluation increments exactly once; iteration starts at 0.

### Known caveats

- JSONL diagnostics/gate_results enrichment is wired for two-pass; single_pass gets core-only fallback.
- No live CST validation of JSONL sidecar output yet.
- JSONL is diagnostic only; not a recovery or warm-start source.
- Second Ctrl+C now performs best-effort cleanup before hard exit (D1);
  live CST validation of D1 cleanup pending.

### Next possible directions

a) Live CST JSONL sidecar smoke (only when explicitly requested).
b) Phase C docs/report consolidation (if needed).

## Phase D 鈥?Ctrl+C hard-exit cleanup (D1)

**Status:** Phase D blocked cleanup milestone closed through D2.7. Normal live CST cleanup validated; hard-exit live Ctrl+C validation deferred to future true interactive terminal.

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| D1 | Ctrl+C hard-exit cleanup skeleton 鈥?`_handle_sigint_event` helper, best-effort cleanup before `_os._exit`, no-CST tests | Accepted |
| D1.1 | D1 helper polish 鈥?return-after-exit guard, cleanup failure warning fallback, BRANCH_CONTEXT cleanup | Accepted |
| D1.2 | Phase C/D BRANCH_CONTEXT table structure cleanup 鈥?removed stray D1 from Phase C table | Accepted |
| D1.3 | D1 milestone closeout 鈥?status alignment | Accepted |
| D2 | Live CST validation of D1 hard-exit cleanup | Partial / normal cleanup passed; hard-exit blocked |
| D2.1 | Hard-exit live validation retry 鈥?attempted but blocked by non-interactive Windows signal delivery | Attempted / blocked |
| D2.2 | Blocked closeout 鈥?honest status correction, future validation deferred to interactive terminal | Accepted |
| D2.3 | Blocked closeout status polish | Accepted |
| D2.4 | Duplicate D2.2 row cleanup | Accepted |
| D2.5 | Blocked closeout final status polish | Accepted |
| D2.6 | Final acceptance polish | Accepted |
| D2.7 | Blocked cleanup milestone closeout | Accepted |

### Authoritative behaviour

- Normal completion and first Ctrl+C 閳?`finally` block runs
  `_cleanup_workflow_connection` as before.
- Second Ctrl+C 閳?`_handle_sigint_event` runs
  `_cleanup_workflow_connection(force=True)` best-effort before
  `_os._exit(130)`.  If cleanup raises, a warning is logged and
  hard-exit proceeds.
- Normal cleanup live CST validated (D2).
- Hard-exit live Ctrl+C validation remains blocked 鈥?requires true
  interactive operator-controlled terminal outside local-agent tool context.

### Known caveats

- If the Python runtime or OS-level kill (``taskkill /F``, SIGKILL) is used,
  cleanup is bypassed entirely.
- Hard-exit live Ctrl+C validation remains future; blocked by non-interactive
  execution environment (see D2.2 report).

### Next possible directions

a) True manual interactive live CST Ctrl+C validation outside local-agent
   tool context.
b) Move on to other non-live hardening or documentation work.

## Phase E 鈥?Workflow3 capability migration design

**Status:** Design document accepted; implementation deferred to future phases (F, G, H, ...).

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| E | Workflow3 capability migration design 鈥?staged search, adaptive bounds, retry/recovery, evaluation database, future phase order | Accepted |
| F | Stage search no-CST helpers 鈥?`StageCandidateStatus`, `StageBounds`, `StageSummary`, `summarize_stage_observations`, `decide_stage_transition`, `make_recentered_bounds`, no-CST tests | Accepted |
| F1 | Stage search helper semantics hardening 鈥?min-span using reference_span, database-reused accounting fix, rate clamp, high-fail-recenters regression tests | Accepted |
| G | Adaptive bounds no-CST helpers 鈥?boundary/quality detection, `recommend_adaptive_bounds`, expand/shift helpers | Accepted |
| G1 | Adaptive bounds semantics hardening 鈥?per-parameter clipping, affected-param-only expansion, validation, quality clustering threshold | Accepted |
| H | Stage + adaptive integration policy 鈥?`combine_stage_and_adaptive_decisions`, `build_adaptive_input_from_stage_decision`, `extract_high_quality_points`, no-CST tests | Accepted |
| I | Stage runtime wiring no-CST 鈥?`StageRuntimeState`, `record_stage_observation`, `maybe_update_stage_bounds`, config helpers, opt-in only, disabled by default | Accepted |
| I1 | Stage runtime semantics hardening 鈥?adaptive config propagation, BLOCK_STAGE_SHRINK non-transition, tightened test assertions | Accepted |
| J | Evaluation database design/schema 鈥?`ParameterIdentity`, `EvaluationDatabaseRecord`, `RawEvaluationPayload`, `record_to_json_dict`, `record_from_json_dict`, schema DDL, no-CST tests | Accepted |
| K | Evaluation database dedup no-CST skeleton 鈥?`InMemoryEvaluationRecordIndex`, `classify_record_for_dedup`, `decide_dedup_for_parameter`, no-CST tests | Accepted |
| L | Evaluation database warm-start/prior construction 鈥?`PriorCandidate`, `PriorConstructionReport`, `classify_record_for_prior`, `build_prior_candidates_from_records`, `select_prior_candidates`, `derive_stage_observations_from_prior_candidates`, no-CST tests | Accepted |
| L1 | Warm-start/prior semantics hardening 鈥?`record_to_prior_candidate` eligibility fix, diagnostic-only classification, missing tests, next-directions cleanup | Accepted |
| M | Retry / recovery taxonomy design 鈥?failure taxonomy, retry eligibility, recovery mechanism separation, evaluation database interaction, future phase order | Accepted |
| N | Retry taxonomy no-CST helper skeleton 鈥?`RetryFailureClass`, `RetryEligibilityAction`, `RetryPolicy`, `classify_failure_record`, `classify_retry_eligibility`, `suggest_next_retry_tier`, `should_escalate_to_probably_infeasible`, no-CST tests | Accepted at 9dcbadf |
| N1 | Retry taxonomy semantics hardening 鈥?probably-infeasible guard now requires same identity, stable allowed class, excludes diagnostic-only/transient/gate/success/unsupported/missing/incompatible; comprehensive tests | Accepted at 9dcbadf |
| O | Retry / inter-pass recovery runtime wiring no-CST skeleton 鈥?`RetryRuntimeConfig`, `RetryAttemptRecord`, `RetryRuntimeResult`, `resolve_retry_runtime_config`, `should_use_retry_runtime`, `run_retry_loop_no_cst`, `run_inter_pass_recovery_no_cst`, `run_post_eval_recovery_no_cst`, no-CST tests | Accepted at c1d7347 |
| O1 | Retry runtime no-CST progress hardening 鈥?`_normalize_retry_record` helper, internal `attempts_consumed` guard, progress guard activations diagnostic, 23 new O1 regression tests (83 total) | Accepted at c1d7347 |
| P | Live CST smoke for retry/recovery 鈥?minimal single_pass validation (n_initial=1, n_iter=0), Best F=-15392.38, cleanup revealed orphan DE hang issue; retry runtime not yet wired to CST runner | Accepted at 38d3d86 |
| P1 | CST cleanup reliability gap analysis / hardening plan 鈥?no-CST `cst_cleanup_diagnostics.py` helper (classify_cst_process, should_force_kill_orphan_de, summarize_cleanup_observation), 24 no-CST tests | Accepted at 07d9133 |
| P2 | CST cleanup observation live smoke / hardening decision 鈥?two-phase live CST confirmed identical orphan DE pattern (PID 36496); P1 helper validated; cleanup gap still open; cleanup runtime hardening recommended before retry runtime CST wiring | Accepted at d3b6668 |
| P3 | CST cleanup runtime hardening 鈥?`_retry_handler` stored on workflow; `_cleanup_workflow_connection` calls `close_all()` to close all connections including replacement DE; live validated: orphan eliminated (both PID 18252 and 57924 terminated, only cstd.exe remains) | Accepted at 0251aee |
| Q | Production-scale validation readiness plan 鈥?validation matrix (T1/T2/T3), success/failure criteria, artifact policy, root shim gating, rollback plan; docs-only | Accepted at e052cba |
| Q1 | Minimal multi-evaluation live validation 鈥?n_initial=3, n_iter=2 (5 evals), Best F -18002.12 (17% improvement), P3 cleanup verified across multiple evals: 6 close hangs handled, no orphan DE, no manual cleanup | Accepted at 9b154a1 |
| Q2 | Repeated-run cleanup stability validation 鈥?3 consecutive runs (15 total evals), Best F -18002/-18002/-17883, 18 close hangs handled, zero orphan DE accumulation, no manual taskkill across full sequence; cleanup stability sufficient for Phase R readiness | Accepted at e2f3b79 |
| R | Root shim repoint readiness / rollback plan 鈥?readiness criteria satisfied (cleanup stable, 399 tests pass, CLI compatible); repoint design, rollback steps, preflight checklist documented; root shim NOT repointed; docs-only | Accepted at 98f8b87 |
| S | Root shim repoint 鈥?`run_workflow_1.py` import changed from `rfgun_single_pass.run` to `rfgun_sao.run`; CLI verified; 399 tests pass; minimal import-only change with explicit operator approval | Accepted at 76ac3bf |
| S1 | Post-repoint root shim live sanity / rollback drill 鈥?first live CST through repointed root shim (run_workflow_1.py), Best F -15392.37, cleanup no orphan DE, rollback drill documented | Accepted at c1f2232 |
| T | Production-scale campaign 鈥?first production-scale run through root shim (run_workflow_1.py, n_initial=3, n_iter=6, 9 evals), Best F -18002.12, zero orphan DE, no manual cleanup | Accepted at 5929027 |
| U | WF1 SAO consolidation closeout / merge readiness 鈥?docs-only closeout: 31 live evals since P3 fix, zero orphan DE, zero manual cleanup; all merge readiness criteria satisfied; future work separately gated | Accepted at c82e809 |
| V | Merge handoff / docs polish / future tracks technical plan 鈥?docs polish (stale wording fixes); future feature tracks technical document created; merge handoff recommendation | Completed / pending review |

### Migration constraints

- Staged search (F鈥旀彂), adaptive bounds (G鈥旀彂), and evaluation database helpers (J鈥旀彆) exist as **no-CST helpers and opt-in runtime wiring only**; durable DB, live CST runtime validation, and retry remain future.
- JSONL diagnostic sidecar (Phase C) remains **diagnostic-only** and must not be promoted to a recovery source.
- The future evaluation database (Phase J+) is a **separate explicit opt-in concept** and is not equivalent to the JSONL sidecar.
- Do **not** import ``cst_optimization.workflows.recovery``; do **not** copy legacy ``RecoveryWorkflowEvaluator``.
- Root shim was repointed from ``rfgun_single_pass`` to ``rfgun_sao`` at Phase S (commit ``76ac3bf``).  ``run_workflow_1.py`` now imports ``workflows.rfgun_sao.run``.  Rollback is always available via ``git revert 76ac3bf``.
- Subsequent phases use single-letter names F, G, H, I, J, K, ... with decimal sub-phases (F1, F2, ...).

### Phase O / O1 caveats

- Phase O and O1 are no-CST only 鈥?no live CST retry validation.
- O1 added `_normalize_retry_record()` and internal `attempts_consumed` guard to prevent infinite loops.
- Runtime uses `classify_retry_eligibility()` to decide retry; does **not** use `should_escalate_to_probably_infeasible()` for skip/reuse.
- `use_probably_infeasible_for_skip` is rejected with diagnostic; not implemented.
- No durable DB 鈥?no append/lookup/load/save.
- No failure reuse implementation.
- No optimizer/runtime warm-start injection.
- At O/O1 time the root shim had not yet been repointed; root shim was later repointed at Phase S and live-validated at S1/T.
- Inter-pass/post-eval recovery are callback-only skeletons 鈥?no real CST cleanup invoked.
- Phase C JSONL diagnostic sidecar is not referenced or used.

### Phase P / P1 / P2 caveats

- Phase P live CST smoke was partial 鈥?evaluation succeeded but cleanup left an orphan DE window (PID 30808) requiring manual `taskkill /F`.
- Phase P2 live CST observation confirmed the **identical orphan DE pattern** on a second run (PID 36496). The `DesignEnvironment.close()` hang is reproducible and deterministic.
- The `DesignEnvironment.close()` hang is a pre-existing issue (documented B5.1). The legacy `cst_optimization.core.retry` proactive reset replaces the hung DE with a new DE that is not fully terminated 鈥?the OS process remains with a visible window.
- The P1 diagnostic helper (`cst_cleanup_diagnostics.py`) correctly classifies licensing service vs. orphan DE and produces accurate `summarize_cleanup_observation()` output.
- The new retry runtime (`retry_runtime.py`) was **not exercised** 鈥?it is not yet wired into the CST runner.
- All retry-related activity came from the legacy `cst_optimization.core.retry` module.
- Phase P3 implemented cleanup runtime hardening: `_retry_handler` stored on workflow; `_cleanup_workflow_connection` now calls `retry_handler.close_all(force)` to close ALL connections including the replacement DE created by `force_reset()`.
- Live CST validation confirmed the fix: both original DE (PID 18252) and replacement DE (PID 57924) properly terminated; only `cstd.exe` licensing service remained.
- No manual `taskkill` was needed after the fix (Phase P and P2 both required manual cleanup).
- Production-scale validation was performed at Phase T (9 evals, no orphan DE).
- No durable DB, no failure reuse, no probably-infeasible skip. Root shim later repointed at Phase S.

### Future work 鈥?separate branches only

**This consolidation branch is complete after Phase V acceptance.** Future feature tracks must be independently planned on separate branches. Do not continue adding new feature phases to this branch.

The following tracks have been **accepted on separate branches** and are now merge/archive only:

| Track | Branch | Final phase | Accepted HEAD |
|-------|--------|-------------|---------------|
| Durable evaluation DB | `feature/wf1-durable-evaluation-db` | DDB3.2 | `cf31c2e4dd174dbbfc451d07a16f4ecbddb70843` |
| DB-backed success reuse / dedup | `feature/wf1-db-success-reuse` | SR4.1 | `b532856232c7f4b8d320c52c83f8f1b25e61e89e` |

The following capabilities remain **not implemented** and are separately gated future work on new branches:

- Phase O/O1 retry runtime CST wiring 鈥?currently no-CST callback-only skeleton
- DB warm-start / optimizer runtime warm-start injection 鈥?design phase WS1 underway
- Failure reuse 鈥?last track, start advisory-only
- Broader production campaigns (beyond 9 evaluations)

These are explicitly **not part of this consolidation** and should be planned as independent future phases.

## Phase B 鈥?Metric roles and gate (B1鈥旀弮9) 鈥?**CLOSED**

### Completed

| Phase | Scope | Status |
|-------|-------|--------|
| B1 | Metric roles skeleton (optimize / threshold / report_only) | Accepted |
| B2 | Threshold penalty formula (`compute_threshold_penalty`) | Accepted |
| B3 | Threshold penalty runtime wiring (`compute_role_penalties`) | Accepted |
| B4 | Report-only diagnostic extraction (`report_only_diagnostics`) | Accepted |
| B4.1 | Diagnostics preservation hardening (stale reset, measurement runner) | Accepted |
| B5 | Live CST role-metrics smoke (optimize + threshold + report_only) | Accepted |
| B5.1 | Runner-level CST cleanup (`_cleanup_workflow_connection`) | Accepted |
| B7 | Gate metric role skeleton (`compute_gate_pass`, `compute_gate_results`) | Accepted |
| B8 | Gate runtime rejection wiring (no-CST) | Accepted |
| B9 | Gate runtime rejection live CST smoke 鈥?q0 gate fail confirmed, Best F=1.0, `gate_reject:q0_gate` | Accepted |

### Authoritative behaviour

- **optimize**: in `objective_names`, checkpoint arrays; penalty via
  `mode.compute`.
- **threshold**: in `objective_names`, checkpoint arrays; penalty via
  `compute_threshold_penalty(spec, value)` (less_than / greater_than formula).
- **report_only**: excluded from `objective_names` and checkpoint arrays;
  surfaced as `EvaluationResult.diagnostics`; logged in two-pass path when
  non-empty; `report_as` controls output key; **not** persisted to `.ckpt`
  or JSONL.
- **Runner-level CST cleanup**: `_cleanup_workflow_connection` runs in
  `finally` block, outputting
  `CST cleanup: attempted=<bool> closed=<bool> pid=<PID>`.
- **gate**: parsed and exposed as `gate_metric_names`; pure pass/fail
  helpers (`compute_gate_pass`, `compute_gate_results`, `summarize_gate_results`);
  excluded from `objective_names`, checkpoint arrays, and `compute_role_penalties`;
  **runtime candidate rejection wired** in two-pass evaluator;
  **live CST validated** (B9): q0 raw=18630.8 vs threshold=999999999 閳?fail,
  `error="gate_reject:q0_gate"`, Best F=1.0, cleanup closed=True.

### Live evidence

| Smoke | Best F | Key confirmation |
|-------|--------|------------------|
| B5 (role metrics) | -17534.24 | optimize + threshold in objective (5 of 7 metrics); report_only diagnostics logged with `report_as` aliases; threshold penalty formula verified |
| B5.1 (shutdown) | 鈥?| `CST cleanup: attempted=True closed=True pid=50700`; no DE window left open after run |
| B9 (gate rejection) | 1.0 | q0 raw=18630.8 vs threshold=999999999 greater_than 閳?`q0_gate=False`; `error="gate_reject:q0_gate"`; objective/checkpoint arrays exclude gate; cleanup closed=True pid=59364 |

### Known caveats

- Production-scale validation remains future.
- Report-only diagnostics not persisted to checkpoint.

> **Historical Phase B caveats (superseded by later phases):**
> JSONL sidecar (Phase C) is now opt-in diagnostic-only; second Ctrl+C (Phase D)
> now performs best-effort cleanup before hard exit (live hard-exit validation
> remains blocked by non-interactive tool environment).

### Next possible directions

a) Additional live CST regression smoke (only when explicitly requested).


