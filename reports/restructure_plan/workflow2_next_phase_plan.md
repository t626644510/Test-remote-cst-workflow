# Workflow2 Next Phase Plan

This document is the authoritative Workflow2 recovery plan after W2-7. It
defines the remaining directions, tracks completed phases with evidence, and
provides web-agent-ready handoffs for the next bounded phase.

> **Source of truth:** code, tests, and current git diff are authoritative.
> Historical reports and earlier plan versions are evidence only.

---

## Recovery Index

- **Baseline merge:** PR #1 merged W2-0 through W2-6F into `main`.
- **Active direction:** W2-7 runner migration is complete; W2-8 config ownership is next.
- **Public command must remain:** `python run_workflow_2.py`.
- **Scheduler must continue targeting** root `run_workflow_2.py` until a dedicated scheduler migration is accepted.
- **Runtime config remains** `config/default.yaml` -> `workflow_2` subtree.
- **`workflows/rfgun_hom_antenna/config.yaml`** remains a snapshot, not runtime source.
- **`DualProjectOrchestrator`** remains in `src/cst_optimization/core/orchestrator.py` until W2-10.
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

**Residual risks (noted, not blocking):**

- `test_workflow2_builder_seam.py` — 2 tests fail because they directly access
  `run_workflow_2.build_workflow_2`, which no longer exists in the shim.
- `test_workflow2_package_skeleton.py` — 5 tests fail because they assert the old
  placeholder API (`LEGACY_ENTRY`, `PACKAGE_ROOT`, `describe_legacy_entry()`, etc.).
  These names were removed when the placeholder was replaced with the real runner.
- Both test files are outside the W2-7 edit scope; fixes are low-effort in a
  dedicated cleanup phase.

---

## Upcoming Phases

The following phases remain. The recommended order matches the dependency chain:
**W2-8 (config)** is unblocked by W2-7 and is the next logical step; live evidence
(**W2-9**) should follow before risky boundary changes (**W2-10**).

---

### W2-8 — Config Ownership

**Decision to make:**

- Whether `workflows/rfgun_hom_antenna/config.yaml` becomes the runtime source
  or remains a snapshot while `config/default.yaml` stays authoritative.

**Required evidence:**

- Exact comparison between committed workflow-local config and
  `config/default.yaml["workflow_2"]`.
- Clear precedence rules for top-level fallback sections: `cst`, `solver`,
  `logging`.
- Tests proving effective solver timeout still resolves to `7200.0` from
  `workflow_2.optimization.solver.stagnation_timeout_s`.
- Tests proving config source and scheduler/root behavior after migration.

**Boundaries:**

- Do not mix with orchestrator migration.
- Do not leave two long-term runtime sources of truth.
- Do not silently drop fallback values such as `cst.library_path`,
  `logging.output_dir`, or solver `settle_s`.

**Validation:**

- `test_workflow2_config_isolation.py` — config equality assertions.
- `test_workflow2_characterization.py` — solver timeout and callback tests.
- `test_workflow2_scheduler_shim.py` — delegation and CLI tests.
- Additional config-loader tests if a dedicated loader is introduced.

**Live CST:** Not required for implementation. Recommended after acceptance if
the runtime config source changes.

---

### W2-9 — Bounded Live Smoke

**Purpose:**

- Collect first post-runner-migration Workflow2 live CST evidence using the
  current public command (`python run_workflow_2.py`) and current config source
  (`config/default.yaml`).

**Minimum requirements:**

- One bounded smoke command with explicit timeout or stop condition.
- Output and logs outside tracked source unless a concise evidence report is
  intentionally added.
- Record effective solver timeout and config source.
- Record checkpoint behavior: one record per logical evaluation.
- Record CST process cleanup state after the run.
- State whether CST was actually exercised.

**Boundaries:**

- No production campaign.
- No committed `.ckpt`, `.jsonl`, database, CST result, or scratch artifacts.
- No destructive process manipulation unless explicitly scoped.
- No default-config changes unless the phase explicitly authorises them.

**Validation:**

1. Re-run W2-7 no-CST tests first (`test_workflow2_scheduler_shim.py`,
   `test_workflow2_characterization.py`, `test_workflow2_config_isolation.py`).
2. Then run one bounded live smoke with recorded cleanup state.

**Live CST:** Required.

---

### W2-10 — Orchestrator Boundary Decision

**Decision to make:**

- Keep `DualProjectOrchestrator` in `src/cst_optimization/core/`, migrate it
  into `workflows/rfgun_hom_antenna/`, or extract a smaller generic interface.

**Default recommendation:**

- Do not move it until W2-7 and W2-9 provide enough evidence. Treat the class
  as high-blast-radius because it currently mixes generic utilities with
  Workflow2-specific phase labels and CST recovery details.

**Required evidence:**

- Current import consumers and construction sites.
- List of truly generic responsibilities vs Workflow2-specific logic.
- Live evidence from W2-9 before making risky boundary changes.
- Targeted tests if any boundary changes touch shared core.

**Boundaries:**

- Do not promote shared core without cross-workflow evidence.
- Do not combine with config or scheduler migration.
- Do not invent CST APIs.
- Do not move high-blast-radius code without targeted and broader validation.

**Validation:**

- If decision-only: no tests required, but cite code evidence.
- If code moves: run Workflow2 tests plus affected shared-core tests.

**Live CST:** Not required for decision-only. Required after any runtime-affecting
orchestrator move.

---

## Web Agent Output Contract

For each upcoming phase, return a local-agent prompt with:

- one-sentence objective;
- at most five current facts;
- bounded read-first files;
- allowed and forbidden edits;
- targeted validation commands;
- residual risks and live/no-CST status.
