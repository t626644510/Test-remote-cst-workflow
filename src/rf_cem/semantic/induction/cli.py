"""Command-line entry points for deterministic R3 proof bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .artifacts import R3SourceSet, load_r3_bundle, write_r3_bundle
from .contracts import InductionContractError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.semantic.induction",
        description="Build or validate the no-CST R3 family-induction proof.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build one immutable accepted-review proof")
    build.add_argument("--repo-root", type=Path, default=Path.cwd())
    build.add_argument("--family-grammar", type=Path, required=True)
    build.add_argument(
        "--training-graph",
        type=Path,
        action="append",
        required=True,
        help="repeat exactly twice for canonical SLS-2 and RF500 graphs",
    )
    build.add_argument("--lerec-design-pdf", type=Path, required=True)
    build.add_argument("--lerec-test-pdf", type=Path, required=True)
    build.add_argument("--representation-core", type=Path)
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument(
        "--review-decision",
        choices=("accepted", "rejected", "needs_evidence"),
        required=True,
    )
    build.add_argument("--reviewer-id", required=True)
    build.add_argument("--review-rationale", required=True)
    build.add_argument("--review-revision", type=int, default=0)

    validate = subparsers.add_parser("validate", help="reload and hash-check one R3 bundle")
    validate.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            kwargs = {}
            if args.representation_core is not None:
                kwargs["representation_core"] = args.representation_core
            bundle = write_r3_bundle(
                R3SourceSet(
                    repo_root=args.repo_root,
                    family_grammar=args.family_grammar,
                    training_graphs=tuple(args.training_graph),
                    lerec704_ipac2015_pdf=args.lerec_design_pdf,
                    lerec704_design_and_test_2018_pdf=args.lerec_test_pdf,
                    **kwargs,
                ),
                args.output_root,
                review_decision=args.review_decision,
                reviewer_id=args.reviewer_id,
                review_rationale=args.review_rationale,
                review_revision=args.review_revision,
            )
        else:
            bundle = load_r3_bundle(args.bundle)
    except (OSError, ValueError, InductionContractError) as exc:
        print(f"R3 induction error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "pass",
                "bundle": str(bundle.path),
                "bundle_id": bundle.bundle_id,
                "input_sha256": bundle.input_sha256,
                "alignment_id": bundle.alignment.alignment_id,
                "proposal_id": bundle.proposal.proposal_id,
                "review_decision": bundle.review.decision,
                "patch_id": bundle.patch.patch_id,
                "patched_grammar_id": bundle.patched_grammar.grammar_id,
                "blind_instance_id": bundle.blind_graph.instance_id,
                "blind_classification": bundle.blind_validation.classification,
                "live_cst_status": "not_run",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


__all__ = ["build_parser", "main"]
