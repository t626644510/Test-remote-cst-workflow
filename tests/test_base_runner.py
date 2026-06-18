from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cst_optimization.runner import BaseRunner


class _Optimizer:
    def optimize(self, **kwargs):
        return SimpleNamespace(
            n_evaluations=1,
            x_opt=np.array([1.0]),
            f_opt=0.0,
        )


class _Runner(BaseRunner):
    def __init__(self) -> None:
        super().__init__("test")
        self.cleanup_calls = 0

    def parse_args(self):
        return SimpleNamespace()

    def load_config(self, path: str = ""):
        self.cfg = {}
        return self.cfg

    def setup_logging(self, level=20):
        return "runs"

    def setup_checkpoint(self, name: str = ""):
        self.ckpt = None
        return ""

    def install_signal_handler(self) -> None:
        return None

    def build_workflow(self):
        workflow = SimpleNamespace(objective_names=["metric"])
        return workflow, _Optimizer(), lambda values: values

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def test_run_cleans_up_exactly_once() -> None:
    runner = _Runner()

    runner.run()

    assert runner.cleanup_calls == 1
