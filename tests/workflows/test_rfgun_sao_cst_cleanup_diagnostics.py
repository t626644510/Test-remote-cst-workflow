"""No-CST tests for CST cleanup diagnostics (Phase P1).

Covers process classification, orphan DE detection, cleanup observation
summary, and safety boundaries (no CST imports, no taskkill, no file I/O).
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

from workflows.rfgun_sao.cst_cleanup_diagnostics import (
    CstProcessInfo,
    classify_cst_process,
    should_force_kill_orphan_de,
    summarize_cleanup_observation,
)


# ---------------------------------------------------------------------------
# classify_cst_process
# ---------------------------------------------------------------------------


class TestClassifyCstProcess:
    def test_cstd_is_licensing_service(self) -> None:
        assert classify_cst_process("cstd") == "licensing_service"
        assert classify_cst_process("cstd.exe") == "licensing_service"
        assert classify_cst_process("CSTD") == "licensing_service"
        assert classify_cst_process("CSTD.EXE") == "licensing_service"

    def test_de_is_design_environment(self) -> None:
        assert (
            classify_cst_process("CST DESIGN ENVIRONMENT_AMD64")
            == "design_environment"
        )
        assert (
            classify_cst_process("cst_design_environment_amd64")
            == "design_environment"
        )
        assert (
            classify_cst_process("cst_design_environment_amd64.exe")
            == "design_environment"
        )
        assert (
            classify_cst_process("cst_design_environment")
            == "design_environment"
        )

    def test_heuristic_detects_variant(self) -> None:
        """Names containing both 'cst' and 'design' are classified as DE."""
        assert (
            classify_cst_process("CST_Design_Environment_2026")
            == "design_environment"
        )
        assert (
            classify_cst_process("cst.myorg.designenv")
            == "design_environment"
        )

    def test_unknown_returns_unknown(self) -> None:
        assert classify_cst_process("explorer.exe") == "unknown"
        assert classify_cst_process("python.exe") == "unknown"
        assert classify_cst_process("notepad.exe") == "unknown"

    def test_empty_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="process_name must be non-empty"):
            classify_cst_process("")
        with pytest.raises(ValueError, match="process_name must be non-empty"):
            classify_cst_process("   ")

    def test_window_title_does_not_affect_classification(self) -> None:
        """Window-title parameters are informational only."""
        assert classify_cst_process(
            "cstd", has_window_title=False,
        ) == "licensing_service"
        assert classify_cst_process(
            "cstd", has_window_title=True,
        ) == "licensing_service"
        assert classify_cst_process(
            "CST DESIGN ENVIRONMENT_AMD64", has_window_title=True,
        ) == "design_environment"


# ---------------------------------------------------------------------------
# should_force_kill_orphan_de
# ---------------------------------------------------------------------------


class TestShouldForceKillOrphanDe:
    def test_licensing_service_never_kill(self) -> None:
        """cstd.exe is never an orphan candidate."""
        info = CstProcessInfo(
            pid=10184, process_name="cstd.exe", has_window_title=False,
        )
        kill, reason = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is False
        assert "licensing" in reason

    def test_de_with_window_after_cleanup_is_orphan(self) -> None:
        """DE with visible window after claimed cleanup is orphan."""
        info = CstProcessInfo(
            pid=30808, process_name="CST DESIGN ENVIRONMENT_AMD64",
            has_window_title=True,
            main_window_title="CST Studio Suite 2026",
        )
        kill, reason = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is True
        assert "window still present" in reason

    def test_de_without_window_after_claimed_closed_is_orphan(self) -> None:
        """DE without window after claimed cleanup is orphan."""
        info = CstProcessInfo(
            pid=30808, process_name="CST DESIGN ENVIRONMENT_AMD64",
            has_window_title=False,
        )
        kill, reason = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is True
        assert "without window after claimed" in reason

    def test_de_without_window_before_cleanup_not_orphan(self) -> None:
        """DE without window before cleanup is not yet orphan."""
        info = CstProcessInfo(
            pid=30808, process_name="CST DESIGN ENVIRONMENT_AMD64",
            has_window_title=False,
        )
        kill, reason = should_force_kill_orphan_de(
            info, workflow_claimed_closed=False,
        )
        assert kill is False
        assert "cleanup not yet claimed" in reason

    def test_invalid_pid_never_kill(self) -> None:
        """PID <= 0 is never a kill candidate."""
        info = CstProcessInfo(
            pid=0, process_name="CST DESIGN ENVIRONMENT_AMD64",
            has_window_title=True,
        )
        kill, _ = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is False

        info2 = CstProcessInfo(
            pid=-1, process_name="CST DESIGN ENVIRONMENT_AMD64",
            has_window_title=True,
        )
        kill2, _ = should_force_kill_orphan_de(
            info2, workflow_claimed_closed=True,
        )
        assert kill2 is False

    def test_empty_process_name_never_kill(self) -> None:
        """Empty process name is never a kill candidate."""
        info = CstProcessInfo(
            pid=12345, process_name="", has_window_title=True,
        )
        kill, _ = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is False

    def test_unknown_process_never_kill(self) -> None:
        """Unknown process type is never a kill candidate."""
        info = CstProcessInfo(
            pid=12345, process_name="explorer.exe", has_window_title=True,
        )
        kill, _ = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is False

    def test_de_heuristic_variant_detected_as_orphan(self) -> None:
        """Heuristic-match DE variant is detected as orphan."""
        info = CstProcessInfo(
            pid=40000, process_name="CST_Design_Environment_2026.exe",
            has_window_title=True,
        )
        cls = classify_cst_process(info.process_name)
        assert cls == "design_environment"
        kill, _ = should_force_kill_orphan_de(
            info, workflow_claimed_closed=True,
        )
        assert kill is True


# ---------------------------------------------------------------------------
# summarize_cleanup_observation
# ---------------------------------------------------------------------------


class TestSummarizeCleanupObservation:
    def test_no_remaining_processes(self) -> None:
        """No remaining processes produces clean summary."""
        result = summarize_cleanup_observation(
            workflow_claimed_closed=True,
            workflow_pid=56996,
            remaining_processes=[],
        )
        assert result["remaining_count"] == 0
        assert len(result["orphan_candidates"]) == 0
        assert result["summary"] == "no remaining CST processes"
        assert result["workflow_pid"] == 56996
        assert result["workflow_claimed_closed"] is True

    def test_default_remaining_processes_is_empty(self) -> None:
        """Default None for remaining_processes is treated as empty."""
        result = summarize_cleanup_observation(workflow_claimed_closed=True)
        assert result["remaining_count"] == 0

    def test_only_licensing_service_no_orphan(self) -> None:
        """Only cstd.exe remaining -no orphan candidates."""
        procs = [
            CstProcessInfo(
                pid=10184, process_name="cstd.exe", has_window_title=False,
            ),
        ]
        result = summarize_cleanup_observation(
            workflow_claimed_closed=True,
            workflow_pid=56996,
            remaining_processes=procs,
        )
        assert result["remaining_count"] == 1
        assert len(result["orphan_candidates"]) == 0
        assert "none orphan" in result["summary"]

    def test_orphan_de_detected(self) -> None:
        """DE with window alongside cstd -orphan detected."""
        procs = [
            CstProcessInfo(
                pid=10184, process_name="cstd.exe", has_window_title=False,
            ),
            CstProcessInfo(
                pid=30808, process_name="CST DESIGN ENVIRONMENT_AMD64",
                has_window_title=True,
                main_window_title="CST Studio Suite 2026",
            ),
        ]
        result = summarize_cleanup_observation(
            workflow_claimed_closed=True,
            workflow_pid=56996,
            remaining_processes=procs,
        )
        assert result["remaining_count"] == 2
        assert len(result["orphan_candidates"]) == 1
        assert result["orphan_candidates"][0]["pid"] == 30808
        assert "orphan DE candidate" in result["summary"]

    def test_multiple_orphans_reported(self) -> None:
        """Multiple orphan DE processes are all reported."""
        procs = [
            CstProcessInfo(
                pid=10184, process_name="cstd.exe", has_window_title=False,
            ),
            CstProcessInfo(
                pid=20001, process_name="CST DESIGN ENVIRONMENT_AMD64",
                has_window_title=True,
            ),
            CstProcessInfo(
                pid=20002, process_name="CST DESIGN ENVIRONMENT_AMD64",
                has_window_title=False,
            ),
        ]
        result = summarize_cleanup_observation(
            workflow_claimed_closed=True,
            workflow_pid=56996,
            remaining_processes=procs,
        )
        assert result["remaining_count"] == 3
        assert len(result["orphan_candidates"]) == 2

    def test_no_workflow_pid_preserved(self) -> None:
        """None workflow_pid is preserved in output."""
        result = summarize_cleanup_observation(
            workflow_claimed_closed=True,
            workflow_pid=None,
            remaining_processes=[],
        )
        assert result["workflow_pid"] is None


# ---------------------------------------------------------------------------
# Safety -no forbidden imports / runtime execution
# ---------------------------------------------------------------------------


class TestSafety:
    def test_no_cst_imports(self) -> None:
        """Module does not import CST libraries."""
        import workflows.rfgun_sao.cst_cleanup_diagnostics as diag
        src_path = diag.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = [
            "cst.interface", "cst.results", "import cst",
            "from cst.",
        ]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"

    def test_no_taskkill_or_kill(self) -> None:
        """Module does not call taskkill, os.kill, or subprocess."""
        import workflows.rfgun_sao.cst_cleanup_diagnostics as diag
        src_path = diag.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = [
            "taskkill", "os.kill", "subprocess", "Popen",
            "CreateProcess", "TerminateProcess",
        ]
        for item in forbidden:
            assert item not in text, f"should not contain {item!r}"

    def test_no_file_io(self) -> None:
        """Module does not perform file I/O."""
        import workflows.rfgun_sao.cst_cleanup_diagnostics as diag
        src_path = diag.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = [".write", ".read", "open(", "pathlib"]
        for item in forbidden:
            assert item not in text, f"should not perform file I/O ({item!r})"

    def test_no_psutil(self) -> None:
        """Module does not import psutil."""
        import workflows.rfgun_sao.cst_cleanup_diagnostics as diag
        src_path = diag.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "psutil" not in text
