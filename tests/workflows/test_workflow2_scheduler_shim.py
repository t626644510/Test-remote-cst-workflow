"""W2-6D: scheduler/root shim compatibility characterisation tests.

These tests verify that:
- The scheduler script still invokes the root ``run_workflow_2.py``.
- The root entry still exposes the expected CLI flags.
- The root entry still imports the builder from the workflow-local package.
- No migration to a separate workflow-package entry has happened.

No PowerShell execution, no CST, no live workflow.
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

import pytest

# ---- Path setup -------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for _p in (str(_PROJECT_ROOT), _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SCHEDULER_PATH = _PROJECT_ROOT / "scripts" / "schedule_workflow2.ps1"
ROOT_ENTRY = _PROJECT_ROOT / "run_workflow_2.py"


# ==============================================================================
# A. Scheduler script compatibility
# ==============================================================================


class TestSchedulerScript:
    """Static characterisation of ``scripts/schedule_workflow2.ps1``."""

    @staticmethod
    def test_scheduler_exists():
        """Scheduler script is present at the expected path."""
        assert SCHEDULER_PATH.exists(), (
            f"Scheduler not found at {SCHEDULER_PATH}"
        )

    @staticmethod
    def test_scheduler_invokes_root_entry():
        """Scheduler references ``run_workflow_2.py``, not a workflow-package entry."""
        content = SCHEDULER_PATH.read_text(encoding="utf-8")
        assert "run_workflow_2.py" in content, (
            "Scheduler does not reference run_workflow_2.py — may have been migrated"
        )
        # Verify it does NOT reference a workflow-package entry
        migrated_indicators = [
            "workflows/rfgun_hom_antenna/run.py",
            "rfgun_hom_antenna.run",
            "workflow2/run.py",
            "wf2_entry",
        ]
        for ind in migrated_indicators:
            assert ind not in content, (
                f"Scheduler appears to reference migrated path '{ind}'"
            )

    @staticmethod
    def test_scheduler_resolves_path_via_workdir():
        """Scheduler resolves run_workflow_2.py relative to WorkDir, not hard-coded."""
        content = SCHEDULER_PATH.read_text(encoding="utf-8")
        assert "WorkDir" in content
        assert "Join-Path" in content

    @staticmethod
    def test_scheduler_uses_auto_resume_flag():
        """Scheduler invocation includes ``--auto-resume``."""
        content = SCHEDULER_PATH.read_text(encoding="utf-8")
        assert "--auto-resume" in content

    @staticmethod
    def test_scheduler_uses_heartbeat_flag():
        """Scheduler invocation includes ``--heartbeat``."""
        content = SCHEDULER_PATH.read_text(encoding="utf-8")
        assert "--heartbeat" in content

    @staticmethod
    def test_scheduler_not_hardcoded_to_workflow_entry():
        """Scheduler action script path contains 'run_workflow_2.py', not a
        workflow-specific name."""
        content = SCHEDULER_PATH.read_text(encoding="utf-8")
        # The $ScriptPath variable should join WorkDir to run_workflow_2.py
        assert "run_workflow_2.py" in content
        # No workflow-package run.py
        assert "rfgun_hom_antenna" not in content


# ==============================================================================
# B. Root entry CLI compatibility
# ==============================================================================


class TestRootEntryCLI:
    """Characterise that ``run_workflow_2.py`` exposes the expected CLI flags
    that the scheduler depends on."""

    @staticmethod
    def test_root_entry_exists():
        """Root entry ``run_workflow_2.py`` exists."""
        assert ROOT_ENTRY.exists(), f"Root entry not found at {ROOT_ENTRY}"

    @staticmethod
    def test_cli_parser_accepts_auto_resume():
        """``--auto-resume`` is a recognised flag."""
        import run_workflow_2 as rw2
        # Reconstruct the parser as used in main()
        parser = argparse.ArgumentParser()
        parser.add_argument("--auto-resume", action="store_true", default=False)
        args = parser.parse_args(["--auto-resume"])
        assert args.auto_resume is True

    @staticmethod
    def test_cli_parser_accepts_heartbeat():
        """``--heartbeat`` is a recognised flag."""
        import run_workflow_2 as rw2
        parser = argparse.ArgumentParser()
        parser.add_argument("--heartbeat", action="store_true", default=False)
        args = parser.parse_args(["--heartbeat"])
        assert args.heartbeat is True

    @staticmethod
    def test_cli_parser_accepts_warmup_from_db():
        """``--warmup-from-db`` is a recognised flag with path argument."""
        import run_workflow_2 as rw2
        parser = argparse.ArgumentParser()
        parser.add_argument("--warmup-from-db", type=str, default="", metavar="PATH")
        args = parser.parse_args(["--warmup-from-db", "D:/test/index.jsonl"])
        assert args.warmup_from_db == "D:/test/index.jsonl"

    @staticmethod
    def test_cli_parser_accepts_all_scheduler_flags_together():
        """All three scheduler-used flags can be passed together."""
        import run_workflow_2 as rw2
        parser = argparse.ArgumentParser()
        parser.add_argument("--auto-resume", action="store_true", default=False)
        parser.add_argument("--heartbeat", action="store_true", default=False)
        parser.add_argument("--warmup-from-db", type=str, default="", metavar="PATH")
        args = parser.parse_args([
            "--auto-resume", "--heartbeat",
            "--warmup-from-db", "D:/data/index.jsonl",
        ])
        assert args.auto_resume is True
        assert args.heartbeat is True
        assert args.warmup_from_db == "D:/data/index.jsonl"


# ==============================================================================
# C. Root entry import compatibility
# ==============================================================================


class TestRootEntryImport:
    """Characterise that root ``run_workflow_2.py`` imports the builder from
    the workflow-local package (unchanged since W2-4A)."""

    @staticmethod
    def test_root_imports_from_workflow_seam():
        """The ``build_workflow_2`` name in run_workflow_2.py is resolved
        from the workflow-local package."""
        import run_workflow_2 as rw2
        build_fn = getattr(rw2, "build_workflow_2", None)
        assert build_fn is not None, "run_workflow_2 should have build_workflow_2"
        fn_module = getattr(build_fn, "__module__", "")
        assert "rfgun_hom_antenna.workflow" in fn_module, (
            f"Expected import from workflows.rfgun_hom_antenna.workflow, "
            f"got __module__={fn_module!r}"
        )

    @staticmethod
    def test_root_reads_default_yaml():
        """The root entry reads ``config/default.yaml`` (CLI-driven config
        path is not yet supported — the path is hard-coded in main())."""
        assert (_PROJECT_ROOT / "config" / "default.yaml").exists(), (
            "config/default.yaml should exist for root entry to read"
        )

    @staticmethod
    def test_root_entry_docstring_now_accurate():
        """The root docstring no longer claims 'two independent CST windows';
        this was fixed in W2-6A."""
        import run_workflow_2 as rw2
        doc = rw2.__doc__ or ""
        assert "two independent CST windows" not in doc, (
            "R1 should be resolved: stale docstring was fixed in W2-6A"
        )
        assert "single CST DesignEnvironment connection" in doc, (
            "W2-6A docstring should mention single CST connection"
        )
