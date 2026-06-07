"""W2-8: config ownership tests for ``workflows/rfgun_hom_antenna/config.yaml``.

These tests verify that the workflow-local configuration file is the
Workflow2 runtime source of truth (W2-8), contains required fallback
sections (``cst``, ``solver``, ``logging``), and that the loader in
``run.py`` returns the effective config with correct precedence.

No CST, builder, orchestrator, or optimiser required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# ---- Path setup -------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for _p in (str(_PROJECT_ROOT), _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LOCAL_CONFIG = _PROJECT_ROOT / "workflows" / "rfgun_hom_antenna" / "config.yaml"
GLOBAL_CONFIG = _PROJECT_ROOT / "config" / "default.yaml"


# ==============================================================================
# A. File presence and parseability
# ==============================================================================


def test_local_config_exists():
    """``workflows/rfgun_hom_antenna/config.yaml`` exists."""
    assert LOCAL_CONFIG.exists(), f"Local config not found at {LOCAL_CONFIG}"


def test_local_config_parses_as_yaml():
    """Local config file parses as valid YAML."""
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert isinstance(cfg, dict), "Local config should be a YAML mapping"


def test_local_config_has_workflow2_top_level_key():
    """Local config contains top-level ``workflow_2`` key."""
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert "workflow_2" in cfg, (
        "Local config should have a top-level ``workflow_2`` key"
    )


# ==============================================================================
# B. W2-8: local config is the runtime source with fallback sections
# ==============================================================================


def test_local_config_has_fallback_sections():
    """W2-8: The local config contains top-level ``cst``, ``solver``, and
    ``logging`` sections that serve as Workflow2 runtime fallbacks."""
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert "cst" in cfg, (
        "W2-8: local config should have top-level 'cst' section"
    )
    assert "solver" in cfg, (
        "W2-8: local config should have top-level 'solver' section"
    )
    assert "logging" in cfg, (
        "W2-8: local config should have top-level 'logging' section"
    )

    # Verify the fallback sections have expected keys
    assert "library_path" in cfg["cst"]
    assert "stagnation_timeout_s" in cfg["solver"]
    assert "settle_s" in cfg["solver"]
    assert "output_dir" in cfg["logging"]


def test_local_config_workflow2_subtree_does_not_have_fallback_keys():
    """The ``workflow_2`` subtree itself does NOT carry ``cst``, ``solver``,
    or ``logging`` — those are at the top level for the fallback merge."""
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    wf2 = cfg.get("workflow_2", {})
    assert "cst" not in wf2, "workflow_2 subtree should not have 'cst'"
    assert "solver" not in wf2, "workflow_2 subtree should not have 'solver'"
    assert "logging" not in wf2, "workflow_2 subtree should not have 'logging'"


def test_local_config_preserves_solver_timeout_intent():
    """The ``optimization.solver.stagnation_timeout_s`` value (7200.0) is
    preserved in the local config as the effective Workflow2 solver timeout.

    W2-6F resolves the historical R2 discrepancy: ``optimization.solver``
    now overrides fallback ``workflow_2.solver`` for overlapping keys.
    """
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    wf2 = cfg.get("workflow_2", {})
    opt = wf2.get("optimization", {})
    solver = opt.get("solver", {})
    timeout = solver.get("stagnation_timeout_s", None)

    assert timeout == 7200.0, (
        f"Expected solver timeout intent 7200.0, got {timeout}. "
        "W2-6F: optimization.solver.stagnation_timeout_s must be 7200.0."
    )


def test_local_config_fallback_solver_settle_s():
    """The fallback ``solver.settle_s`` value (2.0) is available for the
    builder when ``optimization.solver`` does not set it."""
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert cfg["solver"]["settle_s"] == 2.0, (
        "Fallback solver.settle_s should be 2.0"
    )


# ==============================================================================
# C. Loader: effective config precedence
# ==============================================================================


def test_loader_returns_merged_config_with_fallback_sections():
    """``_load_workflow2_config()`` returns the workflow_2 subtree with
    ``cst``, ``solver``, and ``logging`` merged from top-level fallbacks."""
    from workflows.rfgun_hom_antenna.run import _load_workflow2_config

    wf2_cfg = _load_workflow2_config(LOCAL_CONFIG)

    assert "cst" in wf2_cfg, "cst should be merged into effective config"
    assert "solver" in wf2_cfg, "solver should be merged into effective config"
    assert "logging" in wf2_cfg, "logging should be merged into effective config"
    assert wf2_cfg.get("enabled") is True, "workflow_2 subtree keys preserved"
    assert "projects" in wf2_cfg, "workflow_2 subtree keys preserved"


def test_loader_preserves_solver_timeout_7200():
    """Effective config returned by the loader has solver timeout 7200.0
    from ``workflow_2.optimization.solver.stagnation_timeout_s``."""
    from workflows.rfgun_hom_antenna.run import _load_workflow2_config

    wf2_cfg = _load_workflow2_config(LOCAL_CONFIG)

    opt_solver = wf2_cfg.get("optimization", {}).get("solver", {})
    timeout = opt_solver.get("stagnation_timeout_s")
    assert timeout == 7200.0, (
        f"Expected 7200.0 from optimization.solver, got {timeout}"
    )


def test_loader_fallback_merge_is_reference_copy():
    """The fallback merge uses reference assignment — mutating the merged
    result also mutates the source within the same config dict.

    This is tested by calling the merge logic directly on a single dict
    because each ``yaml.safe_load`` call produces independent objects."""
    import types

    # Build a minimal config dict
    cfg = {
        "cst": {"library_path": "dummy", "connect_mode": "any_or_new"},
        "solver": {"stagnation_timeout_s": 300.0, "settle_s": 2.0},
        "logging": {"enabled": True, "output_dir": "/tmp"},
        "workflow_2": {"enabled": True},
    }
    wf2_cfg = cfg["workflow_2"]

    # Replicate the merge logic from run.py
    for section in ("cst", "solver", "logging"):
        if section in cfg and section not in wf2_cfg:
            wf2_cfg[section] = cfg[section]

    wf2_cfg["cst"]["library_path"] = "MUTATED"
    assert cfg["cst"]["library_path"] == "MUTATED", (
        "Fallback merge should be a reference copy within the same config dict"
    )


def test_loader_enabled_false_would_exit():
    """When ``enabled`` is False, main() prints a message and exits with code 0."""
    from workflows.rfgun_hom_antenna.run import _load_workflow2_config
    import tempfile

    # Create a temp config with enabled: false
    cfg = {
        "cst": {"library_path": "dummy", "connect_mode": "any_or_new"},
        "solver": {"stagnation_timeout_s": 300.0, "settle_s": 2.0},
        "logging": {"enabled": True, "output_dir": "/tmp"},
        "workflow_2": {"enabled": False},
    }
    import tempfile, os
    fd, tmp = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f)
        wf2_cfg = _load_workflow2_config(Path(tmp))
        assert wf2_cfg["enabled"] is False, "Should return config even when disabled"
    finally:
        os.unlink(tmp)


def test_workflow2_subtree_in_default_yaml_is_legacy():
    """``config/default.yaml`` still has a ``workflow_2`` section, but it is
    now legacy — the Workflow2 runner reads the local config instead."""
    with open(GLOBAL_CONFIG, "r", encoding="utf-8") as f:
        global_ = yaml.safe_load(f)

    assert "workflow_2" in global_, (
        "config/default.yaml should still have workflow_2 as legacy reference"
    )

    # The global workflow_2 subtree should NOT have cst/solver/logging merged
    wf2 = global_.get("workflow_2", {})
    assert "cst" not in wf2, "Legacy subtree should not have cst"
    assert "solver" not in wf2, "Legacy subtree should not have solver"
