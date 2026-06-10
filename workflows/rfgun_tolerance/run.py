#!/usr/bin/env python
"""Tolerance analysis CLI entry point.

Usage:
    python -m workflows.rfgun_tolerance.run --config config/default.yaml
    python -m workflows.rfgun_tolerance.run --config my_tolerance.yaml --n-samples 50
    python -m workflows.rfgun_tolerance.run ... --tolerance-scale 2.33 4.0 8.33
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
    parser.add_argument(
        "--recover", action="store_true", default=False,
        help="Recover mode: only re-run previously failed records, no new samples.",
    )
    parser.add_argument(
        "--tolerance-scale", type=float, nargs="*", default=None,
        help="Multiply all tolerance_abs values by this factor "
             "(e.g. 2.33 for 7um from 3um baseline). "
             "Multiple values run multiple levels in sequence: "
             "--tolerance-scale 2.33 4.0 8.33",
    )
    return parser


def _run_one(cfg, scale=None, recover=False):
    """Run a single tolerance sampling batch. Returns number of evaluations."""
    from workflows.rfgun_tolerance.runner import ToleranceSampler

    if scale is not None:
        base_um = float(cfg.parameters[0].tolerance_abs) * 1000.0 if cfg.parameters else 3.0
        scaled_um = base_um * scale
        rounded = round(scaled_um)
        if abs(scaled_um - rounded) < 0.05:
            level_str = f"{rounded}um"
        else:
            level_str = f"{scaled_um:.1f}um"

        for p in cfg.parameters:
            p.tolerance_abs = round(p.tolerance_abs * scale, 10)

        import os as _os
        orig_db = cfg.db_path
        db_dir = _os.path.dirname(orig_db) or cfg.output_dir
        db_name = _os.path.basename(orig_db) or "tolerance_eval.db"
        stem, ext = _os.path.splitext(db_name)
        cfg.db_path = _os.path.join(db_dir, f"{stem}_{level_str}{ext}")
        cfg.output_dir = _os.path.join(cfg.output_dir, level_str)

        print(f"\n{'='*60}")
        print(f"Tolerance scale: {scale:.3f}x -> {level_str} "
              f"(base={base_um:.0f}um)")
        print(f"DB: {cfg.db_path}")
        print(f"{'='*60}")

    sampler = ToleranceSampler(cfg)
    try:
        n = sampler.run(recover_only=recover)
        print(f"Done. {n} evaluations -> {cfg.db_path}")
        return n
    except KeyboardInterrupt:
        print("Interrupted.")
        raise
    finally:
        sampler.close()


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    from workflows.rfgun_tolerance.runner import load_tolerance_config

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    scales = args.tolerance_scale
    if scales is None:
        scales = [None]  # single run, no scaling

    total = 0
    for i, scale in enumerate(scales):
        cfg = load_tolerance_config(str(config_path))
        if args.n_samples is not None:
            cfg.max_samples = args.n_samples
        if args.output_dir is not None:
            cfg.output_dir = args.output_dir
            cfg.db_path = ""

        try:
            n = _run_one(cfg, scale=scale, recover=args.recover)
            total += n
        except KeyboardInterrupt:
            print(f"\nInterrupted after {i + 1}/{len(scales)} levels.")
            sys.exit(130)

    print(f"\nAll done. {total} total evaluations across {len(scales)} level(s).")


if __name__ == "__main__":
    main()
