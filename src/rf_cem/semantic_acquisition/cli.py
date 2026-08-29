"""Command line for deterministic Semantic Acquisition probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .a0_coverage import A0SourceSet, write_a0_bundle
from .boundary_signals import BoundarySignalError, DEFAULT_SAMPLE_COUNTS, SignalParameters


def build_parser() -> argparse.ArgumentParser:
    """Create the Semantic Acquisition command parser."""

    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.semantic_acquisition",
        description="Run deterministic no-CST Semantic Acquisition probes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    coverage = subparsers.add_parser(
        "a0-coverage", help="measure deterministic landmark coverage of reviewed junctions"
    )
    coverage.add_argument("--root", type=Path, default=Path.cwd())
    coverage.add_argument("--compile-record", type=Path, required=True)
    coverage.add_argument("--instance-graph", type=Path, required=True)
    coverage.add_argument("--output-root", type=Path, required=True)
    coverage.add_argument("--sample-count", type=int, action="append", dest="sample_counts")
    coverage.add_argument("--merge-distance-u", type=float, default=0.005)
    coverage.add_argument("--stability-tolerance-u", type=float, default=0.005)
    coverage.add_argument("--radius-prominence-mm", type=float, default=0.001)
    coverage.add_argument(
        "--curvature-prominence-per-mm", type=float, default=0.002
    )
    coverage.add_argument("--curvature-zero-per-mm", type=float, default=0.0001)
    coverage.add_argument("--c0-gap-threshold-mm", type=float, default=1.0e-6)
    coverage.add_argument("--g1-angle-threshold-deg", type=float, default=2.0)
    coverage.add_argument("--coverage-tolerance-u", type=float, default=0.02)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one no-CST A0 build and print a compact JSON result."""

    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    parameters = SignalParameters(
        sample_counts=tuple(args.sample_counts or DEFAULT_SAMPLE_COUNTS),
        merge_distance_u=args.merge_distance_u,
        stability_tolerance_u=args.stability_tolerance_u,
        radius_prominence_mm=args.radius_prominence_mm,
        curvature_prominence_per_mm=args.curvature_prominence_per_mm,
        curvature_zero_per_mm=args.curvature_zero_per_mm,
        c0_gap_threshold_mm=args.c0_gap_threshold_mm,
        g1_angle_threshold_deg=args.g1_angle_threshold_deg,
    )
    try:
        result = write_a0_bundle(
            A0SourceSet(
                repo_root=root,
                compile_record=_resolve(root, args.compile_record),
                instance_graph=_resolve(root, args.instance_graph),
            ),
            _resolve(root, args.output_root),
            parameters=parameters,
            coverage_tolerance_u=args.coverage_tolerance_u,
        )
    except (BoundarySignalError, FileExistsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    coverage = result.report["coverage"]
    print(
        json.dumps(
            {
                "bundle_id": result.bundle_id,
                "path": str(result.path),
                "input_sha256": result.input_sha256,
                "instance_id": result.report["instance"]["instance_id"],
                "all_truth_hit": coverage["all_truth_hit"],
                "hit_truth_count": coverage["hit_truth_count"],
                "truth_junction_count": coverage["truth_junction_count"],
                "candidate_count": coverage["candidate_count"],
                "extra_candidate_count": coverage["extra_candidate_count"],
                "unstable_candidate_count": coverage["unstable_candidate_count"],
                "live_cst_status": "not_run",
            },
            sort_keys=True,
        )
    )
    return 0


def _resolve(root: Path, value: Path) -> Path:
    return (value if value.is_absolute() else root / value).resolve()


__all__ = ["build_parser", "main"]
