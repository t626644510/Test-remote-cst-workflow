from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from workflows.rfgun_tolerance.run import (
    _apply_config_overrides,
    _positive_float,
    build_arg_parser,
)


def test_positive_float_accepts_positive_scale() -> None:
    assert _positive_float("2.5") == 2.5


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_positive_float_rejects_non_positive_scale(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_float(value)


def test_tolerance_scale_requires_at_least_one_value() -> None:
    parser = build_arg_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--tolerance-scale"])


def test_output_dir_override_sets_a_usable_database_path() -> None:
    config = SimpleNamespace(
        max_samples=100,
        output_dir="old",
        db_path="old/evaluations.db",
    )

    _apply_config_overrides(
        config,
        n_samples=60,
        output_dir="runs/tolerance",
    )

    assert config.max_samples == 60
    assert config.output_dir == "runs/tolerance"
    assert Path(config.db_path) == Path("runs/tolerance/tolerance_eval.db")
