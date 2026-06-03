# XR2 — no-CST process/fault harness and classifier tests

## Metadata

| Field | Value |
|-------|-------|
| Phase label | `XR2 — no-CST process/fault harness and classifier tests` |
| Base commit | `0e5f09a6ac2429e242c5bb0923a9f6e1ef51cc5e` (XR1 accepted HEAD) |
| Branch | `feature/wf1-extreme-com-recovery` |
| Live CST | **No** |
| Destructive action | **No** |
| Runtime code changed | **No** (new helper module only) |
| Default config changed | **No** |

---

## Files changed

| File | Action | Description |
|------|--------|-------------|
| `workflows/rfgun_sao/extreme_recovery_safety.py` | **Added** | Pure no-CST safety helper module (fault taxonomy, process classifier, target selection, inventory diff, emergency cleanup model, safety summary) |
| `tests/workflows/test_rfgun_sao_extreme_recovery_safety.py` | **Added** | 46 no-CST tests covering all helper surfaces |
| `reports/restructure_plan/xr2_extreme_recovery_no_cst_harness.md` | **Added** | This report |
| `workflows/rfgun_sao/BRANCH_CONTEXT.md` | **Updated** | XR2 status |

---

## Helper API summary

### Module: `workflows/rfgun_sao/extreme_recovery_safety.py`

| API | Type | Description |
|-----|------|-------------|
| `ExtremeRecoveryFaultKind` | `str, Enum` | 10-entry fault taxonomy matching XR1 design |
| `is_destructive_fault_kind()` | function | True for process-kill/COM-sever scenarios |
| `requires_operator_approval()` | function | True for all destructive kinds |
| `is_environment_fault()` | function | True for transient environment/COM failures |
| `is_skip_evidence_candidate()` | function | False for all environment faults; solver_timeout defaults non-skip |
| `ProcessSnapshot` | dataclass | Immutable process observation record |
| `validate_process_snapshot()` | function | Positive PID, non-empty name |
| `KnownCstConnection` | dataclass | Registry-tracked CST DE connection |
| `ProcessClassification` | dataclass | Classification with protected/kill_candidate flags |
| `classify_cst_process()` | function | Classifies one process against connections + policy |
| `OperatorApproval` | dataclass | Explicit operator approval for destructive phase |
| `TargetSelection` | dataclass | Decision: allowed + target_pid + blocked_by reasons |
| `select_destructive_target()` | function | Safety-gated target selection (decision only, no execution) |
| `ProcessInventoryDiff` | dataclass | Deterministic pre/post process inventory diff |
| `diff_process_inventory()` | function | Compute diff with orphan/unknown/cstd classification |
| `EmergencyCleanupRecord` | dataclass | Audit record for emergency manual cleanup |
| `validate_emergency_cleanup_record()` | function | Completeness validation |
| `build_xr_safety_summary()` | function | Deterministic report model (no execution) |

All functions are pure no-CST — no subprocess, no os.system, no taskkill,
no Stop-Process, no CST import.

---

## Fault taxonomy coverage

All 10 XR1 taxonomy entries are represented as `ExtremeRecoveryFaultKind` enum members.
Classification helpers tested for:
- Destructive fault kinds require operator approval
- License daemon fault is never a destructive target
- Environment/COM/process-kill faults are excluded from skip evidence
- `solver_timeout` defaults to non-skip evidence

---

## Process safety classifier semantics

| Classification | protected | kill_candidate | When |
|----------------|-----------|----------------|------|
| `license_daemon_protected` | True | False | `cstd.exe` or `cstd` |
| `known_design_environment` | False | True (active) / False (inactive) | PID matches `KnownCstConnection` |
| `unknown_cst_process` | True | False | CST-like name, no registry match |
| `non_cst_process` | False | False | No CST-related name |
| `invalid_snapshot` | True | False | pid <= 0 or empty name |

---

## Target selection safety gates

`select_destructive_target()` applies 9 gates:

1. Approval must exist (not None)
2. Phase prefix must be XR3/XR4/XR5 (not XR2 or anything else)
3. Scenario string must match approval
4. max_evals must be 1-3
5. License daemon confirmation required
6. Planned taskkill must be allowed
7. `license_daemon_must_not_kill` scenario always blocked
8. Requested PID must be in inventory and be a kill candidate
9. Auto-select: exactly 1 kill candidate required (0 or multiple blocks)

---

## Inventory diff semantics

- `cstd.exe` → always in `protected_license_daemon_pids`, never orphan
- Known active DE still running → in `remaining_known_de_pids`, not orphan
- Known inactive DE still running → orphan candidate
- Unknown CST-like process → in `remaining_unknown_cst_pids`, warning, not target
- Non-CST processes ignored
- Summary is deterministic

---

## Emergency cleanup audit model

`EmergencyCleanupRecord` captures:
- Whether emergency cleanup was allowed by the operator approval
- Reason for emergency action
- Target PID (required if kill command was used)
- Command summary
- Timestamp
- Residual process count after cleanup

`validate_emergency_cleanup_record()` checks:
- Reason is non-empty
- target_pid present if command_summary indicates a kill
- timestamp present
- residual_process_count present

---

## Safety summary model

`build_xr_safety_summary()` returns a deterministic mapping with:
- `scenario`, `approved`, `target_allowed`, `target_pid`, `blocked_by`
- `protected_license_daemon_confirmed`, `orphan_candidate_count`
- `emergency_cleanup_recorded`
- `safe_to_execute_destructive_action` (decision model only)

---

## Tests added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestFaultTaxonomy` | 5 | All entries present, license daemon, environment/COM not skip evidence, solver_timeout default, destructive requires approval |
| `TestProcessSnapshot` | 4 | Valid, pid=0, pid=-1, empty name |
| `TestProcessClassification` | 6 | cstd protected, known DE killable, unknown DE protected, non-CST ignored, invalid protected, inactive DE not killable |
| `TestTargetSelection` | 12 | No approval, scenario mismatch, max_evals >3, license not confirmed, taskkill not allowed, license daemon scenario, requested PID valid/invalid/not found, auto-select 0/1/multiple |
| `TestInventoryDiff` | 5 | cstd not orphan, inactive DE orphan, unknown CST warning, started/ended deterministic, summary deterministic |
| `TestEmergencyCleanup` | 5 | Missing reason, kill needs PID, timestamp required, residual count required, complete valid |
| `TestSafetySummary` | 5 | Blocked target not safe, no approval not safe, valid approval+target safe, invalid cleanup not safe, orphan count reflected |
| `TestGlobalSafety` | 4 | No subprocess import, no os.system, no taskkill/Stop-Process calls, no CST import |

**Total: 46 tests**

---

## Validation

```powershell
python -m compileall workflows/rfgun_sao tests/workflows/test_rfgun_sao_imports.py
-- Compiles OK.

pytest tests/workflows/test_rfgun_sao_extreme_recovery_safety.py --tb=short
-- 46 passed

pytest tests/workflows/test_rfgun_sao_imports.py --tb=short
-- 230 passed, 1 warning

pytest tests/workflows/test_rfgun_single_pass_imports.py --tb=short
-- 12 passed
```

---

## XR1 wording correction

XR1's design report stated that future failure skip should "only skip
environment failures."  This is corrected in XR2:

- **Environment / COM / process-kill faults are transient** by default
  and should generally be **excluded from skip evidence**.
- **Destructive XR rows are used to identify and filter out** transient
  environment failures.
- **Skip evidence should focus on deterministic / repeated exact-key**
  geometry, physics, gate, calibration, or solver failures.

This correction is reflected in `is_skip_evidence_candidate()` returning
`False` for all environment fault kinds.

---

## Artifact check

| Pattern | Tracked? |
|---------|----------|
| `config.local.yaml` | No (untracked) |
| `*.sqlite` / `*.db` | No |
| `*.jsonl` | No |
| `*.ckpt` | No |
| Logs / CST outputs / temp scripts | No |
| `.claude/settings.local.json` | Not tracked |

---

## Explicit statements

| Item | Status |
|------|--------|
| Live CST | **No** |
| Destructive action / kill | **No** |
| Runtime code changed | **No** (helper-only, no-CST) |
| Default config changed | **No** |
| taskkill / Stop-Process executed | **No** |
| Generated artifacts committed | **No** |
| Failure skip implemented | **No** |
| Probably-infeasible skip | **No** |
| Schema migration | **No** |

---

## Recommended next phase

**XR3 — bounded destructive live smoke** (single approved scenario,
`de_process_killed_before_solve`) only with explicit operator approval
per the XR1 approval gate.

Or, if operator prefers skip policy before destructive live test:

**FS1 — failure skip policy design** (docs-only, advisory).
