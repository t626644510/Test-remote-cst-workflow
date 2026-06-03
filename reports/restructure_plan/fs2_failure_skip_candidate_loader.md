# FS2 — failure skip candidate loader / no-CST helpers

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `FS2 — failure skip candidate loader / no-CST helpers` |
| Base commit | `5f5bcb76689208a0b2d8cda626500035fb16b0cc` (FS1 accepted) |
| Branch | `feature/wf1-failure-skip` |
| Live CST | **No** |
| Runtime skip implemented | **No** |
| DB writes by loader | **No** |
| Evaluator/retry calls | **No** |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/failure_skip_candidates.py` | **Added** | Pure no-CST candidate loader: config, evidence classification, DB loader, single-key lookup |
| `tests/workflows/test_rfgun_sao_failure_skip_candidates.py` | **Added** | 37 no-CST tests |
| `reports/restructure_plan/fs2_failure_skip_candidate_loader.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | FS2 phase |

---

## Helper API summary

| API | Type | Description |
|-----|------|-------------|
| `FailureSkipCandidateConfig` | dataclass | Config: enabled, mode, min_failures, allow_* flags |
| `resolve_failure_skip_config()` | function | Resolve config from dict |
| `classify_failure_skip_evidence()` | function | Classify a DB row for skip eligibility |
| `is_environment_fault_classification()` | function | True for environment/COM/process-kill |
| `is_candidate_evidence_classification()` | function | True if classification is allowed by config |
| `load_failure_skip_candidates()` | function | Load candidates from durable DB |
| `find_failure_skip_candidate_for_key()` | function | Single-key lookup |
| `FailureSkipCandidate` | dataclass | Aggregated candidate with evidence_count, decision, blocked_reasons |
| `FailureSkipCandidateLoadResult` | dataclass | Structured loader result with diagnostics |

---

## Config model summary

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `False` | Master switch |
| `mode` | `"disabled"` | `disabled` / `dry_run` / `enforce` |
| `exact_key_only` | `True` | exact parameter_key only |
| `min_failures` | `2` | Minimum evidence rows |
| `allow_gate_reject` | `True` | Include gate_rejected evidence |
| `allow_solver_failed` | `True` | Include solver_failed evidence |
| `allow_environment_faults` | `False` | Exclude environment faults by default |
| `max_candidates` | `100` | Cap on returned candidates |
| `policy_version` | `1` | Policy version identifier |

---

## Evidence classification taxonomy

| Classification | Category | Default allowed? |
|----------------|----------|-----------------|
| `SUCCESS` | Excluded | N/A |
| `SUCCESS_REUSE` | Excluded | N/A |
| `WARM_START_PRIOR` | Excluded | N/A |
| `GATE_REJECTED` | Preferred candidate | Yes |
| `CALIBRATION_FAILED` | Preferred candidate | Yes |
| `SOLVER_FAILED` | Preferred candidate | Yes (requires taxonomy) |
| `OBJECTIVE_EXTRACTION_FAILED` | Preferred candidate | Yes |
| `PROBABLY_INFEASIBLE_CANDIDATE` | Preferred candidate | Yes |
| `XR_PROCESS_KILL` | Environment fault | No (blocked by default) |
| `COM_CONNECTION_LOST` | Environment fault | No |
| `TRANSIENT_ENVIRONMENT_FAULT` | Environment fault | No |
| `UNKNOWN_EXCEPTION` | Excluded/explicit opt-in | No (requires allow_unknown_exception) |
| `SOLVER_FAILED_WITHOUT_TAXONOMY` | Ambiguous | Dry-run only |
| `SCHEMA_INCOMPATIBLE` | Blocked | N/A |

---

## DB loader behavior

| Scenario | Behavior |
|----------|----------|
| Disabled config | Returns empty result, no DB read |
| Missing DB path | Returns empty result with diagnostic |
| SUCCESS rows | Excluded from evidence |
| Success reuse rows | Excluded |
| Warm-start prior rows | Excluded |
| Environment fault rows | Blocked by default; allowed if `allow_environment_faults=True` |
| Schema-incompatible rows | Blocked |
| No parameter_key | Blocked |
| Below min_failures | Candidate created but not recommended |
| At/above min_failures | Candidate recommended (dry_run: `would_skip`, enforce: `enforce_eligible`) |
| Duplicate DB row IDs | Deduped by row_id within same parameter_key |
| max_candidates | Applied deterministically (evidence_count desc, then key) |

---

## DB/schema limitations found

| Limitation | Impact |
|------------|--------|
| v1 schema error_taxonomy exists but is optional | `solver_failed` without taxonomy → `SOLVER_FAILED_WITHOUT_TAXONOMY` (ambiguous) |
| No structured `environment_fault_flag` | Environment classification relies on error_taxonomy text markers |
| No skip-specific audit fields in v1 | FS3/FS4 diagnostics must use JSONL or report until SE track |
| No schema migration done | SE1 recommended before FS4 enforce mode |

**Recommendation**: SE1 schema extension is not required for FS3 (dry-run diagnostics are report/JSONL only), but should be completed before FS4 enforce mode.

---

## Tests added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestConfig` | 5 | Default disabled, disabled returns no candidates, invalid mode, dry_run, enforce |
| `TestEvidenceClassification` | 13 | SUCCESS/REUSE/WARM_START excluded, gate/calibration/solver classified, XR/COM/transient environment, schema incompatible, unknown status, ambiguous solver |
| `TestDBLoader` | 14 | Missing path, disabled, success excluded, solver failure candidate, min_failures threshold, two same-key, different keys, duplicate rows, parameter_keys filter, max_candidates cap, environment fault blocked/allowed, classification counts |
| `TestSingleKeyLookup` | 3 | Found, not found, disabled |
| `TestGlobalSafety` | 4 | No subprocess, no os.system, no taskkill, no CST import |

**Total: 37 tests**

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_failure_skip_candidates.py --tb=short
-- 37 passed

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

## Recommended next phase

**FS3 — runtime dry-run would-skip diagnostics / no-CST**. The v1 schema is
sufficient for dry-run diagnostics (report-only).  SE1 schema extension can
be deferred until FS4 enforce mode.

Or, if the policy requires DB audit fields before any runtime integration:

**SE1 — schema extension hooks** before FS3.
