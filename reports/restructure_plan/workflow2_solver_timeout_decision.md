# W2-6B: Solver Timeout Decision Record

**STATUS: Historical analysis.  Superseded by W2-6F.**

W2-6B characterised the R2 mismatch.  W2-6F implemented the fix:
``workflow_2.optimization.solver`` now overrides fallback ``workflow_2.solver``
for overlapping keys.  Effective Workflow2 timeout is **7200.0** from
``workflow_2.optimization.solver.stagnation_timeout_s``.

See the supersession note at the bottom of this document for the full
transition.

## Current Observed Behaviour (at W2-6B time)

### Config Values

```
config/default.yaml
├── solver.stagnation_timeout_s = 300.0         (top-level fallback)
└── workflow_2
    └── optimization
        └── solver.stagnation_timeout_s = 7200.0 (intent — NOT consumed)
```

### Builder Read Path

`workflows/rfgun_hom_antenna/workflow.py` line 144–148:
```python
solver_cfg = config.get("solver", {})
solver_runner = SolverRunner(
    timeout_s=solver_cfg.get("stagnation_timeout_s", 0.0),
)
```

Where `config` is the `workflow_2` section dict after root-runner fallback merge.

### Root Runner Merge (run_workflow_2.py lines 93–101)

The root runner copies top-level `cst`, `solver`, `logging` into the
`workflow_2` section **only when those keys are absent** from `workflow_2`.
Since `workflow_2.solver` is not a direct key (the only solver sub-key is
`workflow_2.optimization.solver`), the top-level `solver` is merged in,
making `workflow_2.solver.stagnation_timeout_s = 300.0`.

### W2-1 Characterisation Confirmation (historical — superseded for timeout)

- ``test_solver_timeout_comes_from_merged_solver_section``: `SolverRunner`
  receives 300.0 when post-merge config has `workflow_2.solver`.
- ``test_solver_timeout_falls_back_to_default_when_missing``: when no solver
  section exists, `SolverRunner` defaults to 7200.0.
- ``test_optimization_solver_now_consumed_by_builder`` (W2-6F): intentionally
  sets `optimization.solver` to 9999.0; confirms builder NOW reads it.
  (Previously ``test_optimization_solver_key_is_not_read_by_builder`` which
  asserted the old W2-6B-era behaviour.)

### Summary (at W2-6B time)

| Value | Source | Consumed (historically)? |
|-------|--------|--------------------------|
| 300.0 | Top-level `solver` fallback | ✅ Yes — merged by root runner, read by builder |
| 7200.0 | `workflow_2.optimization.solver` | ❌ No — ignored (historical; consumed as of W2-6F) |
| 0.0 (→7200.0) | Builder default when solver absent | ✅ Yes — `SolverRunner` coerces ≤0 to `_DEFAULT_TIMEOUT_S` |

---

## Historical W2-6B Decision Options

### Option A: Preserve + Document (Historical W2-6B recommendation — superseded by W2-6F)

Leave current runtime behaviour unchanged.  At W2-6B time,
`workflow_2.optimization.solver.stagnation_timeout_s` was a non-functional
intent that the builder did not consume.  W2-6F changed this:
`optimization.solver` now overrides fallback `workflow_2.solver` for
overlapping keys, and the effective timeout is 7200.0.

**Pros**:
- Zero behaviour change risk.
- No config migration needed.
- W2-1 characterisation tests already pass.
- W2-6B can be purely documentary.

**Cons**:
- Stale config value may confuse future developers/operators.
- Intent (7200s) is silently ignored.

**Required validation**:
- W2-1 P0.2 tests remain as regression.
- Add tests documenting the mismatch explicitly (this W2-6B phase).
- No CST needed.

### Option B: Move Config Layout

Add a direct `workflow_2.solver.stagnation_timeout_s` to
`config/default.yaml`, duplicate or move the 7200.0 value there, and mark
`workflow_2.optimization.solver` as deprecated.

**Pros**:
- Makes the consumed config path explicit.
- `optimization.solver` can be removed after a deprecation period.

**Cons**:
- Requires `config/default.yaml` changes (forbidden in W2-6 planning).
- May confuse operators who expect the value under `optimization`.
- If only added (not moved), creates two sources of truth with different
  precedence rules.

**Required validation** (for a future implementation phase):
- Update W2-1 P0.1 config-merge tests.
- Update W2-1 P0.2 solver-timeout tests.
- Confirm no consumer reads `workflow_2.optimization.solver` directly
  (search `src/`, `workflows/`, `tests/`).
- No-CST only.

### Option C: Change Builder Precedence

Modify `build_workflow_2` to read `optimization.solver.stagnation_timeout_s`
before falling back to `config["solver"]`.

**Pros**:
- Makes the intent value (7200s) actually take effect.
- Minimal code change in one file.

**Cons**:
- Changes effective timeout from 300s to 7200s for all evaluations.
- May mask genuine solver hangs (wakefield solver could hang for 2h before
  timeout).
- Requires careful operator communication.
- High blast radius for a quick decision.

**Required validation** (for a future implementation phase):
- Update W2-1 P0.2 tests to expect 7200s.
- Add explicit test for the new precedence rule.
- Optional: run a limited live CST smoke test with the new timeout to
  confirm wakefield solves still complete in reasonable time.
- Historical W2-6B gate: run no-CST tests first. Current live-smoke gating is
  governed by `agent_operating_charter.md`.

---

## Current Implementation (W2-6F, supersedes W2-6B Recommendation)

**Decision implemented**: `workflow_2.optimization.solver` now overrides
fallback `workflow_2.solver` for overlapping keys.  The Workflow2 builder
(``workflows/rfgun_hom_antenna/workflow.py``) merges both configs with
``optimization.solver`` taking precedence.

**Effective result** under ``config/default.yaml`` after root-runner merge:
- `stagnation_timeout_s` = **7200.0** (from `workflow_2.optimization.solver`)
- `settle_s` = **2.0** (from fallback `workflow_2.solver`, not overridden)

**Validation**: 34 characterization tests pass, including
``test_actual_timeout_is_7200_via_real_config`` (loads real config, builds
with mock CST, asserts 7200.0) and
``test_optimization_solver_overrides_fallback`` (asserts precedence).

---

## Recommendation (historical — superseded by W2-6F)

**Option A: Preserve + Document.**

Rationale:
1. The current 300s timeout has been the effective behaviour throughout all
   W2-0 through W2-6D phases.  No operational complaint about solver
   timeouts has been recorded.
2. Changing to 7200s (Option C) is a runtime behaviour change that should
   be a deliberate operational decision with its own implementation phase,
   acceptance criteria, and live CST validation — not conflated with
   documentation/planning.
3. Option B (config layout change) is premature without first deciding
   whether the timeout value itself should change.

**W2-6F adopted Option C.**  No-CST validation is covered by current tests
(``test_actual_timeout_is_7200_via_real_config``,
``test_optimization_solver_overrides_fallback``, etc.).  Live CST smoke
remains recommended before production deployment but was not run in this
phase.

---

## Supersession Note — W2-6F

**W2-6B Option A (Preserve + Document) was superseded by W2-6F.**
The unacceptable bug that `workflow_2.optimization.solver.stagnation_timeout_s`
= 7200.0 was silently ignored has been fixed.

**Implemented decision (W2-6F)**: Workflow2-local `optimization.solver`
overrides the root/top-level fallback solver for overlapping keys.
Fields not set in `optimization.solver` (e.g. `settle_s`) still fall back
to `workflow_2.solver`.

**Validation**: see W2-6B Options C validation list above.  No-CST tests
updated; live CST smoke recommended but not run.

---

## Tests Added in W2-6B

| Test (historical W2-6B name → current W2-6F name) | Purpose | Type |
|------|---------|------|
| `test_actual_timeout_is_300_via_real_config` → `test_actual_timeout_is_7200_via_real_config` | Load real config, apply root merge, assert 7200.0 from `optimization.solver` | No-CST |
| `test_mismatch_intent_is_7200` → `test_workflow2_timeout_intent_is_7200` | Assert `optimization.solver.stagnation_timeout_s == 7200.0` exists in real config | No-CST |
| `test_builder_precedence_solver_wins_over_optimization_solver` → `test_optimization_solver_overrides_fallback` | Set both paths; assert `optimization.solver` wins (2222.0) | No-CST |
| `test_fallback_solver_used_when_optimization_solver_absent` | When `optimization.solver` absent, fallback to `workflow_2.solver` (300.0) | No-CST |
| `test_settle_s_falls_back_to_solver` | `settle_s` not in `optimization.solver`, falls back to `workflow_2.solver` | No-CST |

## Appendix: Validation Commands

```powershell
python -m pytest tests/workflows/test_workflow2_characterization.py -q
python -m pytest tests/workflows/test_workflow2_scheduler_shim.py -q
```
