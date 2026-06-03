# FS4 — exact-key enforce skip / no-CST call-count tests

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `FS4 — exact-key enforce skip / no-CST call-count tests` |
| Base commit | `2be78ea8f5adff7d79871267b9bade3014a6370f` (FS3.1 accepted) |
| Branch | `feature/wf1-failure-skip` |
| Live CST | **No** |
| Real runtime wiring | **No** |
| Real workflow skip implemented | **No** |
| Enforce skip implemented in no-CST helper | **Yes** |
| DB writes by helper | **No** (v1 schema cannot store synthetic row status) |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/failure_skip_enforce.py` | **Added** | Enforce decision model + fake-runtime harness |
| `tests/workflows/test_rfgun_sao_failure_skip_enforce.py` | **Added** | 18 no-CST enforce tests |
| `reports/restructure_plan/fs4_failure_skip_enforce_no_cst.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | FS4 phase |

---

## Enforce helper API summary

| API | Type | Description |
|-----|------|-------------|
| `FailureSkipEnforceDecision` | dataclass | Enforce decision with enforce_skip flag, source rows, budget info |
| `evaluate_failure_skip_enforce_for_key()` | function | Single-key enforce decision |
| `FakeEnforceEvaluationResult` | dataclass | Fake evaluation result with call-count evidence |
| `run_failure_skip_enforce_fake_evaluation()` | function | Fake harness: enforces skip by NOT calling evaluator when appropriate |

---

## Config behavior

| Config | `enforce_skip` | `evaluator_must_run` |
|--------|---------------|---------------------|
| `enabled=false` | False | True |
| `mode=disabled` | False | True |
| `mode=dry_run` | False | True |
| `mode=enforce` + no candidate | False | True |
| `mode=enforce` + candidate below threshold | False | True |
| `mode=enforce` + eligible candidate | **True** | **False** |
| `mode=enforce` + XR process-kill | False | True |

---

## Synthetic skip row policy

| Question | Answer |
|----------|--------|
| v1 schema accepts custom statuses? | **No** — `EvaluationDatabaseStatus.validate()` rejects non-standard status values |
| DB write helper implemented? | **No** — deferred pending SE1 schema extension |
| SE1 required before FS5? | **Yes** — synthetic skip rows cannot be recorded without schema update |
| FS4 alternative | Fake-runtime enforce harness verifies call-count behavior without DB writes |

---

## Success reuse / warm-start interaction

Both `success_reuse` and `warm_start` loaders check for `status == "success"` and reject any other status.  Once SE1 adds the `skipped_failure_reuse` status to the valid set, synthetic skip rows would be safely ignored by both loaders without code changes.

---

## Call-count test summary

| Scenario | Evaluator called? | Retry called? |
|----------|-------------------|---------------|
| Enforce hit (eligible candidate) | **No** (0 calls) | **No** (0 calls) |
| Enforce hit + retry wrapper | **No** (0 calls) | **No** (0 calls) |
| Enforce miss (no candidate) | **Yes** (exactly once) | If configured: once |
| Enforce miss (+ retry wrapper) | **Yes** (once) | **Yes** (once) |
| Disabled config | **Yes** (once) | If configured: once |
| Dry_run mode | **Yes** (once) | If configured: once |
| XR process-kill blocked | **Yes** (once) | If configured: once |

All call-count tests use the fake no-CST harness, not real runtime.

---

## Tests added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestEnforceDecision` | 7 | Disabled, dry_run, no candidate, below threshold, eligible candidate, XR blocked, unknown exception allowed |
| `TestFakeEnforceHarness` | 8 | Enforce hit (no evaluator), enforce hit + retry not called, enforce miss calls evaluator, miss + retry, disabled calls evaluator, dry_run calls evaluator, XR blocked calls evaluator |
| `TestGlobalSafety` | 4 | No subprocess, no os.system, no taskkill, no CST import |

**Total: 18 tests** (FS2+FS2.1+FS3+FS3.1+FS4 = 48 + 23 + 18 = 89 failure_skip tests total)

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_failure_skip_candidates.py --tb=short
-- 48 passed

pytest tests/workflows/test_rfgun_sao_failure_skip_dry_run.py --tb=short
-- 23 passed

pytest tests/workflows/test_rfgun_sao_failure_skip_enforce.py --tb=short
-- 18 passed

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

## Explicit statements

| Item | Status |
|------|--------|
| Live CST | **No** |
| Real runtime wiring | **No** |
| Real workflow skip implemented | **No** |
| Enforce skip in no-CST helper | **Yes** |
| DB writes by helper | **No** (v1 schema limitation) |
| Default config changed | **No** |
| Generated artifacts committed | **No** |

---

## Recommended next phase

**SE1 — schema extension hooks** before FS5 live enforce smoke.  The v1
`EvaluationDatabaseStatus` is a closed set that cannot represent synthetic
skip rows.  SE1 should add `SKIPPED_FAILURE_REUSE` and
`SKIPPED_PROBABLY_INFEASIBLE` statuses, along with skip-audit fields
proposed in FS1 section 7.

**FS5 — bounded live exact-key skip smoke** only after SE1 is accepted and
DB recording is adequate.  Requires explicit operator approval.
