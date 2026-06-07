# W2-9 Bounded Live CST Smoke Evidence Report

**Date:** 2026-06-08
**Branch:** `main`
**Commit:** `7363a7d85c567ac266efda64cda3ece4032988e6`
**Status:** Live smoke executed, interrupted by operator decision.  Acceptable as
post-W2-7 no-CST gate before W2-8 config ownership.

---

## Command Run

```
cd <repo_root>
python run_workflow_2.py --heartbeat
```

The public root command (`run_workflow_2.py` → compatibility shim → `run.py`)
was used.  The scheduler was NOT invoked; this was a direct terminal invocation.

---

## Temporary Config Bounds

The following values were temporarily changed in `config/default.yaml` to bound
the live smoke.  All values were **restored to the committed state** before this
report was committed (`git checkout -- config/default.yaml`; confirmed via
`git diff --stat config/default.yaml` showing no output).

| Key | Committed | Bounded (temp) |
|-----|-----------|----------------|
| `logging.output_dir` | `D:/Results` | `D:/Results/w2_9_smoke` |
| `workflow_2.message_log.output_dir` | `D:/Results/cst_messages` | `D:/Results/w2_9_smoke/cst_messages` |
| `workflow_2.optimization.n_initial` | `10` | `1` |
| `workflow_2.optimization.n_iterations` | `50` | `0` |
| `workflow_2.optimization.retry.enabled` | `true` | `false` |
| `workflow_2.optimization.retry.max_tier3` | `2` | `0` |
| `optimization.retry.enabled` | `true` | `false` |
| `workflow_2.adaptive_gate.warmup_n_evaluations` | `10` | `0` |

**Unchanged:** `workflow_2.optimization.solver.stagnation_timeout_s` remained
`7200.0` (the effective Workflow2 solver timeout per W2-6F).

---

## Runtime Observations

### Startup

```
Parameters: 14
Objectives: 4
Constraints: 8
Algorithm: SurrogateAssistedOptimizer
Initial samples: 1,  Iterations: 0
```

The runner loaded 14 Workflow2 parameters, 4 objectives
(`z_longitudinal`, `z_transverse`, `antenna_absorption`,
`antenna_absorption_db`), and 8 constraints from the `workflow_2` subtree of
`config/default.yaml`.

### Phase 1 — Frequency-Domain (Non-Conditional)

```
[iter 0] selfangle1=146.6043, selfangle2=50.7339, inner_angle=-79.3652, ...
[Phase 1] Non-conditional projects (1)
  [frequency_domain] OK (123s, ? cells)
```

- **CST was exercised:** The frequency-domain solver ran on `F2F.cst` and
  completed in **123 seconds**.
- Pre-filter (absorption check) passed — `antenna_absorption raw=-13.12`.
- The message log was written to `D:/Results/w2_9_smoke/cst_messages/msg_frequency_domain_iter0000_20260608_012741.txt`.

### Inter-Pass Reset

```
[Inter-pass] Resetting DE before conditional projects
DesignEnvironment.close() hung (PID=40636) — abandoning COM thread.
[Inter-pass] New DE PID=52936
```

The orchestrator performed the inter-pass DesignEnvironment reset between
frequency-domain and wakefield phases.  The old DE hung on close (a known COM
behavior with CST), and a new DE was created successfully at PID 52936.

### Phase 1.5 — Wakefield (Conditional, Triggered)

```
[Phase 1.5] Conditional projects (2)
  [wakefield] TRIGGER — antenna_absorption raw=-13.12 penalty=1.000 [WARMUP — force run]
```

The `wakefield` project triggered because `antenna_absorption` exceeded the
threshold (raw=-13.12 > -29.0 dB).  The WARMUP phase forced the run (0
warmup evaluations configured).

### Operator Interruption

The operator (博士生) **manually interrupted** the run during the wakefield
computation with the following rationale:

> F2W与F2W_offset的计算时间非常长，我不希望等cst完全计算完他们，你最好能
> 手动中断，只要成功启动就认为其已经通过check了。

**Translation:** "F2W and F2W_offset computations take extremely long. I do not
want to wait for CST to finish computing them. You should manually interrupt.
Successful startup is sufficient to pass the check."

This rationale is accepted for W2-9.  The goals were: (a) confirm the public
entry command works after W2-7 runner migration, (b) confirm `config/default.yaml`
is read correctly, (c) confirm CST is exercised, (d) confirm the builder,
orchestrator, and optimizer chain initializes without error.  All four goals
were met before interruption.

---

## Config Source and Solver Timeout

- **Runtime config source:** `config/default.yaml` → `workflow_2` subtree
  (unchanged from pre-W2-7 state).
- **Effective solver timeout:** `7200.0` seconds, resolving from
  `workflow_2.optimization.solver.stagnation_timeout_s` via builder
  precedence (W2-6F).  This was **not changed** by the temporary bounds.

---

## Checkpoint Behavior

No checkpoint file was created because the single evaluation's `execute()` call
had not returned when the run was interrupted.  The checkpoint callback fires
from the evaluator wrapper AFTER `orchestrator.execute()` completes all phases.
Since `execute()` was blocked in the wakefield solver, the callback was never
invoked and no checkpoint was written.

This is consistent with the pre-W2-7 contract: the evaluator wrapper owns the
callback, and the callback fires exactly once per completed evaluation.

---

## Output and Log Paths

All outputs are outside the tracked repository at `D:/Results/w2_9_smoke/`:

| File | Size | Description |
|------|------|-------------|
| `workflow_2_heartbeat.txt` | 19 B | Heartbeat timestamp (last: `2026-06-08 01:30:07`) |
| `workflow_2_terminal.log` | 580 B | Terminal output log |
| `cst_messages/msg_frequency_domain_iter0000_20260608_012741.txt` | 2.3 KB | CST message log for F2F phase |

No `.ckpt`, `.jsonl`, `.db`, `.sqlite`, `.cst`, or result files were created.

---

## Cleanup State

| Item | State |
|------|-------|
| Python process | Stopped via `TaskStop` (sent SIGTERM to bash wrapper) |
| CST DesignEnvironment PIDs | DE1 PID=40636 (abandoned, hung on close); DE2 PID=52936 (active when run stopped). Both may still be running as orphan processes. |
| Pre-existing CST | `cstd` PID 8748 (from June 4, unrelated to this run) |
| Checkpoint | None created |
| Heartbeat | Last timestamp `2026-06-08 01:30:07`; file present at `D:/Results/w2_9_smoke/workflow_2_heartbeat.txt` |
| `config/default.yaml` | **Restored** to committed state (no diff) |

**Orphan CST note:** Two DesignEnvironment processes (PID 40636, PID 52936) may
still be alive.  These were created during the smoke run.  The operator should
manually verify and `taskkill` them if needed.  No destructive cleanup was used
— the run was interrupted, not killed with `os._exit(130)`.

---

## No-CST Validation

```
python -m pytest tests/workflows/test_workflow2_builder_seam.py \
                  tests/workflows/test_workflow2_package_skeleton.py \
                  tests/workflows/test_workflow2_scheduler_shim.py \
                  tests/workflows/test_workflow2_characterization.py \
                  tests/workflows/test_workflow2_config_isolation.py -q

# 76 passed, 1 failed in 1.16s
```

The single failure (`test_local_config_matches_global_workflow2_subtree`) is a
pre-existing `SystemError: unknown opcode` in the yaml scanner — a CPython
optimization bug, not a config content mismatch.  It reproduces on other
branches and is unrelated to W2-7 or W2-9 changes.

---

## W2-8 Readiness Assessment

W2-8 config ownership remains **deferred** as planned.  Key observations from
this smoke:

- The runner correctly reads `config/default.yaml` → `workflow_2` subtree.
- The fallback merge (`cst`, `solver`, `logging`) is preserved.
- The effective solver timeout (7200.0) is consumed via builder precedence.
- `workflows/rfgun_hom_antenna/config.yaml` was never read at runtime (it
  remains a snapshot, as designed).
- The public command and root shim delegation work correctly.

**Recommendation:** W2-8 can proceed when ready.  The config ownership decision
(swap runtime source or keep snapshot) should be informed by this evidence but
does not need additional live CST before implementation.

---

## Residual Risks

1. **Orphan CST processes** — DE PIDs 40636 and 52936 may still be running.
   Manual cleanup recommended before the next live run.
2. **F2W/F2WO wakefield solver duration** — confirmed very long (as expected).
   Future live smoke may benefit from a shorter timeout or single-phase-only
   mode.
3. **Checkpoint not tested** — the single evaluation was interrupted before
   callback fire.  Checkpoint behavior (one record per logical evaluation) was
   verified in no-CST tests but not exercised live.
4. **Scheduler not tested live** — only the direct `python run_workflow_2.py`
   command was run.  The scheduler (`scripts/schedule_workflow2.ps1`) was
   verified via static characterisation tests.
