"""Shared runner base class for workflow CLI entry points.

Provides common patterns used by all three workflows:
- ``sys.path`` setup (project root + ``src/``)
- CheckpointManager creation and ``_on_evaluation`` callback closure
- Double-tap Ctrl+C signal handling
- Logging configuration
- YAML config loading
- ``_wf_ref`` mutable-list pattern for late-binding closure capture

Subclasses implement ``build_workflow()`` and optionally override
``add_args()``, ``cleanup()``, and ``load_prior_data()``.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml

from cst_optimization.checkpoint import CheckpointManager

_logger = logging.getLogger(__name__)


# ── Shared path setup (run at module level, idempotent) ─────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class BaseRunner:
    """Shared CLI runner for CST optimisation workflows.

    Parameters
    ----------
    wf_name : str
        Short name used for log files and checkpoint paths (e.g. "workflow_1").
    default_config : str
        Path to the default YAML config file (relative to project root).
    """

    wf_name: str
    default_config: str

    def __init__(self, wf_name: str, default_config: str = "") -> None:
        self.wf_name = wf_name
        self.default_config = default_config
        self.cfg: dict[str, Any] = {}
        self.ckpt: CheckpointManager | None = None
        self.log_dir: str = "runs"
        self._wf_ref: list = []          # mutable capture for closure late-binding
        self._interrupt_count: list[int] = [0]

    # ------------------------------------------------------------------
    # Template method — override in subclasses with custom flow
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Canonical run sequence.  Subclasses may override entirely."""
        self.parse_args()
        self.load_config()
        self.setup_logging()
        self.setup_checkpoint()
        self.install_signal_handler()
        workflow, opt, evaluator = self.build_workflow()
        self._wf_ref.append(workflow)
        self._run_optimize(opt, evaluator)

    # ------------------------------------------------------------------
    # CLI
    # ------------------------------------------------------------------

    def parse_args(self) -> argparse.Namespace:
        """Build argument parser and parse.  Subclasses extend via ``add_args()``."""
        parser = argparse.ArgumentParser(
            description=f"{self.wf_name} — CST optimisation runner"
        )
        parser.add_argument("--config", type=str, default=self.default_config,
                           help="Path to YAML config file")
        self.add_args(parser)
        return parser.parse_args()

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Hook for subclass-specific CLI arguments."""
        pass

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_config(self, path: str = "") -> dict[str, Any]:
        """Load YAML config, optionally CLI-overridden."""
        config_path = path or self.default_config
        with open(config_path, "r", encoding="utf-8") as fh:
            self.cfg = yaml.safe_load(fh)
        return self.cfg

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def setup_logging(self, level: int = logging.INFO) -> str:
        """Configure root logger with file + stream handlers.

        Returns the log directory path.
        """
        log_cfg = self.cfg.get("logging", {})
        self.log_dir = log_cfg.get("output_dir", "runs")
        os.makedirs(self.log_dir, exist_ok=True)

        log_path = os.path.join(self.log_dir, f"{self.wf_name}_runtime.log")
        root = logging.getLogger()
        root.setLevel(level)
        root.handlers.clear()

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        root.addHandler(fh)

        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(formatter)
        root.addHandler(sh)

        _logger.info("%s starting — log: %s", self.wf_name, log_path)
        return self.log_dir

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def setup_checkpoint(self, name: str = "") -> str:
        """Create and load a CheckpointManager.

        Returns the checkpoint path.
        """
        ckpt_name = name or self.wf_name
        ckpt_path = os.path.join(self.log_dir, f"{ckpt_name}.ckpt")
        self.ckpt = CheckpointManager(ckpt_path)
        self.ckpt.load()
        return ckpt_path

    def _on_evaluation(
        self,
        x_phys: np.ndarray,
        raw_values: np.ndarray,
        penalties: np.ndarray,
        solver_ok: bool,
        error: str,
    ) -> None:
        """Shared checkpoint callback — late-binding via ``_wf_ref``."""
        if self.ckpt is None:
            return
        idx = self.ckpt.add_pending(x_phys)
        all_finite = bool(np.all(np.isfinite(raw_values)))
        if all_finite and self._wf_ref:
            metric_names = self._resolve_metric_names()
            raw_dict = dict(zip(metric_names, raw_values))
            pen_dict = dict(zip(metric_names, penalties))
            self.ckpt.mark_completed(idx, raw_values=raw_dict, penalties=pen_dict, solver_ok=solver_ok)
        elif not all_finite:
            self.ckpt.mark_failed(idx, error=error)
        self.ckpt.save()
        self._on_evaluation_record(x_phys, raw_values, penalties, solver_ok, error)

    def _resolve_metric_names(self) -> list[str]:
        """Resolve metric names from the workflow container in ``_wf_ref[0]``."""
        if self._wf_ref:
            return getattr(self._wf_ref[0], "objective_names", [])
        return []

    def _on_evaluation_record(
        self,
        x_phys: np.ndarray,
        raw_values: np.ndarray,
        penalties: np.ndarray,
        solver_ok: bool,
        error: str,
    ) -> None:
        """Hook for JSONL sidecar or other per-evaluation recording."""
        pass

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def install_signal_handler(self) -> None:
        """Install double-tap Ctrl+C handler."""
        runner_ref = self

        def _handler(signum: int, frame: object) -> None:
            runner_ref._interrupt_count[0] += 1
            if runner_ref._interrupt_count[0] == 1:
                print(
                    "\nCtrl+C received — waiting for current CST operation to finish...\n"
                    "  (press Ctrl+C again to force-exit immediately)",
                    flush=True,
                )
            else:
                print("\nForce exiting.", flush=True)
                os._exit(130)

        try:
            signal.signal(signal.SIGINT, _handler)
        except ValueError:
            # SIGINT cannot be set in some environments (e.g. embedded threads)
            _logger.warning("Cannot install SIGINT handler in this environment")

    # ------------------------------------------------------------------
    # Abstract / hook methods
    # ------------------------------------------------------------------

    def build_workflow(self) -> tuple[Any, Any, Callable[[np.ndarray], Any]]:
        """Build workflow container, optimizer, and evaluator.

        Subclasses must implement.
        """
        raise NotImplementedError("Subclass must implement build_workflow()")

    def cleanup(self) -> None:
        """Close CST connections, stop heartbeat, etc.

        Called in ``finally`` block.  Subclasses may override.
        """
        pass

    def load_prior_data(self) -> tuple | None:
        """Load prior evaluation data for GP warm-start.

        Returns ``(X, y)`` or ``None``.  Subclasses may override.
        """
        return None

    # ------------------------------------------------------------------
    # Optimize loop
    # ------------------------------------------------------------------

    def _run_optimize(
        self,
        opt: Any,
        evaluator: Callable[[np.ndarray], Any],
    ) -> Any:
        """Run the main optimization loop with try/except/finally."""
        prior_data = self.load_prior_data()
        result = None
        try:
            result = opt.optimize(evaluator=evaluator, prior_data=prior_data)
            self._print_result(result)
            if self.ckpt:
                self.ckpt.clear()
            return result
        except KeyboardInterrupt:
            print("\nInterrupted by user (Ctrl+C) — shutting down...")
            sys.exit(130)
        except Exception:
            _logger.exception("%s failed", self.wf_name)
            if self.ckpt:
                print(
                    f"Checkpoint preserved at {self.ckpt._path} "
                    f"({self.ckpt.completed_count} completed)"
                )
            raise
        finally:
            self.cleanup()

    def _print_result(self, result: Any) -> None:
        """Print optimization result summary."""
        if result is None:
            return
        print("=" * 60)
        print(f"{self.wf_name} complete.")
        print(f"Total evaluations: {result.n_evaluations}")
        print(f"Best params (physical): {result.x_opt}")
        print(f"Best objective value: {result.f_opt}")
