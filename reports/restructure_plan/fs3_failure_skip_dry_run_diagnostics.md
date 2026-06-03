# FS3 — runtime dry-run would-skip diagnostics / no-CST

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `FS3 — runtime dry-run would-skip diagnostics / no-CST` |
| Base commit | `0829d6c659bebdf380a5a892520e1a5c433fc0ec` (FS2.1 accepted) |
| Branch | `feature/wf1-failure-skip` |
| Live CST | **No** |
| Runtime skip implemented | **No** |
| Enforce mode implemented | **No** |
| Evaluator/retry still called in dry-run | **Yes** |
| DB writes by dry-run | **No** |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/failure_skip_dry_run.py` | **Added** | Pure no-CST dry-run decision model and evaluation helpers |
| `tests/workflows/test_rfgun_sao_failure_skip_dry_run.py` | **Added** | 16 no-CST dry-run tests |
| `workflows/rfgun_sao/failure_skip_candidates.py` | **Cleaned** | Removed duplicate `TIMEOUT` constant |
| `reports/restructure_plan/fs3_failure_skip_dry_run_diagnostics.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | FS3 phase |

---

## FS2.1 cleanup

| Issue | Fix |
|-------|-----|
| Duplicate `TIMEOUT = "timeout"` constant | Removed duplicate (line 192) |

---

## Helper API summary

| API | Type | Description |
|-----|------|-------------|
| `FailureSkipDryRunDecision` | dataclass | One dry-run decision for a single parameter_key |
| `FailureSkipDryRunSummary` | dataclass | Aggregated summary for multiple keys |
| `evaluate_failure_skip_dry_run_for_key()` | function | Single-key dry-run evaluation |
| `evaluate_failure_skip_dry_run_for_keys()` | function | Multi-key dry-run evaluation |

---

## Dry-run decision semantics

| Scenario | `would_skip` | `evaluator_must_run` | `retry_must_run` | `budget_consumed_normally` |
|----------|-------------|---------------------|-------------------|---------------------------|
| Disabled config | False | True | True | True |
| No candidate found | False | True | True | True |
| Candidate hit, below min_failures | False | True | True | True |
| Candidate hit, meets threshold | **True** | True | True | True |
| XR process-kill evidence | False | True | True | True |
| Enforce mode (FS3 only) | False (downgraded) | True | True | True |

---

## Config behavior

| Config | Behavior |
|--------|----------|
| Missing / disabled | Disabled decision; no DB read |
| `mode=disabled` | No candidate lookup |
| `mode=dry_run` | Candidate lookup + would-skip diagnostic; evaluator still called |
| `mode=enforce` | **Downgraded** to dry-run in FS3; `ValueError` would be raised by candidate loader if it reached enforce, but dry-run helper explicitly catches and downgrades |

---

## Evidence / candidate source policy

| Source | Used? |
|--------|-------|
| Durable evaluation DB | **Yes** (via FS2 candidate loader) |
| JSONL sidecar | **Never** |
| In-memory or temp data | **No** |

---

## Tests added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestDryRunConfig` | 4 | Disabled, mode disabled, dry_run checks DB, enforce downgraded |
| `TestDryRunDecision` | 5 | Candidate hit (evaluator/retry still runs), candidate miss, XR blocked, insufficient evidence, exact key filter |
| `TestMultiKey` | 3 | Empty keys, multiple keys summary, mixed keys summary |
| `TestGlobalSafety` | 4 | No subprocess, no os.system, no taskkill, no CST import |

**Total: 16 tests** (FS2+FS2.1+FS3 = 48 + 16 = 64 failure_skip tests total)

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_failure_skip_candidates.py --tb=short
-- 48 passed

pytest tests/workflows/test_rfgun_sao_failure_skip_dry_run.py --tb=short
-- 16 passed

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
| Destructive action | **No** |
| Runtime skip implemented | **No** |
| Enforce mode implemented | **No** (downgraded to dry-run) |
| Evaluator/retry still called in dry-run | **Yes** |
| DB writes by dry-run | **No** |
| Default config changed | **No** |
| Generated artifacts committed | **No** |

---

## Recommended next phase

**FS4 — exact-key enforce skip / no-CST call-count tests**. SE1 schema
extension may be needed before FS4 enforce if the current v1 audit fields
are insufficient for enforcement recording.  If schema is sufficient, FS4 can
proceed directly.
