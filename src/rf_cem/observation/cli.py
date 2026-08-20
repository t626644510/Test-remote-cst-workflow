"""Command-line entry points for deterministic R4 proof bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifacts import R4SourceSet, load_r4_bundle, write_r4_bundle


def build_parser() -> argparse.ArgumentParser:
    """Create the strict R4 command parser."""

    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.observation",
        description="Build or validate no-CST RF-CEM R4 observation proofs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build both canonical observations")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument("--compile-record", type=Path, action="append", required=True)
    build.add_argument("--instance-graph", type=Path, action="append", required=True)
    build.add_argument(
        "--architecture-document",
        type=Path,
        default=Path("docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md"),
    )
    build.add_argument("--samples-per-region", type=int, default=65)
    build.add_argument("--authored-by", default="rf-cem-r4-contract-review")
    validate = subparsers.add_parser("validate", help="strictly reload one R4 bundle")
    validate.add_argument("--root", type=Path, default=Path.cwd())
    validate.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one R4 build/validate command and emit a compact JSON result."""

    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "build":
        result = write_r4_bundle(
            R4SourceSet(
                repo_root=root,
                compile_records=tuple(_resolve(root, item) for item in args.compile_record),
                instance_graphs=tuple(_resolve(root, item) for item in args.instance_graph),
                architecture_document=_resolve(root, args.architecture_document),
            ),
            _resolve(root, args.output_root),
            samples_per_region=args.samples_per_region,
            authored_by=args.authored_by,
        )
    else:
        result = load_r4_bundle(_resolve(root, args.bundle), repo_root=root)
    print(
        json.dumps(
            {
                "bundle_id": result.bundle_id,
                "path": str(result.path),
                "input_sha256": result.input_sha256,
                "instance_ids": [
                    item.exact_geometry.instance_id for item in result.instances
                ],
                "constraint_count": len(result.constraints),
                "evaluation_count": sum(
                    len(item.evaluations) for item in result.instances
                ),
                "live_cst_status": "not_run",
                "physical_acceptance_status": "not_established",
            },
            sort_keys=True,
        )
    )
    return 0


def _resolve(root: Path, value: Path) -> Path:
    return (value if value.is_absolute() else root / value).resolve()


__all__ = ["build_parser", "main"]
