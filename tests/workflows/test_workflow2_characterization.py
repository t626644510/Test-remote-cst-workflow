"""W2-1: no-CST characterization tests for legacy workflow2 behavior.

These tests pin the current behavior of the workflow2 entry point, config
merge, builder, and scheduler WITHOUT CST-side live migration.  All CST
interactions are mocked — no CST Studio Suite required.

Coverage
--------
P0.1 — config fallback merge: how the Workflow2 runner merges top-level
       ``cst`` / ``solver`` / ``logging`` into the ``workflow_2`` section.

P0.2 — solver timeout source: what ``stagnation_timeout_s`` value actually
       reaches ``SolverRunner``.  W2-6F resolved: ``optimization.solver``
       now overrides fallback ``workflow_2.solver`` for overlapping keys.
       Effective Workflow2 timeout is 7200.0 from
       ``workflow_2.optimization.solver.stagnation_timeout_s``.

P0.3 — checkpoint callback call count: whether the evaluator wrapper fires
       ``checkpoint_callback`` exactly once per logical evaluation.
       W2-6E resolved: ``DualProjectOrchestrator`` no longer fires the
       callback; the evaluator owns it.

P1.4 — ``build_workflow_2`` return signature: confirm 4-tuple is returned.
       Historical type-annotation mismatch (promised 3 items, returned 4)
       was resolved in W2-4B when the workflow-local builder annotation and
       the factory wrapper annotation were both corrected.

P1.5 — root entry / scheduler compatibility: static text check that
       ``scripts/schedule_workflow2.ps1`` references ``run_workflow_2.py``.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
# Constants  (direct imports after path setup)
# ==============================================================================

_CONFIG_WITH_WF2: dict = {
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


# ==============================================================================
# White-box helper: replicates runner merge logic exactly
# ==============================================================================


def _run_merge_like_root(whole_config: dict) -> dict:
    """White-box characterisation of the Workflow2 runner config-merge logic.

    This replicates the EXACT current behaviour of
    ``workflows/rfgun_hom_antenna/run.py`` lines 117-120:

        wf2_cfg = cfg.get("workflow_2", {})
        ...
        for section in ("cst", "solver", "logging"):
            if section in cfg and section not in wf2_cfg:
                wf2_cfg[section] = cfg[section]

    Note: ``cfg.get("workflow_2", {})`` returns the **actual dict reference**
    (not a copy), and the assignment ``wf2_cfg[section] = cfg[section]`` is
    also a **reference copy** — mutating the merged result affects the source.
    This is the current runtime contract; the test does NOT aim for a safer
    design.
    """
    wf2_cfg = whole_config.get("workflow_2", {})
    for section in ("cst", "solver", "logging"):
        if section in whole_config and section not in wf2_cfg:
            wf2_cfg[section] = whole_config[section]
    return wf2_cfg


# ==============================================================================
# Helpers for P0.2 / P0.3 / P1.4
# ==============================================================================


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
    cfg: dict = {
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
    """Characterize how ``workflows/rfgun_hom_antenna/run.py`` merges top-level config into
    ``workflow_2`` when the workflow_2 section lacks ``cst`` / ``solver`` / ``logging``."""

    # ── White-box tests (via _run_merge_like_root) ───────────────────────

    @staticmethod
    def test_wb_workflow2_lacks_top_level_keys_so_they_are_merged():
        """White-box: when ``workflow_2`` has no ``cst``/``solver``/``logging``,
        the root runner copies the top-level versions by reference."""
        merged = _run_merge_like_root(_CONFIG_WITH_WF2)

        assert "solver" in merged
        assert merged["solver"]["stagnation_timeout_s"] == 300.0
        assert merged["solver"]["settle_s"] == 2.0

        assert "cst" in merged
        assert "library_path" in merged["cst"]

        assert "logging" in merged
        assert merged["logging"]["enabled"] is True

    @staticmethod
    def test_wb_workflow2_retains_its_own_keys():
        """White-box: keys that DO exist in ``workflow_2`` are not overwritten."""
        merged = _run_merge_like_root(_CONFIG_WITH_WF2)

        assert "enabled" in merged
        assert merged["enabled"] is True
        assert "projects" in merged
        assert "frequency_domain" in merged["projects"]

    @staticmethod
    def test_wb_merge_only_three_sections():
        """White-box: only ``cst``, ``solver``, ``logging`` are merged."""
        merged = _run_merge_like_root(_CONFIG_WITH_WF2)

        assert "project" not in merged
        assert "evaluation" not in merged

    @staticmethod
    def test_wb_merged_solver_is_reference_copy():
        """White-box: the merge is a reference assignment — mutating the
        merged result ALSO mutates the source.  This is the current runtime
        contract, not a safer design."""
        source = dict(_CONFIG_WITH_WF2)  # shallow copy of outer dict
        merged = _run_merge_like_root(source)
        merged["cst"]["library_path"] = "MUTATED"
        # Because ``wf2_cfg["cst"] = source["cst"]`` — same object
        assert source["cst"]["library_path"] == "MUTATED"

    @staticmethod
    def test_wb_merged_solver_overrides_optimization_solver():
        """White-box: after merge, ``workflow_2.solver`` is the top-level
        value (300.0), NOT the intent from ``optimization.solver`` (7200.0)."""
        merged = _run_merge_like_root(_CONFIG_WITH_WF2)

        assert merged["solver"]["stagnation_timeout_s"] == 300.0
        assert merged["solver"]["stagnation_timeout_s"] != 7200.0

    # ── Black-box test via run_workflow_2.main() ─────────────────────────

    _TEST_CONFIG = {
        "cst": {"library_path": "D:/dummy/path", "connect_mode": "any_or_new"},
        "solver": {"stagnation_timeout_s": 300.0, "settle_s": 2.0},
        "logging": {"enabled": True, "output_dir": "D:/dummy_log"},
        "project": {"cst_path": "D:/dummy/p.cst"},
        "workflow_2": {
            "enabled": True,
            "optimization": {
                "algorithm": "sao",
                "n_initial": 1,
                "n_iterations": 0,
                "seed": 42,
                "retry": {"enabled": False},
            },
            "parameters": [{"name": "p1", "low": 0.0, "high": 1.0, "enabled": True}],
            "objectives": [{"name": "resonant_freq", "mode": "minimize"}],
        },
    }

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.run.yaml.safe_load")
    @patch("workflows.rfgun_hom_antenna.run.CheckpointManager")
    @patch("workflows.rfgun_hom_antenna.run.os.makedirs")
    @patch("workflows.rfgun_hom_antenna.run.build_workflow_2")
    @patch("workflows.rfgun_hom_antenna.run.sys.argv", ["run_workflow_2.py"])
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    def test_root_main_merges_cst_solver_logging(
        mock_rm_lock,
        mock_rm_result,
        mock_kill_cst,
        mock_build_wf2,
        mock_makedirs,
        mock_ckpt_mgr,
        mock_yaml_load,
    ):
        """Call ``run_workflow_2.main()`` with all side-effects patched and
        capture the config dict that reaches ``build_workflow_2``.

        This is a black-box characterisation: we patch IO/CST dependencies
        but let the real ``main()`` config-merge logic run, then assert
        the merged result.
        """
        import run_workflow_2 as rw2

        mock_yaml_load.return_value = TestConfigFallbackMerge._TEST_CONFIG

        ckpt_instance = MagicMock()
        ckpt_instance.load.return_value = False
        ckpt_instance.completed_count = 0
        mock_ckpt_mgr.return_value = ckpt_instance

        # Capture the config dict passed to build_workflow_2
        captured_cfg: dict = {}

        def _fake_build(cfg, checkpoint_callback=None):
            captured_cfg.clear()
            captured_cfg.update(cfg)
            fake_orch = MagicMock()
            fake_orch.n_parameters = 1
            fake_orch.n_objectives = 1
            fake_orch.objectives = [MagicMock()]
            fake_orch.objectives[0].name = "resonant_freq"
            fake_orch.parameter_set = MagicMock()
            fake_orch.parameter_set.constraints = None
            fake_opt = MagicMock()
            fake_opt._n_initial = 1
            fake_opt._n_iterations = 0
            fake_eval = MagicMock(return_value=0.5)
            fake_retry = None
            return fake_orch, fake_opt, fake_eval, fake_retry

        mock_build_wf2.side_effect = _fake_build

        # The fake evaluator needs a warm_start attribute for the not-taken retry path
        rw2.main()

        # Assertions on the captured merged config
        assert "cst" in captured_cfg, "cst should have been merged into workflow_2 config"
        assert "solver" in captured_cfg, "solver should have been merged into workflow_2 config"
        assert "logging" in captured_cfg, "logging should have been merged into workflow_2 config"
        assert captured_cfg["solver"]["stagnation_timeout_s"] == 300.0, (
            f"solver timeout should be top-level fallback 300.0, got {captured_cfg['solver']['stagnation_timeout_s']}"
        )
        # workflow_2's own keys are preserved
        assert captured_cfg["enabled"] is True
        # Non-merged top-level keys are absent
        assert "project" not in captured_cfg


# ==============================================================================
# P0.2 — Solver timeout source
# ==============================================================================


class TestSolverTimeoutSource:
    """Characterize what ``stagnation_timeout_s`` value reaches ``SolverRunner``
    via ``build_workflow_2`` under the current config layout.

    Key question: does ``workflow_2.optimization.solver.stagnation_timeout_s``
    (the intent, 7200.0) actually flow through, or is it overridden by the
    top-level solver fallback (300.0) or the builder default (0.0 -> 7200.0)?
    """

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_solver_timeout_comes_from_merged_solver_section(MockCST):
        """With a config that has ``workflow_2.solver`` (post-merge), the
        ``SolverRunner`` receives that value."""
        cfg = _minimal_build_config()
        cfg["solver"]["stagnation_timeout_s"] = 300.0

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 300.0

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_solver_timeout_falls_back_to_default_when_missing(MockCST):
        """When ``workflow_2.solver`` has no ``stagnation_timeout_s`` (or is
        missing entirely), ``SolverRunner`` falls back to 7200.0."""
        cfg = _minimal_build_config()
        cfg.pop("solver", None)

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 7200.0

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_solver_timeout_zero_becomes_default(MockCST):
        """A value of 0 triggers the SolverRunner default (7200.0)."""
        cfg = _minimal_build_config()
        cfg["solver"]["stagnation_timeout_s"] = 0.0

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 7200.0

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_optimization_solver_now_consumed_by_builder(MockCST):
        """W2-6F: ``workflow_2.optimization.solver.stagnation_timeout_s`` is
        NOW consumed by ``build_workflow_2`` — it overrides the fallback
        solver for overlapping keys.  Previously (W2-6B) this path was
        ignored."""
        cfg = _minimal_build_config()
        cfg["optimization"]["solver"] = {"stagnation_timeout_s": 9999.0}
        cfg.pop("solver", None)

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 9999.0, (
            "optimization.solver.stagnation_timeout_s should now be consumed "
            "(W2-6F)."
        )

    # ── W2-6B: explicit mismatch characterisation tests ────────────────

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_actual_timeout_is_7200_via_real_config(MockCST):
        """Load the actual ``config/default.yaml``, apply runner merge
        semantics (as ``workflows/rfgun_hom_antenna/run.py`` does), and
        assert that ``SolverRunner`` now receives 7200.0 — the
        Workflow2-specific optimization solver value (W2-6F).
        Previously this received 300.0 (W2-6B behaviour, before the fix)."""
        cfg_path = _TEST_DIR.parent.parent / "config" / "default.yaml"
        assert cfg_path.exists(), f"config/default.yaml not found at {cfg_path}"

        with open(cfg_path, "r", encoding="utf-8") as f:
            whole = yaml.safe_load(f)

        # Replicate runner merge (workflows/rfgun_hom_antenna/run.py lines 117-120)
        wf2_cfg = whole.get("workflow_2", {})
        for section in ("cst", "solver", "logging"):
            if section in whole and section not in wf2_cfg:
                wf2_cfg[section] = whole[section]

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(wf2_cfg)
        assert orch._solver._timeout_s == 7200.0, (
            f"Expected effective timeout 7200.0 (Workflow2 optimization.solver), "
            f"got {orch._solver._timeout_s}.  "
            "The fix in W2-6F makes optimization.solver override the fallback."
        )

    @staticmethod
    def test_workflow2_timeout_intent_is_7200():
        """Assert that ``config/default.yaml`` contains
        ``workflow_2.optimization.solver.stagnation_timeout_s == 7200.0``,
        confirming the Workflow2-specific timeout intent at this path.
        W2-6F consumes this value via builder precedence."""
        cfg_path = _TEST_DIR.parent.parent / "config" / "default.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        wf2 = cfg.get("workflow_2", {})
        opt = wf2.get("optimization", {})
        solver_cfg = opt.get("solver", {})
        timeout = solver_cfg.get("stagnation_timeout_s", None)

        assert timeout == 7200.0, (
            f"Expected workflow_2.optimization.solver.stagnation_timeout_s "
            f"= 7200.0, got {timeout}.  "
            "This value is consumed by the builder (W2-6F: optimization.solver "
            "overrides fallback solver for overlapping keys)."
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_fallback_solver_used_when_optimization_solver_absent(MockCST):
        """When ``optimization.solver`` is absent, the builder falls back to
        ``workflow_2.solver`` (300.0)."""
        cfg = _minimal_build_config()
        cfg["optimization"].pop("solver", None)
        cfg["solver"] = {"stagnation_timeout_s": 300.0, "settle_s": 2.0}

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 300.0, (
            f"Expected 300.0 from fallback solver, got {orch._solver._timeout_s}"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_settle_s_falls_back_to_solver(MockCST):
        """``settle_s`` is not set in ``optimization.solver``, so it falls
        back to ``workflow_2.solver``."""
        cfg = _minimal_build_config()
        cfg["optimization"]["solver"] = {"stagnation_timeout_s": 7200.0}
        cfg["solver"] = {"stagnation_timeout_s": 300.0, "settle_s": 5.0}

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 7200.0, (
            f"Expected timeout 7200.0 from optimization.solver, "
            f"got {orch._solver._timeout_s}"
        )
        assert orch._solver._settle_s == 5.0, (
            f"Expected settle_s 5.0 from fallback solver, "
            f"got {orch._solver._settle_s}"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_optimization_solver_overrides_fallback(MockCST):
        """Set both ``workflow_2.solver`` (1111.0) and
        ``workflow_2.optimization.solver`` (2222.0).  W2-6F makes
        ``optimization.solver`` override the fallback, so ``SolverRunner``
        receives 2222.0."""
        cfg = _minimal_build_config()
        cfg["solver"] = {"stagnation_timeout_s": 1111.0, "settle_s": 2.0}
        cfg["optimization"]["solver"] = {"stagnation_timeout_s": 2222.0}

        from cst_optimization.factory import build_workflow_2

        orch, _, _, _ = build_workflow_2(cfg)
        assert orch._solver._timeout_s == 2222.0, (
            f"Expected 2222.0 from optimization.solver (W2-6F), "
            f"got {orch._solver._timeout_s}.  "
            "optimization.solver now overrides fallback solver for overlapping keys."
        )


# ==============================================================================
# P0.3 — Checkpoint callback call count  (hermetic, no _execute_phase_1)
# ==============================================================================


class TestCheckpointCallbackCount:
    """Characterize how many times ``checkpoint_callback`` fires per evaluator
    call.  Uses a monkeypatched ``orch.execute`` so no cleanup paths or
    real filesystem operations are touched."""

    @staticmethod
    def _make_fake_execute(orch):
        """Return a fake ``execute()`` that sets ``last_*`` properties and
        returns a zero-penalty array.  Does NOT fire checkpoint_callback
        (the orchestrator no longer owns the callback as of W2-6E).
        Does NOT call ``_execute_phase_1``, cleanup functions, or touch
        real paths."""

        def fake_execute(
            params: np.ndarray,
            iteration: int = 0,
            start_phase: str = "f2f",
            f2f_npz_path: str = "",
            skip_phases: set[str] | None = None,
        ) -> np.ndarray:
            n_obj = len(orch.objectives)
            raw = np.full(n_obj, 0.5)
            penalties = np.zeros(n_obj)

            # W2-6E: orchestrator no longer fires checkpoint_callback.
            # Only set last_* state for the evaluator wrapper to read.
            orch.last_raw_values = raw.copy()
            orch.last_penalties = penalties.copy()
            orch.last_solver_ok = True
            orch.last_completed_labels = set()
            return penalties

        return fake_execute

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    def test_non_retry_path_triggers_callback_one_time(
        mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """Non-retry path: the callback fires exactly once per evaluation
        (W2-6E: orchestrator callback removed)."""
        cfg = _minimal_build_config(enable_retry=False)
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        # Replace real execute with hermetic fake
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert callback.call_count == 1, (
            f"Expected 1 call (evaluator only, W2-6E), got {callback.call_count}"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    @patch("cst_optimization.core.cleanup.force_kill_cst")
    @patch("cst_optimization.core.cleanup.verify_process_cleanup")
    def test_retry_path_triggers_callback_one_time(
        mock_verify, mock_force_kill, mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """Retry path: the callback fires exactly once per evaluation
        (W2-6E: orchestrator callback removed)."""
        cfg = _minimal_build_config(enable_retry=True)
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, retry_handler = build_workflow_2(cfg, checkpoint_callback=callback)
        # Replace real execute with hermetic fake
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)
        # Also patch retry cleanup methods that Tier-3 escalation could call
        retry_handler._tier3_kill = MagicMock()
        retry_handler._reconnect = MagicMock()

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert callback.call_count == 1, (
            f"Expected 1 call on retry path (W2-6E), got {callback.call_count}"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    def test_both_paths_invoke_callback_with_arrays(
        mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """Verify the callback arguments are numpy arrays (not raw lists)."""
        cfg = _minimal_build_config(enable_retry=False)
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        evaluator(x)

        for call_args in callback.call_args_list:
            args = call_args[0]
            assert len(args) == 5, f"callback expected 5 args, got {len(args)}"
            _, raw_arr, pen_arr, solver_ok, err_str = args
            assert isinstance(raw_arr, np.ndarray), (
                f"raw_values should be ndarray, got {type(raw_arr)}"
            )
            assert isinstance(pen_arr, np.ndarray), (
                f"penalties should be ndarray, got {type(pen_arr)}"
            )
            assert isinstance(solver_ok, bool), (
                f"solver_ok should be bool, got {type(solver_ok)}"
            )
            assert isinstance(err_str, str), (
                f"error should be str, got {type(err_str)}"
            )

    # ── W2-6C: checkpoint callback side-effect characterisation ─────────

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    def test_non_retry_path_root_like_callback_creates_one_record(
        mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """A root-like callback that appends to a list receives ONE call and
        thus appends ONE record for one evaluation (W2-6E)."""
        records: list[dict] = []

        def root_like_callback(x_phys, raw, penalties, solver_ok, error):
            records.append({
                "x": x_phys.copy(),
                "raw": raw.copy(),
                "penalties": penalties.copy(),
                "solver_ok": solver_ok,
            })

        cfg = _minimal_build_config(enable_retry=False)
        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=root_like_callback)
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert len(records) == 1, (
            f"Expected 1 record (W2-6E: orchestrator callback removed), got {len(records)}."
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    @patch("cst_optimization.core.cleanup.force_kill_cst")
    @patch("cst_optimization.core.cleanup.verify_process_cleanup")
    def test_retry_path_root_like_callback_creates_one_record(
        mock_verify, mock_force_kill, mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """Retry path: a root-like callback receives ONE call and thus
        creates ONE record per logical evaluation (W2-6E)."""
        records: list[dict] = []

        def root_like_callback(x_phys, raw, penalties, solver_ok, error):
            records.append({
                "x": x_phys.copy(),
                "solver_ok": solver_ok,
            })

        cfg = _minimal_build_config(enable_retry=True)
        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, retry_handler = build_workflow_2(
            cfg, checkpoint_callback=root_like_callback,
        )
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)
        retry_handler._tier3_kill = MagicMock()
        retry_handler._reconnect = MagicMock()

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert len(records) == 1, (
            f"Expected 1 record on retry path (W2-6E), got {len(records)}."
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    def test_same_x_vector_one_call(
        mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """The single W2-6E callback invocation receives the expected
        ``x_phys`` vector for one logical evaluation."""
        captured_x: list[np.ndarray] = []

        def record_x(x_phys, raw, penalties, solver_ok, error):
            captured_x.append(x_phys.copy())

        cfg = _minimal_build_config(enable_retry=False)
        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=record_x)
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert len(captured_x) == 1, (
            f"Expected 1 call (W2-6E), got {len(captured_x)}"
        )
        assert np.array_equal(captured_x[0], x), (
            "The single callback call should receive the same x_phys vector."
        )

    # ── W2-6E: SAEA evaluator callback test ────────────────────────────

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_saea_evaluator_fires_callback_once(MockCST):
        """SAEA algorithm path: evaluator wrapper fires checkpoint_callback
        exactly once per call."""
        cfg = _minimal_build_config()
        cfg["optimization"]["algorithm"] = "saea"
        cfg["optimization"]["pop_size"] = 10
        cfg["optimization"]["n_gen_per_iteration"] = 2
        cfg["optimization"]["n_candidates_per_iteration"] = 2
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        try:
            evaluator(x)
        except Exception:
            pass

        assert callback.call_count == 1, (
            f"Expected 1 callback call on SAEA path (W2-6E), got {callback.call_count}"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_saea_evaluator_receives_arrays(MockCST):
        """SAEA evaluator callback receives numpy arrays, not raw lists."""
        cfg = _minimal_build_config()
        cfg["optimization"]["algorithm"] = "saea"
        cfg["optimization"]["pop_size"] = 10
        cfg["optimization"]["n_gen_per_iteration"] = 2
        cfg["optimization"]["n_candidates_per_iteration"] = 2
        callback = MagicMock()

        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        try:
            evaluator(x)
        except Exception:
            pass

        for call_args in callback.call_args_list:
            args = call_args[0]
            assert len(args) == 5, f"Expected 5 args, got {len(args)}"
            _, raw_arr, pen_arr, solver_ok, err_str = args
            assert isinstance(raw_arr, np.ndarray)
            assert isinstance(pen_arr, np.ndarray)
            assert isinstance(solver_ok, bool)
            assert isinstance(err_str, str)

    # ── W2-6E: partial / non-finite raw regression test ──────────────

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    @patch("cst_optimization.core.cleanup.kill_all_cst_processes")
    @patch("cst_optimization.core.cleanup.remove_result_folder")
    @patch("cst_optimization.core.cleanup.remove_lock_file")
    def test_partial_raw_nan_still_fires_callback_once(
        mock_rm_lock, mock_rm_result, mock_kill_cst, MockCST
    ):
        """When raw contains NaN (partial evaluation), the evaluator wrapper
        still fires checkpoint_callback exactly once."""
        records: list[dict] = []

        def root_like_callback(x_phys, raw, penalties, solver_ok, error):
            records.append({"raw": raw.copy()})

        cfg = _minimal_build_config(enable_retry=False)
        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=root_like_callback)
        orig_fake = TestCheckpointCallbackCount._make_fake_execute(orch)

        def _nan_execute(*a, **kw):
            result = orig_fake(*a, **kw)
            orch.last_raw_values = np.full(len(orch.objectives), np.nan)
            return result

        orch.execute = _nan_execute

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert len(records) == 1, (
            f"Expected 1 callback call with NaN raw, got {len(records)}"
        )
        assert all(np.isnan(v) for v in records[0]["raw"]), (
            "Callback should receive NaN raw values unchanged"
        )

    # ── W2-6E fix: SAO non-retry failure semantics ────────────────────

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_non_retry_failure_passes_solver_ok_false(MockCST):
        """SAO non-retry path: when orchestrator reports failure, the
        evaluator callback receives solver_ok=False and a non-empty error
        string."""
        callback = MagicMock()
        cfg = _minimal_build_config(enable_retry=False)
        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        fake = TestCheckpointCallbackCount._make_fake_execute(orch)

        def _fail_execute(*a, **kw):
            fake(*a, **kw)
            orch.last_raw_values = np.array([np.nan])
            orch.last_penalties = np.array([1.0])
            orch.last_solver_ok = False
            orch.last_completed_labels = set()
            return orch.last_penalties

        orch.execute = _fail_execute

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert callback.call_count == 1, (
            f"Expected 1 callback call, got {callback.call_count}"
        )
        args = callback.call_args[0]
        _, raw_arr, pen_arr, solver_ok, err_str = args
        assert solver_ok is False, "solver_ok should be False on failure"
        assert isinstance(err_str, str) and len(err_str) > 0, (
            "error string should be non-empty on failure"
        )
        assert np.isnan(raw_arr[0]), "NaN raw should pass through"
        assert pen_arr[0] == 1.0, "penalties should pass through"

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_non_retry_success_passes_solver_ok_true(MockCST):
        """SAO non-retry path: on success, the evaluator callback receives
        solver_ok=True and an empty error string."""
        callback = MagicMock()
        cfg = _minimal_build_config(enable_retry=False)
        from cst_optimization.factory import build_workflow_2

        orch, _, evaluator, _ = build_workflow_2(cfg, checkpoint_callback=callback)
        orch.execute = TestCheckpointCallbackCount._make_fake_execute(orch)

        x = np.array([0.5], dtype=float)
        evaluator(x)

        assert callback.call_count == 1, (
            f"Expected 1 callback call, got {callback.call_count}"
        )
        args = callback.call_args[0]
        _, _, _, solver_ok, err_str = args
        assert solver_ok is True, "solver_ok should be True on success"
        assert err_str == "", "error string should be empty on success"


# ==============================================================================
# P1.4 — build_workflow_2 return signature
# ==============================================================================


class TestBuildWorkflow2ReturnSignature:
    """Characterize the actual return signature of ``build_workflow_2``.

    Historical W2-1 finding (R3): the shared factory annotation and docstring
    promised 3 items (``DualProjectOrchestrator, BaseOptimizer, Callable``)
    while the implementation returned 4 (adding ``retry_handler``).

    This was resolved in W2-4B:
    - ``workflows.rfgun_hom_antenna.workflow.build_workflow_2`` (current owner)
      now has a correct 4-element annotation and docstring.
    - ``cst_optimization.factory.build_workflow_2`` (compatibility wrapper)
      also has a correct 4-element annotation.

    The runtime 4-tuple return remains pinned by the tests below.
    """

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_returns_four_tuple_with_sao_algorithm(MockCST):
        """Default SAO algorithm returns a 4-tuple."""
        cfg = _minimal_build_config()
        from cst_optimization.factory import build_workflow_2

        result = build_workflow_2(cfg)
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 4, f"Expected 4 values, got {len(result)}"

        orch, opt, evaluator, retry_handler = result
        assert hasattr(orch, "execute"), "orchestrator should have execute()"
        assert hasattr(orch, "n_parameters"), "orchestrator should have n_parameters"
        assert hasattr(opt, "optimize"), "optimizer should have optimize()"
        assert callable(evaluator), "evaluator should be callable"
        assert retry_handler is None, (
            f"Expected retry_handler=None when retry disabled, got {type(retry_handler)}"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_returns_four_tuple_with_retry_enabled(MockCST):
        """With retry enabled, retry_handler is not None."""
        cfg = _minimal_build_config(enable_retry=True)
        from cst_optimization.factory import build_workflow_2

        result = build_workflow_2(cfg)
        assert len(result) == 4
        _, _, _, retry_handler = result
        assert retry_handler is not None, (
            "retry_handler should not be None when retry enabled"
        )

    @staticmethod
    @patch("workflows.rfgun_hom_antenna.workflow.CSTConnection")
    def test_saea_algorithm_also_returns_four_tuple(MockCST):
        """SAEA algorithm also returns a 4-tuple."""
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
    def test_type_annotation_now_matches_four_tuple():
        """Assert the workflow-local builder annotation now documents all 4
        return components (``DualProjectOrchestrator``, ``BaseOptimizer``,
        ``Callable``, ``EvaluationRetryHandler``).

        R3 is resolved: the owner module's type annotation and docstring
        both match the actual 4-tuple return.  The historical mismatch
        (W2-1) existed when the implementation lived in the shared factory
        with a 3-tuple annotation.
        """
        import inspect
        from workflows.rfgun_hom_antenna.workflow import build_workflow_2

        sig = inspect.signature(build_workflow_2)
        ann_str = str(sig.return_annotation)

        assert "EvaluationRetryHandler" in ann_str, (
            "R3 should be resolved: workflow-local builder annotation "
            "should now include EvaluationRetryHandler."
        )
        # All four return types are documented
        assert "DualProjectOrchestrator" in ann_str
        assert "BaseOptimizer" in ann_str
        assert "Callable" in ann_str


# ==============================================================================
# P1.5 — Root entry / scheduler compatibility
# ==============================================================================


class TestSchedulerRootEntryCompatibility:
    """Characterize that ``scripts/schedule_workflow2.ps1`` still references
    the root ``run_workflow_2.py`` — runner body migrated (W2-7), scheduler unchanged."""

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
        """Scheduler still references the ROOT ``run_workflow_2.py``, not a
        workflow2-specific entry point."""
        content = TestSchedulerRootEntryCompatibility.SCHEDULER_PATH.read_text(
            encoding="utf-8"
        )
        indicators = [
            "workflows/rfgun_hom_antenna",
            "workflow2/run.py",
            "wf2_entry",
        ]
        for ind in indicators:
            assert ind not in content, (
                f"Scheduler appears to reference migrated path '{ind}'"
            )
