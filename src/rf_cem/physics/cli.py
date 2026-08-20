"""CLI for deterministic no-CST R5 readiness bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifacts import R5ReadinessSourceSet, load_r5_bundle, write_r5_readiness_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.physics",
        description="Build or validate RF-CEM R5 contracts without invoking CST.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-readiness", help="build planned R5 contracts")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument("--r4-bundle", type=Path, required=True)
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument(
        "--architecture-document",
        type=Path,
        default=Path("docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md"),
    )
    build.add_argument(
        "--interface-document",
        type=Path,
        default=Path("docs/CST_AUTOMATION_INTERFACES.md"),
    )
    build.add_argument(
        "--goal-document",
        type=Path,
        default=Path(".agent/goals/RF-CEM_Codex_Goal_R0B-R5.md"),
    )
    validate = subparsers.add_parser("validate", help="strictly replay one R5 bundle")
    validate.add_argument("--root", type=Path, default=Path.cwd())
    validate.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "build-readiness":
        bundle = write_r5_readiness_bundle(
            R5ReadinessSourceSet(
                repo_root=root,
                r4_bundle=_resolve(root, args.r4_bundle),
                architecture_document=_resolve(root, args.architecture_document),
                interface_document=_resolve(root, args.interface_document),
                goal_document=_resolve(root, args.goal_document),
            ),
            _resolve(root, args.output_root),
        )
    else:
        bundle = load_r5_bundle(_resolve(root, args.bundle), repo_root=root)
    print(
        json.dumps(
            {
                "bundle_id": bundle.bundle_id,
                "path": str(bundle.path),
                "input_sha256": bundle.input_sha256,
                "case_count": len(bundle.cases),
                "metric_contract_count": len(bundle.metric_contracts),
                "metric_observation_count": sum(
                    len(item.metric_observations) for item in bundle.cases
                ),
                "live_cst_status": bundle.manifest["live_cst_status"],
                "live_cst_authorization": bundle.manifest["live_cst_authorization"],
                "physical_acceptance_status": bundle.manifest[
                    "physical_acceptance_status"
                ],
                "sls2_link_status": next(
                    item.link_status
                    for item in bundle.links
                    if item.geometry.instance_id.startswith("sls2.")
                ),
            },
            sort_keys=True,
        )
    )
    return 0


def _resolve(root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (root / value).resolve()


__all__ = ["build_parser", "main"]
