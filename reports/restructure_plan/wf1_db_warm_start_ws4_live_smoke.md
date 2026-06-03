# WS4 — bounded live DB warm-start smoke

## Metadata

| Field | Value |
|-------|-------|
| Base commit | `13982c4ee9dda3618b33083521e2784fbce7eb80` (current HEAD, includes WS3.3 docs cleanup) |
| WS3 accepted base | `20866e5a4974ea21ee9e4077a936211ba40836b4` (pre-WS3.3) |
| Phase label | `WS4 — bounded live DB warm-start smoke` |
| Branch | `feature/wf1-db-warm-start` |
| Operator approval | Explicitly approved in chat for bounded live CST smoke |
| Live CST | **Yes** — bounded and explicitly approved for this phase only |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `reports/restructure_plan/wf1_db_warm_start_ws4_live_smoke.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | WS4 status with live evidence |

---

## Local-only files (not committed)

| File | Status |
|------|--------|
| `config.local.yaml` | Untracked, **not committed** |
| `scripts/inspect_db.py` | Temporary helper, **not committed** |

---

## Outside-repo DB

**Path:** `D:/Results/wf1-ws4-smoke/warm_start_smoke.db`

The path is under `D:/Results/wf1-ws4-smoke/` which is outside the repo root
(`C:/Users/lau/cst_ver3/`).  The DB file was created by the smoke and is
**not committed**.

---

## Seed run (Step A)

### Command

```
python -m workflows.rfgun_sao.run --config config.local.yaml --n-initial 1 --n-iter 0
```

### Config for seed

- `evaluation_database.enabled: true`
- `evaluation_database.warm_start.enabled: false`
- `evaluation_database.success_reuse.enabled: false`
- `optimization.n_initial_samples: 1`
- `optimization.n_iterations: 0`

### Result

| Metric | Value |
|--------|-------|
| DB row count | 1 |
| SUCCESS final authoritative rows | 1 |
| parameter_key | `c325dffff9315d57...` (SHA-256 of parameter vector) |
| Run ID | `bc6986a0` |
| Best F | `-13656.06235578` |
| Objectives | 7 (resonant_freq, coupling_beta, peak_e_field, q0, max_modified_poynting, field_flatness, pulsed_heating) |
| Parameters | 13 |
| Orphan DE after run | **No** (only cstd.exe PID 10184, no DE window) |
| Manual taskkill | **No** |

---

## Warm-start run (Step B)

### Command

```
python -m workflows.rfgun_sao.run --config config.local.yaml --n-initial 1 --n-iter 0
```

### Config for warm-start

- `evaluation_database.enabled: true`
- `evaluation_database.warm_start.enabled: true`
- `evaluation_database.warm_start.max_priors: 1`
- `evaluation_database.success_reuse.enabled: false` (unchanged)
- `optimization.n_initial_samples: 1`
- `optimization.n_iterations: 0`

### Result

| Metric | Value |
|--------|-------|
| DB warm-start `found_rows` | 1 |
| `accepted_priors` | 1 |
| `rejected_rows` | 0 |
| `skipped_duplicates` | 0 (only 1 row in DB) |
| `skipped_checkpoint_duplicates` | 0 (no checkpoint) |
| Log line | `Warm-start merged: 0 checkpoint + 1 DB = 1 total (found=1, rejected=0, skipped_dup=0, ckpt_dup=0)` |
| Optimizer log | `Pre-loaded 1 prior evaluations; LHS set to 2 (base=1 - prior=1 + extra=0)` |
| Total DB rows after run | 3 (1 seed + 2 new LHS evaluations) |
| Best F (warm-start run) | `-95592.43649047` |
| Orphan DE after run | **No** (only cstd.exe PID 10184, no DE window) |
| Manual taskkill | **No** |

### Prior injection evidence

The DB prior was loaded as an optimizer observation BEFORE any CST
evaluation started.  The optimizer log confirms:

```
Pre-loaded 1 prior evaluations
```

This proves the DB prior was injected without calling the evaluator
or the retry runtime.  The 2 new LHS evaluations that followed were
proposed by the optimizer and used actual CST solves, as expected.

### Success reuse evidence

No ``success_reuse`` or ``SR`` log lines appeared in the runtime log.
Success reuse remained disabled throughout the warm-start run,
confirming independence of warm-start and success-reuse configs.

### JSONL sidecar evidence

JSONL records were disabled in the config (``records.enabled: false``).
No ``.jsonl`` file was created.  JSONL sidecar is not a warm-start source.

---

## Artifact policy

| Artifact | Generated | Committed |
|----------|-----------|-----------|
| `config.local.yaml` | Yes | **Not committed** |
| `warm_start_smoke.db` | Yes | **Not committed** |
| `workflow1.ckpt` | No | **Not committed** |
| `*.jsonl` | No | **Not committed** |
| `workflow_1_runtime.log` | Yes | **Not committed** |
| CST output dirs | No | **Not committed** |
| `scripts/inspect_db.py` | Yes | **Not committed** |

---

## Safety

| Check | Status |
|-------|--------|
| Destructive COM kill | **Not performed** |
| Manual taskkill | **Not used** |
| Failure reuse | **Not implemented** |
| Probably-infeasible skip | **Not implemented** |
| Default config changed | **Not changed** |
| `run_workflow_1.py` modified | **No** |
| `src/cst_optimization/` modified | **No** |
| `workflows/rfgun_single_pass/` modified | **No** |

---

## Risk assessment

- **Bounded scope**: 1 initial + 0 BO = 1 evaluation planned per run;
  actual evaluations were 1 (seed) and 2 (warm-start, due to optimizer
  minimum LHS policy).
- **No orphan DE**: Both runs closed cleanly with `closed=True`.
  Only the licensing daemon ``cstd.exe`` remains running (pre-existing).
- **No manual taskkill required**: No CST DE window leaked.
- **No config enablement**: Default ``config.yaml`` unchanged.
  Warm-start remains opt-in only.
- **No production claim**: This was a bounded smoke with 3 total CST
  solves across both runs.  No production campaign was conducted.
- **No performance improvement claim**: Best F improved from -13656
  to -95592, but this is a single-run observation with 3 total solves
  and the comparison is between two different optimizer paths (seed
  vs warm-start, each with 1-2 evaluations).  No statistical
  significance.  The observed improvement is consistent with the
  optimizer having an additional prior observation, but should not be
  interpreted as a performance guarantee.

---

## Final HEAD commit SHA

**To be confirmed by reviewer.**
