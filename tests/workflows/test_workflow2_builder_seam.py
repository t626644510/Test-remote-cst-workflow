"""W2-4B: builder implementation migration tests.

These tests verify that:
- ``workflows.rfgun_hom_antenna.workflow`` now OWNS the implementation.
- ``cst_optimization.factory.build_workflow_2`` is a compatibility wrapper.
- Importing from the old path ``cst_optimization.factory import build_workflow_2``
  still works and preserves the 4-tuple contract.
- The workflow-local builder and factory wrapper produce consistent results.
- Root ``run_workflow_2.py`` delegates via ``workflows/rfgun_hom_antenna/run.py``
  which imports ``build_workflow_2`` from the workflow-local seam.

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
# A. Module import — workflow owns the implementation
# ==============================================================================


@patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
def test_workflow_module_owns_build_function(MockCST):
    """The workflow-local module has an independent ``build_workflow_2``
    that does NOT delegate to ``cst_optimization.factory``."""
    import workflows.rfgun_hom_antenna.workflow as wf

    assert callable(wf.build_workflow_2)
    # The function's module should be the workflow package, not factory
    fn_module = getattr(wf.build_workflow_2, "__module__", "")
    assert "workflows.rfgun_hom_antenna.workflow" in fn_module, (
        f"Expected build_workflow_2 module to be workflows.rfgun_hom_antenna.workflow, "
        f"got {fn_module!r}"
    )


@patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
def test_workflow_build_returns_four_tuple(MockCST):
    """Workflow-local builder returns the standard 4-tuple (orch, opt, eval, retry)."""
    from workflows.rfgun_hom_antenna.workflow import build_workflow_2

    cfg = {"parameters": [{"name": "p1", "low": 0, "high": 1, "enabled": True}]}
    # Need minimal config that passes build_workflow_2 validation
    cfg["cst"] = {"library_path": "dummy", "connect_mode": "any_or_new"}
    cfg["objectives"] = [{
        "name": "antenna_absorption",
        "mode": "less_than",
        "mode_params": {"threshold": -29.0, "sigma": 2.0},
        "obj_params": {"project": "f2f", "antenna_port": 2,
                        "tree_path": "1D Results\\S-Parameters\\S2,1",
                        "search_freq_ghz": 0.5, "search_width_ghz": 0.01},
    }]
    cfg["projects"] = {"f2f": {"cst_path": "d:/dummy/f2f.cst", "is_pre_filter": True}}
    cfg["optimization"] = {"algorithm": "sao", "n_initial": 1, "n_iterations": 0, "seed": 42}

    result = build_workflow_2(cfg)
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 4, f"Expected 4 values, got {len(result)}"
    orch, opt, evaluator, retry = result
    assert hasattr(orch, "execute"), "orchestrator should have execute()"
    assert hasattr(opt, "optimize"), "optimizer should have optimize()"
    assert callable(evaluator), "evaluator should be callable"


# ==============================================================================
# B. Factory compatibility wrapper
# ==============================================================================


@patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
def test_factory_wrapper_delegates_to_workflow(MockCST):
    """``cst_optimization.factory.build_workflow_2`` now delegates to the
    workflow-local builder."""
    from cst_optimization.factory import build_workflow_2 as factory_build

    cfg = {"parameters": [{"name": "p1", "low": 0, "high": 1, "enabled": True}]}
    cfg["cst"] = {"library_path": "dummy", "connect_mode": "any_or_new"}
    cfg["objectives"] = [{
        "name": "antenna_absorption",
        "mode": "less_than",
        "mode_params": {"threshold": -29.0, "sigma": 2.0},
        "obj_params": {"project": "f2f", "antenna_port": 2,
                        "tree_path": "1D Results\\S-Parameters\\S2,1",
                        "search_freq_ghz": 0.5, "search_width_ghz": 0.01},
    }]
    cfg["projects"] = {"f2f": {"cst_path": "d:/dummy/f2f.cst", "is_pre_filter": True}}
    cfg["optimization"] = {"algorithm": "sao", "n_initial": 1, "n_iterations": 0, "seed": 42}

    # Patch the workflow builder to verify delegation happens
    with patch(
        "workflows.rfgun_hom_antenna.workflow.build_workflow_2"
    ) as mock_wf:
        mock_wf.return_value = (MagicMock(), MagicMock(), MagicMock(), None)
        factory_build(cfg)
        assert mock_wf.call_count == 1, (
            f"Expected factory wrapper to delegate to workflow builder, "
            f"got {mock_wf.call_count} calls"
        )


@patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
def test_factory_wrapper_preserves_four_tuple(MockCST):
    """The factory wrapper's 4-tuple annotation now matches the actual return."""
    from cst_optimization.factory import build_workflow_2 as factory_build

    cfg = {"parameters": [{"name": "p1", "low": 0, "high": 1, "enabled": True}]}
    cfg["cst"] = {"library_path": "dummy", "connect_mode": "any_or_new"}
    cfg["objectives"] = [{
        "name": "antenna_absorption",
        "mode": "less_than",
        "mode_params": {"threshold": -29.0, "sigma": 2.0},
        "obj_params": {"project": "f2f", "antenna_port": 2,
                        "tree_path": "1D Results\\S-Parameters\\S2,1",
                        "search_freq_ghz": 0.5, "search_width_ghz": 0.01},
    }]
    cfg["projects"] = {"f2f": {"cst_path": "d:/dummy/f2f.cst", "is_pre_filter": True}}
    cfg["optimization"] = {"algorithm": "sao", "n_initial": 1, "n_iterations": 0, "seed": 42}

    with patch(
        "workflows.rfgun_hom_antenna.workflow.build_workflow_2"
    ) as mock_wf:
        fake = (MagicMock(), MagicMock(), MagicMock(), None)
        mock_wf.return_value = fake
        result = factory_build(cfg)
        assert result is fake, "factory wrapper should return identity of workflow result"


# ==============================================================================
# C. Old import path still works
# ==============================================================================


@patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
def test_import_from_factory_still_works(MockCST):
    """``from cst_optimization.factory import build_workflow_2`` still works."""
    from cst_optimization.factory import build_workflow_2 as factory_build
    assert callable(factory_build)


# ==============================================================================
# D. Root runner import
# ==============================================================================


def test_run_workflow_2_still_delegates_to_workflow_seam():
    """``run_workflow_2.py`` delegates to ``run.py`` which imports
    ``build_workflow_2`` from the workflow-local seam (W2-7)."""
    import workflows.rfgun_hom_antenna.run as wf2_run

    build_fn = getattr(wf2_run, "build_workflow_2", None)
    assert callable(build_fn), "run.py should have build_workflow_2"
    fn_module = getattr(build_fn, "__module__", "")
    assert "workflows.rfgun_hom_antenna.workflow" in fn_module, (
        f"Expected build_workflow_2 from workflows.rfgun_hom_antenna.workflow, "
        f"got __module__={fn_module!r}"
    )


@patch("workflows.rfgun_hom_antenna.run.build_workflow_2")
def test_run_workflow_2_can_be_patched_by_name(mock_build):
    """The build_workflow_2 reference in the runner can be patched."""
    import workflows.rfgun_hom_antenna.run as wf2_run
    assert wf2_run.build_workflow_2 is mock_build
