#!/usr/bin/env python
"""Tolerance analysis CLI entry point.

Two modes:
- ``python -m workflows.rfgun_tolerance.run`` — CST sampling
- ``python -m workflows.rfgun_tolerance.cli`` — analysis (existing)

Usage:
    python -m workflows.rfgun_tolerance.run --config config/default.yaml
    python -m workflows.rfgun_tolerance.run --config my_tolerance.yaml --n-samples 50
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tolerance sampling runner — CST batch evaluation",
    )
    parser.add_argument(
        "--config", type=str, default="config/default.yaml",
        help="Path to YAML config with 'tolerance:' section (default: config/default.yaml)",
    )
    parser.add_argument(
        "--n-samples", type=int, default=None,
        help="Override max_samples from config",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Override output_dir from config",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    from workflows.rfgun_tolerance.runner import load_tolerance_config, ToleranceSampler

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    cfg = load_tolerance_config(str(config_path))
    if args.n_samples is not None:
        cfg.max_samples = args.n_samples
    if args.output_dir is not None:
        cfg.output_dir = args.output_dir

    sampler = ToleranceSampler(cfg)
    try:
        n = sampler.run()
        print(f"\nDone. {n} evaluations written to {cfg.db_path}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        sampler.close()


if __name__ == "__main__":
    main()
