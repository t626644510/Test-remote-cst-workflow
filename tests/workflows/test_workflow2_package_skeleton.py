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
    assert hasattr(run_mod, "LEGACY_ENTRY")
    assert run_mod.LEGACY_ENTRY == "run_workflow_2.py"
    assert run_mod.PACKAGE_ROOT == _PROJECT_ROOT


# ==============================================================================
# B. Placeholder functions
# ==============================================================================


def test_describe_legacy_entry_returns_string():
    """``describe_legacy_entry()`` returns a description without side effects."""
    from workflows.rfgun_hom_antenna.run import describe_legacy_entry
    desc = describe_legacy_entry()
    assert isinstance(desc, str)
    assert "run_workflow_2.py" in desc


def test_get_legacy_entrypoint_returns_path():
    """``get_legacy_entrypoint()`` returns the path to the root entry."""
    from workflows.rfgun_hom_antenna.run import get_legacy_entrypoint
    path = get_legacy_entrypoint()
    assert isinstance(path, Path)
    assert path.name == "run_workflow_2.py"
    assert path.exists(), (
        f"Legacy entry {path} should exist — it is the current public entry point"
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


def test_run_docstring_documents_status():
    """``run.py`` module docstring documents that this is a placeholder."""
    import workflows.rfgun_hom_antenna.run as run_mod
    doc = run_mod.__doc__ or ""
    assert "placeholder" in doc.lower(), (
        "run.py docstring should clearly state it is a placeholder"
    )
    assert "run_workflow_2.py" in doc, (
        "run.py docstring should reference the legacy entry point"
    )


def test_run_module_exports_all():
    """``run.py`` exports the expected names in ``__all__``."""
    from workflows.rfgun_hom_antenna.run import __all__, LEGACY_ENTRY, PACKAGE_ROOT
    assert isinstance(__all__, list)
    assert "LEGACY_ENTRY" in __all__
    assert "PACKAGE_ROOT" in __all__
    assert "describe_legacy_entry" in __all__
    assert "get_legacy_entrypoint" in __all__


def test_package_directory_has_expected_files():
    """Package directory contains the three expected skeleton files."""
    expected_files = {"__init__.py", "run.py", "README.md"}
    actual = {p.name for p in WF2_PACKAGE.iterdir() if p.is_file()}
    missing = expected_files - actual
    assert not missing, (
        f"Package directory {WF2_PACKAGE} is missing expected files: {missing}"
    )
