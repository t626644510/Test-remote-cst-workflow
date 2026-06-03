# FS1 — failure / probably-infeasible skip policy design

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `FS1 — failure / probably-infeasible skip policy design, docs-only` |
| Base branch | `feature/wf1-extreme-com-recovery` |
| Base HEAD | `5bdf4bc8bf4fa1519baa1d49f51205ca2758aaac` (XR3 accepted) |
| New branch | `feature/wf1-failure-skip` |
| Live CST | **No** |
| Runtime skip implemented | **No** |
| Default config changed | **No** |
| Destructive action | **No** |

---

## 1. Current accepted baseline

| Capability | Status |
|------------|--------|
| Durable evaluation DB (v1 schema) | Merged in main |
| DB success reuse (opt-in, SUCCESS only) | Merged in main |
| DB warm-start (opt-in, SUCCESS priors only) | Merged in main |
| XR3 process-kill environment failure row (`solver_failed`) | Accepted; should not become skip evidence |
| Probably-infeasible (advisory-only) | Not used for skip/reuse/runtime discard |
| Environment faults excluded from skip evidence by default | XR2/XR2.1 policy |

---

## 2. Policy goals

1. **Explicit opt-in** — skip must be separately configured; not enabled by DB, success_reuse, or warm-start.
2. **Exact `parameter_key` initially** — no region-wide or proximity-based skip.
3. **Auditable** — every skip decision recorded with source evidence.
4. **Reversible** — config/policy change can disable or restrict skip.
5. **No synthetic SUCCESS** — skipped rows must not be mistaken for successful evaluations.
6. **No side effects** — skipped rows must not feed success reuse or warm-start as SUCCESS priors.
7. **Dry-run before enforce** — `dry_run` mode must come before `enforce`.
8. **Environment/COM/process-kill rows excluded** — these are transient; skip evidence must focus on deterministic, repeated exact-key failures.

---

## 3. Skip modes

| Mode | Evaluator called? | Retry called? | DB row written? | Skip decision recorded? | Use case |
|------|-------------------|---------------|-----------------|------------------------|----------|
| `disabled` | Yes (normal) | Yes (normal) | Yes (normal) | No | Default; no skip logic runs |
| `dry_run` | Yes (normal) | Yes (normal) | Yes (normal) | **Would_skip diagnostic** | Policy calibration; validate candidate rules before enforcement |
| `enforce` | **No** (skipped) | **No** (skipped) | **Synthetic skipped row** | **Enforced_skip** | Active skip after FS4 validation |

### Mode transition path

```
disabled (default, FS1)
  → dry_run (FS3, after candidate loader)
  → enforce (FS4, after dry-run validated)
```

---

## 4. Candidate evidence taxonomy

### Preferred potential skip evidence

| Category | Description | Default min_failures |
|----------|-------------|---------------------|
| Repeated deterministic gate rejection | Same parameter_key, same gate, rejected multiple times | 1-2 |
| Repeated calibration failure | Geometry/physics dependent, same exact key | 1-2 |
| Repeated solver failure at exact key | Not classified as environment fault | 2 |
| Repeated objective extraction failure | Deterministic, same exact key | 2 |
| Explicit probably-infeasible candidate | Produced by accepted future policy | 1 |

### Excluded from skip evidence by default

| Category | Reason |
|----------|--------|
| XR destructive process-kill rows | Transient; environment fault |
| COM connection lost | Transient; not geometry/physics |
| COM call hang | Transient |
| Cleanup close hang | Transient; cleanup artifact |
| License daemon / process ambiguity | Infrastructure issue |
| Unknown CST process state | Cannot classify |
| Single transient timeout | Insufficient evidence |
| Unknown exception | Cannot classify deterministically |
| Schema-incompatible row | Cannot validate |
| Raw-only row (no objective payload) | Insufficient data |
| SUCCESS rows | Not failures |
| Success reuse rows | Not failures; already reused |
| Warm-start prior rows | Not failures |

### Ambiguous evidence (dry-run only until enough repeated evidence)

| Category | Rationale |
|----------|-----------|
| `solver_timeout` | May be transient or deterministic; needs repeated exact-key evidence |
| `solver_failed` without taxonomy | Cannot classify without error details |
| Measurement extraction failure | May be project issue or transient |
| Calibration failure with incomplete context | Needs more context |

---

## 5. Minimum evidence thresholds (policy recommendations)

| Parameter | Default | Notes |
|-----------|---------|-------|
| `exact_key_min_failures` | 2 | Repeated failures at same parameter_key |
| `deterministic_gate_reject_min_failures` | 1-2 | Depends on gate determinism |
| `transient_failure_min_failures` | Disabled | Not allowed by default |
| `unknown_exception_min_failures` | Disabled | Not allowed by default |
| `environment_faults` | Disabled | Excluded by XR2 policy |
| `max_age_days` | Unset | Policy recommendation only |
| Schema compatible required | Yes | Row schema must match current version |
| Objective signature match required | Yes | Objective names must match |

These are **policy recommendations only** in FS1. Actual thresholds will be implemented in FS2+ as config-gated parameters.

---

## 6. Audit record requirements

Every `would_skip` or `enforced_skip` decision must record:

| Field | Description |
|-------|-------------|
| `skip_policy_version` | Version of the skip policy |
| `skip_mode` | `disabled`, `dry_run`, or `enforce` |
| `parameter_key` | Target parameter_key |
| `proposed_parameters` | Parameter values |
| `candidate_statuses` | Statuses of evidence rows |
| `evidence_count` | Number of evidence rows |
| `source_row_ids` | Row IDs of evidence |
| `source_run_ids` | Run IDs of evidence |
| `evidence_timestamps` | When evidence was recorded |
| `failure_taxonomy_categories` | Taxonomy categories |
| `compatibility_checks` | Schema/objective/config match results |
| `threshold_decision` | How thresholds were applied |
| `final_decision` | `no_candidate`, `would_skip`, `enforced_skip`, or blocked reason |
| `evaluator_called` | Whether evaluator ran |
| `retry_called` | Whether retry runtime was invoked |
| `budget_consumed` | Whether CST solve budget was consumed |
| `synthetic_status` | Status of synthetic row if enforce mode |
| `operator_override_id` | Manual override if applicable |

---

## 7. DB / schema implications

### Extension points (for future SE track)

| Field | Type | Purpose |
|-------|------|---------|
| `record_kind` | str | `"evaluation"`, `"skip"`, `"diagnostic"` |
| `skip_policy_version` | int | Policy version that generated this record |
| `skip_mode` | str | `disabled`, `dry_run`, `enforce` |
| `skip_decision` | str | Decision code |
| `skip_reason` | str | Human-readable reason |
| `skip_evidence_json` | json | Source evidence rows |
| `source_row_ids_json` | json | Evidence DB row IDs |
| `would_skip` | bool | Dry-run prediction |
| `enforced_skip` | bool | Whether skip was actually enforced |
| `evaluator_called` | bool | Whether evaluator ran |
| `retry_called` | bool | Whether retry ran |
| `budget_consumed` | bool | Whether CST solve was consumed |
| `failure_taxonomy_version` | int | Taxonomy version |
| `environment_fault_flag` | bool | Whether classified as environment fault |
| `operator_override_id` | str or null | Manual override reference |

**Policy**: If v1 schema cannot represent these cleanly, an SE (schema extension) track should add hooks before enforce mode (FS4). FS2/FS3 may store diagnostics in report/JSONL only.

---

## 8. Runtime interaction policy

| Feature | Interaction |
|---------|-------------|
| **Success reuse** | Only SUCCESS rows reusable. Skipped/failure rows **never** source for success reuse. |
| **Warm-start** | Only SUCCESS rows become optimizer priors. Skipped/failure rows **never** success priors. |
| **Retry runtime** | `dry_run` still calls evaluator/retry normally. `enforce` skip does not call evaluator or retry for skipped point. Environment failures not skip evidence. |
| **Stage search / adaptive bounds** | Failure rows can be diagnostic inputs later, but environment failures must not be treated as infeasible-region evidence. No changes in FS1. |
| **Evaluation DB** | DB enabled alone does not enable skip. Success_reuse does not enable skip. Warm-start does not enable skip. Skip requires separate explicit config. |

---

## 9. Config design proposal (docs-only, not implemented)

```yaml
evaluation_database:
  failure_skip:
    enabled: false
    mode: disabled             # disabled | dry_run | enforce
    exact_key_only: true
    min_failures: 2
    allow_gate_reject: true
    allow_calibration_failed: true
    allow_solver_failed: true
    allow_timeout: false
    allow_com_lost: false
    allow_unknown_exception: false
    allow_environment_faults: false
    max_candidates: 100
    require_schema_compatible: true
    require_objective_signature_match: true
    record_diagnostics: true

probably_infeasible:
  enabled: false
  mode: advisory               # advisory | dry_run | enforce
  allow_runtime_skip: false
```

### Rules

- Default disabled.
- `enabled: true` with `mode: dry_run` does not skip evaluator.
- `mode: enforce` must be explicit.
- `probably_infeasible.allow_runtime_skip` must be explicit and defaults `false`.
- No region-wide skip initially.

---

## 10. Future phase sequence

| Phase | Scope | Live CST? | Destructive? |
|-------|-------|-----------|--------------|
| **FS1** | Failure skip policy design, docs-only | No | No |
| FS2 | Failure skip candidate loader / no-CST helpers | No | No |
| FS3 | Runtime dry-run would-skip diagnostics / no-CST | No | No |
| FS4 | Exact-key enforce skip / no-CST call-count tests | No | No |
| FS5 | Bounded live exact-key skip smoke | **Yes, approved per scenario** | No |

### Optional adjacent tracks

| Phase | Scope | When |
|-------|-------|------|
| SE1 | Schema extension hooks before FS4/FS5 | If DB v1 insufficient |
| XR4 | During-solve destructive smoke (optional) | Only if operator wants broader recovery evidence |

---

## 11. Risk table

| Risk | Likelihood | Impact | Mitigation | Phase |
|------|-----------|--------|------------|-------|
| False skip hides valid parameter | Medium | High (missed optimum) | Dry-run mode first; exact-key only; min_failures threshold; audit trail allows review | FS2-FS4 |
| Environment failure misclassified as infeasible | Medium | High (wrong skip) | XR policy excludes environment faults; taxonomy versioning; manual override | FS1 design |
| Stale DB evidence | Low | Medium | max_age_days; schema check; run_id filtering | FS2 |
| Schema/objective/config drift | Low | Medium | require_schema_compatible; require_objective_signature_match | FS2 |
| Duplicate evidence rows inflate count | Low | Low | Dedup by source_row_ids_json | FS2 |
| Skip rows accidentally feed success reuse | Low | High | Reject non-SUCCESS in success_reuse lookup | Already enforced |
| Skip rows accidentally feed warm-start | Low | High | Reject non-SUCCESS in warm-start loader | Already enforced |
| Optimizer bias from penalized skip result | Medium | Medium | Skip rows produce synthetic result, not penalized SUCCESS; documented in optimizer policy | FS4 |
| Insufficient audit trail | Medium | Medium | Full audit schema (section 6); report records; JSONL diagnostic sidecar | FS2-FS3 |
| Operator cannot reconstruct why point skipped | Medium | High | Audit record includes evidence row IDs, timestamps, taxonomy, threshold decision | FS3 |

---

## 12. Explicit non-goals

| Item | Status |
|------|--------|
| Runtime skip implementation | **Not implemented in FS1** |
| DB skip loader | **Not implemented** |
| Live CST | **Not run** |
| Destructive action | **Not performed** |
| Schema migration | **Not implemented** |
| Success reuse semantics change | **Not changed** |
| Warm-start semantics change | **Not changed** |
| Stage/adaptive runtime change | **Not changed** |
| Workflow2 field objective work | **Deferred** |
| Region-wide skip | **Out of scope** |
| Broad probably-infeasible runtime discard | **Out of scope (remains advisory-only)** |

---

## 13. FS1 caveat cleanup

### XR3 DE name tests added

| Test | Assertion |
|------|-----------|
| `test_known_pid_de_amd64_kill_candidate` | Known PID + `CST DESIGN ENVIRONMENT_AMD64` → kill candidate |
| `test_unknown_pid_de_amd64_protected` | Unknown `CST DESIGN ENVIRONMENT_AMD64` → protected, not kill candidate |
| `test_known_pid_de_noext_kill_candidate` | Known PID + `CSTDesignEnvironment` (no .exe) → kill candidate |

Total safety tests: **58** (55 + 3).

### BRANCH_CONTEXT cleaned

Removed duplicate XR3 future/current wording. XR4 recorded as optional future, not current.

---

## 14. Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_extreme_recovery_safety.py --tb=short
-- 58 passed

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
-- 230 passed, 1 warning

pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
-- 12 passed
```

### Safety grep

No `taskkill`/`Stop-Process`/`subprocess`/`os.system` in helper or tests.

### Artifact check

No forbidden artifacts tracked. No generated artifacts committed.

---

## 15. Commit message

```
docs(wf1): design failure skip policy FS1

- Define 3-mode skip architecture: disabled → dry_run → enforce
- Define candidate evidence taxonomy: preferred, excluded, ambiguous
- Define minimum evidence thresholds (policy recommendations, not enforced)
- Define audit record schema for all skip decisions
- Define runtime interaction policy with success_reuse, warm-start, retry
- Propose future config shape (docs-only, not implemented)
- Propose FS1-FS5 phase sequence
- Add XR3 caveat tests for CST 2026 DE process names (58 total)
- Clean duplicate XR3 wording in BRANCH_CONTEXT

No runtime skip, no DB loader, no live CST, no destructive action.
```
