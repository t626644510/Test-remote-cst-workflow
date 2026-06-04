"""No-CST tests for XR2 extreme recovery safety harness.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from workflows.rfgun_sao.extreme_recovery_safety import (
    KNOWN_DESIGN_ENVIRONMENT,
    KNOWN_PID_UNEXPECTED_PROCESS,
    LICENSE_DAEMON_PROTECTED,
    NON_CST_PROCESS,
    UNKNOWN_CST_PROCESS,
    INVALID_SNAPSHOT,
    EmergencyCleanupRecord,
    ExtremeRecoveryFaultKind,
    KnownCstConnection,
    OperatorApproval,
    ProcessClassification,
    ProcessInventoryDiff,
    ProcessSnapshot,
    TargetSelection,
    build_xr_safety_summary,
    classify_cst_process,
    diff_process_inventory,
    is_destructive_fault_kind,
    is_environment_fault,
    is_skip_evidence_candidate,
    requires_operator_approval,
    select_destructive_target,
    validate_emergency_cleanup_record,
    validate_process_snapshot,
)


# ===================================================================
# Fault taxonomy completeness
# ===================================================================


class TestFaultTaxonomy:
    def test_all_xr1_taxonomy_entries_present(self):
        """All XR1 taxonomy entries are represented in the enum."""
        expected = {
            "de_process_killed_before_solve",
            "de_process_killed_during_solve",
            "de_process_killed_after_solve_before_cleanup",
            "com_call_hang",
            "com_connection_lost",
            "solver_timeout",
            "replacement_de_orphan_candidate",
            "cleanup_close_hang",
            "license_daemon_must_not_kill",
            "unknown_cst_process_state",
        }
        actual = {e.value for e in ExtremeRecoveryFaultKind}
        assert actual == expected

    def test_license_daemon_never_destructive_target(self):
        """license_daemon_must_not_kill is not a destructive fault kind."""
        assert not is_destructive_fault_kind(
            ExtremeRecoveryFaultKind.LICENSE_DAEMON_MUST_NOT_KILL,
        )

    def test_environment_faults_not_skip_evidence(self):
        """Environment/COM/process-kill faults are not skip evidence candidates."""
        env_kinds = [
            ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_DURING_SOLVE,
            ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_AFTER_SOLVE_BEFORE_CLEANUP,
            ExtremeRecoveryFaultKind.COM_CALL_HANG,
            ExtremeRecoveryFaultKind.COM_CONNECTION_LOST,
            ExtremeRecoveryFaultKind.CLEANUP_CLOSE_HANG,
        ]
        for k in env_kinds:
            assert is_environment_fault(k), f"{k.value} should be environment fault"
            assert not is_skip_evidence_candidate(k), (
                f"{k.value} should not be skip evidence candidate"
            )

    def test_solver_timeout_defaults_non_skip_evidence(self):
        """solver_timeout defaults to non-skip evidence."""
        assert not is_skip_evidence_candidate(
            ExtremeRecoveryFaultKind.SOLVER_TIMEOUT,
        )

    def test_destructive_faults_require_approval(self):
        """All destructive fault kinds require operator approval."""
        for k in ExtremeRecoveryFaultKind:
            if is_destructive_fault_kind(k):
                assert requires_operator_approval(k)
            else:
                assert not requires_operator_approval(k)


# ===================================================================
# Process snapshot validation
# ===================================================================


class TestProcessSnapshot:
    def test_valid_snapshot(self):
        snap = ProcessSnapshot(pid=1234, name="CSTDesignEnvironment.exe")
        valid, reasons = validate_process_snapshot(snap)
        assert valid
        assert len(reasons) == 0

    def test_invalid_pid_zero(self):
        snap = ProcessSnapshot(pid=0, name="cstd.exe")
        valid, reasons = validate_process_snapshot(snap)
        assert not valid
        assert "pid_must_be_positive" in reasons

    def test_invalid_negative_pid(self):
        snap = ProcessSnapshot(pid=-1, name="cstd.exe")
        valid, reasons = validate_process_snapshot(snap)
        assert not valid
        assert "pid_must_be_positive" in reasons

    def test_invalid_empty_name(self):
        snap = ProcessSnapshot(pid=1234, name="")
        valid, reasons = validate_process_snapshot(snap)
        assert not valid
        assert "name_must_be_non_empty" in reasons


# ===================================================================
# Process classification
# ===================================================================


cstd_snap = ProcessSnapshot(pid=100, name="cstd.exe")
de_snap = ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe")
solver_snap = ProcessSnapshot(pid=201, name="CSTSolver.exe")
python_snap = ProcessSnapshot(pid=202, name="python.exe")
unknown_snap = ProcessSnapshot(pid=300, name="CSTDesignEnvironment.exe")
chrome_snap = ProcessSnapshot(pid=400, name="chrome.exe")
invalid_snap = ProcessSnapshot(pid=0, name="")
de_amd64_snap = ProcessSnapshot(pid=500, name="CST DESIGN ENVIRONMENT_AMD64")
de_noext_snap = ProcessSnapshot(pid=501, name="CSTDesignEnvironment")
de_conn = KnownCstConnection(pid=200, label="workflow._conn")


class TestProcessClassification:
    def test_cstd_protected_not_kill_candidate(self):
        cl = classify_cst_process(cstd_snap, [])
        assert cl.classification == LICENSE_DAEMON_PROTECTED
        assert cl.protected
        assert not cl.kill_candidate

    def test_known_de_is_kill_candidate(self):
        cl = classify_cst_process(de_snap, [de_conn])
        assert cl.classification == KNOWN_DESIGN_ENVIRONMENT
        assert not cl.protected
        assert cl.kill_candidate
        assert cl.matched_connection_label == "workflow._conn"

    def test_unknown_de_not_kill_candidate(self):
        cl = classify_cst_process(unknown_snap, [])
        assert cl.classification == UNKNOWN_CST_PROCESS
        assert cl.protected
        assert not cl.kill_candidate

    def test_non_cst_process_ignored(self):
        cl = classify_cst_process(chrome_snap, [])
        assert cl.classification == NON_CST_PROCESS
        assert not cl.kill_candidate

    def test_invalid_snapshot_protected(self):
        cl = classify_cst_process(invalid_snap, [])
        assert cl.classification == INVALID_SNAPSHOT
        assert cl.protected
        assert not cl.kill_candidate

    def test_inactive_de_not_kill_candidate(self):
        inactive_conn = KnownCstConnection(
            pid=200, label="workflow._conn", active=False,
        )
        cl = classify_cst_process(de_snap, [inactive_conn])
        assert cl.classification == KNOWN_DESIGN_ENVIRONMENT
        assert not cl.kill_candidate
        assert cl.matched_connection_label == "workflow._conn"

    # ---- XR2.1: strict name matching ---------------------------------

    def test_known_pid_unexpected_solver_not_kill_candidate(self):
        """Known PID + CSTSolver.exe -> blocked, not kill candidate."""
        conn = KnownCstConnection(pid=201, label="solver_conn")
        cl = classify_cst_process(solver_snap, [conn])
        assert cl.classification == KNOWN_PID_UNEXPECTED_PROCESS
        assert cl.protected
        assert not cl.kill_candidate
        assert cl.matched_connection_label == "solver_conn"

    def test_known_pid_python_not_kill_candidate(self):
        """Known PID + python.exe -> non-CST (ignored before PID check)."""
        conn = KnownCstConnection(pid=202, label="python_conn")
        cl = classify_cst_process(python_snap, [conn])
        # python.exe does not contain "cst" in its name, so it is classified
        # as non-CST before the known-PID check
        assert cl.classification == NON_CST_PROCESS
        assert not cl.kill_candidate

    def test_known_pid_cstd_license_daemon_protected(self):
        """Known PID + cstd.exe -> license daemon protected before name check."""
        cstd_conn = KnownCstConnection(pid=100, label="cstd_conn")
        cl = classify_cst_process(cstd_snap, [cstd_conn])
        assert cl.classification == LICENSE_DAEMON_PROTECTED

    # ---- XR3: real DE process name caveat ------------------------------

    def test_known_pid_de_amd64_kill_candidate(self):
        """Known PID + CST DESIGN ENVIRONMENT_AMD64 -> kill candidate."""
        conn = KnownCstConnection(pid=500, label="amd64_conn")
        cl = classify_cst_process(de_amd64_snap, [conn])
        assert cl.classification == KNOWN_DESIGN_ENVIRONMENT
        assert cl.kill_candidate
        assert cl.matched_connection_label == "amd64_conn"

    def test_unknown_pid_de_amd64_protected(self):
        """Unknown CST DESIGN ENVIRONMENT_AMD64 -> protected unknown CST."""
        cl = classify_cst_process(de_amd64_snap, [])
        assert cl.classification == UNKNOWN_CST_PROCESS
        assert cl.protected
        assert not cl.kill_candidate

    def test_known_pid_de_noext_kill_candidate(self):
        """Known PID + CSTDesignEnvironment (no .exe) -> kill candidate."""
        conn = KnownCstConnection(pid=501, label="noext_conn")
        cl = classify_cst_process(de_noext_snap, [conn])
        assert cl.classification == KNOWN_DESIGN_ENVIRONMENT
        assert cl.kill_candidate
        assert cl.matched_connection_label == "noext_conn"
        assert not cl.protected


# ===================================================================
# Target selection
# ===================================================================


_valid_approval = OperatorApproval(
    phase="XR3",
    scenario="de_process_killed_before_solve",
    max_evals=1,
    planned_taskkill_allowed=True,
    emergency_cleanup_allowed=True,
    protected_license_daemon_confirmed=True,
)

_de_process = [
    ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe"),
    ProcessSnapshot(pid=100, name="cstd.exe"),
]
_de_conn = [KnownCstConnection(pid=200, label="workflow._conn")]


class TestTargetSelection:
    def test_no_approval_blocks(self):
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=None,
        )
        assert not result.allowed
        assert "no_approval" in result.blocked_by

    def test_approval_scenario_mismatch_blocks(self):
        bad_approval = OperatorApproval(
            phase="XR3", scenario="com_call_hang",
            planned_taskkill_allowed=True,
            protected_license_daemon_confirmed=True,
        )
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=bad_approval,
        )
        assert not result.allowed
        assert "scenario_mismatch" in result.blocked_by

    def test_max_evals_over_3_blocks(self):
        bad_approval = OperatorApproval(
            phase="XR3", scenario="de_process_killed_before_solve",
            max_evals=5,
            planned_taskkill_allowed=True,
            protected_license_daemon_confirmed=True,
        )
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=bad_approval,
        )
        assert not result.allowed
        assert "max_evals_out_of_range" in result.blocked_by

    def test_license_daemon_not_confirmed_blocks(self):
        no_ld = OperatorApproval(
            phase="XR3", scenario="de_process_killed_before_solve",
            planned_taskkill_allowed=True,
            protected_license_daemon_confirmed=False,
        )
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=no_ld,
        )
        assert not result.allowed
        assert "license_daemon_not_confirmed" in result.blocked_by

    def test_planned_taskkill_not_allowed_blocks(self):
        no_kill = OperatorApproval(
            phase="XR3", scenario="de_process_killed_before_solve",
            planned_taskkill_allowed=False,
            protected_license_daemon_confirmed=True,
        )
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=no_kill,
        )
        assert not result.allowed
        assert "planned_taskkill_not_allowed" in result.blocked_by

    def test_license_daemon_scenario_always_blocked(self):
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.LICENSE_DAEMON_MUST_NOT_KILL,
            approval=_valid_approval,
        )
        assert not result.allowed
        assert "license_daemon_scenario_always_blocked" in result.blocked_by

    def test_requested_pid_must_match_kill_candidate(self):
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            requested_pid=200,
        )
        assert result.allowed
        assert result.target_pid == 200

    def test_requested_pid_not_kill_candidate_blocks(self):
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            requested_pid=100,  # cstd.exe - protected
        )
        assert not result.allowed
        assert "requested_pid_not_kill_candidate" in result.blocked_by

    def test_requested_pid_not_in_inventory_blocks(self):
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            requested_pid=999,
        )
        assert not result.allowed
        assert "requested_pid_not_in_inventory" in result.blocked_by

    def test_auto_select_one_candidate(self):
        result = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
        )
        assert result.allowed
        assert result.target_pid == 200

    def test_auto_select_no_candidates_blocks(self):
        # Only cstd.exe (protected) and chrome.exe (non-CST)
        procs = [
            ProcessSnapshot(pid=100, name="cstd.exe"),
            ProcessSnapshot(pid=400, name="chrome.exe"),
        ]
        result = select_destructive_target(
            procs, [],
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
        )
        assert not result.allowed
        assert "no_kill_candidates_available" in result.blocked_by

    def test_auto_select_multiple_candidates_ambiguity_blocks(self):
        procs = [
            ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe"),
            ProcessSnapshot(pid=201, name="CSTDesignEnvironment.exe"),
        ]
        conns = [
            KnownCstConnection(pid=200, label="conn_1"),
            KnownCstConnection(pid=201, label="conn_2"),
        ]
        result = select_destructive_target(
            procs, conns,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
        )
        assert not result.allowed
        assert "multiple_kill_candidates_ambiguous" in result.blocked_by

    # ---- XR2.1: strict classification in target selection -----------

    def test_requested_pid_unexpected_process_blocks(self):
        """Known PID with unexpected process name -> not kill candidate."""
        procs = [ProcessSnapshot(pid=201, name="CSTSolver.exe")]
        conns = [KnownCstConnection(pid=201, label="solver_conn")]
        result = select_destructive_target(
            procs, conns,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            requested_pid=201,
        )
        assert not result.allowed
        assert "requested_pid_not_kill_candidate" in result.blocked_by

    def test_auto_select_ignores_unexpected_process(self):
        """Auto-select ignores known PID with unexpected process name."""
        procs = [
            ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe"),
            ProcessSnapshot(pid=201, name="CSTSolver.exe"),
        ]
        conns = [
            KnownCstConnection(pid=200, label="de_conn"),
            KnownCstConnection(pid=201, label="solver_conn"),
        ]
        result = select_destructive_target(
            procs, conns,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
        )
        # Only PID 200 is a valid kill candidate; PID 201 is unexpected
        assert result.allowed
        assert result.target_pid == 200

    def test_auto_select_valid_de_with_cstd(self):
        """One valid DE + cstd.exe selects the DE only."""
        procs = [
            ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe"),
            ProcessSnapshot(pid=100, name="cstd.exe"),
        ]
        conns = [KnownCstConnection(pid=200, label="de_conn")]
        result = select_destructive_target(
            procs, conns,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
        )
        assert result.allowed
        assert result.target_pid == 200


# ===================================================================
# Inventory diff
# ===================================================================


class TestInventoryDiff:
    def test_cstd_remaining_not_orphan(self):
        before = [ProcessSnapshot(pid=100, name="cstd.exe")]
        after = [ProcessSnapshot(pid=100, name="cstd.exe")]
        diff = diff_process_inventory(before, after, [])
        assert 100 in diff.protected_license_daemon_pids
        assert 100 not in diff.orphan_candidate_pids

    def test_orphan_candidate_inactive_de(self):
        de_proc = ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe")
        inactive_conn = KnownCstConnection(pid=200, label="old_conn", active=False)
        # DE still present after run but connection is inactive
        diff = diff_process_inventory([de_proc], [de_proc], [inactive_conn])
        assert 200 in diff.orphan_candidate_pids
        assert 200 in diff.remaining_known_de_pids

    def test_unknown_cst_process_warning_not_target(self):
        unknown = ProcessSnapshot(pid=300, name="CSTDesignEnvironment.exe")
        diff = diff_process_inventory([], [unknown], [])
        assert 300 in diff.remaining_unknown_cst_pids
        # Unknown is NOT an orphan candidate
        assert 300 not in diff.orphan_candidate_pids

    def test_started_ended_pids_deterministic(self):
        before = [ProcessSnapshot(pid=100, name="cstd.exe")]
        after = [
            ProcessSnapshot(pid=100, name="cstd.exe"),
            ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe"),
        ]
        conn = [KnownCstConnection(pid=200, label="new_conn")]
        diff = diff_process_inventory(before, after, conn)
        assert 200 in diff.started_pids
        assert len(diff.ended_pids) == 0

    def test_summary_deterministic(self):
        before = [ProcessSnapshot(pid=100, name="cstd.exe")]
        after = [ProcessSnapshot(pid=100, name="cstd.exe")]
        diff1 = diff_process_inventory(before, after, [])
        diff2 = diff_process_inventory(before, after, [])
        assert diff1.summary == diff2.summary


# ===================================================================
# Emergency cleanup record
# ===================================================================


class TestEmergencyCleanup:
    def test_missing_reason_invalid(self):
        record = EmergencyCleanupRecord(allowed_by_approval=True)
        valid, reasons = validate_emergency_cleanup_record(record)
        assert not valid
        assert "reason_required" in reasons

    def test_kill_command_requires_target_pid(self):
        record = EmergencyCleanupRecord(
            allowed_by_approval=True,
            reason="DE unresponsive",
            command_summary="pid_specific_cleanup_redacted",
            target_pid=None,
            timestamp="2026-06-04T12:00:00",
            residual_process_count=0,
        )
        valid, reasons = validate_emergency_cleanup_record(record)
        assert not valid
        assert "target_pid_required_when_kill_command" in reasons

    def test_timestamp_required(self):
        record = EmergencyCleanupRecord(
            allowed_by_approval=True,
            reason="DE unresponsive",
            timestamp=None,
            residual_process_count=0,
        )
        valid, reasons = validate_emergency_cleanup_record(record)
        assert not valid
        assert "timestamp_required" in reasons

    def test_residual_count_required(self):
        record = EmergencyCleanupRecord(
            allowed_by_approval=True,
            reason="DE unresponsive",
            timestamp="2026-06-04T12:00:00",
            residual_process_count=None,
        )
        valid, reasons = validate_emergency_cleanup_record(record)
        assert not valid
        assert "residual_process_count_required" in reasons

    def test_complete_record_valid(self):
        record = EmergencyCleanupRecord(
            allowed_by_approval=True,
            reason="DE unresponsive after solve",
            target_pid=200,
            command_summary="pid_specific_cleanup_redacted",
            timestamp="2026-06-04T12:00:00",
            residual_process_count=0,
        )
        valid, reasons = validate_emergency_cleanup_record(record)
        assert valid
        assert len(reasons) == 0

    def test_no_approval_invalid(self):
        """Complete record but allowed_by_approval=False is invalid."""
        record = EmergencyCleanupRecord(
            allowed_by_approval=False,
            reason="DE unresponsive",
            timestamp="2026-06-04T12:00:00",
            residual_process_count=0,
        )
        valid, reasons = validate_emergency_cleanup_record(record)
        assert not valid
        assert "emergency_cleanup_not_allowed_by_approval" in reasons

    def test_approved_complete_record_valid(self):
        """Complete record with allowed_by_approval=True is valid."""
        record = EmergencyCleanupRecord(
            allowed_by_approval=True,
            reason="DE unresponsive",
            timestamp="2026-06-04T12:00:00",
            residual_process_count=0,
        )
        valid, reasons = validate_emergency_cleanup_record(record)
        assert valid


# ===================================================================
# Safety summary
# ===================================================================


class TestSafetySummary:
    def test_blocked_target_not_safe(self):
        summary = build_xr_safety_summary(
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            target_selection=TargetSelection(
                allowed=False, target_pid=None,
                reason="blocked", blocked_by=("no_kill_candidates_available",),
            ),
        )
        assert not summary["safe_to_execute_destructive_action"]

    def test_no_approval_not_safe(self):
        summary = build_xr_safety_summary(
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=None,
        )
        assert not summary["safe_to_execute_destructive_action"]
        assert not summary["approved"]
        # No approval and no target selection both contribute
        assert "no_approval" in summary.get("not_safe_reasons", ())
        assert "no_target_selection" in summary.get("not_safe_reasons", ())

    def test_valid_approval_and_target_safe(self):
        ts = select_destructive_target(
            _de_process, _de_conn,
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
        )
        summary = build_xr_safety_summary(
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            target_selection=ts,
        )
        assert summary["safe_to_execute_destructive_action"]
        assert summary["target_allowed"]
        assert summary["target_pid"] == 200

    def test_invalid_emergency_cleanup_not_safe(self):
        bad_cleanup = EmergencyCleanupRecord(
            allowed_by_approval=True,
            reason=None,  # missing reason
        )
        summary = build_xr_safety_summary(
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            emergency_cleanup=bad_cleanup,
        )
        assert not summary["safe_to_execute_destructive_action"]

    def test_orphan_candidates_reflected(self):
        de_proc = ProcessSnapshot(pid=200, name="CSTDesignEnvironment.exe")
        inactive_conn = KnownCstConnection(pid=200, label="old", active=False)
        diff = diff_process_inventory([de_proc], [de_proc], [inactive_conn])
        summary = build_xr_safety_summary(
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            inventory_diff=diff,
        )
        assert summary["orphan_candidate_count"] >= 1

    def test_approval_alone_not_safe_without_target_selection(self):
        """Valid approval alone is not sufficient; target_selection required."""
        summary = build_xr_safety_summary(
            scenario=ExtremeRecoveryFaultKind.DE_PROCESS_KILLED_BEFORE_SOLVE,
            approval=_valid_approval,
            # target_selection omitted
        )
        assert not summary["safe_to_execute_destructive_action"]
        assert summary["approved"]
        assert "no_target_selection" in summary.get("not_safe_reasons", ())


# ===================================================================
# Global safety — no dangerous imports or calls
# ===================================================================


class TestGlobalSafety:
    """Verify the helper module never imports or calls dangerous facilities."""

    def test_no_subprocess_import(self):
        import workflows.rfgun_sao.extreme_recovery_safety as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "import subprocess" not in text
        assert "from subprocess" not in text

    def test_no_os_system(self):
        import workflows.rfgun_sao.extreme_recovery_safety as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "os.system" not in text

    def test_no_taskkill_or_stop_process(self):
        import workflows.rfgun_sao.extreme_recovery_safety as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        # Check for executable command references, not docstring mentions
        assert "call(\"taskkill" not in text
        assert "subprocess.run(\"taskkill" not in text
        assert "os.system(\"taskkill" not in text
        # "Stop-Process" is allowed in docstring examples; check it's not called
        assert "subprocess.run" not in text

    def test_no_cst_import(self):
        import workflows.rfgun_sao.extreme_recovery_safety as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"
