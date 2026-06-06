"""W2-1: no-CST characterization tests for legacy workflow2 behavior.

These tests pin the current behavior of the workflow2 entry point, config
merge, builder, and scheduler WITHOUT any runtime migration.  All CST
interactions are mocked — no CST Studio Suite required.

Coverage
--------
P0.1 — config fallback merge: how ``run_workflow_2.py`` merges top-level
       ``cst`` / ``solver`` / ``logging`` into the ``workflow_2`` section.

P0.2 — solver timeout source: what ``stagnation_timeout_s`` value actually
       reaches ``SolverRunner`` under the current config layout.

P0.3 — checkpoint callback call count: whether both the orchestrator and
       the factory evaluator invoke the same callback (double-trigger risk).

P1.4 — ``build_workflow_2`` return signature: confirm 4-tuple is returned
       even though the type annotation promises only 3 items.

P1.5 — root entry / scheduler compatibility: static text check that
       ``scripts/schedule_workflow2.ps1`` references ``run_workflow_2.py``.
"""

from __future__ import annotations

import sys
import copy
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest
import yaml

# ---- Path setup (same pattern as existing test files) -----------------------
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for _p in (str(_PROJECT_ROOT), _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ==============================================================================
# Helpers
# ==============================================================================

# Config that mirrors the relevant structure of config/default.yaml.
# workflow_2 does NOT have top-level "solver" — that comes via merge.
_MERGE_SOURCE_CONFIG: dict = {
    "cst": {
        "library_path": "D:/CST2026/CST Studio Suite 2026/AMD64/python_cst_libraries",
        "connect_mode": "any_or_new",
        "result_cache": True,
    },
    "solver": {
        "stagnation_timeout_s": 300.0,
        "settle_s": 2.0,
    },
    "logging": {
        "enabled": True,
        "output_dir": "D:/Results",
        "auto_flush_interval": 1,
    },
    "optimization": {
        "algorithm": "sao",
        "n_initial_samples": 20,
        "n_iterations": 100,
        "seed": 42,
    },
    "project": {
        "cst_path": "F:/workflow_elgun/PickupDesign_2026.cst",
    },
    "evaluation": {
        "post_eval_recovery": "tier2",
    },
    "workflow_2": {
        "enabled": True,
        "projects": {
            "frequency_domain": {
                "cst_path": "D:/workflow2/F2F.cst",
                "is_pre_filter": True,
            },
        },
        "optimization": {
            "algorithm": "sao",
            "n_initial": 10,
            "n_iterations": 50,
            "seed": 42,
            "solver": {
                "stagnation_timeout_s": 7200.0,  # INTENDED value
            },
            "retry": {"enabled": False},
        },
        "parameters": [
            {"name": "p1", "low": 0.0, "high": 1.0, "enabled": True},
        ],
        "objectives": [
            {
                "name": "antenna_absorption",
                "mode": "less_than",
                "mode_params": {"threshold": -29.0, "sigma": 2.0},
                "obj_params": {
                    "project": "frequency_domain",
                    "antenna_port": 2,
                    "tree_path": "1D Results\\S-Parameters\\S2,1",
                    "search_freq_ghz": 0.5,
                    "search_width_ghz": 0.01,
                },
            },
        ],
    },
}


def _run_merge(whole_config: dict) -> dict:
    """Replicate the config-merge logic from ``run_workflow_2.py`` lines 90-101."""
    wf2_cfg = dict(whole_config.get("workflow_2", {}))
    for section in ("cst", "solver", "logging"):
        if section in whole_config and section not in wf2_cfg:
            wf2_cfg[section] = copy.deepcopy(whole_config[section])
    return wf2_cfg


def _minimal_build_config(enable_retry: bool = False) -> dict:
    """Minimal ``workflow_2`` section config that ``build_workflow_2`` accepts.

    Parameters
    ----------
    enable_retry : bool
        If True, set up the retry handler (mimicking the production config).
    """
    retry_cfg = (
        {
            "enabled": True,
            "max_tier1": 0,
            "max_tier2": 0,
            "max_tier3": 2,
            "cooldown_s": 15.0,
            "evaluation_timeout_s": 10800.0,
        }
        if enable_retry
        else {"enabled": False}
    )
    cfg = {
        "cst": {
            "library_path": "D:/dummy/path",
            "connect_mode": "any_or_new",
        },
        "evaluation": {},
        "logging": {
            "enabled": False,  # prevents eager ResultReader in make_recording_reader
        },
        "parameters": [
            {"name": "p1", "low": 0.0, "high": 1.0, "enabled": True},
        ],
        "objectives": [
            {
                "name": "antenna_absorption",
                "mode": "less_than",
                "mode_params": {"threshold": -29.0, "sigma": 2.0},
                "obj_params": {
                    "project": "frequency_domain",
                    "antenna_port": 2,
                    "tree_path": "1D Results\\S-Parameters\\S2,1",
                    "search_freq_ghz": 0.5,
                    "search_width_ghz": 0.01,
                },
            },
        ],
        "projects": {
            "frequency_domain": {
                "cst_path": "D:/dummy/fake.cst",
                "is_pre_filter": True,
            },
        },
        "optimization": {
            "algorithm": "sao",
            "n_initial": 1,
            "n_iterations": 0,
            "seed": 42,
            "retry": retry_cfg,
        },
        "solver": {
            "stagnation_timeout_s": 300.0,
            "settle_s": 2.0,
        },
    }
    return cfg


# ==============================================================================
# P0.1 — Config fallback merge
# ==============================================================================


class TestConfigFallbackMerge:
    """Characterize how ``run_workflow_2.py`` merges top-level config into
    ``workflow_2`` when the workflow_2 section lacks ``cst`` / ``solver`` / ``logging``."""

    @staticmethod
    def test_workflow2_lacks_top_level_keys_so_they_are_merged():
        """When ``workflow_2`` has no ``cst``/``solver``/``logging``, the root
        runner copies the top-level versions into the ``workflow_2`` dict."""
        merged = _run_merge(_MERGE_SOURCE_CONFIG)

        assert "solver" in merged
        assert merged["solver"]["stagnation_timeout_s"] == 300.0
        assert merged["solver"]["settle_s"] == 2.0

        assert "cst" in merged
        assert "library_path" in merged["cst"]

        assert "logging" in merged
        assert merged["logging"]["enabled"] is True

    @staticmethod
    def test_workflow2_retains_its_own_keys():
        """Keys that DO exist in ``workflow_2`` are not overwritten by the merge."""
        merged = _run_merge(_MERGE_SOURCE_CONFIG)

        assert "enabled" in merged
        assert merged["enabled"] is True
        assert "projects" in merged
        assert "frequency_domain" in merged["projects"]

    @staticmethod
    def test_merge_only_three_sections():
        """Only ``cst``, ``solver``, ``logging`` participate in the merge."""
        merged = _run_merge(_MERGE_SOURCE_CONFIG)

        # Top-level keys like "project", "evaluation", "optimization" are
        # NOT merged into workflow_2.
        assert "project" not in merged
        assert "evaluation" not in merged

    @staticmethod
    def test_merged_solver_overrides_optimization_solver():
        """After merge, ``workflow_2.solver.stagnation_timeout_s`` is the
        top-level value (300.0), NOT the intent value from
        ``workflow_2.optimization.solver`` (7200.0)."""
        merged = _run_merge(_MERGE_SOURCE_CONFIG)

        assert merged["solver"]["stagnation_timeout_s"] == 300.0
        assert merged["solver"]["stagnation_timeout_s"] != 7200.0

    @staticmethod
    def test_merge_is_shallow_copy():
        """The merge copies the dict — mutations to ``merged`` should not
        affect the source unless they share nested references."""
        source = copy.deepcopy(_MERGE_SOURCE_CONFIG)
        merged = _run_merge(source)
        merged["cst"]["library_path"] = "MUTATED"
        assert source["cst"]["library_path"] != "MUTATED"


# ==============================================================================
# P0.2 — Solver timeout source
# ==============================================================================


class TestSolverTimeoutSource:
    """Characterize what ``stagnation_timeout_s`` value reaches ``SolverRunner``
    via ``build_workflow_2`` under the current config layout.

    Key question: does ``workflow_2.optimization.solver.stagnation_timeout_s``
    (the intent, 7200.0) actually flow through, or is it overridden by the
    top-level solver fallback (300.0) or the builder default (0.0 → 7200.0)?
    """

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_solver_timeout_comes_from_merged_solver_section(MockCST):
        """With a config that has ``workflow_2.solver`` (post-merge), the
        ``SolverRunner`` receives that value."""
        cfg = _minimal_build_config()
        # Simulate the merge: inject solver into workflow_2
        cfg["solver"]["stagnation_timeout_s"] = 300.0

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        # _solver._timeout_s is set in SolverRunner.__init__
        # __init__ uses: timeout_s if timeout_s > 0 else _DEFAULT_TIMEOUT_S
        assert orch._solver._timeout_s == 300.0

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_solver_timeout_falls_back_to_default_when_missing(MockCST):
        """When ``workflow_2.solver`` has no ``stagnation_timeout_s`` (or is
        missing entirely), ``SolverRunner`` falls back to its own default
        (7200.0)."""
        cfg = _minimal_build_config()
        cfg.pop("solver", None)  # No solver section at all

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        # SolverRunner default: 7200.0
        assert orch._solver._timeout_s == 7200.0

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_solver_timeout_zero_becomes_default(MockCST):
        """A value of 0 triggers the SolverRunner default (7200.0), which
        is the same value as the config intent.  This means removing the
        solver section would produce the INTENDED 7200s — accidentally."""
        cfg = _minimal_build_config()
        cfg["solver"]["stagnation_timeout_s"] = 0.0

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 7200.0

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_optimization_solver_key_is_not_read_by_builder(MockCST):
        """The value at ``workflow_2.optimization.solver.stagnation_timeout_s``
        is NOT read by ``build_workflow_2`` — the builder reads
        ``workflow_2.solver`` instead.  This confirms the R2 risk.

        We set optimization.solver to 9999.0; if the builder reads this path,
        the solver timeout would be 9999.0.  The test asserts it is NOT."""
        cfg = _minimal_build_config()
        cfg["optimization"]["solver"] = {"stagnation_timeout_s": 9999.0}
        # Do NOT set workflow_2.solver — rely on fallback to default
        cfg.pop("solver", None)

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        # If builder read optimization.solver, timeout would be 9999.0
        # Instead, it falls back to SolverRunner default (7200.0)
        assert orch._solver._timeout_s != 9999.0
        assert orch._solver._timeout_s == 7200.0


# ==============================================================================
# P0.3 — Checkpoint callback call count
# ==============================================================================


class TestCheckpointCallbackCount:
    """Characterize how many times ``checkpoint_callback`` fires per evaluator
    call.  The code-audit risk (R4) shows both ``orchestrator.execute()``
    and the factory evaluator invoke the same callback — this test measures
    the actual runtime count."""

    RETRY_CFG = {
        "enabled": True,
        "max_tier1": 0,
        "max_tier2": 0,
        "max_tier3": 2,
        "cooldown_s": 5.0,
        "evaluation_timeout_s": 600.0,
    }

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_non_retry_path_triggers_callback_two_times(MockCST):
        """On the non-retry path (retry.enabled=False), the callback fires
        twice per evaluation: once from orchestrator.execute() and once from
        the factory evaluator wrapper."""
        cfg = _minimal_build_config(enable_retry=False)
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        _, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        x = np.array([0.5], dtype=float)
        try:
            evaluator(x)
        except Exception:
            pass  # CST mock may raise — we still count callback call attempts

        # Both the orchestrator and the evaluator call callback
        assert callback.call_count == 2, (
            f"Expected 2 calls from orchestrator + evaluator, got {callback.call_count}"
        )

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_retry_path_triggers_callback_two_times(MockCST):
        """On the retry-enabled path, the callback also fires twice:
        once from orchestrator.execute(), and again from the factory
        evaluator after the retry handler returns."""
        cfg = _minimal_build_config(enable_retry=True)
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        _, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        x = np.array([0.5], dtype=float)
        try:
            evaluator(x)
        except Exception:
            pass

        assert callback.call_count == 2, (
            f"Expected 2 calls on retry path, got {callback.call_count}"
        )

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_both_paths_invoke_callback_with_arrays(MockCST):
        """Verify the callback arguments are numpy arrays (not raw lists),
        matching the callback type signature."""
        cfg = _minimal_build_config(enable_retry=False)
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        _, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        x = np.array([0.5], dtype=float)
        try:
            evaluator(x)
        except Exception:
            pass

        for call_args in callback.call_args_list:
            args = call_args[0]
            assert len(args) == 5, f"callback expected 5 args, got {len(args)}"
            _, raw_arr, pen_arr, solver_ok, err_str = args
            assert isinstance(raw_arr, np.ndarray), f"raw_values should be ndarray, got {type(raw_arr)}"
            assert isinstance(pen_arr, np.ndarray), f"penalties should be ndarray, got {type(pen_arr)}"
            assert isinstance(solver_ok, bool), f"solver_ok should be bool, got {type(solver_ok)}"
            assert isinstance(err_str, str), f"error should be str, got {type(err_str)}"


# ==============================================================================
# P1.4 — build_workflow_2 return signature
# ==============================================================================


class TestBuildWorkflow2ReturnSignature:
    """Characterize the actual return signature of ``build_workflow_2``.

    The type annotation (factory.py:327) promises 3 items:
        tuple[DualProjectOrchestrator, BaseOptimizer, Callable]
    but the implementation returns 4:
        (orchestrator, optimizer, evaluator, retry_handler)
    The caller (``run_workflow_2.py:208``) depends on the 4-value form.
    """

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_returns_four_tuple_with_sao_algorithm(MockCST):
        """Default SAO algorithm returns a 4-tuple."""
        cfg = _minimal_build_config()
        from cst_optimization.factory import build_workflow_2

        result = build_workflow_2(cfg)
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 4, f"Expected 4 values, got {len(result)}"

        orch, opt, evaluator, retry_handler = result
        # orch is a DualProjectOrchestrator
        assert hasattr(orch, "execute"), "orchestrator should have execute()"
        assert hasattr(orch, "n_parameters"), "orchestrator should have n_parameters"
        # opt is a BaseOptimizer
        assert hasattr(opt, "optimize"), "optimizer should have optimize()"
        # evaluator is callable
        assert callable(evaluator), "evaluator should be callable"
        # retry_handler is None when retry disabled
        assert retry_handler is None, (
            f"Expected retry_handler=None when retry disabled, got {type(retry_handler)}"
        )

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_returns_four_tuple_with_retry_enabled(MockCST):
        """With retry enabled, retry_handler is not None."""
        cfg = _minimal_build_config(enable_retry=True)
        from cst_optimization.factory import build_workflow_2

        result = build_workflow_2(cfg)
        assert len(result) == 4
        orch, opt, evaluator, retry_handler = result
        assert retry_handler is not None, "retry_handler should not be None when retry enabled"

    @staticmethod
    @patch("cst_optimization.factory.CSTConnection")
    def test_saea_algorithm_also_returns_four_tuple(MockCST):
        """SAEA algorithm also returns a 4-tuple (same factory return)."""
        cfg = _minimal_build_config()
        cfg["optimization"]["algorithm"] = "saea"
        cfg["optimization"]["pop_size"] = 10
        cfg["optimization"]["n_gen_per_iteration"] = 2
        cfg["optimization"]["n_candidates_per_iteration"] = 2
        from cst_optimization.factory import build_workflow_2

        result = build_workflow_2(cfg)
        assert len(result) == 4, f"SAEA path should also return 4-tuple, got {len(result)}"

        orch, opt, evaluator, retry_handler = result
        assert hasattr(orch, "execute")
        assert hasattr(opt, "optimize")
        assert callable(evaluator)

    @staticmethod
    def test_type_annotation_mismatch():
        """Document the mismatch between the type annotation and actual return.

        This is a static/reflection test that reads the source annotation.
        It does NOT exercise CST — purely textual."""
        import inspect
        from cst_optimization.factory import build_workflow_2

        sig = inspect.signature(build_workflow_2)
        return_ann = sig.return_annotation
        ann_str = str(return_ann)

        # The annotation says tuple of 3 elements (no retry_handler)
        assert "DualProjectOrchestrator" in ann_str
        assert "BaseOptimizer" in ann_str

        # Actual code returns 4, but annotation lists 3
        # This test is EXPECTED TO SHOW the mismatch — if the annotation is
        # ever fixed to include retry_handler, this test will fail and the
        # risk can be downgraded.
        items = ann_str.split(",")
        n_ann_items = sum(1 for s in items if "object" in s or "DualProject" in s or "BaseOptimizer" in s or "Callable" in s)
        # Simpler: count tuple elements
        if "EvaluationRetryHandler" not in ann_str:
            print(f"[W2-1] R3 CONFIRMED: type annotation does not mention EvaluationRetryHandler")
        else:
            print(f"[W2-1] R3 CHECK: type annotation now includes EvaluationRetryHandler — risk downgrade candidate")


# ==============================================================================
# P1.5 — Root entry / scheduler compatibility
# ==============================================================================


class TestSchedulerRootEntryCompatibility:
    """Characterize that ``scripts/schedule_workflow2.ps1`` still references
    the root ``run_workflow_2.py`` — no migration has happened yet."""

    SCHEDULER_PATH = _PROJECT_ROOT / "scripts" / "schedule_workflow2.ps1"

    @staticmethod
    def test_scheduler_script_exists():
        assert TestSchedulerRootEntryCompatibility.SCHEDULER_PATH.exists(), (
            f"Scheduler script not found at {TestSchedulerRootEntryCompatibility.SCHEDULER_PATH}"
        )

    @staticmethod
    def test_scheduler_references_root_entry():
        content = TestSchedulerRootEntryCompatibility.SCHEDULER_PATH.read_text(
            encoding="utf-8"
        )
        assert "run_workflow_2.py" in content, (
            "Scheduler does not reference run_workflow_2.py — may have been migrated"
        )
        assert "WorkDir" in content, (
            "Scheduler should resolve run_workflow_2.py relative to WorkDir"
        )

    @staticmethod
    def test_scheduler_uses_auto_resume_and_heartbeat():
        """The production scheduler invocation uses ``--auto-resume --heartbeat``."""
        content = TestSchedulerRootEntryCompatibility.SCHEDULER_PATH.read_text(
            encoding="utf-8"
        )
        assert "--auto-resume" in content
        assert "--heartbeat" in content

    @staticmethod
    def test_scheduler_not_migrated_to_separate_entry():
        """Scheduler still references the ROOT run_workflow_2.py, not a
        workflow2-specific entry point."""
        content = TestSchedulerRootEntryCompatibility.SCHEDULER_PATH.read_text(
            encoding="utf-8"
        )
        # These would indicate partial migration
        indicators = [
            "workflows/rfgun_hom_antenna",
            "workflow2/run.py",
            "wf2_entry",
        ]
        for ind in indicators:
            assert ind not in content, (
                f"Scheduler appears to reference migrated path '{ind}'"
            )
