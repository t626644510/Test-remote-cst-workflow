"""W2-3: config isolation tests for ``workflows/rfgun_hom_antenna/config.yaml``.

These tests verify that the workflow-local configuration file exists,
is parseable, and matches the raw ``workflow_2`` subtree from the
global ``config/default.yaml``.  They do NOT require CST, the builder,
the orchestrator, or any optimiser.

Key design decision
-------------------
This is a **raw ``workflow_2`` subtree snapshot** — it exactly matches
``config/default.yaml["workflow_2"]`` without any top-level fallback keys
(``cst``, ``solver``, ``logging``) merged in.  The root runner's fallback
merge is a legacy runtime behaviour that will be resolved at migration time.
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
# B. Content equality with global default.yaml
# ==============================================================================


def test_local_config_matches_global_workflow2_subtree():
    """The local ``workflow_2`` subtree matches ``config/default.yaml["workflow_2"]``
    exactly.  This is a raw subtree snapshot — no fallback keys merged in."""
    assert GLOBAL_CONFIG.exists(), f"Global config not found at {GLOBAL_CONFIG}"

    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        local = yaml.safe_load(f)
    with open(GLOBAL_CONFIG, "r", encoding="utf-8") as f:
        global_ = yaml.safe_load(f)

    local_wf2 = local.get("workflow_2", {})
    global_wf2 = global_.get("workflow_2", {})

    assert local_wf2 == global_wf2, (
        "Local workflow_2 subtree does NOT match the global default.yaml[workflow_2].\n"
        "If you intentionally diverged, document the reason in the test and in "
        "the config.yaml header comment."
    )


# ==============================================================================
# C. Known W2-1 findings preserved in snapshot
# ==============================================================================


def test_local_config_preserves_solver_timeout_intent():
    """The ``optimization.solver.stagnation_timeout_s`` value (7200.0) is
    preserved in the local config as the configuration intent.

    NOTE: This is the intent value stored in
    ``workflow_2.optimization.solver.stagnation_timeout_s``.  As confirmed
    by W2-1 characterization tests, the current builder reads solver config
    from ``workflow_2.solver`` (post-merge fallback), NOT from
    ``workflow_2.optimization.solver``.  The runtime discrepancy between
    intent (7200.0) and actual (300.0) must be resolved at migration time,
    not during config staging.
    """
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    wf2 = cfg.get("workflow_2", {})
    opt = wf2.get("optimization", {})
    solver = opt.get("solver", {})
    timeout = solver.get("stagnation_timeout_s", None)

    assert timeout == 7200.0, (
        f"Expected solver timeout intent 7200.0, got {timeout}. "
        "This value should match config/default.yaml exactly at snapshot time."
    )


def test_local_config_is_raw_subtree_not_merged():
    """The local config does NOT contain top-level fallback keys (``cst``,
    ``solver``, ``logging``) that the root runner merges at runtime.

    This confirms it is a raw ``workflow_2`` subtree snapshot, NOT a
    merged runtime snapshot.
    """
    with open(LOCAL_CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    wf2 = cfg.get("workflow_2", {})
    # The raw workflow_2 from default.yaml does not have these keys
    assert "cst" not in wf2, (
        "Local config should NOT contain top-level 'cst' — "
        "that comes from root-runner fallback merge at runtime"
    )
    assert "solver" not in wf2, (
        "Local config should NOT contain top-level 'solver' — "
        "that comes from root-runner fallback merge at runtime. "
        "The only solver key belongs under optimization.solver."
    )
    assert "logging" not in wf2, (
        "Local config should NOT contain top-level 'logging' — "
        "that comes from root-runner fallback merge at runtime"
    )
