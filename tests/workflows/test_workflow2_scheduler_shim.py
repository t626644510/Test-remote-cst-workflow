"""W2-6D: scheduler/root shim compatibility characterisation tests.

These tests verify that:
- The scheduler script still invokes the root ``run_workflow_2.py``.
- The root entry is a compatibility shim that delegates to the package run module.
- The CLI flags are defined in ``workflows/rfgun_hom_antenna/run.py``.
- The package run module reads co-located ``workflows/rfgun_hom_antenna/config.yaml`` (W2-8) and imports the builder.
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
RUN_MODULE_PATH = _PROJECT_ROOT / "workflows" / "rfgun_hom_antenna" / "run.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _get_root_ast() -> ast.Module:
    """Parse ``run_workflow_2.py`` into an AST.

    The AST is parsed once per test session (pytest caches the module).
    """
    with open(ROOT_ENTRY_PATH, "r", encoding="utf-8") as f:
        return ast.parse(f.read())


def _get_run_ast() -> ast.Module:
    """Parse ``workflows/rfgun_hom_antenna/run.py`` into an AST."""
    with open(RUN_MODULE_PATH, "r", encoding="utf-8") as f:
        return ast.parse(f.read())


def _find_add_argument_calls(tree: ast.Module) -> list[str]:
    """Return the list of ``--flag`` names passed to ``parser.add_argument``
    calls in the module's AST."""
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


def _find_import_from(tree: ast.Module, module_name: str) -> list[str]:
    """Return the list of names imported via ``from <module_name> import ...``."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_name:
            for alias in node.names:
                names.append(alias.name)
    return names


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
# B. Root entry delegation (AST inspection + runtime check)
# ==============================================================================


class TestRootEntryDelegation:
    """Verify that ``run_workflow_2.py`` is a compatibility shim that delegates
    to ``workflows/rfgun_hom_antenna/run.py``."""

    @staticmethod
    def test_root_entry_exists():
        """Root entry ``run_workflow_2.py`` exists."""
        assert ROOT_ENTRY_PATH.exists(), (
            f"Root entry not found at {ROOT_ENTRY_PATH}"
        )

    @staticmethod
    def test_root_entry_is_shim():
        """AST: root entry imports ``main`` from the package run module."""
        tree = _get_root_ast()
        names = _find_import_from(tree, "workflows.rfgun_hom_antenna.run")
        assert "main" in names, (
            "run_workflow_2.py should import main from workflows.rfgun_hom_antenna.run"
        )

    @staticmethod
    def test_root_entry_main_is_delegated():
        """Runtime: ``run_workflow_2.main`` is from the workflow-package run module."""
        import run_workflow_2 as rw2

        main_fn = getattr(rw2, "main", None)
        assert main_fn is not None, "run_workflow_2 should export main"
        fn_module = getattr(main_fn, "__module__", "")
        assert "rfgun_hom_antenna.run" in fn_module, (
            f"Expected main from workflows.rfgun_hom_antenna.run, "
            f"got __module__={fn_module!r}"
        )

    @staticmethod
    def test_root_entry_has_no_cli_parser():
        """AST: root shim does NOT contain ``add_argument`` calls (they are in run.py)."""
        tree = _get_root_ast()
        flags = _find_add_argument_calls(tree)
        assert len(flags) == 0, (
            f"Root shim should not define CLI flags, found: {flags}"
        )

    @staticmethod
    def test_root_entry_has_no_config_path():
        """AST: root shim does NOT contain ``config/default.yaml`` (it is in run.py)."""
        tree = _get_root_ast()
        strings = _find_string_literals(tree)
        assert "config/default.yaml" not in strings, (
            "config/default.yaml path should be in run.py, not the root shim"
        )

    @staticmethod
    def test_root_entry_docstring_mentions_shim():
        """Root shim docstring accurately describes itself as a compatibility shim."""
        import run_workflow_2 as rw2

        doc = rw2.__doc__ or ""
        assert "two independent CST windows" not in doc, (
            "R1 should still be resolved: stale docstring must not appear"
        )
        assert "compatibility shim" in doc, (
            "Root entry docstring should mention it is a compatibility shim"
        )


# ==============================================================================
# C. Package run module CLI and config (AST inspection)
# ==============================================================================


class TestRunModuleCLI:
    """Characterise that ``workflows/rfgun_hom_antenna/run.py`` defines the
    expected CLI flags that the scheduler depends on."""

    @staticmethod
    def test_run_module_exists():
        """Package run module exists at the expected path."""
        assert RUN_MODULE_PATH.exists(), (
            f"Run module not found at {RUN_MODULE_PATH}"
        )

    @staticmethod
    def test_cli_defines_auto_resume():
        """AST: run module defines ``--auto-resume`` via parser.add_argument."""
        run_tree = _get_run_ast()
        flags = _find_add_argument_calls(run_tree)
        assert "--auto-resume" in flags, (
            "workflows/rfgun_hom_antenna/run.py should define --auto-resume"
        )

    @staticmethod
    def test_cli_defines_heartbeat():
        """AST: run module defines ``--heartbeat`` via parser.add_argument."""
        run_tree = _get_run_ast()
        flags = _find_add_argument_calls(run_tree)
        assert "--heartbeat" in flags, (
            "workflows/rfgun_hom_antenna/run.py should define --heartbeat"
        )

    @staticmethod
    def test_cli_defines_warmup_from_db():
        """AST: run module defines ``--warmup-from-db`` via parser.add_argument."""
        run_tree = _get_run_ast()
        flags = _find_add_argument_calls(run_tree)
        assert "--warmup-from-db" in flags, (
            "workflows/rfgun_hom_antenna/run.py should define --warmup-from-db"
        )

    @staticmethod
    def test_cli_defines_all_scheduler_flags():
        """AST: run module defines all three flags the scheduler depends on."""
        run_tree = _get_run_ast()
        flags = _find_add_argument_calls(run_tree)
        for flag in ("--auto-resume", "--heartbeat", "--warmup-from-db"):
            assert flag in flags, (
                f"workflows/rfgun_hom_antenna/run.py should define {flag}"
            )

    @staticmethod
    def test_no_extra_unexpected_flags():
        """AST: run module has exactly the three expected flags (no unexpected
        new flags that would indicate a major CLI refactor)."""
        run_tree = _get_run_ast()
        flags = _find_add_argument_calls(run_tree)
        expected = {"--auto-resume", "--heartbeat", "--warmup-from-db"}
        assert set(flags) == expected, (
            f"Expected CLI flags {expected}, got {set(flags)}. "
            "If a new flag was intentionally added, update this assertion."
        )

    @staticmethod
    def test_run_module_reads_local_config_yaml():
        """AST: run module references its co-located ``config.yaml`` (W2-8
        runtime source), and does NOT reference ``config/default.yaml``."""
        run_tree = _get_run_ast()
        strings = _find_string_literals(run_tree)
        assert "config.yaml" in strings, (
            "W2-8: run.py should reference its co-located config.yaml"
        )
        assert "config/default.yaml" not in strings, (
            "W2-8: run.py should NOT reference config/default.yaml anymore"
        )

    @staticmethod
    def test_run_module_imports_build_workflow_2():
        """AST: run module imports ``build_workflow_2`` from the workflow-local
        package."""
        run_tree = _get_run_ast()
        names = _find_import_from(run_tree, "workflows.rfgun_hom_antenna.workflow")
        assert "build_workflow_2" in names, (
            "run.py should import build_workflow_2 from workflows.rfgun_hom_antenna.workflow"
        )

    @staticmethod
    def test_run_module_build_workflow_source():
        """Runtime: ``run.py``'s ``build_workflow_2`` is resolved from the
        workflow-local package."""
        import workflows.rfgun_hom_antenna.run as wf2_run  # noqa: F811

        build_fn = getattr(wf2_run, "build_workflow_2", None)
        assert build_fn is not None, "run.py should have build_workflow_2"
        fn_module = getattr(build_fn, "__module__", "")
        assert "rfgun_hom_antenna.workflow" in fn_module, (
            f"Expected import from workflows.rfgun_hom_antenna.workflow, "
            f"got __module__={fn_module!r}"
        )

    @staticmethod
    def test_run_module_docstring_connection():
        """The run module docstring accurately describes the single CST connection."""
        import workflows.rfgun_hom_antenna.run as wf2_run  # noqa: F811

        doc = wf2_run.__doc__ or ""
        assert "two independent CST windows" not in doc, (
            "R1 should be resolved: stale docstring must not appear"
        )
        assert "single CST" in doc, (
            "run.py docstring should mention single CST connection"
        )
