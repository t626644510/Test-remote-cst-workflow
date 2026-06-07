# W2-10A Orchestrator Boundary Assessment

**Date:** 2026-06-08
**Branch:** `analysis/w2-10-orchestrator-boundary`
**Status:** Decision-only; no code moved.

---

## 1. Import Consumer Inventory

```
git grep -n "DualProjectOrchestrator" | grep -v "^_docs/\|^reports/"
```

| File | Line(s) | Usage |
|------|---------|-------|
| `src/cst_optimization/core/orchestrator.py` | 68 | **Definition** — class `DualProjectOrchestrator` |
| `src/cst_optimization/factory.py` | 24, 329, 348, 646 | **Type annotation only** — import + return-signature type hints |
| `workflows/rfgun_hom_antenna/workflow.py` | 19, 63, 81, 211 | **Sole runtime consumer** — import, type annotation, construction |
| `tests/workflows/test_workflow2_characterization.py` | 972, 1040, 1059 | Type reference in docstrings |

```
git grep -n "ProjectSpec"
```

| File | Line(s) | Usage |
|------|---------|-------|
| `src/cst_optimization/core/orchestrator.py` | 44 | **Definition** — dataclass |
| `src/cst_optimization/factory.py` | 24 | Type annotation only |
| `workflows/rfgun_hom_antenna/workflow.py` | 19, 126, 128 | Import, list construction |

**Key finding:** No other workflow (WF1, WF3) imports, constructs, or tests
`DualProjectOrchestrator` or `ProjectSpec`. WF1 returns a `_Workflow1Container`;
WF3 returns a `RecoveryWorkflowEvaluator`. Both have different orchestration
models.

---

## 2. Construction Site Inventory

| Site | Line | Context |
|------|------|---------|
| `workflows/rfgun_hom_antenna/workflow.py` | 211 | `orchestrator = DualProjectOrchestrator(...)` — sole construction |

The orchestrator is built once, inside `build_workflow_2()`, and returned to the
runner. The `src/cst_optimization/factory.py` compatibility wrapper delegates
to this builder and only references the type for annotation purposes.

---

## 3. Responsibility Split

### 3.1 Genuinely generic (candidate for shared core)

| Responsibility | Lines | Notes |
|---------------|-------|-------|
| `ProjectSpec` dataclass | 44–67 | Simple data holder (`cst_path`, `label`, `is_pre_filter`, `condition_trigger`, `condition_max_penalty`). Could be generic but currently WF2-only in its field semantics. |
| CST connection lifecycle | 78–97 (`__init__`), `close_all_connections` | DE create/close/reset is a CST infrastructure concern. |
| Solver runner delegation | `_execute_phase_1`, solver calls | Delegates to `SolverRunner` — already a generic utility. |
| Result reader management | `_make_recording_reader`, etc. | Parameterized by project paths; could be generic. |
| Phase loop structure | `execute()` main loop | Generic multi-project sequential execution pattern with conditional skipping. |

### 3.2 Workflow2-specific (not suitable for shared core without redesign)

| Responsibility | Lines | WF2 Coupling |
|---------------|-------|-------------|
| Phase labels `"f2f"`, `"f2w"`, `"f2wo"` | 146–163, 210–266 | Hard-coded string literals referencing RF gun HOM antenna projects. |
| `is_pre_filter` semantics | 58, 125, 220–235, 624–733 | Pre-filter is a WF2 concept (antenna absorption check on F2F project). |
| `condition_trigger` / `condition_max_penalty` | 60–61, 332–340 | Conditional project gating is WF2-specific (wakefield triggered by antenna absorption). |
| `.npz` replay (`start_phase="f2w"`) | 210–235 | F2F S-parameter replay for crash recovery is WF2-specific. |
| `_save_phase_npz` / `_has` dict | 540–563, 748–751 | Curves DB with `has_f2f`, `has_f2w`, `has_f2wo` flags. |
| `_last_completed_labels` | 138, 214, 230, 574 | Phase-completion tracking for retry/recovery — coupled to WF2 phase names. |
| `_pre_filter_enabled` / `_check_pre_filter` | 85–86, 113–114, 723–733, 853–875 | Antenna absorption threshold check — WF2-specific concept. |
| `_adaptive_gate` integration | 94, 119, 331–340, 484–496 | Adaptive conditional gate — WF2-specific optimization strategy. |
| `curves_db_dir` | 92, 118, 166, 202, 540–563 | Raw curves database — WF2-specific data management. |

### 3.3 CST infrastructure (CST-wrapper concern, not orchestrator concern)

| Responsibility | Lines | Notes |
|---------------|-------|-------|
| DE close with COM hang handling | `close_all_connections`, inter-pass reset | CST COM-specific cleanup; could be factored into `CSTConnection`. |
| `_make_recording_reader` | 781+ | CST ResultReader wrapper; belongs in result/wrapper layer. |
| Mesh error recovery (`rebuildlength`) | Phase 1.5 wakefield retry | CST solver mesh tuning; specific to WF2 wakefield solver behavior. |

---

## 4. Risk Assessment

### Option A: Keep in shared core (recommended)

| Risk | Level | Notes |
|------|-------|-------|
| Shared core bloat | Low | The orchestrator is already in shared core and has been stable since W2-0. |
| Misleading reuse signals | Medium | Other developers may assume it is generic when it is WF2-specific. |
| Import coupling from factory | Low | Factory's type reference is a compatibility wrapper; could be forward-declared. |
| Maintenance cost | Low | No current need to split; W2-10 can be deferred indefinitely. |

### Option B: Move whole class into WF2 package

| Risk | Level | Notes |
|------|-------|-------|
| Factory compatibility break | **High** | `factory.py::build_workflow_2` return type references `DualProjectOrchestrator`. Importing from `workflows.rfgun_hom_antenna` would violate the forbidden-import rule (SAO consolidation). |
| Circular import risk | Medium | Factory → WF2 → factory. Needs careful lazy import or type stub. |
| Test breakage | Medium | 42 characterization tests reference the type; would need import path updates. |
| Benefit | Low | No cross-workflow reuse pressure exists. |

### Option C: Split (small generic core + WF2-specific wrapper)

| Risk | Level | Notes |
|------|-------|-------|
| Premature abstraction | **Medium** | No second consumer proves the interface is correct. |
| Regression risk | **High** | 955-line orchestrator would be rewritten; live CST re-validation is expensive. |
| Implementation cost | **High** | Requires design, implementation, migration, and re-validation of ~900 lines. |
| Long-term benefit | Medium | A clean generic interface would help if a multi-project workflow appears in WF4+. |

---

## 5. Recommendation

**Decision:** Keep `DualProjectOrchestrator` in
`src/cst_optimization/core/orchestrator.py` for now.  **No move in W2-10.**

**Rationale:**

1. **Zero cross-workflow reuse evidence.** WF1 uses `_Workflow1Container`; WF3
   uses `RecoveryWorkflowEvaluator`. Neither imports or references
   `DualProjectOrchestrator`. Moving to WF2 would add no benefit and increase
   factory coupling risk.

2. **High concrete coupling.** The orchestrator has deep WF2-specific phase
   labels (`f2f`, `f2w`, `f2wo`), pre-filter semantics, adaptive gate
   integration, curves DB management, and `.npz` replay. Moving it to the
   WF2 package is architecturally cleaner, but the factory type-reference
   problem makes this riskier than it's worth at this stage.

3. **Factory compat risk is real.** `factory.py::build_workflow_2` returns a
   `DualProjectOrchestrator` type annotation. Breaking this would either
   violate the SAO consolidation forbidden-import rule or require a type stub
   — both are scope creep for W2-10.

4. **Cost/benefit is unfavorable.** A 955-line orchestrator refactor would
   require live CST re-validation (expensive, per W2-9 experience). The
   benefit — cleaner package boundaries — doesn't justify the risk without
   a second consumer.

5. **The current location is acceptable.** The orchestrator is stable, well-
   tested (42 characterization tests pass), and reasonably scoped. Its WF2
   coupling is documented (see §3.2 above) and not misleading to readers.

### Proposed W2-10B scope

**No-op.** W2-10 is closed as decision-only. If a future WF4 or cross-workflow
need arises:
- First extract `ProjectSpec` into a generic `core/specs.py` (simple data
  class, no runtime behavior).
- Then extract a generic `MultiProjectRunner` ABC with `execute()` and
  `close()`.
- Only then migrate WF2-specific phase/gate logic into the WF2 package.

---

## 6. Validation

```
python -m pytest tests/workflows/test_workflow2_builder_seam.py \
                  tests/workflows/test_workflow2_characterization.py -q
# 42 passed in 0.82s
```

No runtime code changes. No live CST run.

---

## 7. Residual Risks

1. **Factory type annotation dependency** — `factory.py` still imports
   `DualProjectOrchestrator` for type hints. This is cosmetic (a type
   annotation) but should be addressed if the class ever moves.
2. **No generic reuse path** — future multi-project workflows would either
   duplicate or re-extract from this orchestrator. This risk is accepted
   pending an actual second consumer.
3. **Orchestrator continues to grow** — if W2-11+ features add more
   WF2-specific code to the orchestrator, the boundary problem worsens.
   Recommended: any new phase/project logic should be added via
   Workflow2-local wrapper or parameterization, not by extending
   `DualProjectOrchestrator`.
