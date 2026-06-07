"""W2-6D: scheduler/root shim compatibility characterisation tests.

These tests verify that:
- The scheduler script still invokes the root ``run_workflow_2.py``.
- The root entry still exposes the expected CLI flags.
- The root entry still imports the builder from the workflow-local package.
- No migration to a separate workflow-package entry has happened.

No PowerShell execution, no CST, no live workflow.
"""

from __future__ import annotations

import ast
import sys
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
ROOT_ENTRY_PATH = _PROJECT_ROOT / "run_workflow_2.py"


# ---------------------------------------------------------------------------
# AST helper
# ---------------------------------------------------------------------------


def _get_root_ast() -> ast.Module:
    """Parse ``run_workflow_2.py`` into an AST.

    The AST is parsed once per test session (pytest caches the module).
    """
    with open(ROOT_ENTRY_PATH, "r", encoding="utf-8") as f:
        return ast.parse(f.read())


def _find_add_argument_calls(tree: ast.Module) -> list[str]:
    """Return the list of ``--flag`` names passed to ``parser.add_argument``
    calls in the root entry's AST."""
    flags: list[str] = []
    for node in ast.walk(tree):
        # Match: parser.add_argument("--flag", ...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith("--")
        ):
            flags.append(node.args[0].value)
    return flags


def _find_string_literals(tree: ast.Module) -> list[str]:
    """Return all string constants found in the AST."""
    strings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
    return strings


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
        assert "run_workflow_2.py" in content
        assert "rfgun_hom_antenna" not in content


# ==============================================================================
# B. Root entry CLI compatibility (AST inspection)
# ==============================================================================


class TestRootEntryCLI:
    """Characterise that ``run_workflow_2.py`` exposes the expected CLI flags
    that the scheduler depends on, using AST inspection — no parser invocation."""

    @staticmethod
    def test_root_entry_exists():
        """Root entry ``run_workflow_2.py`` exists."""
        assert ROOT_ENTRY_PATH.exists(), (
            f"Root entry not found at {ROOT_ENTRY_PATH}"
        )

    @staticmethod
    def test_cli_defines_auto_resume():
        """AST: root entry defines ``--auto-resume`` via parser.add_argument."""
        tree = _get_root_ast()
        flags = _find_add_argument_calls(tree)
        assert "--auto-resume" in flags, (
            "run_workflow_2.py should define --auto-resume CLI flag"
        )

    @staticmethod
    def test_cli_defines_heartbeat():
        """AST: root entry defines ``--heartbeat`` via parser.add_argument."""
        tree = _get_root_ast()
        flags = _find_add_argument_calls(tree)
        assert "--heartbeat" in flags, (
            "run_workflow_2.py should define --heartbeat CLI flag"
        )

    @staticmethod
    def test_cli_defines_warmup_from_db():
        """AST: root entry defines ``--warmup-from-db`` via parser.add_argument."""
        tree = _get_root_ast()
        flags = _find_add_argument_calls(tree)
        assert "--warmup-from-db" in flags, (
            "run_workflow_2.py should define --warmup-from-db CLI flag"
        )

    @staticmethod
    def test_cli_defines_all_scheduler_flags():
        """AST: the root entry defines all three flags the scheduler depends on."""
        tree = _get_root_ast()
        flags = _find_add_argument_calls(tree)
        for flag in ("--auto-resume", "--heartbeat", "--warmup-from-db"):
            assert flag in flags, (
                f"run_workflow_2.py should define {flag}"
            )

    @staticmethod
    def test_no_extra_unexpected_flags():
        """AST: the root entry has exactly the three expected flags (no
        unexpected new flags that would indicate a major CLI refactor)."""
        tree = _get_root_ast()
        flags = _find_add_argument_calls(tree)
        # When this test fails, review whether the new flag is intentional
        # and update both scheduler and characterisation tests.
        expected = {"--auto-resume", "--heartbeat", "--warmup-from-db"}
        assert set(flags) == expected, (
            f"Expected CLI flags {expected}, got {set(flags)}. "
            "If a new flag was intentionally added, update this assertion."
        )


# ==============================================================================
# C. Root entry import and config path (AST inspection)
# ==============================================================================


class TestRootEntryConfig:
    """Characterise that root ``run_workflow_2.py`` still reads
    ``config/default.yaml`` and imports from the workflow-local package."""

    @staticmethod
    def test_root_reads_default_yaml():
        """AST: root entry source contains ``config/default.yaml`` as a
        file-path string literal (hard-coded config path)."""
        tree = _get_root_ast()
        strings = _find_string_literals(tree)
        assert "config/default.yaml" in strings, (
            "run_workflow_2.py should contain 'config/default.yaml' "
            "as a hard-coded path string"
        )

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
