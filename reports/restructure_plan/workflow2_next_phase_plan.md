# Workflow2 Next Phase Plan

This document is the authoritative Workflow2 recovery plan after W2-7. It
defines the remaining directions, tracks completed phases with evidence, and
provides web-agent-ready handoffs for the next bounded phase.

> **Source of truth:** code, tests, and current git diff are authoritative.
> Historical reports and earlier plan versions are evidence only.

---

## Recovery Index

- **Baseline merge:** PR #1 merged W2-0 through W2-6F into `main`.
- **Active direction:** W2-7 through W2-10 are complete. See `workflow2_w2_10_orchestrator_boundary_assessment.md` for the W2-10A decision.
- **Public command must remain:** `python run_workflow_2.py`.
- **Scheduler must continue targeting** root `run_workflow_2.py` until a dedicated scheduler migration is accepted.
- **Runtime config source (W2-8):** `workflows/rfgun_hom_antenna/config.yaml` — contains `workflow_2` subtree plus top-level `cst`, `solver`, `logging` fallback sections.
- **`config/default.yaml["workflow_2"]`** is legacy/compatibility reference, not runtime source.
- **`DualProjectOrchestrator`** remains in `src/cst_optimization/core/orchestrator.py` per W2-10A (decision: keep for now, no move).
- **Do not treat live CST smoke and no-CST validation as interchangeable.**

---

## Completed Phases

### W2-7 — Root Shim / Package Runner Migration

**Goal:** Move Workflow2 runner ownership into
`workflows/rfgun_hom_antenna/run.py`, while keeping `run_workflow_2.py` as the
public compatibility shim.

**Status:** Accepted and merged into the active branch.

**Current evidence:**

| Item | Value |
|------|-------|
| Branch | `refactor/workflow2-runner-migration` |
| Commit | `1d3a39e6195b2df6643d3418027da8f8798e0343` |
| Base | W2-0 through W2-6F in `main` (commit `b1829c6`) |

**Runtime ownership after W2-7:**

| Concern | Owned by |
|---------|----------|
| CLI arg parsing | `workflows/rfgun_hom_antenna/run.py` — `main()` |
| Config load + fallback merge | `workflows/rfgun_hom_antenna/run.py` — `main()` |
| Checkpoint init + heartbeat | `workflows/rfgun_hom_antenna/run.py` — `main()` |
| Warmup from DB | `workflows/rfgun_hom_antenna/run.py` — `main()` |
| Partial eval resume | `workflows/rfgun_hom_antenna/run.py` — `main()` |
| Orchestrator + optimizer build | `workflows/rfgun_hom_antenna/workflow.py` — `build_workflow_2()` |
| Optimisation loop + shutdown | `workflows/rfgun_hom_antenna/run.py` — `main()` |
| Public command target | `run_workflow_2.py` (shim: `from workflows.rfgun_hom_antenna.run import main`) |
| Scheduler contract | `run_workflow_2.py` — CLI flags preserved, same path |

**Changed files:**

- `workflows/rfgun_hom_antenna/run.py` — placeholder → full runtime body (+369/-47)
- `run_workflow_2.py` — 330-line runner → thin shim (-324/+7)
- `tests/workflows/test_workflow2_scheduler_shim.py` — delegation/CLI tests (+127/-80)
- `tests/workflows/test_workflow2_characterization.py` — patch targets repointed (+5/-5)

**Validation:**

```
python -m pytest tests/workflows/test_workflow2_scheduler_shim.py \
                  tests/workflows/test_workflow2_characterization.py \
                  tests/workflows/test_workflow2_config_isolation.py -q
# 62 passed in 0.87s
```

**Live CST:** Not run. W2-9 is the first required live evidence gate.

**Acceptance verification:**

1. **Root command stable** — `python run_workflow_2.py --help` works (shim delegates to `run.py`).
2. **Scheduler contract stable** — `scripts/schedule_workflow2.ps1` still references
   `run_workflow_2.py --auto-resume --heartbeat`; AST tests pin the three flag names.
3. **Runtime source unchanged** — `config/default.yaml` remains the config source;
   fallback merge (`cst`, `solver`, `logging`) is preserved in `run.py/main()`.
4. **Package runner owns runtime** — `workflows/rfgun_hom_antenna/run.py` now contains
   the full `main()` with args, config, checkpoint, heartbeat, warmup, partial
   recovery, build, optimisation loop, and shutdown.
5. **Signal handler moved inside `main()`** — parity with WF1 pattern; no side
   effects on import.
6. **No new CST API assumptions** — all API calls use existing wrappers.

**Residual risks (noted, resolved in W2-7 closure):**

- `test_workflow2_builder_seam.py` and `test_workflow2_package_skeleton.py` — placeholder
  API tests were updated in W2-7 closure to match the real runner interface.
  All Workflow2 no-CST tests now pass.

---

### W2-8 — Config Ownership Migration

**Goal:** Make `workflows/rfgun_hom_antenna/config.yaml` the Workflow2
runtime config source, replacing the `config/default.yaml -> workflow_2` path.

**Status:** Accepted and merged into the active branch.

**Current evidence:**

| Item | Value |
|------|-------|
| Branch | `refactor/workflow2-config-ownership` |
| Base | `main` (W2-7 + W2-9 complete) |
| Runtime config source | `workflows/rfgun_hom_antenna/config.yaml` |
| Fallback sections | `cst`, `solver`, `logging` at top level of local config |
| Effective solver timeout | `7200.0` from `workflow_2.optimization.solver.stagnation_timeout_s` |
| `config/default.yaml` status | Legacy: not read by Workflow2 runner |

**Config loader (`_load_workflow2_config` in `run.py`):**

- Reads the co-located `config.yaml` by default.
- Extracts `workflow_2` subtree and merges top-level `cst`, `solver`, `logging`
  as fallbacks (same merge logic as pre-W2-8, only source path changed).
- Loader is testable independently of `main()`.

**Changed files:**

- `workflows/rfgun_hom_antenna/config.yaml` — added `cst`, `solver`, `logging`
  fallback sections; updated header from "snapshot" to "runtime source".
- `workflows/rfgun_hom_antenna/run.py` — added `_load_workflow2_config()`;
  `main()` now calls it instead of reading `config/default.yaml`.
- `tests/workflows/test_workflow2_config_isolation.py` — replaced exact-match
  test with runtime-source, precedence, and loader tests.
- `tests/workflows/test_workflow2_scheduler_shim.py` — updated config path
  assertion from `config/default.yaml` to `config.yaml`.
- `tests/workflows/test_workflow2_characterization.py` — added
  `TestCompletedEvaluationCheckpoint` (mocked orchestrator, real
  CheckpointManager).

**`config/default.yaml` NOT committed** in this phase.

**Validation:**

```
python -m pytest tests/workflows/ -q
# 1238 passed, 1 failed (pre-existing WF1 warm-start test) in 3.20s
```

**Live CST:** Not run (W2-8 is no-CST only). W2-9 was already run before W2-8.

**Residual risks:**

- `config/default.yaml` still has a legacy `workflow_2` subtree. A future
  cleanup phase should decide whether to remove or deprecate it.
- Scheduler still targets root `run_workflow_2.py` — but the shim delegates
  correctly and the config path change is transparent to the scheduler.
- WF1 test failure (`test_warm_start_does_not_reference_jsonl`) is pre-existing
  and unrelated.

---

## Upcoming Phases

**All W2-0 through W2-10 phases are complete.** No remaining recovery phases.
Future work (WF4 multi-project extraction, legacy `config/default.yaml` cleanup)
is unplanned and not part of the W2 recovery plan.

---

### W2-10A — Orchestrator Boundary Decision ✅ done

**Decision:** Keep `DualProjectOrchestrator` in `src/cst_optimization/core/`.

**Rationale:** Zero cross-workflow reuse evidence (WF1 and WF3 use different
orchestration models).  Moving to WF2 package would create factory import
coupling and circular-dependency risk.  Splitting would be premature abstraction
without a second consumer.  See `workflow2_w2_10_orchestrator_boundary_assessment.md`.

**W2-10B:** No-op / decision-only. Future movement should wait for a
proven second consumer (e.g. WF4), then extract `ProjectSpec` first, then a
generic `MultiProjectRunner` ABC, then migrate WF2-specific logic.

---

## Web Agent Output Contract (reference — no upcoming phases)

All W2 recovery phases are complete. This contract is preserved for future
workflow planning outside the W2 scope. Each new phase prompt should include:
one-sentence objective, ≤5 facts, bounded read set, edit scope, targeted
validation, residual risks, and live/no-CST status.
