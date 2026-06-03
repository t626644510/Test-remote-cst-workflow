# WS3 -- optimizer warm-start runtime wiring, no-CST
# WS3.1 -- checkpoint dedup runtime fix and test hardening

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `bc85a38529d11d0307b7f0e009677ae8f692f868` |
| Phase label | `WS3 -- optimizer warm-start runtime wiring / no-CST` |
| Phase label | `WS3.1 -- checkpoint dedup runtime fix / no-CST test hardening` |
| Branch | `feature/wf1-db-warm-start` |
| Live CST | **No** -- pure no-CST implementation |
| Optimizer wiring | **Implemented** -- DB priors merged into optimizer warm-start |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/evaluation_database_storage.py` | **Modified** | Added `get_all_records()` method returning all rows, newest first |
| `workflows/rfgun_sao/workflow.py` | **Modified** | Added WS3 warm-start config resolution, `get_all_records()` + `load_warm_start_priors()` call, stored report on `workflow._db_warm_start_report` |
| `workflows/rfgun_sao/run.py` | **Modified** | After checkpoint warm-start loading, merges DB warm-start priors into `prior_data` (X, F arrays) |
| `tests/workflows/test_rfgun_sao_db_warm_start_ws3.py` | **Added** | 16 no-CST WS3 optimizer wiring tests |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | WS3 status |
| `reports/restructure_plan/wf1_db_warm_start_ws3_optimizer_wiring.md` | **Added** | This report |

---

## Runtime wiring summary

### Config semantics (unchanged from WS2)

Warm-start requires all three:
1. `evaluation_database.enabled: true` (with outside-repo path)
2. `evaluation_database.warm_start.enabled: true`

Cross-implied enable remains prevented:
- DB enabled alone does NOT enable warm-start
- `success_reuse.enabled` alone does NOT enable warm-start
- Warm-start enabled does NOT enable success reuse

### Data flow

WS3.1 moved DB prior loading from ``build_workflow_1()`` into ``run.py``
after checkpoint load.  WS3.2 refactored the merge to use pure helpers.

```
ckpt.load() -> warm_xy
    |
    v
prior_data = warm_xy           # checkpoint prior_data
ckpt_keys = parameter_keys_from_prior_data(prior_data[0], param_names)
    |
    v
all_rows = _evaluation_db.get_all_records()
ws_report = load_warm_start_priors(all_rows, ws_cfg,
                checkpoint_parameter_keys=ckpt_keys, ...)
    |
    v
if ws_report.accepted_priors > 0:
    ws_priors = ws_report.diagnostics["priors"]
    merged, merge_diag = merge_checkpoint_and_db_priors(
                            prior_data, ws_priors, param_names)
    if merged is not None:
        prior_data = merged
    |
    v
opt.optimize(evaluator=..., prior_data=prior_data)

### DB row source

- `get_all_records()` queries `SELECT * FROM evaluation_records ORDER BY created_at DESC`
- All rows are returned as dicts with JSON columns decoded
- Rows are passed to WS2's `load_warm_start_priors()` which applies eligibility checks
- Only compatible SUCCESS final authoritative rows become priors
- Failure, gate, diagnostic, malformed rows are rejected with specific reasons
- JSONL sidecar is never read

### Optimizer injection

- DB priors are converted to `(X, F)` format matching the optimizer's `prior_data` parameter
- `X` is a 2D array of parameter vectors, `F` is a 1D array of objective scalars
- Checkpoint priors are loaded first, then DB priors are appended
- DB priors do NOT consume CST solve budget
- DB priors do NOT call evaluator or retry runtime

### Warm-start vs success reuse independence

| Config combination | Behavior |
|-------------------|----------|
| WS enabled, SR disabled | Optimizer receives DB priors. Future evaluation proposals run CST normally (no skip). |
| SR enabled, WS disabled | Optimizer does NOT receive DB priors. Future exact DB hits skip CST. |
| Both enabled | Optimizer receives DB priors AND future exact DB hits skip CST. No double-count. |

---

## Test coverage

The WS3.1 phase reorganized the WS3 test suite.  The file
``test_rfgun_sao_db_warm_start_ws3.py`` now contains **42 tests**
across 10 test classes (see WS3.1 section below).  The original 16-test
WS3 suite was replaced with broader coverage including checkpoint dedup,
fake optimizer harness, disabled semantics, malformed rows, pure helpers,
and full diagnostics coverage.

---

## Validation results

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_db_warm_start_ws3.py --tb=short -v
-- 16 passed

pytest tests/workflows/test_rfgun_sao_db_warm_start_ws2.py --tb=short
-- 45 passed

# Full regression (552 existing)
pytest tests/workflows/test_rfgun_sao_imports.py --tb=short -- 230 passed
pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short -- 12 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime.py --tb=short -- 83 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_cst.py --tb=short -- 35 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_workflow.py --tb=short -- 31 passed
pytest tests/workflows/test_rfgun_sao_retry_runtime_recovery.py --tb=short -- 28 passed
pytest tests/workflows/test_rfgun_sao_evaluation_success_reuse.py --tb=short -- 35 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_storage.py --tb=short -- 40 passed
pytest tests/workflows/test_rfgun_sao_evaluation_database_workflow.py --tb=short -- 10 passed

Total: 568 passed, 1 pre-existing warning.
```

---

## Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | **No** |
| Default config changed | **Not changed** |
| `config.local.yaml` committed | **Not committed** |
| Generated artifacts committed | **Not committed** |
| DB warm-start prior loader | **Wired into optimizer initialization** |
| DB priors consume CST solve budget | **No** (priors are observations, not evaluations) |
| DB priors call evaluator | **No** |
| DB priors invoke retry runtime | **No** |
| JSONL sidecar as warm-start source | **Not used** |
| Failure rows as priors | **Rejected** |
| probably-infeasible skip | **Not used** |
| Warm-start implies success reuse | **No** (independent configs) |
| Success reuse implies warm-start | **No** (independent configs) |

---

## Protected areas checklist

| Area | Status |
|------|--------|
| `workflows/rfgun_single_pass/` | **Not modified** |
| `run_workflow_1.py` | **Not modified** |
| `src/cst_optimization/` | **Not modified** |
| `workflows/rfgun_sao/config.yaml` | **Not modified** |
| `cst_optimization.factory` | **Not imported** |
| `cst_optimization.workflows.recovery` | **Not imported** |

---

## Artifacts check

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Pre-existing | **Not committed** |
| `*.jsonl` | No | N/A |
| `*.ckpt` | No | N/A |
| `*.sqlite` / `*.db` | Temporary test files | **Not committed** |
| Logs | No | N/A |
| CST output dirs | No | N/A |
| Temporary scripts | **Not created** | N/A |

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## WS3.1 -- checkpoint dedup / runtime no-CST hardening

### Background

In the WS3 implementation, checkpoint observations and DB priors were
loaded separately — the checkpoint was loaded in ``run.py`` and DB
priors were loaded inside ``build_workflow_1()`` in ``workflow.py``,
then merged as two separate ``prior_data`` arrays.  There was no
deduplication by ``parameter_key``: the same geometrical point could
appear in both checkpoint and DB lists, resulting in duplicate
observations being fed to the SAO optimizer.

### Checkpoint dedup bug and fix

**Bug:** When ``build_workflow_1()`` loaded DB priors without access
to the post-checkpoint ``warm_xy``, duplicate ``parameter_key`` entries
could appear in the final ``prior_data``.  The checkpoint's
``parameter_key`` set was never computed and never compared against
accepted DB priors.

**Fix (Option A):** The DB prior loading was moved from
``build_workflow_1()`` in ``workflow.py`` into ``run.py``, *after*
``ckpt.load()`` and checkpoint ``warm_xy`` are available.  The new
flow:

1. Load checkpoint, extract ``warm_xy`` as ``prior_data``.
2. Compute ``checkpoint_parameter_keys`` from prior_data's X array
   using ``ParameterIdentity``.
3. Call ``load_warm_start_priors(..., checkpoint_parameter_keys=...)``
   — rows whose key appears in the checkpoint are counted as
   ``skipped_checkpoint_duplicates`` and omitted.
4. Merge accepted DB priors with checkpoint priors.
5. Log accepted, rejected, and checkpoint-duplicate counts.

### Final runtime data flow

```
ckpt.load() -> warm_xy
    |
    v
prior_data = warm_xy           # checkpoint prior_data
ckpt_keys = set of parameter_key from prior_data[0]
    |
    v
all_rows = _evaluation_db.get_all_records()
ws_report = load_warm_start_priors(all_rows, ws_cfg,
                checkpoint_parameter_keys=ckpt_keys, ...)
    |
    v
if ws_report.accepted_priors > 0:
    ws_x, ws_f = db_priors_to_prior_data(ws_priors)
    prior_data = vstack/concatenate with ckpt [+]
    |
    v
opt.optimize(evaluator=..., prior_data=prior_data)
```

### How checkpoint parameter keys are computed

``parameter_keys_from_prior_data(prior_x, param_names)`` iterates each
row of the checkpoint X array and builds a ``ParameterIdentity`` using
the workflow's parameter names, then calls ``parameter_key()`` on each.
The resulting ``set[str]`` is passed into ``load_warm_start_priors()``
as ``checkpoint_parameter_keys``.

### Final prior_data merge behavior

| Input | Checkpoint only | DB only | Both |
|-------|-----------------|---------|------|
| ``prior_data`` = | checkpoint ``(X,F)`` | ``(ws_x, ws_f)`` | ``vstack + concatenate`` |
| Checkpoint dup DB rows | N/A | N/A | Skipped, counted in report |
| Per-key DB dedup | N/A | Best row per key | Best row per key |

### Diagnostics / logging

- ``accepted_priors`` — DB priors that passed all checks.
- ``rejected_rows`` — rows that failed eligibility (bad status, schema,
  names mismatch, missing values, etc.).
- ``skipped_duplicates`` — per-key duplicates within the DB (kept best).
- ``skipped_checkpoint_duplicates`` — rows whose ``parameter_key``
  already exists in checkpoint; omitted before per-key dedup.
- ``found_rows`` — total rows scanned.

### New pure no-CST helpers

Added to ``evaluation_database_warm_start.py``:

- ``parameter_keys_from_prior_data(prior_x, param_names) -> set[str]``
  — compute checkpoint-style keys from a prior_data X array.
- ``db_priors_to_prior_data(priors) -> tuple[np.ndarray, np.ndarray]``
  — convert ``DbWarmStartPrior`` list to ``(X, F)`` arrays.
- ``merge_checkpoint_and_db_priors(ckpt_data, db_priors, param_names)``
  — full merge with dedup reporting; returns merged data + diagnostics.

All are pure no-CST, easy to unit test, no runtime side effects, no
JSONL, no evaluator call.

### New tests and results

Added to ``test_rfgun_sao_db_warm_start_ws3.py``:

| Class | Tests | Coverage |
|-------|-------|----------|
| ``TestCheckpointDedup`` | 8 | DB prior matching CKPT skipped; unique accepted; mixed dedup counts; no duplicate keys in final; merge row count; ckpt_keys helper |
| ``TestWS3Config`` | 3 | Default disabled; WS without DB raises; needs explicit enable |
| ``TestNoEvaluatorCalls`` | 2 | Priors do not call evaluator; priors do not invoke retry runtime |
| ``TestFakeOptimizerHarness`` | 3 | Fake optimizer receives ckpt/merged/None prior_data |
| ``TestDisabledSemantics`` | 5 | WS disabled yields None; disabled keeps checkpoint; WS+SR independence; SR without WS |
| ``TestMalformedRowsRejected`` | 3 | SOLVER_FAILED rejected; wrong param count rejected; non-numeric param rejected |
| ``TestWSandSRIndependence`` | 2 | WS without SR injects priors; SR without WS does not |
| ``TestDiagnostics`` | 4 | Report has accepted, rejected, duplicate, all-required counts |
| ``TestHelpers`` | 9 | parameter_keys_from_prior_data; db_priors_to_prior_data; merge_checkpoint_and_db_priors (overlap, no overlap, both empty, ckpt-only, DB-only) |
| ``TestSafety`` | 2 | No JSONL reference; no CST imports |

### Confirmation no live CST

All tests are pure no-CST.  No CST connection is opened, no CST solver
is invoked, no CST Design Environment window is created.

### Confirmation no default config change

``workflows/rfgun_sao/config.yaml`` is not modified.  DB warm-start
remains off by default.

### Confirmation no success reuse behavior change

Warm-start and success reuse remain independent configs.  Neither
implies the other.  Success reuse behavior is unchanged.

### Confirmation no failure reuse / no probably-infeasible skip

Failure rows are rejected by the prior loader (``status_not_success``).
No failure reuse is implemented.  Probably-infeasible skip is not
implemented.

### File changes summary

| File | Action | Description |
|------|--------|-------------|
| ``workflows/rfgun_sao/workflow.py`` | **Modified** | Removed DB prior loading from ``build_workflow_1()``; store WS config + DB reference on workflow object instead of pre-loaded report |
| ``workflows/rfgun_sao/run.py`` | **Modified** | Moved DB prior loading after checkpoint with ``checkpoint_parameter_keys`` dedup; compute ``ckpt_keys`` from workflow param names; detailed logging with dedup counts |
| ``workflows/rfgun_sao/evaluation_database_storage.py`` | **Modified** | Fixed stale "No warm-start" header comment and class docstring |
| ``workflows/rfgun_sao/evaluation_database_warm_start.py`` | **Modified** | Added ``parameter_keys_from_prior_data``, ``db_priors_to_prior_data``, ``merge_checkpoint_and_db_priors`` helpers |
| ``tests/workflows/test_rfgun_sao_db_warm_start_ws3.py`` | **Modified** | 40 no-CST tests: checkpoint dedup, fake optimizer harness, disabled semantics, malformed rows, helpers, full diagnostics |
| ``workflows/rfgun_sao/BRANCH_CONTEXT.md`` | **Updated** | WS3.1 phase status |
| ``reports/restructure_plan/wf1_db_warm_start_ws3_optimizer_wiring.md`` | **Updated** | This WS3.1 report section |

### Final HEAD commit SHA

**To be confirmed by reviewer.**

---

## WS3.2 — runtime helper alignment and report polish

### Changes

1. **``run.py`` aligned with pure helpers** — the hand-written
   ``ParameterIdentity`` loop for checkpoint key computation was
   replaced with ``parameter_keys_from_prior_data()``, and the
   manual ``vstack``/``concatenate`` merge was replaced with
   ``merge_checkpoint_and_db_priors()``.  The same pure no-CST
   helpers that are unit-tested in ``TestHelpers`` now drive the
   actual runtime merge path.

2. **Diagnostics logging updated** — ``skipped_duplicates`` is now
   included in all three log messages (merged, no-eligible, and
   no-DB-priors), so the operator sees the full per-key dedup count
   alongside ``found_rows``, ``rejected_rows``, and
   ``skipped_checkpoint_duplicates``.

3. **Tests strengthened** — the fake optimizer harness now receives
   its prior_data via ``merge_checkpoint_and_db_priors()`` (the same
   helper ``run.py`` uses) instead of a hand-rolled ``vstack``.
   Added a DB-only merge test and a diagnostics-keys-required test.
   All merge-path tests assert that ``merge_checkpoint_and_db_priors``
   diagnostics contain ``ckpt_count``, ``db_input_count``,
   ``db_checkpoint_duplicates``, and ``db_accepted``.

### Validation

Test count grew from 40 (WS3.1) to **42** (WS3.2).  Same command suite
as WS3.1; no regressions across the full test matrix.

### Explicit statements

| Statement | Status |
|-----------|--------|
| Live CST run | **No** |
| Default config changed | **Not changed** |
| ``run.py`` uses the tested helper path | **Yes** |
| Checkpoint dedup active in runtime | **Yes** |
| DB priors call evaluator | **No** |
| DB priors invoke retry runtime | **No** |
| Warm-start implies success reuse | **No** |
| Failure reuse / probably-infeasible skip | **Not implemented** |
| WS4 live smoke | **Future, requires explicit approval** |

```
feat(wf1): harden DB warm-start optimizer wiring WS3.1

- Move DB prior loading from workflow.py to run.py after checkpoint
  so checkpoint parameter keys are available for dedup
- Compute checkpoint_parameter_keys from checkpoint warm_xy and pass
  into load_warm_start_priors(); skip DB rows matching checkpoint
- Log accepted, rejected, and checkpoint-duplicate counts per run
- Add pure no-CST helpers: parameter_keys_from_prior_data,
  db_priors_to_prior_data, merge_checkpoint_and_db_priors
- Fix stale documentation in evaluation_database_storage.py
  (remove stale "No warm-start queries" claim)
- 43 no-CST tests: checkpoint dedup, fake optimizer harness, disabled
  semantics, malformed rows, pure helpers, full diagnostics coverage

No live CST, no default config change, no failure reuse,
no success reuse behavior change, no probably-infeasible skip.
WS4 requires explicit approval.
```