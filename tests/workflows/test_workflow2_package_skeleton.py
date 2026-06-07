"""W2-2: skeleton import and presence tests for ``workflows.rfgun_hom_antenna``.

These tests verify that the package skeleton exists and can be imported.
They do NOT call CST, the builder, the orchestrator, or any optimiser.
"""

from __future__ import annotations

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

WF2_PACKAGE = _PROJECT_ROOT / "workflows" / "rfgun_hom_antenna"


# ==============================================================================
# A. Package import
# ==============================================================================


def test_import_package():
    """``import workflows.rfgun_hom_antenna`` succeeds without CST."""
    import workflows.rfgun_hom_antenna as pkg
    assert hasattr(pkg, "__version__")
    assert pkg.__version__ == "0.1.0"
    assert hasattr(pkg, "__legacy_entry__")
    assert pkg.__legacy_entry__ == "run_workflow_2.py"


def test_import_run_module():
    """``import workflows.rfgun_hom_antenna.run`` succeeds without CST."""
    import workflows.rfgun_hom_antenna.run as run_mod
    assert hasattr(run_mod, "main")
    assert callable(run_mod.main)


# ==============================================================================
# B. Runner interface
# ==============================================================================


def test_run_main_is_callable():
    """``run.main()`` exists and is callable."""
    import workflows.rfgun_hom_antenna.run as run_mod
    assert callable(run_mod.main)


def test_run_main_delegates_from_root_shim():
    """``run_workflow_2.main`` is the same function as ``run.main``."""
    import run_workflow_2 as rw2
    import workflows.rfgun_hom_antenna.run as wf2_run
    assert rw2.main is wf2_run.main, (
        "Root shim main should be the same object as run.py main"
    )


# ==============================================================================
# C. Package file presence
# ==============================================================================


def test_readme_exists():
    """Package README.md is present."""
    readme = WF2_PACKAGE / "README.md"
    assert readme.exists(), f"README not found at {readme}"
    content = readme.read_text(encoding="utf-8")
    assert "run_workflow_2.py" in content, (
        "README should document the legacy entry point"
    )


def test_init_docstring_documents_legacy_entry():
    """Package __init__.py docstring mentions the legacy entry point."""
    import workflows.rfgun_hom_antenna
    doc = workflows.rfgun_hom_antenna.__doc__ or ""
    assert "run_workflow_2.py" in doc, (
        "__init__.py docstring should reference the legacy entry point"
    )


def test_run_docstring_documents_runner():
    """``run.py`` module docstring describes the real runner (no longer a placeholder)."""
    import workflows.rfgun_hom_antenna.run as run_mod
    doc = run_mod.__doc__ or ""
    assert "compatibility shim" in doc, (
        "run.py docstring should mention the root is a compatibility shim"
    )
    assert "run_workflow_2.py" in doc, (
        "run.py docstring should reference the root entry point"
    )
    assert "placeholder" not in doc.lower(), (
        "run.py docstring should no longer describe itself as a placeholder"
    )


def test_package_directory_has_expected_files():
    """Package directory contains the three expected skeleton files."""
    expected_files = {"__init__.py", "run.py", "README.md"}
    actual = {p.name for p in WF2_PACKAGE.iterdir() if p.is_file()}
    missing = expected_files - actual
    assert not missing, (
        f"Package directory {WF2_PACKAGE} is missing expected files: {missing}"
    )
