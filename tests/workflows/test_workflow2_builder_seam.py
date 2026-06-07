"""W2-4A: builder ownership seam tests for ``workflows.rfgun_hom_antenna.workflow``.

These tests verify that:
- The workflow-local ``build_workflow_2`` imports and delegates correctly.
- The root ``run_workflow_2.py`` now uses the workflow-local seam.
- The four-value return contract is preserved.

No CST, solver, orchestrator execute, optimizer live run, or scheduler
is invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---- Path setup -------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for _p in (str(_PROJECT_ROOT), _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ==============================================================================
# A. Module import
# ==============================================================================


def test_import_workflow_module():
    """``import workflows.rfgun_hom_antenna.workflow`` succeeds without CST."""
    import workflows.rfgun_hom_antenna.workflow as wf
    assert hasattr(wf, "build_workflow_2")
    assert callable(wf.build_workflow_2)


def test_workflow_module_has_build_function():
    """``build_workflow_2`` exists as a named function in the module."""
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2
    assert callable(build_workflow_2)


# ==============================================================================
# B. Delegation contract
# ==============================================================================


@patch("cst_optimization.factory.CSTConnection")
def test_delegation_preserves_config_identity(MockCST):
    """The wrapper passes the config dict through to the legacy builder
    without wrapping or copying."""
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2

    cfg = {"test": "value", "nested": {"key": 1}}
    ckpt = MagicMock()

    with patch(
        "workflows.rfgun_hom_antenna.workflow._legacy_build"
    ) as mock_legacy:
        mock_legacy.return_value = (MagicMock(), MagicMock(), MagicMock(), None)
        build_workflow_2(cfg, checkpoint_callback=ckpt)

        mock_legacy.assert_called_once()
        args, kwargs = mock_legacy.call_args
        # Config dict identity is preserved (same object, not a copy)
        assert args[0] is cfg, "config identity should be preserved"
        # checkpoint_callback identity is preserved
        assert kwargs.get("checkpoint_callback") is ckpt, (
            "checkpoint_callback identity should be preserved"
        )


@patch("cst_optimization.factory.CSTConnection")
def test_delegation_preserves_checkpoint_callback_identity(MockCST):
    """The wrapper passes the checkpoint_callback through by identity."""
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2

    cfg = {"test": "value"}
    ckpt = MagicMock()

    with patch(
        "workflows.rfgun_hom_antenna.workflow._legacy_build"
    ) as mock_legacy:
        mock_legacy.return_value = (MagicMock(), MagicMock(), MagicMock(), None)
        build_workflow_2(cfg, checkpoint_callback=ckpt)

        args, kwargs = mock_legacy.call_args
        assert "checkpoint_callback" in kwargs
        assert kwargs["checkpoint_callback"] is ckpt


@patch("cst_optimization.factory.CSTConnection")
def test_delegation_call_count(MockCST):
    """The wrapper delegates exactly once."""
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2

    cfg = {"test": "value"}

    with patch(
        "workflows.rfgun_hom_antenna.workflow._legacy_build"
    ) as mock_legacy:
        mock_legacy.return_value = (MagicMock(), MagicMock(), MagicMock(), None)
        build_workflow_2(cfg)

        assert mock_legacy.call_count == 1, (
            f"Expected exactly 1 delegation call, got {mock_legacy.call_count}"
        )


@patch("cst_optimization.factory.CSTConnection")
def test_delegation_returns_four_tuple(MockCST):
    """The wrapper returns exactly what the legacy builder returns — a 4-tuple.

    This test patches the legacy builder and verifies the wrapper returns
    the exact same objects (identity preserved).
    """
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2

    cfg = {"test": "value"}
    fake_orch = MagicMock()
    fake_opt = MagicMock()
    fake_eval = MagicMock()
    fake_retry = None
    expected = (fake_orch, fake_opt, fake_eval, fake_retry)

    with patch(
        "workflows.rfgun_hom_antenna.workflow._legacy_build"
    ) as mock_legacy:
        mock_legacy.return_value = expected
        result = build_workflow_2(cfg)

        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 4, f"Expected 4 values, got {len(result)}"
        # Identity check — wrapper should return same objects
        assert result[0] is fake_orch, "orchestrator identity preserved"
        assert result[1] is fake_opt, "optimizer identity preserved"
        assert result[2] is fake_eval, "evaluator identity preserved"
        assert result[3] is fake_retry, "retry_handler identity preserved"


# ==============================================================================
# C. Root runner import verification
# ==============================================================================


def test_run_workflow_2_now_imports_from_workflow_seam():
    """``run_workflow_2.py`` now imports ``build_workflow_2`` from the
    workflow-local seam, not from the shared factory directly."""
    import run_workflow_2 as rw2

    # The module-level name ``build_workflow_2`` should be resolved from
    # the workflow-local module, not cst_optimization.factory.
    build_fn = getattr(rw2, "build_workflow_2", None)
    assert build_fn is not None, (
        "run_workflow_2 should have a build_workflow_2 attribute"
    )
    # Verify the function's module is the workflow-local seam
    fn_module = getattr(build_fn, "__module__", "")
    assert "rfgun_hom_antenna.workflow" in fn_module, (
        f"Expected build_workflow_2 to come from workflows.rfgun_hom_antenna.workflow, "
        f"got __module__={fn_module!r}"
    )


@patch("run_workflow_2.build_workflow_2")
def test_run_workflow_2_can_be_patched_by_name(mock_build):
    """The existing characterisation test's patch target
    ``run_workflow_2.build_workflow_2`` still works after the import change."""
    import run_workflow_2 as rw2

    # The patch should replace the name in the module namespace
    assert rw2.build_workflow_2 is mock_build


@patch("run_workflow_2.build_workflow_2")
def test_run_workflow_2_main_patch_still_works(mock_build):
    """``run_workflow_2.build_workflow_2`` can still be patched with
    ``MagicMock``, which is what the black-box characterisation test does."""
    pass  # The patch itself is the test — it didn't raise ImportError
